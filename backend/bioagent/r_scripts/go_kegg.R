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
