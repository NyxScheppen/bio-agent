"""
Delegator Agent (Phase 3.2).

在 Planner 之后判断复杂任务是否应拆分为子Agent 并行执行。
参考 Hermes agent 的 Delegator 模式。

用法:
    from app.agent.delegator_agent import run_delegator_agent
    result = run_delegator_agent(context_pack, planner_result)
    # result: {"should_delegate": bool, "sub_tasks": [...]}
"""

import json
from typing import Any, Dict, List, Optional

from app.core.config import MODEL_NAME
from app.agent.llm_client import client
from app.agent.agent_utils import extract_json_object

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
3. 参数从 Planner 的 parameter_strategy 中提取
4. 如果不确定是否可并行，should_delegate=false
"""


def run_delegator_agent(
    context_pack: Dict[str, Any],
    planner_result: Dict[str, Any],
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
    if len(steps) < 3:
        return {"should_delegate": False, "reason": "步骤数不足3，无并行收益", "sub_tasks": []}

    # 检查是否已有 parallel_groups（Planner 自己判断了）
    if planner_result.get("parallel_groups"):
        return {
            "should_delegate": True,
            "reason": "Planner 已标注 parallel_groups",
            "sub_tasks": _steps_to_sub_tasks(steps, planner_result.get("step_dependencies", {})),
        }

    payload = {
        "latest_user_message": context_pack.get("latest_user_message", ""),
        "planner_objective": planner_result.get("objective", ""),
        "steps": [
            {
                "step_id": s.get("step_id"),
                "goal": s.get("goal", ""),
                "preferred_tools": s.get("preferred_tools", []),
                "parameter_strategy": s.get("parameter_strategy", ""),
            }
            for s in steps
        ],
        "available_tools": [
            t.get("name", "") for t in (planner_result.get("available_tools", []) or [])
        ][:30],
    }

    try:
        messages = [
            {"role": "system", "content": DELEGATOR_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        result = extract_json_object(content)
    except Exception:
        return {"should_delegate": False, "reason": "Delegator LLM 调用失败", "sub_tasks": []}

    if not result:
        return {"should_delegate": False, "reason": "Delegator 无法解析", "sub_tasks": []}

    # 验证 sub_tasks 中的工具是否存在
    if result.get("should_delegate") and result.get("sub_tasks"):
        from app.agent.tool_registry import TOOL_REGISTRY
        valid_tasks = []
        for t in result["sub_tasks"]:
            tool_name = t.get("tool", "")
            if tool_name in TOOL_REGISTRY:
                valid_tasks.append(t)
            else:
                print(f"[Delegator] 跳过不存在的工具: {tool_name}")
        result["sub_tasks"] = valid_tasks
        if not valid_tasks:
            result["should_delegate"] = False

    return result


def _steps_to_sub_tasks(steps: list, dependencies: dict) -> list:
    """将 Planner 步骤转换为子Agent 任务列表。"""
    tasks = []
    for s in steps:
        sid = s.get("step_id", 0)
        tools = s.get("preferred_tools", [])
        tasks.append({
            "goal": s.get("goal", ""),
            "tool": tools[0] if tools else "",
            "args": {},
            "depends_on": dependencies.get(sid, []),
        })
    return tasks
