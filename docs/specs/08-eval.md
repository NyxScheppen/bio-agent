# 评测（两个 judge + 落库）

> 范围：`bioagent/eval/judge.py`（`judge_report` / `judge_tool_call` / `parse_scores`）+ `bioagent/eval/evaluate.py`（`evaluate_report` / `evaluate_tool_call` / `_record`）。
> 纯基础设施 spec：「两者都判」= 报告质量 judge（format/relevance/completeness）+ 工具调用 judge（intent_correct/tool_correct），各产出一个 `EvalReport`；同时把被评输出与 judge 调用的 token 用量落 `token_usage` 表。
> `LLMOutput` / `EvalScores` / `EvalReport` / `TokenUsage` / `TokenUsageDict` 取自 01-types；`LlmClient` 取自 04-llm；`Database` / `token_usage` / `eval_report` 表取自 03-db。

## 元信息

- **前置依赖**：01-types（`EvalScores` / `EvalReport` / `LLMOutput` / `TokenUsageDict`）、02-config（`EvalConfig.judge_sample_rate` 由编排层读，非本 spec）、03-db（`Database` + `token_usage` / `eval_report` 表）、04-llm（`LlmClient`）

## 用户故事

> 作为 bio agent 系统的开发者，我想要两个聚焦的 judge——一个评报告质量、一个评工具调用正确性——各产出可落库的 `EvalReport` 并记全 token 用量，以便用「改了会不会炸」之外还能量化「答得好不好、工具选得对不对」。

## 验收标准

- [ ] `judge.py` 含 `judge_report` / `judge_tool_call` / `parse_scores`，与「`bioagent/eval/judge.py`（完整）」段代码逐字一致
- [ ] `evaluate.py` 含 `evaluate_report` / `evaluate_tool_call` / `_record`，与「`bioagent/eval/evaluate.py`（完整）」段代码逐字一致
- [ ] `parse_scores` 纯函数：合法 JSON → 5 维；报告 judge JSON（只 3 键）→ 工具 2 维计 0；坏 JSON / 非对象 / 非数字 → 对应维度计 0，不抛
- [ ] `judge_*` 以 `output_type="eval"`、`json_mode=True` 调 `client.complete`
- [ ] `evaluate_*` 写 2 行 `token_usage`（被评 output 一行 + judge 一行，purpose 分别为 `output.type` 与 `"eval"`）+ 1 行 `eval_report`，返回 `EvalReport`
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`bioagent/eval/__init__.py`（空）、`bioagent/eval/judge.py`、`bioagent/eval/evaluate.py`（无 Facade、无 API）
- **公开面**：`from bioagent.eval.judge import judge_report, judge_tool_call, parse_scores`、`from bioagent.eval.evaluate import evaluate_report, evaluate_tool_call`（不加 `__all__`）
- **两个独立 judge（用户已定）**：报告 judge 评报告质量 3 维、工具调用 judge 评意图+工具 2 维，各产一个 `EvalReport`（`type` 判别 `"report"` / `"tool_call"`），职责清晰、可在不同时点触发（工具调用 judge 在执行后、报告 judge 在报告后）
- **谁触发**：09-orchestration 的 reporter/executor 节点在产出后（按 `config.eval.judge_sample_rate` 抽样）调 `evaluate_*`；本 spec 只提供函数，不决定抽样策略
- **judge 返回原始 `LLMOutput`**（不直接返回分数）：evaluate 层需要 judge 的 `token_usage` + `id` 落库，故 judge 返回 `LLMOutput`，`parse_scores` 单独解析 `content`——「调 LLM」与「解析」分离
- **token 记账完整**：evaluate 写两行 `token_usage`——被评 output（`purpose=output.type`，`id=output.id`）与 judge 调用（`purpose="eval"`，`id=judge_output.id`）。judge 调用自身不再被 eval（否则无限递归）
- **不 dedup**：MVP 假定每个 output 至多被 eval 一次（抽样或全量），不做「已评跳过」；重复 eval 会撞 `token_usage` 主键，属调用方 bug
- **`_record` 原子**：两行 token_usage + 一行 eval_report 在同一 `db.lock` 下、单次 commit，失败整体不落

### `bioagent/eval/judge.py`（完整）

```python
import json
from typing import Any

from bioagent.llm.client import LlmClient, LlmMessage
from bioagent.types import EvalScores, LLMOutput


_REPORT_PROMPT = """你是生物信息学报告质量评审。给 3 个 0-1 分：
- format：格式规范性（markdown 结构、图表/表格引用）
- relevance：与用户问题的相关度
- completeness：是否完整覆盖用户问题
只输出 JSON 对象，如 {"format": 0.9, "relevance": 0.8, "completeness": 0.7}

用户问题：{query}

报告：
{report}
"""

_TOOL_PROMPT = """你是生物信息学 agent 的工具调用评审。给 2 个 0-1 分：
- intent_correct：意图分类（intent）是否命中用户真实诉求
- tool_correct：所选工具是否适合该问题
只输出 JSON 对象，如 {"intent_correct": 1.0, "tool_correct": 0.5}

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
        [_system(_TOOL_PROMPT.format(query=query, intent=intent, tool_calls=tool_calls))],
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
        data: Any = json.loads(content)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "format": _to_float(data.get("format")),
        "relevance": _to_float(data.get("relevance")),
        "completeness": _to_float(data.get("completeness")),
        "intent_correct": _to_float(data.get("intent_correct")),
        "tool_correct": _to_float(data.get("tool_correct")),
    }
```

### `bioagent/eval/evaluate.py`（完整）

```python
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
    """落库：被评 output 与 judge 各一行 token_usage + 一行 eval_report。原子提交。"""
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
        # 被评 output 记账（purpose = output.type）
        await db.conn.execute(
            "INSERT INTO token_usage (id, correlation_id, module, purpose, model, "
            "input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                output.id,
                output.correlation_id,
                output.module,
                output.type,
                output.model,
                output.token_usage["input"],
                output.token_usage["output"],
                report.created_at,
            ),
        )
        # judge 调用记账（purpose = judge_output.type = "eval"）
        await db.conn.execute(
            "INSERT INTO token_usage (id, correlation_id, module, purpose, model, "
            "input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                judge_output.id,
                judge_output.correlation_id,
                judge_output.module,
                judge_output.type,
                judge_output.model,
                judge_output.token_usage["input"],
                judge_output.token_usage["output"],
                report.created_at,
            ),
        )
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
```

## 测试要点

- [ ] 单元测试 `tests/test_eval/`（`pytest-asyncio`，注入 fake `LlmClient` 与 fake `Database`）：
  - [ ] `parse_scores` 纯函数：`{"format":0.9,"relevance":0.8,"completeness":0.7}` → 3 维正确、工具 2 维 0；`{"intent_correct":1.0,"tool_correct":0.5}` → 工具 2 维正确、报告 3 维 0；坏 JSON（`"not json"`）→ 全 0；非对象（`"[1,2]"`）→ 全 0；非数字（`{"format":"high"}`）→ 该维 0
  - [ ] `judge_report`：fake client（`complete` 记录参数并返回预设 `LLMOutput`）→ 返回该 `LLMOutput`；断言 `output_type=="eval"`、`json_mode=True`、`module=="eval"`、prompt 含 query 与 report 文本
  - [ ] `judge_tool_call`：同上，断言 prompt 含 intent 与 tool_calls
  - [ ] `evaluate_report`（fake db：`conn.execute` 记录 SQL 参数、`commit` 计数）：返回 `EvalReport` 且 `type=="report"`、`output_id==output.id`；`token_usage` 表写 2 行、`eval_report` 表写 1 行；2 行 token_usage 的 `purpose` 分别为 `output.type` 与 `"eval"`；`scores` 由 `parse_scores(judge.content)` 得出
  - [ ] `evaluate_tool_call`：返回 `EvalReport` 且 `type=="tool_call"`；落库同 2+1
- [ ] 集成测试：无（fake LLM + fake db，不触真实 LLM / 真实 SQLite 文件）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] 09-orchestration 在 reporter/executor 产出后（按 `judge_sample_rate` 抽样）调 `evaluate_report` / `evaluate_tool_call`，`EvalReport` 与 `TokenUsage` 落库可查
