from pathlib import Path
from typing import Optional
import os

BACKEND_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BACKEND_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
GENERATED_DIR = STORAGE_DIR / "generated"
TEMP_DIR = STORAGE_DIR / "temp"

_STORAGE_ROOT = STORAGE_DIR.resolve()


def _within_storage(path: Path) -> bool:
    """判断路径是否落在 storage 根目录内，防止路径穿越读取 storage 外文件（如 ../.env）。"""
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return False

    try:
        resolved.relative_to(_STORAGE_ROOT)
        return True
    except ValueError:
        return False

def resolve_file_path(file_path: str, session_id: Optional[str] = None) -> Optional[Path]:
    """
    将 agent/前端传来的文件路径解析为真实磁盘路径。
    支持：
    1. 绝对路径
    2. uploads/... / generated/... / temp/...
    3. 纯文件名 + session_id
    4. 全局搜索 storage 下匹配文件

    路径穿越到 storage 外（如 ../.env）时返回 None，调用方按「文件不存在」处理。
    """
    if not file_path:
        return None

    raw = str(file_path).strip().replace("\\", "/")
    p = Path(raw)

    target: Path = Path("")

    # 1) 绝对路径
    if p.is_absolute():
        target = p
    else:
        # 2) 去掉前导斜杠
        raw = raw.lstrip("/")

        # 3) 标准逻辑路径
        if raw.startswith(("uploads/", "generated/", "temp/")):
            target = STORAGE_DIR / raw
        elif raw.startswith("storage/"):
            target = BACKEND_DIR / raw
        else:
            target = STORAGE_DIR / raw  # 兜底默认值，下面再覆盖

            # 4) 如果只是文件名，优先到当前 session 上传目录找
            if session_id:
                session_candidate = UPLOAD_DIR / session_id / raw
                if session_candidate.exists():
                    target = session_candidate

            # 5) 去 generated 里全局找
            # 6) 去 uploads 里全局找
            for base in (GENERATED_DIR, UPLOAD_DIR):
                matches = list(base.rglob(raw))
                if matches:
                    target = matches[0]
                    break

    # 最终 containment：只允许 storage 内的路径
    return target if _within_storage(target) else None

def debug_file_context(file_path: str, session_id: Optional[str] = None) -> dict:
    resolved = resolve_file_path(file_path, session_id)
    return {
        "cwd": os.getcwd(),
        "input_file_path": file_path,
        "session_id": session_id,
        "resolved_path": str(resolved) if resolved is not None else "",
        "resolved_exists": resolved is not None and resolved.exists(),
        "backend_dir": str(BACKEND_DIR),
        "storage_dir": str(STORAGE_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "generated_dir": str(GENERATED_DIR),
    }