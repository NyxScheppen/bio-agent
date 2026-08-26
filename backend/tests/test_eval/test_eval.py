import asyncio
from typing import Any, cast

import pytest

from bioagent.db import Database
from bioagent.eval import evaluate
from bioagent.eval.evaluate import evaluate_report, evaluate_tool_call
from bioagent.eval.judge import judge_report, judge_tool_call, parse_scores
from bioagent.llm.client import LlmClient
from bioagent.types import EvalScores, LLMOutput


class _FakeConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.commits = 0

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.executed.append((sql, params))

    async def commit(self) -> None:
        self.commits += 1


class _FakeDb:
    def __init__(self) -> None:
        self.conn = _FakeConn()
        self.lock = asyncio.Lock()


class _FakeClient:
    def __init__(self, output: LLMOutput) -> None:
        self._output = output
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
        return self._output


# ---- parse_scores ----

@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            '{"format":0.9,"relevance":0.8,"completeness":0.7}',
            {
                "format": 0.9,
                "relevance": 0.8,
                "completeness": 0.7,
                "intent_correct": 0.0,
                "tool_correct": 0.0,
            },
        ),
        (
            '{"intent_correct":1.0,"tool_correct":0.5}',
            {
                "format": 0.0,
                "relevance": 0.0,
                "completeness": 0.0,
                "intent_correct": 1.0,
                "tool_correct": 0.5,
            },
        ),
        ("not json", {
            "format": 0.0,
            "relevance": 0.0,
            "completeness": 0.0,
            "intent_correct": 0.0,
            "tool_correct": 0.0,
        }),
        ("[1,2]", {
            "format": 0.0,
            "relevance": 0.0,
            "completeness": 0.0,
            "intent_correct": 0.0,
            "tool_correct": 0.0,
        }),
        ('{"format":"high"}', {
            "format": 0.0,
            "relevance": 0.0,
            "completeness": 0.0,
            "intent_correct": 0.0,
            "tool_correct": 0.0,
        }),
    ],
)
def test_parse_scores(content: str, expected: EvalScores) -> None:
    assert parse_scores(content) == expected


# ---- judge_report ----

async def test_judge_report() -> None:
    preset = LLMOutput(
        id="j-1",
        module="eval",
        type="eval",
        model="test-model",
        content='{"format":0.9}',
        token_usage={"input": 1, "output": 1},
        correlation_id="corr-9",
    )
    fake = _FakeClient(preset)
    result = await judge_report(cast(LlmClient, fake), "query text", "report text", "corr-9")
    assert result is preset
    call = fake.calls[0]
    assert call["module"] == "eval"
    assert call["output_type"] == "eval"
    assert call["json_mode"] is True
    assert call["correlation_id"] == "corr-9"
    prompt = call["messages"][0]["content"]
    assert "query text" in prompt
    assert "report text" in prompt


# ---- judge_tool_call ----

async def test_judge_tool_call() -> None:
    preset = LLMOutput(
        id="j-2",
        module="eval",
        type="eval",
        model="test-model",
        content='{"intent_correct":1.0}',
        token_usage={"input": 1, "output": 1},
        correlation_id="corr-9",
    )
    fake = _FakeClient(preset)
    tool_calls = [{"tool": "dge", "args": {"x": 1}}]
    result = await judge_tool_call(
        cast(LlmClient, fake), "query", "differential expression", tool_calls, "corr-9"
    )
    assert result is preset
    call = fake.calls[0]
    assert call["output_type"] == "eval"
    assert call["json_mode"] is True
    prompt = call["messages"][0]["content"]
    assert "differential expression" in prompt
    assert "dge" in prompt


# ---- evaluate_report ----

async def test_evaluate_report(monkeypatch: pytest.MonkeyPatch) -> None:
    judge_output = LLMOutput(
        id="j-3",
        module="eval",
        type="eval",
        model="test-model",
        content='{"format":0.9,"relevance":0.8,"completeness":0.7}',
        token_usage={"input": 11, "output": 4},
        correlation_id="corr-42",
    )
    output = LLMOutput(
        id="out-42",
        module="reporter",
        type="report",
        model="test-model",
        content="raw report",
        token_usage={"input": 5, "output": 9},
        correlation_id="corr-42",
    )

    async def fake_judge(
        client: LlmClient, query: str, report: str, correlation_id: str
    ) -> LLMOutput:
        return judge_output

    monkeypatch.setattr(evaluate, "judge_report", fake_judge)
    fake_db = _FakeDb()
    result = await evaluate_report(
        cast(LlmClient, _FakeClient(judge_output)),
        cast(Database, fake_db),
        output,
        "query",
        "the report",
    )
    assert result.type == "report"
    assert result.output_id == "out-42"
    assert result.scores == {
        "format": 0.9,
        "relevance": 0.8,
        "completeness": 0.7,
        "intent_correct": 0.0,
        "tool_correct": 0.0,
    }
    assert len(fake_db.conn.executed) == 1
    assert fake_db.conn.commits == 1
    sql, _params = fake_db.conn.executed[0]
    assert "INSERT INTO eval_report" in sql


# ---- evaluate_tool_call ----

async def test_evaluate_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    judge_output = LLMOutput(
        id="j-4",
        module="eval",
        type="eval",
        model="test-model",
        content='{"intent_correct":1.0,"tool_correct":0.5}',
        token_usage={"input": 5, "output": 2},
        correlation_id="corr-7",
    )
    output = LLMOutput(
        id="out-7",
        module="planner",
        type="plan",
        model="test-model",
        content="raw plan",
        token_usage={"input": 3, "output": 4},
        correlation_id="corr-7",
    )

    async def fake_judge(
        client: LlmClient,
        query: str,
        intent: str,
        tool_calls: list[dict[str, Any]],
        correlation_id: str,
    ) -> LLMOutput:
        return judge_output

    monkeypatch.setattr(evaluate, "judge_tool_call", fake_judge)
    fake_db = _FakeDb()
    result = await evaluate_tool_call(
        cast(LlmClient, _FakeClient(judge_output)),
        cast(Database, fake_db),
        output,
        "query",
        "intent",
        [{"tool": "dge"}],
    )
    assert result.type == "tool_call"
    assert result.output_id == "out-7"
    assert result.scores == {
        "format": 0.0,
        "relevance": 0.0,
        "completeness": 0.0,
        "intent_correct": 1.0,
        "tool_correct": 0.5,
    }
    assert len(fake_db.conn.executed) == 1
    assert fake_db.conn.commits == 1
