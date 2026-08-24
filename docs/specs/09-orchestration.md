# 编排（LangGraph 四节点）

> 范围：`backend/bioagent/orchestration/state.py`（`AgentState`）、`backend/bioagent/orchestration/nodes.py`（`make_router_node` / `make_planner_node` / `make_executor_node` / `make_reporter_node`）、`backend/bioagent/orchestration/graph.py`（`build_graph`）。
> 把 router → planner → executor → reporter 四节点装成 LangGraph `StateGraph`，跑一次「问题 → 意图 → 规划 → 执行 → 报告」。
> 纯编排 spec：只定义图结构与节点，不含 API 层（那是 10-api）、不含任何具体工具（那是 11-15）、不含 Facade。
> `LlmClient` 取自 04-llm、`ToolRegistry` 取自 05-tools、`RRunner` 取自 06-r-runner、`RagClient` 取自 07-rag、`Database` 取自 03-db、`evaluate_report`/`evaluate_tool_call` 取自 08-eval、`Category`/`Runtime` 取自 01-types。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：01-types（`Category`/`Runtime`）、03-db（`Database`）、04-llm（`LlmClient`/`LlmMessage`）、05-tools（`ToolRegistry`）、06-r-runner（`RRunner`）、07-rag（`RagClient`）、08-eval（`evaluate_report`/`evaluate_tool_call`）
- **无循环依赖**：本 spec 只被 10-api 依赖；它依赖的所有模块（01/03/04/05/06/08）都先于它编号。11-15 的生物工具不 import 本 spec。

## 用户故事

> 作为 bio agent 系统的开发者，我想要一条固定的四节点流水线——router 判意图与类别、planner 用「可用工具清单」规划出顺序步骤、executor 机械执行（Python 走 `run`、R 走 `runner`）、reporter 汇总成 markdown 报告——以便「加工具 = 加文件」后流水线自动能跑，且每个节点产出可单独测试、可抽样 eval。

## 验收标准

- [ ] `state.py` 含 `AgentState`，字段与「`backend/bioagent/orchestration/state.py`（完整）」段逐字一致
- [ ] `nodes.py` 含 4 个 `make_*_node` 工厂，与「`backend/bioagent/orchestration/nodes.py`（完整）」段逐字一致
- [ ] `graph.py` 含 `build_graph`，与「`backend/bioagent/orchestration/graph.py`（完整）」段逐字一致
- [ ] 图拓扑：`START → router → planner → executor → reporter → END`（线性，无分支）
- [ ] router 用 `json_mode=True` 调 LLM，输出 `{"intent": str, "categories": list[str]}`；`categories` 来自 `[c.value for c in Category]` 数据驱动推导，不写死列表
- [ ] planner 用 `registry.for_categories()` 裁剪工具、`json_mode=True` 产出 `{"steps": [{tool, args}]}`；executor 机械执行不调 LLM
- [ ] planner / reporter 各自先 `rag.query(query)` 取 top_k 相关语料拼进 prompt（`{knowledge}` 占位；空语料 = 「（无相关语料）」）
- [ ] executor 按 `tool.runtime` 分派：`Runtime.R` → `runner.run(r_script, args)`；否则 `tool.run(**args)`；每步产出 `{tool, status, result}`
- [ ] 抽样 eval：planner 产出后按 `sample_rate` 调 `evaluate_tool_call`；reporter 产出后按 `sample_rate` 调 `evaluate_report`（`sample_rate` 取自 `config.eval.judge_sample_rate`）
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`backend/bioagent/orchestration/__init__.py`（空）、`backend/bioagent/orchestration/state.py`、`backend/bioagent/orchestration/nodes.py`、`backend/bioagent/orchestration/graph.py`（无 Facade、无 API）
- **库**：`langgraph`（`StateGraph`）；`langchain-core`（消息类，仅 04-llm 内用，本 spec 不直接用）
- **公开面**：`from bioagent.orchestration.graph import build_graph`、`from bioagent.orchestration.state import AgentState`（不加 `__all__`；`nodes.py` 的 `make_*_node` 是 `build_graph` 的实现细节，不单独导出）

### 关键决策（实现者务必读，改动前先问）

1. **计划-执行（plan-and-execute）模型**：planner 用 `json_mode` 一次性产出**顺序步骤序列**，executor 机械执行、**不调 LLM**、不在运行时动态选工具。选它而非 ReAct/function-calling 循环：符合设计文档的「步骤 DAG」、可测（每个节点输入输出确定）、「工具调用 judge」评的是 planner 的规划（`tool_calls` = plan 的步骤）。若要改成 executor 动态 function-calling，属架构变更，先问。
2. **MVP 步骤是线性的**：plan 是 `list[{tool, args}]`，**没有** `depends_on`、没有并行分支。5 条管线（11-15）天然是「load → 分析 → 返回」的顺序链；前端把线性链画成 DAG 形状（顺序箭头），无需真 DAG/拓扑排序。加 `depends_on`/并行是「未请求的灵活性」，不做。同样**步骤间不传数据**：每步 args 只来自用户 query 与 `*_file`（`_resolve_files` 解析出的路径），executor 不做 step N 输出 → step N+1 args 的注入；跨步骤数据依赖（如 DGE 结果喂富集）是 MVP 之外的增强，不做。
3. **eval 内联在节点里**：planner 产出 plan 后调 `evaluate_tool_call`、reporter 产出 report 后调 `evaluate_report`（都按 `sample_rate` 抽样）。节点由此多拿 `db` + `sample_rate` 两个参数——这是为拿到「刚产出的 `LLMOutput`」（eval 需要 `output.id`/`output.module`/`output.correlation_id`）最省事的落点。token 记账由 04-llm 的 `complete()` 自动落，节点不写。抽样的确定性：`sample_rate=0.0` 永不评、`1.0` 必评，测试用这两个极端，不 mock `random`。
4. **不接 checkpointer（resume 不做）**：`build_graph` 不接收 checkpointer，`compile()` 不带参数。SSE 流式用 `graph.astream()`，**不需要** checkpointer；checkpoint（失败续跑/人机交互）是 MVP 之外的增强。将来要加 = `compile(checkpointer=AsyncSqliteSaver(...))` 一个参数的事，但那是独立文件/独立 sqlite，别和 03-db 的 `task` 表混。
5. **错误处理 = 异常上抛**：节点里 LLM 坏 JSON、工具抛错、R 非零退出都不捕获，直接向上抛。10-api 捕获后把 task 置 `FAILED`。不做「优雅错误节点 / 部分步骤失败继续」，那会让「报告里混进失败步骤」变成常态，属过度设计。
6. **`correlation_id = task id`**：10-api 生成 uuid（同时作为 `task` 表主键与 `correlation_id`），注入初始 state，贯穿所有 `client.complete` 调用与 eval 落库，把一次会话的所有 LLM 调用/评测串起来。9 不生成它，只读 `state["correlation_id"]`。
7. **`*_file` 参数约定（文件解析）**：工具 input_schema 里以 `_file` 结尾的字段（如 `matrix_file` / `clinical_file`）填上传接口返回的 `file_id`；executor 执行前用 `_resolve_files` 把它们解析成 `upload_dir` 下的绝对路径，R/Python 脚本直接 `read.table`/`read_csv` 即可。原因：工具靠 `discover()` 自动发现、拿不到组合根注入的 `upload_dir`，而 R 脚本（06-r-runner）只收 args 无 DB 访问，故解析统一落在 executor（它被注入 `upload_dir`）。
8. **RAG 接地在 planner + reporter（两处）**：planner 规划前、reporter 写报告前，各用 `rag.query(query)` 取 top_k 相关语料拼进 prompt——planner 用地接地规划、reporter 用地回答「用户问知识」。检索失败按决策 5 异常上抛（qdrant 未起 = 任务 FAILED）；collection 为空只返回空列表，prompt 用「（无相关语料）」占位，不阻断。`rag` 由组合根（10-api）构造并注入（07-rag）。

### `backend/bioagent/orchestration/state.py`（完整）

```python
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph 编排状态：各节点按职责增量读写的共享 dict。

    无 reducer，同名键后写覆盖；各节点只写自己负责的键，线性链下天然不冲突。
    query / correlation_id 由 10-api 注入初始 state，其余键由对应节点写入。
    """
    query: str                  # 用户问题（贯穿全链）
    correlation_id: str         # 关联 ID（= task id，10-api 生成）
    intent: str                 # router 分类出的意图（一句话）
    categories: list[str]       # router 判出的类别（Category.value）
    plan: list[dict[str, Any]]  # planner 产出的步骤序列 [{tool, args}]
    steps: list[dict[str, Any]]  # executor 每步结果 [{tool, status, result}]（status="completed"；失败整体上抛，见决策 5）
    report: str                 # reporter 最终报告（markdown，纯文本）
```

### `backend/bioagent/orchestration/nodes.py`（完整）

```python
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
```

### `backend/bioagent/orchestration/graph.py`（完整）

```python
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
) -> CompiledStateGraph:
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
```

**依赖 pin（实现时锁）**：`langgraph` / `langchain-core` 锁精确版本（非 `>=` 宽范围）。`StateGraph` / `CompiledStateGraph` 的导入路径（`langgraph.graph` / `langgraph.graph.state`）与 `compile()` 返回类型的泛型形参以锁定版本为准；若 pyright strict 对 `CompiledStateGraph` 报「缺类型实参」，按锁定版本补 `CompiledStateGraph[AgentState, ...]` 即可，升级依赖须重跑本 spec 测试。

## 测试要点

- [ ] 单元测试 `tests/test_orchestration/`（`pytest-asyncio`，注入 fake `LlmClient` / fake `ToolRegistry` / fake `RRunner` / fake `Database`）：
  - [ ] `make_router_node`：fake client（`complete` 记录参数、返回 content=JSON 的 `LLMOutput`）→ 节点返回 `{"intent": ..., "categories": [...]}`；断言 `module=="router"`、`output_type=="intent"`、`json_mode=True`、`correlation_id` 透传、prompt（`messages[0]["content"]`）含 `allowed` 全量类别值 + query 文本
  - [ ] `make_planner_node`：fake client 返回 `{"steps":[...]}` JSON → 节点返回 `{"plan": [...]}`；断言 `registry.for_categories` 收到 `{Category(c) for c in categories}`；prompt 含工具名与 input_schema；fake `rag.query` 收到 `state["query"]`、返回的 docs 文本进了 prompt（`knowledge` 占位）；`sample_rate=0.0` → `evaluate_tool_call` 不被调；`sample_rate=1.0` → 被调且参数 `(client, db, output, query, intent, plan)` 正确
  - [ ] `make_executor_node`：fake registry 注册 1 个 Python 工具（`run` 记录 kwargs）+ 1 个 R 工具（`r_script="km.R"`）；plan 两步 → `steps` 长度 2、每步 `{tool, status:"completed", result}`；断言 R 步走 `runner.run("km.R", args)`、Python 步走 `tool.run(**args)`
  - [ ] `_resolve_files`：`{"matrix_file": "abc", "n": 3}` → `{"matrix_file": "<upload_dir>/abc", "n": 3}`（`*_file` 结尾的 str 值解析成路径、其余不动）；`{"matrix_file": 5}`（非 str）→ 不动
  - [ ] `make_reporter_node`：fake client 返回 markdown → 节点返回 `{"report": markdown}`；断言 `json_mode` 缺省（报告非 JSON）；fake `rag.query` 收到 query 且 docs 文本进了 prompt；`sample_rate=1.0` → `evaluate_report` 被调且 `report == output.content`
- [ ] 集成测试 `tests/test_orchestration/`（真实 `langgraph` 编译 + 全 fake 依赖）：
  - [ ] `build_graph`：注入「按 `module` 分派返回值的 fake client」（router→JSON / planner→JSON / reporter→markdown）+ fake registry + fake runner + fake db + fake rag（`query` 返回 `[]`）→ `compile()` 返回对象；`await graph.ainvoke({"query": ..., "correlation_id": ...})` → 终态含 `intent` / `categories` / `plan` / `steps` / `report`，且四节点按序执行（fake client 记录 module 调用顺序 = router → planner → reporter，executor 不调 LLM）
- [ ] E2E 测试：无（不触真实 LLM / 真实 R / 真实工具）

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] 10-api 用 `build_graph(...)` + `graph.astream()` 驱动一次会话，把终态 `report`/`plan`/`steps` 写回 `task` 表；11-15 的工具被 `discover()` 发现后，planner 能按类别拿到、executor 能按 runtime 执行
