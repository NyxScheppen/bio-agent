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
        args: Dict[str, Any] = None,
        depends_on: List[str] = None,
    ):
        self.task_id = task_id
        self.name = name
        self.tool = tool
        self.args = args or {}
        self.depends_on = depends_on or []
        self.status: TaskStatus = TaskStatus.TODO
        self.result: Optional[SubAgentResult] = None
        self.error: Optional[str] = None

    def can_start(self, completed_ids: set) -> bool:
        """检查所有依赖是否已完成。"""
        if self.status != TaskStatus.TODO:
            return False
        return all(dep in completed_ids for dep in self.depends_on)

    def mark_blocked(self):
        """标记为阻塞（依赖任务失败）。"""
        self.status = TaskStatus.BLOCKED
        self.error = "依赖任务失败"


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

    def __init__(self, manager: SubAgentManager = None):
        self.tasks: Dict[str, KanbanTask] = {}
        self._manager = manager or sub_agent_manager

    def add_task(
        self,
        task_id: str,
        name: str,
        tool: str,
        args: Dict[str, Any] = None,
        depends_on: List[str] = None,
    ) -> "Orchestrator":
        """添加一个任务到 Kanban 板。"""
        self.tasks[task_id] = KanbanTask(
            task_id=task_id,
            name=name,
            tool=tool,
            args=args,
            depends_on=depends_on,
        )
        return self  # 链式调用

    def add_tasks_from_planner(
        self,
        steps: List[Dict[str, Any]],
        step_dependencies: Dict[int, List[int]] = None,
    ) -> "Orchestrator":
        """从 Planner 步骤自动添加任务。"""
        for s in steps:
            sid = str(s.get("step_id", ""))
            tools = s.get("preferred_tools", [])
            deps = step_dependencies.get(int(s.get("step_id", 0)), []) if step_dependencies else []
            self.add_task(
                task_id=sid,
                name=s.get("goal", ""),
                tool=tools[0] if tools else "",
                args={},
                depends_on=[str(d) for d in deps],
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

        max_iterations = len(self.tasks) * 2  # 安全上限
        iteration = 0

        while len(completed_ids) + len(failed_ids) < len(self.tasks) and iteration < max_iterations:
            iteration += 1

            # 找可启动的任务
            ready = []
            for tid, task in self.tasks.items():
                if task.status == TaskStatus.TODO:
                    # 检查是否有依赖失败
                    has_failed_dep = any(
                        dep in failed_ids for dep in task.depends_on
                    )
                    if has_failed_dep:
                        task.mark_blocked()
                        continue

                    if task.can_start(completed_ids):
                        ready.append(task)

            if not ready:
                # 没有可执行任务：要么全完成了，要么存在循环依赖
                remaining_todo = [
                    t for t in self.tasks.values()
                    if t.status == TaskStatus.TODO
                ]
                if remaining_todo:
                    # 尝试强制执行无工具依赖的任务
                    for task in remaining_todo:
                        if not task.tool:
                            task.status = TaskStatus.DONE
                            completed_ids.add(task.task_id)
                        else:
                            task.mark_blocked()
                break

            # 构建 SubAgentTask 列表
            sub_tasks = []
            task_id_map = {}
            for i, task in enumerate(ready):
                sub_tasks.append(SubAgentTask(
                    goal=task.name,
                    tool=task.tool,
                    args=task.args,
                ))
                task_id_map[i] = task.task_id
                task.status = TaskStatus.IN_PROGRESS

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

        # 汇总
        completed = [t for t in self.tasks.values() if t.status == TaskStatus.DONE]
        failed = [t for t in self.tasks.values() if t.status == TaskStatus.FAILED]
        blocked = [t for t in self.tasks.values() if t.status == TaskStatus.BLOCKED]

        return {
            "completed": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "files": t.result.output_files if t.result else [],
                }
                for t in completed
            ],
            "failed": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "error": t.error or "未知错误",
                }
                for t in failed
            ],
            "blocked": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "reason": t.error or "依赖未满足",
                }
                for t in blocked
            ],
            "summary": f"完成 {len(completed)}/{len(self.tasks)} 个任务"
            + (f"，{len(failed)} 失败" if failed else "")
            + (f"，{len(blocked)} 阻塞" if blocked else ""),
            "all_output_files": _collect_all_files(completed),
        }


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
