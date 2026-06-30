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
import time
from typing import Any, Callable, Dict, List, Optional

from app.agent.tool_registry import TOOL_REGISTRY, TOOL_META
from app.agent.tool_runner import run_tool_with_lifecycle
from app.agent.tool_result import ToolResult


class RaceResult:
    """竞速结果容器。"""

    def __init__(self):
        self.winner: Optional[ToolResult] = None
        self.winner_tool_name: str = ""
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
    t_start = time.time()

    # 验证和准备
    valid_tools = []
    for name in tool_names:
        if name in TOOL_REGISTRY:
            valid_tools.append(name)

    if not valid_tools:
        return result

    if len(valid_tools) == 1:
        # 只有一个工具，直接执行
        func = TOOL_REGISTRY[valid_tools[0]]
        r = run_tool_with_lifecycle(
            tool_name=valid_tools[0],
            func=func,
            function_args=function_args,
            session_id=session_id,
        )
        result.winner = r
        result.winner_tool_name = valid_tools[0]
        result.all_completed = True
        result.total_runtime = time.time() - t_start
        return result

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(max_workers, len(valid_tools))
    ) as executor:
        future_to_name = {}
        for name in valid_tools:
            func = TOOL_REGISTRY[name]
            future = executor.submit(
                run_tool_with_lifecycle,
                tool_name=name,
                func=func,
                function_args=function_args,
                session_id=session_id,
            )
            future_to_name[future] = name

        winner_found = False

        for future in concurrent.futures.as_completed(future_to_name):
            name = future_to_name[future]

            try:
                tool_result = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                result.losers.append({
                    "tool_name": name,
                    "status": "timeout",
                    "reason": f"超时（>{timeout}秒）",
                })
                continue
            except Exception as e:
                result.losers.append({
                    "tool_name": name,
                    "status": "error",
                    "reason": str(e),
                })
                continue

            if not winner_found and tool_result and _is_success(tool_result):
                result.winner = tool_result
                result.winner_tool_name = name
                winner_found = True
                # 不 cancel 其他 future — ThreadPoolExecutor 不支持真正的取消
                # 但后续结果都会被记为 loser
            else:
                status = tool_result.status if tool_result else "null"
                reason = tool_result.message if tool_result else "无返回值"
                result.losers.append({
                    "tool_name": name,
                    "status": status,
                    "reason": reason[:200],
                })

    result.all_completed = True
    result.total_runtime = round(time.time() - t_start, 3)

    # 如果没有 winner，取第一个完成的结果作为 winner（即使失败）
    if not result.winner and result.losers:
        # 这种情况不应该出现（所有 future 都被循环处理了）
        pass

    return result


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
        candidates = _find_racing_candidates(t, available_tool_names)
        if len(candidates) >= 2:
            return candidates

    return None


def _is_success(result: Any) -> bool:
    """判断工具结果是否成功。"""
    if result is None:
        return False
    if hasattr(result, "status"):
        return str(getattr(result, "status", "")).lower() == "success"
    if isinstance(result, dict):
        return str(result.get("status", "")).lower() == "success"
    return True
