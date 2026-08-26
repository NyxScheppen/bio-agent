from pathlib import Path

from bioagent.enums import Category, Runtime
from bioagent.tools import ToolRegistry
from bioagent.tools.enrichment.go_kegg import TOOL


_SCRIPT = Path(__file__).resolve().parents[2] / "bioagent" / "r_scripts" / "go_kegg.R"


def _r_script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_tool_shape() -> None:
    assert TOOL.name == "go_kegg"
    assert TOOL.category is Category.ENRICHMENT
    assert TOOL.runtime is Runtime.R
    assert TOOL.r_script == "go_kegg.R"
    assert TOOL.run is None


def test_register_contract() -> None:
    registry = ToolRegistry()
    registry.register(TOOL)  # 合法 R 工具，不抛
    assert registry.get("go_kegg") is TOOL


def test_r_script_contract() -> None:
    script = _r_script()
    assert "enrichGO" in script
    assert 'keyType = "SYMBOL"' in script
    assert "enrichKEGG" in script
    assert "tryCatch" in script
    assert "cat(jsonlite::toJSON(" in script


def test_r_script_empty_gene_list() -> None:
    script = _r_script()
    assert "if (length(genes) == 0)" in script
    assert 'stop("gene_list 为空")' in script
