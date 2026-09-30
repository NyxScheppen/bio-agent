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


def _within_directory(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _session_upload_dir(session_id: str) -> Optional[Path]:
    """Return the exact session upload directory for a simple, safe session key."""
    key = str(session_id or "").strip()
    if not key or key in {".", ".."} or Path(key).name != key or "/" in key or "\\" in key:
        return None
    candidate = UPLOAD_DIR / key
    return candidate if _within_storage(candidate) else None


def _first_file_named(base: Path, filename: str) -> Optional[Path]:
    """Find one matching file lazily without materializing the full recursive scan."""
    if not base.exists():
        return None
    return next((match for match in base.rglob(filename) if match.is_file()), None)

def resolve_file_path(file_path: str, session_id: Optional[str] = None) -> Optional[Path]:
    """
    将 agent/前端传来的文件路径解析为真实磁盘路径。
    支持：
    1. 绝对路径
    2. uploads/... / generated/... / temp/...
    3. 纯文件名 + session_id（只搜索该会话上传目录）
    4. 无 session_id 时兼容全局搜索 storage 下匹配文件

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

            # 4) 有 session 时只解析该 session，避免跨会话同名文件覆盖或泄露
            if session_id:
                session_dir = _session_upload_dir(session_id)
                if session_dir is None:
                    return None
                session_candidate = session_dir / raw
                if (
                    _within_directory(session_candidate, session_dir)
                    and session_candidate.is_file()
                ):
                    return session_candidate

                # 带 session 的调用必须使用明确的 generated/... 路径访问生成物。
                return target if _within_storage(target) else None

            # 5) 无 session 的兼容路径只对纯文件名执行惰性全局搜索
            if Path(raw).name == raw:
                for base in (GENERATED_DIR, UPLOAD_DIR):
                    match = _first_file_named(base, raw)
                    if match is not None:
                        target = match
                        break

    # 最终 containment：只允许 storage 内路径；带 session 时禁止读取其他上传目录。
    if not _within_storage(target):
        return None
    if session_id and _within_directory(target, UPLOAD_DIR):
        session_dir = _session_upload_dir(session_id)
        if session_dir is None or not _within_directory(target, session_dir):
            return None
    return target

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
