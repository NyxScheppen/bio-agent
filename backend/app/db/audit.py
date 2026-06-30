"""
非阻塞审计日志模块 (Feature 2: Audit Logs).

将 ToolProvenance + ToolResult 持久化到 SQLite tool_executions 表。
设计原则：
1. 独立 SessionLocal — 不依赖 FastAPI 依赖注入
2. 永不抛异常 — 审计失败仅打印警告，绝不影响工具执行
3. JSON 序列化在调用栈外完成 — 避免内存问题
"""

import json
import logging
from typing import Any, Dict, Optional

from app.db.database import SessionLocal
from app.db.crud import save_tool_execution

logger = logging.getLogger(__name__)


def _safe_json_dumps(obj: Any) -> Optional[str]:
    """安全 JSON 序列化，失败返回 None。"""
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return None


def audit_tool_execution(
    tool_result: Any,   # ToolResult (lazy import)
    session_id: str = "",
    retry_count: int = 0,
) -> None:
    """
    将一次工具有执行持久化到数据库。

    设计为 fire-and-forget：任何异常都被捕获并打印警告，
    绝不向上传播影响工具执行流。

    Args:
        tool_result: ToolResult 实例
        session_id: 会话 ID
        retry_count: 已重试次数（Feature 3 使用）
    """
    try:
        prov = tool_result.provenance

        # 序列化 JSON 字段
        params_json = _safe_json_dumps(prov.parameters)

        errors_json = _safe_json_dumps(
            tool_result.errors if tool_result.errors else None
        )

        warnings_json = _safe_json_dumps(
            tool_result.warnings if tool_result.warnings else None
        )

        # output_files: 只存 name/url/relative_path 三个关键字段
        output_files_slim = []
        for f in (tool_result.output_files or []):
            if hasattr(f, "model_dump"):
                d = f.model_dump()
            elif isinstance(f, dict):
                d = f
            else:
                continue
            output_files_slim.append({
                "name": d.get("name", ""),
                "url": d.get("url", ""),
                "relative_path": d.get("relative_path", ""),
            })
        output_files_json = _safe_json_dumps(output_files_slim if output_files_slim else None)

        resource_json = None
        if prov.resource_usage:
            if hasattr(prov.resource_usage, "model_dump"):
                resource_json = _safe_json_dumps(prov.resource_usage.model_dump())
            elif isinstance(prov.resource_usage, dict):
                resource_json = _safe_json_dumps(prov.resource_usage)

        recovery_json = None
        if hasattr(tool_result, "retry_records") and tool_result.retry_records:
            records = []
            for r in tool_result.retry_records:
                if hasattr(r, "model_dump"):
                    records.append(r.model_dump())
                elif isinstance(r, dict):
                    records.append(r)
            recovery_json = _safe_json_dumps(records if records else None)

        # 独立数据库 Session
        db = SessionLocal()
        try:
            save_tool_execution(
                db=db,
                session_id=session_id or "",
                job_id=prov.job_id or "",
                tool_name=prov.tool_name or "",
                tool_category=prov.tool_category or "general",
                status=tool_result.status or "success",
                parameters_json=params_json,
                started_at=prov.started_at,
                finished_at=prov.finished_at,
                runtime_seconds=prov.runtime_seconds,
                message=tool_result.message,
                errors_json=errors_json,
                warnings_json=warnings_json,
                output_files_json=output_files_json,
                resource_usage_json=resource_json,
                retry_count=retry_count or 0,
                recovery_attempts_json=recovery_json,
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Audit log write failed (non-fatal): {e}")


def audit_tool_execution_safe(
    tool_result: Any,
    session_id: str = "",
    retry_count: int = 0,
) -> None:
    """
    audit_tool_execution 的完全安全包装。
    即使 audit 模块本身有 bug，也不会影响调用方。
    """
    try:
        audit_tool_execution(
            tool_result=tool_result,
            session_id=session_id,
            retry_count=retry_count,
        )
    except Exception:
        # 绝对静默
        pass
