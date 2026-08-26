# pyright: reportTypedDictNotRequiredAccess=false, reportUnknownMemberType=false
import asyncio
import os
from typing import Any, cast

import pytest

from bioagent.db import Database
from bioagent.enums import Category, Runtime
from bioagent.llm.client import LlmClient
from bioagent.orchestration import nodes
from bioagent.orchestration.graph import build_graph
from bioagent.orchestration.nodes import (
    make_executor_node,
    make_planner_node,
    make_reporter_node,
    make_router_node,
)
from bioagent.orchestration.nodes import _resolve_files  # pyright: ignore[reportPrivateUsage]
from bioagent.orchestration.state import AgentState
from bioagent.r_runner import RRunner
from bioagent.rag import RagClient
from bioagent.tools import ToolRegistry
from bioagent.types import LLMOutput, ToolDefinition


def _output(content: str, *, module: str, output_type: str) -> LLMOutput:
    return LLMOutput(
        id=f"{module}-1",
        module=module,
        type=output_type,
        model="test-model",
        content=content,
        token_usage={"input": 1, "output": 1},
        correlation_id="corr-1",
    )


class _FakeClient:
    def __init__(self, outputs: dict[str, LLMOutput]) -> None:
        self._outputs = outputs
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        module: str,
        output_type: str,
        correlation_id: str,
        json_mode: bool = False,
    ) -> LLMOutput:
        self.calls.append(
            {
                "messages": messages,
                "module": module,
                "output_type": output_type,
                "correlation_id": correlation_id,
                "json_mode": json_mode,
            }
        )
        return self._outputs[module]


class _FakeRegistry:
    def __init__(self) -> None:
        self.for_categories_calls: list[set[Category]] = []
        self._tools: list[ToolDefinition] = []
        self._by_name: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools.append(tool)
        self._by_name[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        return self._by_name[name]

    def for_categories(self, categories: set[Category]) -> list[ToolDefinition]:
        self.for_categories_calls.append(categories)
        return [t for t in self._tools if t.category in categories]


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, script_name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((script_name, args))
        return {"r": "ok"}


class _FakeRag:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = docs if docs is not None else []
        self.queries: list[str] = []

    async def query(self, text: str) -> list[dict[str, Any]]:
        self.queries.append(text)
        return self.docs


class _FakeDb:
    def __init__(self) -> None:
        self.conn: Any = None
        self.lock = asyncio.Lock()


def _tool(name: str, category: Category) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} 描述",
        category=category,
        runtime=Runtime.PYTHON,
        input_schema={"type": "object", "properties": {"n": {"type": "integer"}}},
        output_schema={"type": "object"},
        run=None,
        r_script=None,
    )


# ---- make_router_node ----

async def test_router_node() -> None:
    output = _output('{"intent": "差异表达分析", "categories": ["dge"]}', module="router", output_type="intent")
    fake = _FakeClient({"router": output})
    node = make_router_node(cast(LlmClient, fake))
    state: AgentState = {"query": "哪些基因差异表达？", "correlation_id": "corr-1"}
    result = await node(state)
    assert result == {"intent": "差异表达分析", "categories": ["dge"]}
    call = fake.calls[0]
    assert call["module"] == "router"
    assert call["output_type"] == "intent"
    assert call["json_mode"] is True
    assert call["correlation_id"] == "corr-1"
    prompt = call["messages"][0]["content"]
    assert "dge" in prompt and "enrichment" in prompt
    assert "哪些基因差异表达？" in prompt


# ---- make_planner_node ----

async def test_planner_node_sample_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _output('{"steps": [{"tool": "dge_foo", "args": {"n": 3}}]}', module="planner", output_type="plan")
    fake = _FakeClient({"planner": output})
    registry = _FakeRegistry()
    registry.register(_tool("dge_foo", Category.DGE))
    rag = _FakeRag([{"text": "基因表达", "score": 0.9}])

    calls: list[tuple[Any, ...]] = []

    async def fake_eval(
        client: LlmClient,
        db: Database,
        output: LLMOutput,
        query: str,
        intent: str,
        plan: list[dict[str, Any]],
    ) -> None:
        calls.append((client, db, output, query, intent, plan))

    monkeypatch.setattr(nodes, "evaluate_tool_call", fake_eval)

    node = make_planner_node(
        cast(LlmClient, fake),
        cast(ToolRegistry, registry),
        cast(Database, _FakeDb()),
        0.0,
        cast(RagClient, rag),
    )
    state: AgentState = {
        "query": "哪些基因差异表达？",
        "correlation_id": "corr-1",
        "intent": "差异表达",
        "categories": ["dge"],
    }
    result = await node(state)
    assert result == {"plan": [{"tool": "dge_foo", "args": {"n": 3}}]}
    assert registry.for_categories_calls == [{Category.DGE}]
    assert rag.queries == ["哪些基因差异表达？"]
    prompt = fake.calls[0]["messages"][0]["content"]
    assert "dge_foo" in prompt
    assert "integer" in prompt
    assert "基因表达" in prompt
    assert calls == []


async def test_planner_node_sample_one(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _output('{"steps": [{"tool": "dge_foo", "args": {}}]}', module="planner", output_type="plan")
    fake = _FakeClient({"planner": output})
    registry = _FakeRegistry()
    registry.register(_tool("dge_foo", Category.DGE))
    rag = _FakeRag([])

    calls: list[dict[str, Any]] = []

    async def fake_eval(
        client: LlmClient,
        db: Database,
        output: LLMOutput,
        query: str,
        intent: str,
        plan: list[dict[str, Any]],
    ) -> None:
        calls.append({"output": output, "query": query, "intent": intent, "plan": plan})

    monkeypatch.setattr(nodes, "evaluate_tool_call", fake_eval)

    node = make_planner_node(
        cast(LlmClient, fake),
        cast(ToolRegistry, registry),
        cast(Database, _FakeDb()),
        1.0,
        cast(RagClient, rag),
    )
    state: AgentState = {
        "query": "q",
        "correlation_id": "c",
        "intent": "i",
        "categories": ["dge"],
    }
    await node(state)
    assert len(calls) == 1
    assert calls[0]["output"] is output
    assert calls[0]["query"] == "q"
    assert calls[0]["intent"] == "i"
    assert calls[0]["plan"] == [{"tool": "dge_foo", "args": {}}]


# ---- make_executor_node ----

async def test_executor_node() -> None:
    registry = _FakeRegistry()

    py_calls: list[dict[str, Any]] = []

    async def py_run(**kwargs: Any) -> dict[str, Any]:
        py_calls.append(kwargs)
        return {"value": 1}

    registry.register(
        ToolDefinition(
            name="summarize",
            description="d",
            category=Category.SINGLE_GENE,
            runtime=Runtime.PYTHON,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            run=py_run,
            r_script=None,
        )
    )
    registry.register(
        ToolDefinition(
            name="km",
            description="d",
            category=Category.SURVIVAL,
            runtime=Runtime.R,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            run=None,
            r_script="km.R",
        )
    )
    runner = _FakeRunner()

    node = make_executor_node(cast(ToolRegistry, registry), cast(RRunner, runner), "/uploads")
    state: AgentState = {
        "plan": [
            {"tool": "summarize", "args": {"matrix_file": "abc", "n": 3}},
            {"tool": "km", "args": {"clinical_file": "xyz"}},
        ],
    }
    result = await node(state)
    steps = result["steps"]
    assert len(steps) == 2
    assert steps[0] == {"tool": "summarize", "status": "completed", "result": {"value": 1}}
    assert steps[1] == {"tool": "km", "status": "completed", "result": {"r": "ok"}}
    assert py_calls == [{"matrix_file": os.path.join("/uploads", "abc"), "n": 3}]
    assert runner.calls == [("km.R", {"clinical_file": os.path.join("/uploads", "xyz")})]


# ---- _resolve_files ----

def test_resolve_files() -> None:
    assert _resolve_files({"matrix_file": "abc", "n": 3}, "/uploads") == {
        "matrix_file": os.path.join("/uploads", "abc"),
        "n": 3,
    }
    assert _resolve_files({"matrix_file": 5}, "/uploads") == {"matrix_file": 5}


# ---- make_reporter_node ----

async def test_reporter_node(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _output("# 报告\n结论", module="reporter", output_type="report")
    fake = _FakeClient({"reporter": output})
    rag = _FakeRag([{"text": "背景", "score": 0.5}])

    calls: list[dict[str, Any]] = []

    async def fake_eval(
        client: LlmClient,
        db: Database,
        output: LLMOutput,
        query: str,
        report: str,
    ) -> None:
        calls.append({"query": query, "report": report})

    monkeypatch.setattr(nodes, "evaluate_report", fake_eval)

    node = make_reporter_node(cast(LlmClient, fake), cast(Database, _FakeDb()), 1.0, cast(RagClient, rag))
    state: AgentState = {
        "query": "q",
        "correlation_id": "c",
        "plan": [{"tool": "t", "args": {}}],
        "steps": [{"tool": "t", "status": "completed", "result": {}}],
    }
    result = await node(state)
    assert result == {"report": "# 报告\n结论"}
    assert fake.calls[0]["json_mode"] is False
    assert rag.queries == ["q"]
    assert "背景" in fake.calls[0]["messages"][0]["content"]
    assert len(calls) == 1
    assert calls[0]["report"] == output.content


# ---- build_graph（集成） ----

async def test_build_graph_end_to_end() -> None:
    router_out = _output('{"intent": "差异表达", "categories": ["dge"]}', module="router", output_type="intent")
    planner_out = _output('{"steps": [{"tool": "dge_foo", "args": {"n": 3}}]}', module="planner", output_type="plan")
    reporter_out = _output("# 报告", module="reporter", output_type="report")
    fake = _FakeClient({"router": router_out, "planner": planner_out, "reporter": reporter_out})

    registry = _FakeRegistry()

    async def py_run(**kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    registry.register(
        ToolDefinition(
            name="dge_foo",
            description="d",
            category=Category.DGE,
            runtime=Runtime.PYTHON,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            run=py_run,
            r_script=None,
        )
    )

    graph = build_graph(
        cast(LlmClient, fake),
        cast(ToolRegistry, registry),
        cast(RRunner, _FakeRunner()),
        cast(Database, _FakeDb()),
        0.0,
        "/uploads",
        cast(RagClient, _FakeRag()),
    )
    final = await graph.ainvoke({"query": "哪些基因差异表达？", "correlation_id": "corr-9"})
    assert final["intent"] == "差异表达"
    assert final["categories"] == ["dge"]
    assert final["plan"] == [{"tool": "dge_foo", "args": {"n": 3}}]
    assert final["steps"] == [{"tool": "dge_foo", "status": "completed", "result": {"ok": True}}]
    assert final["report"] == "# 报告"
    assert [c["module"] for c in fake.calls] == ["router", "planner", "reporter"]
