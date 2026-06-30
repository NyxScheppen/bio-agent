from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis

@register_tool(
    name="run_go_kegg_enrichment",
    description="对基因列表执行 GO 和 KEGG 富集分析，输出富集结果表及可视化图。输入文件应至少包含一列 gene。",
    parameters={
        "type": "object",
        "properties": {
            "gene_file": {
                "type": "string",
                "description": "基因列表CSV文件，至少包含 gene 列"
            },
            "organism": {
                "type": "string",
                "description": "物种，支持 human 或 mouse",
                "default": "human"
            }
        },
        "required": ["gene_file"]
    }
)
def run_go_kegg_enrichment(gene_file: str, organism: str = "human"):
    org_pkg = "org.Hs.eg.db" if organism.lower() == "human" else "org.Mm.eg.db"
    org_db = "org.Hs.eg.db" if organism.lower() == "human" else "org.Mm.eg.db"
    kegg_org = "hsa" if organism.lower() == "human" else "mmu"

    r_code = f'''
library(data.table)
library(clusterProfiler)
library(enrichplot)
library({org_pkg})
library(ggplot2)

smart_read <- function(fp) {{
  full_path <- fp
  if (!file.exists(full_path)) full_path <- file.path(UPLOAD_DIR, fp)
  if (!file.exists(full_path)) stop(paste("文件不存在:", fp))
  fread(full_path, data.table = FALSE)
}}

gene_df <- smart_read("{gene_file}")
if (!("gene" %in% colnames(gene_df))) stop("gene_file 必须包含 gene 列")

genes <- unique(as.character(gene_df$gene))
genes <- genes[genes != "" & !is.na(genes)]
if (length(genes) < 5) stop("基因数太少，至少需要5个基因")

eg <- bitr(genes, fromType = "SYMBOL", toType = "ENTREZID", OrgDb = {org_db})
if (is.null(eg) || nrow(eg) == 0) stop("无法将 SYMBOL 转换为 ENTREZID，请检查物种或基因名")

entrez <- unique(eg$ENTREZID)

ego <- enrichGO(
  gene = entrez,
  OrgDb = {org_db},
  keyType = "ENTREZID",
  ont = "ALL",
  pAdjustMethod = "BH",
  qvalueCutoff = 0.2,
  readable = TRUE
)

ekegg <- enrichKEGG(
  gene = entrez,
  organism = "{kegg_org}",
  pAdjustMethod = "BH",
  qvalueCutoff = 0.2
)

go_df <- as.data.frame(ego)
kegg_df <- as.data.frame(ekegg)

write.csv(go_df, "go_enrichment_results.csv", row.names = FALSE)
write.csv(kegg_df, "kegg_enrichment_results.csv", row.names = FALSE)

if (nrow(go_df) > 0) {{
  p1 <- dotplot(ego, showCategory = 15) + ggtitle("GO Enrichment")
  ggsave("go_dotplot.png", p1, width = 9, height = 7, dpi = 150)
}}

if (nrow(kegg_df) > 0) {{
  p2 <- dotplot(ekegg, showCategory = 15) + ggtitle("KEGG Enrichment")
  ggsave("kegg_dotplot.png", p2, width = 9, height = 7, dpi = 150)
}}

cat("生成文件: go_enrichment_results.csv, kegg_enrichment_results.csv, go_dotplot.png, kegg_dotplot.png\\n")
'''
    return run_r_analysis(r_code)

@register_tool(
    name="run_gsea_analysis",
    description="对排序基因列表进行 GSEA 分析。输入文件应包含 gene 和 score 两列。",
    parameters={
        "type": "object",
        "properties": {
            "ranked_gene_file": {
                "type": "string",
                "description": "排序基因列表CSV文件，需包含 gene 和 score 列"
            },
            "organism": {
                "type": "string",
                "description": "物种，human 或 mouse",
                "default": "human"
            }
        },
        "required": ["ranked_gene_file"]
    }
)
def run_gsea_analysis(ranked_gene_file: str, organism: str = "human"):
    species = "Homo sapiens" if organism.lower() == "human" else "Mus musculus"
    org_db = "org.Hs.eg.db" if organism.lower() == "human" else "org.Mm.eg.db"

    r_code = f'''
library(data.table)
library(clusterProfiler)
library(enrichplot)
library(msigdbr)
library({org_db})
library(ggplot2)

smart_read <- function(fp) {{
  full_path <- fp
  if (!file.exists(full_path)) full_path <- file.path(UPLOAD_DIR, fp)
  if (!file.exists(full_path)) stop(paste("文件不存在:", fp))
  fread(full_path, data.table = FALSE)
}}

df <- smart_read("{ranked_gene_file}")
if (!all(c("gene", "score") %in% colnames(df))) stop("文件必须包含 gene 和 score 列")

df <- df[!is.na(df$gene) & !is.na(df$score), ]
df$gene <- as.character(df$gene)
df$score <- as.numeric(df$score)

gene_map <- bitr(unique(df$gene), fromType = "SYMBOL", toType = "ENTREZID", OrgDb = {org_db})
df2 <- merge(df, gene_map, by.x = "gene", by.y = "SYMBOL")
df2 <- df2[!duplicated(df2$ENTREZID), ]

gene_list <- df2$score
names(gene_list) <- df2$ENTREZID
gene_list <- sort(gene_list, decreasing = TRUE)

m_df <- msigdbr(species = "{species}", category = "H")
term2gene <- m_df[, c("gs_name", "entrez_gene")]

gsea_res <- GSEA(geneList = gene_list, TERM2GENE = term2gene, pvalueCutoff = 0.2)
res_df <- as.data.frame(gsea_res)
write.csv(res_df, "gsea_results.csv", row.names = FALSE)

if (nrow(res_df) > 0) {{
  p <- dotplot(gsea_res, showCategory = 15) + ggtitle("GSEA Hallmark")
  ggsave("gsea_dotplot.png", p, width = 9, height = 7, dpi = 150)
}}

cat("生成文件: gsea_results.csv, gsea_dotplot.png\\n")
'''
    return run_r_analysis(r_code)

@register_tool(
    name="run_gsva_analysis",
    description="对表达矩阵执行 GSVA 通路打分，并比较不同组之间的通路差异。",
    parameters={
        "type": "object",
        "properties": {
            "expression_file": {"type": "string", "description": "表达矩阵CSV文件，第一列为gene"},
            "group_file": {"type": "string", "description": "样本分组CSV文件，包含 sample 和 group 两列"},
            "organism": {
                "type": "string",
                "description": "物种，human 或 mouse",
                "default": "human"
            }
        },
        "required": ["expression_file", "group_file"]
    }
)
def run_gsva_analysis(expression_file: str, group_file: str, organism: str = "human"):
    species = "Homo sapiens" if organism.lower() == "human" else "Mus musculus"

    r_code = f'''
library(data.table)
library(GSVA)
library(msigdbr)
library(limma)
library(pheatmap)

expr <- fread(smart_read("{expression_file}"), data.table = FALSE)
grp <- fread(smart_read("{group_file}"), data.table = FALSE)

if (!("gene" %in% colnames(expr))) stop("表达矩阵必须包含 gene 列")
if (!all(c("sample", "group") %in% colnames(grp))) stop("group_file 必须包含 sample 和 group")

rownames(expr) <- expr$gene
expr$gene <- NULL
expr_mat <- as.matrix(expr)
mode(expr_mat) <- "numeric"

common_samples <- intersect(colnames(expr_mat), grp$sample)
if (length(common_samples) < 4) stop("样本重叠太少")

expr_mat <- expr_mat[, common_samples, drop = FALSE]
grp <- grp[match(common_samples, grp$sample), , drop = FALSE]

m_df <- msigdbr(species = "{species}", category = "H")
gene_sets <- split(m_df$gene_symbol, m_df$gs_name)

gsva_res <- gsva(expr_mat, gene_sets, method = "gsva", kcdf = "Gaussian", verbose = FALSE)
gsva_df <- data.frame(pathway = rownames(gsva_res), gsva_res, check.names = FALSE)
write.csv(gsva_df, "gsva_scores.csv", row.names = FALSE)

group_factor <- factor(grp$group)
design <- model.matrix(~ 0 + group_factor)
colnames(design) <- levels(group_factor)

fit <- lmFit(gsva_res, design)
if (ncol(design) == 2) {{
  contrast.matrix <- makeContrasts(contrasts = paste0(colnames(design)[2], "-", colnames(design)[1]), levels = design)
  fit2 <- contrasts.fit(fit, contrast.matrix)
  fit2 <- eBayes(fit2)
  diff_df <- topTable(fit2, number = Inf, adjust.method = "BH")
  diff_df$pathway <- rownames(diff_df)
  write.csv(diff_df, "gsva_diff_pathways.csv", row.names = FALSE)
}}

top_pathways <- head(rownames(gsva_res), 30)
png("gsva_heatmap.png", width = 1200, height = 1000, res = 150)
pheatmap(gsva_res[top_pathways, , drop = FALSE],
         scale = "row",
         annotation_col = data.frame(Group = grp$group, row.names = grp$sample))
dev.off()

cat("生成文件: gsva_scores.csv, gsva_diff_pathways.csv, gsva_heatmap.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="gsva")