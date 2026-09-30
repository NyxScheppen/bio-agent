from app.agent.tool_registry import register_tool
from app.tools.omics_input import prepare_omics_input, run_with_prepared_input
from app.tools.r_tools import (
    prepare_r_job_dir,
    run_r_analysis,
    r_escape_string_content,
)


@register_tool(
    name="run_scrna_standard_pipeline",
    description=(
        "对单个 10X Genomics scRNA-seq 数据集执行原子 Seurat 标准流程：安全读取 ZIP/H5、"
        "QC 过滤、LogNormalize、HVG、PCA、邻居图、聚类、UMAP 和 marker 分析。"
    ),
    category="scrna",
    tags=["10x", "seurat", "qc", "umap", "markers"],
    task_types=["scrna_analysis", "scrna_clustering"],
    timeout=3600,
    max_memory_mb=16384,
    parameters={
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "当前会话上传的 10X H5 文件或仅含一个 10X 数据集的 ZIP 文件",
            },
            "project_name": {"type": "string", "default": "scRNA_project"},
            "species": {
                "type": "string",
                "enum": ["auto", "human", "mouse"],
                "default": "auto",
            },
            "min_cells": {"type": "integer", "default": 3},
            "min_features": {"type": "integer", "default": 200},
            "max_features": {"type": "integer", "default": 7500},
            "max_mt_percent": {"type": "number", "default": 20},
            "resolution": {"type": "number", "default": 0.5},
            "top_n_markers": {"type": "integer", "default": 10},
            "seed": {"type": "integer", "default": 2026},
        },
        "required": ["input_file"],
    },
)
def run_scrna_standard_pipeline(
    input_file: str,
    project_name: str = "scRNA_project",
    species: str = "auto",
    min_cells: int = 3,
    min_features: int = 200,
    max_features: int = 7500,
    max_mt_percent: float = 20.0,
    resolution: float = 0.5,
    top_n_markers: int = 10,
    seed: int = 2026,
    session_id: str = "",
    job_dir: str = None,
):
    species = str(species or "auto").strip().lower()
    if species not in {"auto", "human", "mouse"}:
        raise ValueError("species must be one of: auto, human, mouse")

    min_cells = int(min_cells)
    min_features = int(min_features)
    max_features = int(max_features)
    max_mt_percent = float(max_mt_percent)
    resolution = float(resolution)
    top_n_markers = int(top_n_markers)
    seed = int(seed)
    if not 1 <= min_cells <= 100:
        raise ValueError("min_cells must be between 1 and 100")
    if min_features < 1 or max_features <= min_features:
        raise ValueError("max_features must be greater than min_features")
    if not 0 <= max_mt_percent <= 100:
        raise ValueError("max_mt_percent must be between 0 and 100")
    if not 0 <= resolution <= 10:
        raise ValueError("resolution must be between 0 and 10")
    if not 1 <= top_n_markers <= 100:
        raise ValueError("top_n_markers must be between 1 and 100")

    resolved_job_dir = prepare_r_job_dir(job_dir, "scrna_standard")
    prepared = prepare_omics_input(
        input_file=input_file,
        input_type="scrna",
        job_dir=resolved_job_dir,
        session_id=session_id,
    )
    input_path = r_escape_string_content(prepared.path)
    input_kind = r_escape_string_content(prepared.input_kind)
    project_name = r_escape_string_content(project_name)
    species_r = r_escape_string_content(species)

    r_code = f'''
library(Seurat)
library(ggplot2)

set.seed({seed})
input_path <- smart_read("{input_path}")
input_kind <- "{input_kind}"

counts <- if (identical(input_kind, "h5")) {{
  Read10X_h5(input_path, use.names = TRUE, unique.features = TRUE)
}} else {{
  # Seurat 5 delegates gz decompression to an external command on Windows,
  # which the R execution guard intentionally blocks. Base R connections keep
  # the same input contract without weakening that guard.
  raw_counts <- local({{
    matrix_connection <- gzfile(file.path(input_path, "matrix.mtx.gz"), "rb")
    on.exit(close(matrix_connection), add = TRUE)
    Matrix::readMM(matrix_connection)
  }})
  feature_path <- if (file.exists(file.path(input_path, "features.tsv.gz"))) {{
    file.path(input_path, "features.tsv.gz")
  }} else {{
    file.path(input_path, "genes.tsv.gz")
  }}
  features <- read.delim(gzfile(feature_path), header = FALSE, stringsAsFactors = FALSE)
  barcodes <- read.delim(gzfile(file.path(input_path, "barcodes.tsv.gz")), header = FALSE, stringsAsFactors = FALSE)
  if (nrow(features) != nrow(raw_counts) || nrow(barcodes) != ncol(raw_counts)) {{
    stop("10X matrix dimensions do not match features/barcodes")
  }}
  rownames(raw_counts) <- make.unique(as.character(features[[min(2L, ncol(features))]]))
  colnames(raw_counts) <- make.unique(as.character(barcodes[[1]]))
  as(raw_counts, "CsparseMatrix")
}}
if (is.list(counts)) {{
  if (!("Gene Expression" %in% names(counts))) {{
    stop("10X input contains multiple assays but no 'Gene Expression' assay")
  }}
  counts <- counts[["Gene Expression"]]
}}
if (nrow(counts) < 2 || ncol(counts) < 3) stop("10X matrix needs at least 2 genes and 3 cells")

obj <- CreateSeuratObject(
  counts = counts,
  project = "{project_name}",
  min.cells = {min_cells},
  min.features = 0
)
if (nrow(obj) < 2 || ncol(obj) < 3) stop("Too few genes or cells remain after min_cells filtering")

species <- "{species_r}"
human_mt <- sum(grepl("^MT-", rownames(obj)))
mouse_mt <- sum(grepl("^mt-", rownames(obj)))
mt_pattern <- if (species == "human") "^MT-" else if (species == "mouse") "^mt-" else if (human_mt >= mouse_mt) "^MT-" else "^mt-"
if (sum(grepl(mt_pattern, rownames(obj))) > 0) {{
  obj[["percent.mt"]] <- PercentageFeatureSet(obj, pattern = mt_pattern)
}} else {{
  obj$percent.mt <- 0
}}

raw_cells <- ncol(obj)
obj$qc_pass <- obj$nFeature_RNA >= {min_features} &
  obj$nFeature_RNA <= {max_features} &
  obj$percent.mt <= {max_mt_percent} &
  obj$nCount_RNA > 0
qc_metrics <- obj@meta.data
qc_metrics$cell <- rownames(qc_metrics)
write.csv(qc_metrics, "scrna_qc_metrics.csv", row.names = FALSE)

png("scrna_qc_violin.png", width = 1500, height = 900, res = 150)
print(VlnPlot(obj, features = c("nFeature_RNA", "nCount_RNA", "percent.mt"), ncol = 3))
dev.off()

obj <- subset(obj, subset = qc_pass)
if (ncol(obj) < 3) stop("QC thresholds leave fewer than 3 cells; relax the thresholds")
if (nrow(obj) < 2) stop("QC thresholds leave fewer than 2 genes")

obj <- NormalizeData(obj, normalization.method = "LogNormalize", scale.factor = 10000, verbose = FALSE)
variable_count <- min(2000L, nrow(obj))
obj <- FindVariableFeatures(obj, selection.method = "vst", nfeatures = variable_count, verbose = FALSE)
variable_features <- VariableFeatures(obj)
if (length(variable_features) < 3) stop("Too few variable genes for PCA")
obj <- ScaleData(obj, features = variable_features, verbose = FALSE)
npcs <- min(50L, ncol(obj) - 1L, length(variable_features) - 1L)
if (npcs < 2) stop("Too few cells or variable genes for PCA")
obj <- RunPCA(obj, features = variable_features, npcs = npcs, seed.use = {seed}, verbose = FALSE)
dims_use <- seq_len(min(30L, npcs))
k_param <- max(1L, min(20L, ncol(obj) - 1L))
umap_neighbors <- max(2L, min(30L, ncol(obj) - 1L))
obj <- FindNeighbors(obj, dims = dims_use, k.param = k_param, verbose = FALSE)
obj <- FindClusters(obj, resolution = {resolution}, random.seed = {seed}, verbose = FALSE)
obj <- RunUMAP(obj, dims = dims_use, n.neighbors = umap_neighbors, seed.use = {seed}, verbose = FALSE)

png("scrna_umap_clusters.png", width = 1200, height = 900, res = 150)
print(DimPlot(obj, reduction = "umap", label = TRUE, repel = TRUE) + ggtitle("10X scRNA-seq clusters"))
dev.off()

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
write.csv(markers, "scrna_all_markers.csv", row.names = FALSE)
if (nrow(markers) > 0) {{
  fc_col <- if ("avg_log2FC" %in% colnames(markers)) "avg_log2FC" else "avg_logFC"
  top_markers <- do.call(rbind, lapply(split(markers, markers$cluster), function(x) {{
    head(x[order(x[[fc_col]], decreasing = TRUE), , drop = FALSE], {top_n_markers})
  }}))
}} else {{
  top_markers <- data.frame()
}}
write.csv(top_markers, "scrna_top_markers.csv", row.names = FALSE)

metadata <- obj@meta.data
metadata$cell <- rownames(metadata)
write.csv(metadata, "scrna_cluster_metadata.csv", row.names = FALSE)
saveRDS(obj, "scrna_standard_seurat.rds")

qc_summary <- data.frame(
  input_kind = input_kind,
  species_request = species,
  mitochondrial_pattern = mt_pattern,
  raw_cells = raw_cells,
  retained_cells = ncol(obj),
  retained_genes = nrow(obj),
  clusters = length(unique(Idents(obj))),
  pca_dimensions = length(dims_use),
  marker_status = if (nzchar(marker_error)) marker_error else "completed",
  stringsAsFactors = FALSE
)
write.csv(qc_summary, "scrna_qc_summary.csv", row.names = FALSE)

packages <- c("Seurat", "SeuratObject", "ggplot2")
versions <- data.frame(
  package = packages,
  version = vapply(packages, function(pkg) as.character(packageVersion(pkg)), character(1)),
  seed = {seed},
  stringsAsFactors = FALSE
)
write.csv(versions, "scrna_software_versions.csv", row.names = FALSE)

cat("Generated: scrna_qc_violin.png, scrna_umap_clusters.png, scrna_all_markers.csv, scrna_top_markers.csv, scrna_qc_metrics.csv, scrna_qc_summary.csv, scrna_cluster_metadata.csv, scrna_standard_seurat.rds, scrna_software_versions.csv\\n")
'''
    return run_with_prepared_input(
        prepared,
        run_r_analysis,
        r_code,
        timeout=3600,
        job_subdir="scrna_standard",
        job_dir=str(resolved_job_dir),
    )

@register_tool(
    name="run_scrna_basic_qc_analysis",
    description="对单细胞 10X 数据进行基础质控分析，输出 QC 图和 Seurat 对象。",
    category="scrna",
    parameters={
        "type": "object",
        "properties": {
            "data_dir": {"type": "string", "description": "10X 数据目录名，位于 uploads 下"},
            "project_name": {"type": "string", "default": "scRNA_project"}
        },
        "required": ["data_dir"]
    }
)
def run_scrna_basic_qc_analysis(
    data_dir: str,
    project_name: str = "scRNA_project",
    job_dir: str = None,
):
    data_dir = r_escape_string_content(data_dir)
    project_name = r_escape_string_content(project_name)
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
    return run_r_analysis(r_code, job_subdir="scrna_qc", job_dir=job_dir)

@register_tool(
    name="run_scrna_clustering_analysis",
    description="对 Seurat 对象执行标准聚类分析，输出 UMAP 图和聚类后的 Seurat 对象。",
    category="scrna",
    parameters={
        "type": "object",
        "properties": {
            "seurat_rds": {"type": "string", "description": "Seurat RDS 文件"},
            "resolution": {"type": "number", "default": 0.5}
        },
        "required": ["seurat_rds"]
    }
)
def run_scrna_clustering_analysis(
    seurat_rds: str,
    resolution: float = 0.5,
    job_dir: str = None,
):
    seurat_rds = r_escape_string_content(seurat_rds)
    resolution = max(0.0, min(float(resolution), 10.0))
    r_code = f'''
library(Seurat)
library(ggplot2)

obj <- readRDS(smart_read("{seurat_rds}"))

obj <- NormalizeData(obj)
obj <- FindVariableFeatures(obj)
obj <- ScaleData(obj)
obj <- RunPCA(obj)
obj <- FindNeighbors(obj, dims = 1:20)
obj <- FindClusters(obj, resolution = {resolution})
obj <- RunUMAP(obj, dims = 1:20)

png("scrna_umap_clusters.png", width = 1200, height = 900, res = 150)
print(DimPlot(obj, reduction = "umap", label = TRUE))
dev.off()

saveRDS(obj, "scrna_clustered_seurat.rds")
write.csv(obj@meta.data, "scrna_cluster_metadata.csv", row.names = TRUE)

cat("生成文件: scrna_umap_clusters.png, scrna_clustered_seurat.rds, scrna_cluster_metadata.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="scrna_cluster", job_dir=job_dir)

@register_tool(
    name="run_scrna_marker_analysis",
    description="对聚类后的 Seurat 对象进行 marker 基因分析。",
    category="scrna",
    parameters={
        "type": "object",
        "properties": {
            "seurat_rds": {"type": "string", "description": "聚类后的 Seurat RDS 文件"},
            "top_n": {"type": "integer", "default": 10}
        },
        "required": ["seurat_rds"]
    }
)
def run_scrna_marker_analysis(
    seurat_rds: str,
    top_n: int = 10,
    job_dir: str = None,
):
    seurat_rds = r_escape_string_content(seurat_rds)
    top_n = max(1, min(int(top_n), 100))
    r_code = f'''
library(Seurat)
library(dplyr)

obj <- readRDS(smart_read("{seurat_rds}"))
markers <- FindAllMarkers(obj, only.pos = TRUE, min.pct = 0.25, logfc.threshold = 0.25)
write.csv(markers, "scrna_all_markers.csv", row.names = FALSE)

top_markers <- markers %>%
  group_by(cluster) %>%
  slice_max(order_by = avg_log2FC, n = {top_n}) %>%
  ungroup()

write.csv(top_markers, "scrna_top_markers.csv", row.names = FALSE)

cat("生成文件: scrna_all_markers.csv, scrna_top_markers.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="scrna_marker", job_dir=job_dir)
