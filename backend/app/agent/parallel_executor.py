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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.agent.agent_utils import to_plain_dict
from app.agent.agent_constants import FEATURE_FLAGS
from app.agent.tool_registry import TOOL_REGISTRY
from app.agent.tool_result import make_error_result
from app.agent.tool_runner import run_tool_with_lifecycle


def _normalize_dependencies(
    steps: List[Dict[str, Any]],
    dependencies: Optional[Dict[Any, List[Any]]] = None,
) -> Dict[int, List[int]]:
    """校验并归一化 Planner 的依赖声明。"""
    id_to_step: Dict[int, Dict[str, Any]] = {}
    for step in steps:
        raw_step_id = step.get("step_id")
        if raw_step_id is None:
            raise ValueError("步骤缺少 step_id")
        try:
            step_id = int(raw_step_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"无效 step_id: {raw_step_id!r}") from exc
        if step_id in id_to_step:
            raise ValueError(f"重复 step_id: {step_id}")
        id_to_step[step_id] = step

    normalized: Dict[int, List[int]] = {step_id: [] for step_id in id_to_step}
    declarations: Dict[Any, Any] = dict(dependencies or {})
    for step_id, step in id_to_step.items():
        if "depends_on" in step and step_id not in declarations and str(step_id) not in declarations:
            declarations[step_id] = step.get("depends_on", [])

    for raw_step_id, raw_prerequisites in declarations.items():
        try:
            step_id = int(raw_step_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"无效依赖键: {raw_step_id!r}") from exc
        if step_id not in id_to_step:
            raise ValueError(f"依赖声明引用未知步骤: {step_id}")
        if not isinstance(raw_prerequisites, list):
            raise ValueError(f"步骤 {step_id} 的依赖必须是列表")

        prerequisites: List[int] = []
        for raw_prerequisite in raw_prerequisites:
            try:
                prerequisite = int(raw_prerequisite)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"步骤 {step_id} 包含无效依赖: {raw_prerequisite!r}"
                ) from exc
            if prerequisite not in id_to_step:
                raise ValueError(f"步骤 {step_id} 依赖未知步骤 {prerequisite}")
            if prerequisite == step_id:
                raise ValueError(f"步骤 {step_id} 不能依赖自身")
            if prerequisite not in prerequisites:
                prerequisites.append(prerequisite)
        normalized[step_id] = prerequisites

    return normalized


def _topological_batches(
    steps: List[Dict[str, Any]],
    dependencies: Optional[Dict[Any, List[Any]]] = None,
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
    if not steps:
        return []

    normalized = _normalize_dependencies(steps, dependencies)
    if not any(normalized.values()):
        return [[step] for step in steps]

    id_to_step = {int(step["step_id"]): step for step in steps}
    in_degree = {step_id: len(prerequisites) for step_id, prerequisites in normalized.items()}
    dependents: Dict[int, List[int]] = {step_id: [] for step_id in id_to_step}
    for step_id, prerequisites in normalized.items():
        for prerequisite in prerequisites:
            dependents[prerequisite].append(step_id)

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

            for dependent in dependents.get(sid, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_queue.append(dependent)

        if batch:
            batches.append(batch)
        queue = next_queue

    if len(processed) != len(steps):
        unresolved = sorted(set(id_to_step) - processed)
        raise ValueError(f"检测到循环依赖: {unresolved}")

    return batches


def _build_execution_batches(
    steps: List[Dict[str, Any]],
    dependencies: Optional[Dict[Any, List[Any]]] = None,
    parallel_groups: Optional[List[List[Any]]] = None,
) -> List[List[Dict[str, Any]]]:
    """结合依赖拓扑和 Planner 并行白名单生成执行批次。"""
    normalized_dependencies = _normalize_dependencies(steps, dependencies)
    if any(normalized_dependencies.values()):
        base_batches = _topological_batches(steps, normalized_dependencies)
    elif parallel_groups:
        base_batches = [list(steps)]
    else:
        return [[step] for step in steps]

    if not parallel_groups:
        return base_batches
    if not isinstance(parallel_groups, list):
        raise ValueError("parallel_groups 必须是列表")

    known_ids = {int(step["step_id"]) for step in steps}
    normalized_groups: List[List[int]] = []
    grouped_ids: Set[int] = set()
    for raw_group in parallel_groups:
        if not isinstance(raw_group, list):
            raise ValueError("parallel_groups 中的每一项必须是 step_id 列表")
        group: List[int] = []
        for raw_step_id in raw_group:
            try:
                step_id = int(raw_step_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"无效并行 step_id: {raw_step_id!r}") from exc
            if step_id not in known_ids:
                raise ValueError(f"并行组引用未知步骤: {step_id}")
            if step_id in grouped_ids:
                raise ValueError(f"步骤 {step_id} 出现在多个并行组")
            grouped_ids.add(step_id)
            group.append(step_id)
        if group:
            normalized_groups.append(group)

    batches: List[List[Dict[str, Any]]] = []
    for base_batch in base_batches:
        step_by_id = {int(step["step_id"]): step for step in base_batch}
        assigned: Set[int] = set()
        for group in normalized_groups:
            selected = [step_by_id[step_id] for step_id in group if step_id in step_by_id]
            if selected:
                batches.append(selected)
                assigned.update(int(step["step_id"]) for step in selected)
        for step in base_batch:
            if int(step["step_id"]) not in assigned:
                batches.append([step])

    return batches


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
    dependencies: Optional[Dict[Any, List[Any]]] = None,
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
    normalized_dependencies = _normalize_dependencies(
        [step for batch in batches for step in batch],
        dependencies,
    )

    total_batches = len(batches)

    for batch_idx, batch in enumerate(batches):
        if progress_callback:
            progress_callback(batch_idx + 1, total_batches, None, "running")

        runnable: List[Dict[str, Any]] = []
        for step in batch:
            step_id = int(step["step_id"])
            prerequisites = normalized_dependencies.get(step_id, [])
            failed_dependencies = [
                prerequisite
                for prerequisite in prerequisites
                if prerequisite not in step_results
                or step_results[prerequisite].get("status") != "success"
            ]
            if failed_dependencies:
                observation = {
                    "tool": _step_tool_name(step),
                    "args": dict(step.get("parameters", {}) or {}),
                    "result_summary": f"依赖步骤失败，跳过步骤 {step_id}",
                    "output_files": [],
                    "status": "blocked",
                    "errors": [f"failed_dependencies: {failed_dependencies}"],
                    "step_id": step_id,
                }
                all_observations.append(observation)
                step_results[step_id] = observation
            else:
                runnable.append(step)

        # 串行批（单步骤）→ 直接执行
        if len(runnable) == 1:
            obs, files = _execute_single_step(
                runnable[0],
                available_tool_names,
                session_id,
                step_results,
                allowed_reference_ids=set(
                    normalized_dependencies.get(int(runnable[0]["step_id"]), [])
                ),
            )
            all_observations.extend(obs)
            all_output_files.extend(files)
            if obs:
                step_results[int(runnable[0]["step_id"])] = obs[-1]

        # 并行批 → ThreadPoolExecutor
        elif len(runnable) > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, min(max_workers, len(runnable)))
            ) as executor:
                futures = {}
                previous_results = dict(step_results)
                for step in runnable:
                    future = executor.submit(
                        _execute_single_step,
                        step,
                        available_tool_names,
                        session_id,
                        previous_results,
                        set(normalized_dependencies.get(int(step["step_id"]), [])),
                    )
                    futures[future] = step

                completed: Dict[int, Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = {}
                for future in concurrent.futures.as_completed(futures):
                    step = futures[future]
                    step_id = int(step["step_id"])
                    try:
                        completed[step_id] = future.result()
                    except Exception as exc:
                        completed[step_id] = ([{
                            "tool": _step_tool_name(step),
                            "args": dict(step.get("parameters", {}) or {}),
                            "result_summary": f"并行步骤执行异常: {exc}",
                            "output_files": [],
                            "status": "error",
                            "errors": [str(exc)],
                            "step_id": step_id,
                        }], [])

                # 并发完成顺序不稳定，对外按 Planner 顺序输出。
                for step in runnable:
                    step_id = int(step["step_id"])
                    obs, files = completed[step_id]
                    all_observations.extend(obs)
                    all_output_files.extend(files)
                    if obs:
                        step_results[step_id] = obs[-1]

        if progress_callback:
            progress_callback(batch_idx + 1, total_batches, None, "done")

    return all_observations, all_output_files


def _step_tool_name(step: Dict[str, Any]) -> str:
    direct_tool = str(step.get("tool", "") or "")
    if direct_tool:
        return direct_tool
    preferred = step.get("preferred_tools", []) or []
    return str(preferred[0]) if preferred else "unknown"


def _execute_single_step(
    step: Dict[str, Any],
    available_tool_names: Set[str],
    session_id: str,
    previous_results: Optional[Dict[int, Any]] = None,
    allowed_reference_ids: Optional[Set[int]] = None,
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

    raw_params = step.get("parameters")
    if not isinstance(raw_params, dict):
        return ([{
            "tool": tool_name,
            "args": {},
            "result_summary": "并行步骤缺少结构化 parameters",
            "output_files": [],
            "status": "error",
            "errors": ["invalid_parameters"],
            "step_id": step.get("step_id"),
        }], [])

    try:
        params = _resolve_step_references(
            dict(raw_params),
            previous_results or {},
            allowed_reference_ids=allowed_reference_ids,
        )
    except ValueError as exc:
        return ([{
            "tool": tool_name,
            "args": dict(raw_params),
            "result_summary": str(exc),
            "output_files": [],
            "status": "blocked",
            "errors": ["unresolved_step_reference"],
            "step_id": step.get("step_id"),
        }], [])

    try:
        actual_tool_name = tool_name
        race_metadata: Dict[str, Any] = {}
        result: Any
        if FEATURE_FLAGS.get("waterfall_racing", False):
            from app.agent.racing_executor import (
                get_compatible_racing_candidates,
                race_tools,
            )

            candidates = get_compatible_racing_candidates(
                tool_name,
                available_tool_names,
                params,
            )
            if len(candidates) >= 2:
                race_result = race_tools(candidates, params, session_id=session_id)
                result = race_result.winner or race_result.fallback_result
                actual_tool_name = (
                    race_result.winner_tool_name
                    or race_result.fallback_tool_name
                    or tool_name
                )
                race_metadata = {
                    "requested_tool": tool_name,
                    "racing_candidates": candidates,
                    "racing_losers": race_result.losers,
                    "racing_runtime_seconds": race_result.total_runtime,
                }
            else:
                result = run_tool_with_lifecycle(
                    tool_name=tool_name,
                    func=func,
                    function_args=params,
                    session_id=session_id,
                )
        else:
            result = run_tool_with_lifecycle(
                tool_name=tool_name,
                func=func,
                function_args=params,
                session_id=session_id,
            )

        if result is None:
            result = make_error_result(
                message="竞速执行未返回结果",
                errors=["race_no_result"],
            )

        output_files = _extract_files_from_result(result)
        observation = {
            "tool": actual_tool_name,
            "args": params,
            "result_summary": result.message or "",
            "output_files": output_files,
            "status": result.status,
            "warnings": result.warnings,
            "errors": result.errors,
            "job_id": result.provenance.job_id,
            "job_dir": result.summary.get("job_dir", ""),
            "step_id": step.get("step_id"),
            **race_metadata,
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
    params: Any,
    previous_results: Dict[int, Any],
    allowed_reference_ids: Optional[Set[int]] = None,
) -> Any:
    """解析参数中的 $step_N 引用为实际值。"""
    if isinstance(params, dict):
        return {
            key: _resolve_step_references(
                value,
                previous_results,
                allowed_reference_ids,
            )
            for key, value in params.items()
        }
    if isinstance(params, list):
        return [
            _resolve_step_references(value, previous_results, allowed_reference_ids)
            for value in params
        ]
    if not isinstance(params, str) or not params.startswith("$step_"):
        return params

    try:
        step_id = int(params[len("$step_"):])
    except ValueError as exc:
        raise ValueError(f"无效步骤引用: {params}") from exc

    if allowed_reference_ids is not None and step_id not in allowed_reference_ids:
        raise ValueError(f"步骤引用未声明依赖: {params}")

    reference = previous_results.get(step_id)
    if not isinstance(reference, dict):
        raise ValueError(f"步骤引用尚不可用: {params}")
    if reference.get("status") != "success":
        raise ValueError(f"步骤引用未成功: {params}")

    files = reference.get("output_files", []) or []
    if files:
        first_file = files[0]
        resolved_path = first_file.get("relative_path") or first_file.get("url")
        if resolved_path:
            return resolved_path
    summary = reference.get("result_summary")
    if summary:
        return summary
    raise ValueError(f"步骤引用没有可传递结果: {params}")


def _extract_files_from_result(result: Any) -> List[Dict[str, Any]]:
    """从 ToolResult 提取文件列表。"""
    files = []
    if hasattr(result, "output_files"):
        for f in (result.output_files or []):
            d = to_plain_dict(f)
            if d is not None:
                files.append(d)
    elif isinstance(result, dict):
        ofs = result.get("output_files", [])
        for f in (ofs or []):
            if isinstance(f, dict):
                files.append(f)
    return files
