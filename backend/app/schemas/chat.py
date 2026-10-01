from pydantic import BaseModel
from typing import List, Dict, Optional

class AttachedFileItem(BaseModel):
    filename: str
    relative_path: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    size_bytes: Optional[int] = None

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    session_id: Optional[str] = "default"
    attached_files: Optional[List[AttachedFileItem]] = []