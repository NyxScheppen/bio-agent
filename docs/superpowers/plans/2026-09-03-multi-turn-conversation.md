# 多轮对话上下文（Multi-turn Conversation）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 agent 记住同一对话内的历史轮次，把之前轮次的 user/assistant 消息作为上下文喂给 router/planner/reporter，实现可回溯的多轮对话。

**Architecture:** 引入 `conversation_id`（对话 id，区别于每次运行的 `task_id`）。后端新增 `message` 表持久化每轮成功后的 Q&A；`/chat` 请求携带可选 `conversation_id`，加载历史注入 `AgentState.history`，各节点把 history 拼到 LLM 消息列表末尾。前端 `chatStore` 维护 `conversationId` 并在每条消息后把助手报告追加进 `messages`，使对话面板按 `messages` 渲染完整多轮对话。

**Tech Stack:** Python 3.11 + aiosqlite（迁移）+ LangGraph 状态；React 19 + Zustand + react-markdown/remark-gfm。

**Spec:** `docs/design/2026-08-22-synthbio-agent-design.md`（权威架构）。本计划扩展以下 spec：`docs/specs/03-db.md`（message 表）、`docs/specs/09-orchestration.md`（state/nodes）、`docs/specs/10-api.md`（/chat 端点）、`docs/specs/16-frontend.md`（对话面板）。当前尚无 17-multi-turn spec，本计划即新 spec 的落地来源；如需 spec-driven，可据本计划反向补 `docs/specs/17-multi-turn.md`。

## Global Constraints

- Python 3.11+，严格类型注解（所有函数签名完整标注）。
- LLM 调用统一走 `LlmClient`（LangChain 封装），不直接 httpx。
- 数据库访问统一走 `Database`（`conn` + `lock`），每条写后 `commit`。
- 迁移走 `schema_version` 版本门控，每版本一个事务（原子）。
- 工具/编排分层不动：本计划只改 API 层、DB、编排 state/nodes，不改 router→planner→executor→reporter 拓扑。
- 前端 TypeScript `strict: true`；Zustand 一个系统一个 store（对话系统 = `chatStore`）。
- 每个工具 `run()` 测试 ≤ 5 断言；纯逻辑测全；测试不依赖真实 LLM/R/文件系统。
- 每次写测试后更新 `docs/test-inventory.md`（CLAUDE.md Part 4）。

---

## File Structure

**后端：**
- Modify `backend/bioagent/db.py` — 迁移 v2 加 `message` 表 + 索引。
- Modify `backend/bioagent/api.py` — `append_message` / `list_messages` 助手；`ChatRequest` 加 `conversation_id`；`/chat` 接线。
- Modify `backend/bioagent/orchestration/state.py` — `AgentState` 加 `conversation_id`、`history`。
- Modify `backend/bioagent/orchestration/nodes.py` — `_with_history` 助手 + router/planner/reporter 注入。
- Modify `backend/tests/test_db/test_db.py`、`backend/tests/test_api/test_api.py`、`backend/tests/test_orchestration/test_orchestration.py`。

**前端：**
- Modify `frontend/src/stores/chatStore.ts` — `conversationId` + assistant 消息追加 + `reset`。
- Modify `frontend/src/components/ChatPanel.tsx` — 去掉 `report`/`textSteps` props，从 `messages` 渲染。
- Modify `frontend/src/App.tsx` — 传参调整 + 「新对话」按钮。
- Modify `frontend/src/stores/taskStore.ts` — 回看回填 `messages`。
- Modify `frontend/src/stores/chatStore.test.ts`、`frontend/src/stores/taskStore.test.ts`、`frontend/src/components/ChatPanel.test.tsx`。

---

### Task 1: DB 迁移 v2 —— `message` 表

**Files:**
- Modify: `backend/bioagent/db.py:20-66`
- Test: `backend/tests/test_db/test_db.py:56-84`

**Interfaces:**
- Consumes: 无（第一个任务）。
- Produces: 表 `message(id INTEGER PK AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL)` + 索引 `idx_message_conversation(conversation_id, created_at)`；`schema_version` 最高版本变为 2。

- [ ] **Step 1: 写失败测试**

改 `test_migrate_creates_all_tables_and_indexes` 的期望集合：

```python
async def test_migrate_creates_all_tables_and_indexes(conn: aiosqlite.Connection) -> None:
    await db.migrate(conn)
    assert await _table_names(conn) == {
        "task", "upload", "eval_report", "token_usage", "message", "schema_version",
    }
    assert await _index_names(conn) == {
        "idx_task_created_at", "idx_token_usage_corr", "idx_message_conversation",
    }
    assert await _version(conn) == max(v for v, _ in _MIGRATIONS)
```

改 `test_migrate_idempotent` 的表计数：

```python
    assert len(await _table_names(conn)) == 6
```

新增列约束测试：

```python
async def test_migrate_message_table_columns(conn: aiosqlite.Connection) -> None:
    await db.migrate(conn)
    assert "message" in await _table_names(conn)
    assert await _notnull(conn, "message", "conversation_id") == 1
    assert await _notnull(conn, "message", "role") == 1
    assert await _notnull(conn, "message", "content") == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_db/test_db.py -v`
Expected: `test_migrate_creates_all_tables_and_indexes` / `test_migrate_idempotent` FAIL（实际表集合缺 `message`）；`test_migrate_message_table_columns` FAIL（`message` 不存在）。

- [ ] **Step 3: 写最小实现**

在 `_MIGRATIONS` 里，`(1, (...))` 之后、收尾 `)` 之前追加 v2：

```python
    (
        2,
        (
            """CREATE TABLE message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,  -- 对话 id（uuid4）
                role TEXT NOT NULL,             -- "user" | "assistant"
                content TEXT NOT NULL,          -- user 原话 / assistant markdown 报告
                created_at REAL NOT NULL
            )""",
            "CREATE INDEX idx_message_conversation ON message(conversation_id, created_at)",
        ),
    ),
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_db/test_db.py -v`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/bioagent/db.py backend/tests/test_db/test_db.py
git commit -m "feat(db): add message table for multi-turn context"
```

提交时按 CLAUDE.md Part 4 在 `docs/test-inventory.md` 追加：新增 `test_migrate_message_table_columns`（功能正确 / 边界鲁棒，db 系统，多轮上下文阶段）。

---

### Task 2: message 持久化助手（api.py）

**Files:**
- Modify: `backend/bioagent/api.py:43-87`（在 task CRUD 之后新增两个函数）
- Test: `backend/tests/test_api/test_api.py`（imports + 新增测试）

**Interfaces:**
- Consumes: Task 1 的 `message` 表结构。
- Produces: `async def append_message(db: Database, conversation_id: str, role: str, content: str) -> None`；`async def list_messages(db: Database, conversation_id: str) -> list[dict[str, str]]`（按 `created_at ASC, id ASC` 排序，元素形如 `{"role": "user"|"assistant", "content": str}`）。

- [ ] **Step 1: 写失败测试**

在 `test_api.py` 顶部 import 增加两个名字，并新增测试：

```python
from bioagent.api import (
    append_message,
    complete_task,
    create_task,
    fail_task,
    list_messages,
    router,
    set_task_status,
)
```

```python
async def test_append_and_list_messages(db: Database) -> None:
    await append_message(db, "conv-1", "user", "hello")
    await append_message(db, "conv-1", "assistant", "# report")
    await append_message(db, "conv-2", "user", "other")

    msgs = await list_messages(db, "conv-1")
    assert msgs == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "# report"},
    ]
    assert await list_messages(db, "conv-3") == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_api/test_api.py::test_append_and_list_messages -v`
Expected: FAIL（`ImportError: cannot import name 'append_message'`）。

- [ ] **Step 3: 写最小实现**

在 `api.py` 的 `fail_task` 之后、`# ---- SSE helper ----` 之前新增：

```python
async def append_message(db: Database, conversation_id: str, role: str, content: str) -> None:
    """持久化一轮对话消息（user/assistant）；供 /chat 成功落库 + 后续轮次加载历史。"""
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO message (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, time.time()),
        )
        await db.conn.commit()


async def list_messages(db: Database, conversation_id: str) -> list[dict[str, str]]:
    """按时间升序取某对话的全部历史消息，供 /chat 注入 AgentState.history。"""
    async with db.lock:
        cursor = await db.conn.execute(
            "SELECT role, content FROM message WHERE conversation_id = ? ORDER BY created_at ASC, id ASC",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_api/test_api.py::test_append_and_list_messages -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/bioagent/api.py backend/tests/test_api/test_api.py
git commit -m "feat(api): add message append/list helpers for conversation history"
```

提交时在 `docs/test-inventory.md` 追加：`test_append_and_list_messages`（功能正确，api 系统，多轮上下文阶段）。

---

### Task 3: AgentState + nodes 注入 history

**Files:**
- Modify: `backend/bioagent/orchestration/state.py:4-17`
- Modify: `backend/bioagent/orchestration/nodes.py:1-24, 76-88, 106-117, 169-187`
- Test: `backend/tests/test_orchestration/test_orchestration.py`

**Interfaces:**
- Consumes: 无（Task 2 的产物在 api 层用，本任务不依赖）。
- Produces: `AgentState` 新增键 `conversation_id: str`、`history: list[dict[str, str]]`（元素 `{"role": "user"|"assistant", "content": str}`，不含当前 query）；`nodes.py` 新增私有 `_with_history(prompt: str, state: AgentState) -> list[LlmMessage]`。

- [ ] **Step 1: 写失败测试**

在 `test_orchestration.py` 新增（复用已有 `_FakeClient`/`_output`）：

```python
async def test_router_node_includes_history() -> None:
    output = _output('{"intent": "差异表达分析", "categories": ["dge"]}', module="router", output_type="intent")
    fake = _FakeClient({"router": output})
    node = make_router_node(cast(LlmClient, fake))
    state: AgentState = {
        "query": "把显著性阈值改成 0.01 再跑一次",
        "correlation_id": "corr-1",
        "history": [
            {"role": "user", "content": "做 DGE 分析"},
            {"role": "assistant", "content": "# DGE 报告"},
        ],
    }
    await node(state)
    messages = fake.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "做 DGE 分析"}
    assert messages[2] == {"role": "assistant", "content": "# DGE 报告"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_orchestration/test_orchestration.py::test_router_node_includes_history -v`
Expected: FAIL（`len(messages) == 1`，`messages[1]` 越界 IndexError）。

- [ ] **Step 3: 写最小实现**

`state.py` 加两个键（在 `report` 之后）：

```python
    conversation_id: str        # 对话 id（10-api 生成/透传，多轮上下文）
    history: list[dict[str, str]]  # 之前轮次 [{role, content}]，role ∈ {user, assistant}；不含当前 query
```

`nodes.py`：import 加 `cast`，加助手，三处调用改写。

```python
from typing import Any, cast
```

```python
def _with_history(prompt: str, state: AgentState) -> list[LlmMessage]:
    """系统 prompt + 之前轮次上下文（user/assistant 交替）；当前 query 已含在 prompt 内。"""
    history: list[LlmMessage] = []
    for m in state.get("history", []):
        role = m.get("role")
        if role in ("user", "assistant"):
            history.append(cast(LlmMessage, {"role": role, "content": m["content"]}))
    return [_system(prompt)] + history
```

router：

```python
        output = await client.complete(
            _with_history(_ROUTER_PROMPT.format(query=state["query"], allowed=json.dumps(allowed)), state),
            module="router",
```

planner：

```python
        output = await client.complete(
            _with_history(_PLANNER_PROMPT.format(
                query=state["query"],
                intent=state["intent"],
                tools=json.dumps(tool_descs, ensure_ascii=False),
                knowledge=_format_docs(docs),
            ), state),
            module="planner",
```

reporter：

```python
        output = await client.complete(
            _with_history(_REPORTER_PROMPT.format(
                query=state["query"],
                plan=json.dumps(state["plan"], ensure_ascii=False),
                steps=json.dumps(state["steps"], ensure_ascii=False),
                knowledge=_format_docs(docs),
            ), state),
            module="reporter",
```

（其余参数 `output_type` / `correlation_id` / `json_mode` 保持不变。）

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_orchestration/test_orchestration.py -v`
Expected: 全 PASS（含既有 `test_router_node`/`test_planner_node_*`/`test_reporter_node`，因为 `state.get("history", [])` 为空时消息列表仍是单条 system）。

- [ ] **Step 5: 提交**

```bash
git add backend/bioagent/orchestration/state.py backend/bioagent/orchestration/nodes.py backend/tests/test_orchestration/test_orchestration.py
git commit -m "feat(orchestration): inject conversation history into router/planner/reporter"
```

提交时在 `docs/test-inventory.md` 追加：`test_router_node_includes_history`（功能正确，orchestration 系统，多轮上下文阶段）。

---

### Task 4: `/chat` 端点接线（conversation_id + history + 落库）

**Files:**
- Modify: `backend/bioagent/api.py:24-26, 94-116`
- Test: `backend/tests/test_api/test_api.py`

**Interfaces:**
- Consumes: Task 2 的 `append_message`/`list_messages`；Task 3 的 `AgentState.history`/`conversation_id`。
- Produces: `ChatRequest` 新增 `conversation_id: str | None = None`；`/chat` 成功后 SSE 结束帧新增 `conversation_id` 字段；成功轮次落 `message` 表（user + assistant）。

- [ ] **Step 1: 写失败测试**

在 `test_api.py` 新增两个测试：

```python
class _CapturingGraph(_FakeGraph):
    def __init__(self, states: list[dict[str, Any]]) -> None:
        super().__init__(states)
        self.initial: dict[str, Any] = {}

    async def astream(self, initial: dict[str, Any], stream_mode: str = "values") -> AsyncIterator[dict[str, Any]]:
        self.initial = initial
        async for s in self._states:
            yield s


async def test_chat_persists_conversation_and_injects_history(db: Database, tmp_path: Path) -> None:
    await append_message(db, "conv-9", "user", "做 DGE")
    await append_message(db, "conv-9", "assistant", "# 上轮报告")
    full = {"query": "改阈值", "correlation_id": "corr-x", "report": "# r"}
    graph = _CapturingGraph([full])
    app = _make_app(db, graph, ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)

    resp = client.post("/chat", json={"message": "改阈值", "conversation_id": "conv-9"})
    events = _sse_events(resp.text)

    assert resp.status_code == 200
    assert events[-1]["done"] is True
    assert events[-1]["conversation_id"] == "conv-9"
    assert graph.initial["history"] == [
        {"role": "user", "content": "做 DGE"},
        {"role": "assistant", "content": "# 上轮报告"},
    ]
    assert await list_messages(db, "conv-9") == [
        {"role": "user", "content": "做 DGE"},
        {"role": "assistant", "content": "# 上轮报告"},
        {"role": "user", "content": "改阈值"},
        {"role": "assistant", "content": "# r"},
    ]


async def test_chat_generates_new_conversation_when_absent(db: Database, tmp_path: Path) -> None:
    full = {"query": "q", "correlation_id": "c", "report": "# r"}
    app = _make_app(db, _FakeGraph([full]), ToolRegistry(), _cfg(tmp_path))
    client = TestClient(app)

    resp = client.post("/chat", json={"message": "q"})
    events = _sse_events(resp.text)

    assert resp.status_code == 200
    conv_id = events[-1]["conversation_id"]
    assert conv_id  # 非空
    assert await list_messages(db, conv_id) == [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "# r"},
    ]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_api/test_api.py::test_chat_persists_conversation_and_injects_history backend/tests/test_api/test_api.py::test_chat_generates_new_conversation_when_absent -v`
Expected: FAIL（结束帧无 `conversation_id`；`graph.initial` 无 `history`；`list_messages` 返回空）。

- [ ] **Step 3: 写最小实现**

`ChatRequest` 加字段：

```python
class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None  # 多轮：续接某对话；缺省新建一个
```

`/chat` 端点改写：

```python
@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    state = request.app.state
    task_id = str(uuid.uuid4())
    conversation_id = req.conversation_id or str(uuid.uuid4())
    history = await list_messages(state.db, conversation_id)  # 之前轮次（不含当前 query）
    await create_task(state.db, task_id, req.message)  # 建 task 失败 = 正常 500

    async def stream():
        await set_task_status(state.db, task_id, TaskStatus.RUNNING)
        initial: dict[str, Any] = {
            "query": req.message,
            "correlation_id": task_id,
            "conversation_id": conversation_id,
            "history": history,
        }
        final: dict[str, Any] = initial
        try:
            async for chunk in state.graph.astream(initial, stream_mode="values"):
                final = chunk
                yield _sse(chunk)
            await complete_task(state.db, task_id, final)
            # 多轮：成功轮次的 Q&A 落 message 表，供后续轮次作为上下文
            await append_message(state.db, conversation_id, "user", req.message)
            await append_message(state.db, conversation_id, "assistant", final.get("report", ""))
            yield _sse({"done": True, "task_id": task_id, "conversation_id": conversation_id})
        except Exception as exc:
            log.exception("chat %s failed", task_id)
            await fail_task(state.db, task_id, str(exc))
            yield _sse({"error": str(exc), "task_id": task_id})

    return StreamingResponse(stream(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/test_api/test_api.py -v`
Expected: 全 PASS（含既有 `test_chat_stream_success`/`test_chat_stream_failure`/`test_chat_empty_message_422`）。

- [ ] **Step 5: 提交**

```bash
git add backend/bioagent/api.py backend/tests/test_api/test_api.py
git commit -m "feat(api): wire conversation_id + history into /chat"
```

提交时在 `docs/test-inventory.md` 追加：`test_chat_persists_conversation_and_injects_history`、`test_chat_generates_new_conversation_when_absent`（功能正确 / 边界鲁棒，api 系统，多轮上下文阶段）。

---

### Task 5: chatStore —— conversationId + assistant 消息 + reset

**Files:**
- Modify: `frontend/src/stores/chatStore.ts`
- Test: `frontend/src/stores/chatStore.test.ts`

**Interfaces:**
- Consumes: Task 4 的 `/chat` 请求体 `{message, conversation_id}` 与结束帧 `{done, task_id, conversation_id}`。
- Produces: `ChatState` 新增 `conversationId: string`、`reset: () => void`；`send` 完成后把助手报告追加进 `messages`（`{role:'assistant', content: report}`）。

- [ ] **Step 1: 写失败测试**

改 `chatStore.test.ts` 的第一个测试，并新增 reset 测试：

```ts
it('send 入消息、快照随帧更新、report 后追加 assistant 消息', async () => {
  const { body } = fakeStream([
    'data: {"query":"hi"}\n\n',
    'data: {"query":"hi","plan":[{"tool":"dge","args":{}}]}\n\n',
    'data: {"query":"hi","plan":[{"tool":"dge","args":{}}],"report":"# r"}\n\n',
    'data: {"done":true}\n\n',
  ])
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, body })
  vi.stubGlobal('fetch', fetchMock)

  await useChatStore.getState().send('hi')

  const s = useChatStore.getState()
  expect(s.messages).toEqual([
    { role: 'user', content: 'hi' },
    { role: 'assistant', content: '# r' },
  ])
  expect(s.currentState?.report).toBe('# r')
  expect(s.status).toBe('done')

  const [, init] = fetchMock.mock.calls[0]
  const parsed = JSON.parse(init.body as string)
  expect(parsed.message).toBe('hi')
  expect(typeof parsed.conversation_id).toBe('string')
})

it('reset 清空消息并生成新 conversationId', () => {
  useChatStore.setState({ messages: [{ role: 'user', content: 'a' }], conversationId: 'old' })
  useChatStore.getState().reset()
  const s = useChatStore.getState()
  expect(s.messages).toEqual([])
  expect(s.conversationId).not.toBe('old')
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npx vitest run src/stores/chatStore.test.ts`
Expected: FAIL（`conversationId` 不存在；`messages` 缺 assistant 项；`reset` 未定义）。

- [ ] **Step 3: 写最小实现**

```ts
import { create } from 'zustand'
import type { AgentState, Message } from '../types'
import { readSSE } from '../hooks/useSSE'

interface ChatState {
  messages: Message[]                 // 用户/助手消息（完整多轮对话）
  conversationId: string              // 对话 id，随消息发给后端
  currentState: AgentState | null     // 最新 SSE 快照（驱动 步骤/结果 面板）
  status: 'idle' | 'streaming' | 'done' | 'error'
  send: (message: string) => Promise<void>
  reset: () => void                   // 新对话：清空 + 新 conversationId
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  conversationId: crypto.randomUUID(),
  currentState: null,
  status: 'idle',

  send: async (message: string): Promise<void> => {
    set((s) => ({
      messages: [...s.messages, { role: 'user' as const, content: message }],
      status: 'streaming' as const,
      currentState: { query: message },
    }))
    try {
      const resp = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, conversation_id: get().conversationId }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('响应无 body')
      const reader = resp.body.getReader()
      let lastReport = ''
      await readSSE(reader, (snapshot) => {
        if (snapshot.report != null) lastReport = snapshot.report
        set({
          currentState: snapshot,
          status: snapshot.report != null ? ('done' as const) : ('streaming' as const),
        })
      })
      set((s) => ({
        status: 'done',
        messages: lastReport
          ? [...s.messages, { role: 'assistant' as const, content: lastReport }]
          : s.messages,
      }))
    } catch (err) {
      set({ status: 'error' })
      throw err
    }
  },

  reset: (): void =>
    set({ messages: [], conversationId: crypto.randomUUID(), currentState: null, status: 'idle' }),
}))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npx vitest run src/stores/chatStore.test.ts`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/stores/chatStore.ts frontend/src/stores/chatStore.test.ts
git commit -m "feat(chat): track conversationId and persist assistant replies"
```

提交时在 `docs/test-inventory.md` 追加：改写的 send 测试 + 新增 `reset` 测试（功能正确，chatStore 系统，多轮上下文阶段）。

---

### Task 6: ChatPanel / App —— 从 messages 渲染 + 新对话按钮

**Files:**
- Modify: `frontend/src/components/ChatPanel.tsx`
- Modify: `frontend/src/App.tsx:11-51`
- Test: `frontend/src/components/ChatPanel.test.tsx`

**Interfaces:**
- Consumes: Task 5 的 `messages`（含 assistant markdown）。
- Produces: `ChatPanel` 无 props（内部读 store）；App 移除 `textSteps`/`report` 传参，新增「新对话」按钮调用 `useChatStore.getState().reset()`。

- [ ] **Step 1: 写失败测试**

重写 `ChatPanel.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import ChatPanel from './ChatPanel'
import { useChatStore } from '../stores/chatStore'

describe('ChatPanel', () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [], conversationId: 'c', currentState: null, status: 'idle' })
  })

  it('助手 markdown 报告渲染在对话中', () => {
    useChatStore.setState({
      messages: [{ role: 'assistant', content: '# 分析报告\n\n[KEGG](https://kegg.jp)' }],
    })
    render(<ChatPanel />)
    expect(screen.getByRole('heading', { name: '分析报告' })).toBeInTheDocument()
    expect(screen.getByText('KEGG')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npx vitest run src/components/ChatPanel.test.tsx`
Expected: FAIL（`ChatPanel` 现要求 `report`/`textSteps` props；markdown 不再走 messages 渲染）。

- [ ] **Step 3: 写最小实现**

`ChatPanel.tsx` 整文件替换：

```tsx
import { useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '../stores/chatStore'

export default function ChatPanel() {
  const [input, setInput] = useState('')
  const messages = useChatStore((s) => s.messages)
  const status = useChatStore((s) => s.status)
  const send = useChatStore((s) => s.send)

  const onSubmit = (e: FormEvent): void => {
    e.preventDefault()
    const text = input.trim()
    if (!text || status === 'streaming') return
    setInput('')
    void send(text)
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-1 overflow-y-auto space-y-2 p-4 min-h-0">
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
            <div
              className={
                m.role === 'user'
                  ? 'inline-block rounded-lg px-3 py-2 bg-blue-600 text-white'
                  : 'inline-block max-w-full rounded-lg px-3 py-2 bg-gray-100 text-gray-900 text-sm markdown'
              }
            >
              {m.role === 'user' ? (
                m.content
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
              )}
            </div>
          </div>
        ))}
        {messages.length === 0 && <p className="text-sm text-gray-400">问点什么，比如：帮我做 DGE 分析</p>}
      </div>
      <form onSubmit={onSubmit} className="p-4 border-t">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入分析需求…"
          disabled={status === 'streaming'}
          className="w-full border rounded px-3 py-2 text-sm"
        />
      </form>
    </div>
  )
}
```

`App.tsx` 改动：去掉 `textSteps` 计算，`ChatPanel` 不传 props，对话头部加「新对话」按钮。

```tsx
  const plan = currentState?.plan ?? []
  const steps = currentState?.steps ?? []
  const failed = status === 'error'
  const chartSteps = steps.filter((s) => isChartStep(s, tools))
```

```tsx
      <div className="lg:col-span-1 border rounded-lg flex flex-col h-[80vh]">
        <div className="flex items-center justify-between p-4 pb-0">
          <h2 className="font-semibold">对话</h2>
          <button
            onClick={() => useChatStore.getState().reset()}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            新对话
          </button>
        </div>
        <ChatPanel />
      </div>
```

（`ExecutedStep`、`isChartStep`、`CHART_RESULT_TYPES`、`chartSteps` 保留，供「结果」面板使用；删除对 `textSteps` 的引用。）

- [ ] **Step 4: 运行测试确认通过 + 类型/ lint**

Run: `npx vitest run src/components/ChatPanel.test.tsx` 及 `npm run typecheck`、`npm run lint`
Expected: 全 PASS / 零报错。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/ChatPanel.tsx frontend/src/App.tsx frontend/src/components/ChatPanel.test.tsx
git commit -m "feat(chat): render conversation from messages, add new-chat reset"
```

提交时在 `docs/test-inventory.md` 追加：改写的 `ChatPanel` 测试（功能正确，ChatPanel 系统，多轮上下文阶段）。

---

### Task 7: taskStore.open 回看回填 messages

**Files:**
- Modify: `frontend/src/stores/taskStore.ts:30-38`
- Test: `frontend/src/stores/taskStore.test.ts`

**Interfaces:**
- Consumes: Task 5 的 `messages`（`Message[]`，含 `{role:'user'|'assistant', content}`）。
- Produces: `open(id)` 在回填 `currentState` 之外，把该任务 `userMessage` + `report` 追加进 `messages`，使回看报告继续显示在对话面板。

- [ ] **Step 1: 写失败测试**

改 `taskStore.test.ts` 的 `open 取回任务` 测试，追加 messages 断言：

```ts
  it('open 取回任务并把内容回填主视图与对话', async () => {
    vi.mocked(client.getTask).mockResolvedValue({
      id: 't1',
      userMessage: 'hi',
      status: 'completed',
      createdAt: 1,
      updatedAt: 2,
      plan: [{ tool: 'dge', args: {} }],
      steps: [{ tool: 'dge', status: 'completed', result: { x: 1 } }],
      report: '# r',
      error: null,
    })

    await useTaskStore.getState().open('t1')

    expect(useTaskStore.getState().current?.id).toBe('t1')
    const c = useChatStore.getState()
    expect(c.currentState?.report).toBe('# r')
    expect(c.currentState?.plan).toHaveLength(1)
    expect(c.messages).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: '# r' },
    ])
    expect(c.status).toBe('done')
  })
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npx vitest run src/stores/taskStore.test.ts`
Expected: FAIL（`c.messages` 仍为 `[]`）。

- [ ] **Step 3: 写最小实现**

`taskStore.ts` 的 `open`：

```ts
  open: async (id: string): Promise<void> => {
    const detail = await client.getTask(id)
    set({ current: detail })
    // 回看：把历史任务内容回填主视图（复用 StepList/ResultChart 渲染），并把 Q&A 追加进对话
    useChatStore.setState((s) => ({
      currentState: { plan: detail.plan, steps: detail.steps, report: detail.report },
      status: detail.status === 'failed' ? 'error' : 'done',
      messages: detail.report
        ? [
            ...s.messages,
            { role: 'user', content: detail.userMessage },
            { role: 'assistant', content: detail.report },
          ]
        : [...s.messages, { role: 'user', content: detail.userMessage }],
    }))
  },
```

- [ ] **Step 4: 运行测试确认通过 + 类型/ lint**

Run: `npx vitest run src/stores/taskStore.test.ts` 及 `npm run typecheck`、`npm run lint`
Expected: 全 PASS / 零报错。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/stores/taskStore.ts frontend/src/stores/taskStore.test.ts
git commit -m "feat(chat): replay task report into conversation on open"
```

提交时在 `docs/test-inventory.md` 追加：改写的 `open` 测试（功能正确，taskStore 系统，多轮上下文阶段）。

---

## 收尾：全量质量门

后端（在仓库根目录）：

```bash
ruff check
pyright
pytest
```

前端：

```bash
cd frontend && npm run typecheck && npm run lint && npm test
```

全部零报错 / 全绿后，人工抽查：

1. `ChatRequest` 契约与 `docs/specs/10-api.md` 一致（新增可选 `conversation_id`）。
2. `AgentState` 新增键与 `docs/specs/09-orchestration.md` 一致。
3. 是否有 spec 未定义的新文件/类？→ 无（只改了既有文件；`message` 表属 `03-db` 扩展，`_with_history` 是 nodes 私有助手）。

## Self-Review

- **Spec 覆盖**：03-db（message 表）→ Task 1；10-api（/chat + 持久化）→ Task 2/4；09-orchestration（state/nodes 注入）→ Task 3；16-frontend（对话面板）→ Task 5/6/7。每处 spec 均有对应任务。
- **占位符扫描**：无 TBD/TODO；所有代码块均给出完整实现。
- **类型一致**：`conversation_id`（api 层）↔ `conversationId`（前端 store）↔ `conversation_id`（state）；`history` 形状 `list[dict[str,str]]` 在 api/state/nodes 三处一致；`_with_history` 返回 `list[LlmMessage]` 与 `client.complete` 入参一致。
- **回归点**：`_with_history` 在 history 为空时退化为单条 system（既有 orchestration 测试不受影响）；`test_migrate_idempotent` 表计数 5→6 已同步；chatStore/`taskStore.open` 的 messages 断言已同步。
