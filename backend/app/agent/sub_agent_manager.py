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
        SubAgentTask(goal="富集分析", tool="run_enrichment_analysis", args={...}),
    ]
    results = manager.spawn_and_collect_all(tasks, session_id="abc123")
"""

import concurrent.futures
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agent.tool_registry import TOOL_REGISTRY, get_tool_meta
from app.agent.tool_runner import run_tool_with_lifecycle


class SubAgentTask(BaseModel):
    """子Agent 任务规格。"""
    goal: str = ""
    tool: str = ""                      # 工具名
    args: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[int] = Field(default_factory=list)  # 依赖的任务索引
    max_retries: int = 1
    timeout: int = 600


class SubAgentResult(BaseModel):
    """子Agent 执行结果。"""
    task_index: int = 0
    goal: str = ""
    tool: str = ""
    status: str = "pending"  # success / error / timeout
    message: str = ""
    output_files: List[Dict[str, Any]] = Field(default_factory=list)
    job_id: str = ""
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    runtime_seconds: float = 0.0


class SubAgentManager:
    """
    子Agent 管理器。

    功能:
    - spawn(task) → agent_id (异步启动子Agent)
    - collect(agent_id) → SubAgentResult (等待结果)
    - spawn_and_collect_all(tasks) → List[SubAgentResult] (批量启动+收集)
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._results: Dict[int, SubAgentResult] = {}

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
        t_start = time.time()

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(tasks))
        ) as executor:
            # 拓扑排序：按依赖关系分批
            pending = list(enumerate(tasks))
            futures: Dict[concurrent.futures.Future, int] = {}

            while pending or futures:
                # 提交无依赖或依赖已满足的任务
                ready = []
                still_pending = []
                for idx, task in pending:
                    deps_satisfied = all(
                        dep in results and results[dep].status == "success"
                        for dep in task.depends_on
                    )
                    if deps_satisfied:
                        ready.append((idx, task))
                    else:
                        still_pending.append((idx, task))
                pending = still_pending

                for idx, task in ready:
                    future = executor.submit(
                        self._execute_single_task,
                        task,
                        idx,
                        session_id,
                    )
                    futures[future] = idx

                # 如果还有 future 在运行，等待一个完成
                if futures:
                    done_futures = set()
                    for future in list(futures.keys()):
                        if future.done():
                            done_futures.add(future)
                            idx = futures.pop(future)
                            try:
                                results[idx] = future.result(timeout=10)
                            except Exception as e:
                                results[idx] = SubAgentResult(
                                    task_index=idx,
                                    goal=tasks[idx].goal,
                                    tool=tasks[idx].tool,
                                    status="error",
                                    message=str(e),
                                    errors=[str(e)],
                                )

                    if not done_futures and futures:
                        # 等第一个完成
                        done, _ = concurrent.futures.wait(
                            futures.keys(),
                            return_when=concurrent.futures.FIRST_COMPLETED,
                            timeout=30,
                        )
                        for future in done:
                            idx = futures.pop(future)
                            try:
                                results[idx] = future.result(timeout=10)
                            except Exception as e:
                                results[idx] = SubAgentResult(
                                    task_index=idx,
                                    goal=tasks[idx].goal,
                                    tool=tasks[idx].tool,
                                    status="error",
                                    message=str(e),
                                    errors=[str(e)],
                                )

        # 收集未执行的任务
        for idx, task in enumerate(tasks):
            if idx not in results:
                # 检查是否有失败的依赖
                failed_deps = [
                    dep for dep in task.depends_on
                    if dep in results and results[dep].status != "success"
                ]
                results[idx] = SubAgentResult(
                    task_index=idx,
                    goal=task.goal,
                    tool=task.tool,
                    status="error",
                    message=f"依赖未满足: {failed_deps}" if failed_deps else "未执行",
                    errors=[f"未满足的依赖: {failed_deps}"] if failed_deps else [],
                )

        # 按索引排序返回
        total_time = round(time.time() - t_start, 3)
        return [results[i] for i in sorted(results.keys())]

    def _execute_single_task(
        self,
        task: SubAgentTask,
        task_index: int,
        session_id: str,
    ) -> SubAgentResult:
        """执行单个子Agent 任务。"""
        func = TOOL_REGISTRY.get(task.tool)
        if not func:
            return SubAgentResult(
                task_index=task_index,
                goal=task.goal,
                tool=task.tool,
                status="error",
                message=f"工具 {task.tool} 未注册",
                errors=[f"tool_not_registered: {task.tool}"],
            )

        try:
            result = run_tool_with_lifecycle(
                tool_name=task.tool,
                func=func,
                function_args=task.args,
                session_id=f"{session_id}_sub_{task_index}" if session_id else "",
            )

            output_files = []
            if hasattr(result, "output_files"):
                for f in (result.output_files or []):
                    if hasattr(f, "model_dump"):
                        output_files.append(f.model_dump())
                    elif isinstance(f, dict):
                        output_files.append(f)

            return SubAgentResult(
                task_index=task_index,
                goal=task.goal,
                tool=task.tool,
                status=result.status if hasattr(result, "status") else "success",
                message=result.message if hasattr(result, "message") else "",
                output_files=output_files,
                job_id=result.provenance.job_id if hasattr(result, "provenance") else "",
                errors=result.errors if hasattr(result, "errors") else [],
                warnings=result.warnings if hasattr(result, "warnings") else [],
            )

        except Exception as e:
            return SubAgentResult(
                task_index=task_index,
                goal=task.goal,
                tool=task.tool,
                status="error",
                message=str(e),
                errors=[str(e)],
            )


# 全局单例
sub_agent_manager = SubAgentManager(max_workers=4)
