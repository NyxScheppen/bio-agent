from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis

@register_tool(
    name="run_spatial_basic_analysis",
    description="对 10X Visium 空间转录组数据进行基础分析，输出空间聚类图。",
    parameters={
        "type": "object",
        "properties": {
            "data_dir": {"type": "string", "description": "Visium 数据目录"},
            "project_name": {"type": "string", "default": "spatial_project"}
        },
        "required": ["data_dir"]
    }
)
def run_spatial_basic_analysis(data_dir: str, project_name: str = "spatial_project"):
    r_code = f'''
library(Seurat)
library(ggplot2)

input_dir <- smart_read("{data_dir}")
if (!dir.exists(input_dir)) stop("data_dir 不是有效目录")

obj <- Load10X_Spatial(data.dir = input_dir)
obj <- SCTransform(obj, assay = "Spatial", verbose = FALSE)
obj <- RunPCA(obj, assay = "SCT", verbose = FALSE)
obj <- FindNeighbors(obj, reduction = "pca", dims = 1:20)
obj <- FindClusters(obj, verbose = FALSE)
obj <- RunUMAP(obj, reduction = "pca", dims = 1:20)

png("spatial_cluster_plot.png", width = 1200, height = 900, res = 150)
print(SpatialDimPlot(obj, label = TRUE, label.size = 3))
dev.off()

saveRDS(obj, "spatial_seurat.rds")
write.csv(obj@meta.data, "spatial_metadata.csv", row.names = TRUE)

cat("生成文件: spatial_cluster_plot.png, spatial_seurat.rds, spatial_metadata.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="spatial_basic")

@register_tool(
    name="run_spatial_feature_plot",
    description="绘制空间转录组目标基因的空间表达图。",
    parameters={
        "type": "object",
        "properties": {
            "seurat_rds": {"type": "string"},
            "gene": {"type": "string"}
        },
        "required": ["seurat_rds", "gene"]
    }
)
def run_spatial_feature_plot(seurat_rds: str, gene: str):
    r_code = f'''
library(Seurat)

obj <- readRDS(smart_read("{seurat_rds}"))
if (!("{gene}" %in% rownames(obj))) stop("找不到目标基因")

png("spatial_feature_{gene}.png", width = 1200, height = 900, res = 150)
print(SpatialFeaturePlot(obj, features = "{gene}"))
dev.off()

cat("生成文件: spatial_feature_{gene}.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="spatial_feature")