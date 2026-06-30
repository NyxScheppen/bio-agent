import json
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pandas as pd
import requests
import networkx as nx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.agent.tool_registry import register_tool
from app.core.paths import GENERATED_DIR
from app.utils.file_resolver import resolve_file_path, debug_file_context


STRING_API_BASE = "https://string-db.org/api/json"
REQUEST_HEADERS = {
    "User-Agent": "BioAI-Agent/1.0 network pharmacology tool"
}


def _safe_json_dumps(data):
    return json.dumps(data, ensure_ascii=False)


def _safe_name(name: str, default: str = "network_pharmacology"):
    name = str(name or default).strip()
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name[:80] or default


def _make_job_dir(job_subdir: str = ""):
    job_id = _safe_name(job_subdir) if job_subdir else f"network_pharmacology_{str(uuid.uuid4())[:8]}"
    job_dir = Path(GENERATED_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_id, job_dir


def _file_record(path: Path):
    rel = path.relative_to(GENERATED_DIR).as_posix()
    return {
        "name": path.name,
        "relative_path": f"generated/{rel}",
        "url": f"/files/generated/{rel}",
        "size_bytes": path.stat().st_size if path.exists() else 0
    }


def _list_output_files(job_dir: Path):
    files = []
    if not job_dir.exists():
        return files

    for p in job_dir.rglob("*"):
        if p.is_file():
            files.append(_file_record(p))

    return files


def _read_table_any(file_path: str, session_id: str = None):
    real_path = resolve_file_path(file_path, session_id)

    if not real_path.exists():
        raise FileNotFoundError(
            f"文件不存在：{file_path}\n"
            f"调试信息：{debug_file_context(file_path, session_id)}"
        )

    name = real_path.name.lower()

    if name.endswith(".csv"):
        return pd.read_csv(real_path), real_path

    if name.endswith(".tsv") or name.endswith(".txt"):
        return pd.read_csv(real_path, sep="\t"), real_path

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(real_path), real_path

    if name.endswith(".csv.gz"):
        return pd.read_csv(real_path, compression="gzip"), real_path

    if name.endswith(".tsv.gz") or name.endswith(".txt.gz"):
        return pd.read_csv(real_path, sep="\t", compression="gzip"), real_path

    raise ValueError(f"暂不支持该文件类型：{real_path.name}")


def _normalize_colname(col: str):
    return re.sub(r"[^a-z0-9]+", "", str(col).strip().lower())


def _find_column(df: pd.DataFrame, candidates: List[str], required: bool = True, label: str = ""):
    normalized_map = {_normalize_colname(c): c for c in df.columns}

    for cand in candidates:
        key = _normalize_colname(cand)
        if key in normalized_map:
            return normalized_map[key]

    if required:
        raise ValueError(
            f"找不到必要列：{label or candidates[0]}。"
            f"可接受列名：{candidates}。"
            f"当前文件列名：{list(df.columns)}"
        )

    return None


def _split_targets(value):
    if pd.isna(value):
        return []

    text = str(value).strip()
    if not text:
        return []

    parts = re.split(r"[;,/|，；、\s]+", text)
    genes = []

    for p in parts:
        g = str(p).strip()
        if not g:
            continue

        # 去掉常见修饰
        g = re.sub(r"^\s*gene[:：]\s*", "", g, flags=re.I)
        g = g.strip().upper()

        # 基因符号简单过滤，避免把长句子塞进去
        if 1 <= len(g) <= 30:
            genes.append(g)

    return list(dict.fromkeys(genes))


def _normalize_gene_symbol(gene):
    if pd.isna(gene):
        return ""

    gene = str(gene).strip()
    gene = re.sub(r"^\s*gene[:：]\s*", "", gene, flags=re.I)
    gene = gene.strip().upper()

    return gene


def _prepare_compound_target_data(
    compound_df: pd.DataFrame,
    ob_threshold: float,
    dl_threshold: float
):
    herb_col = _find_column(
        compound_df,
        ["herb", "herb_name", "medicine", "tcm", "中药", "药材", "草药"],
        required=False,
        label="中药名"
    )

    compound_col = _find_column(
        compound_df,
        ["compound", "compound_name", "molecule", "molecule_name", "ingredient", "成分", "化合物", "活性成分"],
        required=True,
        label="化合物名"
    )

    target_col = _find_column(
        compound_df,
        ["target", "targets", "gene", "genes", "symbol", "target_gene", "target_genes", "靶点", "基因"],
        required=True,
        label="靶点"
    )

    ob_col = _find_column(
        compound_df,
        ["ob", "oral_bioavailability", "oral bioavailability", "口服生物利用度"],
        required=False,
        label="OB"
    )

    dl_col = _find_column(
        compound_df,
        ["dl", "drug_likeness", "drug likeness", "类药性"],
        required=False,
        label="DL"
    )

    df = compound_df.copy()

    if herb_col is None:
        df["herb"] = "Unknown_Herb"
        herb_col = "herb"

    if ob_col is not None:
        df[ob_col] = pd.to_numeric(df[ob_col], errors="coerce")
        df = df[df[ob_col].fillna(-999) >= float(ob_threshold)]

    if dl_col is not None:
        df[dl_col] = pd.to_numeric(df[dl_col], errors="coerce")
        df = df[df[dl_col].fillna(-999) >= float(dl_threshold)]

    active_compounds = df.copy()

    edges = []
    for _, row in active_compounds.iterrows():
        herb = str(row.get(herb_col, "Unknown_Herb")).strip() or "Unknown_Herb"
        compound = str(row.get(compound_col, "")).strip()
        if not compound:
            continue

        targets = _split_targets(row.get(target_col, ""))
        for gene in targets:
            edges.append({
                "herb": herb,
                "compound": compound,
                "target": gene,
                "OB": row.get(ob_col, None) if ob_col else None,
                "DL": row.get(dl_col, None) if dl_col else None
            })

    edge_df = pd.DataFrame(edges)

    if len(edge_df) > 0:
        edge_df = edge_df.drop_duplicates()

    return active_compounds, edge_df


def _prepare_disease_targets(disease_df: pd.DataFrame):
    gene_col = _find_column(
        disease_df,
        ["gene", "genes", "symbol", "target", "targets", "gene_symbol", "靶点", "基因"],
        required=True,
        label="疾病靶点 gene"
    )

    genes = disease_df[gene_col].dropna().map(_normalize_gene_symbol)
    genes = [g for g in genes if g]
    genes = list(dict.fromkeys(genes))

    return pd.DataFrame({"gene": genes})


def _string_species_id(species: str):
    species = str(species or "human").strip().lower()

    if species in ["human", "homo sapiens", "hsa", "9606"]:
        return 9606

    if species in ["mouse", "mus musculus", "mmu", "10090"]:
        return 10090

    # 默认人
    return 9606


def _map_genes_to_string_ids(genes: List[str], species_id: int):
    if not genes:
        return {}, []

    url = f"{STRING_API_BASE}/get_string_ids"

    # STRING 建议 identifiers 用 \r 分隔
    params = {
        "identifiers": "\r".join(genes),
        "species": species_id,
        "limit": 1,
        "echo_query": 1
    }

    resp = requests.post(url, data=params, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    gene_to_string = {}
    mapped_rows = []

    for item in data:
        query = str(item.get("queryItem", "")).upper()
        string_id = item.get("stringId", "")
        preferred_name = str(item.get("preferredName", query)).upper()

        if query and string_id:
            gene_to_string[query] = string_id
            mapped_rows.append({
                "query_gene": query,
                "string_id": string_id,
                "preferred_name": preferred_name,
                "annotation": item.get("annotation", "")
            })

    return gene_to_string, mapped_rows


def _query_string_network(string_ids: List[str], species_id: int, required_score: int):
    if len(string_ids) < 2:
        return pd.DataFrame(columns=["source", "target", "combined_score", "source_string_id", "target_string_id"])

    url = f"{STRING_API_BASE}/network"
    params = {
        "identifiers": "\r".join(string_ids),
        "species": species_id,
        "required_score": int(required_score),
        "network_type": "functional"
    }

    resp = requests.post(url, data=params, headers=REQUEST_HEADERS, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    edges = []
    for item in data:
        source = str(item.get("preferredName_A", "")).upper()
        target = str(item.get("preferredName_B", "")).upper()

        if not source or not target or source == target:
            continue

        score = item.get("score", item.get("combined_score", None))
        try:
            score = float(score)
        except Exception:
            score = None

        edges.append({
            "source": source,
            "target": target,
            "combined_score": score,
            "source_string_id": item.get("stringId_A", ""),
            "target_string_id": item.get("stringId_B", "")
        })

    edge_df = pd.DataFrame(edges)

    if len(edge_df) > 0:
        edge_df = edge_df.drop_duplicates(subset=["source", "target"])

    return edge_df


def _analyze_ppi_topology(ppi_edges: pd.DataFrame, all_targets: List[str]):
    G = nx.Graph()

    for gene in all_targets:
        if gene:
            G.add_node(gene)

    if ppi_edges is not None and len(ppi_edges) > 0:
        for _, row in ppi_edges.iterrows():
            s = str(row["source"]).upper()
            t = str(row["target"]).upper()
            weight = row.get("combined_score", 1.0)
            try:
                weight = float(weight)
            except Exception:
                weight = 1.0
            G.add_edge(s, t, weight=weight)

    if G.number_of_nodes() == 0:
        return G, pd.DataFrame(columns=["gene", "degree", "betweenness", "closeness", "eigenvector"])

    degree_dict = dict(G.degree())
    betweenness_dict = nx.betweenness_centrality(G) if G.number_of_edges() > 0 else {n: 0 for n in G.nodes()}
    closeness_dict = nx.closeness_centrality(G) if G.number_of_edges() > 0 else {n: 0 for n in G.nodes()}

    try:
        eigenvector_dict = nx.eigenvector_centrality(G, max_iter=1000)
    except Exception:
        eigenvector_dict = {n: 0 for n in G.nodes()}

    rows = []
    for node in G.nodes():
        rows.append({
            "gene": node,
            "degree": degree_dict.get(node, 0),
            "betweenness": betweenness_dict.get(node, 0),
            "closeness": closeness_dict.get(node, 0),
            "eigenvector": eigenvector_dict.get(node, 0)
        })

    topo_df = pd.DataFrame(rows)
    topo_df = topo_df.sort_values(
        by=["degree", "betweenness", "closeness", "eigenvector"],
        ascending=[False, False, False, False]
    )

    return G, topo_df


def _plot_ppi_network(G: nx.Graph, core_genes: List[str], out_png: Path):
    plt.figure(figsize=(10, 8))

    if G.number_of_nodes() == 0:
        plt.text(0.5, 0.5, "No PPI network available", ha="center", va="center", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(out_png, dpi=180)
        plt.close()
        return

    if G.number_of_edges() > 0:
        pos = nx.spring_layout(G, seed=42, k=0.55)
    else:
        pos = nx.circular_layout(G)

    core_set = set(core_genes)

    degrees = dict(G.degree())
    node_sizes = [300 + degrees.get(n, 0) * 120 for n in G.nodes()]
    node_colors = ["#ef4444" if n in core_set else "#60a5fa" for n in G.nodes()]

    nx.draw_networkx_edges(
        G,
        pos,
        alpha=0.35,
        width=1.2,
        edge_color="#64748b"
    )

    nx.draw_networkx_nodes(
        G,
        pos,
        node_size=node_sizes,
        node_color=node_colors,
        edgecolors="#1f2937",
        linewidths=0.6,
        alpha=0.95
    )

    # 节点太多时只标核心节点，避免糊成毛线团
    if G.number_of_nodes() <= 40:
        labels = {n: n for n in G.nodes()}
    else:
        labels = {n: n for n in core_set if n in G.nodes()}

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=8,
        font_color="#111827"
    )

    plt.title("PPI Network", fontsize=16, fontweight="bold")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def _plot_compound_target_network(edge_df: pd.DataFrame, out_png: Path, max_edges: int = 150):
    plt.figure(figsize=(12, 9))

    if edge_df is None or len(edge_df) == 0:
        plt.text(0.5, 0.5, "No compound-target network available", ha="center", va="center", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(out_png, dpi=180)
        plt.close()
        return

    plot_df = edge_df.head(max_edges).copy()

    G = nx.Graph()

    for _, row in plot_df.iterrows():
        herb = f"Herb:{row['herb']}"
        compound = f"Compound:{row['compound']}"
        target = f"Target:{row['target']}"

        G.add_node(herb, node_type="herb", label=str(row["herb"]))
        G.add_node(compound, node_type="compound", label=str(row["compound"]))
        G.add_node(target, node_type="target", label=str(row["target"]))

        G.add_edge(herb, compound)
        G.add_edge(compound, target)

    pos = nx.spring_layout(G, seed=42, k=0.7)

    color_map = {
        "herb": "#22c55e",
        "compound": "#f59e0b",
        "target": "#60a5fa"
    }

    colors = [color_map.get(G.nodes[n].get("node_type"), "#94a3b8") for n in G.nodes()]
    sizes = []
    for n in G.nodes():
        node_type = G.nodes[n].get("node_type")
        if node_type == "herb":
            sizes.append(900)
        elif node_type == "compound":
            sizes.append(450)
        else:
            sizes.append(320)

    nx.draw_networkx_edges(G, pos, alpha=0.25, width=1.0, edge_color="#64748b")
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=sizes, edgecolors="#1f2937", linewidths=0.4)

    if G.number_of_nodes() <= 60:
        labels = {n: G.nodes[n].get("label", n) for n in G.nodes()}
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=7)

    plt.title("Herb-Compound-Target Network", fontsize=16, fontweight="bold")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def _write_report(
    out_path: Path,
    herbs: str,
    disease: str,
    ob_threshold: float,
    dl_threshold: float,
    active_compound_count: int,
    drug_target_count: int,
    disease_target_count: int,
    intersection_count: int,
    ppi_edge_count: int,
    core_df: pd.DataFrame,
    string_status: str
):
    top_core_md = "暂无核心靶点。"

    if core_df is not None and len(core_df) > 0:
        show_df = core_df.head(20).copy()
        top_core_md = show_df.to_markdown(index=False)

    report = f"""# 网络药理学分析报告

## 1. 分析概览

| 项目 | 内容 |
|---|---|
| 中药/方剂 | {herbs or "未指定"} |
| 疾病 | {disease or "未指定"} |
| OB 阈值 | {ob_threshold} |
| DL 阈值 | {dl_threshold} |
| PPI 数据源 | STRING |
| STRING 状态 | {string_status} |

## 2. 数据统计

| 指标 | 数量 |
|---|---:|
| 筛选后活性成分数 | {active_compound_count} |
| 药物相关靶点数 | {drug_target_count} |
| 疾病靶点数 | {disease_target_count} |
| 药物-疾病交集靶点数 | {intersection_count} |
| PPI 边数量 | {ppi_edge_count} |

## 3. 核心靶点 Top 20

{top_core_md}

## 4. 结果文件说明

| 文件 | 含义 |
|---|---|
| active_compounds.csv | 根据 OB/DL 筛选后的活性成分表 |
| compound_target_edges.csv | Herb-Compound-Target 边表 |
| disease_targets_normalized.csv | 标准化后的疾病靶点 |
| intersection_targets.csv | 药物靶点与疾病靶点交集 |
| string_mapped_targets.csv | STRING ID 映射结果 |
| ppi_edges.csv | PPI 网络边表 |
| ppi_topology_metrics.csv | PPI 拓扑指标 |
| core_targets.csv | 核心靶点 |
| compound_target_network.png | 成分-靶点网络图 |
| ppi_network.png | PPI 网络图 |

## 5. 解释提示

- Degree 越高，说明该靶点在 PPI 网络中连接越多，可能是关键枢纽靶点。
- Betweenness 越高，说明该靶点可能承担网络信息流桥梁作用。
- 核心靶点可继续用于 GO/KEGG 富集分析、分子对接或实验验证。
"""

    out_path.write_text(report, encoding="utf-8")


@register_tool(
    name="run_ppi_network_analysis",
    description="基于基因列表构建 STRING PPI 网络，并进行拓扑分析，输出 PPI 边表、核心靶点表和网络图。PPI 是网络药理学核心功能。",
    parameters={
        "type": "object",
        "properties": {
            "target_file": {
                "type": "string",
                "description": "靶点基因文件，支持 csv/tsv/xlsx，需包含 gene 或 target 列"
            },
            "species": {
                "type": "string",
                "description": "物种，human 或 mouse",
                "default": "human"
            },
            "ppi_confidence": {
                "type": "number",
                "description": "STRING 置信度，0-1。0.4=medium，0.7=high，0.9=highest",
                "default": 0.7
            },
            "top_n": {
                "type": "integer",
                "description": "输出核心靶点数量",
                "default": 20
            }
        },
        "required": ["target_file"]
    }
)
def run_ppi_network_analysis(
    target_file: str,
    species: str = "human",
    ppi_confidence: float = 0.7,
    top_n: int = 20,
    session_id: str = None
):
    try:
        job_id, job_dir = _make_job_dir("ppi_network_analysis")

        target_df, _ = _read_table_any(target_file, session_id=session_id)
        disease_target_df = _prepare_disease_targets(target_df)
        genes = disease_target_df["gene"].dropna().astype(str).str.upper().unique().tolist()

        if len(genes) < 2:
            return _safe_json_dumps({
                "status": "error",
                "message": "有效基因数量少于 2，无法构建 PPI 网络。"
            })

        species_id = _string_species_id(species)
        required_score = int(max(0, min(float(ppi_confidence), 1)) * 1000)

        string_status = "success"
        mapped_rows = []
        ppi_edges = pd.DataFrame(columns=["source", "target", "combined_score", "source_string_id", "target_string_id"])

        try:
            gene_to_string, mapped_rows = _map_genes_to_string_ids(genes, species_id)
            string_ids = list(gene_to_string.values())
            ppi_edges = _query_string_network(string_ids, species_id, required_score)
        except Exception as e:
            string_status = f"STRING 查询失败：{str(e)}。已输出空 PPI 网络。"

        mapped_df = pd.DataFrame(mapped_rows)
        if len(mapped_df) == 0:
            mapped_df = pd.DataFrame(columns=["query_gene", "string_id", "preferred_name", "annotation"])

        all_ppi_targets = sorted(set(genes))
        G, topo_df = _analyze_ppi_topology(ppi_edges, all_ppi_targets)

        top_n = max(1, int(top_n or 20))
        core_df = topo_df.head(top_n).copy()

        disease_target_df.to_csv(job_dir / "input_targets_normalized.csv", index=False, encoding="utf-8-sig")
        mapped_df.to_csv(job_dir / "string_mapped_targets.csv", index=False, encoding="utf-8-sig")
        ppi_edges.to_csv(job_dir / "ppi_edges.csv", index=False, encoding="utf-8-sig")
        topo_df.to_csv(job_dir / "ppi_topology_metrics.csv", index=False, encoding="utf-8-sig")
        core_df.to_csv(job_dir / "core_targets.csv", index=False, encoding="utf-8-sig")

        _plot_ppi_network(G, core_df["gene"].tolist() if len(core_df) > 0 else [], job_dir / "ppi_network.png")

        _write_report(
            out_path=job_dir / "ppi_analysis_report.md",
            herbs="",
            disease="",
            ob_threshold=0,
            dl_threshold=0,
            active_compound_count=0,
            drug_target_count=len(genes),
            disease_target_count=0,
            intersection_count=len(genes),
            ppi_edge_count=len(ppi_edges),
            core_df=core_df,
            string_status=string_status
        )

        return _safe_json_dumps({
            "status": "success",
            "message": "PPI 网络分析完成。",
            "job_id": job_id,
            "job_dir": f"generated/{job_id}",
            "summary": {
                "input_gene_count": len(genes),
                "mapped_string_count": len(mapped_df),
                "ppi_edge_count": len(ppi_edges),
                "core_target_count": len(core_df),
                "species_id": species_id,
                "required_score": required_score,
                "string_status": string_status
            },
            "output_files": _list_output_files(job_dir)
        })

    except Exception as e:
        return _safe_json_dumps({
            "status": "error",
            "message": f"PPI 网络分析失败：{str(e)}"
        })


@register_tool(
    name="run_network_pharmacology_analysis",
    description="执行中药网络药理学分析。输入 TCMSP 风格成分-靶点表和疾病靶点表，筛选活性成分，构建成分-靶点网络，取药物-疾病交集靶点，调用 STRING 构建 PPI 网络并筛选核心靶点。",
    parameters={
        "type": "object",
        "properties": {
            "compound_target_file": {
                "type": "string",
                "description": "TCMSP/中药成分-靶点表，支持 csv/tsv/xlsx。建议包含 herb, compound, OB, DL, target 列"
            },
            "disease_target_file": {
                "type": "string",
                "description": "疾病靶点表，支持 csv/tsv/xlsx，需包含 gene 或 target 列"
            },
            "herbs": {
                "type": "string",
                "description": "中药或方剂名称，可选，仅用于报告展示",
                "default": ""
            },
            "disease": {
                "type": "string",
                "description": "疾病名称，可选，仅用于报告展示",
                "default": ""
            },
            "ob_threshold": {
                "type": "number",
                "description": "OB 阈值，默认 30",
                "default": 30
            },
            "dl_threshold": {
                "type": "number",
                "description": "DL 阈值，默认 0.18",
                "default": 0.18
            },
            "species": {
                "type": "string",
                "description": "物种，human 或 mouse",
                "default": "human"
            },
            "ppi_confidence": {
                "type": "number",
                "description": "STRING PPI 置信度，0-1。0.4=medium，0.7=high",
                "default": 0.7
            },
            "top_n": {
                "type": "integer",
                "description": "核心靶点数量",
                "default": 20
            }
        },
        "required": ["compound_target_file", "disease_target_file"]
    }
)
def run_network_pharmacology_analysis(
    compound_target_file: str,
    disease_target_file: str,
    herbs: str = "",
    disease: str = "",
    ob_threshold: float = 30,
    dl_threshold: float = 0.18,
    species: str = "human",
    ppi_confidence: float = 0.7,
    top_n: int = 20,
    session_id: str = None
):
    try:
        job_id, job_dir = _make_job_dir("network_pharmacology")

        compound_df, compound_real_path = _read_table_any(compound_target_file, session_id=session_id)
        disease_df, disease_real_path = _read_table_any(disease_target_file, session_id=session_id)

        active_compounds, compound_target_edges = _prepare_compound_target_data(
            compound_df,
            ob_threshold=float(ob_threshold),
            dl_threshold=float(dl_threshold)
        )

        if len(compound_target_edges) == 0:
            return _safe_json_dumps({
                "status": "error",
                "message": "没有得到有效的化合物-靶点边。请检查 compound_target_file 是否包含 compound/target 列，以及 OB/DL 阈值是否过高。",
                "debug": {
                    "compound_file": str(compound_real_path),
                    "columns": list(compound_df.columns)
                }
            })

        disease_targets = _prepare_disease_targets(disease_df)

        drug_targets = sorted(compound_target_edges["target"].dropna().astype(str).str.upper().unique().tolist())
        disease_target_set = set(disease_targets["gene"].dropna().astype(str).str.upper().tolist())

        intersection_targets = sorted(set(drug_targets) & disease_target_set)

        intersection_df = pd.DataFrame({"gene": intersection_targets})

        active_compounds.to_csv(job_dir / "active_compounds.csv", index=False, encoding="utf-8-sig")
        compound_target_edges.to_csv(job_dir / "compound_target_edges.csv", index=False, encoding="utf-8-sig")
        disease_targets.to_csv(job_dir / "disease_targets_normalized.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame({"gene": drug_targets}).to_csv(job_dir / "drug_targets.csv", index=False, encoding="utf-8-sig")
        intersection_df.to_csv(job_dir / "intersection_targets.csv", index=False, encoding="utf-8-sig")

        _plot_compound_target_network(compound_target_edges, job_dir / "compound_target_network.png")

        species_id = _string_species_id(species)
        required_score = int(max(0, min(float(ppi_confidence), 1)) * 1000)

        string_status = "success"
        mapped_rows = []
        ppi_edges = pd.DataFrame(columns=["source", "target", "combined_score", "source_string_id", "target_string_id"])

        if len(intersection_targets) >= 2:
            try:
                gene_to_string, mapped_rows = _map_genes_to_string_ids(intersection_targets, species_id)
                string_ids = list(gene_to_string.values())
                ppi_edges = _query_string_network(string_ids, species_id, required_score)
            except Exception as e:
                string_status = f"STRING 查询失败：{str(e)}。已继续生成本地结果，但 PPI 为空。"
        else:
            string_status = "交集靶点少于 2 个，无法构建 PPI。"

        mapped_df = pd.DataFrame(mapped_rows)
        if len(mapped_df) == 0:
            mapped_df = pd.DataFrame(columns=["query_gene", "string_id", "preferred_name", "annotation"])

        G, topo_df = _analyze_ppi_topology(ppi_edges, intersection_targets)

        top_n = max(1, int(top_n or 20))
        core_df = topo_df.head(top_n).copy()

        mapped_df.to_csv(job_dir / "string_mapped_targets.csv", index=False, encoding="utf-8-sig")
        ppi_edges.to_csv(job_dir / "ppi_edges.csv", index=False, encoding="utf-8-sig")
        topo_df.to_csv(job_dir / "ppi_topology_metrics.csv", index=False, encoding="utf-8-sig")
        core_df.to_csv(job_dir / "core_targets.csv", index=False, encoding="utf-8-sig")

        _plot_ppi_network(G, core_df["gene"].tolist() if len(core_df) > 0 else [], job_dir / "ppi_network.png")

        _write_report(
            out_path=job_dir / "network_pharmacology_report.md",
            herbs=herbs,
            disease=disease,
            ob_threshold=ob_threshold,
            dl_threshold=dl_threshold,
            active_compound_count=len(active_compounds),
            drug_target_count=len(drug_targets),
            disease_target_count=len(disease_targets),
            intersection_count=len(intersection_targets),
            ppi_edge_count=len(ppi_edges),
            core_df=core_df,
            string_status=string_status
        )

        return _safe_json_dumps({
            "status": "success",
            "message": "网络药理学分析完成。",
            "job_id": job_id,
            "job_dir": f"generated/{job_id}",
            "summary": {
                "compound_file": str(compound_real_path),
                "disease_target_file": str(disease_real_path),
                "active_compound_count": len(active_compounds),
                "compound_target_edge_count": len(compound_target_edges),
                "drug_target_count": len(drug_targets),
                "disease_target_count": len(disease_targets),
                "intersection_target_count": len(intersection_targets),
                "mapped_string_count": len(mapped_df),
                "ppi_edge_count": len(ppi_edges),
                "core_target_count": len(core_df),
                "species_id": species_id,
                "required_score": required_score,
                "string_status": string_status
            },
            "output_files": _list_output_files(job_dir)
        })

    except Exception as e:
        return _safe_json_dumps({
            "status": "error",
            "message": f"网络药理学分析失败：{str(e)}"
        })