import json
from app.agent.tool_registry import register_tool

@register_tool(
    name="calculate_gc_content",
    description="计算 DNA 序列的 GC 含量",
    parameters={
        "type": "object",
        "properties": {
            "sequence": {
                "type": "string",
                "description": "DNA 序列"
            }
        },
        "required": ["sequence"]
    }
)
def calculate_gc_content(sequence: str):
    """
    一个基础生信工具示例
    """
    seq = sequence.upper()
    gc = (seq.count("G") + seq.count("C")) / len(seq) * 100 if len(seq) > 0 else 0
    return json.dumps({
        "status": "success",
        "gc_content_percentage": round(gc, 2)
    }, ensure_ascii=False)