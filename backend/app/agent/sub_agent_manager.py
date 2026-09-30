"""
子Agent管理器 (Phase 3.1: Sub-Agent Manager).

参考 Hermes agent 的子Agent委派模式。
管理子Agent 的创建、执行和结果收集。

子Agent 是轻量级的 Executor 变体:
- 聚焦单一目标（一个 Planner 步骤）
- 受限的工具集（仅该步骤需要的工具）
- 独立 session_id 命名空间
- 可并行执行多个子Agent

用法:
    manager = SubAgentManager()
    tasks = [
        SubAgentTask(goal="DEG分析", tool="run_bulk_rnaseq_deg_analysis", args={...}),
        SubAgentTask(goal="富集分析", tool="run_go_kegg_enrichment", args={...}),
    ]
    results = manager.spawn_and_collect_all(tasks, session_id="abc123")
"""

import concurrent.futures
import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.agent.agent_utils import result_status, to_plain_dict
from app.agent.tool_registry import TOOL_REGISTRY
from app.agent.tool_runner import run_tool_with_lifecycle


class SubAgentTask(BaseModel):
    """子Agent 任务规格。"""
    goal: str = ""
    tool: str = ""                      # 工具名
    args: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[int] = Field(default_factory=list)  # 依赖的任务索引
    max_retries: int = Field(default=0, ge=0, le=3)
    timeout: int = Field(default=600, ge=10, le=3600)


class SubAgentResult(BaseModel):
    """子Agent 执行结果。"""
    task_index: int = 0
    goal: str = ""
    tool: str = ""
    status: str = "pending"  # success / partial / error / timeout / blocked
    message: str = ""
    output_files: List[Dict[str, Any]] = Field(default_factory=list)
    job_id: str = ""
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    runtime_seconds: float = 0.0
    attempts: int = 0


class SubAgentManager:
    """
    子Agent 管理器。

    功能:
    - spawn(task) → agent_id (异步启动子Agent)
    - collect(agent_id) → SubAgentResult (等待结果)
    - spawn_and_collect_all(tasks) → List[SubAgentResult] (批量启动+收集)
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max(1, int(max_workers))

    def spawn_and_collect_all(
        self,
        tasks: List[SubAgentTask],
        session_id: str = "",
    ) -> List[SubAgentResult]:
        """
        批量启动子Agent 并收集所有结果。

        支持依赖关系：有 depends_on 的任务等依赖完成后再启动。

        Args:
            tasks: 子Agent 任务列表
            session_id: 父会话 ID

        Returns:
            按任务顺序排列的结果列表
        """
        if not tasks:
            return []

        results: Dict[int, SubAgentResult] = {}
        task_count = len(tasks)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.max_workers, task_count)
        ) as executor:
            pending = dict(enumerate(tasks))
            futures: Dict[concurrent.futures.Future, int] = {}

            while pending or futures:
                submitted = False
                for idx, task in list(pending.items()):
                    invalid_dependencies = [
                        dep for dep in task.depends_on
                        if dep < 0 or dep >= task_count or dep == idx
                    ]
                    if invalid_dependencies:
                        results[idx] = self._blocked_result(
                            task,
                            idx,
                            f"无效依赖: {invalid_dependencies}",
                        )
                        pending.pop(idx)
                        continue

                    failed_dependencies = [
                        dep for dep in task.depends_on
                        if dep in results and results[dep].status != "success"
                    ]
                    if failed_dependencies:
                        results[idx] = self._blocked_result(
                            task,
                            idx,
                            f"依赖任务失败: {failed_dependencies}",
                        )
                        pending.pop(idx)
                        continue

                    if not all(dep in results for dep in task.depends_on):
                        continue

                    future = executor.submit(
                        self._execute_single_task,
                        task,
                        idx,
                        session_id,
                    )
                    futures[future] = idx
                    pending.pop(idx)
                    submitted = True

                if futures:
                    done, _ = concurrent.futures.wait(
                        futures,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    for future in done:
                        idx = futures.pop(future)
                        try:
                            results[idx] = future.result()
                        except Exception as exc:
                            results[idx] = SubAgentResult(
                                task_index=idx,
                                goal=tasks[idx].goal,
                                tool=tasks[idx].tool,
                                status="error",
                                message=str(exc),
                                errors=[str(exc)],
                            )
                    continue

                if pending and not submitted:
                    # 没有运行中任务且没有任务可提交，只可能是循环或不可解析依赖。
                    unresolved = sorted(pending)
                    for idx, task in list(pending.items()):
                        results[idx] = self._blocked_result(
                            task,
                            idx,
                            f"循环或不可解析依赖: {unresolved}",
                        )
                        pending.pop(idx)

        return [results[index] for index in range(task_count)]

    @staticmethod
    def _blocked_result(
        task: SubAgentTask,
        task_index: int,
        reason: str,
    ) -> SubAgentResult:
        return SubAgentResult(
            task_index=task_index,
            goal=task.goal,
            tool=task.tool,
            status="blocked",
            message=reason,
            errors=[reason],
        )

    def _execute_single_task(
        self,
        task: SubAgentTask,
        task_index: int,
        session_id: str,
    ) -> SubAgentResult:
        """执行单个子Agent 任务。"""
        started = time.monotonic()
        func = TOOL_REGISTRY.get(task.tool)
        if not func:
            return SubAgentResult(
                task_index=task_index,
                goal=task.goal,
                tool=task.tool,
                status="error",
                message=f"工具 {task.tool} 未注册",
                errors=[f"tool_not_registered: {task.tool}"],
                runtime_seconds=round(time.monotonic() - started, 3),
            )

        result: Any = None
        last_exception: Exception | None = None
        attempts = 0
        for attempts in range(1, task.max_retries + 2):
            try:
                result = run_tool_with_lifecycle(
                    tool_name=task.tool,
                    func=func,
                    function_args=dict(task.args),
                    # Jobs already have unique IDs. Preserve the real session so
                    # delegated tools can read that session's uploads and their
                    # outputs remain owned by the same lifecycle.
                    session_id=session_id,
                    timeout_override=task.timeout,
                )
                status = result_status(result) or "success"
                provenance = getattr(result, "provenance", None)
                resource_usage = getattr(provenance, "resource_usage", None)
                if getattr(resource_usage, "timeout_triggered", False):
                    break
                if status != "error":
                    break
            except Exception as exc:
                last_exception = exc
                result = None

        runtime_seconds = round(time.monotonic() - started, 3)
        if result is None:
            message = str(last_exception or "子Agent 执行失败")
            return SubAgentResult(
                task_index=task_index,
                goal=task.goal,
                tool=task.tool,
                status="error",
                message=message,
                errors=[message],
                runtime_seconds=runtime_seconds,
                attempts=attempts,
            )

        output_files = []
        for output_file in getattr(result, "output_files", []) or []:
            plain_file = to_plain_dict(output_file)
            if plain_file is not None:
                output_files.append(plain_file)

        status = result_status(result) or "success"
        provenance = getattr(result, "provenance", None)
        resource_usage = getattr(provenance, "resource_usage", None)
        if getattr(resource_usage, "timeout_triggered", False):
            status = "timeout"

        return SubAgentResult(
            task_index=task_index,
            goal=task.goal,
            tool=task.tool,
            status=status,
            message=getattr(result, "message", ""),
            output_files=output_files,
            job_id=getattr(provenance, "job_id", ""),
            errors=list(getattr(result, "errors", []) or []),
            warnings=list(getattr(result, "warnings", []) or []),
            runtime_seconds=runtime_seconds,
            attempts=attempts,
        )


# 全局单例
sub_agent_manager = SubAgentManager(max_workers=4)
