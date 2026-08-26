# pyright: reportTypedDictNotRequiredAccess=false
import json
import os
import random
from collections.abc import Awaitable, Callable
from typing import Any

from bioagent.db import Database
from bioagent.enums import Category, Runtime
from bioagent.eval.evaluate import evaluate_report, evaluate_tool_call
from bioagent.llm.client import LlmClient, LlmMessage
from bioagent.orchestration.state import AgentState
from bioagent.r_runner import RRunner
from bioagent.rag import RagClient
from bioagent.tools import ToolRegistry


Node = Callable[[AgentState], Awaitable[dict[str, Any]]]


def _system(text: str) -> LlmMessage:
    return {"role": "system", "content": text}


def _format_docs(docs: list[dict[str, Any]]) -> str:
    """RAG 检索结果 → prompt 片段；空列表 = 无相关语料占位。"""
    if not docs:
        return "（无相关语料）"
    return "\n".join(f"- {d['text']}" for d in docs)


_ROUTER_PROMPT = """你是合成生物学分析 agent 的意图路由器。根据用户问题，输出：
- intent：一句话中文意图描述
- categories：涉及的类别，只能从下面固定集合里选（英文小写值，可多选，至少一个）

类别集合：{allowed}

只输出 JSON 对象，格式：{{"intent": "...", "categories": ["dge", "enrichment"]}}

用户问题：{query}
"""

_PLANNER_PROMPT = """你是合成生物学分析 agent 的规划器。根据用户问题、意图、可用工具与相关知识，把任务拆成**顺序执行**的步骤序列。

可用工具（JSON 数组，每项含 name/description/parameters）：{tools}

相关知识（RAG 检索，供规划参考；「（无相关语料）」则忽略）：
{knowledge}

只输出 JSON 对象，格式：{{"steps": [{{"tool": "工具名", "args": {{...}}}}]}}
- 每个步骤的 tool 必须是上面列出的工具名
- args 必须符合该工具 parameters 定义的键与类型
- 步骤按执行顺序排列；多步骤 = 多个独立工具，每步 args 只来自用户 query 与 `*_file`（步骤间不传数据）
- 只输出 JSON，不要解释

用户问题：{query}
意图：{intent}
"""

_REPORTER_PROMPT = """你是合成生物学分析 agent 的报告员。根据用户问题、规划步骤、执行结果与相关知识，用中文写一份结构化的 markdown 报告。

用户问题：{query}

规划步骤：{plan}

执行结果：{steps}

相关知识（RAG 检索，供回答知识问题参考；「（无相关语料）」则忽略）：
{knowledge}

要求：结论先行；引用执行结果里的具体数值；用标题/列表/表格组织；不编造结果里没有的数据。
"""


def make_router_node(client: LlmClient) -> Node:
    async def router(state: AgentState) -> dict[str, Any]:
        allowed = [c.value for c in Category]  # 数据驱动，不写死类别列表
        output = await client.complete(
            [_system(_ROUTER_PROMPT.format(query=state["query"], allowed=json.dumps(allowed)))],
            module="router",
            output_type="intent",
            correlation_id=state["correlation_id"],
            json_mode=True,
        )
        parsed = json.loads(output.content)
        return {"intent": parsed["intent"], "categories": parsed["categories"]}
    return router


def make_planner_node(
    client: LlmClient,
    registry: ToolRegistry,
    db: Database,
    sample_rate: float,
    rag: RagClient,
) -> Node:
    async def planner(state: AgentState) -> dict[str, Any]:
        categories = {Category(c) for c in state["categories"]}
        tools = registry.for_categories(categories)
        tool_descs = [
            {"name": t.name, "description": t.description, "parameters": t.input_schema}
            for t in tools
        ]
        docs = await rag.query(state["query"])
        output = await client.complete(
            [_system(_PLANNER_PROMPT.format(
                query=state["query"],
                intent=state["intent"],
                tools=json.dumps(tool_descs, ensure_ascii=False),
                knowledge=_format_docs(docs),
            ))],
            module="planner",
            output_type="plan",
            correlation_id=state["correlation_id"],
            json_mode=True,
        )
        plan = json.loads(output.content)["steps"]
        if random.random() < sample_rate:
            await evaluate_tool_call(
                client, db, output, state["query"], state["intent"], plan
            )
        return {"plan": plan}
    return planner


def _resolve_files(args: dict[str, Any], upload_dir: str) -> dict[str, Any]:
    """把 *_file 字段的值（file_id）解析成 upload_dir 下的绝对路径。

    约定：工具 input_schema 里以 _file 结尾的字段（matrix_file / clinical_file）填的是
    上传接口返回的 file_id；executor 在这里统一解析成绝对路径，R/Python 脚本直接 read。
    """
    resolved = dict(args)
    for key, value in args.items():
        if key.endswith("_file") and isinstance(value, str):
            resolved[key] = os.path.join(upload_dir, value)
    return resolved


def make_executor_node(registry: ToolRegistry, runner: RRunner, upload_dir: str) -> Node:
    async def executor(state: AgentState) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        for step in state["plan"]:
            tool = registry.get(step["tool"])
            args = _resolve_files(step["args"], upload_dir)
            if tool.runtime is Runtime.R:
                assert tool.r_script is not None
                result = await runner.run(tool.r_script, args)
            else:
                assert tool.run is not None
                result = await tool.run(**args)
            steps.append({"tool": step["tool"], "status": "completed", "result": result})
        return {"steps": steps}
    return executor


def make_reporter_node(
    client: LlmClient, db: Database, sample_rate: float, rag: RagClient
) -> Node:
    async def reporter(state: AgentState) -> dict[str, Any]:
        docs = await rag.query(state["query"])
        output = await client.complete(
            [_system(_REPORTER_PROMPT.format(
                query=state["query"],
                plan=json.dumps(state["plan"], ensure_ascii=False),
                steps=json.dumps(state["steps"], ensure_ascii=False),
                knowledge=_format_docs(docs),
            ))],
            module="reporter",
            output_type="report",
            correlation_id=state["correlation_id"],
        )
        if random.random() < sample_rate:
            await evaluate_report(client, db, output, state["query"], output.content)
        return {"report": output.content}
    return reporter
