# 富集分析（R clusterProfiler）

> 范围：`backend/bioagent/tools/enrichment/__init__.py`（空）+ `backend/bioagent/tools/enrichment/go_kegg.py`（导出 `TOOL`）+ `backend/bioagent/r_scripts/go_kegg.R`。
> 一条 R 工具 `go_kegg`：基因列表（symbol）→ GO（BP）+ KEGG 富集表（各 top 20）。
> 纯工具 spec：只定义这一个工具与 R 脚本，不含编排、不含 API、不含 Facade。
> `ToolDefinition`/`Category`/`Runtime` 取自 01-types；`RRunner` 执行取自 06-r-runner。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：01-types、06-r-runner、05-tools（自动发现）
- **无循环依赖**：本 spec 只 import 纯类型/枚举叶子模块（`bioagent.enums`/`bioagent.types`，无回边），不 import 任何编排/执行模块（R 工具声明式，`run=None`）

## 用户故事

> 作为生物信息分析者，我想要「丢一个差异基因列表，就知道它们富集在哪些 GO 通路 / KEGG 通路上」，以便从基因列表跳到生物学机制。

## 验收标准

- [ ] `go_kegg.py` 导出 `TOOL`（`category==Category.ENRICHMENT`、`runtime==Runtime.R`、`r_script=="go_kegg.R"`、`run is None`），与「工具定义」段逐字一致
- [ ] `go_kegg.R` 读 stdin JSON、`enrichGO`（BP）+ `enrichKEGG`（tryCatch 包裹）、`cat(toJSON(...))` 输出，与「R 脚本」段逐字一致
- [ ] 输出 `{"go": [...], "kegg": [...]}`，各按 p 升序 top 20；KEGG 失败（无网/无映射）→ `kegg` 空数组，`go` 不受影响
- [ ] 空 `gene_list` → `stop`（非零退出，06-r-runner 转 `RRuntimeError`）
- [ ] `pyright` strict 零报错（工具定义文件）

## 技术方案

- **新文件**：`backend/bioagent/tools/enrichment/__init__.py`（空）、`backend/bioagent/tools/enrichment/go_kegg.py`、`backend/bioagent/r_scripts/go_kegg.R`
- **R 依赖**：`clusterProfiler`、`org.Hs.eg.db`（人类注释，Bioconductor）、`jsonlite`；镜像预装
- **人类-only（MVP）**：organism 写死 `hsa`、`OrgDb=org.Hs.eg.db`，不加 organism 参数。多物种 = 换 `org.*.eg.db` 包 + organism 码，是「未请求的灵活性」，不做。
- **GO 离线 / KEGG 联网**：`enrichGO`（org.Hs.eg.db）装包后离线可用，是核心路径；`enrichKEGG` 需运行时联网访问 KEGG、且要先 `bitr` symbol→ENTREZID，故用 `tryCatch` 包成 best-effort——失败返空数组，GO 照常出。这与 CLAUDE.md「best-effort 旁路」一致（KEGG 是增强、非主流程正确性所依赖）。
- **top 20**：GO/KEGG 各取 p 升序前 20，报告够用；全量富集表不做。

### `backend/bioagent/tools/enrichment/go_kegg.py`（完整）

```python
from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


TOOL = ToolDefinition(
    name="go_kegg",
    description="富集分析（clusterProfiler）：基因 symbol 列表 → GO(BP) + KEGG 富集表，各按 p 升序 top 20",
    category=Category.ENRICHMENT,
    runtime=Runtime.R,
    input_schema={
        "type": "object",
        "properties": {
            "gene_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "基因 symbol 列表（如差异基因）",
            },
        },
        "required": ["gene_list"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "go": {"type": "array"},   # [{id, term, p_value, adj_p_value, gene_count}]
            "kegg": {"type": "array"}, # 同结构；KEGG 失败为空
        },
    },
    run=None,
    r_script="go_kegg.R",
    frontend={"result_type": "barplot"},
)
```

### `backend/bioagent/r_scripts/go_kegg.R`（完整）

```r
suppressMessages(library(clusterProfiler))
suppressMessages(library(org.Hs.eg.db))

args <- jsonlite::fromJSON(file("stdin"))
genes <- args$gene_list
if (length(genes) == 0) {
  stop("gene_list 为空")
}

ego <- clusterProfiler::enrichGO(
  gene = genes,
  OrgDb = org.Hs.eg.db,
  keyType = "SYMBOL",
  ont = "BP",
  pvalueCutoff = 0.05,
  qvalueCutoff = 0.2
)
go <- ego@result[, c("ID", "Description", "pvalue", "p.adjust", "Count")]
colnames(go) <- c("id", "term", "p_value", "adj_p_value", "gene_count")
go <- go[order(go$p_value), ][seq_len(min(20, nrow(go))), ]

kegg <- tryCatch({
  mapped <- clusterProfiler::bitr(genes, fromType = "SYMBOL", toType = "ENTREZID", OrgDb = org.Hs.eg.db)
  ekegg <- clusterProfiler::enrichKEGG(gene = mapped$ENTREZID, organism = "hsa")
  k <- ekegg@result[, c("ID", "Description", "pvalue", "p.adjust", "Count")]
  colnames(k) <- c("id", "term", "p_value", "adj_p_value", "gene_count")
  k[order(k$p_value), ][seq_len(min(20, nrow(k))), ]
}, error = function(e) data.frame())

result <- list(go = go, kegg = kegg)
cat(jsonlite::toJSON(result, auto_unbox = TRUE))
```

## 测试要点

- [ ] 单元测试 `tests/test_tools_enrichment/`：
  - [ ] `TOOL` 形状：`category is Category.ENRICHMENT`、`runtime is Runtime.R`、`r_script == "go_kegg.R"`、`run is None`
  - [ ] `register()` 契约通过（合法 R 工具）
  - [ ] R 脚本（字符串断言，不真跑 R）：含 `enrichGO`、`keyType = "SYMBOL"`、`enrichKEGG`、`tryCatch`、`cat(jsonlite::toJSON(...))`、`if (length(genes) == 0)` + `stop(...)`
- [ ] 集成测试：无（不真跑 Rscript，与 06-r-runner 一致）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] `discover()` 自动发现该工具；planner 把「富集」意图映射到 ENRICHMENT 类别后能拿到 `go_kegg`
