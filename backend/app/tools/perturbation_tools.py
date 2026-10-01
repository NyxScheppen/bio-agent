from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis, r_escape_string_content


_SCALING_PARAMETERS = {
    "type": "object",
    "properties": {
        "expression_file": {
            "type": "string",
            "description": "表达矩阵 CSV，第一列或明确列名为 gene，其余列为样本",
        },
        "gene": {"type": "string", "description": "要缩放的目标基因"},
        "scaling_ratio": {
            "type": "number",
            "description": "表达降低比例，0-1；0.8 表示仅将目标基因行缩放为原值的 20%",
            "default": 0.8,
        },
    },
    "required": ["expression_file", "gene"],
}


def _run_expression_scaling(
    expression_file: str,
    gene: str,
    scaling_ratio: float,
    job_dir: str | None,
):
    ratio = float(scaling_ratio)
    if not 0 <= ratio <= 1:
        raise ValueError("scaling_ratio must be between 0 and 1")
    expression_file = r_escape_string_content(expression_file)
    gene = r_escape_string_content(gene)

    r_code = f'''
library(data.table)

expr <- fread(smart_read("{expression_file}"), data.table = FALSE)
if (!("gene" %in% colnames(expr))) stop("Expression matrix must contain a gene column")
if (anyDuplicated(expr$gene)) stop("Expression matrix contains duplicate gene identifiers")

rownames(expr) <- expr$gene
expr$gene <- NULL
expr_mat <- suppressWarnings(as.matrix(expr))
mode(expr_mat) <- "numeric"
if (any(!is.finite(expr_mat))) stop("Expression matrix contains non-numeric, NA, or infinite values")
if (!("{gene}" %in% rownames(expr_mat))) stop("Target gene was not found")

original <- expr_mat["{gene}", ]
scaled <- original * (1 - {ratio})
expr_mat["{gene}", ] <- scaled

before_after <- data.frame(
  sample = colnames(expr_mat),
  before = as.numeric(original),
  after = as.numeric(scaled)
)
write.csv(before_after, "expression_scaling_before_after.csv", row.names = FALSE)

out_df <- data.frame(gene = rownames(expr_mat), expr_mat, check.names = FALSE)
write.csv(out_df, "expression_scaling_matrix.csv", row.names = FALSE)

mean_before <- mean(original)
mean_after <- mean(scaled)
summary_df <- data.frame(
  scenario = "target-row expression scaling only",
  target_gene = "{gene}",
  scaling_ratio = {ratio},
  mean_before = mean_before,
  mean_after = mean_after,
  fold_change = ifelse(mean_before == 0, NA, mean_after / mean_before),
  predicts_downstream_response = FALSE,
  scientific_limit = "No regulatory network or downstream genes are inferred; this is not a knockout prediction.",
  stringsAsFactors = FALSE
)
write.csv(summary_df, "expression_scaling_summary.csv", row.names = FALSE)

cat("Generated: expression_scaling_before_after.csv, expression_scaling_matrix.csv, expression_scaling_summary.csv\\n")
'''
    return run_r_analysis(
        r_code,
        timeout=1200,
        job_subdir="expression_scaling",
        job_dir=job_dir,
    )


@register_tool(
    name="run_expression_scaling_scenario",
    description=(
        "将表达矩阵中一个目标基因的整行按固定比例缩放，输出前后矩阵。"
        "这是数值情景分析，不预测下游响应，也不等同于真实基因敲低或敲除。"
    ),
    category="perturbation",
    tags=["expression-scaling", "scenario", "non-predictive"],
    task_types=["perturbation_scenario"],
    timeout=1200,
    max_memory_mb=4096,
    parameters=_SCALING_PARAMETERS,
)
def run_expression_scaling_scenario(
    expression_file: str,
    gene: str,
    scaling_ratio: float = 0.8,
    job_dir: str = None,
):
    return _run_expression_scaling(expression_file, gene, scaling_ratio, job_dir)


@register_tool(
    name="run_virtual_knockdown_bulk_analysis",
    description=(
        "兼容旧调用：仅缩放目标基因表达行，不预测任何下游响应。"
        "新任务应优先使用 run_expression_scaling_scenario。"
    ),
    category="perturbation",
    tags=["legacy", "expression-scaling", "non-predictive"],
    task_types=["perturbation_scenario"],
    timeout=1200,
    max_memory_mb=4096,
    parameters={
        "type": "object",
        "properties": {
            "expression_file": _SCALING_PARAMETERS["properties"]["expression_file"],
            "gene": _SCALING_PARAMETERS["properties"]["gene"],
            "knockdown_ratio": {
                "type": "number",
                "description": "兼容参数；实际语义为目标表达行的降低比例",
                "default": 0.8,
            },
        },
        "required": ["expression_file", "gene"],
    },
)
def run_virtual_knockdown_bulk_analysis(
    expression_file: str,
    gene: str,
    knockdown_ratio: float = 0.8,
    job_dir: str = None,
):
    return _run_expression_scaling(expression_file, gene, knockdown_ratio, job_dir)


@register_tool(
    name="run_observed_perturbation_response_analysis",
    description=(
        "基于真实 control 与 perturbed 样本的表达矩阵和元数据执行差异响应分析。"
        "raw_count 使用 DESeq2，continuous 使用 limma；该工具描述观测关联，不进行虚拟扰动预测。"
    ),
    category="perturbation",
    tags=["observed-response", "deseq2", "limma", "differential-expression"],
    task_types=["perturbation_response"],
    timeout=3600,
    max_memory_mb=8192,
    parameters={
        "type": "object",
        "properties": {
            "expression_file": {
                "type": "string",
                "description": "CSV 表达矩阵，必须含 gene 列，其余列为样本",
            },
            "metadata_file": {
                "type": "string",
                "description": "CSV 样本元数据，包含样本列和条件列",
            },
            "sample_col": {"type": "string", "default": "sample"},
            "condition_col": {"type": "string", "default": "condition"},
            "control_group": {"type": "string", "description": "对照组标签"},
            "treatment_group": {"type": "string", "description": "真实扰动组标签"},
            "data_type": {
                "type": "string",
                "enum": ["raw_count", "continuous"],
                "default": "continuous",
            },
            "expression_preprocess": {
                "type": "string",
                "enum": ["auto", "log2", "non_log2", "none"],
                "default": "auto",
                "description": "仅用于 continuous；auto 会记录并应用保守的 log2(x+1) 启发式判断",
            },
            "target_gene": {
                "type": "string",
                "description": "可选，仅用于在结果摘要中报告该基因的真实观测变化",
            },
            "padj_threshold": {"type": "number", "default": 0.05},
            "abs_log2fc_threshold": {"type": "number", "default": 1.0},
        },
        "required": [
            "expression_file",
            "metadata_file",
            "control_group",
            "treatment_group",
        ],
    },
)
def run_observed_perturbation_response_analysis(
    expression_file: str,
    metadata_file: str,
    control_group: str,
    treatment_group: str,
    sample_col: str = "sample",
    condition_col: str = "condition",
    data_type: str = "continuous",
    expression_preprocess: str = "auto",
    target_gene: str = "",
    padj_threshold: float = 0.05,
    abs_log2fc_threshold: float = 1.0,
    job_dir: str = None,
):
    data_type = str(data_type or "continuous").strip().lower()
    expression_preprocess = str(expression_preprocess or "auto").strip().lower()
    if data_type not in {"raw_count", "continuous"}:
        raise ValueError("data_type must be raw_count or continuous")
    if expression_preprocess not in {"auto", "log2", "non_log2", "none"}:
        raise ValueError("expression_preprocess must be auto, log2, non_log2, or none")
    padj_threshold = float(padj_threshold)
    abs_log2fc_threshold = float(abs_log2fc_threshold)
    if not 0 < padj_threshold <= 1:
        raise ValueError("padj_threshold must be in (0, 1]")
    if abs_log2fc_threshold < 0:
        raise ValueError("abs_log2fc_threshold must be non-negative")
    if str(control_group) == str(treatment_group):
        raise ValueError("control_group and treatment_group must be different")

    values = {
        "expression_file": expression_file,
        "metadata_file": metadata_file,
        "control_group": control_group,
        "treatment_group": treatment_group,
        "sample_col": sample_col,
        "condition_col": condition_col,
        "target_gene": target_gene,
        "data_type": data_type,
        "expression_preprocess": expression_preprocess,
    }
    escaped = {key: r_escape_string_content(value) for key, value in values.items()}

    r_code = f'''
library(data.table)
library(ggplot2)

expr <- fread(smart_read("{escaped['expression_file']}"), data.table = FALSE)
meta <- fread(smart_read("{escaped['metadata_file']}"), data.table = FALSE)
sample_col <- "{escaped['sample_col']}"
condition_col <- "{escaped['condition_col']}"
control_group <- "{escaped['control_group']}"
treatment_group <- "{escaped['treatment_group']}"
target_gene <- "{escaped['target_gene']}"
data_type <- "{escaped['data_type']}"
preprocess_request <- "{escaped['expression_preprocess']}"

if (!("gene" %in% colnames(expr))) stop("Expression matrix must contain a gene column")
if (anyDuplicated(expr$gene)) stop("Expression matrix contains duplicate gene identifiers")
if (!(sample_col %in% colnames(meta))) stop("metadata is missing sample_col")
if (!(condition_col %in% colnames(meta))) stop("metadata is missing condition_col")
if (anyDuplicated(meta[[sample_col]])) stop("metadata sample identifiers must be unique")

meta <- meta[meta[[condition_col]] %in% c(control_group, treatment_group), , drop = FALSE]
meta[[sample_col]] <- as.character(meta[[sample_col]])
missing_samples <- setdiff(meta[[sample_col]], colnames(expr))
if (length(missing_samples) > 0) stop("Metadata samples missing from expression matrix: ", paste(missing_samples, collapse = ", "))
group_counts <- table(meta[[condition_col]])
if (!(control_group %in% names(group_counts)) || !(treatment_group %in% names(group_counts))) stop("Both groups must be present in metadata")
if (group_counts[[control_group]] < 2 || group_counts[[treatment_group]] < 2) stop("Each group needs at least 2 biological samples")

rownames(expr) <- expr$gene
expr$gene <- NULL
samples <- meta[[sample_col]]
mat <- suppressWarnings(as.matrix(expr[, samples, drop = FALSE]))
mode(mat) <- "numeric"
if (any(!is.finite(mat))) stop("Expression matrix contains non-numeric, NA, or infinite values")
if (nzchar(target_gene) && !(target_gene %in% rownames(mat))) stop("target_gene was not found")

group <- factor(meta[[condition_col]], levels = c(control_group, treatment_group))
preprocess_applied <- "none"
if (data_type == "raw_count") {{
  if (any(mat < 0) || any(abs(mat - round(mat)) > 1e-8)) stop("raw_count data must contain non-negative integers")
  library(DESeq2)
  dds <- DESeqDataSetFromMatrix(
    countData = round(mat),
    colData = data.frame(group = group, row.names = samples),
    design = ~ group
  )
  keep <- rowSums(counts(dds) >= 10) >= 2
  if (sum(keep) < 2) stop("Too few genes pass the raw-count filter")
  dds <- dds[keep, ]
  dispersion_method <- "standard fitted dispersion trend"
  dds <- tryCatch(
    DESeq(dds, quiet = TRUE),
    error = function(e) {{
      message_text <- conditionMessage(e)
      if (!grepl("all gene-wise dispersion estimates are within", message_text, fixed = TRUE)) stop(e)
      fallback <- estimateSizeFactors(dds)
      fallback <- estimateDispersionsGeneEst(fallback, quiet = TRUE)
      dispersions(fallback) <- mcols(fallback)$dispGeneEst
      dispersion_method <<- "gene-wise dispersion fallback (no fitted trend)"
      nbinomWaldTest(fallback, quiet = TRUE)
    }}
  )
  de <- as.data.frame(results(dds, contrast = c("group", treatment_group, control_group)))
  de$gene <- rownames(de)
  result <- data.frame(
    gene = de$gene,
    log2FoldChange = de$log2FoldChange,
    statistic = de$stat,
    pvalue = de$pvalue,
    padj = de$padj,
    baseMean = de$baseMean,
    stringsAsFactors = FALSE
  )
  plot_matrix <- log2(counts(dds, normalized = TRUE) + 1)
  preprocess_applied <- "DESeq2 size-factor normalization; log2 normalized counts for heatmap only"
  method <- paste("DESeq2;", dispersion_method)
}} else {{
  if (preprocess_request == "non_log2") {{
    if (any(mat < 0)) stop("non_log2 preprocessing requires non-negative values")
    mat <- log2(mat + 1)
    preprocess_applied <- "log2(x+1) requested"
  }} else if (preprocess_request == "auto") {{
    q99 <- as.numeric(quantile(mat, 0.99, na.rm = TRUE))
    if (all(mat >= 0) && q99 > 50) {{
      mat <- log2(mat + 1)
      preprocess_applied <- "log2(x+1) by auto heuristic (99th percentile > 50)"
    }} else {{
      preprocess_applied <- "none by auto heuristic"
    }}
  }} else if (preprocess_request == "log2") {{
    preprocess_applied <- "none; input declared log2"
  }} else {{
    preprocess_applied <- "none requested"
  }}
  library(limma)
  design <- model.matrix(~ group)
  fit <- eBayes(lmFit(mat, design))
  de <- topTable(fit, coef = 2, number = Inf, sort.by = "P")
  de$gene <- rownames(de)
  result <- data.frame(
    gene = de$gene,
    log2FoldChange = de$logFC,
    statistic = de$t,
    pvalue = de$P.Value,
    padj = de$adj.P.Val,
    baseMean = de$AveExpr,
    stringsAsFactors = FALSE
  )
  plot_matrix <- mat
  method <- "limma"
}}

result <- result[order(result$padj, result$pvalue), , drop = FALSE]
result$significance <- ifelse(
  !is.na(result$padj) & result$padj <= {padj_threshold} & abs(result$log2FoldChange) >= {abs_log2fc_threshold},
  ifelse(result$log2FoldChange > 0, "up", "down"),
  "not_significant"
)
write.csv(result, "observed_perturbation_de_results.csv", row.names = FALSE)
write.csv(result[result$significance == "up", , drop = FALSE], "observed_perturbation_up_genes.csv", row.names = FALSE)
write.csv(result[result$significance == "down", , drop = FALSE], "observed_perturbation_down_genes.csv", row.names = FALSE)

plot_df <- result
plot_df$minus_log10_padj <- -log10(pmax(plot_df$padj, .Machine$double.xmin))
png("observed_perturbation_volcano.png", width = 1200, height = 900, res = 150)
print(ggplot(plot_df, aes(x = log2FoldChange, y = minus_log10_padj, color = significance)) +
  geom_point(alpha = 0.65, size = 1.4, na.rm = TRUE) +
  scale_color_manual(values = c(down = "#2b6cb0", not_significant = "#8a8a8a", up = "#c53030")) +
  geom_vline(xintercept = c(-{abs_log2fc_threshold}, {abs_log2fc_threshold}), linetype = 2) +
  geom_hline(yintercept = -log10({padj_threshold}), linetype = 2) +
  theme_minimal() + labs(title = paste(treatment_group, "vs", control_group), color = "Response"))
dev.off()

top_genes <- head(result$gene[is.finite(result$padj)], 50)
top_genes <- intersect(top_genes, rownames(plot_matrix))
if (length(top_genes) >= 2) {{
  library(pheatmap)
  annotation <- data.frame(condition = group, row.names = samples)
  png("observed_perturbation_heatmap.png", width = 1300, height = 1100, res = 150)
  pheatmap(plot_matrix[top_genes, , drop = FALSE], scale = "row", annotation_col = annotation, show_rownames = length(top_genes) <= 50)
  dev.off()
}}

target_row <- if (nzchar(target_gene)) result[result$gene == target_gene, , drop = FALSE] else data.frame()
summary_df <- data.frame(
  method = method,
  interpretation = "observed association between real sample groups; not a virtual perturbation prediction",
  control_group = control_group,
  treatment_group = treatment_group,
  control_samples = as.integer(group_counts[[control_group]]),
  treatment_samples = as.integer(group_counts[[treatment_group]]),
  tested_genes = nrow(result),
  significant_up = sum(result$significance == "up", na.rm = TRUE),
  significant_down = sum(result$significance == "down", na.rm = TRUE),
  target_gene = target_gene,
  target_log2fc = if (nrow(target_row)) target_row$log2FoldChange[1] else NA,
  target_padj = if (nrow(target_row)) target_row$padj[1] else NA,
  preprocess_applied = preprocess_applied,
  stringsAsFactors = FALSE
)
write.csv(summary_df, "observed_perturbation_summary.csv", row.names = FALSE)
write.csv(
  data.frame(package = c("data.table", "ggplot2", method), version = c(
    as.character(packageVersion("data.table")),
    as.character(packageVersion("ggplot2")),
    as.character(packageVersion(if (startsWith(method, "DESeq2")) "DESeq2" else method))
  )),
  "observed_perturbation_software_versions.csv",
  row.names = FALSE
)

cat("Generated: observed_perturbation_de_results.csv, observed_perturbation_up_genes.csv, observed_perturbation_down_genes.csv, observed_perturbation_volcano.png, observed_perturbation_heatmap.png, observed_perturbation_summary.csv, observed_perturbation_software_versions.csv\\n")
'''
    return run_r_analysis(
        r_code,
        timeout=3600,
        job_subdir="observed_perturbation",
        job_dir=job_dir,
    )
