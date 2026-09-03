# 多轮对话上下文（Multi-turn Conversation）

> 范围：`backend/bioagent/db.py`（migration v2 `message` 表）、`backend/bioagent/api.py`（`append_turn` / `list_messages` + `/chat` 接线）、`backend/bioagent/orchestration/state.py`（`conversation_id` / `history`）、`backend/bioagent/orchestration/nodes.py`（`_with_history`）、前端 `chatStore` / `ChatPanel` / `taskStore.open`。
> 本 spec 落地于 2026-09-03 的实现计划，反向补写为 spec：让 agent 记住同一对话内的历史轮次，把之前轮次的 user/assistant 作为上下文喂给 router/planner/reporter。
> **关键语义修订**：设计文档 5.2 原「一次会话 = 一个 task（`correlation_id`）」在本 spec 下被细化为「一次 **conversation** 可跨多个 **task**」——`conversation_id` 是对话维度，`task_id`（`correlation_id`）仍是单次运行的执行维度。

## 元信息

- **前置依赖**：03-db（`message` 表 DDL + `Database`）、09-orchestration（`AgentState`）、10-api（`/chat`、`task` 表 CRUD）、16-frontend（对话面板）
- **包根路径**：`backend/bioagent/`，import 为 `bioagent.xxx`

## 用户故事

> 作为 bio agent 的用户，我想要在同一次对话里连续追问时，agent 记得我之前说过什么、答过什么，以便追问「改一下阈值」「换成 survival 分析」时不丢上下文、可回溯每一轮的 Q&A。

## 验收标准

- [ ] `message` 表 DDL 与 03-db `_MIGRATIONS` v2 逐字一致（`id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL` + 索引 `idx_message_conversation(conversation_id, created_at)`）
- [ ] `AgentState` 含 `conversation_id: str`、`history: list[dict[str, str]]` 两个字段
- [ ] `/chat` 请求体 `{message, conversation_id?}`：`conversation_id` 缺省时新建一个 uuid；续接时加载历史
- [ ] 一轮成功的 turn 把 user + assistant 两条消息**原子**写入 `message` 表（`append_turn` 单事务），失败 turn 不写任何 message
- [ ] router / planner / reporter 三节点都把 `history` 拼到系统消息之后、作为 LLM 上下文（`_with_history`，role 只收 user/assistant，空 history 退化为单条 system 消息）
- [ ] 前端对话面板按 `messages` 数组渲染完整多轮（assistant 走 markdown），「新对话」重置 `conversationId`；回看历史 task 时把 Q&A 回填进 `messages`
- [ ] `pyright` strict 零报错；前端 `tsc --noEmit` 零报错
- [ ] 拓扑不变：router→planner→executor→reporter 编排层不改

## 技术方案

### `message` 表（03-db migration v2）

每轮**成功后**落一条 user + 一条 assistant。`id` 是 AUTOINCREMENT，作为 `created_at` 相同（原子写入同一次 `time.time()`）时的顺序 tiebreaker。`conversation_id` 是 uuid4，`role` ∈ `{"user", "assistant"}`。

### 状态字段（09-orchestration）

`AgentState` 新增：`conversation_id: str`、`history: list[dict[str, str]]`。`history` 由 `/chat` 从 `list_messages` 装载（不含当前 query），注入 `initial`，随 SSE 逐帧透传。

### `/chat` 接线（10-api）

```
POST /chat  {message, conversation_id?}
  conversation_id = req.conversation_id or uuid4()
  history = list_messages(conversation_id)          # 之前轮次
  initial = {query, correlation_id: task_id, conversation_id, history}
  astream(initial, values) → 逐帧 yield state
  成功后：complete_task → append_turn(user, assistant) → yield {done, task_id, conversation_id}
  失败后：fail_task → yield {error, task_id}        # 不写 message
```

**只持久化成功轮次**（ruling）：失败 turn 不写 `message`，故失败的追问不会成为下一轮 LLM 的上下文；失败尝试仍留在 `task` 表（可回溯）。代价：失败后追问缺少上一问作上下文（可接受，用户重试）。

### 原子写入助手（10-api）

```python
async def append_turn(
    db: Database, conversation_id: str, user_content: str, assistant_content: str
) -> None:
    """一轮对话 user+assistant 原子写入（单事务），避免中途失败留 dangling user。"""
    now = time.time()
    async with db.lock:
        await db.conn.execute("BEGIN")
        try:
            await db.conn.execute(
                "INSERT INTO message (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, "user", user_content, now),
            )
            await db.conn.execute(
                "INSERT INTO message (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, "assistant", assistant_content, now),
            )
            await db.conn.commit()
        except BaseException:
            await db.conn.rollback()
            raise
```

`list_messages` 按 `ORDER BY created_at ASC, id ASC` 返回 `[{role, content}]`，`id ASC` 是并发/同时间戳下的顺序保证。

### 历史注入（09-orchestration nodes）

`_with_history(prompt, state)` 返回 `[_system(prompt)] + history`，其中 history 只收 `role ∈ {user, assistant}` 的消息（过滤其它 role）；空 history 退化为单条 system，保持既有测试（断言 `messages[0]`）不变。

### 前端（16-frontend）

- `chatStore`：`conversationId = crypto.randomUUID()`（初始化 + `reset`），`messages: Message[]`，`send` 后把 `lastReport` 追加为 assistant 消息；`reset` 清空并生成新 id。
- `ChatPanel`：无 props，从 store 读 `messages` 渲染；user 纯文本、assistant `ReactMarkdown`。
- `taskStore.open`：回看历史 task 时把 `userMessage` + `report` 回填进 `messages`（复用对话面板展示报告）。

## 已知局限 / 范围决定（ruling）

- **会话仅内存态**：`conversationId` 不落 `localStorage`，页面刷新后对话在服务端孤立、UI 无 resume 入口。MVP 范围外（persistence 未定义）；若需跨刷新记忆，再扩展。
- **历史无上限**：`list_messages` 全量返回、`_with_history` 全量注入三节点 + 每帧 SSE 全量回放 history；token 随轮数线性增长，超长对话可能触上下文上限。已知限制，暂不加 cap。
- **失败轮次 UI 残留**：前端 `send` 乐观追加 user 消息且失败不撤；后端不持久化失败轮次，故下一轮模型实际看不到该条。单轮可见/实际上下文短暂不一致，接受（撤销会丢失用户输入）。
- **prompt 注入面**：持久化的用户原文与 assistant markdown 被逐字回注入 LLM 上下文（仅 role 过滤，无分隔符/消毒）。多轮固有、低风险（同一用户拥有该对话），与 how-security.md 姿态一致。
- **`conversation_id` 后端写而不读**：进了 `initial` 但无节点消费，端点用局部变量回显；前端忽略回显。无害的冗余往返，暂不清理。

## 测试要点

- [ ] 单元（`tests/test_api/`，`pytest-asyncio`，`:memory:`）：
  - [ ] `append_turn` + `list_messages`：写入一对 user+assistant 后按序返回；跨对话隔离；空对话返回 `[]`
  - [ ] `/chat` 成功轮次持久化：`test_chat_generates_new_conversation_when_absent` 断言 `list_messages` = 当前轮 user+assistant
  - [ ] `/chat` 续接注入历史：`test_chat_persists_conversation_and_injects_history` 断言 `graph.initial["history"]` = 之前轮次
  - [ ] `/chat` 失败轮次不落库：`test_chat_stream_failure` 断言 task FAILED 且 `message` 表 0 行
- [ ] 编排（`tests/test_orchestration/`）：router 节点 messages 含 history（`test_router_node` 已断言 `messages[0]` 为 system，追加 history 断言）
- [ ] 前端（vitest）：`chatStore` conversationId + assistant 消息、`ChatPanel` markdown 渲染、`taskStore.open` 回填 messages
- [ ] 集成：无独立集成（复用 /chat 端到端）
- [ ] E2E：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] 前端 `npm run typecheck` / `npm run lint` / `npm test` 全绿
- [ ] `docs/test-inventory.md` 已更新
- [ ] 设计文档 5.2 的「会话」定义已修订（conversation 可跨多个 task）
