from pathlib import Path

from app.core.paths import STORAGE_DIR, GENERATED_DIR, UPLOAD_DIR
from app.db import crud

def _safe_resolve_storage_path(relative_path: str) -> Path | None:
    """
    把数据库里的 relative_path 安全解析成真实磁盘路径。
    """
    if not relative_path:
        return None

    rel = str(relative_path).replace("\\", "/").strip()
    rel = rel.lstrip("/")

    # 防止 ../../ 这种路径穿越
    if ".." in Path(rel).parts:
        return None

    storage_root = Path(STORAGE_DIR).resolve()
    target = (storage_root / rel).resolve()

    try:
        target.relative_to(storage_root)
    except ValueError:
        return None

    return target

def _cleanup_empty_parent_dirs(path: Path):
    """
    删除文件后，顺手清理空目录。
    """
    if not path:
        return

    stop_dirs = {
        Path(STORAGE_DIR).resolve(),
        Path(GENERATED_DIR).resolve(),
        Path(UPLOAD_DIR).resolve()
    }

    current = path.parent.resolve()

    while current not in stop_dirs:
        if not current.exists():
            current = current.parent.resolve()
            continue

        try:
            current.rmdir()
        except OSError:
            # 目录非空，停止
            break
        except Exception:
            break

        current = current.parent.resolve()

def _delete_one_file_by_record(file_record):
    """
    根据 StoredFile 记录删除真实磁盘文件。

    返回格式：
    {
        "filename": "...",
        "relative_path": "...",
        "source_type": "...",
        "deleted": true/false,
        "reason": "..."
    }
    """
    filename = getattr(file_record, "filename", "")
    relative_path = getattr(file_record, "relative_path", "")
    source_type = getattr(file_record, "source_type", "")

    result = {
        "filename": filename,
        "relative_path": relative_path,
        "source_type": source_type,
        "deleted": False,
        "reason": ""
    }

    target = _safe_resolve_storage_path(relative_path)

    if target is None:
        result["reason"] = "非法路径，已跳过"
        return result

    if not target.exists():
        result["reason"] = "文件不存在，可能已被手动删除"
        return result

    if target.is_dir():
        result["reason"] = "目标是目录，不按文件记录删除"
        return result

    try:
        target.unlink()
        result["deleted"] = True
        result["reason"] = "删除成功"
        _cleanup_empty_parent_dirs(target)
        return result
    except Exception as e:
        result["reason"] = f"删除失败：{str(e)}"
        return result

def delete_session_with_files(
    db,
    session_id: str,
    delete_uploads: bool = True,
    delete_generated: bool = True
):
    """
    删除一个会话，同时删除该会话关联的文件。
    """
    session_id = str(session_id or "").strip()

    if not session_id:
        return {
            "status": "error",
            "message": "session_id 不能为空"
        }

    session = crud.get_session(db, session_id)
    if not session:
        return {
            "status": "error",
            "message": f"会话不存在：{session_id}"
        }

    file_records = crud.get_files_by_session(db, session_id)

    records_to_delete = []
    skipped_records = []

    for f in file_records:
        source_type = getattr(f, "source_type", "")

        if source_type == "generated" and delete_generated:
            records_to_delete.append(f)
        elif source_type == "upload" and delete_uploads:
            records_to_delete.append(f)
        else:
            skipped_records.append({
                "filename": getattr(f, "filename", ""),
                "relative_path": getattr(f, "relative_path", ""),
                "source_type": source_type,
                "reason": "当前删除参数选择保留该类型文件"
            })

    deleted_files = []
    failed_files = []

    # 先删真实文件
    for f in records_to_delete:
        res = _delete_one_file_by_record(f)
        if res.get("deleted"):
            deleted_files.append(res)
        else:
            failed_files.append(res)

    # 再删数据库记录
    try:
        file_record_count = crud.delete_file_records_by_session(db, session_id)
        message_count = crud.delete_messages_by_session(db, session_id)
        session_count = crud.delete_session_record(db, session_id)

        db.commit()

        return {
            "status": "success",
            "message": "会话及关联文件删除完成",
            "session_id": session_id,
            "deleted_files_count": len(deleted_files),
            "failed_files_count": len(failed_files),
            "skipped_files_count": len(skipped_records),
            "deleted_db_records": {
                "stored_files": file_record_count,
                "chat_messages": message_count,
                "chat_sessions": session_count
            },
            "deleted_files": deleted_files,
            "failed_files": failed_files,
            "skipped_files": skipped_records
        }

    except Exception as e:
        db.rollback()

        return {
            "status": "error",
            "message": f"数据库删除失败：{str(e)}",
            "session_id": session_id,
            "deleted_files_before_db_error": deleted_files,
            "failed_files": failed_files,
            "skipped_files": skipped_records
        }

def delete_session_generated_files_only(db, session_id: str):
    """
    只删除会话关联的 generated 文件，不删除上传文件。
    """
    return delete_session_with_files(
        db=db,
        session_id=session_id,
        delete_uploads=False,
        delete_generated=True
    )