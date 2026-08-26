from pathlib import Path

from bioagent.enums import Category, Runtime
from bioagent.tools import ToolRegistry
from bioagent.tools.survival.km_cox import TOOL


_SCRIPT = Path(__file__).resolve().parents[2] / "bioagent" / "r_scripts" / "km_cox.R"


def _r_script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_tool_shape() -> None:
    assert TOOL.name == "km_cox"
    assert TOOL.category is Category.SURVIVAL
    assert TOOL.runtime is Runtime.R
    assert TOOL.r_script == "km_cox.R"
    assert TOOL.run is None


def test_register_contract() -> None:
    registry = ToolRegistry()
    registry.register(TOOL)  # 合法 R 工具，不抛
    assert registry.get("km_cox") is TOOL


def test_r_script_flow() -> None:
    script = _r_script()
    assert "Surv" in script
    assert "survfit" in script
    assert "survdiff" in script
    assert "coxph" in script
    assert "cat(jsonlite::toJSON(" in script


def test_r_script_column_defaults() -> None:
    script = _r_script()
    assert 'if (is.null(args$time_col)) "time" else args$time_col' in script
    assert 'if (is.null(args$event_col)) "event" else args$event_col' in script
    assert 'if (is.null(args$group_col)) "group" else args$group_col' in script


def test_r_script_strata_slicing() -> None:
    script = _r_script()
    assert "seq_along(fit$strata)" in script
    assert "fit$strata[i]" in script


def test_r_script_validation() -> None:
    script = _r_script()
    assert "%in% colnames(clin)" in script
    assert 'stop("临床表缺少列: "' in script
    assert "length(levels(group)) != 2" in script
    assert 'stop("group 需恰 2 组")' in script


def test_r_script_serialization() -> None:
    script = _r_script()
    assert "jsonlite::unbox" in script
    assert "levels(group)[i]" in script


def test_r_script_cox_guard() -> None:
    script = _r_script()
    assert "nrow(cox_sum)" in script
    assert '"Pr(>|z|)"' in script
