import os
import uuid
from pathlib import Path

from app.core.config import (
    MAX_UPLOAD_BATCH_BYTES,
    MAX_UPLOAD_FILE_BYTES,
    MAX_UPLOAD_FILES,
)
from app.db import crud
from app.utils.file_utils import build_file_url, detect_file_type
from app.utils.storage_contracts import (
    StorageValidationError,
    normalize_upload_filename,
    publish_staged_upload,
    session_upload_dir,
    validate_session_id,
)


UPLOAD_CHUNK_BYTES = 1024 * 1024


class UploadLimitError(StorageValidationError):
    """Raised when an upload exceeds a configured resource budget."""


def _check_upload_batch(files) -> list:
    file_list = list(files or [])
    if not file_list:
        raise StorageValidationError("未检测到上传文件")
    if len(file_list) > MAX_UPLOAD_FILES:
        raise UploadLimitError(
            f"单次最多上传 {MAX_UPLOAD_FILES} 个文件，当前为 {len(file_list)} 个"
        )

    declared_total = 0
    for upload in file_list:
        normalize_upload_filename(getattr(upload, "filename", ""))
        declared_size = getattr(upload, "size", None)
        if isinstance(declared_size, int) and declared_size >= 0:
            if declared_size > MAX_UPLOAD_FILE_BYTES:
                raise UploadLimitError(
                    f"文件 {upload.filename} 超过单文件上限 {MAX_UPLOAD_FILE_BYTES} 字节"
                )
            declared_total += declared_size
    if declared_total > MAX_UPLOAD_BATCH_BYTES:
        raise UploadLimitError(
            f"上传批次超过总上限 {MAX_UPLOAD_BATCH_BYTES} 字节"
        )
    return file_list


def _write_one_upload(file, session_dir: Path, batch_bytes: int) -> tuple[Path, int]:
    filename = normalize_upload_filename(getattr(file, "filename", ""))
    staged_path = session_dir / f".upload-{uuid.uuid4().hex}.tmp"
    descriptor = os.open(
        staged_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        0o600,
    )
    file_bytes = 0

    try:
        with os.fdopen(descriptor, "wb") as buffer:
            descriptor = -1
            while True:
                chunk = file.file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, (bytes, bytearray)):
                    raise StorageValidationError(f"文件 {filename} 返回了非二进制内容")

                file_bytes += len(chunk)
                if file_bytes > MAX_UPLOAD_FILE_BYTES:
                    raise UploadLimitError(
                        f"文件 {filename} 超过单文件上限 {MAX_UPLOAD_FILE_BYTES} 字节"
                    )
                if batch_bytes + file_bytes > MAX_UPLOAD_BATCH_BYTES:
                    raise UploadLimitError(
                        f"上传批次超过总上限 {MAX_UPLOAD_BATCH_BYTES} 字节"
                    )
                buffer.write(chunk)

            buffer.flush()
            os.fsync(buffer.fileno())
        save_path = publish_staged_upload(session_dir, filename, staged_path)
        return save_path, file_bytes
    except Exception:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        staged_path.unlink(missing_ok=True)
        raise


def _upload_result(session_id: str, path: Path, size_bytes: int) -> dict:
    relative_path = f"uploads/{session_id}/{path.name}"
    return {
        "message": "上传成功",
        "filename": path.name,
        "relative_path": relative_path,
        "url": build_file_url(relative_path),
        "type": detect_file_type(path.name),
        "size_bytes": size_bytes,
    }


def save_upload_files(db, files, session_id: str = "default"):
    """Persist one upload batch with all-or-nothing database/file cleanup."""
    sid = validate_session_id(session_id)
    file_list = _check_upload_batch(files)
    session_dir = session_upload_dir(sid, create=True)
    created_paths: list[Path] = []
    results: list[dict] = []
    batch_bytes = 0

    try:
        crud.create_session(db, session_id=sid, commit=False)
        for upload in file_list:
            save_path, size_bytes = _write_one_upload(upload, session_dir, batch_bytes)
            created_paths.append(save_path)
            batch_bytes += size_bytes
            result = _upload_result(sid, save_path, size_bytes)
            results.append(result)
            crud.save_file_record(
                db=db,
                session_id=sid,
                filename=save_path.name,
                relative_path=result["relative_path"],
                file_type=result["type"],
                source_type="upload",
                commit=False,
            )
        db.commit()
    except Exception:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise

    return {
        "message": "批量上传成功",
        "files": results,
        "total_size_bytes": batch_bytes,
    }


def save_upload_file(db, file, session_id: str = "default"):
    return save_upload_files(db, [file], session_id=session_id)["files"][0]


def list_uploaded_files(session_id: str = "default"):
    sid = validate_session_id(session_id)
    session_dir = session_upload_dir(sid, create=False)
    files = []

    if session_dir.exists() and session_dir.is_dir():
        for path in sorted(session_dir.iterdir(), key=lambda item: item.name.lower()):
            if (
                not path.is_file()
                or path.is_symlink()
                or path.name.startswith((".delete-", ".upload-"))
            ):
                continue
            relative_path = f"uploads/{sid}/{path.name}"
            files.append({
                "filename": path.name,
                "relative_path": relative_path,
                "url": build_file_url(relative_path),
                "type": detect_file_type(path.name),
                "size_bytes": path.stat().st_size,
            })
    return {"session_id": sid, "files": files}


def delete_uploaded_file(db, session_id: str, filename: str):
    """Delete an upload and its records, restoring the file if the DB commit fails."""
    sid = validate_session_id(session_id)
    safe_filename = normalize_upload_filename(filename)
    session_dir = session_upload_dir(sid, create=False)
    target = session_dir / safe_filename

    if not target.exists() or not target.is_file():
        return {"status": "error", "message": f"文件不存在: {safe_filename}"}

    tombstone = session_dir / f".delete-{uuid.uuid4().hex}.tmp"
    os.replace(target, tombstone)
    relative_path = f"uploads/{sid}/{safe_filename}"
    try:
        deleted_records = crud.delete_file_record_by_path(
            db,
            session_id=sid,
            relative_path=relative_path,
            source_type="upload",
        )
        db.commit()
    except Exception:
        db.rollback()
        os.replace(tombstone, target)
        raise

    tombstone.unlink(missing_ok=True)
    return {
        "status": "success",
        "message": "文件删除成功",
        "filename": safe_filename,
        "deleted_records": deleted_records,
    }
