from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis
from app.tools.r_preprocess_templates import build_feature_df_preprocess_r

@register_tool(
    name="run_ml_classification_model",
    description="使用机器学习分类模型进行样本分类。支持 logistic、rf、svm。输入文件需包含标签列和特征列。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "CSV文件路径"},
            "label_col": {"type": "string", "description": "标签列名，二分类最好"},
            "algorithm": {
                "type": "string",
                "description": "算法，可选 logistic / rf / svm",
                "default": "rf"
            },
            "test_ratio": {
                "type": "number",
                "description": "测试集比例，默认0.3",
                "default": 0.3
            },
            "feature_preprocess": {
                "type": "string",
                "description": "特征预处理方式：auto / log2 / non_log2 / raw_count / none",
                "default": "auto"
            }
        },
        "required": ["file_path", "label_col"]
    }
)

def run_ml_classification_model(
    file_path: str,
    label_col: str,
    algorithm: str = "rf",
    test_ratio: float = 0.3,
    feature_preprocess: str = "auto"
):
    method_map = {
        "logistic": "glm",
        "rf": "rf",
        "svm": "svmRadial"
    }
    caret_method = method_map.get(algorithm.lower(), "rf")
    family_line = 'family = "binomial",' if algorithm.lower() == "logistic" else ""
    preprocess_r = build_feature_df_preprocess_r(f'setdiff(colnames(df), "{label_col}")', feature_preprocess)

    r_code = f'''
library(data.table)
library(caret)
library(pROC)
library(ggplot2)

{preprocess_r}

smart_read <- function(fp) {{
  full_path <- fp
  if (!file.exists(full_path)) full_path <- file.path(UPLOAD_DIR, fp)
  if (!file.exists(full_path)) stop(paste("文件不存在:", fp))
  fread(full_path, data.table = FALSE)
}}

set.seed(123)
df <- smart_read("{file_path}")

if (!("{label_col}" %in% colnames(df))) stop("找不到标签列")
df <- df[complete.cases(df), ]
if (nrow(df) < 20) stop("样本数太少，无法稳定建模")

prep <- auto_preprocess_feature_df(df, feature_cols, feature_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df[["{label_col}"]] <- as.factor(df[["{label_col}"]])
if (length(unique(df[["{label_col}"]])) != 2) stop("当前工具仅支持二分类任务")

inTrain <- createDataPartition(df[["{label_col}"]], p = {1-float(test_ratio)}, list = FALSE)
train_df <- df[inTrain, , drop = FALSE]
test_df  <- df[-inTrain, , drop = FALSE]

ctrl <- trainControl(
  method = "cv",
  number = 5,
  classProbs = TRUE,
  summaryFunction = twoClassSummary,
  savePredictions = TRUE
)

formula_str <- as.formula(paste("{label_col}", "~ ."))

model <- train(
  formula_str,
  data = train_df,
  method = "{caret_method}",
  metric = "ROC",
  trControl = ctrl,
  {family_line}
  preProcess = c("center", "scale")
)

pred_class <- predict(model, newdata = test_df)
pred_prob <- predict(model, newdata = test_df, type = "prob")

cm <- confusionMatrix(pred_class, test_df[["{label_col}"]])
capture.output(cm, file = "ml_confusion_matrix.txt")

positive_class <- levels(test_df[["{label_col}"]])[2]
roc_obj <- roc(test_df[["{label_col}"]], pred_prob[[positive_class]])

png("ml_roc_curve.png", width = 1200, height = 900, res = 150)
plot(roc_obj, col = "#2E86DE", lwd = 3, main = paste("ROC Curve -", "{algorithm}"))
dev.off()

metrics_df <- data.frame(
  algorithm = "{algorithm}",
  auc = as.numeric(auc(roc_obj)),
  accuracy = cm$overall["Accuracy"],
  kappa = cm$overall["Kappa"]
)
write.csv(metrics_df, "ml_metrics.csv", row.names = FALSE)

pred_out <- data.frame(
  truth = test_df[["{label_col}"]],
  pred = pred_class
)
for (cn in colnames(pred_prob)) {{
  pred_out[[paste0("prob_", cn)]] <- pred_prob[[cn]]
}}
write.csv(pred_out, "ml_predictions.csv", row.names = FALSE)

if ("rf" == "{algorithm}") {{
  imp <- varImp(model)
  imp_df <- data.frame(feature = rownames(imp$importance), importance = imp$importance[,1])
  imp_df <- imp_df[order(-imp_df$importance), ]
  write.csv(imp_df, "ml_feature_importance.csv", row.names = FALSE)

  plot_df <- head(imp_df, 20)
  plot_df$feature <- factor(plot_df$feature, levels = rev(plot_df$feature))
  p <- ggplot(plot_df, aes(x = feature, y = importance)) +
    geom_col(fill = "#2E86DE") +
    coord_flip() +
    theme_bw() +
    labs(title = "Top Feature Importance", x = "", y = "Importance")
  ggsave("ml_feature_importance_top20.png", p, width = 8, height = 6, dpi = 150)
}}

cat("生成文件: preprocess_log2_info.csv, ml_confusion_matrix.txt, ml_roc_curve.png, ml_metrics.csv, ml_predictions.csv\\n")
'''
    return run_r_analysis(r_code)


@register_tool(
    name="run_ml_feature_selection_lasso",
    description="使用 LASSO 进行特征选择，输出非零系数特征、交叉验证曲线和系数路径图。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "CSV文件路径"},
            "label_col": {"type": "string", "description": "标签列名，建议二分类"},
            "feature_preprocess": {
                "type": "string",
                "description": "特征预处理方式：auto / log2 / non_log2 / raw_count / none",
                "default": "auto"
            }
        },
        "required": ["file_path", "label_col"]
    }
)
def run_ml_feature_selection_lasso(
    file_path: str,
    label_col: str,
    feature_preprocess: str = "auto"
):
    preprocess_r = build_feature_df_preprocess_r(f'setdiff(colnames(df), "{label_col}")', feature_preprocess)

    r_code = f'''
library(data.table)
library(glmnet)

{preprocess_r}

smart_read <- function(fp) {{
  full_path <- fp
  if (!file.exists(full_path)) full_path <- file.path(UPLOAD_DIR, fp)
  if (!file.exists(full_path)) stop(paste("文件不存在:", fp))
  fread(full_path, data.table = FALSE)
}}

df <- smart_read("{file_path}")
if (!("{label_col}" %in% colnames(df))) stop("找不到标签列")
df <- df[complete.cases(df), ]
if (nrow(df) < 20) stop("样本数太少")

prep <- auto_preprocess_feature_df(df, feature_cols, feature_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

y <- as.factor(df[["{label_col}"]])
if (length(levels(y)) != 2) stop("当前仅支持二分类")
x <- df[, setdiff(colnames(df), "{label_col}"), drop = FALSE]
x <- as.matrix(x)
mode(x) <- "numeric"

y_num <- ifelse(y == levels(y)[2], 1, 0)

set.seed(123)
cvfit <- cv.glmnet(x, y_num, family = "binomial", alpha = 1)

png("lasso_feature_cv_curve.png", width = 1200, height = 900, res = 150)
plot(cvfit)
dev.off()

png("lasso_feature_coef_path.png", width = 1200, height = 900, res = 150)
plot(glmnet(x, y_num, family = "binomial", alpha = 1), xvar = "lambda")
dev.off()

coef_mat <- coef(cvfit, s = "lambda.min")
coef_df <- data.frame(
  feature = rownames(coef_mat),
  coefficient = as.numeric(coef_mat)
)
coef_df <- coef_df[coef_df$coefficient != 0, ]
write.csv(coef_df, "lasso_feature_selection.csv", row.names = FALSE)

cat("生成文件: preprocess_log2_info.csv, lasso_feature_cv_curve.png, lasso_feature_coef_path.png, lasso_feature_selection.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="ml_lasso_feature_selection")


@register_tool(
    name="run_multi_model_comparison",
    description="使用多个分类模型进行比较，输出各模型 AUC、Accuracy、Kappa。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "label_col": {"type": "string"},
            "algorithms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "模型列表，如 ['logistic','rf','svm']",
                "default": ["logistic", "rf", "svm"]
            },
            "test_ratio": {
                "type": "number",
                "default": 0.3
            },
            "feature_preprocess": {
                "type": "string",
                "description": "特征预处理方式：auto / log2 / non_log2 / raw_count / none",
                "default": "auto"
            }
        },
        "required": ["file_path", "label_col"]
    }
)
def run_multi_model_comparison(
    file_path: str,
    label_col: str,
    algorithms: list = None,
    test_ratio: float = 0.3,
    feature_preprocess: str = "auto"
):
    algorithms = algorithms or ["logistic", "rf", "svm"]
    method_map = {
        "logistic": "glm",
        "rf": "rf",
        "svm": "svmRadial"
    }
    algos_r = "c(" + ", ".join([f'"{a}"' for a in algorithms if a in method_map]) + ")"
    preprocess_r = build_feature_df_preprocess_r(f'setdiff(colnames(df), "{label_col}")', feature_preprocess)

    r_code = f'''
library(data.table)
library(caret)
library(pROC)

{preprocess_r}

smart_read <- function(fp) {{
  full_path <- fp
  if (!file.exists(full_path)) full_path <- file.path(UPLOAD_DIR, fp)
  if (!file.exists(full_path)) stop(paste("文件不存在:", fp))
  fread(full_path, data.table = FALSE)
}}

set.seed(123)
df <- smart_read("{file_path}")

if (!("{label_col}" %in% colnames(df))) stop("找不到标签列")
df <- df[complete.cases(df), ]
if (nrow(df) < 20) stop("样本数太少")

prep <- auto_preprocess_feature_df(df, feature_cols, feature_preprocess_mode)
df <- prep$data
write.csv(prep$info, "preprocess_log2_info.csv", row.names = FALSE)

df[["{label_col}"]] <- as.factor(df[["{label_col}"]])
if (length(unique(df[["{label_col}"]])) != 2) stop("当前仅支持二分类")

inTrain <- createDataPartition(df[["{label_col}"]], p = {1-float(test_ratio)}, list = FALSE)
train_df <- df[inTrain, , drop = FALSE]
test_df  <- df[-inTrain, , drop = FALSE]

ctrl <- trainControl(
  method = "cv",
  number = 5,
  classProbs = TRUE,
  summaryFunction = twoClassSummary
)

algorithms <- {algos_r}
method_map <- c(logistic = "glm", rf = "rf", svm = "svmRadial")
results <- list()

for (alg in algorithms) {{
  method_name <- method_map[[alg]]

  fit <- train(
    as.formula(paste("{label_col}", "~ .")),
    data = train_df,
    method = method_name,
    metric = "ROC",
    trControl = ctrl,
    preProcess = c("center", "scale"),
    family = if (alg == "logistic") "binomial" else NULL
  )

  pred_class <- predict(fit, newdata = test_df)
  pred_prob <- predict(fit, newdata = test_df, type = "prob")
  cm <- confusionMatrix(pred_class, test_df[["{label_col}"]])

  positive_class <- levels(test_df[["{label_col}"]])[2]
  roc_obj <- roc(test_df[["{label_col}"]], pred_prob[[positive_class]])

  results[[alg]] <- data.frame(
    algorithm = alg,
    auc = as.numeric(auc(roc_obj)),
    accuracy = as.numeric(cm$overall["Accuracy"]),
    kappa = as.numeric(cm$overall["Kappa"])
  )
}}

res_df <- do.call(rbind, results)
write.csv(res_df, "multi_model_comparison.csv", row.names = FALSE)

cat("生成文件: preprocess_log2_info.csv, multi_model_comparison.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="multi_model_comparison")