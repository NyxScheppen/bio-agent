import json
from typing import Any, cast

from bioagent.llm.client import LlmClient, LlmMessage
from bioagent.types import EvalScores, LLMOutput


_REPORT_PROMPT = """你是生物信息学报告质量评审。给 3 个 0-1 分：
- format：格式规范性（markdown 结构、图表/表格引用）
- relevance：与用户问题的相关度
- completeness：是否完整覆盖用户问题
只输出 JSON 对象，如 {{"format": 0.9, "relevance": 0.8, "completeness": 0.7}}

用户问题：{query}

报告：
{report}
"""

_TOOL_PROMPT = """你是生物信息学 agent 的工具调用评审。给 2 个 0-1 分：
- intent_correct：意图分类（intent）是否命中用户真实诉求
- tool_correct：所选工具是否适合该问题
只输出 JSON 对象，如 {{"intent_correct": 1.0, "tool_correct": 0.5}}

用户问题：{query}
意图分类：{intent}
工具调用：{tool_calls}
"""


def _system(text: str) -> LlmMessage:
    return {"role": "system", "content": text}


async def judge_report(
    client: LlmClient, query: str, report: str, correlation_id: str
) -> LLMOutput:
    """跑报告质量 judge，返回原始 LLMOutput（content 为 JSON 分数）。"""
    return await client.complete(
        [_system(_REPORT_PROMPT.format(query=query, report=report))],
        module="eval",
        output_type="eval",
        correlation_id=correlation_id,
        json_mode=True,
    )


async def judge_tool_call(
    client: LlmClient,
    query: str,
    intent: str,
    tool_calls: list[dict[str, Any]],
    correlation_id: str,
) -> LLMOutput:
    """跑工具调用 judge，返回原始 LLMOutput（content 为 JSON 分数）。"""
    return await client.complete(
        [_system(_TOOL_PROMPT.format(query=query, intent=intent, tool_calls=json.dumps(tool_calls)))],
        module="eval",
        output_type="eval",
        correlation_id=correlation_id,
        json_mode=True,
    )


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_scores(content: str) -> EvalScores:
    """解析 judge JSON 为 EvalScores；缺键/坏 JSON/非数字计 0，不抛。纯函数。"""
    try:
        raw: Any = json.loads(content)
    except json.JSONDecodeError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    data = cast(dict[str, Any], raw)
    return {
        "format": _to_float(data.get("format")),
        "relevance": _to_float(data.get("relevance")),
        "completeness": _to_float(data.get("completeness")),
        "intent_correct": _to_float(data.get("intent_correct")),
        "tool_correct": _to_float(data.get("tool_correct")),
    }
