import os
import shutil
from pathlib import Path
from app.core.paths import UPLOAD_DIR
from app.db import crud
from app.utils.file_utils import detect_file_type


def _safe_session_dir(session_id: str) -> Path:
    safe_session_id = os.path.basename(str(session_id)).strip() or "default"
    session_dir = Path(UPLOAD_DIR) / safe_session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _unique_filename(session_dir: Path, filename: str) -> str:
    base_name = os.path.basename(filename)
    stem, ext = os.path.splitext(base_name)
    candidate = base_name
    idx = 1

    while (session_dir / candidate).exists():
        candidate = f"{stem}_{idx}{ext}"
        idx += 1

    return candidate


def save_upload_file(db, file, session_id: str = "default"):
    """
    保存单个上传文件到 uploads/<session_id>/ 目录，并写数据库记录
    """
    session_dir = _safe_session_dir(session_id)

    filename = _unique_filename(session_dir, file.filename)
    save_path = session_dir / filename

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_type = detect_file_type(filename)

    crud.create_session(db, session_id=session_id)
    crud.save_file_record(
        db=db,
        session_id=session_id,
        filename=filename,
        relative_path=f"uploads/{session_id}/{filename}",
        file_type=file_type,
        source_type="upload"
    )

    return {
        "message": "上传成功",
        "filename": filename,
        "relative_path": f"uploads/{session_id}/{filename}",
        "url": f"http://127.0.0.1:8000/files/uploads/{session_id}/{filename}",
        "type": file_type
    }


def save_upload_files(db, files, session_id: str = "default"):
    """
    批量上传文件
    """
    results = []
    for file in files:
        results.append(save_upload_file(db, file, session_id=session_id))
    return {
        "message": "批量上传成功",
        "files": results
    }


def list_uploaded_files(session_id: str = "default"):
    """
    列出当前 session 已上传文件
    """
    session_dir = _safe_session_dir(session_id)
    files = []

    for p in sorted(session_dir.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file():
            file_type = detect_file_type(p.name)
            files.append({
                "filename": p.name,
                "relative_path": f"uploads/{session_id}/{p.name}",
                "url": f"http://127.0.0.1:8000/files/uploads/{session_id}/{p.name}",
                "type": file_type,
                "size_bytes": p.stat().st_size
            })

    return {
        "session_id": session_id,
        "files": files
    }


def delete_uploaded_file(session_id: str, filename: str):
    """
    删除某个上传文件
    """
    safe_filename = os.path.basename(filename)
    session_dir = _safe_session_dir(session_id)
    target = session_dir / safe_filename

    if not target.exists() or not target.is_file():
        return {
            "status": "error",
            "message": f"文件不存在: {safe_filename}"
        }

    target.unlink()

    return {
        "status": "success",
        "message": "文件删除成功",
        "filename": safe_filename
    }