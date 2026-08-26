import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from bioagent.db import Database
from bioagent.enums import TaskStatus

log = logging.getLogger(__name__)

router = APIRouter()

_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB（how-security.md:16）
_ALLOWED_SUFFIXES = {".csv", ".tsv", ".txt"}


# ---- 请求 / 响应模型 ----
class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class TaskSummary(BaseModel):
    id: str
    user_message: str
    status: str
    created_at: float
    updated_at: float


class TaskDetail(TaskSummary):
    plan: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    report: str
    error: str | None


# ---- task CRUD（本 spec 拥有 task 表） ----
async def create_task(db: Database, task_id: str, message: str) -> None:
    now = time.time()
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO task (id, user_message, status, plan, steps, report, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, message, TaskStatus.PENDING.value, "[]", "[]", "", now, now),
        )
        await db.conn.commit()


async def set_task_status(db: Database, task_id: str, status: TaskStatus) -> None:
    async with db.lock:
        await db.conn.execute(
            "UPDATE task SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, time.time(), task_id),
        )
        await db.conn.commit()


async def complete_task(db: Database, task_id: str, final: dict[str, Any]) -> None:
    async with db.lock:
        await db.conn.execute(
            "UPDATE task SET status = ?, plan = ?, steps = ?, report = ?, updated_at = ? WHERE id = ?",
            (
                TaskStatus.COMPLETED.value,
                json.dumps(final.get("plan", [])),
                json.dumps(final.get("steps", [])),
                final.get("report", ""),
                time.time(),
                task_id,
            ),
        )
        await db.conn.commit()


async def fail_task(db: Database, task_id: str, error: str) -> None:
    async with db.lock:
        await db.conn.execute(
            "UPDATE task SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.FAILED.value, error, time.time(), task_id),
        )
        await db.conn.commit()


# ---- SSE helper ----
def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---- 端点 ----
@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    state = request.app.state
    task_id = str(uuid.uuid4())
    await create_task(state.db, task_id, req.message)  # 建 task 失败 = 正常 500

    async def stream():
        await set_task_status(state.db, task_id, TaskStatus.RUNNING)
        initial: dict[str, Any] = {"query": req.message, "correlation_id": task_id}
        final: dict[str, Any] = initial
        try:
            async for chunk in state.graph.astream(initial, stream_mode="values"):
                final = chunk
                yield _sse(chunk)
            await complete_task(state.db, task_id, final)
            yield _sse({"done": True, "task_id": task_id})
        except Exception as exc:
            log.exception("chat %s failed", task_id)
            await fail_task(state.db, task_id, str(exc))
            yield _sse({"error": str(exc), "task_id": task_id})

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/tasks", response_model=list[TaskSummary])
async def list_tasks(request: Request) -> list[TaskSummary]:
    db = request.app.state.db
    async with db.lock:
        cursor = await db.conn.execute(
            "SELECT id, user_message, status, created_at, updated_at "
            "FROM task ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
    return [
        TaskSummary(
            id=r["id"],
            user_message=r["user_message"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(task_id: str, request: Request) -> TaskDetail:
    db = request.app.state.db
    async with db.lock:
        cursor = await db.conn.execute("SELECT * FROM task WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskDetail(
        id=row["id"],
        user_message=row["user_message"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        plan=json.loads(row["plan"]),
        steps=json.loads(row["steps"]),
        report=row["report"],
        error=row["error"],
    )


@router.post("/uploads")
async def upload(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    state = request.app.state
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 CSV/TSV/TXT 文件")
    file_id = str(uuid.uuid4())
    upload_dir = Path(state.cfg.storage.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / file_id
    content = await file.read(_MAX_UPLOAD_SIZE + 1)  # 上限 +1 探测超限，防 OOM
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="文件超过 100MB 上限")
    path.write_bytes(content)
    now = time.time()
    async with state.db.lock:
        await state.db.conn.execute(
            "INSERT INTO upload (id, original_name, path, size, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_id, file.filename or "", str(path), len(content), now),
        )
        await state.db.conn.commit()
    return {"file_id": file_id, "original_name": file.filename or "", "size": len(content)}


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.registry
    return [
        {
            "name": t.name,
            "description": t.description,
            "category": t.category.value,
            "runtime": t.runtime.value,
            "input_schema": t.input_schema,
            "frontend": t.frontend,
        }
        for t in registry.all_tools()
    ]
