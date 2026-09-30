"""
多Agent 编排器 (Phase 3.3: Kanban Orchestrator).

参考 Hermes agent 的 Kanban 多Agent 编排模式。
管理长时间多步骤分析的 TODO → IN_PROGRESS → DONE 状态流转。

用法:
    from app.agent.orchestrator import Orchestrator
    orch = Orchestrator()
    orch.add_task("deg_analysis", {"tool": "run_bulk_rnaseq_deg_analysis", ...})
    orch.add_task("enrichment", {"tool": "run_enrichment_analysis", ...}, depends_on=["deg_analysis"])
    results = orch.run_all(session_id="abc123")
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from app.agent.sub_agent_manager import (
    SubAgentManager,
    SubAgentTask,
    SubAgentResult,
    sub_agent_manager,
)
from app.agent.agent_utils import to_plain_dict


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


class KanbanTask:
    """Kanban 板上的单个任务。"""

    def __init__(
        self,
        task_id: str,
        name: str,
        tool: str,
        args: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
        schedule_after: Optional[List[str]] = None,
        max_retries: int = 0,
        timeout: int = 600,
    ):
        self.task_id = task_id
        self.name = name
        self.tool = tool
        self.args = args or {}
        self.depends_on = depends_on or []
        self.schedule_after = schedule_after or []
        self.max_retries = max_retries
        self.timeout = timeout
        self.status: TaskStatus = TaskStatus.TODO
        self.result: Optional[SubAgentResult] = None
        self.error: Optional[str] = None

    def can_start(self, completed_ids: set, terminal_ids: set) -> bool:
        """检查所有依赖是否已完成。"""
        if self.status != TaskStatus.TODO:
            return False
        return (
            all(dep in completed_ids for dep in self.depends_on)
            and all(dep in terminal_ids for dep in self.schedule_after)
        )

    def mark_blocked(self, reason: str = "依赖任务失败") -> None:
        """标记为阻塞（依赖任务失败）。"""
        self.status = TaskStatus.BLOCKED
        self.error = reason


class Orchestrator:
    """
    Kanban 编排器。

    管理多步骤生信分析流程:
    1. 添加任务（带依赖声明）
    2. 按批次执行（TODO → IN_PROGRESS → DONE）
    3. 处理依赖失败时的级联阻塞
    4. 输出结构化结果

    用法:
        orch = Orchestrator()
        orch.add_task("step1", "PCA分析", "run_bulk_pca_analysis", {"expression_file": "..."})
        orch.add_task("step2", "差异分析", "run_bulk_rnaseq_deg_analysis", {...}, depends_on=["step1"])
        results = orch.run_all()
    """

    def __init__(self, manager: Optional[SubAgentManager] = None):
        self.tasks: Dict[str, KanbanTask] = {}
        self._manager = manager or sub_agent_manager

    def add_task(
        self,
        task_id: str,
        name: str,
        tool: str,
        args: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
        schedule_after: Optional[List[str]] = None,
        max_retries: int = 0,
        timeout: int = 600,
    ) -> "Orchestrator":
        """添加一个任务到 Kanban 板。"""
        self.tasks[task_id] = KanbanTask(
            task_id=task_id,
            name=name,
            tool=tool,
            args=args,
            depends_on=depends_on,
            schedule_after=schedule_after,
            max_retries=max_retries,
            timeout=timeout,
        )
        return self  # 链式调用

    def add_tasks_from_planner(
        self,
        steps: List[Dict[str, Any]],
        step_dependencies: Optional[Dict[Any, List[Any]]] = None,
    ) -> "Orchestrator":
        """从 Planner 步骤自动添加任务。"""
        for s in steps:
            sid = str(s.get("step_id", ""))
            tools = s.get("preferred_tools", [])
            deps: List[Any] = []
            if step_dependencies:
                numeric_id = int(s.get("step_id", 0))
                deps = step_dependencies.get(
                    numeric_id,
                    step_dependencies.get(str(numeric_id), []),
                )
            self.add_task(
                task_id=sid,
                name=s.get("goal", ""),
                tool=tools[0] if tools else "",
                args=dict(s.get("parameters", {}) or {}),
                depends_on=[str(d) for d in deps],
                max_retries=int(s.get("max_retries", 0) or 0),
                timeout=int(s.get("timeout", 600) or 600),
            )
        return self

    def run_all(self, session_id: str = "") -> Dict[str, Any]:
        """
        执行所有任务，按依赖分批。

        Returns:
            {
                "completed": [...],
                "failed": [...],
                "blocked": [...],
                "summary": "完成 3/5 个任务"
            }
        """
        completed_ids: set = set()
        failed_ids: set = set()
        blocked_ids: set = set()

        max_iterations = max(1, len(self.tasks) * 2)
        iteration = 0

        while (
            len(completed_ids) + len(failed_ids) + len(blocked_ids) < len(self.tasks)
            and iteration < max_iterations
        ):
            iteration += 1

            # 找可启动的任务
            ready = []
            for tid, task in self.tasks.items():
                if task.status == TaskStatus.TODO:
                    unknown_dependencies = [
                        dep
                        for dep in task.depends_on + task.schedule_after
                        if dep not in self.tasks
                    ]
                    if unknown_dependencies:
                        task.mark_blocked(f"未知依赖: {unknown_dependencies}")
                        blocked_ids.add(tid)
                        continue

                    # 检查是否有依赖失败
                    has_failed_dep = any(
                        dep in failed_ids or dep in blocked_ids
                        for dep in task.depends_on
                    )
                    if has_failed_dep:
                        task.mark_blocked("依赖任务失败")
                        blocked_ids.add(tid)
                        continue

                    terminal_ids = completed_ids | failed_ids | blocked_ids
                    if task.can_start(completed_ids, terminal_ids):
                        ready.append(task)

            if not ready:
                # 没有可执行任务：要么全完成了，要么存在循环依赖
                remaining_todo = [
                    t for t in self.tasks.values()
                    if t.status == TaskStatus.TODO
                ]
                if remaining_todo:
                    for task in remaining_todo:
                        task.mark_blocked("循环或不可解析依赖")
                        blocked_ids.add(task.task_id)
                break

            # 构建 SubAgentTask 列表
            sub_tasks = []
            task_id_map = {}
            for task in ready:
                try:
                    resolved_args = self._resolve_task_references(
                        task.args,
                        declared_dependencies=set(task.depends_on),
                    )
                except ValueError as exc:
                    task.mark_blocked(str(exc))
                    blocked_ids.add(task.task_id)
                    continue

                sub_task_index = len(sub_tasks)
                sub_tasks.append(SubAgentTask(
                    goal=task.name,
                    tool=task.tool,
                    args=resolved_args,
                    max_retries=task.max_retries,
                    timeout=task.timeout,
                ))
                task_id_map[sub_task_index] = task.task_id
                task.status = TaskStatus.IN_PROGRESS

            if not sub_tasks:
                continue

            # 并行执行
            results = self._manager.spawn_and_collect_all(sub_tasks, session_id)

            # 处理结果
            for i, result in enumerate(results):
                tid = task_id_map.get(i)
                if not tid:
                    continue
                task = self.tasks[tid]
                task.result = result

                if result.status == "success":
                    task.status = TaskStatus.DONE
                    completed_ids.add(tid)
                else:
                    task.status = TaskStatus.FAILED
                    failed_ids.add(tid)
                    task.error = result.message

        for task in self.tasks.values():
            if task.status == TaskStatus.TODO:
                task.mark_blocked("达到调度迭代上限")

        # 汇总
        completed = [t for t in self.tasks.values() if t.status == TaskStatus.DONE]
        failed = [t for t in self.tasks.values() if t.status == TaskStatus.FAILED]
        blocked = [t for t in self.tasks.values() if t.status == TaskStatus.BLOCKED]

        return {
            "completed": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "tool": t.tool,
                    "args": t.args,
                    "message": t.result.message if t.result else "",
                    "runtime_seconds": t.result.runtime_seconds if t.result else 0.0,
                    "attempts": t.result.attempts if t.result else 0,
                    "files": t.result.output_files if t.result else [],
                }
                for t in completed
            ],
            "failed": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "tool": t.tool,
                    "args": t.args,
                    "error": t.error or "未知错误",
                }
                for t in failed
            ],
            "blocked": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "tool": t.tool,
                    "args": t.args,
                    "reason": t.error or "依赖未满足",
                }
                for t in blocked
            ],
            "summary": f"完成 {len(completed)}/{len(self.tasks)} 个任务"
            + (f"，{len(failed)} 失败" if failed else "")
            + (f"，{len(blocked)} 阻塞" if blocked else ""),
            "all_output_files": _collect_all_files(completed),
        }

    def _resolve_task_references(
        self,
        value: Any,
        *,
        declared_dependencies: Optional[set[str]] = None,
    ) -> Any:
        """解析参数中指向已完成任务的精确 ``$step_ID`` 引用。"""
        if isinstance(value, dict):
            return {
                key: self._resolve_task_references(
                    item,
                    declared_dependencies=declared_dependencies,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve_task_references(
                    item,
                    declared_dependencies=declared_dependencies,
                )
                for item in value
            ]
        if not isinstance(value, str) or not value.startswith("$step_"):
            return value

        task_id = value[len("$step_"):]
        dependency = self.tasks.get(task_id)
        if not dependency:
            raise ValueError(f"步骤引用不存在: {value}")
        if declared_dependencies is not None and task_id not in declared_dependencies:
            raise ValueError(f"步骤引用未声明依赖: {value}")
        if not dependency.result:
            raise ValueError(f"步骤引用尚不可用: {value}")
        if dependency.result.status != "success":
            raise ValueError(f"步骤引用未成功: {value}")

        result = to_plain_dict(dependency.result) or {}
        files = result.get("output_files", []) or []
        if files:
            first_file = files[0]
            resolved_path = first_file.get("relative_path") or first_file.get("url")
            if resolved_path:
                return resolved_path
        message = result.get("message")
        if message:
            return message
        raise ValueError(f"步骤引用没有可传递结果: {value}")


def _collect_all_files(completed_tasks: List[KanbanTask]) -> List[Dict[str, Any]]:
    """收集所有已完成任务的输出文件。"""
    files = []
    seen = set()
    for task in completed_tasks:
        if task.result:
            for f in (task.result.output_files or []):
                key = f.get("url", "") or f.get("relative_path", "")
                if key and key not in seen:
                    seen.add(key)
                    files.append(f)
    return files
