# Agent 框架骨架 + 单基因表达竖切片 Implementation Plan

> **⚠️ 已过时（历史快照，勿按此实现）**：本 plan 写于设计文档与 16 份实现 spec 之前，架构已被取代——唯一权威是 `docs/design/2026-08-22-synthbio-agent-design.md` + `docs/specs/`。本文件里的 `backend/app/`→`backend/bioagent/`、`InMemorySaver` checkpointer→task 落库、`thread_id`→`task`、`bind_tools`→planner `json_mode`、`Retriever`→`RagClient` 均已失效。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭起「加工具 = 加一个文件」的 agent 框架，并让一条单基因表达管线端到端跑通（前端输入 → router/planner/executor/reporter → SSE 实时步骤 → 结果图）。

**Architecture:** FastAPI 后端 + LangGraph 四节点编排（router→planner→executor→reporter）+ 工具注册表（`tools/` 目录自动发现）。executor 通过 tool-calling 绑定注册表里裁剪后的工具子集。checkpointer 用 InMemorySaver（SQLite 升级留到后续计划）。前端 React+Vite 通过 fetch 流式读 SSE 渲染步骤。

**Tech Stack:** Python 3.11+, FastAPI, LangChain, LangGraph, sse-starlette, DeepSeek(OpenAI 兼容接口), pytest, ruff, pyright；前端 React + Vite + TypeScript(strict) + Zustand。

**Spec:** `docs/specs/2026-08-22-synthbio-agent-design.md`

## Global Constraints

- Python 3.11+，所有函数签名完整类型标注（`from __future__ import annotations`）
- 命名：`snake_case` 变量/函数，`PascalCase` 类，`UPPER_SNAKE` 常量
- I/O 操作用 `async def`（工具 `run()`、LLM 调用）；纯计算函数同步
- LLM 统一走 `app/llm/client.py::get_llm()`，不直接 httpx；测试通过 monkeypatch 注入 mock
- 加工具 = 在 `backend/tools/<category>/` 下加一个文件，不改 `app/agents/`
- 工具「文件进、文件出」契约：输入参数 + 文件路径，输出结构化 dict
- 每个工具 `run()` 测试 ≤ 5 断言；测试目录 `tests/test_{系统}/`
- 每次新增测试后更新 `docs/test-inventory.md`
- 质量门：`ruff check`、`pyright`、`pytest` 三项零报错
- 提交信息以 `Co-Authored-By: Claude <noreply@anthropic.com>` 结尾

---

## File Structure

```
backend/
├── pyproject.toml                 # 依赖 + ruff + pyright 配置
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口，挂载 chat 路由，启动时 build graph
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py              # get_llm()（mockable 工厂）
│   ├── registry/
│   │   ├── __init__.py
│   │   ├── contract.py            # Category / Runtime / ToolDefinition
│   │   └── registry.py            # ToolRegistry: register/discover/for_categories
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py               # AgentState (TypedDict)
│   │   ├── nodes.py               # router/planner/executor/reporter 四节点
│   │   └── graph.py               # build_graph(registry) -> CompiledGraph
│   └── api/
│       ├── __init__.py
│       └── chat.py                # POST /chat -> SSE 流
├── tools/
│   ├── __init__.py                # 空包，供 discover() 扫描
│   ├── system/
│   │   ├── __init__.py
│   │   └── env_check.py           # 环境诊断工具（category=system）
│   └── single_gene/
│       ├── __init__.py
│       └── expression.py          # 单基因表达（category=single_gene，mock 数据）
└── tests/
    ├── conftest.py                # fake 工具 + fake LLM fixture
    ├── test_registry/
    │   └── test_registry.py
    ├── test_agents/
    │   └── test_graph.py
    └── test_tools/
        └── test_env_check.py

frontend/
├── package.json                   # 由 vite 脚手架生成后补充
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── stores/chatStore.ts        # Zustand：messages + steps
│   ├── hooks/useChatSSE.ts        # fetch POST 流式读 SSE
│   └── components/
│       ├── ChatBox.tsx
│       ├── StepList.tsx
│       └── ResultPanel.tsx
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/tools/__init__.py`
- Create: `backend/tools/system/__init__.py`
- Create: `backend/tools/single_gene/__init__.py`

**Interfaces:**
- Produces: 可被 `pip install -e .` 的包；`tools` 与 `app` 两个可导入命名空间。

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "bio-agent-backend"
version = "0.1.0"
description = "Synthetic biology multi-agent assistant backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sse-starlette>=2.1",
    "langchain>=0.3",
    "langgraph>=0.2",
    "langchain-openai>=0.2",
    "pydantic>=2.7",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6", "pyright>=1.1"]

[tool.setuptools]
packages = ["app", "tools"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pyright]
pythonVersion = "3.11"
typeCheckingMode = "standard"
include = ["app", "tools", "tests"]
```

- [ ] **Step 2: 写空 `__init__.py` 文件**

四个 `__init__.py` 内容均为空（`app/__init__.py`、`tools/__init__.py`、`tools/system/__init__.py`、`tools/single_gene/__init__.py`）。

- [ ] **Step 3: 安装并验证导入**

Run: `cd backend && pip install -e ".[dev]" && python -c "import app, tools; print('ok')"`
Expected: 打印 `ok`，无报错。

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tools
git commit -m "chore: scaffold backend package with ruff/pyright config

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 工具契约 ToolDefinition

**Files:**
- Create: `backend/app/registry/__init__.py`
- Create: `backend/app/registry/contract.py`
- Test: `backend/tests/test_registry/__init__.py`

**Interfaces:**
- Produces: `Category(str, Enum)`（含 `DATA/KNOWLEDGE/SYSTEM/SINGLE_GENE/DGE/ENRICHMENT/NETWORK/SURVIVAL`）、`Runtime(str, Enum)`（`PYTHON/R`）、`ToolDefinition`（frozen dataclass，字段：`name: str, description: str, category: Category, runtime: Runtime, input_schema: dict, output_schema: dict, run: Callable[..., Awaitable[dict]], frontend: dict = {}`）。

- [ ] **Step 1: 写 contract.py**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Category(str, Enum):
    DATA = "data"
    KNOWLEDGE = "knowledge"
    SYSTEM = "system"
    SINGLE_GENE = "single_gene"
    DGE = "dge"
    ENRICHMENT = "enrichment"
    NETWORK = "network"
    SURVIVAL = "survival"


class Runtime(str, Enum):
    PYTHON = "python"
    R = "r"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    category: Category
    runtime: Runtime
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    run: Callable[..., Awaitable[dict[str, Any]]]
    frontend: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 2: 写测试验证契约字段**

```python
# tests/test_registry/test_contract.py
from __future__ import annotations

from app.registry.contract import Category, Runtime, ToolDefinition


async def _noop(**kwargs: object) -> dict[str, object]:
    return {}


def test_tool_definition_is_frozen_and_defaulted():
    t = ToolDefinition(
        name="x",
        description="d",
        category=Category.SYSTEM,
        runtime=Runtime.PYTHON,
        input_schema={},
        output_schema={},
        run=_noop,
    )
    assert t.frontend == {}
    assert t.category is Category.SYSTEM
```

- [ ] **Step 3: 跑测试确认通过**

Run: `cd backend && pytest tests/test_registry/test_contract.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/registry backend/tests/test_registry
git commit -m "feat: add ToolDefinition contract

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 工具注册表 ToolRegistry

**Files:**
- Create: `backend/app/registry/registry.py`
- Test: `backend/tests/test_registry/test_registry.py`

**Interfaces:**
- Consumes: `ToolDefinition`, `Category`（Task 2）。
- Produces: `ToolRegistry` 类，方法 `register(tool) -> None`、`discover(package: str = "tools") -> None`、`get(name) -> ToolDefinition`、`for_categories(categories: set[Category]) -> list[ToolDefinition]`。`discover` 用 `pkgutil.walk_packages` 导入 `tools` 包下每个子模块，取模块级 `TOOL` 属性注册。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_registry/test_registry.py
from __future__ import annotations

import pytest

from app.registry.contract import Category, Runtime, ToolDefinition
from app.registry.registry import ToolRegistry


async def _noop(**kwargs: object) -> dict[str, object]:
    return {}


def _make(name: str, category: Category) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="d",
        category=category,
        runtime=Runtime.PYTHON,
        input_schema={},
        output_schema={},
        run=_noop,
    )


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(_make("a", Category.SYSTEM))
    assert reg.get("a").name == "a"


def test_duplicate_name_raises():
    reg = ToolRegistry()
    reg.register(_make("a", Category.SYSTEM))
    with pytest.raises(ValueError):
        reg.register(_make("a", Category.DATA))


def test_for_categories_filters():
    reg = ToolRegistry()
    reg.register(_make("a", Category.SYSTEM))
    reg.register(_make("b", Category.SINGLE_GENE))
    assert [t.name for t in reg.for_categories({Category.SINGLE_GENE})] == ["b"]


def test_discover_finds_tools_package():
    reg = ToolRegistry()
    reg.discover()
    # tools/ 下已有 env_check 与 expression，见 Task 6/7；此处先断言 discover 不抛错
    assert isinstance(reg.get("env_check"), ToolDefinition)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/test_registry/test_registry.py -v`
Expected: 前三个 PASS，`test_discover_finds_tools_package` FAIL（`env_check` 尚未注册 / `ToolRegistry` 未定义）。

- [ ] **Step 3: 写 registry.py**

```python
from __future__ import annotations

import importlib
import pkgutil

from .contract import Category, ToolDefinition


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def discover(self, package: str = "tools") -> None:
        pkg = importlib.import_module(package)
        for _, mod_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=package + "."):
            module = importlib.import_module(mod_name)
            tool = getattr(module, "TOOL", None)
            if isinstance(tool, ToolDefinition):
                self.register(tool)

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]

    def for_categories(self, categories: set[Category]) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.category in categories]
```

- [ ] **Step 4: 暂缓 discover 测试**（`test_discover_finds_tools_package` 依赖 Task 7 的 `env_check`）

给该测试加 `@pytest.mark.skip(reason="env_check tool lands in Task 7")`，其余断言通过。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && pytest tests/test_registry/test_registry.py -v`
Expected: 3 PASS + 1 SKIP

- [ ] **Step 6: Commit**

```bash
git add backend/app/registry/registry.py backend/tests/test_registry/test_registry.py
git commit -m "feat: add ToolRegistry with auto-discovery

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: LLM 客户端

**Files:**
- Create: `backend/app/llm/__init__.py`
- Create: `backend/app/llm/client.py`
- Test: `backend/tests/test_llm/test_client.py`（含 `__init__.py`）

**Interfaces:**
- Produces: `get_llm() -> BaseChatModel`。读环境变量 `BIO_AGENT_MODEL`（默认 `deepseek-chat`）、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`）。测试通过 monkeypatch `get_llm` 注入 `FakeListChatModel`。

- [ ] **Step 1: 写 client.py**

```python
from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


def get_llm() -> BaseChatModel:
    """统一 LLM 工厂。DeepSeek 走 OpenAI 兼容接口；测试 monkeypatch 此函数。"""
    return ChatOpenAI(
        model=os.environ.get("BIO_AGENT_MODEL", "deepseek-chat"),
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0,
    )
```

- [ ] **Step 2: 写测试验证工厂可被替换**

```python
# tests/test_llm/test_client.py
from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeListChatModel

import app.llm.client as client


def test_get_llm_is_monkeypatchable(monkeypatch):
    fake = FakeListChatModel(responses=["ok"])
    monkeypatch.setattr(client, "get_llm", lambda: fake)
    assert client.get_llm() is fake
```

- [ ] **Step 3: 跑测试确认通过**

Run: `cd backend && pytest tests/test_llm/test_client.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/llm backend/tests/test_llm
git commit -m "feat: add mockable LLM client

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: AgentState + 四节点 + graph

**Files:**
- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/agents/state.py`
- Create: `backend/app/agents/nodes.py`
- Create: `backend/app/agents/graph.py`
- Test: `backend/tests/test_agents/test_graph.py`（含 `__init__.py`）

**Interfaces:**
- Consumes: `get_llm`（Task 4）、`ToolRegistry`（Task 3）。
- Produces:
  - `AgentState`（`TypedDict`，字段 `messages: Annotated[list[AnyMessage], add_messages]`、`intent: str`、`plan: list[str]`、`steps: list[dict]`、`report: str`）。
  - `router_node(state) -> dict`、`planner_node(state) -> dict`、`executor_node(state, registry, categories) -> dict`（用 `functools.partial` 绑定）、`reporter_node(state) -> dict`。
  - `build_graph(registry) -> CompiledStateGraph`（`InMemorySaver` checkpointer）。

- [ ] **Step 1: 写 state.py**

```python
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: str
    plan: list[str]
    steps: list[dict]
    report: str
```

- [ ] **Step 2: 写 nodes.py**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain_core.messages import SystemMessage

from app.llm.client import get_llm
from app.registry.contract import Category, ToolDefinition
from app.registry.registry import ToolRegistry
from app.agents.state import AgentState

_CATEGORY_NAMES = [c.value for c in Category]


def router_node(state: AgentState) -> dict:
    llm = get_llm()
    msg = llm.invoke(
        [
            SystemMessage(
                content=(
                    "你是合成生物学 agent 的意图路由器。"
                    "根据用户需求输出一个类别名，只能从以下选择："
                    f"{', '.join(_CATEGORY_NAMES)}。只输出类别名，不要解释。"
                )
            ),
            *state.get("messages", []),
        ]
    )
    intent = (msg.content or "").strip().lower()
    return {"intent": intent if intent in _CATEGORY_NAMES else "system"}


def planner_node(state: AgentState) -> dict:
    llm = get_llm()
    msg = llm.invoke(
        [
            SystemMessage(content="你是规划器。把用户需求拆成 2-5 步，每步一行，不要编号以外的文字。"),
            *state.get("messages", []),
        ]
    )
    plan = [line.strip("- ") for line in str(msg.content).splitlines() if line.strip()]
    return {"plan": plan}


def make_executor_node(
    registry: ToolRegistry, categories: set[Category]
) -> Callable[[AgentState], Awaitable[dict[str, object]]]:
    async def executor_node(state: AgentState) -> dict[str, object]:
        tools = [t for t in registry.for_categories(categories)]
        steps: list[dict] = []
        llm = get_llm()
        tool_map = {t.name: t for t in tools}
        bound = llm.bind_tools([_as_openai_tool(t) for t in tools])
        messages = [*state.get("messages", [])]
        for _ in range(5):
            ai_msg = bound.invoke(messages)
            messages.append(ai_msg)
            if not getattr(ai_msg, "tool_calls", None):
                break
            for call in ai_msg.tool_calls:
                tool = tool_map[call["name"]]
                result = await tool.run(**call["args"])
                steps.append({"tool": tool.name, "input": call["args"], "output": result})
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": str(result)}
                )
        return {"steps": steps}

    return executor_node


def _as_openai_tool(t: ToolDefinition) -> dict:
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.input_schema,
        },
    }


def reporter_node(state: AgentState) -> dict:
    llm = get_llm()
    steps_text = "\n".join(str(s) for s in state.get("steps", []))
    msg = llm.invoke(
        [
            SystemMessage(content="你是报告生成器。根据已执行步骤的结果，用中文写一段简洁结论。"),
            *state.get("messages", []),
            SystemMessage(content=f"执行结果：\n{steps_text}"),
        ]
    )
    return {"report": str(msg.content)}
```

- [ ] **Step 3: 写 graph.py**

```python
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import AgentState
from app.registry.contract import Category
from app.registry.registry import ToolRegistry


def build_graph(registry: ToolRegistry) -> object:
    graph = StateGraph(AgentState)
    graph.add_node("router", nodes.router_node)
    graph.add_node("planner", nodes.planner_node)
    graph.add_node("reporter", nodes.reporter_node)
    graph.add_node("executor", nodes.make_executor_node(registry, set(Category)))
    graph.add_edge(START, "router")
    graph.add_edge("router", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile(checkpointer=InMemorySaver())
```

> 说明：MVP 阶段 executor 绑定全量工具（`set(Category)`）；管线裁剪（按 router 判定的 intent 只绑子集）留到 plan 2，与真实工具一起落地。

- [ ] **Step 4: 写 graph 测试（mock LLM + fake 工具，验证四节点走通）**

```python
# tests/test_agents/test_graph.py
from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeListChatModel

import app.llm.client as llm_client
from app.agents.graph import build_graph
from app.registry.contract import Category, Runtime, ToolDefinition
from app.registry.registry import ToolRegistry

import pytest

async def _echo(**kwargs: object) -> dict[str, object]:
    return {"echoed": kwargs}


@pytest.mark.asyncio
async def test_graph_runs_four_nodes(monkeypatch):
    # router -> "single_gene", planner -> 2 步, executor LLM 无 tool_call 直接结束, reporter -> 结论
    monkeypatch.setattr(
        llm_client, "get_llm", lambda: FakeListChatModel(responses=["single_gene", "step1\nstep2", "", "done"])
    )
    reg = ToolRegistry()
    reg.register(
        ToolDefinition(
            name="echo",
            description="echo back",
            category=Category.SYSTEM,
            runtime=Runtime.PYTHON,
            input_schema={},
            output_schema={},
            run=_echo,
        )
    )
    graph = build_graph(reg)
    result = await graph.ainvoke(
        {"messages": [("user", "分析这个基因")]},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert result["intent"] == "single_gene"
    assert result["plan"] == ["step1", "step2"]
    assert result["report"] == "done"
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && pip install pytest-asyncio && pytest tests/test_agents/test_graph.py -v`
Expected: PASS（`pytest-asyncio` 需在 `pyproject.toml` dev 依赖补 `"pytest-asyncio>=0.23"`）

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents backend/tests/test_agents
git commit -m "feat: add LangGraph four-node orchestration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: FastAPI `/chat` SSE 流

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/chat.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api/test_chat.py`（含 `__init__.py`）

**Interfaces:**
- Consumes: `build_graph`（Task 5）。
- Produces: `POST /chat`，请求体 `{"message": str, "thread_id": str | None}`。返回 `EventSourceResponse`，流式产出 JSON 事件：`{"event": "node", "data": {"node": str, "update": dict}}`，最后 `{"event": "done", "data": {"thread_id": str}}`。`main.py` 里模块级 `build_graph` 一次，暴露 `app.state.graph` 供测试注入 mock。

- [ ] **Step 1: 写 chat.py**

```python
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> EventSourceResponse:
    graph = request.app.state.graph
    thread_id = req.thread_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    async def event_stream():
        async for node, update in graph.astream(
            {"messages": [("user", req.message)]}, config, stream_mode="updates"
        ):
            yield {"event": "node", "data": json.dumps({"node": node, "update": update})}
        yield {"event": "done", "data": json.dumps({"thread_id": thread_id})}

    return EventSourceResponse(event_stream())
```

- [ ] **Step 2: 写 main.py**

```python
from __future__ import annotations

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.agents.graph import build_graph
from app.registry.registry import ToolRegistry


def create_app() -> FastAPI:
    registry = ToolRegistry()
    registry.discover()
    app = FastAPI(title="bio-agent-backend")
    app.state.registry = registry
    app.state.graph = build_graph(registry)
    app.include_router(chat_router)
    return app


app = create_app()
```

- [ ] **Step 3: 写 SSE 测试**

```python
# tests/test_api/test_chat.py
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.registry.contract import Category, Runtime, ToolDefinition
from app.registry.registry import ToolRegistry

from langchain_core.language_models.fake_chat_models import FakeListChatModel
import app.llm.client as llm_client


def test_chat_streams_nodes(monkeypatch):
    monkeypatch.setattr(
        llm_client, "get_llm", lambda: FakeListChatModel(responses=["system", "a\nb", "", "ok"])
    )
    client = TestClient(app)
    with client.stream("POST", "/chat", json={"message": "hi"}) as r:
        events = [
            json.loads(line.removeprefix("data: ").strip())
            for line in r.iter_lines()
            if line and line.startswith("data: ")
        ]
    kinds = [e["event"] for e in events if "event" in e]
    assert kinds[0] == "node"
    assert kinds[-1] == "done"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pip install httpx && pytest tests/test_api/test_chat.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_api
git commit -m "feat: add /chat SSE streaming endpoint

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 第一个真实工具 env_check（+ 单基因 expression 占位）

**Files:**
- Create: `backend/tools/system/env_check.py`
- Create: `backend/tools/single_gene/expression.py`
- Test: `backend/tests/test_tools/test_env_check.py`

**Interfaces:**
- Consumes: `ToolDefinition`（Task 2）。每个工具模块暴露模块级 `TOOL: ToolDefinition`。
- Produces: `env_check`（`category=system`，返回 python 版本 + 已安装关键包版本）；`single_gene_expression`（`category=single_gene`，输入 `gene: str`，返回 mock 表达向量 + 图片路径占位）。

- [ ] **Step 1: 写 env_check.py**

```python
from __future__ import annotations

import platform
import sys

from app.registry.contract import Category, Runtime, ToolDefinition


async def _run(gene: str = "") -> dict:
    return {"python": sys.version.split()[0], "platform": platform.platform()}


TOOL = ToolDefinition(
    name="env_check",
    description="检查运行环境的 Python 版本与平台。",
    category=Category.SYSTEM,
    runtime=Runtime.PYTHON,
    input_schema={"type": "object", "properties": {}, "required": []},
    output_schema={"type": "object", "properties": {"python": {"type": "string"}}},
    run=_run,
    frontend={"result_type": "text"},
)
```

- [ ] **Step 2: 写 expression.py（mock 数据，真实 R 在 plan 2）**

```python
from __future__ import annotations

import hashlib

from app.registry.contract import Category, Runtime, ToolDefinition


async def _run(gene: str) -> dict:
    # MVP 用确定性 mock 表达向量；真实数据读取在 plan 2 接入
    seed = int(hashlib.md5(gene.encode()).hexdigest(), 16)
    values = [round((seed % 97 + i) % 17 + 0.5, 2) for i in range(10)]
    return {"gene": gene, "expression": values, "figure": None}


TOOL = ToolDefinition(
    name="single_gene_expression",
    description="查询单个基因的表达值向量。输入 gene 为基因名（如 TP53）。",
    category=Category.SINGLE_GENE,
    runtime=Runtime.PYTHON,
    input_schema={
        "type": "object",
        "properties": {"gene": {"type": "string"}},
        "required": ["gene"],
    },
    output_schema={
        "type": "object",
        "properties": {"gene": {"type": "string"}, "expression": {"type": "array"}},
    },
    run=_run,
    frontend={"result_type": "bar_chart"},
)
```

- [ ] **Step 3: 写 env_check 测试**

```python
# tests/test_tools/test_env_check.py
from __future__ import annotations

import pytest

from tools.system.env_check import TOOL


@pytest.mark.asyncio
async def test_env_check_returns_python_version():
    out = await TOOL.run()
    assert "python" in out
    assert "platform" in out
```

- [ ] **Step 4: 移除 Task 3 的 skip，跑全部工具与注册表测试**

Run: `cd backend && pytest tests/test_registry tests/test_tools -v`
Expected: `test_discover_finds_tools_package` 现在 PASS，其余 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/tools backend/tests/test_tools
git commit -m "feat: add env_check and single_gene_expression tools

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 前端最小闭环

**Files:**
- Create: `frontend/`（`npm create vite@latest frontend -- --template react-ts`）
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/stores/chatStore.ts`
- Create: `frontend/src/hooks/useChatSSE.ts`
- Create: `frontend/src/components/ChatBox.tsx`
- Create: `frontend/src/components/StepList.tsx`
- Create: `frontend/src/components/ResultPanel.tsx`

**Interfaces:**
- Consumes: `POST /chat` 的 SSE 事件格式（Task 6）。
- Produces: 可运行的聊天页：输入框 → 发送 → StepList 实时显示节点 → ResultPanel 显示结论。

- [ ] **Step 1: 脚手架 + 装依赖**

Run: `npm create vite@latest frontend -- --template react-ts && cd frontend && npm i && npm i zustand`
Expected: 生成 `frontend/`，`npm run dev` 能起。

- [ ] **Step 2: 写 chatStore.ts**

```ts
import { create } from "zustand";

export interface Step {
  node: string;
  update: Record<string, unknown>;
}

interface ChatState {
  messages: { role: "user" | "assistant"; content: string }[];
  steps: Step[];
  report: string;
  send: (text: string) => void;
  addStep: (s: Step) => void;
  setReport: (r: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  steps: [],
  report: "",
  send: (text) =>
    set((s) => ({ messages: [...s.messages, { role: "user", content: text }] })),
  addStep: (step) => set((s) => ({ steps: [...s.steps, step] })),
  setReport: (report) => set({ report }),
}));
```

- [ ] **Step 3: 写 useChatSSE.ts**

```ts
import { useChatStore } from "../stores/chatStore";

export function useChatSSE() {
  const addStep = useChatStore((s) => s.addStep);
  const setReport = useChatStore((s) => s.setReport);

  const send = async (message: string, threadId?: string) => {
    const resp = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: threadId }),
    });
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const event = JSON.parse(line.slice(6));
        if (event.event === "node") {
          addStep({ node: event.data.node, update: event.data.update });
        } else if (event.event === "done") {
          setReport(event.data.report ?? "");
        }
      }
    }
  };

  return { send };
}
```

- [ ] **Step 4: 写三个组件 + App.tsx**

```tsx
// ChatBox.tsx
import { useState } from "react";
import { useChatStore } from "../stores/chatStore";
import { useChatSSE } from "../hooks/useChatSSE";

export function ChatBox() {
  const [text, setText] = useState("");
  const messages = useChatStore((s) => s.messages);
  const sendMessage = useChatStore((s) => s.send);
  const { send } = useChatSSE();

  const onSubmit = async () => {
    sendMessage(text);
    await send(text);
    setText("");
  };

  return (
    <div>
      <div>
        {messages.map((m, i) => (
          <div key={i}>
            <b>{m.role}:</b> {m.content}
          </div>
        ))}
      </div>
      <input value={text} onChange={(e) => setText(e.target.value)} />
      <button onClick={onSubmit}>发送</button>
    </div>
  );
}
```

```tsx
// StepList.tsx
import { useChatStore } from "../stores/chatStore";

export function StepList() {
  const steps = useChatStore((s) => s.steps);
  return (
    <ul>
      {steps.map((s, i) => (
        <li key={i}>
          <b>{s.node}</b> {JSON.stringify(s.update)}
        </li>
      ))}
    </ul>
  );
}
```

```tsx
// ResultPanel.tsx
import { useChatStore } from "../stores/chatStore";

export function ResultPanel() {
  const report = useChatStore((s) => s.report);
  return <pre>{report}</pre>;
}
```

```tsx
// App.tsx
import { ChatBox } from "./components/ChatBox";
import { StepList } from "./components/StepList";
import { ResultPanel } from "./components/ResultPanel";

export default function App() {
  return (
    <div>
      <h1>bio-agent</h1>
      <StepList />
      <ResultPanel />
      <ChatBox />
    </div>
  );
}
```

- [ ] **Step 5: 配置 dev 代理，手动联调**

在 `frontend/vite.config.ts` 加 `server: { proxy: { "/chat": "http://localhost:8000" } }`。先后端 `uvicorn app.main:app --reload`，再前端 `npm run dev`，浏览器输入「分析基因 TP53 的表达」，确认 StepList 出现四个节点、ResultPanel 出现结论。

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: add minimal React frontend with SSE chat

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 后续计划（不在本计划内）

- **Plan 2**：管线裁剪（router intent → executor 绑定子集）+ 真实 R 子进程（`runners/`）+ 真实 DESeq2/limma 差异表达 + KM 生存曲线。
- **Plan 3**：RAG 层（`Retriever` 接口 + Qdrant）+ `knowledge` 工具。
- **Plan 4**：checkpointer 升级 SQLite、任务历史接口 `/tasks`、Docker 一键部署。
- **Plan 5**：网络药理学（PPI/STRING）+ 其余工具（机器学习/单细胞/空间/虚拟扰动/文献）。
