from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis

@register_tool(
    name="run_bulk_rnaseq_deg_analysis",
    description="对 bulk RNA-seq 表达矩阵进行差异表达分析，生成差异表达结果表、火山图、热图和 PCA 图。适合已标准化表达矩阵或近似连续表达矩阵。",
    parameters={
        "type": "object",
        "properties": {
            "expression_file": {
                "type": "string",
                "description": "表达矩阵CSV文件，第一列为gene，后续列为样本"
            },
            "group_file": {
                "type": "string",
                "description": "样本分组CSV文件，包含 sample 和 group 两列"
            },
            "control_group": {
                "type": "string",
                "description": "对照组名称"
            },
            "treatment_group": {
                "type": "string",
                "description": "实验组名称"
            }
        },
        "required": ["expression_file", "group_file", "control_group", "treatment_group"]
    },
    racing_group="deg_analysis",
)
def run_bulk_rnaseq_deg_analysis(expression_file: str, group_file: str, control_group: str, treatment_group: str):
    r_code = f'''
library(data.table)
library(limma)
library(ggplot2)
library(pheatmap)

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

rownames(expr) <- expr$gene
expr$gene <- NULL
expr_mat <- as.matrix(expr)
mode(expr_mat) <- "numeric"

common_samples <- intersect(colnames(expr_mat), grp$sample)
if (length(common_samples) < 2) stop("表达矩阵和分组文件没有足够重叠样本")

expr_mat <- expr_mat[, common_samples, drop = FALSE]
grp <- grp[match(common_samples, grp$sample), , drop = FALSE]

grp <- grp[grp$group %in% c("{control_group}", "{treatment_group}"), ]
expr_mat <- expr_mat[, grp$sample, drop = FALSE]

if (ncol(expr_mat) < 4) stop("样本数太少，建议至少4个样本")

group_factor <- factor(grp$group, levels = c("{control_group}", "{treatment_group}"))
design <- model.matrix(~ 0 + group_factor)
colnames(design) <- levels(group_factor)

fit <- lmFit(expr_mat, design)
contrast.matrix <- makeContrasts(contrasts = paste0("{treatment_group}", "-", "{control_group}"), levels = design)
fit2 <- contrasts.fit(fit, contrast.matrix)
fit2 <- eBayes(fit2)

deg <- topTable(fit2, number = Inf, adjust.method = "BH")
deg$gene <- rownames(deg)
deg <- deg[, c("gene", setdiff(colnames(deg), "gene"))]
write.csv(deg, "bulk_deg_results.csv", row.names = FALSE)

deg$significance <- "NS"
deg$significance[deg$adj.P.Val < 0.05 & deg$logFC > 1] <- "Up"
deg$significance[deg$adj.P.Val < 0.05 & deg$logFC < -1] <- "Down"

p1 <- ggplot(deg, aes(x = logFC, y = -log10(adj.P.Val), color = significance)) +
  geom_point(alpha = 0.7, size = 1.5) +
  scale_color_manual(values = c("Up" = "#E74C3C", "Down" = "#2E86DE", "NS" = "grey70")) +
  theme_bw() +
  labs(title = "Volcano Plot")

ggsave("bulk_volcano.png", p1, width = 8, height = 6, dpi = 150)

top_genes <- head(deg$gene[order(deg$adj.P.Val)], 30)
heat_mat <- expr_mat[top_genes, , drop = FALSE]
png("bulk_heatmap.png", width = 1200, height = 1000, res = 150)
pheatmap(heat_mat, scale = "row", annotation_col = data.frame(Group = grp$group, row.names = grp$sample))
dev.off()

pca <- prcomp(t(expr_mat), scale. = TRUE)
pca_df <- data.frame(
  sample = rownames(pca$x),
  PC1 = pca$x[,1],
  PC2 = pca$x[,2],
  group = grp$group
)
p2 <- ggplot(pca_df, aes(x = PC1, y = PC2, color = group, label = sample)) +
  geom_point(size = 3) +
  theme_bw() +
  labs(title = "PCA Plot")

ggsave("bulk_pca.png", p2, width = 8, height = 6, dpi = 150)

cat("生成文件: bulk_deg_results.csv, bulk_volcano.png, bulk_heatmap.png, bulk_pca.png\\n")
'''
    return run_r_analysis(r_code)


@register_tool(
    name="run_deseq2_count_deg_analysis",
    description="对 RNA-seq 原始 count 矩阵执行 DESeq2 差异分析，输出结果表、火山图、标准化矩阵和热图。",
    parameters={
        "type": "object",
        "properties": {
            "count_file": {"type": "string", "description": "原始count矩阵CSV文件，第一列为gene"},
            "group_file": {"type": "string", "description": "样本分组CSV文件，包含 sample 和 group 两列"},
            "control_group": {"type": "string", "description": "对照组名称"},
            "treatment_group": {"type": "string", "description": "实验组名称"}
        },
        "required": ["count_file", "group_file", "control_group", "treatment_group"]
    },
    racing_group="deg_analysis",
)
def run_deseq2_count_deg_analysis(count_file: str, group_file: str, control_group: str, treatment_group: str):
    r_code = f'''
library(data.table)
library(DESeq2)
library(ggplot2)
library(pheatmap)

count_df <- fread(smart_read("{count_file}"), data.table = FALSE)
group_df <- fread(smart_read("{group_file}"), data.table = FALSE)

if (!("gene" %in% colnames(count_df))) stop("count_file 必须包含 gene 列")
if (!all(c("sample", "group") %in% colnames(group_df))) stop("group_file 必须包含 sample 和 group 列")

rownames(count_df) <- count_df$gene
count_df$gene <- NULL

count_mat <- as.matrix(count_df)
mode(count_mat) <- "numeric"

common_samples <- intersect(colnames(count_mat), group_df$sample)
if (length(common_samples) < 4) stop("重叠样本太少")

count_mat <- count_mat[, common_samples, drop = FALSE]
group_df <- group_df[match(common_samples, group_df$sample), , drop = FALSE]
group_df <- group_df[group_df$group %in% c("{control_group}", "{treatment_group}"), , drop = FALSE]
count_mat <- count_mat[, group_df$sample, drop = FALSE]

group_df$group <- factor(group_df$group, levels = c("{control_group}", "{treatment_group}"))

dds <- DESeqDataSetFromMatrix(
  countData = round(count_mat),
  colData = group_df,
  design = ~ group
)

dds <- dds[rowSums(counts(dds)) > 1, ]
dds <- DESeq(dds)

res <- results(dds, contrast = c("group", "{treatment_group}", "{control_group}"))
res_df <- as.data.frame(res)
res_df$gene <- rownames(res_df)
res_df <- res_df[, c("gene", setdiff(colnames(res_df), "gene"))]
write.csv(res_df, "deseq2_deg_results.csv", row.names = FALSE)

norm_mat <- counts(dds, normalized = TRUE)
norm_df <- data.frame(gene = rownames(norm_mat), norm_mat, check.names = FALSE)
write.csv(norm_df, "deseq2_normalized_counts.csv", row.names = FALSE)

plot_df <- res_df
plot_df$significance <- "NS"
plot_df$significance[!is.na(plot_df$padj) & plot_df$padj < 0.05 & plot_df$log2FoldChange > 1] <- "Up"
plot_df$significance[!is.na(plot_df$padj) & plot_df$padj < 0.05 & plot_df$log2FoldChange < -1] <- "Down"

p <- ggplot(plot_df, aes(x = log2FoldChange, y = -log10(padj), color = significance)) +
  geom_point(alpha = 0.7, size = 1.5) +
  scale_color_manual(values = c("Up" = "#E74C3C", "Down" = "#2E86DE", "NS" = "grey70")) +
  theme_bw() +
  labs(title = "DESeq2 Volcano Plot")

ggsave("deseq2_volcano.png", p, width = 8, height = 6, dpi = 150)

vsd <- vst(dds, blind = TRUE)
top_genes <- head(rownames(res[order(res$padj), ]), 30)
top_genes <- top_genes[!is.na(top_genes)]

if (length(top_genes) > 1) {{
  png("deseq2_heatmap.png", width = 1200, height = 1000, res = 150)
  pheatmap(
    assay(vsd)[top_genes, , drop = FALSE],
    scale = "row",
    annotation_col = data.frame(Group = group_df$group, row.names = group_df$sample)
  )
  dev.off()
}}

cat("生成文件: deseq2_deg_results.csv, deseq2_normalized_counts.csv, deseq2_volcano.png, deseq2_heatmap.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="deseq2_deg")

@register_tool(
    name="run_bulk_pca_analysis",
    description="对 bulk 表达矩阵执行 PCA 分析，输出 PCA 坐标表和散点图。",
    parameters={
        "type": "object",
        "properties": {
            "expression_file": {"type": "string", "description": "表达矩阵CSV文件，第一列为gene"},
            "group_file": {"type": "string", "description": "可选，样本分组CSV文件，包含 sample 和 group 两列"}
        },
        "required": ["expression_file"]
    }
)
def run_bulk_pca_analysis(expression_file: str, group_file: str = ""):
    group_read_code = f'grp <- fread(smart_read("{group_file}"), data.table = FALSE)' if group_file else 'grp <- NULL'

    r_code = f'''
library(data.table)
library(ggplot2)

expr <- fread(smart_read("{expression_file}"), data.table = FALSE)
if (!("gene" %in% colnames(expr))) stop("表达矩阵必须包含 gene 列")

rownames(expr) <- expr$gene
expr$gene <- NULL
expr_mat <- as.matrix(expr)
mode(expr_mat) <- "numeric"

{group_read_code}

pca <- prcomp(t(expr_mat), scale. = TRUE)
pca_df <- data.frame(
  sample = rownames(pca$x),
  PC1 = pca$x[,1],
  PC2 = pca$x[,2],
  stringsAsFactors = FALSE
)

if (!is.null(grp)) {{
  if (!all(c("sample", "group") %in% colnames(grp))) stop("group_file 必须包含 sample 和 group 两列")
  pca_df <- merge(pca_df, grp, by = "sample", all.x = TRUE)
}} else {{
  pca_df$group <- "All"
}}

var_explained <- summary(pca)$importance[2, ]
var_df <- data.frame(
  PC = names(var_explained),
  variance_explained = as.numeric(var_explained)
)
write.csv(pca_df, "bulk_pca_coordinates.csv", row.names = FALSE)
write.csv(var_df, "bulk_pca_variance.csv", row.names = FALSE)

p <- ggplot(pca_df, aes(x = PC1, y = PC2, color = group, label = sample)) +
  geom_point(size = 3) +
  theme_bw() +
  labs(title = "Bulk PCA", x = "PC1", y = "PC2")

ggsave("bulk_pca_only.png", p, width = 8, height = 6, dpi = 150)

cat("生成文件: bulk_pca_coordinates.csv, bulk_pca_variance.csv, bulk_pca_only.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="bulk_pca")