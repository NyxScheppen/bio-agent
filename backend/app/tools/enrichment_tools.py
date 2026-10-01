import csv
import ipaddress
import socket
from pathlib import Path

from app.agent.tool_registry import register_tool
from app.core.runtime_paths import R_LIBS_USER
from app.tools.r_tools import run_r_analysis, r_escape_string_content


GSEA_DEPENDENCY_HOST = "zenodo.org"
GSEA_R_TIMEOUT_SECONDS = 900


def _diagnose_dns(host: str) -> dict:
    """Resolve an external dependency and flag non-routable sinkhole answers."""
    diagnostic = {
        "host": host,
        "status": "error",
        "addresses": [],
        "sinkhole_addresses": [],
        "error": "",
        "reason": "dns_resolution_failed",
    }

    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        diagnostic["error"] = str(exc)
        return diagnostic

    addresses = sorted({str(record[4][0]).split("%", 1)[0] for record in records})
    diagnostic["addresses"] = addresses
    if not addresses:
        diagnostic["error"] = "DNS resolver returned no addresses"
        return diagnostic

    sinkhole_addresses = []
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not parsed.is_global or parsed.is_multicast:
            sinkhole_addresses.append(address)

    diagnostic["sinkhole_addresses"] = sinkhole_addresses
    if sinkhole_addresses:
        diagnostic["status"] = "sinkhole"
        diagnostic["reason"] = "resolved_to_non_routable_address"
        return diagnostic

    diagnostic["status"] = "ok"
    diagnostic["reason"] = "public_addresses_resolved"
    return diagnostic


def _diagnose_msigdb_cache() -> dict:
    cache_dir = Path(R_LIBS_USER) / ".cache" / "R" / "msigdbr"
    archives = sorted(cache_dir.glob("msigdb.*.zip")) if cache_dir.is_dir() else []
    return {
        "cache_dir": str(cache_dir),
        "archive_present": bool(archives),
        "archives": [path.name for path in archives],
    }


def _gsea_dns_error(diagnostic: dict, cache_diagnostic: dict) -> dict:
    addresses = ", ".join(diagnostic.get("addresses") or []) or "无"
    detail = diagnostic.get("error") or f"解析结果为 {addresses}"
    return {
        "status": "error",
        "message": (
            f"GSEA 依赖数据不可用：系统 DNS 无法正常解析 {GSEA_DEPENDENCY_HOST}"
            f"（{detail}）。本次未启动 R；这不是 HTTP 402 或额度不足。"
            "请检查系统 DNS、网络安全软件或组织网络策略后重试。"
        ),
        "errors": ["gsea_dependency_dns_unavailable"],
        "output_files": [],
        "summary": {
            "failure_stage": "dns_resolution",
            "dependency": "MSigDB Hallmark",
            "dependency_host": GSEA_DEPENDENCY_HOST,
            "retryable": True,
            "dns_diagnostic": diagnostic,
            "cache_diagnostic": cache_diagnostic,
        },
    }


def _read_gsea_diagnostics(job_dir: str | None) -> dict:
    if not job_dir:
        return {}
    path = Path(job_dir) / "gsea_diagnostics.csv"
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.DictReader(handle)
            return {
                str(row.get("metric", "")).strip(): str(row.get("value", "")).strip()
                for row in rows
                if str(row.get("metric", "")).strip()
            }
    except (OSError, csv.Error):
        return {}


def _annotate_gsea_result(result, dns_diagnostic: dict, cache_diagnostic: dict):
    if not isinstance(result, dict):
        return result

    summary = dict(result.get("summary") or {})
    summary["dns_diagnostic"] = dns_diagnostic
    summary["cache_diagnostic"] = cache_diagnostic
    summary["using_cache_without_dns"] = (
        dns_diagnostic.get("status") != "ok"
        and cache_diagnostic.get("archive_present") is True
    )
    summary["dependency_host"] = GSEA_DEPENDENCY_HOST
    summary["r_timeout_seconds"] = GSEA_R_TIMEOUT_SECONDS
    r_diagnostics = _read_gsea_diagnostics(result.get("job_dir"))
    input_error_code = ""
    input_error_message = ""
    if r_diagnostics:
        summary["gsea_diagnostics"] = r_diagnostics
        try:
            tie_fraction = float(r_diagnostics.get("score_tie_fraction", 0))
        except (TypeError, ValueError):
            tie_fraction = 0.0
        if tie_fraction > 0:
            warnings = list(result.get("warnings") or [])
            warnings.append(
                f"排序分数存在 {tie_fraction:.1%} 并列值；并列基因内部顺序可能影响 GSEA。"
            )
            result["warnings"] = warnings

        def diagnostic_int(name: str):
            try:
                return int(float(r_diagnostics[name]))
            except (KeyError, TypeError, ValueError):
                return None

        finite_score_count = diagnostic_int("finite_score_count")
        unique_score_count = diagnostic_int("unique_score_count")
        mapped_entrez_count = diagnostic_int("mapped_entrez_count")
        max_gene_set_overlap = diagnostic_int("max_gene_set_overlap")
        if finite_score_count is not None and finite_score_count < 10:
            input_error_code = "gsea_insufficient_valid_genes"
            input_error_message = (
                f"GSEA 有效排序基因仅 {finite_score_count} 个，至少需要 10 个；"
                "gene 必须非空且 score 必须为有限数值。"
            )
        elif unique_score_count is not None and unique_score_count < 2:
            input_error_code = "gsea_constant_scores"
            input_error_message = "GSEA score 缺少变化，至少需要两个不同的有限 score。"
        elif mapped_entrez_count is not None and mapped_entrez_count < 10:
            input_gene_count = diagnostic_int("unique_input_gene_count") or 0
            try:
                mapping_rate = f"{float(r_diagnostics.get('mapping_rate', 0)):.1%}"
            except (TypeError, ValueError):
                mapping_rate = str(r_diagnostics.get("mapping_rate", "未知"))
            input_error_code = "gsea_insufficient_mapped_genes"
            input_error_message = (
                f"GSEA 仅有 {mapped_entrez_count}/{input_gene_count} 个排序基因映射到 "
                f"ENTREZID（映射率 {mapping_rate}），至少需要 10 个；"
                "请检查物种与基因标识。"
            )
        elif max_gene_set_overlap is not None and max_gene_set_overlap < 10:
            input_error_code = "gsea_insufficient_gene_set_overlap"
            input_error_message = (
                f"GSEA 与 Hallmark 基因集的最大重叠仅 {max_gene_set_overlap}，"
                "小于 minGSSize=10。"
            )

    if result.get("status") != "success":
        failure_text = "\n".join(
            str(result.get(key) or "") for key in ("message", "stderr", "stdout")
        ).lower()
        dns_markers = (
            "could not resolve host",
            "couldn't resolve host",
            "name or service not known",
            "temporary failure in name resolution",
        )
        errors = list(result.get("errors") or [])
        if any(marker in failure_text for marker in dns_markers):
            summary["failure_stage"] = "dns_resolution"
            if "gsea_dependency_dns_unavailable" not in errors:
                errors.append("gsea_dependency_dns_unavailable")
            result["message"] = (
                f"GSEA 失败：R 无法解析依赖域名 {GSEA_DEPENDENCY_HOST}。"
                "这不是 HTTP 402 或额度不足；请检查系统 DNS 或网络拦截策略。"
            )
        elif "timed out" in failure_text or "timeout" in failure_text or "超时" in failure_text:
            summary["failure_stage"] = "dependency_download"
            if "gsea_dependency_download_timeout" not in errors:
                errors.append("gsea_dependency_download_timeout")
            result["message"] = (
                "GSEA 依赖下载或执行超时。请检查 MSigDB/Zenodo 可达性后重试；"
                "这不是 HTTP 402 或额度不足。"
            )
        elif input_error_code:
            summary["failure_stage"] = "input_validation"
            if input_error_code not in errors:
                errors.append(input_error_code)
            result["message"] = input_error_message
        else:
            summary.setdefault("failure_stage", "analysis")
            if "gsea_analysis_failed" not in errors:
                errors.append("gsea_analysis_failed")
            if not result.get("message"):
                result["message"] = "GSEA 分析失败，请查看 stderr 与 gsea_diagnostics.csv。"
        if errors:
            result["errors"] = errors

    result["summary"] = summary
    return result


def _annotate_enrichment_component_status(result):
    if not isinstance(result, dict):
        return result

    job_dir = result.get("job_dir")
    if not job_dir:
        return result

    status_path = Path(job_dir) / "enrichment_status.csv"
    if not status_path.is_file():
        return result

    try:
        with status_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return result

    components = {
        str(row.get("component", "")).strip(): {
            "status": str(row.get("status", "")).strip(),
            "message": str(row.get("message", "")).strip(),
            "attempts": str(row.get("attempts", "")).strip(),
        }
        for row in rows
        if str(row.get("component", "")).strip()
    }
    if not components:
        return result

    summary = dict(result.get("summary") or {})
    runner_status = str(result.get("status") or "")
    runner_message = str(result.get("message") or "")
    summary["runner_status"] = runner_status
    if runner_message:
        summary["runner_message"] = runner_message
    summary["runner_timed_out"] = (
        "timeout" in runner_message.lower() or "超时" in runner_message
    )
    summary["components"] = components
    result["summary"] = summary

    failed = [
        f"{name}: {details['message'] or details['status']}"
        for name, details in components.items()
        if details["status"] != "success"
    ]
    if failed:
        warnings = list(result.get("warnings") or [])
        warnings.extend(failed)
        result["warnings"] = warnings
        has_success = any(
            details["status"] in {"success", "partial"}
            for details in components.values()
        )
        if has_success:
            result["status"] = "partial"
            result["message"] = "GO/KEGG 富集部分完成，请查看组件状态。"

    return result

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
def run_go_kegg_enrichment(
    gene_file: str,
    organism: str = "human",
    job_dir: str = None,
):
    org_pkg = "org.Hs.eg.db" if organism.lower() == "human" else "org.Mm.eg.db"
    org_db = "org.Hs.eg.db" if organism.lower() == "human" else "org.Mm.eg.db"
    kegg_org = "hsa" if organism.lower() == "human" else "mmu"
    gene_file = r_escape_string_content(gene_file)

    r_code = f'''
library(data.table)
library(clusterProfiler)
library(enrichplot)
library({org_pkg})
library(ggplot2)

options(timeout = 30L)

gene_df <- fread(smart_read("{gene_file}"), data.table = FALSE)
if (!("gene" %in% colnames(gene_df))) stop("gene_file 必须包含 gene 列")

genes <- unique(as.character(gene_df$gene))
genes <- genes[genes != "" & !is.na(genes)]
if (length(genes) < 5) stop("基因数太少，至少需要5个基因")

eg <- bitr(genes, fromType = "SYMBOL", toType = "ENTREZID", OrgDb = {org_db})
if (is.null(eg) || nrow(eg) == 0) stop("无法将 SYMBOL 转换为 ENTREZID，请检查物种或基因名")

entrez <- unique(eg$ENTREZID)

ego <- NULL
ekegg <- NULL
go_status <- "success"
kegg_status <- "success"
go_message <- ""
kegg_message <- ""

tryCatch({{
  ego <- enrichGO(
    gene = entrez,
    OrgDb = {org_db},
    keyType = "ENTREZID",
    ont = "ALL",
    pAdjustMethod = "BH",
    qvalueCutoff = 0.2,
    readable = TRUE
  )
}}, error = function(e) {{
  go_status <<- "error"
  go_message <<- conditionMessage(e)
}})

kegg_attempts <- 0L
for (attempt in seq_len(2L)) {{
  kegg_attempts <- attempt
  tryCatch({{
    ekegg <- enrichKEGG(
      gene = entrez,
      organism = "{kegg_org}",
      pAdjustMethod = "BH",
      qvalueCutoff = 0.2
    )
  }}, error = function(e) {{
    kegg_status <<- "error"
    kegg_message <<- conditionMessage(e)
  }})
  if (!is.null(ekegg)) {{
    kegg_status <- "success"
    kegg_message <- ""
    break
  }}
  if (attempt < 2L) Sys.sleep(2L)
}}
if (is.null(ekegg) && nzchar(kegg_message)) {{
  kegg_message <- paste0("2 attempts failed: ", kegg_message)
}}

go_df <- if (is.null(ego)) data.frame() else as.data.frame(ego)
kegg_df <- if (is.null(ekegg)) data.frame() else as.data.frame(ekegg)

write.csv(go_df, "go_enrichment_results.csv", row.names = FALSE)
write.csv(kegg_df, "kegg_enrichment_results.csv", row.names = FALSE)

if (!is.null(ego) && nrow(go_df) > 0) {{
  tryCatch({{
    p1 <- dotplot(ego, showCategory = 15) + ggtitle("GO Enrichment")
    ggsave("go_dotplot.png", p1, width = 9, height = 7, dpi = 150)
  }}, error = function(e) {{
    go_status <<- "partial"
    go_message <<- paste("GO table succeeded but plot failed:", conditionMessage(e))
  }})
}}

if (!is.null(ekegg) && nrow(kegg_df) > 0) {{
  tryCatch({{
    p2 <- dotplot(ekegg, showCategory = 15) + ggtitle("KEGG Enrichment")
    ggsave("kegg_dotplot.png", p2, width = 9, height = 7, dpi = 150)
  }}, error = function(e) {{
    kegg_status <<- "partial"
    kegg_message <<- paste("KEGG table succeeded but plot failed:", conditionMessage(e))
  }})
}}

status_df <- data.frame(
  component = c("GO", "KEGG"),
  status = c(go_status, kegg_status),
  message = c(go_message, kegg_message),
  attempts = c(1L, kegg_attempts),
  stringsAsFactors = FALSE
)
write.csv(status_df, "enrichment_status.csv", row.names = FALSE)

cat("GO status:", go_status, "| KEGG status:", kegg_status, "\\n")
cat("生成文件: go_enrichment_results.csv, kegg_enrichment_results.csv, enrichment_status.csv\\n")
if (all(status_df$status == "error")) stop("GO 和 KEGG 富集均失败，请查看 enrichment_status.csv")
'''
    result = run_r_analysis(r_code, job_subdir="go_kegg", job_dir=job_dir)
    return _annotate_enrichment_component_status(result)

@register_tool(
    name="run_gsea_analysis",
    description="对排序基因列表进行 GSEA 分析。输入文件应包含 gene 和 score 两列。",
    timeout=GSEA_R_TIMEOUT_SECONDS,
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
def run_gsea_analysis(
    ranked_gene_file: str,
    organism: str = "human",
    job_dir: str = None,
):
    dns_diagnostic = _diagnose_dns(GSEA_DEPENDENCY_HOST)
    cache_diagnostic = _diagnose_msigdb_cache()
    if dns_diagnostic["status"] != "ok" and not cache_diagnostic["archive_present"]:
        return _gsea_dns_error(dns_diagnostic, cache_diagnostic)

    species = "Homo sapiens" if organism.lower() == "human" else "Mus musculus"
    org_db = "org.Hs.eg.db" if organism.lower() == "human" else "org.Mm.eg.db"
    ranked_gene_file = r_escape_string_content(ranked_gene_file)

    r_code = f'''
msigdb_cache_root <- file.path(Sys.getenv("R_LIBS_USER"), ".cache")
dir.create(msigdb_cache_root, recursive = TRUE, showWarnings = FALSE)
Sys.setenv(R_USER_CACHE_DIR = msigdb_cache_root)
options(timeout = 600L)

library(data.table)
library(clusterProfiler)
library(enrichplot)
library(msigdbr)
library({org_db})
library(ggplot2)

gsea_diagnostics <- data.frame(
  metric = character(), value = character(), stringsAsFactors = FALSE
)
record_gsea_metric <- function(metric, value) {{
  row <- data.frame(
    metric = as.character(metric), value = as.character(value), stringsAsFactors = FALSE
  )
  existing <- match(row$metric, gsea_diagnostics$metric)
  if (is.na(existing)) {{
    gsea_diagnostics <<- rbind(gsea_diagnostics, row)
  }} else {{
    gsea_diagnostics$value[existing] <<- row$value
  }}
  write.csv(gsea_diagnostics, "gsea_diagnostics.csv", row.names = FALSE)
}}

record_gsea_metric("msigdb_cache_root", msigdb_cache_root)
record_gsea_metric("min_gene_set_size", 10L)
BiocParallel::register(BiocParallel::SerialParam())
record_gsea_metric("parallel_backend", "serial")

df <- fread(smart_read("{ranked_gene_file}"), data.table = FALSE)
if (!all(c("gene", "score") %in% colnames(df))) stop("文件必须包含 gene 和 score 列")

record_gsea_metric("input_gene_count", nrow(df))
df$gene <- trimws(as.character(df$gene))
df$score <- suppressWarnings(as.numeric(df$score))
valid_rows <- !is.na(df$gene) & nzchar(df$gene) & is.finite(df$score)
record_gsea_metric("finite_score_count", sum(valid_rows))
df <- df[valid_rows, , drop = FALSE]
if (nrow(df) < 10L) stop("有效排序基因少于 10 个；gene 必须非空且 score 必须为有限数值")

df <- df[order(-abs(df$score), df$gene), , drop = FALSE]
df <- df[!duplicated(df$gene), , drop = FALSE]
record_gsea_metric("unique_input_gene_count", nrow(df))
unique_score_count <- length(unique(df$score))
record_gsea_metric("unique_score_count", unique_score_count)
if (unique_score_count < 2L) stop("score 缺少变化，无法执行 GSEA")
score_tie_fraction <- 1 - unique_score_count / nrow(df)
record_gsea_metric("score_tie_fraction", sprintf("%.6f", score_tie_fraction))

gene_map <- bitr(unique(df$gene), fromType = "SYMBOL", toType = "ENTREZID", OrgDb = {org_db})
if (is.null(gene_map) || nrow(gene_map) == 0L) stop("没有基因可映射到 ENTREZID，请检查物种与基因标识")
df2 <- merge(df, gene_map, by.x = "gene", by.y = "SYMBOL", sort = FALSE)
df2 <- df2[order(-abs(df2$score), df2$gene), , drop = FALSE]
mapped_gene_count <- length(unique(df2$gene))
mapping_rate <- mapped_gene_count / nrow(df)
record_gsea_metric("mapped_gene_count", mapped_gene_count)
record_gsea_metric("mapped_entrez_count", length(unique(df2$ENTREZID)))
record_gsea_metric("mapping_rate", sprintf("%.6f", mapping_rate))
df2 <- df2[!duplicated(df2$ENTREZID), , drop = FALSE]
if (nrow(df2) < 10L) {{
  stop(sprintf(
    "映射到 ENTREZID 的排序基因不足 10 个（%d/%d，%.1f%%）；请检查物种与基因标识",
    nrow(df2), nrow(df), 100 * mapping_rate
  ))
}}

gene_list <- df2$score
names(gene_list) <- as.character(df2$ENTREZID)
gene_list <- sort(gene_list, decreasing = TRUE)
score_type <- if (all(gene_list >= 0)) {{
  "pos"
}} else if (all(gene_list <= 0)) {{
  "neg"
}} else {{
  "std"
}}
record_gsea_metric("score_type", score_type)

m_df <- msigdbr(species = "{species}", collection = "H")
gene_id_col <- if ("ncbi_gene" %in% colnames(m_df)) {{
  "ncbi_gene"
}} else if ("entrez_gene" %in% colnames(m_df)) {{
  "entrez_gene"
}} else {{
  stop("msigdbr 输出缺少 ncbi_gene/entrez_gene 列")
}}
record_gsea_metric("msigdbr_gene_id_column", gene_id_col)

term2gene <- unique(data.frame(
  term = as.character(m_df$gs_name),
  gene = as.character(m_df[[gene_id_col]]),
  stringsAsFactors = FALSE
))
term2gene <- term2gene[
  !is.na(term2gene$term) & nzchar(term2gene$term) &
    !is.na(term2gene$gene) & nzchar(term2gene$gene),
  , drop = FALSE
]
overlap_counts <- table(term2gene$term[term2gene$gene %in% names(gene_list)])
max_gene_set_overlap <- if (length(overlap_counts)) max(overlap_counts) else 0L
record_gsea_metric("max_gene_set_overlap", max_gene_set_overlap)
if (max_gene_set_overlap < 10L) {{
  stop(sprintf(
    "排序基因与 Hallmark 基因集的最大重叠仅 %d，小于 minGSSize=10；无法执行有效 GSEA",
    max_gene_set_overlap
  ))
}}

set.seed(123)
gsea_res <- GSEA(
  geneList = gene_list,
  TERM2GENE = term2gene,
  pvalueCutoff = 0.2,
  minGSSize = 10,
  scoreType = score_type,
  seed = TRUE,
  verbose = FALSE
)
res_df <- as.data.frame(gsea_res)
write.csv(res_df, "gsea_results.csv", row.names = FALSE)

if (nrow(res_df) > 0) {{
  p <- dotplot(gsea_res, showCategory = 15) + ggtitle("GSEA Hallmark")
  ggsave("gsea_dotplot.png", p, width = 9, height = 7, dpi = 150)
}}

cat("GSEA scoreType:", score_type, "| mapped genes:", nrow(df2),
    "| max Hallmark overlap:", max_gene_set_overlap, "\\n")
cat("生成文件: gsea_results.csv, gsea_diagnostics.csv, gsea_dotplot.png\\n")
'''
    result = run_r_analysis(
        r_code,
        timeout=GSEA_R_TIMEOUT_SECONDS,
        job_subdir="gsea",
        job_dir=job_dir,
    )
    return _annotate_gsea_result(result, dns_diagnostic, cache_diagnostic)

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
def run_gsva_analysis(
    expression_file: str,
    group_file: str,
    organism: str = "human",
    job_dir: str = None,
):
    species = "Homo sapiens" if organism.lower() == "human" else "Mus musculus"
    expression_file = r_escape_string_content(expression_file)
    group_file = r_escape_string_content(group_file)

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

m_df <- msigdbr(species = "{species}", collection = "H")
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
    return run_r_analysis(r_code, job_subdir="gsva", job_dir=job_dir)
