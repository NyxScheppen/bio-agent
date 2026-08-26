import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bioagent.api import (
    complete_task,
    create_task,
    fail_task,
    router,
    set_task_status,
)
from bioagent.config import Config
from bioagent.db import Database, connect
from bioagent.enums import Category, Runtime, TaskStatus
from bioagent.tools import ToolRegistry
from bioagent.types import ToolDefinition


# ---- 工具 ----

@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    d = await connect(":memory:")
    yield d
    await d.conn.close()


async def _get_task(db: Database, task_id: str) -> Any:
    async with db.lock:
        cursor = await db.conn.execute("SELECT * FROM task WHERE id = ?", (task_id,))
        return await cursor.fetchone()


async def _dummy_run(**kwargs: Any) -> dict[str, Any]:
    return {}


def _tool(name: str, category: Category) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} desc",
        category=category,
        runtime=Runtime.PYTHON,
        input_schema={"type": "object", "properties": {"n": {"type": "integer"}}},
        output_schema={"type": "object"},
        run=_dummy_run,
        r_script=None,
        frontend={"result_type": "table"},
    )


class _FakeGraph:
    def __init__(self, states: list[dict[str, Any]], error: str | None = None) -> None:
        self._states = states
        self._error = error

    async def astream(
        self, initial: dict[str, Any], stream_mode: str = "values"
    ) -> AsyncIterator[dict[str, Any]]:
        for s in self._states:
            yield s
        if self._error is not None:
            raise RuntimeError(self._error)


def _make_app(db: Database, graph: Any, registry: ToolRegistry, cfg: Config) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.db = db
    app.state.graph = graph
    app.state.registry = registry
    app.state.cfg = cfg
    return app


def _cfg(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.storage.upload_dir = str(tmp_path)
    return cfg


def _sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.strip().split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: "):]))
    return events


# ---- task CRUD（单元） ----

async def test_create_task(db: Database) -> None:
    await create_task(db, "t-1", "hello")
    row = await _get_task(db, "t-1")
    assert row is not None
    assert row["user_message"] == "hello"
    assert row["status"] == "pending"
    assert row["plan"] == "[]"
    assert row["steps"] == "[]"
    assert row["report"] == ""


async def test_set_task_status(db: Database) -> None:
    await create_task(db, "t-2", "q")
    before = (await _get_task(db, "t-2"))["updated_at"]
    await set_task_status(db, "t-2", TaskStatus.RUNNING)
    row = await _get_task(db, "t-2")
    assert row["status"] == "running"
    assert row["updated_at"] >= before


async def test_complete_task(db: Database) -> None:
    await create_task(db, "t-3", "q")
    final: dict[str, Any] = {
        "plan": [{"tool": "a", "args": {}}],
        "steps": [{"tool": "a", "status": "completed", "result": {"x": 1}}],
        "report": "# 报告",
    }
    await complete_task(db, "t-3", final)
    row = await _get_task(db, "t-3")
    assert row["status"] == "completed"
    assert row["plan"] == json.dumps([{"tool": "a", "args": {}}])
    assert row["steps"] == json.dumps([{"tool": "a", "status": "completed", "result": {"x": 1}}])
    assert row["report"] == "# 报告"


async def test_fail_task(db: Database) -> None:
    await create_task(db, "t-4", "q")
    await fail_task(db, "t-4", "boom!")
    row = await _get_task(db, "t-4")
    assert row["status"] == "failed"
    assert row["error"] == "boom!"


# ---- 端点（集成，裸 FastAPI + 手动 app.state，不跑 lifespan） ----

async def test_chat_stream_success(db: Database, tmp_path: Path) -> None:
    full: dict[str, Any] = {
        "query": "哪些基因差异表达？",
        "correlation_id": "corr-x",
        "intent": "差异表达",
        "categories": ["dge"],
        "plan": [{"tool": "dge", "args": {"n": 3}}],
        "steps": [{"tool": "dge", "status": "completed", "result": {}}],
        "report": "# 报告",
    }
    app = _make_app(db, _FakeGraph([full]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "哪些基因差异表达？"})
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    assert events[-1]["done"] is True
    assert events[0]["report"] == "# 报告"
    row = await _get_task(db, events[-1]["task_id"])
    assert row is not None
    assert row["status"] == "completed"
    assert row["report"] == "# 报告"


async def test_chat_stream_failure(db: Database, tmp_path: Path) -> None:
    app = _make_app(db, _FakeGraph([], error="boom"), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hi"})
    events = _sse_events(resp.text)
    assert events[-1]["error"] == "boom"
    row = await _get_task(db, events[-1]["task_id"])
    assert row is not None
    assert row["status"] == "failed"
    assert row["error"] == "boom"


async def test_chat_empty_message_422(db: Database, tmp_path: Path) -> None:
    app = _make_app(db, _FakeGraph([]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422


async def test_list_tasks_desc(db: Database, tmp_path: Path) -> None:
    await create_task(db, "t-old", "old")
    await create_task(db, "t-new", "new")
    app = _make_app(db, _FakeGraph([]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    resp = client.get("/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert [d["id"] for d in data] == ["t-new", "t-old"]
    assert data[0]["user_message"] == "new"
    assert data[0]["status"] == "pending"


async def test_get_task_and_404(db: Database, tmp_path: Path) -> None:
    await create_task(db, "t-1", "q")
    await complete_task(db, "t-1", {"plan": [{"tool": "x", "args": {}}], "steps": [], "report": "# r"})
    app = _make_app(db, _FakeGraph([]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    resp = client.get("/tasks/t-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "t-1"
    assert data["plan"] == [{"tool": "x", "args": {}}]
    assert data["steps"] == []
    assert data["report"] == "# r"
    assert data["error"] is None
    assert client.get("/tasks/nope").status_code == 404


async def test_upload(db: Database, tmp_path: Path) -> None:
    app = _make_app(db, _FakeGraph([]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    content = b"a,b\n1,2\n"
    resp = client.post("/uploads", files={"file": ("data.csv", content, "text/csv")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_name"] == "data.csv"
    assert data["size"] == len(content)
    uploaded = list(tmp_path.iterdir())
    assert len(uploaded) == 1
    assert uploaded[0].read_bytes() == content
    async with db.lock:
        cursor = await db.conn.execute("SELECT * FROM upload WHERE id = ?", (data["file_id"],))
        row = await cursor.fetchone()
    assert row is not None
    assert row["original_name"] == "data.csv"


async def test_upload_rejects_bad_type(db: Database, tmp_path: Path) -> None:
    app = _make_app(db, _FakeGraph([]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    resp = client.post("/uploads", files={"file": ("data.xlsx", b"x", "application/octet-stream")})
    assert resp.status_code == 415


async def test_upload_rejects_oversize(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bioagent.api._MAX_UPLOAD_SIZE", 4)
    app = _make_app(db, _FakeGraph([]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)
    resp = client.post("/uploads", files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")})
    assert resp.status_code == 413


async def test_tools(db: Database, tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(_tool("dge_foo", Category.DGE))
    registry.register(_tool("km", Category.SURVIVAL))
    app = _make_app(db, _FakeGraph([]), registry, _cfg(tmp_path))
    client = TestClient(app)
    resp = client.get("/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert {t["name"] for t in data} == {"dge_foo", "km"}
    first = next(t for t in data if t["name"] == "dge_foo")
    assert first["category"] == "dge"
    assert first["runtime"] == "python"
    assert first["input_schema"] == {"type": "object", "properties": {"n": {"type": "integer"}}}
    assert first["frontend"] == {"result_type": "table"}
