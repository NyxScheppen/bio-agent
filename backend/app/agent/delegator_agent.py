"""
Delegator Agent (Phase 3.2).

在 Planner 之后判断复杂任务是否应拆分为子Agent 并行执行。
参考 Hermes agent 的 Delegator 模式。

用法:
    from app.agent.delegator_agent import run_delegator_agent
    result = run_delegator_agent(context_pack, planner_result)
    # result: {"should_delegate": bool, "sub_tasks": [...]}
"""

from typing import Any, Dict, Optional

from app.agent.router_agent import call_json_agent
from app.agent.skills.skill_models import SkillSpec
from app.agent.skills.tool_policy import allowed_tool_names_for_skill

DELEGATOR_PROMPT = """
你是 Delegator Agent，负责判断复杂的生信分析任务是否应该拆分为子任务并行执行。

你必须输出严格 JSON，不要 Markdown。

判断标准：
1. Planner 步骤数 >= 3 → 可能适合并行
2. 步骤之间有明确的依赖关系 → 不能完全并行
3. 两个步骤使用不同工具、不同数据 → 可以并行
4. 步骤数据依赖前一阶段的结果 → 必须串行

输出格式：
{
  "should_delegate": true/false,
  "reason": "简短判断依据",
  "sub_tasks": [
    {
      "goal": "子任务目标",
      "tool": "工具名",
      "args": {"file_path": "...", ...},
      "depends_on": []
    }
  ]
}

依赖关系：
- depends_on: [] 表示无依赖，可以和其它同样无依赖的任务并行
- depends_on: [0] 表示依赖索引 0 的任务完成

重要：
1. 只拆分确实可以并行的步骤
2. 不要编造不存在的工具名
3. 参数优先复制 Planner 的 parameters；缺失时再根据 parameter_strategy 补全
4. 如果不确定是否可并行，should_delegate=false
5. args 中引用前置子任务时使用精确值 "$step_N"，N 是从 0 开始的 sub_tasks 列表索引
"""


def run_delegator_agent(
    context_pack: Dict[str, Any],
    planner_result: Dict[str, Any],
    selected_skill: Optional[SkillSpec] = None,
) -> Dict[str, Any]:
    """
    判断是否应拆分子Agent。

    Args:
        context_pack: 上下文包
        planner_result: Planner 的输出

    Returns:
        {"should_delegate": bool, "reason": str, "sub_tasks": [...]}
    """
    steps = planner_result.get("steps", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        return {"should_delegate": False, "reason": "Planner steps 格式无效", "sub_tasks": []}
    if len(steps) < 3:
        return {"should_delegate": False, "reason": "步骤数不足3，无并行收益", "sub_tasks": []}

    # 检查是否已有 parallel_groups（Planner 自己判断了）
    if planner_result.get("parallel_groups"):
        try:
            sub_tasks = _steps_to_sub_tasks(
                steps,
                planner_result.get("step_dependencies", {}),
                planner_result.get("parallel_groups", []),
            )
        except (TypeError, ValueError):
            return {
                "should_delegate": False,
                "reason": "Planner 的步骤或依赖格式无效",
                "sub_tasks": [],
            }
        result = {
            "should_delegate": True,
            "reason": "Planner 已标注 parallel_groups",
            "sub_tasks": sub_tasks,
        }
    else:
        payload = {
            "latest_user_message": context_pack.get("latest_user_message", ""),
            "planner_objective": planner_result.get("objective", ""),
            "steps": [
                {
                    "step_id": s.get("step_id"),
                    "goal": s.get("goal", ""),
                    "preferred_tools": s.get("preferred_tools", []),
                    "parameters": s.get("parameters", {}),
                    "parameter_strategy": s.get("parameter_strategy", ""),
                }
                for s in steps
            ],
            "available_tools": [
                t.get("name", "")
                for t in (planner_result.get("available_tools", []) or [])
            ][:30],
        }

        result = call_json_agent(DELEGATOR_PROMPT, payload)
        if "error" in result:
            return {
                "should_delegate": False,
                "reason": "Delegator LLM 调用失败",
                "sub_tasks": [],
            }
        if not result:
            return {
                "should_delegate": False,
                "reason": "Delegator 无法解析",
                "sub_tasks": [],
            }

    if (
        not isinstance(result, dict)
        or not isinstance(result.get("should_delegate"), bool)
        or not isinstance(result.get("sub_tasks", []), list)
    ):
        return {
            "should_delegate": False,
            "reason": "Delegator 输出格式无效",
            "sub_tasks": [],
        }

    # 验证子任务结构、工具名和依赖索引，避免把坏计划送进调度器。
    if result.get("should_delegate") and result.get("sub_tasks"):
        from app.agent.tool_registry import TOOL_REGISTRY

        allowed_tools = allowed_tool_names_for_skill(selected_skill, TOOL_REGISTRY)
        valid_tasks = []
        task_count = len(result["sub_tasks"])
        for index, task in enumerate(result["sub_tasks"]):
            if not isinstance(task, dict):
                continue
            t = dict(task)
            tool_name = t.get("tool", "")
            args = t.get("args", {})
            raw_dependencies = t.get("depends_on", [])
            raw_schedule_after = t.get("schedule_after", [])
            if tool_name not in TOOL_REGISTRY:
                print(f"[Delegator] 跳过不存在的工具: {tool_name}")
                continue
            if tool_name not in allowed_tools:
                print(f"[Delegator] Skill 工具策略拒绝: {tool_name}")
                continue
            if (
                not isinstance(args, dict)
                or not isinstance(raw_dependencies, list)
                or not isinstance(raw_schedule_after, list)
            ):
                continue

            try:
                dependencies = list(dict.fromkeys(int(dep) for dep in raw_dependencies))
                schedule_after = list(
                    dict.fromkeys(int(dep) for dep in raw_schedule_after)
                )
            except (TypeError, ValueError):
                continue
            if any(
                dep < 0 or dep >= task_count or dep == index
                for dep in dependencies + schedule_after
            ):
                continue

            t["args"] = args
            t["depends_on"] = dependencies
            t["schedule_after"] = schedule_after
            # Delegator 输出来自 LLM。除非未来工具元数据显式声明可安全重试，
            # 委派任务采用至多一次执行语义。
            t["max_retries"] = 0
            try:
                t["timeout"] = max(10, min(int(t.get("timeout", 600)), 3600))
            except (TypeError, ValueError):
                continue
            valid_tasks.append(t)
        result["sub_tasks"] = valid_tasks
        if len(valid_tasks) != task_count:
            result["should_delegate"] = False
            result["reason"] = "Delegator 子任务包含无效工具、参数或依赖"

    return result


def _steps_to_sub_tasks(
    steps: list,
    dependencies: dict,
    parallel_groups: Optional[list] = None,
) -> list:
    """将 Planner 步骤转换为子Agent 任务列表。"""
    tasks = []
    id_to_index: Dict[int, int] = {}
    for index, step in enumerate(steps):
        step_id = int(step["step_id"])
        if step_id in id_to_index:
            raise ValueError(f"重复 step_id: {step_id}")
        id_to_index[step_id] = index
    for s in steps:
        sid = int(s["step_id"])
        tools = s.get("preferred_tools", [])
        raw_dependencies = dependencies.get(sid, dependencies.get(str(sid), []))
        if not isinstance(raw_dependencies, list):
            raise ValueError(f"步骤 {sid} 的依赖必须是列表")
        normalized_dependencies = []
        for dependency in raw_dependencies:
            dependency_id = int(dependency)
            if dependency_id not in id_to_index:
                raise ValueError(f"步骤 {sid} 依赖未知步骤 {dependency_id}")
            dependency_index = id_to_index[dependency_id]
            if dependency_index == id_to_index[sid]:
                raise ValueError(f"步骤 {sid} 不能依赖自身")
            if dependency_index not in normalized_dependencies:
                normalized_dependencies.append(dependency_index)
        tasks.append({
            "goal": s.get("goal", ""),
            "tool": tools[0] if tools else "",
            "args": _remap_step_references(
                dict(s.get("parameters", {}) or {}),
                id_to_index,
            ),
            "depends_on": normalized_dependencies,
            "schedule_after": [],
            "max_retries": 0,
            "timeout": max(10, min(int(s.get("timeout", 600) or 600), 3600)),
        })

    if parallel_groups:
        from app.agent.parallel_executor import _build_execution_batches

        batches = _build_execution_batches(steps, dependencies, parallel_groups)
        previous_batch_indexes: list[int] = []
        for batch in batches:
            current_indexes = [id_to_index[int(step["step_id"])] for step in batch]
            for task_index in current_indexes:
                for prerequisite_index in previous_batch_indexes:
                    if prerequisite_index not in tasks[task_index]["schedule_after"]:
                        tasks[task_index]["schedule_after"].append(prerequisite_index)
            previous_batch_indexes.extend(current_indexes)
    return tasks


def _remap_step_references(value: Any, id_to_index: Dict[int, int]) -> Any:
    """把 Planner 的 ``$step_<id>`` 引用转换成子任务索引引用。"""
    if isinstance(value, dict):
        return {
            key: _remap_step_references(item, id_to_index)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_remap_step_references(item, id_to_index) for item in value]
    if not isinstance(value, str) or not value.startswith("$step_"):
        return value
    try:
        step_id = int(value[len("$step_"):])
    except ValueError:
        raise ValueError(f"无效步骤引用: {value}")
    if step_id not in id_to_index:
        raise ValueError(f"引用未知步骤: {value}")
    return f"$step_{id_to_index[step_id]}"
