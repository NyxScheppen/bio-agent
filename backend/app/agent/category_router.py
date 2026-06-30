from typing import Any, Dict, List

from app.agent.tool_registry import (
    TOOLS_SCHEMA,
    TOOL_META,
    get_tool_meta,
    get_tools_schema_by_categories,
    normalize_tool_category,
)

TOOL_CATEGORY_KEYWORDS = {
    "survival": [
        "survival",
        "cox",
        "kaplan",
        "km",
        "lasso_cox",
        "risk_model",
        "risk_group",
        "time_roc",
        "prognostic",
        "预后",
        "生存",
        "风险模型",
    ],
    "transcriptome": [
        "bulk",
        "rnaseq",
        "rna_seq",
        "deg",
        "deseq2",
        "pca",
        "limma",
        "表达矩阵",
        "差异",
        "转录组",
    ],
    "file_io": [
        "file",
        "preview",
        "probe",
        "read",
        "upload",
        "table",
        "csv",
        "xlsx",
        "文件",
        "预览",
        "解包",
        "探测",
    ],
    "system": [
        "system",
        "config",
        "environment",
        "rscript",
        "scan_system",
        "系统",
        "环境",
    ],
    "enrichment": [
        "go",
        "kegg",
        "gsea",
        "gsva",
        "enrich",
        "pathway",
        "富集",
        "通路",
    ],
    "ml": [
        "machine_learning",
        "random_forest",
        "svm",
        "xgboost",
        "logistic",
        "classifier",
        "机器学习",
        "分类",
    ],
    "modeling": [
        "docking",
        "pdb",
        "protein",
        "structure",
        "ligand",
        "分子对接",
        "蛋白",
        "结构",
    ],
    "drug_screening": [
        "drug",
        "screening",
        "candidate",
        "药物",
        "筛选",
    ],
    "aptamer": [
        "aptamer",
        "适配体",
    ],
}

TEXT_CATEGORY_KEYWORDS = {
    "survival": [
        "生存", "预后", "cox", "km", "kaplan", "lasso-cox",
        "lasso cox", "风险模型", "risk model", "time roc", "timeroc",
        "单因素cox", "多因素cox", "风险评分"
    ],
    "transcriptome": [
        "差异分析", "差异表达", "deg", "deseq2", "limma",
        "bulk", "rnaseq", "rna-seq", "表达矩阵", "pca", "转录组"
    ],
    "file_io": [
        "文件", "上传", "读取", "预览", "解包", "格式", "csv",
        "tsv", "xlsx", "txt", "gz", "zip", "看看", "探测"
    ],
    "system": [
        "r环境", "r 环境", "rscript", "r版本", "检测环境",
        "系统环境", "依赖", "找不到r", "找不到 r", "package not found",
        "there is no package", "r包", "环境变量", "path"
    ],
    "enrichment": [
        "富集", "go", "kegg", "gsea", "gsva", "通路"
    ],
    "ml": [
        "机器学习", "分类模型", "随机森林", "svm", "lasso", "xgboost", "auc"
    ],
    "modeling": [
        "蛋白", "结构", "pdb", "分子对接", "docking", "ligand"
    ],
    "drug_screening": [
        "药物筛选", "候选药物", "drug screening"
    ],
    "aptamer": [
        "适配体", "aptamer"
    ],
}

def normalize_categories(categories: list) -> List[str]:
    out = []
    for c in categories or []:
        nc = normalize_tool_category(c)
        if nc and nc not in out:
            out.append(nc)
    return out

def infer_category_from_tool_name(tool_name: str, description: str = "") -> str:
    """
    当工具注册时没有显式 category，根据工具名和描述自动推断类别。
    """
    text = f"{tool_name} {description}".lower()

    for category, keywords in TOOL_CATEGORY_KEYWORDS.items():
        if any(k.lower() in text for k in keywords):
            return category

    return "general"

def get_effective_tool_category(tool_name: str) -> str:
    """
    获取工具有效 category：
    1. 优先用 TOOL_META 中注册的 category
    2. 如果是 general 或空，则根据工具名/描述自动推断
    """
    meta = get_tool_meta(tool_name) or {}
    category = meta.get("category") or ""

    if category and category != "general":
        return normalize_tool_category(category)

    description = meta.get("description", "")
    inferred = infer_category_from_tool_name(tool_name, description)
    return normalize_tool_category(inferred)

def infer_categories_from_text(text: str) -> List[str]:
    """
    根据用户请求推断工具组。
    """
    text = (text or "").lower()
    cats = []

    for category, keywords in TEXT_CATEGORY_KEYWORDS.items():
        if any(k.lower() in text for k in keywords):
            cats.append(category)

    return normalize_categories(cats)

def collect_preferred_tools_from_plan(planner_result: Dict[str, Any]) -> List[str]:
    tools = []

    for step in planner_result.get("steps", []) or []:
        for t in step.get("preferred_tools", []) or []:
            if isinstance(t, str) and t not in tools:
                tools.append(t)

    return tools

def categories_from_preferred_tools(tool_names: List[str]) -> List[str]:
    cats = []

    for name in tool_names or []:
        cat = get_effective_tool_category(name)
        if cat and cat not in cats:
            cats.append(cat)

    return normalize_categories(cats)

def text_needs_system_tools(text: str) -> bool:
    text = (text or "").lower()
    keywords = TEXT_CATEGORY_KEYWORDS["system"]
    return any(k.lower() in text for k in keywords)

def should_include_system_tools(
    context_pack: Dict[str, Any],
    router_result: Dict[str, Any],
    planner_result: Dict[str, Any]
) -> bool:
    """
    只有涉及环境、Rscript、R 包、执行错误诊断时开放 system 工具。
    """
    text = "\n".join([
        context_pack.get("latest_user_message", ""),
        str(router_result),
        str(planner_result),
    ]).lower()

    return text_needs_system_tools(text)

def resolve_tool_categories(
    context_pack: Dict[str, Any],
    router_result: Dict[str, Any],
    planner_result: Dict[str, Any] = None
) -> List[str]:
    """
    统一决定本轮启用哪些工具组。

    优先级：
    1. Planner.tool_categories
    2. Router.tool_categories
    3. Planner.preferred_tools 反推
    4. 用户文本关键词推断
    5. general
    """
    planner_result = planner_result or {}

    cats = []

    cats.extend(planner_result.get("tool_categories", []) or [])
    cats.extend(router_result.get("tool_categories", []) or [])

    preferred_tools = collect_preferred_tools_from_plan(planner_result)
    cats.extend(categories_from_preferred_tools(preferred_tools))

    latest_text = context_pack.get("latest_user_message", "")
    cats.extend(infer_categories_from_text(latest_text))

    cats = normalize_categories(cats)

    if not cats:
        cats = ["general"]

    mode = (
        planner_result.get("execution_mode")
        or router_result.get("suggested_mode")
        or ""
    )

    # 只要要执行工具，就默认开放 file_io
    # 因为大部分生信任务都先要预览/确认文件结构
    if mode == "tool_execution" and "file_io" not in cats:
        cats.insert(0, "file_io")

    # 涉及 R 环境、依赖、Rscript 时开放 system
    if should_include_system_tools(context_pack, router_result, planner_result):
        if "system" not in cats:
            cats.append("system")

    return cats

def filter_tools_schema_by_effective_categories(
    categories: List[str],
    include_file_io: bool = True,
    include_system: bool = False
) -> List[dict]:
    """
    不完全依赖 TOOL_META.category。
    即使工具注册时没写 category，也能根据工具名自动归类。
    """
    categories = set(normalize_categories(categories))

    if include_file_io:
        categories.add("file_io")

    if include_system:
        categories.add("system")

    filtered = []

    for item in TOOLS_SCHEMA:
        fn = item.get("function", {})
        name = fn.get("name", "")
        if not name:
            continue

        effective_cat = get_effective_tool_category(name)

        if effective_cat in categories:
            filtered.append(item)

    return filtered

def filter_tools_schema_by_plan(
    router_result: Dict[str, Any],
    planner_result: Dict[str, Any],
    context_pack: Dict[str, Any]
) -> List[dict]:
    """
    过滤 Executor 可见工具。

    逻辑：
    1. 如果 Planner 明确 preferred_tools，则暴露 preferred_tools + file_io + 必要 system
    2. 否则按 resolve_tool_categories 暴露工具组
    3. 不再完全依赖工具注册时的 category，支持自动推断
    """
    preferred_tools = collect_preferred_tools_from_plan(planner_result)

    include_system = should_include_system_tools(
        context_pack=context_pack,
        router_result=router_result,
        planner_result=planner_result
    )

    if preferred_tools:
        allowed_names = set(preferred_tools)

        # 文件工具永远补上
        for item in TOOLS_SCHEMA:
            fn = item.get("function", {})
            name = fn.get("name", "")
            cat = get_effective_tool_category(name)
            if cat == "file_io":
                allowed_names.add(name)

        # system 工具按需补上
        if include_system:
            for item in TOOLS_SCHEMA:
                fn = item.get("function", {})
                name = fn.get("name", "")
                cat = get_effective_tool_category(name)
                if cat == "system":
                    allowed_names.add(name)

        filtered = []
        for item in TOOLS_SCHEMA:
            fn = item.get("function", {})
            if fn.get("name") in allowed_names:
                filtered.append(item)

        if filtered:
            return filtered

    categories = resolve_tool_categories(
        context_pack=context_pack,
        router_result=router_result,
        planner_result=planner_result
    )

    filtered = filter_tools_schema_by_effective_categories(
        categories=categories,
        include_file_io=True,
        include_system=include_system
    )

    if filtered:
        return filtered

    # 兜底：file_io + general
    fallback = filter_tools_schema_by_effective_categories(
        categories=["file_io", "general"],
        include_file_io=True,
        include_system=include_system
    )

    return fallback or TOOLS_SCHEMA
