from pathlib import Path

from app.core.paths import GENERATED_DIR, STORAGE_DIR, UPLOAD_DIR
from app.db import crud
from app.utils.storage_contracts import (
    artifact_relative_path_for_session,
    create_deletion_guard,
    discard_deletion_guard,
    finalize_guarded_delete,
    resolve_storage_relative_path,
    StorageValidationError,
    validate_session_id,
)


def _safe_resolve_storage_path(relative_path: str) -> Path | None:
    return resolve_storage_relative_path(relative_path, require_exists=False)


def _cleanup_empty_parent_dirs(path: Path):
    stop_dirs = {
        Path(STORAGE_DIR).resolve(),
        Path(GENERATED_DIR).resolve(),
        Path(UPLOAD_DIR).resolve(),
    }
    current = path.parent.resolve()
    while current not in stop_dirs:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent.resolve()


def _stage_file_for_deletion(db, file_record, session_id: str):
    relative_path = getattr(file_record, "relative_path", "")
    result = {
        "filename": getattr(file_record, "filename", ""),
        "relative_path": relative_path,
        "source_type": getattr(file_record, "source_type", ""),
        "deleted": False,
        "reason": "",
    }
    target = _safe_resolve_storage_path(relative_path)
    if target is None:
        result["reason"] = "非法路径，未删除记录"
        return result, None, False
    other_references = crud.count_other_file_references(
        db,
        session_id,
        relative_path,
    )
    owned_path = artifact_relative_path_for_session(
        relative_path,
        session_id,
        require_exists=False,
    )
    if owned_path is None and other_references == 0:
        try:
            storage_relative = target.relative_to(Path(STORAGE_DIR).resolve())
        except ValueError:
            storage_relative = Path()
        is_legacy_generated = (
            getattr(file_record, "source_type", "") == "generated"
            and len(storage_relative.parts) >= 3
            and storage_relative.parts[0] == "generated"
            and crud.get_session(db, storage_relative.parts[1]) is None
        )
        if not is_legacy_generated:
            result["reason"] = "文件路径不属于当前会话，未删除记录"
            return result, None, False
    if other_references > 0:
        result["reason"] = "文件仍被其他会话引用，仅删除当前会话记录"
        return result, None, True
    if not target.exists():
        result["reason"] = "文件不存在，删除失效记录"
        return result, None, True
    if not target.is_file():
        result["reason"] = "目标是目录，未删除记录"
        return result, None, False

    try:
        guard = create_deletion_guard(target)
    except Exception as exc:
        result["reason"] = f"文件暂存失败：{exc}"
        return result, None, False
    result["reason"] = "等待数据库提交"
    return result, (target, guard), True


def _discard_deletion_guards(staged_files):
    for _, guard, _ in reversed(staged_files):
        try:
            discard_deletion_guard(guard)
        except OSError:
            pass


def delete_session_with_files(
    db,
    session_id: str,
    delete_uploads: bool = True,
    delete_generated: bool = True,
):
    """Delete selected artifacts; delete the session itself only for a full delete."""
    try:
        session_id = validate_session_id(session_id)
    except StorageValidationError as exc:
        return {"status": "error", "message": str(exc)}

    session = crud.get_session(db, session_id)
    if not session:
        return {"status": "error", "message": f"会话不存在：{session_id}"}

    file_records = crud.get_files_by_session(db, session_id)
    records_to_delete = []
    skipped_records = []
    for record in file_records:
        source_type = getattr(record, "source_type", "")
        selected = (
            source_type == "generated" and delete_generated
        ) or (
            source_type == "upload" and delete_uploads
        )
        if selected:
            records_to_delete.append(record)
        else:
            skipped_records.append({
                "filename": getattr(record, "filename", ""),
                "relative_path": getattr(record, "relative_path", ""),
                "source_type": source_type,
                "reason": "当前删除参数选择保留该类型文件",
            })

    staged_files = []
    staged_results = []
    failed_files = []
    records_ready = []
    for record in records_to_delete:
        result, staged, ready = _stage_file_for_deletion(db, record, session_id)
        staged_results.append(result)
        if staged:
            staged_files.append((*staged, result))
        if ready:
            records_ready.append(record)
        else:
            failed_files.append(result)

    if failed_files:
        _discard_deletion_guards(staged_files)
        db.rollback()
        return {
            "status": "error",
            "message": "部分文件无法安全删除，数据库未修改",
            "session_id": session_id,
            "failed_files": failed_files,
            "skipped_files": skipped_records,
        }

    full_delete = delete_uploads and delete_generated
    try:
        for record in records_ready:
            db.delete(record)

        message_count = 0
        session_count = 0
        execution_count = 0
        if full_delete:
            message_count = crud.delete_messages_by_session(db, session_id)
            execution_count = crud.delete_tool_executions_by_session(db, session_id)
            session_count = crud.delete_session_record(db, session_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        _discard_deletion_guards(staged_files)
        return {
            "status": "error",
            "message": f"数据库删除失败：{exc}",
            "session_id": session_id,
            "failed_files": failed_files,
            "skipped_files": skipped_records,
        }

    deleted_files = []
    cleanup_failures = []
    for target, guard, result in staged_files:
        try:
            target_deleted = finalize_guarded_delete(target, guard)
            if target_deleted:
                result["deleted"] = True
                result["reason"] = "删除成功"
                _cleanup_empty_parent_dirs(target)
                deleted_files.append(result)
            else:
                result["reason"] = "路径已被并发替换，替换文件已保留"
                cleanup_failures.append(result)
        except OSError as exc:
            result["reason"] = f"数据库已提交，但删除守卫清理失败：{exc}"
            cleanup_failures.append(result)

    stale_or_shared = [result for result in staged_results if not result["deleted"]]
    return {
        "status": "success",
        "message": "会话删除完成" if full_delete else "选定类型文件删除完成",
        "session_id": session_id,
        "deleted_files_count": len(deleted_files),
        "failed_files_count": len(cleanup_failures),
        "skipped_files_count": len(skipped_records),
        "deleted_db_records": {
            "stored_files": len(records_ready),
            "chat_messages": message_count,
            "tool_executions": execution_count,
            "chat_sessions": session_count,
        },
        "deleted_files": deleted_files,
        "stale_or_shared_files": stale_or_shared,
        "failed_files": cleanup_failures,
        "skipped_files": skipped_records,
    }


def delete_session_generated_files_only(db, session_id: str):
    return delete_session_with_files(
        db=db,
        session_id=session_id,
        delete_uploads=False,
        delete_generated=True,
    )
