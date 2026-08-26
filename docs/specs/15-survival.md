# 生存分析（R survival）

> 范围：`backend/bioagent/tools/survival/__init__.py`（空）+ `backend/bioagent/tools/survival/km_cox.py`（导出 `TOOL`）+ `backend/bioagent/r_scripts/km_cox.R`。
> 一条 R 工具 `km_cox`：临床表（样本 × 生存时间/状态/分组）→ KM 曲线数据 + log-rank p + Cox HR。
> 纯工具 spec：只定义这一个工具与 R 脚本，不含编排、不含 API、不含 Facade。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：01-types、06-r-runner、05-tools（自动发现）
- **无循环依赖**：本 spec 只 import 纯类型/枚举叶子模块（`bioagent.enums`/`bioagent.types`，无回边），不 import 任何编排/执行模块（R 工具声明式，`run=None`）

## 用户故事

> 作为生物信息分析者，我想要「给一张临床表，就能拿到分组间的生存曲线（KM）与风险比（Cox）」，以便比较不同组（如高低表达组）的预后差异。

## 验收标准

- [ ] `km_cox.py` 导出 `TOOL`（`category==Category.SURVIVAL`、`runtime==Runtime.R`、`r_script=="km_cox.R"`、`run is None`），与「工具定义」段逐字一致
- [ ] `km_cox.R` 读 stdin JSON、读临床表、`survfit`（KM）+ `survdiff`（log-rank）+ `coxph`（Cox）、`cat(toJSON(...))` 输出，与「R 脚本」段逐字一致
- [ ] 输出 `{"km_curves": [{group, time, survival}], "logrank_p", "cox_hr", "cox_p"}`
- [ ] 临床表缺列（time/event/group 任一不存在）或 group 非恰 2 组 → `stop`（非零退出，06-r-runner 转 `RRuntimeError`）
- [ ] `pyright` strict 零报错（工具定义文件）

## 技术方案

- **新文件**：`backend/bioagent/tools/survival/__init__.py`（空）、`backend/bioagent/tools/survival/km_cox.py`、`backend/bioagent/r_scripts/km_cox.R`
- **R 依赖**：`survival`（`survfit`/`survdiff`/`coxph`）、`jsonlite`；镜像预装
- **临床表格式**：TSV，行 = 样本、列含 `time`（生存时间）/`event`（事件 1/删失 0）/`group`（分组）。列名由 `time_col`/`event_col`/`group_col` 参数指定（默认 `time`/`event`/`group`）。
- **独立的临床表输入**：生存分析需要临床表，**不在**「表达矩阵 + 分组」主输入里（那是 11/12 的输入）。用户对生存分析需单独上传一张临床表，`clinical_file` 走 `*_file` 解析（09）。这是第 15 号 spec 的独立数据来源。
- **KM 曲线数据（survfit 拼接解析）**：`survfit` 的 `time`/`surv` 跨 strata 拼接，`strata` 给出每层样本数，脚本按 `strata` 切片还原每组曲线——这是本 R 脚本最易写错的点，见下方代码与测试的字符串断言。
- **Cox HR 方向**：`coxph(surv ~ group)` 的系数参照 `group` factor 第一水平（`factor()` 默认字母序），故 `cox_hr` 恒为「字母序第二组 vs 第一组」，`>1` 表示第二组风险更高。与 11 的显式 control/case 不同，此处无 case 概念，按字母序约定即可。
- **cox p 守卫**：`summary(cox)$coefficients` 取 `[1, "Pr(>|z|)"]`（按列名而非魔数下标），并在 `nrow` < 1 时回退 `NA`，避免某组全删失导致下标越界。

### `backend/bioagent/tools/survival/km_cox.py`（完整）

```python
from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


TOOL = ToolDefinition(
    name="km_cox",
    description="生存分析（KM + Cox）：临床表 → 分组 KM 曲线数据 + log-rank p + Cox 风险比",
    category=Category.SURVIVAL,
    runtime=Runtime.R,
    input_schema={
        "type": "object",
        "properties": {
            "clinical_file": {
                "type": "string",
                "description": "临床表文件 ID（上传返回的 file_id；TSV，行=样本，含时间/事件/分组列）",
            },
            "time_col": {"type": "string", "description": "生存时间列名（默认 time）"},
            "event_col": {"type": "string", "description": "事件列名，1=事件/0=删失（默认 event）"},
            "group_col": {"type": "string", "description": "分组列名（默认 group）"},
        },
        "required": ["clinical_file"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "km_curves": {"type": "array"},  # [{group, time[], survival[]}]
            "logrank_p": {"type": "number"},
            "cox_hr": {"type": "number"},
            "cox_p": {"type": "number"},
        },
    },
    run=None,
    r_script="km_cox.R",
    frontend={"result_type": "km_curve"},
)
```

### `backend/bioagent/r_scripts/km_cox.R`（完整）

```r
suppressMessages(library(survival))

args <- jsonlite::fromJSON(file("stdin"))
time_col <- if (is.null(args$time_col)) "time" else args$time_col
event_col <- if (is.null(args$event_col)) "event" else args$event_col
group_col <- if (is.null(args$group_col)) "group" else args$group_col

clin <- read.delim(args$clinical_file, row.names = 1, check.names = FALSE)
for (col in c(time_col, event_col, group_col)) {
  if (!(col %in% colnames(clin))) {
    stop("临床表缺少列: ", col)
  }
}
time <- as.numeric(clin[[time_col]])
event <- as.numeric(clin[[event_col]])
group <- factor(clin[[group_col]])
if (length(levels(group)) != 2) {
  stop("group 需恰 2 组")
}

surv_obj <- survival::Surv(time, event)
fit <- survival::survfit(surv_obj ~ group)

# survfit 的 time/surv 跨 strata 拼接，strata 给出每层样本数 → 按层切片
idx <- 0
km_curves <- list()
for (i in seq_along(fit$strata)) {
  n <- fit$strata[i]
  sel <- (idx + 1):(idx + n)
  km_curves[[i]] <- list(
    group = jsonlite::unbox(levels(group)[i]),
    time = as.numeric(fit$time[sel]),
    survival = as.numeric(fit$surv[sel])
  )
  idx <- idx + n
}

lr <- survival::survdiff(surv_obj ~ group)
logrank_p <- 1 - stats::pchisq(lr$chisq, df = length(levels(group)) - 1)

cox <- survival::coxph(surv_obj ~ group)
cox_hr <- as.numeric(exp(stats::coef(cox)))
# Cox HR 参照组 = factor 第一水平（字母序更小者）：HR = 第二组 vs 第一组，>1 表示第二组风险更高
cox_sum <- summary(cox)$coefficients
cox_p <- as.numeric(if (nrow(cox_sum) >= 1) cox_sum[1, "Pr(>|z|)"] else NA)

result <- list(
  km_curves = km_curves,
  logrank_p = jsonlite::unbox(logrank_p),
  cox_hr = jsonlite::unbox(cox_hr),
  cox_p = jsonlite::unbox(cox_p)
)
cat(jsonlite::toJSON(result))
```

## 测试要点

- [ ] 单元测试 `tests/test_tools_survival/`：
  - [ ] `TOOL` 形状：`category is Category.SURVIVAL`、`runtime is Runtime.R`、`r_script == "km_cox.R"`、`run is None`
  - [ ] `register()` 契约通过（合法 R 工具）
  - [ ] R 脚本（字符串断言，不真跑 R）：含 `Surv`、`survfit`、`survdiff`、`coxph`、`strata` 切片、`cat(jsonlite::toJSON(...))`；断言 `time_col/event_col/group_col` 的默认值回退逻辑存在
  - [ ] R 脚本校验：含 `%in% colnames(clin)` 缺列 `stop`、`length(levels(group)) != 2` 二组 `stop`（字符串断言；退化输入非零退出）
  - [ ] R 脚本序列化：含 `jsonlite::unbox`（logrank_p/cox_hr/cox_p/group 单点）、`levels(group)[i]`（group 名去 `group=` 前缀）（字符串断言；时间/生存保持数组、标量显式 unbox）
  - [ ] R 脚本 cox 守卫：含 `nrow(cox_sum)` 守卫、`"Pr(>|z|)"` 列名取 p（字符串断言；某组全删失不越界）
- [ ] 集成测试：无（不真跑 Rscript，与 06-r-runner 一致）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] `discover()` 自动发现该工具；planner 把「生存」意图映射到 SURVIVAL 类别后能拿到 `km_cox`；`clinical_file` 走 executor 的 `*_file` 解析
