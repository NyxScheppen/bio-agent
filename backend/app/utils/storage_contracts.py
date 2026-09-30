"""Shared validation and containment rules for persisted files."""

import os
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Iterable

from app.core.paths import GENERATED_DIR, STORAGE_DIR, UPLOAD_DIR


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_FILENAME_BYTES = 240
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class StorageValidationError(ValueError):
    """Raised when a user-controlled storage identifier is invalid."""


def validate_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not SESSION_ID_PATTERN.fullmatch(value):
        raise StorageValidationError(
            "session_id 必须为 1-64 位 ASCII 字母、数字、下划线或连字符，且首位必须是字母或数字"
        )
    return value


def normalize_upload_filename(filename: str) -> str:
    raw = str(filename or "").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1].strip().rstrip(". ")
    name = _INVALID_FILENAME_CHARS.sub("_", name)

    if not name or name in {".", ".."}:
        raise StorageValidationError("上传文件名不能为空")
    if name.lower().startswith((".upload-", ".delete-")):
        raise StorageValidationError("上传文件名使用了内部保留前缀")
    if len(name.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise StorageValidationError(
            f"上传文件名过长，UTF-8 编码后不能超过 {MAX_FILENAME_BYTES} 字节"
        )

    device_name = name.split(".", 1)[0].upper()
    if device_name in _WINDOWS_RESERVED_NAMES:
        raise StorageValidationError(f"上传文件名使用了系统保留名称: {name}")
    return name


def session_upload_dir(session_id: str, *, create: bool = False) -> Path:
    sid = validate_session_id(session_id)
    directory = Path(UPLOAD_DIR) / sid
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def session_generated_dir(session_id: str, *, create: bool = False) -> Path:
    sid = validate_session_id(session_id)
    directory = Path(GENERATED_DIR) / sid
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_storage_relative_path(
    relative_path: str,
    *,
    allowed_roots: Iterable[str] = ("uploads", "generated"),
    require_exists: bool = False,
) -> Path | None:
    """Resolve a portable relative path while enforcing storage containment."""
    raw = str(relative_path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return None

    pure = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in pure.parts):
        return None
    if any(part.lower().startswith((".upload-", ".delete-")) for part in pure.parts):
        return None
    roots = {str(root).strip("/") for root in allowed_roots}
    if not pure.parts or pure.parts[0] not in roots:
        return None

    storage_root = Path(STORAGE_DIR).resolve()
    candidate = storage_root / Path(*pure.parts)
    current = storage_root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            return None
    target = candidate.resolve()
    try:
        target.relative_to(storage_root)
    except ValueError:
        return None
    if require_exists and (not target.exists() or not target.is_file()):
        return None
    return target


def generated_relative_path_for_session(relative_path: str, session_id: str) -> str | None:
    """Return a canonical generated path only when it belongs to the session."""
    sid = validate_session_id(session_id)
    target = resolve_storage_relative_path(
        relative_path,
        allowed_roots=("generated",),
        require_exists=True,
    )
    if target is None:
        return None

    session_root = (Path(GENERATED_DIR) / sid).resolve()
    try:
        target.relative_to(session_root)
    except ValueError:
        return None
    return target.relative_to(Path(STORAGE_DIR).resolve()).as_posix()


def artifact_relative_path_for_session(
    relative_path: str,
    session_id: str,
    *,
    require_exists: bool = True,
) -> str | None:
    """Canonicalize an upload/generated artifact owned by one session."""
    sid = validate_session_id(session_id)
    target = resolve_storage_relative_path(
        relative_path,
        require_exists=require_exists,
    )
    if target is None:
        return None
    storage_root = Path(STORAGE_DIR).resolve()
    relative = target.relative_to(storage_root)
    if len(relative.parts) < 3 or relative.parts[1] != sid:
        return None
    return relative.as_posix()


def is_dangerous_inline_file(path: Path | str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {
        ".html", ".htm", ".xhtml", ".svg", ".xml",
        ".js", ".mjs", ".css",
    }


def create_deletion_guard(target: Path) -> Path:
    """Pin a file inode without vacating its public name during a DB transaction."""
    guard = target.with_name(f".delete-{uuid.uuid4().hex}.tmp")
    os.link(target, guard)
    return guard


def discard_deletion_guard(guard: Path) -> None:
    guard.unlink(missing_ok=True)


def finalize_guarded_delete(target: Path, guard: Path) -> bool:
    """Delete the guarded entity without deleting a concurrently replaced path."""
    public_entity_removed = not target.exists()
    try:
        if target.exists() and guard.exists() and os.path.samefile(target, guard):
            target.unlink()
            public_entity_removed = True
        return public_entity_removed
    finally:
        guard.unlink(missing_ok=True)


def publish_staged_upload(
    session_dir: Path,
    filename: str,
    staged_path: Path,
) -> Path:
    """Atomically expose a completed staged upload without replacing a peer."""
    base_name = normalize_upload_filename(filename)
    stem, suffix = os.path.splitext(base_name)
    for index in range(10_000):
        candidate_name = base_name if index == 0 else f"{stem}_{index}{suffix}"
        candidate = session_dir / candidate_name
        try:
            os.link(staged_path, candidate)
            try:
                staged_path.unlink()
            except OSError as exc:
                for cleanup_path in (candidate, staged_path):
                    try:
                        cleanup_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise StorageValidationError(
                    f"无法清理上传暂存文件 {base_name}: {exc}"
                ) from exc
            return candidate
        except FileExistsError:
            continue
        except OSError as exc:
            raise StorageValidationError(
                f"无法原子发布上传文件 {base_name}: {exc}"
            ) from exc
    raise StorageValidationError("同名上传文件过多，无法分配唯一文件名")
