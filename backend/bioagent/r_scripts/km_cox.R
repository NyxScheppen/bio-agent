suppressMessages(library(survival))

args <- jsonlite::fromJSON(file("stdin"))
time_col <- if (is.null(args$time_col)) "time" else args$time_col
event_col <- if (is.null(args$event_col)) "event" else args$event_col
group_col <- if (is.null(args$group_col)) "group" else args$group_col

clin <- read.delim(args$clinical_file, row.names = 1, check.names = FALSE)
for (col in c(time_col, event_col, group_col)) {
  if (!(col %in% colnames(clin))) {
    stop("临床表缺少列: ", col)
  }
}
time <- as.numeric(clin[[time_col]])
event <- as.numeric(clin[[event_col]])
group <- factor(clin[[group_col]])
if (length(levels(group)) != 2) {
  stop("group 需恰 2 组")
}

surv_obj <- survival::Surv(time, event)
fit <- survival::survfit(surv_obj ~ group)

# survfit 的 time/surv 跨 strata 拼接，strata 给出每层样本数 → 按层切片
idx <- 0
km_curves <- list()
for (i in seq_along(fit$strata)) {
  n <- fit$strata[i]
  sel <- (idx + 1):(idx + n)
  km_curves[[i]] <- list(
    group = jsonlite::unbox(levels(group)[i]),
    time = as.numeric(fit$time[sel]),
    survival = as.numeric(fit$surv[sel])
  )
  idx <- idx + n
}

lr <- survival::survdiff(surv_obj ~ group)
logrank_p <- 1 - stats::pchisq(lr$chisq, df = length(levels(group)) - 1)

cox <- survival::coxph(surv_obj ~ group)
cox_hr <- as.numeric(exp(stats::coef(cox)))
# Cox HR 参照组 = factor 第一水平（字母序更小者）：HR = 第二组 vs 第一组，>1 表示第二组风险更高
cox_sum <- summary(cox)$coefficients
cox_p <- as.numeric(if (nrow(cox_sum) >= 1) cox_sum[1, "Pr(>|z|)"] else NA)

result <- list(
  km_curves = km_curves,
  logrank_p = jsonlite::unbox(logrank_p),
  cox_hr = jsonlite::unbox(cox_hr),
  cox_p = jsonlite::unbox(cox_p)
)
cat(jsonlite::toJSON(result))
