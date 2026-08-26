suppressMessages(library(limma))

args <- jsonlite::fromJSON(file("stdin"))

mat <- read.delim(args$matrix_file, row.names = 1, check.names = FALSE)

# 校验：样本名必须都在矩阵列中（与 11-single-gene 缺失样本报错对齐）
missing <- setdiff(c(args$case, args$control), colnames(mat))
if (length(missing) > 0) {
  stop("样本不在矩阵中: ", paste(missing, collapse = ", "))
}

# case/control 顺序与 factor levels 一致（control 在前、case 在后）
case <- args$case
control <- args$control
if (length(case) < 2 || length(control) < 2) {
  stop("case/control 与矩阵对齐后样本不足")
}
mat <- mat[, c(control, case), drop = FALSE]

group <- factor(c(rep("control", length(control)), rep("case", length(case))),
                levels = c("control", "case"))
design <- model.matrix(~ group)
fit <- limma::lmFit(mat, design)
fit <- limma::eBayes(fit)
res <- limma::topTable(fit, coef = 2, number = Inf, sort.by = "p")

genes <- data.frame(
  gene = rownames(res),
  logFC = res$logFC,
  p_value = res$P.Value,
  adj_p_value = res$adj.P.Val,
  stringsAsFactors = FALSE
)
top <- utils::head(genes[order(genes$p_value), ], 50)

cat(jsonlite::toJSON(list(genes = top), auto_unbox = TRUE))
