from pathlib import Path
from typing import Optional
import os

BACKEND_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BACKEND_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
GENERATED_DIR = STORAGE_DIR / "generated"
TEMP_DIR = STORAGE_DIR / "temp"

def resolve_file_path(file_path: str, session_id: Optional[str] = None) -> Path:
    """
    将 agent/前端传来的文件路径解析为真实磁盘路径。
    支持：
    1. 绝对路径
    2. uploads/... / generated/... / temp/...
    3. 纯文件名 + session_id
    4. 全局搜索 storage 下匹配文件
    """
    if not file_path:
        return Path("")

    raw = str(file_path).strip().replace("\\", "/")
    p = Path(raw)

    # 1) 绝对路径直接返回
    if p.is_absolute():
        return p

    # 2) 去掉前导斜杠
    raw = raw.lstrip("/")

    # 3) 标准逻辑路径
    if raw.startswith("uploads/"):
        return STORAGE_DIR / raw

    if raw.startswith("generated/"):
        return STORAGE_DIR / raw

    if raw.startswith("temp/"):
        return STORAGE_DIR / raw

    if raw.startswith("storage/"):
        return BACKEND_DIR / raw

    # 4) 如果只是文件名，优先到当前 session 上传目录找
    if session_id:
        session_candidate = UPLOAD_DIR / session_id / raw
        if session_candidate.exists():
            return session_candidate

    # 5) 去 generated 里全局找
    generated_matches = list(GENERATED_DIR.rglob(raw))
    if generated_matches:
        return generated_matches[0]

    # 6) 去 uploads 里全局找
    upload_matches = list(UPLOAD_DIR.rglob(raw))
    if upload_matches:
        return upload_matches[0]

    # 7) 最后兜底返回 storage 相对路径
    return STORAGE_DIR / raw

def debug_file_context(file_path: str, session_id: Optional[str] = None) -> dict:
    resolved = resolve_file_path(file_path, session_id)
    return {
        "cwd": os.getcwd(),
        "input_file_path": file_path,
        "session_id": session_id,
        "resolved_path": str(resolved),
        "resolved_exists": resolved.exists(),
        "backend_dir": str(BACKEND_DIR),
        "storage_dir": str(STORAGE_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "generated_dir": str(GENERATED_DIR),
    }