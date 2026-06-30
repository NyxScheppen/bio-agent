from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis

@register_tool(
    name="run_scrna_basic_qc_analysis",
    description="对单细胞 10X 数据进行基础质控分析，输出 QC 图和 Seurat 对象。",
    parameters={
        "type": "object",
        "properties": {
            "data_dir": {"type": "string", "description": "10X 数据目录名，位于 uploads 下"},
            "project_name": {"type": "string", "default": "scRNA_project"}
        },
        "required": ["data_dir"]
    }
)
def run_scrna_basic_qc_analysis(data_dir: str, project_name: str = "scRNA_project"):
    r_code = f'''
library(Seurat)
library(ggplot2)

input_dir <- smart_read("{data_dir}")
if (!dir.exists(input_dir)) stop("data_dir 不是有效目录")

sc <- Read10X(data.dir = input_dir)
obj <- CreateSeuratObject(counts = sc, project = "{project_name}", min.cells = 3, min.features = 200)
obj[["percent.mt"]] <- PercentageFeatureSet(obj, pattern = "^MT-")

png("scrna_qc_violin.png", width = 1400, height = 900, res = 150)
print(VlnPlot(obj, features = c("nFeature_RNA", "nCount_RNA", "percent.mt"), ncol = 3))
dev.off()

qc_df <- obj@meta.data
write.csv(qc_df, "scrna_qc_metrics.csv", row.names = TRUE)
saveRDS(obj, "scrna_raw_seurat.rds")

cat("生成文件: scrna_qc_violin.png, scrna_qc_metrics.csv, scrna_raw_seurat.rds\\n")
'''
    return run_r_analysis(r_code, job_subdir="scrna_qc")

@register_tool(
    name="run_scrna_clustering_analysis",
    description="对 Seurat 对象执行标准聚类分析，输出 UMAP 图和聚类后的 Seurat 对象。",
    parameters={
        "type": "object",
        "properties": {
            "seurat_rds": {"type": "string", "description": "Seurat RDS 文件"},
            "resolution": {"type": "number", "default": 0.5}
        },
        "required": ["seurat_rds"]
    }
)
def run_scrna_clustering_analysis(seurat_rds: str, resolution: float = 0.5):
    r_code = f'''
library(Seurat)
library(ggplot2)

obj <- readRDS(smart_read("{seurat_rds}"))

obj <- NormalizeData(obj)
obj <- FindVariableFeatures(obj)
obj <- ScaleData(obj)
obj <- RunPCA(obj)
obj <- FindNeighbors(obj, dims = 1:20)
obj <- FindClusters(obj, resolution = {float(resolution)})
obj <- RunUMAP(obj, dims = 1:20)

png("scrna_umap_clusters.png", width = 1200, height = 900, res = 150)
print(DimPlot(obj, reduction = "umap", label = TRUE))
dev.off()

saveRDS(obj, "scrna_clustered_seurat.rds")
write.csv(obj@meta.data, "scrna_cluster_metadata.csv", row.names = TRUE)

cat("生成文件: scrna_umap_clusters.png, scrna_clustered_seurat.rds, scrna_cluster_metadata.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="scrna_cluster")

@register_tool(
    name="run_scrna_marker_analysis",
    description="对聚类后的 Seurat 对象进行 marker 基因分析。",
    parameters={
        "type": "object",
        "properties": {
            "seurat_rds": {"type": "string", "description": "聚类后的 Seurat RDS 文件"},
            "top_n": {"type": "integer", "default": 10}
        },
        "required": ["seurat_rds"]
    }
)
def run_scrna_marker_analysis(seurat_rds: str, top_n: int = 10):
    r_code = f'''
library(Seurat)
library(dplyr)

obj <- readRDS(smart_read("{seurat_rds}"))
markers <- FindAllMarkers(obj, only.pos = TRUE, min.pct = 0.25, logfc.threshold = 0.25)
write.csv(markers, "scrna_all_markers.csv", row.names = FALSE)

top_markers <- markers %>%
  group_by(cluster) %>%
  slice_max(order_by = avg_log2FC, n = {int(top_n)}) %>%
  ungroup()

write.csv(top_markers, "scrna_top_markers.csv", row.names = FALSE)

cat("生成文件: scrna_all_markers.csv, scrna_top_markers.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="scrna_marker")