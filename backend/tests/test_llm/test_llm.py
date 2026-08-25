import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

import bioagent.llm.client as client_mod
from bioagent.config import ConfigError, LlmConfig
from bioagent.db import Database
from bioagent.llm.client import LlmClient

# 测试要点要求直测纯函数；直接绑定私有函数（spec 04 测试要点明确列出）
_to_lc = client_mod._to_lc  # pyright: ignore[reportPrivateUsage]
_extract_usage = client_mod._extract_usage  # pyright: ignore[reportPrivateUsage]
_resolve_base_url = client_mod._resolve_base_url  # pyright: ignore[reportPrivateUsage]


# ---- _to_lc ----

def test_to_lc_system() -> None:
    msg = _to_lc({"role": "system", "content": "sys"})
    assert isinstance(msg, SystemMessage)
    assert msg.content == "sys"


def test_to_lc_user() -> None:
    msg = _to_lc({"role": "user", "content": "usr"})
    assert isinstance(msg, HumanMessage)
    assert msg.content == "usr"


def test_to_lc_assistant() -> None:
    msg = _to_lc({"role": "assistant", "content": "asst"})
    assert isinstance(msg, AIMessage)
    assert msg.content == "asst"


def test_to_lc_unknown_role_raises() -> None:
    with pytest.raises(ValueError):
        _to_lc(cast(Any, {"role": "bogus", "content": "x"}))


# ---- _extract_usage ----

def _fake_msg(usage_metadata: Any) -> BaseMessage:
    """绕过 AIMessage 对 usage_metadata 的 Pydantic 校验，注入任意形状。"""
    return cast(BaseMessage, SimpleNamespace(usage_metadata=usage_metadata))


class _Usage(BaseModel):
    input_tokens: int
    output_tokens: int


def test_extract_usage_dict_shape() -> None:
    assert _extract_usage(_fake_msg({"input_tokens": 12, "output_tokens": 7})) == {
        "input": 12,
        "output": 7,
    }


def test_extract_usage_pydantic_shape() -> None:
    assert _extract_usage(_fake_msg(_Usage(input_tokens=12, output_tokens=7))) == {
        "input": 12,
        "output": 7,
    }


def test_extract_usage_none() -> None:
    assert _extract_usage(_fake_msg(None)) == {"input": 0, "output": 0}


def test_extract_usage_none_values() -> None:
    assert _extract_usage(_fake_msg({"input_tokens": None, "output_tokens": None})) == {
        "input": 0,
        "output": 0,
    }


def test_extract_usage_non_numeric() -> None:
    assert _extract_usage(
        _fake_msg({"input_tokens": "abc", "output_tokens": "7"})
    ) == {"input": 0, "output": 7}


def test_extract_usage_unknown_shape() -> None:
    assert _extract_usage(_fake_msg("not-a-dict")) == {"input": 0, "output": 0}


# ---- _resolve_base_url ----

def test_resolve_base_url_explicit() -> None:
    assert _resolve_base_url("deepseek", "http://custom/v1") == "http://custom/v1"


def test_resolve_base_url_known_provider() -> None:
    assert _resolve_base_url("openai", None) == "https://api.openai.com/v1"


def test_resolve_base_url_unknown_provider() -> None:
    assert _resolve_base_url("claude", None) is None


# ---- complete（fake model + fake db）----

class _FakeConn:
    """记录 execute 参数 / commit 次数；fail=True 模拟记账失败。"""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.executes: list[tuple[str, tuple[Any, ...]]] = []
        self.commit_count = 0

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.executes.append((sql, params))

    async def commit(self) -> None:
        self.commit_count += 1


class _FakeDb:
    def __init__(self, fail: bool = False) -> None:
        self.conn = _FakeConn(fail=fail)
        self.lock = asyncio.Lock()


class _FakeModel:
    """ainvoke 返回预设响应（content + usage_metadata），记录消息与 kwargs。"""

    def __init__(self, content: Any, usage_metadata: Any = None) -> None:
        self._response = SimpleNamespace(content=content, usage_metadata=usage_metadata)
        self.calls: list[tuple[list[BaseMessage], dict[str, Any]]] = []

    async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> BaseMessage:
        self.calls.append((messages, kwargs))
        return cast(BaseMessage, self._response)


def _client(model: _FakeModel, db: _FakeDb, model_name: str = "test-model") -> LlmClient:
    return LlmClient(cast(BaseChatModel, model), model_name, cast(Database, db))


async def test_complete_fills_output_fields() -> None:
    model = _FakeModel(content="hello")
    out = await _client(model, _FakeDb()).complete(
        [{"role": "user", "content": "hi"}],
        module="planner",
        output_type="plan",
        correlation_id="corr-1",
    )
    assert out.id != ""
    assert out.module == "planner"
    assert out.type == "plan"
    assert out.correlation_id == "corr-1"
    assert out.content == "hello"
    assert out.model == "test-model"


async def test_complete_extracts_token_usage() -> None:
    model = _FakeModel(content="hi", usage_metadata={"input_tokens": 12, "output_tokens": 7})
    out = await _client(model, _FakeDb()).complete(
        [{"role": "user", "content": "hi"}], module="m", output_type="t", correlation_id="c"
    )
    assert out.token_usage == {"input": 12, "output": 7}


async def test_complete_missing_usage_counts_zero() -> None:
    model = _FakeModel(content="hi", usage_metadata=None)
    out = await _client(model, _FakeDb()).complete(
        [{"role": "user", "content": "hi"}], module="m", output_type="t", correlation_id="c"
    )
    assert out.token_usage == {"input": 0, "output": 0}


async def test_complete_json_mode_forwards_response_format() -> None:
    model = _FakeModel(content="{}")
    await _client(model, _FakeDb()).complete(
        [{"role": "user", "content": "json please"}],
        module="m",
        output_type="t",
        correlation_id="c",
        json_mode=True,
    )
    assert model.calls[0][1] == {"response_format": {"type": "json_object"}}


async def test_complete_no_json_mode_omits_response_format() -> None:
    model = _FakeModel(content="{}")
    await _client(model, _FakeDb()).complete(
        [{"role": "user", "content": "hi"}], module="m", output_type="t", correlation_id="c"
    )
    assert model.calls[0][1] == {}


async def test_complete_passes_messages_in_order() -> None:
    model = _FakeModel(content="hi")
    await _client(model, _FakeDb()).complete(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
        module="m",
        output_type="t",
        correlation_id="c",
    )
    lc_messages = model.calls[0][0]
    assert [type(m).__name__ for m in lc_messages] == ["SystemMessage", "HumanMessage"]
    assert [m.content for m in lc_messages] == ["sys", "usr"]


async def test_complete_non_text_content_raises() -> None:
    model = _FakeModel(content=["a", "b"])
    with pytest.raises(RuntimeError):
        await _client(model, _FakeDb()).complete(
            [{"role": "user", "content": "hi"}], module="m", output_type="t", correlation_id="c"
        )


async def test_complete_writes_token_usage_row() -> None:
    db = _FakeDb()
    model = _FakeModel(content="hi", usage_metadata={"input_tokens": 12, "output_tokens": 7})
    out = await _client(model, db).complete(
        [{"role": "user", "content": "hi"}],
        module="planner",
        output_type="plan",
        correlation_id="corr-1",
    )
    assert len(db.conn.executes) == 1
    sql, params = db.conn.executes[0]
    assert "INSERT INTO token_usage" in sql
    assert params[0] == out.id
    assert params[1] == "corr-1"
    assert params[2] == "planner"
    assert params[3] == "plan"
    assert params[4] == "test-model"
    assert params[5] == 12
    assert params[6] == 7
    assert isinstance(params[7], float)
    assert db.conn.commit_count == 1


async def test_complete_accounting_failure_is_best_effort() -> None:
    model = _FakeModel(content="hi")
    out = await _client(model, _FakeDb(fail=True)).complete(
        [{"role": "user", "content": "hi"}], module="m", output_type="t", correlation_id="c"
    )
    assert out.content == "hi"


# ---- from_config ----

def test_from_config_unknown_provider_raises() -> None:
    with pytest.raises(ConfigError):
        LlmClient.from_config(LlmConfig(provider="claude"), cast(Database, _FakeDb()))


def test_from_config_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        LlmClient.from_config(LlmConfig(provider="deepseek"), cast(Database, _FakeDb()))


def test_from_config_ollama_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = LlmClient.from_config(LlmConfig(provider="ollama"), cast(Database, _FakeDb()))
    assert isinstance(client, LlmClient)


def test_from_config_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    client = LlmClient.from_config(
        LlmConfig(provider="deepseek", model="deepseek-chat"), cast(Database, _FakeDb())
    )
    assert isinstance(client, LlmClient)
    assert client._model_name == "deepseek-chat"  # pyright: ignore[reportPrivateUsage]


def test_from_config_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    client = LlmClient.from_config(LlmConfig(provider="openai"), cast(Database, _FakeDb()))
    assert isinstance(client, LlmClient)


def test_from_config_custom_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    client = LlmClient.from_config(
        LlmConfig(provider="deepseek", base_url="http://custom/v1"), cast(Database, _FakeDb())
    )
    assert isinstance(client, LlmClient)
