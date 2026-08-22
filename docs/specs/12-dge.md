# 差异表达分析（R limma）

> 范围：`backend/bioagent/tools/dge/__init__.py`（空）+ `backend/bioagent/tools/dge/limma_dge.py`（导出 `TOOL`）+ `backend/bioagent/r_scripts/limma_dge.R`。
> 一条 R 工具 `limma_dge`：表达矩阵 + case/control 样本列表 → limma 差异表（gene/logFC/p_value/adj_p_value，按 p 升序取 top 50）。
> 纯工具 spec：只定义这一个工具与 R 脚本，不含编排、不含 API、不含 Facade。
> `ToolDefinition`/`Category`/`Runtime` 取自 01-types；`RRunner` 执行取自 06-r-runner；`matrix_file` 的 `*_file` 解析取自 09-orchestration。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：01-types、06-r-runner（`RRunner` 执行本 spec 的 R 脚本，工具只声明 `r_script`）、05-tools（自动发现）
- **无循环依赖**：本 spec 不 import 任何 `bioagent` 模块（R 工具声明式，`run=None`）

## 用户故事

> 作为生物信息分析者，我想要「给表达矩阵 + case/control 两组样本，就能拿到每个基因的差异显著性表」，以便快速圈出上调/下调的关键基因。

## 验收标准

- [ ] `limma_dge.py` 导出 `TOOL`（`category==Category.DGE`、`runtime==Runtime.R`、`r_script=="limma_dge.R"`、`run is None`），与「工具定义」段逐字一致
- [ ] `limma_dge.R` 读 stdin JSON、`read.delim` 读矩阵、limma `lmFit→eBayes→topTable`、`cat(toJSON(...))` 输出，与「R 脚本」段逐字一致
- [ ] 输出 `{"genes": [{gene, logFC, p_value, adj_p_value}, ...]}`，按 p 升序、最多 50 条
- [ ] case/control 与矩阵列对齐（列缺失不崩溃——子集到存在的列）
- [ ] `pyright` strict 零报错（工具定义文件）

## 技术方案

- **新文件**：`backend/bioagent/tools/dge/__init__.py`（空）、`backend/bioagent/tools/dge/limma_dge.py`、`backend/bioagent/r_scripts/limma_dge.R`
- **R 依赖**：`limma`（Bioconductor）、`jsonlite`（读 stdin/写 stdout，镜像预装）；Docker 镜像装 `Bioconductor::limma` + `jsonlite`
- **R 工具 = 声明 + 脚本分离**：Python 文件只声明 `ToolDefinition`（`r_script="limma_dge.R"`、`run=None`），执行体在 `r_scripts/limma_dge.R`，由 executor 持 `RRunner` 跑（06-r-runner 契约：stdin 读 args JSON、stdout `cat(toJSON(...))`）
- **方向约定**：`group` factor levels 设 `c("control", "case")`，故 `coef=2`（`groupcase`）= case vs control，`logFC>0` 表示 case 高表达。写死在脚本里，不暴露给 LLM 去猜方向。
- **top 50**：`head(genes[order(p_value), ], 50)`——MVP 只回前 50，报告够用；全量差异表是「未请求的灵活性」，不做。

### `backend/bioagent/tools/dge/limma_dge.py`（完整）

```python
from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


TOOL = ToolDefinition(
    name="limma_dge",
    description="差异表达分析（limma）：表达矩阵 + case/control 样本列表 → 差异表（logFC/p/adj.P），按 p 升序 top 50",
    category=Category.DGE,
    runtime=Runtime.R,
    input_schema={
        "type": "object",
        "properties": {
            "matrix_file": {
                "type": "string",
                "description": "表达矩阵文件 ID（上传返回的 file_id；TSV，行=基因、列=样本）",
            },
            "case": {
                "type": "array",
                "items": {"type": "string"},
                "description": "case 组样本名列表",
            },
            "control": {
                "type": "array",
                "items": {"type": "string"},
                "description": "control 组样本名列表",
            },
        },
        "required": ["matrix_file", "case", "control"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "genes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "gene": {"type": "string"},
                        "logFC": {"type": "number"},
                        "p_value": {"type": "number"},
                        "adj_p_value": {"type": "number"},
                    },
                },
            },
        },
    },
    run=None,
    r_script="limma_dge.R",
    frontend={"result_type": "volcano"},
)
```

### `backend/bioagent/r_scripts/limma_dge.R`（完整）

```r
suppressMessages(library(limma))

args <- jsonlite::fromJSON(file("stdin"))

mat <- read.delim(args$matrix_file, row.names = 1, check.names = FALSE)

# 子集到存在的样本列，case/control 顺序与 levels 一致
case <- intersect(args$case, colnames(mat))
control <- intersect(args$control, colnames(mat))
mat <- mat[, c(control, case), drop = FALSE]

group <- factor(c(rep("control", length(control)), rep("case", length(case))),
                levels = c("control", "case"))
design <- model.matrix(~ group)
fit <- limma::lmFit(mat, design)
fit <- limma::eBayes(fit)
res <- limma::topTable(fit, coef = 2, number = Inf, sort.by = "p")

genes <- data.frame(
  gene = rownames(res),
  logFC = res$logFC,
  p_value = res$P.Value,
  adj_p_value = res$adj.P.Val,
  stringsAsFactors = FALSE
)
top <- utils::head(genes[order(genes$p_value), ], 50)

cat(jsonlite::toJSON(list(genes = top), auto_unbox = TRUE))
```

## 测试要点

- [ ] 单元测试 `tests/test_tools_dge/`：
  - [ ] `TOOL` 形状：`category is Category.DGE`、`runtime is Runtime.R`、`r_script == "limma_dge.R"`、`run is None`
  - [ ] `register()` 契约通过：该 TOOL 能通过 `ToolRegistry.register()`（`run=None` + `r_script` 非空 = 合法 R 工具）
  - [ ] R 脚本本身（`monkeypatch`/子进程 mock 不真跑 R）：断言脚本文本含 `fromJSON(file("stdin"))`、`lmFit`、`eBayes`、`topTable`、`cat(jsonlite::toJSON(...))`（字符串断言，验证 stdin/stdout 契约与 limma 流程）
- [ ] 集成测试：无（不真跑 Rscript，测试不依赖真实 R/limma 环境——与 06-r-runner 一致）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] `discover()` 自动发现该工具；planner 拿到 DGE 类别工具时，executor 用 `RRunner` 跑 `limma_dge.R` 且不再出现 subprocess 样板
