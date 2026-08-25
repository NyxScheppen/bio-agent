from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from bioagent.enums import Category, Runtime
from bioagent.tools import ToolRegistry
from bioagent.types import ToolDefinition


async def _noop(**kwargs: Any) -> dict[str, Any]:
    return {}


def _tool(
    name: str = "t",
    *,
    category: Category = Category.SINGLE_GENE,
    runtime: Runtime = Runtime.PYTHON,
    run: Callable[..., Awaitable[dict[str, Any]]] | None = _noop,
    r_script: str | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="test tool",
        category=category,
        runtime=runtime,
        input_schema={},
        output_schema={},
        run=run,
        r_script=r_script,
    )


# ---- register / get ----

def test_register_then_get() -> None:
    reg = ToolRegistry()
    tool = _tool(name="t1")
    reg.register(tool)
    assert reg.get("t1") is tool


def test_get_missing_raises_keyerror() -> None:
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_register_duplicate_raises() -> None:
    reg = ToolRegistry()
    reg.register(_tool(name="t1"))
    with pytest.raises(ValueError):
        reg.register(_tool(name="t1"))


# ---- register runtime 契约 ----

def test_register_r_without_script_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ValueError):
        reg.register(_tool(name="r1", runtime=Runtime.R, run=None, r_script=None))


def test_register_r_empty_script_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ValueError):
        reg.register(_tool(name="r2", runtime=Runtime.R, run=None, r_script=""))


def test_register_r_with_run_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ValueError):
        reg.register(_tool(name="r3", runtime=Runtime.R, run=_noop, r_script="x.R"))


def test_register_python_without_run_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ValueError):
        reg.register(_tool(name="p1", runtime=Runtime.PYTHON, run=None, r_script=None))


def test_register_python_with_script_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ValueError):
        reg.register(_tool(name="p2", runtime=Runtime.PYTHON, run=_noop, r_script="x.R"))


def test_register_compliant_python() -> None:
    reg = ToolRegistry()
    reg.register(_tool(name="p3", runtime=Runtime.PYTHON, run=_noop, r_script=None))
    assert reg.get("p3").runtime is Runtime.PYTHON


def test_register_compliant_r() -> None:
    reg = ToolRegistry()
    reg.register(_tool(name="r4", runtime=Runtime.R, run=None, r_script="x.R"))
    assert reg.get("r4").runtime is Runtime.R


# ---- for_categories ----

def test_for_categories_filters() -> None:
    reg = ToolRegistry()
    reg.register(_tool(name="a", category=Category.SINGLE_GENE))
    reg.register(_tool(name="b", category=Category.DGE))
    reg.register(_tool(name="c", category=Category.DGE))
    assert sorted(t.name for t in reg.for_categories({Category.DGE})) == ["b", "c"]


def test_for_categories_empty_returns_empty() -> None:
    reg = ToolRegistry()
    reg.register(_tool(name="a", category=Category.DGE))
    assert reg.for_categories(set()) == []


# ---- all_tools / __iter__ / __len__ ----

def test_collection_protocol() -> None:
    reg = ToolRegistry()
    for name in ("a", "b", "c"):
        reg.register(_tool(name=name))
    assert len(reg) == 3
    assert len(reg.all_tools()) == 3
    assert sum(1 for _ in reg) == 3


# ---- discover（fixture 包）----

def test_discover_registers_only_tool_exports() -> None:
    reg = ToolRegistry()
    reg.discover("tests.fixtures.fake_tools")
    assert len(reg) == 1
    assert reg.get("dge_foo").category is Category.DGE


def test_discover_non_idempotent() -> None:
    reg = ToolRegistry()
    reg.discover("tests.fixtures.fake_tools")
    with pytest.raises(ValueError):
        reg.discover("tests.fixtures.fake_tools")  # 第二次撞同名 → ValueError
