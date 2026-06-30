from app.agent.tool_registry import register_tool
from app.tools.r_tools import run_r_analysis

@register_tool(
    name="run_virtual_knockdown_bulk_analysis",
    description="对 bulk 表达矩阵执行目标基因虚拟敲低（将目标基因表达乘以 1-knockdown_ratio），输出扰动前后表达矩阵与变化摘要。",
    parameters={
        "type": "object",
        "properties": {
            "expression_file": {"type": "string", "description": "表达矩阵CSV文件，第一列为gene"},
            "gene": {"type": "string", "description": "目标基因"},
            "knockdown_ratio": {
                "type": "number",
                "description": "敲低比例，0-1，如0.8表示降低80%",
                "default": 0.8
            }
        },
        "required": ["expression_file", "gene"]
    }
)
def run_virtual_knockdown_bulk_analysis(expression_file: str, gene: str, knockdown_ratio: float = 0.8):
    ratio = max(0.0, min(float(knockdown_ratio), 1.0))

    r_code = f'''
library(data.table)

expr <- fread(smart_read("{expression_file}"), data.table = FALSE)
if (!("gene" %in% colnames(expr))) stop("表达矩阵必须包含 gene 列")

rownames(expr) <- expr$gene
expr$gene <- NULL
expr_mat <- as.matrix(expr)
mode(expr_mat) <- "numeric"

if (!("{gene}" %in% rownames(expr_mat))) stop("找不到目标基因")

original <- expr_mat["{gene}", ]
perturbed <- original * (1 - {ratio})
expr_mat["{gene}", ] <- perturbed

before_after <- data.frame(
  sample = colnames(expr_mat),
  before = as.numeric(original),
  after = as.numeric(perturbed)
)
write.csv(before_after, "virtual_knockdown_before_after.csv", row.names = FALSE)

out_df <- data.frame(gene = rownames(expr_mat), expr_mat, check.names = FALSE)
write.csv(out_df, "virtual_knockdown_expression_matrix.csv", row.names = FALSE)

mean_before <- mean(original, na.rm = TRUE)
mean_after <- mean(perturbed, na.rm = TRUE)

summary_df <- data.frame(
  gene = "{gene}",
  knockdown_ratio = {ratio},
  mean_before = mean_before,
  mean_after = mean_after,
  fold_change = ifelse(mean_before == 0, NA, mean_after / mean_before)
)
write.csv(summary_df, "virtual_knockdown_summary.csv", row.names = FALSE)

cat("生成文件: virtual_knockdown_before_after.csv, virtual_knockdown_expression_matrix.csv, virtual_knockdown_summary.csv\\n")
'''
    return run_r_analysis(r_code, job_subdir="virtual_knockdown")