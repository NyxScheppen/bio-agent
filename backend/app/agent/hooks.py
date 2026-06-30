"""
Hook 系统 (Phase 5.2: Event-Based Automation).

参考 ECC 的 Hooks 系统，在工具执行生命周期关键节点触发事件。
支持注册回调函数，默认提供 error_notification 和 cleanup hooks。

用法:
    from app.agent.hooks import hook_manager, HookPoint
    hook_manager.register(HookPoint.POST_TOOL_EXECUTION, my_callback)
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class HookPoint(Enum):
    """Hook 触发点。"""
    PRE_TOOL_EXECUTION = "pre_tool"
    POST_TOOL_EXECUTION = "post_tool"
    PRE_REPORTING = "pre_report"
    POST_AGENT_TURN = "post_turn"


class HookManager:
    """
    轻量级 Hook 管理器。

    支持同步和异步回调。
    回调失败不传播异常——单个 Hook 失败不影响其他 Hook 或主流程。
    """

    def __init__(self):
        self._hooks: Dict[HookPoint, List[Callable]] = {
            hp: [] for hp in HookPoint
        }

    def register(self, hook_point: HookPoint, callback: Callable) -> None:
        """
        注册一个 Hook 回调。

        Args:
            hook_point: 触发点
            callback: 回调函数，签名为 callback(context: dict) -> None
        """
        if callback not in self._hooks[hook_point]:
            self._hooks[hook_point].append(callback)

    def unregister(self, hook_point: HookPoint, callback: Callable) -> None:
        """移除一个 Hook 回调。"""
        if callback in self._hooks[hook_point]:
            self._hooks[hook_point].remove(callback)

    def trigger(self, hook_point: HookPoint, context: Dict[str, Any] = None) -> None:
        """
        触发指定 Hook 点的所有回调。

        Args:
            hook_point: 触发点
            context: 传递给回调的上下文数据
        """
        ctx = context or {}
        for callback in self._hooks.get(hook_point, []):
            try:
                callback(ctx)
            except Exception:
                # Hook 失败静默，不影响主流程
                pass

    def clear(self) -> None:
        """清空所有 Hook。"""
        for hp in HookPoint:
            self._hooks[hp].clear()


# 全局单例
hook_manager = HookManager()


# ============================================================
# 默认 Hooks
# ============================================================

def _default_error_notification(ctx: Dict[str, Any]) -> None:
    """
    工具有执行失败时的默认通知 Hook。
    将错误信息记录到日志目录。
    """
    tool_name = ctx.get("tool_name", "unknown")
    status = ctx.get("status", "")
    if status != "error":
        return

    try:
        from pathlib import Path
        from app.core.runtime_paths import PROJECT_ROOT
        import json
        from datetime import datetime

        log_dir = PROJECT_ROOT / "logs" / "hook_errors"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "tool_errors.jsonl"

        entry = {
            "timestamp": datetime.now().isoformat(),
            **{k: str(v)[:500] for k, v in ctx.items()},
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _default_cleanup_temp_files(ctx: Dict[str, Any]) -> None:
    """
    每轮 Agent 结束后清理临时文件。
    """
    try:
        from pathlib import Path
        from app.core.runtime_paths import TEMP_DIR
        import time

        if not TEMP_DIR or not TEMP_DIR.exists():
            return

        now = time.time()
        max_age = 3600  # 1 小时

        for p in TEMP_DIR.rglob("*"):
            if p.is_file():
                try:
                    if now - p.stat().st_mtime > max_age:
                        p.unlink()
                except Exception:
                    pass
    except Exception:
        pass


# 注册默认 Hooks
hook_manager.register(HookPoint.POST_TOOL_EXECUTION, _default_error_notification)
hook_manager.register(HookPoint.POST_AGENT_TURN, _default_cleanup_temp_files)
