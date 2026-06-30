from typing import List
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.file_service import (
    save_upload_files,
    list_uploaded_files,
    delete_uploaded_file
)

router = APIRouter()

@router.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    session_id: str = Form("default"),
    db: Session = Depends(get_db)
):
    if not files:
        raise HTTPException(status_code=400, detail="未检测到上传文件")

    return save_upload_files(db, files, session_id=session_id)

@router.get("/api/uploads/{session_id}")
async def get_uploaded_files(session_id: str):
    return list_uploaded_files(session_id=session_id)

@router.delete("/api/uploads/{session_id}/{filename}")
async def remove_uploaded_file(session_id: str, filename: str):
    result = delete_uploaded_file(session_id=session_id, filename=filename)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result