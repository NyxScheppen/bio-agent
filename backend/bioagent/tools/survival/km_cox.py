from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


TOOL = ToolDefinition(
    name="km_cox",
    description="生存分析（KM + Cox）：临床表 → 分组 KM 曲线数据 + log-rank p + Cox 风险比",
    category=Category.SURVIVAL,
    runtime=Runtime.R,
    input_schema={
        "type": "object",
        "properties": {
            "clinical_file": {
                "type": "string",
                "description": "临床表文件 ID（上传返回的 file_id；TSV，行=样本，含时间/事件/分组列）",
            },
            "time_col": {"type": "string", "description": "生存时间列名（默认 time）"},
            "event_col": {"type": "string", "description": "事件列名，1=事件/0=删失（默认 event）"},
            "group_col": {"type": "string", "description": "分组列名（默认 group）"},
        },
        "required": ["clinical_file"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "km_curves": {"type": "array"},  # [{group, time[], survival[]}]
            "logrank_p": {"type": "number"},
            "cox_hr": {"type": "number"},
            "cox_p": {"type": "number"},
        },
    },
    run=None,
    r_script="km_cox.R",
    frontend={"result_type": "km_curve"},
)
