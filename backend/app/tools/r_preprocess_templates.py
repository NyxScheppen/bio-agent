def build_expression_preprocess_r(expr_cols_r: str, preprocess_mode: str = "auto") -> str:
    """
    用于 survival / Cox / 预后模型这类“data.frame 中指定表达列”的预处理。
    适用场景：
    - 单基因生存
    - 单因素 Cox
    - 多因素 Cox
    - LASSO-Cox
    - 风险模型

    R 侧输出：
    - expr_cols
    - expression_preprocess_mode
    - auto_preprocess_expression(df, expr_cols, mode)
    """
    return f'''
expr_cols <- {expr_cols_r}
expression_preprocess_mode <- "{preprocess_mode}"

coerce_numeric_cols <- function(df, cols) {{
  for (cn in cols) {{
    df[[cn]] <- suppressWarnings(as.numeric(df[[cn]]))
  }}
  df
}}

auto_preprocess_expression <- function(df, expr_cols, mode = "auto") {{
  expr_cols <- intersect(expr_cols, colnames(df))
  if (length(expr_cols) == 0) stop("没有找到可预处理的表达列")

  df <- coerce_numeric_cols(df, expr_cols)

  vals <- unlist(df[, expr_cols, drop = FALSE], use.names = FALSE)
  vals <- vals[!is.na(vals) & is.finite(vals)]
  if (length(vals) == 0) stop("表达列没有有效数值")

  transformed <- FALSE
  reason <- ""

  if (mode == "raw_count") {{
    stop("检测到 raw_count 模式。预后/生存模型不应直接使用原始 count，请先标准化，或使用 log2(count+1) 后再分析。")
  }} else if (mode == "log2") {{
    reason <- "用户指定数据已完成 log2 变换，未再处理。"
  }} else if (mode == "non_log2") {{
    if (any(vals < 0, na.rm = TRUE)) stop("表达值存在负数，无法执行 log2(x+1)")
    df[, expr_cols] <- lapply(df[, expr_cols, drop = FALSE], function(x) log2(x + 1))
    transformed <- TRUE
    reason <- "用户指定数据未做 log2，已执行 log2(x+1)。"
  }} else if (mode == "auto") {{
    q99 <- as.numeric(stats::quantile(vals, 0.99, na.rm = TRUE))
    vmax <- max(vals, na.rm = TRUE)

    if (any(vals < 0, na.rm = TRUE)) {{
      reason <- paste0("检测到负值，推测已做中心化/标准化或对数变换，未执行 log2。max=", round(vmax, 4))
    }} else if (vmax > 50 || q99 > 20) {{
      df[, expr_cols] <- lapply(df[, expr_cols, drop = FALSE], function(x) log2(x + 1))
      transformed <- TRUE
      reason <- paste0("auto 检测到表达值范围较大（max=", round(vmax, 4), ", q99=", round(q99, 4), "），已执行 log2(x+1)。")
    }} else {{
      reason <- paste0("auto 检测表达值范围较小（max=", round(vmax, 4), ", q99=", round(q99, 4), "），推测已接近 log 尺度，未执行 log2。")
    }}
  }} else {{
    stop("expression_preprocess 仅支持 auto / log2 / non_log2 / raw_count")
  }}

  info_df <- data.frame(
    mode = mode,
    transformed = transformed,
    message = reason,
    n_features = length(expr_cols),
    stringsAsFactors = FALSE
  )

  list(data = df, info = info_df)
}}
'''


def build_single_value_preprocess_r(preprocess_mode: str = "auto") -> str:
    """
    用于单个表达向量的预处理。
    适用场景：
    - 单基因表达箱线图
    - 单基因 ROC
    - 单基因临床关联

    R 侧输出：
    - expression_preprocess_mode
    - auto_preprocess_vector(x, mode)
    """
    return f'''
expression_preprocess_mode <- "{preprocess_mode}"

auto_preprocess_vector <- function(x, mode = "auto") {{
  x <- suppressWarnings(as.numeric(x))
  vals <- x[!is.na(x) & is.finite(x)]
  if (length(vals) == 0) stop("表达向量没有有效数值")

  transformed <- FALSE
  reason <- ""

  if (mode == "raw_count") {{
    reason <- "raw_count 模式：未自动 log2，请确认当前分析是否允许直接使用原始 count。"
  }} else if (mode == "log2") {{
    reason <- "用户指定数据已完成 log2 变换，未再处理。"
  }} else if (mode == "non_log2") {{
    if (any(vals < 0, na.rm = TRUE)) stop("表达值存在负数，无法执行 log2(x+1)")
    x <- log2(x + 1)
    transformed <- TRUE
    reason <- "用户指定数据未做 log2，已执行 log2(x+1)。"
  }} else if (mode == "auto") {{
    q99 <- as.numeric(stats::quantile(vals, 0.99, na.rm = TRUE))
    vmax <- max(vals, na.rm = TRUE)

    if (any(vals < 0, na.rm = TRUE)) {{
      reason <- paste0("检测到负值，推测已做中心化/标准化或对数变换，未执行 log2。max=", round(vmax, 4))
    }} else if (vmax > 50 || q99 > 20) {{
      x <- log2(x + 1)
      transformed <- TRUE
      reason <- paste0("auto 检测到表达值范围较大（max=", round(vmax, 4), ", q99=", round(q99, 4), "），已执行 log2(x+1)。")
    }} else {{
      reason <- paste0("auto 检测表达值范围较小（max=", round(vmax, 4), ", q99=", round(q99, 4), "），推测已接近 log 尺度，未执行 log2。")
    }}
  }} else {{
    stop("expression_preprocess 仅支持 auto / log2 / non_log2 / raw_count")
  }}

  info_df <- data.frame(
    mode = mode,
    transformed = transformed,
    message = reason,
    stringsAsFactors = FALSE
  )

  list(x = x, info = info_df)
}}
'''


def build_matrix_preprocess_r(preprocess_mode: str = "auto") -> str:
    """
    用于表达矩阵预处理。
    适用场景：
    - 表达矩阵相关性
    - bulk PCA
    - limma 连续表达矩阵差异分析
    - GSVA 类矩阵输入

    R 侧输出：
    - expression_preprocess_mode
    - auto_preprocess_matrix(mat, mode)
    """
    return f'''
expression_preprocess_mode <- "{preprocess_mode}"

auto_preprocess_matrix <- function(mat, mode = "auto") {{
  mat <- as.matrix(mat)
  mode(mat) <- "numeric"

  vals <- as.numeric(mat)
  vals <- vals[!is.na(vals) & is.finite(vals)]
  if (length(vals) == 0) stop("矩阵没有有效数值")

  transformed <- FALSE
  reason <- ""

  if (mode == "raw_count") {{
    reason <- "raw_count 模式：未自动 log2，请确认当前分析是否允许直接使用原始 count。"
  }} else if (mode == "log2") {{
    reason <- "用户指定矩阵已完成 log2 变换，未再处理。"
  }} else if (mode == "non_log2") {{
    if (any(vals < 0, na.rm = TRUE)) stop("矩阵存在负数，无法执行 log2(x+1)")
    mat <- log2(mat + 1)
    transformed <- TRUE
    reason <- "用户指定矩阵未做 log2，已执行 log2(x+1)。"
  }} else if (mode == "auto") {{
    q99 <- as.numeric(stats::quantile(vals, 0.99, na.rm = TRUE))
    vmax <- max(vals, na.rm = TRUE)

    if (any(vals < 0, na.rm = TRUE)) {{
      reason <- paste0("检测到负值，推测已做中心化/标准化或对数变换，未执行 log2。max=", round(vmax, 4))
    }} else if (vmax > 50 || q99 > 20) {{
      mat <- log2(mat + 1)
      transformed <- TRUE
      reason <- paste0("auto 检测到矩阵值范围较大（max=", round(vmax, 4), ", q99=", round(q99, 4), "），已执行 log2(x+1)。")
    }} else {{
      reason <- paste0("auto 检测矩阵值范围较小（max=", round(vmax, 4), ", q99=", round(q99, 4), "），推测已接近 log 尺度，未执行 log2。")
    }}
  }} else {{
    stop("expression_preprocess 仅支持 auto / log2 / non_log2 / raw_count")
  }}

  info_df <- data.frame(
    mode = mode,
    transformed = transformed,
    message = reason,
    stringsAsFactors = FALSE
  )

  list(mat = mat, info = info_df)
}}
'''


def build_feature_df_preprocess_r(feature_cols_r: str, preprocess_mode: str = "auto") -> str:
    """
    用于机器学习特征表预处理。
    适用场景：
    - 机器学习分类
    - LASSO 特征筛选
    - 多模型比较

    注意：
    - ML 特征不一定是表达值，所以额外支持 none
    - raw_count 不强制报错，只给提示，因为某些非表达特征场景不适合拦截

    R 侧输出：
    - feature_cols
    - feature_preprocess_mode
    - auto_preprocess_feature_df(df, feature_cols, mode)
    """
    return f'''
feature_cols <- {feature_cols_r}
feature_preprocess_mode <- "{preprocess_mode}"

coerce_numeric_feature_cols <- function(df, cols) {{
  for (cn in cols) {{
    df[[cn]] <- suppressWarnings(as.numeric(df[[cn]]))
  }}
  df
}}

auto_preprocess_feature_df <- function(df, feature_cols, mode = "auto") {{
  feature_cols <- intersect(feature_cols, colnames(df))
  if (length(feature_cols) == 0) stop("没有找到可预处理的特征列")

  df <- coerce_numeric_feature_cols(df, feature_cols)
  vals <- unlist(df[, feature_cols, drop = FALSE], use.names = FALSE)
  vals <- vals[!is.na(vals) & is.finite(vals)]
  if (length(vals) == 0) stop("特征列没有有效数值")

  transformed <- FALSE
  reason <- ""

  if (mode == "none") {{
    reason <- "用户指定不做额外预处理。"
  }} else if (mode == "raw_count") {{
    reason <- "raw_count 模式：未自动 log2，请确认模型输入是否合理。"
  }} else if (mode == "log2") {{
    reason <- "用户指定已 log2，未再处理。"
  }} else if (mode == "non_log2") {{
    if (any(vals < 0, na.rm = TRUE)) stop("特征存在负数，无法执行 log2(x+1)")
    df[, feature_cols] <- lapply(df[, feature_cols, drop = FALSE], function(x) log2(x + 1))
    transformed <- TRUE
    reason <- "用户指定未 log2，已执行 log2(x+1)。"
  }} else if (mode == "auto") {{
    q99 <- as.numeric(stats::quantile(vals, 0.99, na.rm = TRUE))
    vmax <- max(vals, na.rm = TRUE)

    if (any(vals < 0, na.rm = TRUE)) {{
      reason <- paste0("检测到负值，推测已标准化或已对数化，未执行 log2。max=", round(vmax, 4))
    }} else if (vmax > 50 || q99 > 20) {{
      df[, feature_cols] <- lapply(df[, feature_cols, drop = FALSE], function(x) log2(x + 1))
      transformed <- TRUE
      reason <- paste0("auto 检测值范围较大（max=", round(vmax, 4), ", q99=", round(q99, 4), "），已执行 log2(x+1)。")
    }} else {{
      reason <- paste0("auto 检测值范围较小（max=", round(vmax, 4), ", q99=", round(q99, 4), "），未执行 log2。")
    }}
  }} else {{
    stop("feature_preprocess 仅支持 auto / log2 / non_log2 / raw_count / none")
  }}

  info_df <- data.frame(
    mode = mode,
    transformed = transformed,
    message = reason,
    n_features = length(feature_cols),
    stringsAsFactors = FALSE
  )

  list(data = df, info = info_df)
}}
'''