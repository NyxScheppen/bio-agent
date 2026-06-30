from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis
from app.tools.r_preprocess_templates import build_expression_preprocess_r


@register_tool(
    name="run_single_gene_survival_analysis",
    description="对指定基因进行单基因生存分析，生成 Kaplan-Meier 曲线、Cox 回归结果和处理后的数据表。输入文件应包含目标基因表达列、生存时间列和结局状态列。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "上传的CSV文件路径，例如 survival_data.csv"
            },
            "gene": {
                "type": "string",
                "description": "目标基因名，例如 TP53"
            },
            "time_col": {
                "type": "string",
                "description": "生存时间列名，例如 OS_time"
            },
            "status_col": {
                "type": "string",
                "description": "结局状态列名，通常0/1，例如 OS_status"
            },
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["file_path", "gene", "time_col", "status_col"]
    }
)
def run_single_gene_survival_analysis(
    file_path: str,
    gene: str,
    time_col: str,
    status_col: str,
    expression_preprocess: str = "auto"
):
    preprocess_r = build_expression_preprocess_r(f'c("{gene}")', expression_preprocess)

    r_code = f'''
library(data.table)
library(survival)
library(survminer)
library(ggplot2)

{preprocess_r}

df <- fread(smart_read("{file_path}"), data.table = FALSE)

if (!("{gene}" %in% colnames(df))) stop("找不到目标基因列")
if (!("{time_col}" %in% colnames(df))) stop("找不到生存时间列")
if (!("{status_col}" %in% colnames(df))) stop("找不到生存状态列")

prep <- auto_preprocess_expression(df, expr_cols, expression_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df[["{time_col}"]] <- suppressWarnings(as.numeric(df[["{time_col}"]]))
df[["{status_col}"]] <- suppressWarnings(as.numeric(df[["{status_col}"]]))
df[["{gene}"]] <- suppressWarnings(as.numeric(df[["{gene}"]]))

df <- df[!is.na(df[["{gene}"]]) & !is.na(df[["{time_col}"]]) & !is.na(df[["{status_col}"]]), ]
if (nrow(df) < 5) stop("有效样本数太少，无法进行生存分析")

med <- median(df[["{gene}"]], na.rm = TRUE)
df$group <- ifelse(df[["{gene}"]] >= med, "High", "Low")
df$group <- factor(df$group, levels = c("Low", "High"))

fit <- survfit(Surv(df[["{time_col}"]], df[["{status_col}"]]) ~ group, data = df)

p <- ggsurvplot(
  fit,
  data = df,
  pval = TRUE,
  risk.table = TRUE,
  conf.int = FALSE,
  palette = c("#2E86DE", "#E74C3C"),
  title = paste("{gene}", "Kaplan-Meier Survival Curve")
)

png("single_gene_km.png", width = 1400, height = 1000, res = 150)
print(p)
dev.off()

cox_fit <- coxph(Surv(df[["{time_col}"]], df[["{status_col}"]]) ~ df[["{gene}"]], data = df)
cox_sum <- summary(cox_fit)

cox_df <- data.frame(
  variable = rownames(cox_sum$coefficients),
  coef = cox_sum$coefficients[, "coef"],
  HR = cox_sum$conf.int[, "exp(coef)"],
  lower95 = cox_sum$conf.int[, "lower .95"],
  upper95 = cox_sum$conf.int[, "upper .95"],
  pvalue = cox_sum$coefficients[, "Pr(>|z|)"],
  check.names = FALSE
)

write.csv(cox_df, "single_gene_cox_result.csv", row.names = FALSE)
write.csv(df, "single_gene_survival_processed.csv", row.names = FALSE)

cat("生成文件: preprocess_log2_info.csv, single_gene_km.png, single_gene_cox_result.csv, single_gene_survival_processed.csv\\n")
'''
    return run_r_analysis(r_code)


@register_tool(
    name="run_univariate_cox_batch",
    description="对多个特征批量进行单因素 Cox 回归分析，输出结果表和森林图。适合预后候选基因初筛。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "包含生存和特征列的CSV文件"},
            "feature_cols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "待分析的特征列名列表"
            },
            "time_col": {"type": "string", "description": "生存时间列名"},
            "status_col": {"type": "string", "description": "结局状态列名"},
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["file_path", "feature_cols", "time_col", "status_col"]
    }
)
def run_univariate_cox_batch(
    file_path: str,
    feature_cols: list,
    time_col: str,
    status_col: str,
    expression_preprocess: str = "auto"
):
    feature_cols_r = "c(" + ", ".join([f'"{x}"' for x in feature_cols]) + ")"
    preprocess_r = build_expression_preprocess_r(feature_cols_r, expression_preprocess)

    r_code = f'''
library(data.table)
library(survival)
library(ggplot2)

{preprocess_r}

df <- fread(smart_read("{file_path}"), data.table = FALSE)
features <- {feature_cols_r}

missing_cols <- setdiff(c(features, "{time_col}", "{status_col}"), colnames(df))
if (length(missing_cols) > 0) stop(paste("缺少列:", paste(missing_cols, collapse = ", ")))

prep <- auto_preprocess_expression(df, expr_cols, expression_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df[["{time_col}"]] <- suppressWarnings(as.numeric(df[["{time_col}"]]))
df[["{status_col}"]] <- suppressWarnings(as.numeric(df[["{status_col}"]]))

results <- list()

for (g in features) {{
  df[[g]] <- suppressWarnings(as.numeric(df[[g]]))
  subdf <- df[, c(g, "{time_col}", "{status_col}"), drop = FALSE]
  subdf <- subdf[complete.cases(subdf), ]
  if (nrow(subdf) < 5) next

  fml <- as.formula(paste0("Surv(`{time_col}`, `{status_col}`) ~ `", g, "`"))
  fit <- tryCatch(coxph(fml, data = subdf), error = function(e) NULL)
  if (is.null(fit)) next
  s <- summary(fit)

  results[[g]] <- data.frame(
    feature = g,
    coef = s$coefficients[1, "coef"],
    HR = s$conf.int[1, "exp(coef)"],
    lower95 = s$conf.int[1, "lower .95"],
    upper95 = s$conf.int[1, "upper .95"],
    pvalue = s$coefficients[1, "Pr(>|z|)"]
  )
}}

if (length(results) == 0) stop("没有成功完成任何单因素 Cox 分析")

res_df <- do.call(rbind, results)
res_df <- res_df[order(res_df$pvalue), ]
write.csv(res_df, "univariate_cox_results.csv", row.names = FALSE)

top_n <- min(20, nrow(res_df))
plot_df <- res_df[1:top_n, ]
plot_df$feature <- factor(plot_df$feature, levels = rev(plot_df$feature))

p <- ggplot(plot_df, aes(x = feature, y = HR)) +
  geom_point(color = "#2E86DE", size = 2.8) +
  geom_errorbar(aes(ymin = lower95, ymax = upper95), width = 0.2, color = "#555555") +
  geom_hline(yintercept = 1, linetype = 2, color = "red") +
  coord_flip() +
  theme_bw(base_size = 12) +
  labs(title = "Univariate Cox Forest Plot", x = "", y = "Hazard Ratio")

ggsave("univariate_cox_forest.png", p, width = 8, height = 6, dpi = 150)

cat("生成文件: preprocess_log2_info.csv, univariate_cox_results.csv, univariate_cox_forest.png\\n")
'''
    return run_r_analysis(r_code)


@register_tool(
    name="run_lasso_cox_model",
    description="构建 LASSO-Cox 预后模型，输出 lambda 曲线、系数路径图和筛选特征结果。输入文件应包含生存列和候选特征列。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "CSV文件路径"},
            "feature_cols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "候选特征列名列表"
            },
            "time_col": {"type": "string", "description": "生存时间列名"},
            "status_col": {"type": "string", "description": "生存状态列名"},
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["file_path", "feature_cols", "time_col", "status_col"]
    }
)
def run_lasso_cox_model(
    file_path: str,
    feature_cols: list,
    time_col: str,
    status_col: str,
    expression_preprocess: str = "auto"
):
    feature_cols_r = "c(" + ", ".join([f'"{x}"' for x in feature_cols]) + ")"
    preprocess_r = build_expression_preprocess_r(feature_cols_r, expression_preprocess)

    r_code = f'''
library(data.table)
library(glmnet)
library(survival)

{preprocess_r}

df <- fread(smart_read("{file_path}"), data.table = FALSE)
features <- {feature_cols_r}

missing_cols <- setdiff(c(features, "{time_col}", "{status_col}"), colnames(df))
if (length(missing_cols) > 0) stop(paste("缺少列:", paste(missing_cols, collapse = ", ")))

prep <- auto_preprocess_expression(df, expr_cols, expression_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df[["{time_col}"]] <- suppressWarnings(as.numeric(df[["{time_col}"]]))
df[["{status_col}"]] <- suppressWarnings(as.numeric(df[["{status_col}"]]))

subdf <- df[, c(features, "{time_col}", "{status_col}"), drop = FALSE]
subdf <- subdf[complete.cases(subdf), ]
if (nrow(subdf) < 10) stop("有效样本太少，无法进行 LASSO-Cox")

x <- as.matrix(subdf[, features, drop = FALSE])
mode(x) <- "numeric"
y <- Surv(subdf[["{time_col}"]], subdf[["{status_col}"]])

cvfit <- cv.glmnet(x, y, family = "cox", alpha = 1)

png("lasso_cv_curve.png", width = 1200, height = 900, res = 150)
plot(cvfit)
dev.off()

png("lasso_coef_path.png", width = 1200, height = 900, res = 150)
plot(glmnet(x, y, family = "cox", alpha = 1), xvar = "lambda")
dev.off()

coef_mat <- coef(cvfit, s = "lambda.min")
coef_df <- data.frame(
  feature = rownames(coef_mat),
  coefficient = as.numeric(coef_mat)
)
coef_df <- coef_df[coef_df$coefficient != 0, ]
write.csv(coef_df, "lasso_selected_features.csv", row.names = FALSE)

cat("生成文件: preprocess_log2_info.csv, lasso_cv_curve.png, lasso_coef_path.png, lasso_selected_features.csv\\n")
'''
    return run_r_analysis(r_code)


@register_tool(
    name="run_multivariate_cox_analysis",
    description="对多个特征执行多因素 Cox 回归分析，输出结果表。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "feature_cols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "特征列名列表"
            },
            "time_col": {"type": "string"},
            "status_col": {"type": "string"},
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["file_path", "feature_cols", "time_col", "status_col"]
    }
)
def run_multivariate_cox_analysis(
    file_path: str,
    feature_cols: list,
    time_col: str,
    status_col: str,
    expression_preprocess: str = "auto"
):
    feature_cols_r = "c(" + ", ".join([f'"{x}"' for x in feature_cols]) + ")"
    preprocess_r = build_expression_preprocess_r(feature_cols_r, expression_preprocess)

    r_code = f'''
library(data.table)
library(survival)

{preprocess_r}

df <- fread(smart_read("{file_path}"), data.table = FALSE)
features <- {feature_cols_r}

missing_cols <- setdiff(c(features, "{time_col}", "{status_col}"), colnames(df))
if (length(missing_cols) > 0) stop(paste("缺少列:", paste(missing_cols, collapse = ", ")))

prep <- auto_preprocess_expression(df, expr_cols, expression_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df[["{time_col}"]] <- suppressWarnings(as.numeric(df[["{time_col}"]]))
df[["{status_col}"]] <- suppressWarnings(as.numeric(df[["{status_col}"]]))

subdf <- df[, c(features, "{time_col}", "{status_col}"), drop = FALSE]
subdf <- subdf[complete.cases(subdf), ]
if (nrow(subdf) < 10) stop("有效样本太少")

formula_str <- paste("Surv(`{time_col}`, `{status_col}`) ~", paste(sprintf("`%s`", features), collapse = " + "))
fit <- coxph(as.formula(formula_str), data = subdf)
s <- summary(fit)

res_df <- data.frame(
  variable = rownames(s$coefficients),
  coef = s$coefficients[, "coef"],
  HR = s$conf.int[, "exp(coef)"],
  lower95 = s$conf.int[, "lower .95"],
  upper95 = s$conf.int[, "upper .95"],
  pvalue = s$coefficients[, "Pr(>|z|)"],
  check.names = FALSE
)

write.csv(res_df, "multivariate_cox_results.csv", row.names = FALSE)
cat("生成文件: preprocess_log2_info.csv, multivariate_cox_results.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="multivariate_cox")


@register_tool(
    name="run_prognostic_risk_model",
    description="基于给定特征构建 Cox 风险评分模型，输出风险评分、风险分组和热图。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "feature_cols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "进入模型的特征列名"
            },
            "time_col": {"type": "string"},
            "status_col": {"type": "string"},
            "expression_preprocess": {
                "type": "string",
                "description": "表达值预处理方式：auto / log2 / non_log2 / raw_count",
                "default": "auto"
            }
        },
        "required": ["file_path", "feature_cols", "time_col", "status_col"]
    }
)
def run_prognostic_risk_model(
    file_path: str,
    feature_cols: list,
    time_col: str,
    status_col: str,
    expression_preprocess: str = "auto"
):
    feature_cols_r = "c(" + ", ".join([f'"{x}"' for x in feature_cols]) + ")"
    preprocess_r = build_expression_preprocess_r(feature_cols_r, expression_preprocess)

    r_code = f'''
library(data.table)
library(survival)
library(pheatmap)
library(ggplot2)

{preprocess_r}

df <- fread(smart_read("{file_path}"), data.table = FALSE)
features <- {feature_cols_r}

missing_cols <- setdiff(c(features, "{time_col}", "{status_col}"), colnames(df))
if (length(missing_cols) > 0) stop(paste("缺少列:", paste(missing_cols, collapse = ", ")))

prep <- auto_preprocess_expression(df, expr_cols, expression_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df[["{time_col}"]] <- suppressWarnings(as.numeric(df[["{time_col}"]]))
df[["{status_col}"]] <- suppressWarnings(as.numeric(df[["{status_col}"]]))

subdf <- df[, c(features, "{time_col}", "{status_col}"), drop = FALSE]
subdf <- subdf[complete.cases(subdf), ]
if (nrow(subdf) < 10) stop("有效样本太少")

formula_str <- paste("Surv(`{time_col}`, `{status_col}`) ~", paste(sprintf("`%s`", features), collapse = " + "))
fit <- coxph(as.formula(formula_str), data = subdf)

subdf$risk_score <- as.numeric(predict(fit, type = "lp"))
med <- median(subdf$risk_score, na.rm = TRUE)
subdf$risk_group <- ifelse(subdf$risk_score >= med, "High", "Low")
subdf$risk_group <- factor(subdf$risk_group, levels = c("Low", "High"))

subdf <- subdf[order(subdf$risk_score), ]
subdf$index <- seq_len(nrow(subdf))
write.csv(subdf, "risk_model_scored_data.csv", row.names = FALSE)

p1 <- ggplot(subdf, aes(x = index, y = risk_score, color = risk_group)) +
  geom_point() +
  theme_bw() +
  labs(title = "Risk Score Distribution", x = "Sample Rank", y = "Risk Score")
ggsave("risk_score_distribution.png", p1, width = 8, height = 5, dpi = 150)

p2 <- ggplot(subdf, aes(x = index, y = .data[["{time_col}"]], color = as.factor(.data[["{status_col}"]]))) +
  geom_point() +
  theme_bw() +
  labs(title = "Survival Status Distribution", x = "Sample Rank", y = "{time_col}")
ggsave("risk_survival_status.png", p2, width = 8, height = 5, dpi = 150)

heat_mat <- as.matrix(subdf[, features, drop = FALSE])
mode(heat_mat) <- "numeric"
rownames(heat_mat) <- paste0("Sample_", seq_len(nrow(subdf)))

png("risk_model_heatmap.png", width = 1200, height = 1000, res = 150)
pheatmap(
  t(heat_mat),
  scale = "row",
  annotation_col = data.frame(
    RiskGroup = subdf$risk_group,
    row.names = rownames(heat_mat)
  )
)
dev.off()

coef_df <- data.frame(
  feature = names(coef(fit)),
  coefficient = as.numeric(coef(fit))
)
write.csv(coef_df, "risk_model_coefficients.csv", row.names = FALSE)

cat("生成文件: preprocess_log2_info.csv, risk_model_scored_data.csv, risk_score_distribution.png, risk_survival_status.png, risk_model_heatmap.png, risk_model_coefficients.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="risk_model")


@register_tool(
    name="run_risk_group_survival_analysis",
    description="基于风险评分结果执行高低风险组 Kaplan-Meier 生存分析。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "包含 risk_group、time、status 的CSV文件"},
            "time_col": {"type": "string"},
            "status_col": {"type": "string"},
            "risk_group_col": {
                "type": "string",
                "description": "风险分组列名",
                "default": "risk_group"
            }
        },
        "required": ["file_path", "time_col", "status_col"]
    }
)
def run_risk_group_survival_analysis(file_path: str, time_col: str, status_col: str, risk_group_col: str = "risk_group"):
    r_code = f'''
library(data.table)
library(survival)
library(survminer)

df <- fread(smart_read("{file_path}"), data.table = FALSE)

missing_cols <- setdiff(c("{time_col}", "{status_col}", "{risk_group_col}"), colnames(df))
if (length(missing_cols) > 0) stop(paste("缺少列:", paste(missing_cols, collapse = ", ")))

df <- df[complete.cases(df[, c("{time_col}", "{status_col}", "{risk_group_col}")]), ]
if (nrow(df) < 10) stop("有效样本太少")

df[["{risk_group_col}"]] <- factor(df[["{risk_group_col}"]], levels = c("Low", "High"))
fit <- survfit(Surv(df[["{time_col}"]], df[["{status_col}"]]) ~ df[["{risk_group_col}"]], data = df)

p <- ggsurvplot(
  fit,
  data = df,
  pval = TRUE,
  risk.table = TRUE,
  conf.int = FALSE,
  palette = c("#2E86DE", "#E74C3C"),
  title = "Risk Group Kaplan-Meier Curve"
)

png("risk_group_km.png", width = 1400, height = 1000, res = 150)
print(p)
dev.off()

cat("生成文件: risk_group_km.png\\n")
'''
    return run_r_analysis(r_code, job_subdir="risk_group_km")


@register_tool(
    name="run_time_roc_analysis",
    description="执行 time-dependent ROC 分析。输入文件应包含生存时间、状态和风险评分列。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "time_col": {"type": "string"},
            "status_col": {"type": "string"},
            "score_col": {"type": "string", "description": "风险评分列名"},
            "times": {
                "type": "array",
                "items": {"type": "number"},
                "description": "时间点列表，如 [365, 1095, 1825]"
            }
        },
        "required": ["file_path", "time_col", "status_col", "score_col", "times"]
    }
)
def run_time_roc_analysis(file_path: str, time_col: str, status_col: str, score_col: str, times: list):
    times = [float(t) for t in times]
    times_r = "c(" + ", ".join([str(x) for x in times]) + ")"

    r_code = f'''
library(data.table)
library(timeROC)

df <- fread(smart_read("{file_path}"), data.table = FALSE)

missing_cols <- setdiff(c("{time_col}", "{status_col}", "{score_col}"), colnames(df))
if (length(missing_cols) > 0) stop(paste("缺少列:", paste(missing_cols, collapse = ", ")))

df <- df[complete.cases(df[, c("{time_col}", "{status_col}", "{score_col}")]), ]
if (nrow(df) < 10) stop("有效样本太少")

roc_res <- timeROC(
  T = df[["{time_col}"]],
  delta = df[["{status_col}"]],
  marker = df[["{score_col}"]],
  cause = 1,
  times = {times_r},
  iid = TRUE
)

png("time_roc_curve.png", width = 1200, height = 900, res = 150)
plot(roc_res, time = {times[0]}, col = "#E74C3C", lwd = 2)
if (length({times_r}) >= 2) {{
  for (tt in {times_r}[-1]) {{
    plot(roc_res, time = tt, add = TRUE, lwd = 2)
  }}
}}
legend("bottomright",
       legend = paste0({times_r}, ": AUC=", round(roc_res$AUC, 4)),
       lwd = 2,
       bty = "n")
dev.off()

auc_df <- data.frame(
  time = {times_r},
  auc = roc_res$AUC
)
write.csv(auc_df, "time_roc_auc.csv", row.names = FALSE)

cat("生成文件: time_roc_curve.png, time_roc_auc.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="time_roc")