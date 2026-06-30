"""
依赖感知并行执行器 (Phase 1.1: Parallel Tool Execution).

将 Planner 输出的步骤按依赖关系分组并行执行。
参考 Firecrawl "Waterfall Racing" 和 Hermes 子Agent委派模式。

核心算法:
1. 读取 PlannerResult.steps + step_dependencies
2. 拓扑排序分组为并行 batch
3. 每个 batch 内使用 ThreadPoolExecutor 并发执行
4. 收集结果，传递给下一 batch
"""

import concurrent.futures
import json
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.agent.tool_registry import TOOL_REGISTRY
from app.agent.tool_result import ToolResult
from app.agent.tool_runner import run_tool_with_lifecycle


def _topological_batches(
    steps: List[Dict[str, Any]],
    dependencies: Optional[Dict[int, List[int]]] = None,
) -> List[List[Dict[str, Any]]]:
    """
    将步骤按依赖关系分组为可并行执行的批次。

    无依赖关系的步骤放在同一批（可并行），有依赖的等前一批完成。

    Args:
        steps: Planner 输出的步骤列表，每个步骤含 step_id
        dependencies: {step_id: [prerequisite_step_ids]}，可选

    Returns:
        [[batch1_steps], [batch2_steps], ...] 拓扑排序后的批次
    """
    if not dependencies:
        # 无依赖声明 → 全部串行（保守默认）
        return [[s] for s in steps]

    # 构建 step_id 到索引的映射
    id_to_step = {}
    for s in steps:
        sid = s.get("step_id")
        if sid is not None:
            id_to_step[int(sid)] = s

    # 构建入度表
    in_degree: Dict[int, int] = {}
    depends_on: Dict[int, List[int]] = {}

    for s in steps:
        sid = int(s.get("step_id", 0))
        in_degree[sid] = 0
        depends_on[sid] = []

    for sid, prereqs in (dependencies or {}).items():
        sid = int(sid)
        if sid not in in_degree:
            in_degree[sid] = 0
        in_degree[sid] += len(prereqs)
        for prereq in prereqs:
            prereq = int(prereq)
            if prereq not in depends_on:
                depends_on[prereq] = []
            depends_on[prereq].append(sid)

    # Kahn 算法
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    batches: List[List[Dict[str, Any]]] = []
    processed: Set[int] = set()

    while queue:
        batch: List[Dict[str, Any]] = []
        next_queue: List[int] = []

        for sid in sorted(queue):
            if sid in processed:
                continue
            step = id_to_step.get(sid)
            if step:
                batch.append(step)
            processed.add(sid)

            for dependent in depends_on.get(sid, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_queue.append(dependent)

        if batch:
            batches.append(batch)
        queue = next_queue

    # 兜底：未处理的步骤逐个串行
    for s in steps:
        sid = int(s.get("step_id", 0))
        if sid not in processed:
            batches.append([s])

    return batches if batches else [[s] for s in steps]


def _resolve_tool_for_step(
    step: Dict[str, Any],
    available_tool_names: Set[str],
) -> Optional[str]:
    """
    从步骤的 preferred_tools 中选择第一个可用的工具。
    若 step 有 "tool" 字段直接使用。
    """
    direct_tool = step.get("tool", "")
    if direct_tool and direct_tool in available_tool_names:
        return direct_tool

    preferred = step.get("preferred_tools", []) or []
    for t in preferred:
        if t in available_tool_names:
            return t

    return None


def execute_parallel_steps(
    batches: List[List[Dict[str, Any]]],
    available_tool_names: Set[str],
    session_id: str,
    progress_callback: Optional[Callable] = None,
    max_workers: int = 4,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    按批次并行执行步骤。

    Args:
        batches: 拓扑排序后的批次
        available_tool_names: 可用工具名集合
        session_id: 会话 ID
        progress_callback: 可选进度回调 (batch_idx, total_batches, step_id, status)
        max_workers: 每批最大并发数

    Returns:
        (tool_observations, all_output_files)
    """
    all_observations: List[Dict[str, Any]] = []
    all_output_files: List[Dict[str, Any]] = []
    step_results: Dict[int, Any] = {}  # step_id → result，供后续步骤引用

    total_batches = len(batches)

    for batch_idx, batch in enumerate(batches):
        if progress_callback:
            progress_callback(batch_idx + 1, total_batches, None, "running")

        # 串行批（单步骤）→ 直接执行
        if len(batch) == 1:
            obs, files = _execute_single_step(
                batch[0], available_tool_names, session_id, step_results
            )
            all_observations.extend(obs)
            all_output_files.extend(files)
            if obs:
                step_results[int(batch[0].get("step_id", 0))] = obs[-1]
            continue

        # 并行批 → ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max_workers, len(batch))
        ) as executor:
            futures = {}
            for step in batch:
                future = executor.submit(
                    _execute_single_step,
                    step,
                    available_tool_names,
                    session_id,
                    step_results,
                )
                futures[future] = step

            for future in concurrent.futures.as_completed(futures):
                step = futures[future]
                try:
                    obs, files = future.result(timeout=600)
                    all_observations.extend(obs)
                    all_output_files.extend(files)
                    if obs:
                        step_results[int(step.get("step_id", 0))] = obs[-1]
                except concurrent.futures.TimeoutError:
                    all_observations.append({
                        "tool": step.get("preferred_tools", ["unknown"])[0],
                        "args": {},
                        "result_summary": "并行步骤执行超时",
                        "output_files": [],
                        "status": "error",
                        "errors": ["timeout"],
                    })
                except Exception as e:
                    all_observations.append({
                        "tool": step.get("preferred_tools", ["unknown"])[0],
                        "args": {},
                        "result_summary": f"并行步骤执行异常: {e}",
                        "output_files": [],
                        "status": "error",
                        "errors": [str(e)],
                    })

        if progress_callback:
            progress_callback(batch_idx + 1, total_batches, None, "done")

    return all_observations, all_output_files


def _execute_single_step(
    step: Dict[str, Any],
    available_tool_names: Set[str],
    session_id: str,
    previous_results: Dict[int, Any] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    执行单个 Planner 步骤。

    返回 (observations, output_files)。
    """
    tool_name = _resolve_tool_for_step(step, available_tool_names)
    if not tool_name:
        return ([{
            "tool": step.get("preferred_tools", ["unknown"])[0] if step.get("preferred_tools") else "unknown",
            "args": {},
            "result_summary": f"步骤 {step.get('step_id')} ({step.get('goal', '')}) — 无可用工具",
            "output_files": [],
            "status": "error",
            "errors": ["no_available_tool"],
        }], [])

    func = TOOL_REGISTRY.get(tool_name)
    if not func:
        return ([{
            "tool": tool_name,
            "args": {},
            "result_summary": f"工具 {tool_name} 未注册",
            "output_files": [],
            "status": "error",
            "errors": ["tool_not_registered"],
        }], [])

    # 构建参数 — 从 step.parameter_strategy 或默认空参数
    params = step.get("parameters", {}) or {}
    # 注入上一步骤的结果引用（如果参数中有 $step_N 引用）
    if previous_results:
        params = _resolve_step_references(params, previous_results)

    try:
        result: ToolResult = run_tool_with_lifecycle(
            tool_name=tool_name,
            func=func,
            function_args=params,
            session_id=session_id,
        )

        output_files = _extract_files_from_result(result)
        observation = {
            "tool": tool_name,
            "args": params,
            "result_summary": result.message or "",
            "output_files": output_files,
            "status": result.status,
            "warnings": result.warnings,
            "errors": result.errors,
            "job_id": result.provenance.job_id,
            "job_dir": result.summary.get("job_dir", ""),
            "step_id": step.get("step_id"),
        }

        return ([observation], output_files)

    except Exception as e:
        return ([{
            "tool": tool_name,
            "args": params,
            "result_summary": f"执行异常: {e}",
            "output_files": [],
            "status": "error",
            "errors": [str(e)],
            "step_id": step.get("step_id"),
        }], [])


def _resolve_step_references(
    params: Dict[str, Any],
    previous_results: Dict[int, Any],
) -> Dict[str, Any]:
    """解析参数中的 $step_N 引用为实际值。"""
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith("$step_"):
            try:
                step_id = int(value.replace("$step_", ""))
                ref = previous_results.get(step_id, {})
                # 尝试取 output_files 中第一个文件的 relative_path
                files = ref.get("output_files", [])
                if files:
                    resolved[key] = files[0].get("relative_path", value)
                else:
                    resolved[key] = ref.get("result_summary", value)
            except (ValueError, AttributeError):
                resolved[key] = value
        else:
            resolved[key] = value
    return resolved


def _extract_files_from_result(result: Any) -> List[Dict[str, Any]]:
    """从 ToolResult 提取文件列表。"""
    files = []
    if hasattr(result, "output_files"):
        for f in (result.output_files or []):
            if hasattr(f, "model_dump"):
                files.append(f.model_dump())
            elif isinstance(f, dict):
                files.append(f)
    elif isinstance(result, dict):
        ofs = result.get("output_files", [])
        for f in (ofs or []):
            if isinstance(f, dict):
                files.append(f)
    return files
