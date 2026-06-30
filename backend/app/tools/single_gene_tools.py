from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis
from app.tools.r_preprocess_templates import (
    build_single_value_preprocess_r,
    build_matrix_preprocess_r,
)

@register_tool(
    name="run_single_gene_clinical_association_analysis",
    description="分析目标基因与临床分组变量的关系，输出箱线图和统计结果。输入文件需包含目标基因列和临床变量列。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "CSV文件路径"},
            "gene": {"type": "string", "description": "目标基因列名"},
            "clinical_col": {"type": "string", "description": "临床变量列名，如 stage、grade、sex"},
            "plot_type": {
                "type": "string",
                "description": "图类型，boxplot 或 violin",
                "default": "boxplot"
            },
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["file_path", "gene", "clinical_col"]
    }
)
def run_single_gene_clinical_association_analysis(
    file_path: str,
    gene: str,
    clinical_col: str,
    plot_type: str = "boxplot",
    expression_preprocess: str = "auto"
):
    geom_code = """
geom_boxplot(outlier.shape = NA, alpha = 0.7)
""" if plot_type.lower() != "violin" else """
geom_violin(alpha = 0.7, trim = FALSE)
"""

    preprocess_r = build_single_value_preprocess_r(expression_preprocess)

    r_code = f'''
library(data.table)
library(ggplot2)

{preprocess_r}

df <- fread(smart_read("{file_path}"), data.table = FALSE)

if (!("{gene}" %in% colnames(df))) stop("找不到目标基因列")
if (!("{clinical_col}" %in% colnames(df))) stop("找不到临床变量列")

prep <- auto_preprocess_vector(df[["{gene}"]], expression_preprocess_mode)
df[["{gene}"]] <- prep$x
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df <- df[!is.na(df[["{gene}"]]) & !is.na(df[["{clinical_col}"]]), ]
if (nrow(df) < 5) stop("有效样本太少")

df[["{clinical_col}"]] <- as.factor(df[["{clinical_col}"]])

if (length(levels(df[["{clinical_col}"]])) < 2) stop("临床变量分组不足，至少需要两组")

stat_method <- if (length(levels(df[["{clinical_col}"]])) == 2) "wilcox.test" else "kruskal.test"

p <- ggplot(df, aes(x = .data[["{clinical_col}"]], y = .data[["{gene}"]], fill = .data[["{clinical_col}"]])) +
  {geom_code}
  geom_jitter(width = 0.15, size = 1.8) +
  theme_bw() +
  labs(
    title = paste("{gene}", "vs", "{clinical_col}"),
    x = "{clinical_col}",
    y = "{gene} expression"
  )

ggsave("single_gene_clinical_association.png", p, width = 7, height = 5, dpi = 150)

summary_df <- aggregate(df[["{gene}"]], by = list(group = df[["{clinical_col}"]]),
                        FUN = function(x) c(n = length(x), mean = mean(x), median = median(x), sd = sd(x)))
summary_out <- data.frame(
  group = summary_df$group,
  n = sapply(summary_df$x, function(v) v[1]),
  mean = sapply(summary_df$x, function(v) v[2]),
  median = sapply(summary_df$x, function(v) v[3]),
  sd = sapply(summary_df$x, function(v) v[4])
)
write.csv(summary_out, "single_gene_clinical_summary.csv", row.names = FALSE)

if (stat_method == "wilcox.test") {{
  stat_res <- wilcox.test(df[["{gene}"]] ~ df[["{clinical_col}"]])
  stat_df <- data.frame(
    method = "wilcox.test",
    pvalue = stat_res$p.value
  )
}} else {{
  stat_res <- kruskal.test(df[["{gene}"]] ~ df[["{clinical_col}"]])
  stat_df <- data.frame(
    method = "kruskal.test",
    pvalue = stat_res$p.value
  )
}}

write.csv(stat_df, "single_gene_clinical_stats.csv", row.names = FALSE)

cat("生成文件: preprocess_log2_info.csv, single_gene_clinical_association.png, single_gene_clinical_summary.csv, single_gene_clinical_stats.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="single_gene_clinical")


@register_tool(
    name="run_single_gene_roc_analysis",
    description="对单基因进行二分类 ROC 分析。输入文件需包含目标基因列和标签列。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "CSV文件路径"},
            "gene": {"type": "string", "description": "目标基因列名"},
            "label_col": {"type": "string", "description": "标签列名，必须为二分类"},
            "positive_class": {
                "type": "string",
                "description": "阳性类别名称；为空则默认取因子第二类",
                "default": ""
            },
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["file_path", "gene", "label_col"]
    }
)
def run_single_gene_roc_analysis(
    file_path: str,
    gene: str,
    label_col: str,
    positive_class: str = "",
    expression_preprocess: str = "auto"
):
    pos_expr = f'"{positive_class}"' if positive_class else 'NULL'
    preprocess_r = build_single_value_preprocess_r(expression_preprocess)

    r_code = f'''
library(data.table)
library(pROC)

{preprocess_r}

df <- fread(smart_read("{file_path}"), data.table = FALSE)

if (!("{gene}" %in% colnames(df))) stop("找不到目标基因列")
if (!("{label_col}" %in% colnames(df))) stop("找不到标签列")

prep <- auto_preprocess_vector(df[["{gene}"]], expression_preprocess_mode)
df[["{gene}"]] <- prep$x
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df <- df[!is.na(df[["{gene}"]]) & !is.na(df[["{label_col}"]]), ]
if (nrow(df) < 10) stop("有效样本太少")

df[["{label_col}"]] <- as.factor(df[["{label_col}"]])
if (length(levels(df[["{label_col}"]])) != 2) stop("当前仅支持二分类 ROC")

positive_class <- {pos_expr}
if (is.null(positive_class) || positive_class == "") {{
  positive_class <- levels(df[["{label_col}"]])[2]
}}

roc_obj <- roc(
  response = df[["{label_col}"]],
  predictor = df[["{gene}"]],
  levels = levels(df[["{label_col}"]]),
  direction = "<"
)

auc_val <- as.numeric(auc(roc_obj))
coords_df <- coords(roc_obj, x = "best", ret = c("threshold", "sensitivity", "specificity"))
coords_df <- as.data.frame(coords_df)

png("single_gene_roc_curve.png", width = 1200, height = 900, res = 150)
plot(roc_obj, col = "#2E86DE", lwd = 3, main = paste("ROC Curve -", "{gene}"))
legend("bottomright", legend = paste("AUC =", round(auc_val, 4)), bty = "n")
dev.off()

metrics_df <- data.frame(
  gene = "{gene}",
  label_col = "{label_col}",
  positive_class = positive_class,
  auc = auc_val
)
write.csv(metrics_df, "single_gene_roc_metrics.csv", row.names = FALSE)
write.csv(coords_df, "single_gene_roc_best_cutoff.csv", row.names = FALSE)

cat("生成文件: preprocess_log2_info.csv, single_gene_roc_curve.png, single_gene_roc_metrics.csv, single_gene_roc_best_cutoff.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="single_gene_roc")


@register_tool(
    name="run_single_gene_expression_analysis",
    description="在 bulk 表达矩阵中分析单个基因在不同分组中的表达差异，输出箱线图和汇总表。",
    parameters={
        "type": "object",
        "properties": {
            "expression_file": {"type": "string", "description": "表达矩阵CSV文件，第一列为gene"},
            "group_file": {"type": "string", "description": "样本分组CSV文件，包含 sample 和 group"},
            "gene": {"type": "string", "description": "目标基因名"},
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["expression_file", "group_file", "gene"]
    }
)
def run_single_gene_expression_analysis(
    expression_file: str,
    group_file: str,
    gene: str,
    expression_preprocess: str = "auto"
):
    preprocess_r = build_single_value_preprocess_r(expression_preprocess)

    r_code = f'''
library(data.table)
library(ggplot2)

{preprocess_r}

smart_read <- function(fp) {{
  full_path <- fp
  if (!file.exists(full_path)) full_path <- file.path(UPLOAD_DIR, fp)
  if (!file.exists(full_path)) stop(paste("文件不存在:", fp))
  fread(full_path, data.table = FALSE)
}}

expr <- smart_read("{expression_file}")
grp <- smart_read("{group_file}")

if (!("gene" %in% colnames(expr))) stop("表达矩阵必须包含 gene 列")
if (!all(c("sample", "group") %in% colnames(grp))) stop("分组文件必须包含 sample 和 group 列")

target <- expr[expr$gene == "{gene}", , drop = FALSE]
if (nrow(target) == 0) stop("找不到目标基因")

rownames(target) <- target$gene
target$gene <- NULL

samples <- intersect(colnames(target), grp$sample)
if (length(samples) < 2) stop("样本匹配不足")

target_values <- as.numeric(target[1, samples])
prep <- auto_preprocess_vector(target_values, expression_preprocess_mode)
target_values <- prep$x
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

val_df <- data.frame(
  sample = samples,
  expression = as.numeric(target_values),
  stringsAsFactors = FALSE
)
val_df <- merge(val_df, grp, by = "sample")

write.csv(val_df, "single_gene_expression_values.csv", row.names = FALSE)

p <- ggplot(val_df, aes(x = group, y = expression, fill = group)) +
  geom_boxplot(outlier.shape = NA, alpha = 0.7) +
  geom_jitter(width = 0.15, size = 2) +
  theme_bw() +
  labs(title = paste("Expression of", "{gene}"), x = "Group", y = "Expression")

ggsave("single_gene_expression_boxplot.png", p, width = 7, height = 5, dpi = 150)

cat("生成文件: preprocess_log2_info.csv, single_gene_expression_values.csv, single_gene_expression_boxplot.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="single_gene_expression")


@register_tool(
    name="run_expression_correlation_analysis",
    description="在表达矩阵中计算目标基因与其他基因的相关性，输出相关基因表和前20相关基因柱状图。",
    parameters={
        "type": "object",
        "properties": {
            "expression_file": {"type": "string", "description": "表达矩阵CSV文件，第一列为gene"},
            "gene": {"type": "string", "description": "目标基因名"},
            "expression_preprocess": {
                "type": "string",
                "description": "表达矩阵预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["expression_file", "gene"]
    }
)
def run_expression_correlation_analysis(
    expression_file: str,
    gene: str,
    expression_preprocess: str = "auto"
):
    preprocess_r = build_matrix_preprocess_r(expression_preprocess)

    r_code = f'''
library(data.table)
library(ggplot2)

{preprocess_r}

smart_read <- function(fp) {{
  full_path <- fp
  if (!file.exists(full_path)) full_path <- file.path(UPLOAD_DIR, fp)
  if (!file.exists(full_path)) stop(paste("文件不存在:", fp))
  fread(full_path, data.table = FALSE)
}}

expr <- smart_read("{expression_file}")
if (!("gene" %in% colnames(expr))) stop("表达矩阵必须包含 gene 列")

rownames(expr) <- expr$gene
expr$gene <- NULL
expr_mat <- as.matrix(expr)
mode(expr_mat) <- "numeric"

prep <- auto_preprocess_matrix(expr_mat, expression_preprocess_mode)
expr_mat <- prep$mat
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

if (!("{gene}" %in% rownames(expr_mat))) stop("找不到目标基因")

target <- as.numeric(expr_mat["{gene}", ])
cors <- apply(expr_mat, 1, function(x) cor(target, as.numeric(x), use = "pairwise.complete.obs", method = "pearson"))

res <- data.frame(gene = names(cors), correlation = as.numeric(cors))
res <- res[!is.na(res$correlation), ]
res <- res[res$gene != "{gene}", ]
res <- res[order(-abs(res$correlation)), ]
write.csv(res, "gene_correlation_results.csv", row.names = FALSE)

plot_df <- head(res, 20)
plot_df$gene <- factor(plot_df$gene, levels = rev(plot_df$gene))

p <- ggplot(plot_df, aes(x = gene, y = correlation, fill = correlation > 0)) +
  geom_col() +
  coord_flip() +
  theme_bw() +
  labs(title = paste("Top correlated genes with", "{gene}"), x = "", y = "Correlation")

ggsave("gene_correlation_top20.png", p, width = 8, height = 6, dpi = 150)

cat("生成文件: preprocess_log2_info.csv, gene_correlation_results.csv, gene_correlation_top20.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="gene_correlation")