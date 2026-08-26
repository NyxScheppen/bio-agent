from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


TOOL = ToolDefinition(
    name="limma_dge",
    description="差异表达分析（limma）：表达矩阵 + case/control 样本列表 → 差异表（logFC/p/adj.P），按 p 升序 top 50",
    category=Category.DGE,
    runtime=Runtime.R,
    input_schema={
        "type": "object",
        "properties": {
            "matrix_file": {
                "type": "string",
                "description": "表达矩阵文件 ID（上传返回的 file_id；TSV，行=基因、列=样本）",
            },
            "case": {
                "type": "array",
                "items": {"type": "string"},
                "description": "case 组样本名列表",
            },
            "control": {
                "type": "array",
                "items": {"type": "string"},
                "description": "control 组样本名列表",
            },
        },
        "required": ["matrix_file", "case", "control"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "genes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "gene": {"type": "string"},
                        "logFC": {"type": "number"},
                        "p_value": {"type": "number"},
                        "adj_p_value": {"type": "number"},
                    },
                },
            },
        },
    },
    run=None,
    r_script="limma_dge.R",
    frontend={"result_type": "volcano"},
)
