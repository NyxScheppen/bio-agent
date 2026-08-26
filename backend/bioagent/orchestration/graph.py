# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportArgumentType=false
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from bioagent.db import Database
from bioagent.llm.client import LlmClient
from bioagent.orchestration.nodes import (
    make_executor_node,
    make_planner_node,
    make_reporter_node,
    make_router_node,
)
from bioagent.orchestration.state import AgentState
from bioagent.r_runner import RRunner
from bioagent.rag import RagClient
from bioagent.tools import ToolRegistry


def build_graph(
    client: LlmClient,
    registry: ToolRegistry,
    runner: RRunner,
    db: Database,
    sample_rate: float,
    upload_dir: str,
    rag: RagClient,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    """组装 router → planner → executor → reporter 线性图。

    sample_rate 由组合根（10-api）从 config.eval.judge_sample_rate 传入；
    upload_dir 由组合根从 config.storage.upload_dir 传入（executor 解析 *_file 用）；
    rag 由组合根构造（07-rag），planner/reporter 各检索一次做接地。
    """
    graph = StateGraph(AgentState)
    graph.add_node("router", make_router_node(client))
    graph.add_node("planner", make_planner_node(client, registry, db, sample_rate, rag))
    graph.add_node("executor", make_executor_node(registry, runner, upload_dir))
    graph.add_node("reporter", make_reporter_node(client, db, sample_rate, rag))
    graph.add_edge(START, "router")
    graph.add_edge("router", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile()
