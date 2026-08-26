from pathlib import Path

from bioagent.enums import Category, Runtime
from bioagent.tools import ToolRegistry
from bioagent.tools.dge.limma_dge import TOOL


_SCRIPT = Path(__file__).resolve().parents[2] / "bioagent" / "r_scripts" / "limma_dge.R"


def _r_script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_tool_shape() -> None:
    assert TOOL.name == "limma_dge"
    assert TOOL.category is Category.DGE
    assert TOOL.runtime is Runtime.R
    assert TOOL.r_script == "limma_dge.R"
    assert TOOL.run is None


def test_register_contract() -> None:
    registry = ToolRegistry()
    registry.register(TOOL)  # run=None + r_script 非空 = 合法 R 工具，不抛
    assert registry.get("limma_dge") is TOOL


def test_r_script_stdin_stdout_contract() -> None:
    script = _r_script()
    assert 'fromJSON(file("stdin"))' in script
    assert "lmFit" in script
    assert "eBayes" in script
    assert "topTable" in script
    assert "cat(jsonlite::toJSON(" in script


def test_r_script_alignment_floor() -> None:
    script = _r_script()
    assert "length(case) < 2 || length(control) < 2" in script
    assert 'stop("case/control 与矩阵对齐后样本不足")' in script


def test_r_script_sample_validation() -> None:
    script = _r_script()
    assert "setdiff(c(args$case, args$control), colnames(mat))" in script
    assert 'stop("样本不在矩阵中: "' in script
