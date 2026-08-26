# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from typing import Any

import httpx
import networkx as nx

from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition


async def run(gene_list: list[str]) -> dict[str, Any]:
    """基因列表 → STRING PPI 网络（节点 + 边）。只保留 gene_list 内部的互作。"""
    if not gene_list:
        return {"nodes": [], "edges": []}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://string-db.org/api/tsv/network",
            params={"identifiers": "\r".join(gene_list), "species": "9606"},
        )
        resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    if not lines:
        return {"nodes": [{"id": n, "degree": 0} for n in gene_list], "edges": []}
    header = lines[0].split("\t")
    col = {name: i for i, name in enumerate(header)}
    g = nx.Graph()
    g.add_nodes_from(gene_list)
    gene_set = set(gene_list)
    for line in lines[1:]:
        cols = line.split("\t")
        source = cols[col["preferredName_A"]]
        target = cols[col["preferredName_B"]]
        score = float(cols[col["score"]])
        if source in gene_set and target in gene_set:
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
