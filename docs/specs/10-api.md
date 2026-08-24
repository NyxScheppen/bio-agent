# API 层 + 组合根（FastAPI + SSE）

> 范围：`backend/bioagent/main.py`（组合根 `create_app()` + lifespan）、`backend/bioagent/api.py`（`APIRouter` + Pydantic 模型 + task CRUD）。
> 把 09 的图、03 的 db、04 的 LlmClient、05 的 registry、06 的 RRunner 全接起来：启动时装配依赖，暴露 chat（SSE 流式）/ tasks（任务历史）/ uploads（文件上传）/ tools（工具清单）五个端点。
> 纯接线 spec：不含任何分析逻辑（那是 11-15）、不含图结构（那是 09）、不含前端（那是 16）。
> `Config` 取自 02-config、`connect`/`Database` 取自 03-db、`LlmClient` 取自 04-llm、`ToolRegistry` 取自 05-tools、`RRunner` 取自 06-r-runner、`Embedder`/`RagClient` 取自 07-rag、`build_graph` 取自 09-orchestration、`TaskStatus` 取自 01-types。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：01-types（`TaskStatus`）、02-config（`Config`/`load_config`）、03-db（`connect`/`Database`）、04-llm（`LlmClient`）、05-tools（`ToolRegistry`）、06-r-runner（`RRunner`）、07-rag（`Embedder`/`RagClient`）、09-orchestration（`build_graph`）
- **无循环依赖**：10 是装配终点，只依赖先编号的模块，无任何模块反向依赖它。

## 用户故事

> 作为 bio agent 系统的使用者，我想要 `uvicorn bioagent.main:app` 一条命令起服务，前端能发起一次会话（边跑边看到线性步骤与结果流式推进）、翻看任务历史、上传数据文件、拉取工具清单，以便把 11-15 的生物工具通过前端用起来。

## 验收标准

- [ ] `main.py` 含 `create_app()`（+ 模块级 `app`）与 lifespan，与「`backend/bioagent/main.py`（完整）」段逐字一致
- [ ] `api.py` 含 `router` + `ChatRequest`/`TaskSummary`/`TaskDetail` + task CRUD，与「`backend/bioagent/api.py`（完整）」段逐字一致
- [ ] lifespan 装配：`load_config` → `connect(db_path)` → `LlmClient.from_config(cfg.llm, db)` → `ToolRegistry.discover()` → `RRunner` → `Embedder`+`RagClient`+`ensure_collection()` → `build_graph`，全挂到 `app.state`；退出关 `rag` 与 `db.conn`
- [ ] `POST /chat` 建 task → 流式返回 `text/event-stream`：每节点后一条全量 state、结束 `{"done": true}`、失败 `{"error": ...}`，并把 task 置 `COMPLETED`/`FAILED`（失败时 `error` 落库）
- [ ] `GET /tasks` 按 `created_at` 倒序列任务摘要；`GET /tasks/{id}` 返回完整 plan/steps/report（404 无则）
- [ ] `POST /uploads` 落盘到 `upload_dir`（uuid 重命名）+ 写 `upload` 表，返回 `{file_id, original_name, size}`
- [ ] `GET /tools` 返回 registry 全量工具元数据（name/description/category/runtime/input_schema/frontend）
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`backend/bioagent/main.py`、`backend/bioagent/api.py`（无 Facade；这是系统的 API 出口）
- **库**：`fastapi` + `uvicorn`；`pydantic`（请求/响应模型，`>=2.0` 与 04-llm 一致）
- **公开面**：`from bioagent.main import create_app`；`from bioagent.api import router`（不加 `__all__`）

### 关键决策（实现者务必读，改动前先问）

1. **task CRUD 归属 10-api（03-db 映射已对齐为「api（10，读写）| task」）**：09 是纯图（不写 task，只经 `evaluate_*` 写 `eval_report`；`token_usage` 由 04-llm 写）。task 的写发生在**图的调用方**（10-api，因为只有它知道「一次会话 = 一个 task」）。故 task 的 create/status/complete/fail 落在 `api.py`，09 不碰 task 表。
2. **RAG 两处接地（lifespan 构造 + 注入图）**：RAG 在 planner + reporter 两处接地（09-orchestration 决策 8）。10-api 在 lifespan 用 `config.embedding.model` 建 `Embedder`、用 `config.rag.*` 建 `RagClient`，`ensure_collection()` 后把 `rag` 传给 `build_graph`。首次启动下载 `all-MiniLM-L6-v2` 模型（较慢）；qdrant 未起时 `ensure_collection()`/检索按 09 决策 5 上抛（启动失败或任务 FAILED）。
3. **失败落 error 列**：task 表有 `error` 列（`str | None`，03-db 已加）。失败时 `fail_task` 把错误文本写进 `error`，同时走 SSE `error` 事件 + 服务端日志（`log.exception`）；`TaskDetail` 带 `error` 字段，任务历史能回看失败原因。
4. **task 一次性写**：MVP 只在结束/失败时写一次 plan/steps/report（非每节点增量写）；中途崩溃 task 停在 `RUNNING`。逐节点持久化是「未请求的灵活性」，不做。
5. **SSE 用 POST 流式 + 自定义 hook**：`POST /chat` 直接返回 `StreamingResponse(text/event-stream)`，前端用 `fetch` 读流（`hooks/useSSE.ts`，见 16）。**不用原生 `EventSource`**（它只支持 GET、不能带 POST body）。SSE 事件统一 `data: <json>\n\n`，无 `event:` 字段；前端按 payload 是否有 `done`/`error` 键判别事件类型。
6. **CORS 开发期放开**：`allow_origins=["*"]`（Vite 前端跨域）；上线收紧为白名单。
7. **上传整读内存**：`await file.read()` 全量读（MVP 小 CSV/TSV 够用）；表达矩阵变大换 `aiofiles` 分块写。`write_bytes` 是同步 I/O，会短暂阻塞 event loop，MVP 接受。
8. **`load_config` 延迟到 lifespan**：`create_app()` 不在 import 时读 `config.yaml`（放在 lifespan 里），测试可 `create_app(cfg)` 注入配置、或直接裸 `FastAPI` + `include_router(router)` + 手动填 `app.state` 测路由。

### `backend/bioagent/main.py`（完整）

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bioagent.api import router
from bioagent.config import Config, load_config
from bioagent.db import connect
from bioagent.llm.client import LlmClient
from bioagent.orchestration.graph import build_graph
from bioagent.r_runner import RRunner
from bioagent.rag import Embedder, RagClient
from bioagent.tools import ToolRegistry

log = logging.getLogger(__name__)


def create_app(config: Config | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = config or load_config()  # 延迟到启动时读，测试可注入
        db = await connect(cfg.db.db_path)
        client = LlmClient.from_config(cfg.llm, db)
        registry = ToolRegistry()
        registry.discover()
        runner = RRunner(cfg.storage.r_scripts_dir)
        embedder = Embedder(cfg.embedding.model)
        rag = RagClient(embedder, cfg.rag.qdrant_url, cfg.rag.collection, cfg.rag.top_k)
        await rag.ensure_collection()
        graph = build_graph(
            client, registry, runner, db,
            cfg.eval.judge_sample_rate, cfg.storage.upload_dir, rag,
        )
        app.state.cfg = cfg
        app.state.db = db
        app.state.registry = registry
        app.state.graph = graph
        log.info("bioagent ready: %d tools", len(registry))
        yield
        await rag.close()
        await db.conn.close()

    app = FastAPI(title="bioagent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # 开发期放开；上线收紧为白名单
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()  # 生产入口：uvicorn bioagent.main:app
```

### `backend/bioagent/api.py`（完整）

```python
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


async def set_task_status(db: Database, task_id: str, status: str) -> None:
    async with db.lock:
        await db.conn.execute(
            "UPDATE task SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), task_id),
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
        await set_task_status(state.db, task_id, TaskStatus.RUNNING.value)
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
    file_id = str(uuid.uuid4())
    upload_dir = Path(state.cfg.storage.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / file_id
    content = await file.read()  # 整读内存：MVP 小文件够用（见决策 7）
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
```

**依赖 pin（实现时锁）**：`fastapi` / `uvicorn` / `pydantic`（`>=2.0`）/ `python-multipart`（`UploadFile` 表单解析依赖）锁精确版本。`graph.astream(..., stream_mode="values")` 的 chunk 类型、`request.app.state` 的动态属性访问均以锁定版本为准；若 pyright 对 `request.app.state.db` 报 `Unknown`，用 `cast`/局部变量收窄。

## 测试要点

- [ ] 单元测试 `tests/test_api/`（task CRUD，`pytest-asyncio` + `:memory:` 真实 aiosqlite）：
  - [ ] `create_task` → `task` 表一行，`status=="pending"`、`plan=="[]"`、`steps=="[]"`、`report==""`
  - [ ] `set_task_status` → `status` 更新、`updated_at` 变化
  - [ ] `complete_task` → `status=="completed"`、`plan`/`steps` 是 `json.dumps` 结果、`report` 落库
  - [ ] `fail_task` → `status=="failed"` 且 `error` 落库（= 传入的错误文本）
- [ ] 集成测试 `tests/test_api/`（`fastapi.testclient.TestClient` + 裸 `FastAPI` 挂 `router` + 手动填 `app.state`，**不跑 lifespan**）：
  - [ ] `POST /chat`（`app.state.graph` 换成 fake：`astream` 依次 yield 预设 state）→ `response.text` 是 `data:` 行流；断言含全量 state、末条 `{"done": true, "task_id": ...}`；task 表 `status=="completed"`
  - [ ] `POST /chat` 失败路径（fake `astream` 中途抛异常）→ 流末条含 `error`；task `status=="failed"` 且 `error` 列非空
  - [ ] `POST /chat` 空 message → 422（`min_length=1` 校验）
  - [ ] `GET /tasks` → 倒序摘要；`GET /tasks/{id}` → 完整 detail（`plan`/`steps` 已 `json.loads`）；`GET /tasks/nope` → 404
  - [ ] `POST /uploads`（`files=` 上传小文件）→ 返回 `file_id`；`upload_dir` 下出现 uuid 文件、内容一致；`upload` 表一行
  - [ ] `GET /tools`（`app.state.registry` 注册 2 个工具）→ 返回 2 条，含 name/category/runtime/input_schema/frontend
- [ ] E2E 测试：无（不触真实 LLM / 真实 R / 真实上传目录——集成测试用 `tmp_path` 当 `upload_dir`）

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] `uvicorn bioagent.main:app` 起来后：`POST /chat` 流式跑通一次会话、`GET /tasks` 看到历史、`GET /tools` 看到 11-15 的工具；11-15 的工具经 `discover()` 自动出现在 `/tools` 与 planner 的候选里
