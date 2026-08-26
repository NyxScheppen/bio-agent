# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false
from typing import Any

import pandas as pd
from scipy import stats

from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


async def run(matrix_file: str, gene: str, groups: dict[str, list[str]]) -> dict[str, Any]:
    """单基因表达分析：每组分布 + 两组 t 检验。groups = 组名 → 样本名列表。"""
    df = pd.read_csv(matrix_file, sep="\t", index_col=0)
    if gene not in df.index:
        raise ValueError(f"基因 {gene} 不在表达矩阵中")
    all_samples = [s for cols in groups.values() for s in cols]
    missing = set(all_samples) - set(df.columns)
    if missing:
        raise ValueError(f"样本 {missing} 不在矩阵中")
    row = df.loc[gene].astype(float)
    samples: dict[str, list[float]] = {}
    summary: dict[str, dict[str, Any]] = {}
    for group, cols in groups.items():
        if not cols:
            raise ValueError(f"组 {group} 无样本")
        vals = row[cols].tolist()
        samples[group] = vals
        summary[group] = {
            "n": len(vals),
            "mean": float(row[cols].mean()),
            "median": float(row[cols].median()),
            "sd": None if len(vals) < 2 else float(row[cols].std()),
        }
    p_value: float | None = None
    names = list(groups)
    if len(names) == 2 and all(len(samples[n]) >= 2 for n in names):
        p_value = float(stats.ttest_ind(samples[names[0]], samples[names[1]]).pvalue)
    return {"gene": gene, "samples": samples, "summary": summary, "p_value": p_value}


TOOL = ToolDefinition(
    name="single_gene_expression",
    description="单基因表达分析：给定基因与分组，算每组表达分布（n/mean/median/sd）与组间 t 检验 p 值",
    category=Category.SINGLE_GENE,
    runtime=Runtime.PYTHON,
    input_schema={
        "type": "object",
        "properties": {
            "matrix_file": {
                "type": "string",
                "description": "表达矩阵文件 ID（上传返回的 file_id；TSV，行=基因、列=样本）",
            },
            "gene": {"type": "string", "description": "基因 symbol"},
            "groups": {
                "type": "object",
                "description": "分组：组名 → 样本名列表，如 {\"case\": [\"s1\",\"s2\"], \"control\": [\"s3\",\"s4\"]}",
            },
        },
        "required": ["matrix_file", "gene", "groups"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "gene": {"type": "string"},
            "samples": {"type": "object"},  # 组名 → 该组每样本表达值列表
            "summary": {"type": "object"},  # 组名 → {n, mean, median, sd}
            "p_value": {"type": ["number", "null"]},  # 恰两组时 t 检验 p 值
        },
    },
    run=run,
    frontend={"result_type": "boxplot"},
)
