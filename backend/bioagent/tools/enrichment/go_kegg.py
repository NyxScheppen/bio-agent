from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


TOOL = ToolDefinition(
    name="go_kegg",
    description="富集分析（clusterProfiler）：基因 symbol 列表 → GO(BP) + KEGG 富集表，各按 p 升序 top 20",
    category=Category.ENRICHMENT,
    runtime=Runtime.R,
    input_schema={
        "type": "object",
        "properties": {
            "gene_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "基因 symbol 列表（如差异基因）",
            },
        },
        "required": ["gene_list"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "go": {"type": "array"},   # [{id, term, p_value, adj_p_value, gene_count}]
            "kegg": {"type": "array"}, # 同结构；KEGG 失败为空
        },
    },
    run=None,
    r_script="go_kegg.R",
    frontend={"result_type": "barplot"},
)
