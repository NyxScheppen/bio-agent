import json
import time
import uuid
from typing import Any

from bioagent.db import Database
from bioagent.eval.judge import judge_report, judge_tool_call, parse_scores
from bioagent.llm.client import LlmClient
from bioagent.types import EvalReport, EvalScores, LLMOutput


async def evaluate_report(
    client: LlmClient, db: Database, output: LLMOutput, query: str, report: str
) -> EvalReport:
    """评报告质量：跑报告 judge → 落库 → 返回 EvalReport。"""
    judge_output = await judge_report(client, query, report, output.correlation_id)
    return await _record(db, output, judge_output, parse_scores(judge_output.content), "report")


async def evaluate_tool_call(
    client: LlmClient,
    db: Database,
    output: LLMOutput,
    query: str,
    intent: str,
    tool_calls: list[dict[str, Any]],
) -> EvalReport:
    """评工具调用：跑工具 judge → 落库 → 返回 EvalReport。"""
    judge_output = await judge_tool_call(
        client, query, intent, tool_calls, output.correlation_id
    )
    return await _record(db, output, judge_output, parse_scores(judge_output.content), "tool_call")


async def _record(
    db: Database,
    output: LLMOutput,
    judge_output: LLMOutput,
    scores: EvalScores,
    kind: str,
) -> EvalReport:
    """落库：一行 eval_report；`token_usage` 存 judge 本次评测的 token（judge_output.token_usage，自包含快照，非被评对象）。"""
    report = EvalReport(
        id=str(uuid.uuid4()),
        output_id=output.id,
        module=output.module,
        type=kind,
        scores=scores,
        token_usage=judge_output.token_usage,
        correlation_id=output.correlation_id,
        created_at=time.time(),
    )
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO eval_report (id, output_id, module, type, scores, token_usage, "
            "correlation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report.id,
                report.output_id,
                report.module,
                report.type,
                json.dumps(report.scores),
                json.dumps(report.token_usage),
                report.correlation_id,
                report.created_at,
            ),
        )
        await db.conn.commit()
    return report
