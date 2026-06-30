"""
工具执行上下文 ToolExecutionContext。

统一工具执行时的元数据容器：
- job_id / job_dir 自动生成
- session_id 关联
- 参数快照
- 时间记录
"""

import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.runtime_paths import GENERATED_DIR


# 在 GENERATED_DIR 下按 session 组织 job 目录
#   generated/{session_id}/{job_id}/
# 当 session_id 为空时：
#   generated/{job_id}/
def _make_job_dir(session_id: str = "", job_id: str = "") -> Path:
    """构建 job 输出目录路径并自动创建。"""
    sid = _safe_path_segment(session_id)
    jid = _safe_path_segment(job_id)

    if sid and jid:
        job_dir = GENERATED_DIR / sid / jid
    elif jid:
        job_dir = GENERATED_DIR / jid
    elif sid:
        # 有 session 但无 job_id，给一个默认
        fallback_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = GENERATED_DIR / sid / fallback_id
    else:
        fallback_id = f"job_{uuid.uuid4().hex[:8]}"
        job_dir = GENERATED_DIR / fallback_id

    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _safe_path_segment(value: str) -> str:
    """过滤路径分隔符等不安全字符。"""
    if not value:
        return ""
    value = str(value).strip()
    if not value:
        return ""
    # 移除路径分隔符和 ..
    value = value.replace("\\", "_").replace("/", "_").replace("..", "_")
    # 只保留字母数字、下划线、连字符
    return "".join(c for c in value if c.isalnum() or c in "_-")[:64]


class ToolExecutionContext:
    """
    工具执行上下文。

    包含：
    - job_id: 本次工具调用的唯一 ID
    - session_id: 会话 ID
    - tool_name: 工具名
    - tool_category: 工具类别
    - job_dir: 输出目录（自动创建）
    - started_at: 开始时间 ISO 字符串
    - parameters: 工具参数快照
    - storage_dir: STORAGE_DIR 备份
    - generated_dir: GENERATED_DIR 备份
    """

    def __init__(
        self,
        tool_name: str = "",
        tool_category: str = "",
        session_id: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        job_id: str = "",
        job_dir: str = "",
    ):
        self.tool_name = str(tool_name or "")
        self.tool_category = str(tool_category or "")
        self.session_id = str(session_id or "")
        self.parameters = dict(parameters or {})

        # 生成 job_id
        if job_id:
            self.job_id = _safe_path_segment(job_id)
        else:
            short_name = _safe_path_segment(tool_name) or "tool"
            self.job_id = f"{short_name}_{uuid.uuid4().hex[:8]}"

        # 创建 job_dir
        if job_dir:
            self.job_dir = str(Path(job_dir))
            Path(self.job_dir).mkdir(parents=True, exist_ok=True)
        else:
            self.job_dir = str(_make_job_dir(
                session_id=self.session_id,
                job_id=self.job_id,
            ))

        self.started_at = datetime.now().isoformat()

        # 路径引用
        from app.core.runtime_paths import STORAGE_DIR
        self.storage_dir = str(STORAGE_DIR)
        self.generated_dir = str(GENERATED_DIR)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "tool_category": self.tool_category,
            "job_dir": self.job_dir,
            "started_at": self.started_at,
            "parameters": self.parameters,
            "storage_dir": self.storage_dir,
            "generated_dir": self.generated_dir,
        }

    def __repr__(self) -> str:
        return (
            f"ToolExecutionContext(job_id={self.job_id!r}, "
            f"tool={self.tool_name!r}, "
            f"session={self.session_id!r}, "
            f"dir={self.job_dir!r})"
        )


def create_tool_context(
    tool_name: str = "",
    session_id: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    tool_category: str = "",
) -> ToolExecutionContext:
    """
    工厂函数：创建 ToolExecutionContext。

    自动生成 job_id 和 job_dir。

    Args:
        tool_name: 工具名
        session_id: 会话 ID
        parameters: 工具参数
        tool_category: 工具类别
    """
    return ToolExecutionContext(
        tool_name=tool_name,
        tool_category=tool_category,
        session_id=session_id,
        parameters=parameters or {},
    )
