from pathlib import Path
import shutil

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.chat import ChatRequest
from app.db.database import get_db
from app.services.chat_service import handle_chat
from app.services.session_service import delete_session_with_files
from app.agent.context_manager import clear_session_memory
from app.core.runtime_paths import BACKEND_ROOT, STORAGE_DIR, UPLOAD_DIR, GENERATED_DIR

router = APIRouter()

def _safe_session_id(session_id: str) -> str:
    if not session_id:
        return ""

    session_id = str(session_id).strip()

    if not session_id:
        return ""

    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return ""

    return session_id

def _safe_remove_tree(path: Path) -> dict:
    try:
        path = Path(path)

        if not path.exists():
            return {
                "path": str(path),
                "deleted": False,
                "reason": "not_exists"
            }

        if path.is_file():
            path.unlink()
            return {
                "path": str(path),
                "deleted": True,
                "reason": "file_deleted"
            }

        if path.is_dir():
            shutil.rmtree(path)
            return {
                "path": str(path),
                "deleted": True,
                "reason": "directory_deleted"
            }

        return {
            "path": str(path),
            "deleted": False,
            "reason": "unknown_path_type"
        }
    except Exception as e:
        return {
            "path": str(path),
            "deleted": False,
            "reason": str(e)
        }

def _force_delete_session_files(session_id: str) -> list:
    safe_id = _safe_session_id(session_id)
    if not safe_id:
        return [{
            "path": "",
            "deleted": False,
            "reason": "invalid_session_id"
        }]

    legacy_upload_dir = BACKEND_ROOT / "uploads" / safe_id
    legacy_generated_dir = BACKEND_ROOT / "generated" / safe_id

    candidate_dirs = [
        UPLOAD_DIR / safe_id,
        GENERATED_DIR / safe_id,
        STORAGE_DIR / "uploads" / safe_id,
        STORAGE_DIR / "generated" / safe_id,
        legacy_upload_dir,
        legacy_generated_dir,
    ]

    seen = set()
    results = []

    for path in candidate_dirs:
        normalized = str(Path(path).resolve())

        if normalized in seen:
            continue

        seen.add(normalized)
        results.append(_safe_remove_tree(path))

    return results

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

        clear_session_memory(session_id)

        force_deleted_files = _force_delete_session_files(session_id)

        if isinstance(result, dict):
            result["force_deleted_files"] = force_deleted_files
            result["session_memory_cleared"] = True
            return result

        return {
            "status": "success",
            "result": result,
            "force_deleted_files": force_deleted_files,
            "session_memory_cleared": True
        }
    except Exception as e:
        print(f"🔥 删除会话接口报错: {e}")

        clear_session_memory(session_id)
        force_deleted_files = _force_delete_session_files(session_id)

        return {
            "status": "error",
            "message": f"删除会话失败：{str(e)}",
            "force_deleted_files": force_deleted_files,
            "session_memory_cleared": True
        }