"""
Waterfall Racing 竞速执行器 (Phase 1.2).

参考 Firecrawl 的 "多引擎竞速" 模式:
多个等价工具同时启动，第一个成功者胜出，其余取消。

适用场景:
- 用户说"做差异分析"时，DESeq2 和 limma 可能都适用
- 多个工具在同一个 racing_group，不需要 LLM 提前选择

用法:
    from app.agent.racing_executor import race_tools
    result = race_tools(
        tool_names=["run_deseq2_count_deg_analysis", "run_bulk_rnaseq_deg_analysis"],
        function_args={"expression_file": "...", "group_file": "..."},
        session_id="abc123",
    )
"""

import concurrent.futures
import inspect
import time
from typing import Any, Dict, List, Optional

from app.agent.agent_utils import result_status
from app.agent.tool_registry import TOOL_REGISTRY, TOOL_META
from app.agent.tool_runner import run_tool_with_lifecycle
from app.agent.tool_result import ToolResult


class RaceResult:
    """竞速结果容器。"""

    def __init__(self):
        self.winner: Optional[ToolResult] = None
        self.winner_tool_name: str = ""
        self.fallback_result: Optional[ToolResult] = None
        self.fallback_tool_name: str = ""
        self.losers: List[Dict[str, Any]] = []
        self.all_completed: bool = False
        self.total_runtime: float = 0.0


def _get_racing_group(tool_name: str) -> Optional[str]:
    """获取工具的 racing_group 元信息。"""
    meta = TOOL_META.get(tool_name, {})
    return meta.get("racing_group")


def _find_racing_candidates(
    tool_name: str,
    available_tool_names: set,
) -> List[str]:
    """
    找到与指定工具同 racing_group 的可用工具。

    返回: [tool_name, ...] 按优先级排序（原始工具排第一）。
    """
    group = _get_racing_group(tool_name)
    if not group:
        return [tool_name]

    candidates = []
    for name in available_tool_names:
        if _get_racing_group(name) == group:
            candidates.append(name)

    if not candidates:
        return [tool_name]

    # 原始工具排最前面
    if tool_name in candidates:
        candidates.remove(tool_name)
        candidates.insert(0, tool_name)

    return candidates


def race_tools(
    tool_names: List[str],
    function_args: Dict[str, Any],
    session_id: str = "",
    timeout: int = 600,
    max_workers: int = 4,
) -> RaceResult:
    """
    竞速执行多个等价工具，返回第一个成功的结果。

    工作方式:
    1. 所有工具同时提交到 ThreadPoolExecutor
    2. 使用 concurrent.futures.as_completed 按完成顺序收集
    3. 第一个 status=="success" 的作为 winner
    4. 其余标记为 loser 并取消（尽力而为）

    Args:
        tool_names: 竞速工具名列表
        function_args: 工具参数（所有工具用同一套参数）
        session_id: 会话 ID
        timeout: 单个工具超时（秒）
        max_workers: 最大并发数

    Returns:
        RaceResult
    """
    result = RaceResult()
    t_start = time.monotonic()

    # 验证和准备
    valid_tools = []
    for name in tool_names:
        if name in TOOL_REGISTRY and name not in valid_tools:
            valid_tools.append(name)

    if not valid_tools:
        result.all_completed = True
        result.total_runtime = round(time.monotonic() - t_start, 3)
        return result

    if len(valid_tools) == 1:
        # 只有一个工具，直接执行
        func = TOOL_REGISTRY[valid_tools[0]]
        r = run_tool_with_lifecycle(
            tool_name=valid_tools[0],
            func=func,
            function_args=function_args,
            session_id=session_id,
            timeout_override=timeout,
        )
        if _is_success(r):
            result.winner = r
            result.winner_tool_name = valid_tools[0]
        else:
            result.fallback_result = r
            result.fallback_tool_name = valid_tools[0]
        result.all_completed = True
        result.total_runtime = round(time.monotonic() - t_start, 3)
        return result

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(max_workers, len(valid_tools)))
    )
    future_to_name: Dict[concurrent.futures.Future, str] = {}
    try:
        future_to_name = {}
        for name in valid_tools:
            func = TOOL_REGISTRY[name]
            future = executor.submit(
                run_tool_with_lifecycle,
                tool_name=name,
                func=func,
                function_args=dict(function_args),
                session_id=session_id,
                timeout_override=timeout,
            )
            future_to_name[future] = name

        for future in concurrent.futures.as_completed(
            future_to_name,
            timeout=max(1, int(timeout)),
        ):
            name = future_to_name[future]

            try:
                tool_result = future.result()
            except Exception as exc:
                result.losers.append({
                    "tool_name": name,
                    "status": "error",
                    "reason": str(exc),
                })
                continue

            if result.fallback_result is None:
                result.fallback_result = tool_result
                result.fallback_tool_name = name

            if tool_result and _is_success(tool_result):
                result.winner = tool_result
                result.winner_tool_name = name
                break

            status = result_status(tool_result) or "error"
            reason = getattr(tool_result, "message", "") if tool_result else "无返回值"
            result.losers.append({
                "tool_name": name,
                "status": status,
                "reason": str(reason)[:200],
            })
    except concurrent.futures.TimeoutError:
        pass
    finally:
        recorded = {item["tool_name"] for item in result.losers}
        for future, name in future_to_name.items():
            if name == result.winner_tool_name or name in recorded:
                continue
            if future.done():
                status = "completed_not_selected"
            elif future.cancel():
                status = "cancelled"
            else:
                status = "running"
            result.losers.append({
                "tool_name": name,
                "status": status,
                "reason": "竞速已产生胜者" if result.winner else "竞速等待超时",
            })

        result.all_completed = all(future.done() for future in future_to_name)
        result.total_runtime = round(time.monotonic() - t_start, 3)
        executor.shutdown(wait=False, cancel_futures=True)

    return result


def get_compatible_racing_candidates(
    tool_name: str,
    available_tool_names: set,
    function_args: Dict[str, Any],
) -> List[str]:
    """返回同组且能接受同一组参数的工具，避免错误的跨 schema 竞速。"""
    return [
        candidate
        for candidate in _find_racing_candidates(tool_name, available_tool_names)
        if _tool_accepts_arguments(candidate, function_args)
    ]


def _tool_accepts_arguments(tool_name: str, function_args: Dict[str, Any]) -> bool:
    func = TOOL_REGISTRY.get(tool_name)
    if func is None or not isinstance(function_args, dict):
        return False

    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False

    injected = {"session_id", "job_dir", "context"}
    accepts_extra = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    accepted_names = {
        name
        for name, parameter in parameters.items()
        if parameter.kind in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    }
    if not accepts_extra and any(name not in accepted_names for name in function_args):
        return False

    required_names = {
        name
        for name, parameter in parameters.items()
        if name not in injected
        and parameter.kind in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
        and parameter.default is inspect.Parameter.empty
    }
    return required_names.issubset(function_args)


def should_race(
    tool_name: str,
    available_tool_names: set,
) -> bool:
    """
    判断是否应该为指定工具启用竞速模式。

    条件:
    1. 工具注册了 racing_group
    2. 当前可用工具集中至少有 2 个同组工具
    3. 原始工具本身没有被禁用

    Args:
        tool_name: 要检查的工具名
        available_tool_names: 当前可用工具名集合

    Returns:
        True 表示应该启用竞速
    """

    group = _get_racing_group(tool_name)
    if not group:
        return False

    count = 0
    for name in available_tool_names:
        if _get_racing_group(name) == group:
            count += 1
            if count >= 2:
                return True

    return False


def get_racing_candidates_for_step(
    planner_step: Dict[str, Any],
    available_tool_names: set,
) -> Optional[List[str]]:
    """
    从 Planner 步骤获取竞速候选工具。

    如果步骤的 preferred_tools 中有多个工具属于同一 racing_group，
    返回完整的竞速候选列表。
    """
    preferred = planner_step.get("preferred_tools", []) or []
    if len(preferred) < 2:
        return None

    # 找第一个有 racing_group 的工具
    for t in preferred:
        if t not in available_tool_names:
            continue
        candidates = get_compatible_racing_candidates(
            t,
            available_tool_names,
            planner_step.get("parameters", {}) or {},
        )
        if len(candidates) >= 2:
            return candidates

    return None


def _is_success(result: Any) -> bool:
    """判断工具结果是否成功（无 status 的非 dict 对象宽松视为成功）。"""
    if result is None:
        return False
    if isinstance(result, dict) or hasattr(result, "status"):
        return result_status(result) == "success"
    return True
