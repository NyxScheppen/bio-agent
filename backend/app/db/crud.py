from app.db.models import ChatSession, ChatMessage, StoredFile
from sqlalchemy import func, distinct

def create_session(db, session_id: str, title: str = "新会话"):
    """
    若会话不存在则创建，会话已存在就直接返回
    """
    existing = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if existing:
        return existing

    session = ChatSession(session_id=session_id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def get_session(db, session_id: str):
    """
    获取单个会话
    """
    return db.query(ChatSession).filter(ChatSession.session_id == session_id).first()

def update_session_title(db, session_id: str, title: str):
    """
    更新会话标题
    """
    session = get_session(db, session_id)
    if not session:
        return None

    session.title = title
    db.commit()
    db.refresh(session)
    return session

def ensure_session_title(db, session_id: str, title: str):
    """
    只有标题为空或默认标题时才更新，避免后续覆盖用户已有标题
    """
    session = get_session(db, session_id)
    if not session:
        return None

    current_title = (session.title or "").strip()
    if current_title in ["", "新会话"]:
        session.title = title
        db.commit()
        db.refresh(session)

    return session

def save_message(db, session_id: str, role: str, content: str):
    """
    保存一条消息
    """
    msg = ChatMessage(session_id=session_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

def get_session_messages(db, session_id: str):
    """
    获取某个会话下的所有消息，按时间顺序
    """
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )

def save_file_record(
    db,
    session_id: str,
    filename: str,
    relative_path: str,
    file_type: str,
    source_type: str
):
    """
    保存文件记录

    source_type:
    - upload: 用户上传文件
    - generated: 工具生成文件
    """
    file_obj = StoredFile(
        session_id=session_id,
        filename=filename,
        relative_path=relative_path,
        file_type=file_type,
        source_type=source_type
    )
    db.add(file_obj)
    db.commit()
    db.refresh(file_obj)
    return file_obj

def get_session_files(db, session_id: str):
    """
    获取某个会话关联的所有文件
    """
    return (
        db.query(StoredFile)
        .filter(StoredFile.session_id == session_id)
        .order_by(StoredFile.id.desc())
        .all()
    )

def get_files_by_session(db, session_id: str):
    """
    get_session_files 的别名。
    """
    return get_session_files(db, session_id)

def get_generated_files_by_session(db, session_id: str):
    """
    获取某个会话关联的生成文件
    """
    return (
        db.query(StoredFile)
        .filter(
            StoredFile.session_id == session_id,
            StoredFile.source_type == "generated"
        )
        .order_by(StoredFile.id.desc())
        .all()
    )

def get_upload_files_by_session(db, session_id: str):
    """
    获取某个会话关联的上传文件
    """
    return (
        db.query(StoredFile)
        .filter(
            StoredFile.session_id == session_id,
            StoredFile.source_type == "upload"
        )
        .order_by(StoredFile.id.desc())
        .all()
    )

def get_first_uploaded_file(db, session_id: str):
    """
    获取该会话最早上传的文件
    """
    return (
        db.query(StoredFile)
        .filter(
            StoredFile.session_id == session_id,
            StoredFile.source_type == "upload"
        )
        .order_by(StoredFile.id.asc())
        .first()
    )

def get_all_sessions(db):
    """
    获取所有会话及其消息数、文件数。
    """
    results = (
        db.query(
            ChatSession,
            func.count(distinct(ChatMessage.id)).label("message_count"),
            func.count(distinct(StoredFile.id)).label("file_count")
        )
        .outerjoin(ChatMessage, ChatSession.session_id == ChatMessage.session_id)
        .outerjoin(StoredFile, ChatSession.session_id == StoredFile.session_id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
        .all()
    )
    return results

def delete_messages_by_session(db, session_id: str):
    """
    删除某个会话下的所有聊天消息。
    """
    count = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .delete(synchronize_session=False)
    )
    return count

def delete_file_records_by_session(db, session_id: str):
    """
    删除某个会话下的所有文件数据库记录。
    """
    count = (
        db.query(StoredFile)
        .filter(StoredFile.session_id == session_id)
        .delete(synchronize_session=False)
    )
    return count

def delete_generated_file_records_by_session(db, session_id: str):
    """
    删除某个会话下的 generated 文件数据库记录。
    """
    count = (
        db.query(StoredFile)
        .filter(
            StoredFile.session_id == session_id,
            StoredFile.source_type == "generated"
        )
        .delete(synchronize_session=False)
    )
    return count

def delete_upload_file_records_by_session(db, session_id: str):
    """
    删除某个会话下的 upload 文件数据库记录。
    """
    count = (
        db.query(StoredFile)
        .filter(
            StoredFile.session_id == session_id,
            StoredFile.source_type == "upload"
        )
        .delete(synchronize_session=False)
    )
    return count

def delete_session_record(db, session_id: str):
    """
    删除会话记录。
    """
    count = (
        db.query(ChatSession)
        .filter(ChatSession.session_id == session_id)
        .delete(synchronize_session=False)
    )
    return count


# ============================================================
# ToolExecution 审计日志 CRUD (Feature 2)
# ============================================================

def save_tool_execution(
    db,
    session_id: str,
    job_id: str,
    tool_name: str,
    tool_category: str = "general",
    status: str = "success",
    parameters_json: str = None,
    started_at: str = None,
    finished_at: str = None,
    runtime_seconds: float = None,
    message: str = None,
    errors_json: str = None,
    warnings_json: str = None,
    output_files_json: str = None,
    resource_usage_json: str = None,
    retry_count: int = 0,
    recovery_attempts_json: str = None,
):
    """
    写入一条工具有执行审计记录。

    所有 JSON 字段由调用方序列化后传入。
    """
    from app.db.models import ToolExecution

    record = ToolExecution(
        session_id=session_id,
        job_id=job_id or "",
        tool_name=tool_name or "",
        tool_category=tool_category or "general",
        status=status or "success",
        parameters_json=parameters_json,
        started_at=started_at,
        finished_at=finished_at,
        runtime_seconds=runtime_seconds,
        message=message,
        errors_json=errors_json,
        warnings_json=warnings_json,
        output_files_json=output_files_json,
        resource_usage_json=resource_usage_json,
        retry_count=retry_count or 0,
        recovery_attempts_json=recovery_attempts_json,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_tool_executions_by_session(db, session_id: str, limit: int = 100):
    """
    按会话查询工具有执行记录，最新在前。
    """
    from app.db.models import ToolExecution

    return (
        db.query(ToolExecution)
        .filter(ToolExecution.session_id == session_id)
        .order_by(ToolExecution.id.desc())
        .limit(limit)
        .all()
    )


def get_tool_execution_by_job_id(db, job_id: str):
    """
    按 job_id 查询单条执行记录。
    """
    from app.db.models import ToolExecution

    return (
        db.query(ToolExecution)
        .filter(ToolExecution.job_id == job_id)
        .first()
    )


def delete_tool_executions_by_session(db, session_id: str):
    """
    删除某个会话下的所有工具有执行记录。
    """
    from app.db.models import ToolExecution

    count = (
        db.query(ToolExecution)
        .filter(ToolExecution.session_id == session_id)
        .delete(synchronize_session=False)
    )
    return count