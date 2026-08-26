import json
from pathlib import Path

import pytest

from bioagent.enums import Category, Runtime
from bioagent.tools.single_gene.expression import TOOL, run


_MATRIX = [
    "gene\ts1\ts2\ts3\ts4\ts5\ts6",
    "g1\t1\t2\t3\t4\t5\t6",
    "g2\t10\t20\t30\t40\t50\t60",
    "g3\t1.5\t2.5\t3.5\t4.5\t5.5\t6.5",
]


def _write_matrix(tmp_path: Path) -> str:
    path = tmp_path / "matrix.tsv"
    path.write_text("\n".join(_MATRIX) + "\n", encoding="utf-8")
    return str(path)


async def test_run_success(tmp_path: Path) -> None:
    matrix = _write_matrix(tmp_path)
    result = await run(matrix, "g1", {"case": ["s1", "s2", "s3"], "control": ["s4", "s5", "s6"]})
    assert result["gene"] == "g1"
    assert result["samples"] == {"case": [1.0, 2.0, 3.0], "control": [4.0, 5.0, 6.0]}
    assert result["summary"]["case"] == {"n": 3, "mean": 2.0, "median": 2.0, "sd": 1.0}
    assert result["summary"]["control"] == {"n": 3, "mean": 5.0, "median": 5.0, "sd": 1.0}
    assert isinstance(result["p_value"], float) and 0.0 <= result["p_value"] <= 1.0


async def test_run_json_serializable(tmp_path: Path) -> None:
    matrix = _write_matrix(tmp_path)
    result = await run(matrix, "g1", {"case": ["s1", "s2", "s3"], "control": ["s4", "s5", "s6"]})
    json.dumps(result)  # 不抛即通过（samples/summary/p_value 均为 Python float/int/None）
    assert isinstance(result["samples"]["case"][0], float)
    assert isinstance(result["summary"]["case"]["n"], int)
    assert isinstance(result["summary"]["case"]["sd"], float)


async def test_run_gene_not_found(tmp_path: Path) -> None:
    matrix = _write_matrix(tmp_path)
    with pytest.raises(ValueError, match="gX"):
        await run(matrix, "gX", {"case": ["s1", "s2"], "control": ["s3", "s4"]})


async def test_run_sample_not_found(tmp_path: Path) -> None:
    matrix = _write_matrix(tmp_path)
    with pytest.raises(ValueError, match="sX"):
        await run(matrix, "g1", {"case": ["s1", "sX"], "control": ["s3", "s4"]})


async def test_run_empty_group(tmp_path: Path) -> None:
    matrix = _write_matrix(tmp_path)
    with pytest.raises(ValueError, match="case"):
        await run(matrix, "g1", {"case": [], "control": ["s1", "s2"]})


async def test_run_single_sample_group(tmp_path: Path) -> None:
    matrix = _write_matrix(tmp_path)
    result = await run(matrix, "g1", {"case": ["s1"], "control": ["s2", "s3"]})
    assert result["summary"]["case"]["sd"] is None
    assert result["p_value"] is None
    json.dumps(result)  # sd=None / p_value=None 可序列化


async def test_run_three_groups(tmp_path: Path) -> None:
    matrix = _write_matrix(tmp_path)
    result = await run(
        matrix, "g1", {"a": ["s1", "s2"], "b": ["s3", "s4"], "c": ["s5", "s6"]}
    )
    assert result["p_value"] is None
    assert set(result["samples"]) == {"a", "b", "c"}
    assert set(result["summary"]) == {"a", "b", "c"}


def test_tool_shape() -> None:
    assert TOOL.name == "single_gene_expression"
    assert TOOL.category is Category.SINGLE_GENE
    assert TOOL.runtime is Runtime.PYTHON
    assert TOOL.run is not None
    assert TOOL.r_script is None
