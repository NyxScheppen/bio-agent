from typing import List
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.file_service import (
    save_upload_files,
    list_uploaded_files,
    delete_uploaded_file,
    UploadLimitError,
)
from app.utils.storage_contracts import StorageValidationError

router = APIRouter()

@router.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    session_id: str = Form("default"),
    db: Session = Depends(get_db)
):
    if not files:
        raise HTTPException(status_code=400, detail="未检测到上传文件")

    try:
        return await run_in_threadpool(save_upload_files, db, files, session_id)
    except UploadLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except StorageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/api/uploads/{session_id}")
async def get_uploaded_files(session_id: str):
    try:
        return list_uploaded_files(session_id=session_id)
    except StorageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.delete("/api/uploads/{session_id}/{filename}")
async def remove_uploaded_file(
    session_id: str,
    filename: str,
    db: Session = Depends(get_db),
):
    try:
        result = await run_in_threadpool(
            delete_uploaded_file, db, session_id, filename
        )
    except StorageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result
