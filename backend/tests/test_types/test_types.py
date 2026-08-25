from typing import Any, get_type_hints

from bioagent.enums import Category, Runtime
from bioagent.types import EvalScores, TokenUsageDict, ToolDefinition


async def async_fn() -> dict[str, Any]:
    return {}


def test_python_tool_keeps_category() -> None:
    td = ToolDefinition("", "", Category.DGE, Runtime.PYTHON, {}, {}, async_fn)
    assert td.category is Category.DGE


def test_r_tool_shape() -> None:
    td = ToolDefinition("", "", Category.SURVIVAL, Runtime.R, {}, {}, None, "km.R")
    assert td.r_script == "km.R"
    assert td.run is None


def test_frontend_default_factory_isolated() -> None:
    a = ToolDefinition("", "", Category.DGE, Runtime.PYTHON, {}, {}, async_fn)
    b = ToolDefinition("", "", Category.DGE, Runtime.PYTHON, {}, {}, async_fn)
    a.frontend["result_type"] = "bar"
    assert b.frontend == {}
    assert a.frontend == {"result_type": "bar"}


def test_typeddict_keys() -> None:
    assert set(get_type_hints(EvalScores)) == {
        "format",
        "relevance",
        "completeness",
        "intent_correct",
        "tool_correct",
    }
    assert set(get_type_hints(TokenUsageDict)) == {"input", "output"}
