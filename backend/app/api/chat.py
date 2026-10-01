from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.chat import ChatRequest
from app.db.database import get_db
from app.services.chat_service import handle_chat
from app.services.session_service import delete_session_with_files
from app.agent.context_manager import clear_session_memory

router = APIRouter()

@router.post("/api/chat")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        return await handle_chat(
            db=db,
            session_id=request.session_id,
            messages=request.messages,
            attached_files=[f.model_dump() for f in (request.attached_files or [])]
        )
    except Exception as e:
        print(f"🔥 聊天接口报错: {e}")
        safe_error = str(e).replace('"', "'").replace("\n", " ")
        return {
            "reply": f"❌ 服务器开小差了: {safe_error}",
            "files": []
        }

@router.delete("/api/chat/session/{session_id}")
def delete_chat_session_endpoint(session_id: str, db: Session = Depends(get_db)):
    try:
        result = delete_session_with_files(
            db=db,
            session_id=session_id,
            delete_uploads=True,
            delete_generated=True
        )

        delete_succeeded = isinstance(result, dict) and result.get("status") == "success"
        if delete_succeeded:
            clear_session_memory(session_id)

        if isinstance(result, dict):
            # Kept for response compatibility. Physical deletion is exclusively
            # owned by the service, which has the database reference context.
            result["force_deleted_files"] = []
            result["session_memory_cleared"] = delete_succeeded
            return result

        return {
            "status": "success",
            "result": result,
            "force_deleted_files": [],
            "session_memory_cleared": True
        }
    except Exception as e:
        print(f"🔥 删除会话接口报错: {e}")

        return {
            "status": "error",
            "message": f"删除会话失败：{str(e)}",
            "force_deleted_files": [],
            "session_memory_cleared": False,
        }
