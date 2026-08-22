# 网络药理（Python networkx + STRING PPI）

> 范围：`bioagent/tools/network/__init__.py`（空）+ `bioagent/tools/network/ppi.py`（导出 `TOOL`）。
> 一条 Python 工具 `ppi_network`：基因列表 → 调 STRING API 拿蛋白互作 → networkx 图 → 节点（id/degree）+ 边（source/target/score）。
> 纯工具 spec：只定义这一个工具与 `run` 执行体，不含编排、不含 API、不含 Facade。

## 元信息

- **前置依赖**：01-types、05-tools（自动发现）
- **无循环依赖**：本 spec 不 import 任何 `bioagent` 模块，只 import 第三方（networkx/httpx）

## 用户故事

> 作为生物信息分析者，我想要「丢一个蛋白/基因列表，就能拿到它们之间的互作网络（节点+边）」，以便画 PPI 网络、看核心 hub 基因。

## 验收标准

- [ ] `ppi.py` 导出 `TOOL`（`category==Category.NETWORK`、`runtime==Runtime.PYTHON`、`run` 非空、`r_script is None`），与「工具定义」段逐字一致
- [ ] `run(gene_list, species)` 调 STRING `network` 端点、解析 TSV、建 `nx.Graph`、返回 `{"nodes": [{id, degree}], "edges": [{source, target, score}]}`
- [ ] 按 header 名取列（不依赖列顺序）；只保留 gene_list 内的边
- [ ] 输出所有数值 Python 原生类型（`float`/`int`），可 `json.dumps`
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`bioagent/tools/network/__init__.py`（空）、`bioagent/tools/network/ppi.py`
- **库**：`networkx`（图 + degree）、`httpx`（异步调 STRING API）；锁精确版本
- **数据源 STRING**：`https://string-db.org/api/tsv/network`，`identifiers`（CR 拼接）+ `species`（默认 9606 = 人）。**需运行时联网**；实现时锁 STRING API 的返回列名（`preferredName_A`/`preferredName_B`/`score`），测试用 fixture 不真调 STRING。
- **httpx 直连（非 LLM）**：CLAUDE.md「不直接使用 httpx」只约束 LLM 调用（走 04-llm）；STRING 是外部数据 API，`httpx.AsyncClient` 合法。`run` 里 `async with httpx.AsyncClient()` 每次新建客户端（工具无注入、不持长连接），MVP 一次请求够用。
- **测试不触网**：`run` 直调 `httpx.AsyncClient.get`，测试用 `monkeypatch`/`respx` 换掉 `httpx.AsyncClient` 返回 fixture TSV，不真连 STRING。

### `bioagent/tools/network/ppi.py`（完整）

```python
from typing import Any

import httpx
import networkx as nx

from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


async def run(gene_list: list[str], species: int = 9606) -> dict[str, Any]:
    """基因列表 → STRING PPI 网络（节点 + 边）。只保留 gene_list 内部的互作。"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://string-db.org/api/tsv/network",
            params={"identifiers": "\r".join(gene_list), "species": str(species)},
        )
        resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    header = lines[0].split("\t")
    col = {name: i for i, name in enumerate(header)}
    g = nx.Graph()
    g.add_nodes_from(gene_list)
    for line in lines[1:]:
        cols = line.split("\t")
        source = cols[col["preferredName_A"]]
        target = cols[col["preferredName_B"]]
        score = float(cols[col["score"]])
        if source in gene_list and target in gene_list:
            g.add_edge(source, target, score=score)
    nodes = [{"id": n, "degree": g.degree(n)} for n in g.nodes]
    edges = [
        {"source": u, "target": v, "score": g[u][v]["score"]} for u, v in g.edges
    ]
    return {"nodes": nodes, "edges": edges}


TOOL = ToolDefinition(
    name="ppi_network",
    description="蛋白互作网络：基因/蛋白列表 → STRING PPI 网络（节点 degree + 边 score）",
    category=Category.NETWORK,
    runtime=Runtime.PYTHON,
    input_schema={
        "type": "object",
        "properties": {
            "gene_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "基因/蛋白 symbol 列表",
            },
            "species": {
                "type": "integer",
                "description": "NCBI taxonomy id（默认 9606 = 人）",
            },
        },
        "required": ["gene_list"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "nodes": {"type": "array"},  # [{id, degree}]
            "edges": {"type": "array"},  # [{source, target, score}]
        },
    },
    run=run,
    frontend={"result_type": "network"},
)
```

## 测试要点

- [ ] 单元测试 `tests/test_tools_network/`（`pytest-asyncio`，`monkeypatch` `httpx.AsyncClient` 返回 fixture TSV）：
  - [ ] `run` 成功：fixture 含 header + 3 行互作（其中 1 行的 target 不在 gene_list 内）→ `nodes` 含所有 gene_list 节点、`edges` 只含 gene_list 内互作；`score` 是 float、`degree` 是 int
  - [ ] `nodes`/`edges` 可 `json.dumps`（无 numpy 类型）
  - [ ] 空 gene_list → `nodes`/`edges` 为空，不抛
  - [ ] STRING 非 200 → `raise_for_status()` 抛（`httpx.HTTPStatusError`）
  - [ ] `TOOL` 形状：`category is Category.NETWORK`、`runtime is Runtime.PYTHON`、`run is not None`、`r_script is None`
- [ ] 集成测试：无
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] `discover()` 自动发现该工具；`GET /tools` 出现 `ppi_network`（category=network、runtime=python）
