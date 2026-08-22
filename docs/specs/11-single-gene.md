# 单基因表达分析（Python）

> 范围：`bioagent/tools/single_gene/__init__.py`（空）+ `bioagent/tools/single_gene/expression.py`（导出 `TOOL`）。
> 一条 Python 工具 `single_gene_expression`：给定基因 + 表达矩阵 + 分组，算每组表达分布（mean/median/sd）+ 两组 t 检验。
> 纯工具 spec：只定义这一个工具与 `run` 执行体，不含编排、不含 API、不含 Facade。
> `ToolDefinition`/`Category`/`Runtime` 取自 01-types；`discover()` 自动发现取自 05-tools；`matrix_file` 的 `*_file` 解析取自 09-orchestration。

## 元信息

- **前置依赖**：01-types（`ToolDefinition`/`Category`/`Runtime`）、05-tools（`discover()` 自动发现）
- **无循环依赖**：本 spec 不 import 任何 `bioagent` 模块，只 import 第三方（pandas/scipy）；只被 `discover()` 被动发现

## 用户故事

> 作为生物信息分析者，我想要「丢一个基因名 + 分组，就知道它在各组里的表达分布和组间有没有差异」，以便看某个关键基因在不同条件下是否高/低表达。

## 验收标准

- [ ] `bioagent/tools/single_gene/expression.py` 导出 `TOOL`（`ToolDefinition`，`category==Category.SINGLE_GENE`、`runtime==Runtime.PYTHON`、`run` 非空、`r_script is None`），与「工具定义」段逐字一致
- [ ] `run(matrix_file, gene, groups)` 读 TSV 矩阵、按 `groups` 分组、算 `samples`（组→每样本值）+ `summary`（组→{n, mean, median, sd}）+ `p_value`（恰两组时 t 检验）
- [ ] 基因不在矩阵 → `ValueError`；组数非 2 → `p_value=None`（不报错）
- [ ] 输出所有数值是 Python 原生类型（numpy 标量已 `float()`/`.tolist()`，可 `json.dumps`）
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`bioagent/tools/single_gene/__init__.py`（空）、`bioagent/tools/single_gene/expression.py`
- **库**：`pandas`（读矩阵/统计）、`scipy`（`stats.ttest_ind`）；锁精确版本
- **矩阵格式约定（11-15 通用，本 spec 首次定义）**：TSV，行 = 基因（首列 = gene symbol，作 index），列 = 样本（首行 = 样本名）。`read_csv(..., sep="\t", index_col=0)`。
- **同步 pandas 读文件**：`run` 是 `async def`（满足 ToolDefinition.run 的 `Awaitable` 契约），但 pandas 读文件/统计是同步 CPU+磁盘，MVP 小矩阵直接同步做（不套 `asyncio.to_thread`）；矩阵变大再异步化，先不做。
- **`*_file` 解析在 executor**：`matrix_file` 填的是上传返回的 file_id；executor（09）已把它解析成绝对路径，`run` 收到的就是路径，直接 `read_csv`。工具自身不 import config、不碰 upload 表。
- **JSON 可序列化是硬约束**：executor 会把 `steps` 交给 reporter `json.dumps`，numpy `float64`/`int64` 会炸。故 `mean/median/std` 全 `float()`、每样本值 `.tolist()`。这是 11-15 所有 Python 工具的通用规则。

### `bioagent/tools/single_gene/expression.py`（完整）

```python
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
    row = df.loc[gene].astype(float)
    samples: dict[str, list[float]] = {}
    summary: dict[str, dict[str, Any]] = {}
    for group, cols in groups.items():
        vals = row[cols].tolist()
        samples[group] = vals
        summary[group] = {
            "n": len(vals),
            "mean": float(row[cols].mean()),
            "median": float(row[cols].median()),
            "sd": float(row[cols].std()),
        }
    p_value: float | None = None
    names = list(groups)
    if len(names) == 2:
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
```

## 测试要点

- [ ] 单元测试 `tests/test_tools_single_gene/`（`pytest-asyncio`，`tmp_path` 写临时 TSV 矩阵）：
  - [ ] `run` 成功：写 3 基因 × 6 样本矩阵、`groups={"case":["s1","s2","s3"],"control":["s4","s5","s6"]}` → 返回 `samples` 两组各 3 值、`summary` 两组各 {n=3, mean, median, sd}、`p_value` 是 float
  - [ ] `p_value` 非 None 且 ∈ [0,1]；`samples`/`summary` 的数值都是 Python `float`/`int`（`json.dumps(result)` 不抛）
  - [ ] 基因不存在 → `ValueError`（消息含基因名）
  - [ ] 组数非 2（给 3 组）→ `p_value is None`，但 `samples`/`summary` 仍返回
  - [ ] `TOOL` 形状：`category is Category.SINGLE_GENE`、`runtime is Runtime.PYTHON`、`run is not None`、`r_script is None`、`name == "single_gene_expression"`
- [ ] 集成测试：无（不触编排）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] `discover()` 自动发现该工具；`GET /tools` 里出现 `single_gene_expression`（category=single_gene、runtime=python）
