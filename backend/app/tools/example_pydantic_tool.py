"""
Phase 3 示例：使用 Pydantic params_model 注册工具。

演示三种注册方式：
1. 旧写法：显式 parameters dict
2. 新写法：Pydantic params_model
3. 最简写法：函数签名自动推导

运行验证：
    cd D:/Desktop/bio_test
    $env:PYTHONPATH = "D:/Desktop/bio_test/backend"
    .venv/Scripts/python.exe -c "from app.tools.example_pydantic_tool import *; print('OK')"
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from app.agent.tool_registry import register_tool


# ============================================================
# 方式 1：Pydantic params_model
# ============================================================

class GCContentParams(BaseModel):
    """GC 含量计算参数。"""
    sequence: str = Field(description="DNA/RNA 序列字符串，例如 ATGCGTACG")
    window_size: int = Field(default=100, description="滑动窗口大小")
    as_percentage: bool = Field(default=True, description="是否返回百分比")


@register_tool(
    name="calculate_gc_content_v2",
    description="计算 DNA/RNA 序列的 GC 含量。支持滑动窗口和百分比/小数输出。",
    category="basic",
    params_model=GCContentParams,
    tags=["gc", "sequence", "basic"],
)
def calculate_gc_content_v2(
    sequence: str,
    window_size: int = 100,
    as_percentage: bool = True,
    session_id: str = "",
    job_dir: str = "",
):
    """
    计算 GC 含量（Pydantic params_model 示例）。

    session_id 和 job_dir 由生命周期自动注入，不出现在 OpenAI schema 中。
    """
    if not sequence:
        return {"status": "error", "message": "序列为空"}

    seq = sequence.upper()
    gc_count = seq.count("G") + seq.count("C")
    total = len(seq)
    ratio = gc_count / total if total > 0 else 0.0
    value = ratio * 100 if as_percentage else ratio

    return {
        "status": "success",
        "message": f"GC 含量: {value:.2f}{'%' if as_percentage else ''}",
        "summary": {
            "gc_count": gc_count,
            "total_bases": total,
            "gc_content": round(value, 2),
            "as_percentage": as_percentage,
        },
    }


# ============================================================
# 方式 2：函数签名自动推导
# ============================================================

@register_tool(
    name="count_sequence_bases",
    description="统计 DNA/RNA 序列中各碱基数量。",
    category="basic",
    tags=["sequence", "count", "basic"],
)
def count_sequence_bases(
    sequence: str,
    include_gaps: bool = False,
) -> dict:
    """统计碱基数量（函数签名自动生成 schema 示例）。"""
    if not sequence:
        return {"status": "error", "message": "序列为空"}

    seq = sequence.upper()
    bases = ["A", "T", "G", "C", "U"]
    if include_gaps:
        bases.append("-")

    counts = {b: seq.count(b) for b in bases}
    total = sum(counts.values())

    return {
        "status": "success",
        "message": f"统计完成，共 {total} 个碱基",
        "summary": {"counts": counts, "total": total},
    }


# ============================================================
# 方式 3：旧写法（仍兼容）
# ============================================================

@register_tool(
    name="reverse_complement_v2",
    description="计算 DNA 序列的反向互补序列。",
    parameters={
        "type": "object",
        "properties": {
            "sequence": {
                "type": "string",
                "description": "DNA 序列字符串"
            }
        },
        "required": ["sequence"]
    },
    category="basic",
    tags=["sequence", "complement"],
)
def reverse_complement_v2(sequence: str) -> dict:
    """反向互补（旧 parameters dict 示例）。"""
    if not sequence:
        return {"status": "error", "message": "序列为空"}

    complement = {"A": "T", "T": "A", "G": "C", "C": "G", "a": "t", "t": "a", "g": "c", "c": "g"}
    result = "".join(complement.get(b, b) for b in reversed(sequence))

    return {
        "status": "success",
        "message": f"反向互补完成，长度 {len(result)}",
        "summary": {"length": len(result), "result": result[:50]},
    }
