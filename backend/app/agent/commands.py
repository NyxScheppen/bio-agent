"""
斜杠命令系统 (Phase 5.3: Slash Commands).

参考 ECC 的 92 个 slash commands，提供快捷命令直接映射到 Skill 或工具类别。

用法:
    /survival → 激活 single_gene_survival Skill
    /deg → 激活 bulk_rnaseq_deg Skill
    /env → 调用 scan_system_config
"""

from typing import Any, Dict, Optional

COMMANDS: Dict[str, Dict[str, Any]] = {
    "/survival": {
        "skill": "single_gene_survival",
        "description": "单基因生存分析",
        "example": "/survival 对 TP53 做生存分析",
    },
    "/cox": {
        "skill": "univariate_cox_batch",
        "description": "批量单因素 Cox 回归",
        "example": "/cox 对全部基因做 Cox 筛选",
    },
    "/lasso": {
        "skill": "lasso_cox_model",
        "description": "LASSO-Cox 预后模型",
        "example": "/lasso 构建预后模型",
    },
    "/risk": {
        "skill": "prognostic_risk_model",
        "description": "预后风险评分模型",
        "example": "/risk 构建风险评分",
    },
    "/deg": {
        "skill": "bulk_rnaseq_deg",
        "description": "差异表达分析（limma）",
        "example": "/deg 对照组 vs 实验组",
    },
    "/deseq2": {
        "skill": "deseq2_count_deg",
        "description": "DESeq2 差异分析（count数据）",
        "example": "/deseq2 对照组 vs 实验组",
    },
    "/pca": {
        "skill": "bulk_pca_analysis",
        "description": "PCA 主成分分析",
        "example": "/pca 用表达矩阵做 PCA",
    },
    "/enrich": {
        "skill": "go_enrichment",
        "description": "GO/KEGG 富集分析",
        "example": "/enrich 对 DEG 基因做富集分析",
    },
    "/gsea": {
        "skill": "gsea_prerank",
        "description": "GSEA 基因集富集分析",
        "example": "/gsea 用排序基因表做 GSEA",
    },
    "/ml": {
        "skill": "ml_binary_classification",
        "description": "机器学习分类模型",
        "example": "/ml 训练二分类模型",
    },
    "/compare": {
        "skill": "multi_model_comparison",
        "description": "多模型比较",
        "example": "/compare 比较 RF/SVM/XGBoost",
    },
    "/ppi": {
        "skill": "ppi_network_analysis",
        "description": "PPI 蛋白互作网络",
        "example": "/ppi 构建基因列表的 PPI",
    },
    "/netpharm": {
        "skill": "network_pharm_full",
        "description": "网络药理学全流程",
        "example": "/netpharm 中药成分-靶点-疾病分析",
    },
    "/scrna": {
        "skill": "scrna_standard_pipeline",
        "description": "单细胞标准流程",
        "example": "/scrna 分析 10x 数据",
    },
    "/probe": {
        "skill": "file_probe",
        "description": "文件预览与探测",
        "example": "/probe 看看这个文件",
    },
    "/geo": {
        "skill": "geo_data_download",
        "description": "GEO 数据下载",
        "example": "/geo GSE84402",
    },
    "/lit": {
        "task_type": "literature",
        "tool_categories": ["literature"],
        "description": "文献检索",
        "example": "/lit 搜索 PD-L1 免疫治疗",
    },
    "/env": {
        "task_type": "system",
        "tool_categories": ["system"],
        "description": "检测 R/Python 运行环境",
        "example": "/env",
    },
    "/help": {
        "task_type": "general",
        "description": "显示可用命令",
        "example": "/help",
    },
}


def resolve_command(user_message: str) -> Optional[Dict[str, Any]]:
    """
    解析用户消息中的斜杠命令。

    如果消息以 / 开头且匹配已知命令，返回命令的元信息。
    否则返回 None（走正常 Router 流程）。

    Returns:
        None 或 {"skill": "...", "task_type": "...", "original_text": "..."}
    """
    text = (user_message or "").strip()
    if not text.startswith("/"):
        return None

    # 提取命令名和参数
    parts = text.split(maxsplit=1)
    command = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        return build_help_response()

    cmd_info = COMMANDS.get(command)
    if not cmd_info:
        return None

    result = dict(cmd_info)
    result["original_text"] = text

    # 如果有剩余文本，作为用户意图追加
    if rest:
        result["user_intent"] = rest
        result["command"] = command

    return result


def build_help_response() -> Dict[str, Any]:
    """构建 /help 命令的响应。"""
    lines = ["可用命令：", ""]
    by_category: Dict[str, list] = {}

    for cmd, info in sorted(COMMANDS.items()):
        skill = info.get("skill", "")
        if skill:
            # 从 skill_id 推断类别
            parts = skill.split("_")
            cat = parts[0] if parts else "general"
        else:
            cat = "general"
        by_category.setdefault(cat, []).append((cmd, info))

    help_text = ""
    for cat, cmds in sorted(by_category.items()):
        help_text += f"\n**{cat}**\n"
        for cmd, info in cmds:
            help_text += f"- `{cmd}` — {info['description']}\n"

    return {
        "task_type": "general",
        "suggested_mode": "direct_answer",
        "tool_categories": ["general"],
        "help_text": help_text,
        "total_commands": len(COMMANDS),
    }
