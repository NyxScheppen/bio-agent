from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.crud import get_session_messages, get_session_files, get_all_sessions

router = APIRouter()

@router.get("/api/history")
async def list_history(db: Session = Depends(get_db)):
    """
    获取所有会话列表
    """
    sessions = get_all_sessions(db)

    return [
        {
            "session_id": session.session_id,
            "title": session.title,
            "created_at": str(session.created_at),
            "message_count": message_count,
            "file_count": file_count
        }
        for session, message_count, file_count in sessions
    ]

@router.get("/api/history/{session_id}")
async def get_history(session_id: str, db: Session = Depends(get_db)):
    """
    获取某个会话的历史消息和文件
    """
    messages = get_session_messages(db, session_id)
    files = get_session_files(db, session_id)

    return {
        "session_id": session_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": str(m.created_at)
            }
            for m in messages
        ],
        "files": [
            {
                "filename": f.filename,
                "relative_path": f.relative_path,
                "file_type": f.file_type,
                "source_type": f.source_type,
                "created_at": str(f.created_at)
            }
            for f in files
        ]
    }