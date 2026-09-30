from app.agent.tool_registry import register_tool
from app.tools.omics_input import prepare_omics_input, run_with_prepared_input
from app.tools.r_tools import (
    prepare_r_job_dir,
    run_r_analysis,
    r_character_vector,
    r_escape_string_content,
)


@register_tool(
    name="run_visium_standard_pipeline",
    description=(
        "对单个 10X Visium Space Ranger ZIP 执行原子 Seurat 流程：QC、SCTransform、PCA、"
        "表达聚类、组织切片空间投影、marker 和可选基因空间表达图。该工具不是空间感知聚类。"
    ),
    category="spatial",
    tags=["visium", "seurat", "sctransform", "spatial-projection"],
    task_types=["spatial_analysis", "spatial_clustering"],
    timeout=3600,
    max_memory_mb=16384,
    parameters={
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "当前会话上传的、仅含一个完整 Space Ranger 输出目录的 ZIP",
            },
            "project_name": {"type": "string", "default": "visium_project"},
            "species": {
                "type": "string",
                "enum": ["auto", "human", "mouse"],
                "default": "auto",
            },
            "min_features": {"type": "integer", "default": 200},
            "max_features": {"type": "integer", "default": 7500},
            "max_mt_percent": {"type": "number", "default": 25},
            "resolution": {"type": "number", "default": 0.5},
            "top_n_markers": {"type": "integer", "default": 10},
            "feature_genes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选的空间表达可视化基因，最多 12 个",
            },
            "seed": {"type": "integer", "default": 2026},
        },
        "required": ["input_file"],
    },
)
def run_visium_standard_pipeline(
    input_file: str,
    project_name: str = "visium_project",
    species: str = "auto",
    min_features: int = 200,
    max_features: int = 7500,
    max_mt_percent: float = 25.0,
    resolution: float = 0.5,
    top_n_markers: int = 10,
    feature_genes: list[str] | None = None,
    seed: int = 2026,
    session_id: str = "",
    job_dir: str = None,
):
    species = str(species or "auto").strip().lower()
    if species not in {"auto", "human", "mouse"}:
        raise ValueError("species must be one of: auto, human, mouse")
    min_features = int(min_features)
    max_features = int(max_features)
    max_mt_percent = float(max_mt_percent)
    resolution = float(resolution)
    top_n_markers = int(top_n_markers)
    seed = int(seed)
    if min_features < 1 or max_features <= min_features:
        raise ValueError("max_features must be greater than min_features")
    if not 0 <= max_mt_percent <= 100:
        raise ValueError("max_mt_percent must be between 0 and 100")
    if not 0 <= resolution <= 10:
        raise ValueError("resolution must be between 0 and 10")
    if not 1 <= top_n_markers <= 100:
        raise ValueError("top_n_markers must be between 1 and 100")
    feature_genes = [str(gene).strip() for gene in (feature_genes or []) if str(gene).strip()]
    if len(feature_genes) > 12:
        raise ValueError("feature_genes accepts at most 12 genes")

    resolved_job_dir = prepare_r_job_dir(job_dir, "visium_standard")
    prepared = prepare_omics_input(
        input_file=input_file,
        input_type="visium",
        job_dir=resolved_job_dir,
        session_id=session_id,
    )
    input_dir = r_escape_string_content(prepared.path)
    project_name = r_escape_string_content(project_name)
    species_r = r_escape_string_content(species)
    feature_genes_r = r_character_vector(feature_genes)

    r_code = f'''
library(Seurat)
library(ggplot2)

set.seed({seed})
input_dir <- smart_read("{input_dir}")
obj <- Load10X_Spatial(
  data.dir = input_dir,
  filename = "filtered_feature_bc_matrix.h5",
  assay = "Spatial",
  slice = "slice1",
  filter.matrix = TRUE
)
Project(obj) <- "{project_name}"
if (nrow(obj) < 2 || ncol(obj) < 3) stop("Visium matrix needs at least 2 genes and 3 tissue spots")

species <- "{species_r}"
human_mt <- sum(grepl("^MT-", rownames(obj)))
mouse_mt <- sum(grepl("^mt-", rownames(obj)))
mt_pattern <- if (species == "human") "^MT-" else if (species == "mouse") "^mt-" else if (human_mt >= mouse_mt) "^MT-" else "^mt-"
if (sum(grepl(mt_pattern, rownames(obj))) > 0) {{
  obj[["percent.mt"]] <- PercentageFeatureSet(obj, pattern = mt_pattern, assay = "Spatial")
}} else {{
  obj$percent.mt <- 0
}}

raw_spots <- ncol(obj)
obj$qc_pass <- obj$nFeature_Spatial >= {min_features} &
  obj$nFeature_Spatial <= {max_features} &
  obj$percent.mt <= {max_mt_percent} &
  obj$nCount_Spatial > 0
qc_metrics <- obj@meta.data
qc_metrics$barcode <- rownames(qc_metrics)
write.csv(qc_metrics, "visium_qc_metrics.csv", row.names = FALSE)

png("visium_qc_violin.png", width = 1500, height = 900, res = 150)
print(VlnPlot(obj, features = c("nFeature_Spatial", "nCount_Spatial", "percent.mt"), ncol = 3, assay = "Spatial"))
dev.off()

obj <- subset(obj, subset = qc_pass)
if (ncol(obj) < 3) stop("QC thresholds leave fewer than 3 tissue spots; relax the thresholds")

obj <- SCTransform(obj, assay = "Spatial", verbose = FALSE, seed.use = {seed})
variable_features <- VariableFeatures(obj)
if (length(variable_features) < 3) stop("Too few variable genes for PCA")
npcs <- min(50L, ncol(obj) - 1L, length(variable_features) - 1L)
if (npcs < 2) stop("Too few spots or variable genes for PCA")
obj <- RunPCA(obj, assay = "SCT", features = variable_features, npcs = npcs, seed.use = {seed}, verbose = FALSE)
dims_use <- seq_len(min(30L, npcs))
k_param <- max(1L, min(20L, ncol(obj) - 1L))
obj <- FindNeighbors(obj, reduction = "pca", dims = dims_use, k.param = k_param, verbose = FALSE)
obj <- FindClusters(obj, resolution = {resolution}, random.seed = {seed}, verbose = FALSE)

png("visium_expression_clusters_spatial.png", width = 1400, height = 1100, res = 150)
print(SpatialDimPlot(obj, label = TRUE, label.size = 3) + ggtitle("Expression clusters projected on tissue"))
dev.off()

DefaultAssay(obj) <- "SCT"
marker_error <- ""
markers <- tryCatch(
  {{
    if (length(unique(Idents(obj))) < 2) stop("Only one cluster was detected")
    FindAllMarkers(obj, only.pos = TRUE, min.pct = 0.25, logfc.threshold = 0.25, verbose = FALSE)
  }},
  error = function(e) {{
    marker_error <<- conditionMessage(e)
    data.frame()
  }}
)
write.csv(markers, "visium_all_markers.csv", row.names = FALSE)
if (nrow(markers) > 0) {{
  fc_col <- if ("avg_log2FC" %in% colnames(markers)) "avg_log2FC" else "avg_logFC"
  top_markers <- do.call(rbind, lapply(split(markers, markers$cluster), function(x) {{
    head(x[order(x[[fc_col]], decreasing = TRUE), , drop = FALSE], {top_n_markers})
  }}))
}} else {{
  top_markers <- data.frame()
}}
write.csv(top_markers, "visium_top_markers.csv", row.names = FALSE)

requested_genes <- {feature_genes_r}
available_genes <- requested_genes[requested_genes %in% rownames(obj)]
missing_genes <- setdiff(requested_genes, available_genes)
if (length(available_genes) > 0) {{
  png("visium_feature_plots.png", width = 1400, height = max(900, 550 * ceiling(length(available_genes) / 2)), res = 150)
  print(SpatialFeaturePlot(obj, features = available_genes, ncol = min(2, length(available_genes))))
  dev.off()
}}
write.csv(
  data.frame(gene = requested_genes, available = requested_genes %in% available_genes),
  "visium_requested_features.csv",
  row.names = FALSE
)

metadata <- obj@meta.data
metadata$barcode <- rownames(metadata)
write.csv(metadata, "visium_cluster_metadata.csv", row.names = FALSE)
saveRDS(obj, "visium_standard_seurat.rds")

summary_df <- data.frame(
  workflow = "expression clustering with tissue projection (not spatial-aware clustering)",
  species_request = species,
  mitochondrial_pattern = mt_pattern,
  raw_spots = raw_spots,
  retained_spots = ncol(obj),
  retained_genes = nrow(obj),
  clusters = length(unique(Idents(obj))),
  pca_dimensions = length(dims_use),
  marker_status = if (nzchar(marker_error)) marker_error else "completed",
  missing_feature_genes = paste(missing_genes, collapse = ";"),
  stringsAsFactors = FALSE
)
write.csv(summary_df, "visium_qc_summary.csv", row.names = FALSE)

packages <- c("Seurat", "SeuratObject", "sctransform", "ggplot2")
versions <- data.frame(
  package = packages,
  version = vapply(packages, function(pkg) as.character(packageVersion(pkg)), character(1)),
  seed = {seed},
  stringsAsFactors = FALSE
)
write.csv(versions, "visium_software_versions.csv", row.names = FALSE)

cat("Generated: visium_qc_violin.png, visium_expression_clusters_spatial.png, visium_all_markers.csv, visium_top_markers.csv, visium_qc_metrics.csv, visium_qc_summary.csv, visium_cluster_metadata.csv, visium_standard_seurat.rds, visium_software_versions.csv\\n")
'''
    return run_with_prepared_input(
        prepared,
        run_r_analysis,
        r_code,
        timeout=3600,
        job_subdir="visium_standard",
        job_dir=str(resolved_job_dir),
    )

@register_tool(
    name="run_spatial_basic_analysis",
    description="对已解压 10X Visium 目录做兼容性基础分析；结果是表达聚类在组织切片上的投影，不是空间感知聚类。",
    category="spatial",
    parameters={
        "type": "object",
        "properties": {
            "data_dir": {"type": "string", "description": "Visium 数据目录"},
            "project_name": {"type": "string", "default": "spatial_project"}
        },
        "required": ["data_dir"]
    }
)
def run_spatial_basic_analysis(
    data_dir: str,
    project_name: str = "spatial_project",
    job_dir: str = None,
):
    data_dir = r_escape_string_content(data_dir)
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
    return run_r_analysis(r_code, job_subdir="spatial_basic", job_dir=job_dir)

@register_tool(
    name="run_spatial_feature_plot",
    description="绘制空间转录组目标基因的空间表达图。",
    category="spatial",
    parameters={
        "type": "object",
        "properties": {
            "seurat_rds": {"type": "string"},
            "gene": {"type": "string"}
        },
        "required": ["seurat_rds", "gene"]
    }
)
def run_spatial_feature_plot(seurat_rds: str, gene: str, job_dir: str = None):
    seurat_rds = r_escape_string_content(seurat_rds)
    gene = r_escape_string_content(gene)
    r_code = f'''
library(Seurat)

obj <- readRDS(smart_read("{seurat_rds}"))
if (!("{gene}" %in% rownames(obj))) stop("找不到目标基因")

png("spatial_feature_plot.png", width = 1200, height = 900, res = 150)
print(SpatialFeaturePlot(obj, features = "{gene}"))
dev.off()

cat("生成文件: spatial_feature_plot.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="spatial_feature", job_dir=job_dir)
