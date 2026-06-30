import re
import inspect
from typing import Dict, List, Any, Optional, get_type_hints

TOOL_REGISTRY: Dict[str, Any] = {}
TOOLS_SCHEMA: List[dict] = []

# 新增：工具元信息，不传给 OpenAI，只给后端路由用
TOOL_META: Dict[str, dict] = {}

# 记录已加载的模块，用于 auto_discover 避免重复
_LOADED_TOOL_MODULES: set = set()

VALID_TOOL_CATEGORIES = {
    "file_io",
    "basic",
    "literature",
    "single_gene",
    "survival",
    "transcriptome",
    "enrichment",
    "ml",
    "network_pharmacology",
    "perturbation",
    "scrna",
    "spatial",
    "modeling",
    "drug_screening",
    "aptamer",
    "system",
    "general",
}

def normalize_tool_category(category: Optional[str]) -> str:
    """
    统一工具分类名。
    """
    if not category:
        return "general"

    category = str(category).strip().lower()

    aliases = {
        "file": "file_io",
        "files": "file_io",
        "io": "file_io",
        "literature_search": "literature",
        "paper": "literature",
        "papers": "literature",
        "single": "single_gene",
        "gene": "single_gene",
        "cox": "survival",
        "prognosis": "survival",
        "prognostic": "survival",
        "bulk": "transcriptome",
        "rnaseq": "transcriptome",
        "rna_seq": "transcriptome",
        "deg": "transcriptome",
        "go_kegg": "enrichment",
        "pathway": "enrichment",
        "machine_learning": "ml",
        "network": "network_pharmacology",
        "netpharm": "network_pharmacology",
        "ppi": "network_pharmacology",
        "virtual_knockout": "perturbation",
        "virtual_knockdown": "perturbation",
        "single_cell": "scrna",
        "scRNA": "scrna",
        "sc": "scrna",
        "spatial_transcriptome": "spatial",
    }

    category = aliases.get(category, category)

    if category not in VALID_TOOL_CATEGORIES:
        return "general"

    return category

def infer_tool_category(name: str, description: str = "") -> str:
    """
    根据工具名和描述自动推断 category。
    这样你不用立刻改所有工具文件。
    """
    text = f"{name} {description}".lower()

    rules = [
        ("file_io", [
            "read_csv", "preview_table", "load_large", "file", "读取", "预览"
        ]),
        ("literature", [
            "literature", "paper", "pubmed", "pmid", "pmcid", "doi",
            "crossref", "europe", "pdf", "文献", "论文"
        ]),
        ("network_pharmacology", [
            "network_pharmacology", "ppi", "string", "tcmsp",
            "compound", "herb", "target", "网络药理", "成分", "靶点"
        ]),
        ("ml", [
            "ml_", "machine", "classification", "lasso_feature",
            "multi_model", "svm", "random forest", "机器学习", "分类模型"
        ]),
        ("survival", [
            "survival", "cox", "lasso_cox", "prognostic", "risk_model",
            "time_roc", "生存", "预后"
        ]),
        ("single_gene", [
            "single_gene", "gene_expression", "clinical_association",
            "expression_correlation", "single gene", "单基因"
        ]),
        ("transcriptome", [
            "bulk", "rnaseq", "rna_seq", "deg", "deseq2", "pca",
            "transcriptome", "差异表达", "转录组"
        ]),
        ("enrichment", [
            "enrichment", "go", "kegg", "gsea", "gsva",
            "富集", "通路"
        ]),
        ("perturbation", [
            "virtual", "knockdown", "knockout", "perturbation",
            "敲低", "敲除", "扰动"
        ]),
        ("scrna", [
            "scrna", "single_cell", "seurat", "marker", "单细胞"
        ]),
        ("spatial", [
            "spatial", "空间转录组"
        ]),
        ("modeling", [
            "docking", "protein", "pdb", "structure", "ligand",
            "分子对接", "蛋白结构"
        ]),
        ("drug_screening", [
            "drug", "screening", "compound_screening", "药物筛选"
        ]),
        ("aptamer", [
            "aptamer", "适配体"
        ]),
        ("basic", [
            "gc_content", "calculate_gc", "gc含量"
        ]),
        ("system", [
            "system", "list", "health", "debug"
        ]),
    ]

    for category, keywords in rules:
        for keyword in keywords:
            if keyword.lower() in text:
                return category

    return "general"

def register_tool(
    name: str,
    description: str,
    parameters: dict = None,
    category: str = None,
    tags: list = None,
    task_types: list = None,
    params_model: Any = None,
    timeout: int = None,              # Feature 1: per-tool timeout seconds
    max_memory_mb: int = None,        # Feature 1: per-tool memory limit MB
    recovery_strategies: list = None, # Feature 3: list of RecoveryStrategy
    racing_group: str = None,         # Phase 1: racing group for waterfall racing
):
    """
    工具注册装饰器。

    【旧写法 - 仍兼容】
    @register_tool(name="xxx", description="xxx", parameters={...})

    【新写法 - Pydantic params_model】
    @register_tool(
        name="xxx",
        description="xxx",
        category="survival",
        params_model=MyParamsModel,
        tags=["cox", "prognosis"]
    )

    【最简写法 - 自动从函数签名生成 schema】
    @register_tool(name="xxx", description="xxx")

    【资源限制 (Feature 1)】
    @register_tool(name="xxx", description="xxx", timeout=3600, max_memory_mb=8192)

    【竞速分组 (Phase 1.2)】
    @register_tool(name="xxx", description="xxx", racing_group="deg_analysis")
    同 racing_group 的工具可以被 Waterfall Racing 竞速执行。

    schema 优先级：
    1. 显式 parameters dict
    2. params_model (Pydantic)
    3. 函数签名自动推导
    """
    if parameters is None and params_model is None:
        # 延迟解析：decorator 执行时还没拿到 func，先在 decorator 内处理
        pass

    def decorator(func):
        nonlocal parameters

        final_category = normalize_tool_category(
            category or infer_tool_category(name, description)
        )

        # 决定 schema 来源
        schema_source = "manual"

        if parameters is not None:
            # 显式 parameters dict - 最高优先级
            schema_source = "manual"
            final_parameters = parameters
        elif params_model is not None:
            # Pydantic params_model
            schema_source = "pydantic_model"
            final_parameters = _pydantic_to_openai_schema(params_model)
        else:
            # 从函数签名自动生成
            schema_source = "function_signature"
            final_parameters = _signature_to_openai_schema(func)

        TOOL_REGISTRY[name] = func

        TOOLS_SCHEMA.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": final_parameters
            }
        })

        TOOL_META[name] = {
            "name": name,
            "description": description,
            "category": final_category,
            "tags": tags or [],
            "task_types": task_types or [],
            "schema_source": schema_source,
            "timeout": timeout,                      # Feature 1
            "max_memory_mb": max_memory_mb,          # Feature 1
            "recovery_strategies": recovery_strategies or [],  # Feature 3
            "racing_group": racing_group,             # Phase 1.2
        }

        if params_model is not None:
            TOOL_META[name]["params_model"] = params_model

        # 给函数本身也挂一下，方便 debug
        setattr(func, "__tool_name__", name)
        setattr(func, "__tool_category__", final_category)
        setattr(func, "__tool_tags__", tags or [])
        setattr(func, "__tool_schema_source__", schema_source)

        return func

    return decorator


# ============================================================
# Schema 自动生成
# ============================================================

def _pydantic_to_openai_schema(params_model: Any) -> dict:
    """
    将 Pydantic 模型转换为 OpenAI function parameters schema。

    支持 Pydantic v1 (.schema()) 和 v2 (.model_json_schema())。
    """
    try:
        # Pydantic v2
        if hasattr(params_model, "model_json_schema"):
            raw = params_model.model_json_schema()
        # Pydantic v1
        elif hasattr(params_model, "schema"):
            raw = params_model.schema()
        else:
            return {"type": "object", "properties": {}}
    except Exception:
        return {"type": "object", "properties": {}}

    # Pydantic schema → OpenAI schema
    result: Dict[str, Any] = {
        "type": "object",
        "properties": {},
    }

    properties = raw.get("properties", {})
    required_list = raw.get("required", [])

    for prop_name, prop_schema in properties.items():
        openai_prop = _convert_json_schema_prop(prop_schema)
        result["properties"][prop_name] = openai_prop

    if required_list:
        # OpenAI 要求 required 在顶层
        result["required"] = [
            r for r in required_list
            if r in result["properties"]
        ]

    return result


def _convert_json_schema_prop(prop_schema: dict) -> dict:
    """将单个 JSON Schema property 转为 OpenAI 格式。"""
    result: Dict[str, Any] = {}

    prop_type = prop_schema.get("type", "string")

    # 处理 anyOf / oneOf（常用于 Optional / Union）
    if "anyOf" in prop_schema:
        types = [t.get("type") for t in prop_schema["anyOf"] if "type" in t]
        non_null = [t for t in types if t != "null"]
        if non_null:
            prop_type = non_null[0]
    elif "oneOf" in prop_schema:
        types = [t.get("type") for t in prop_schema["oneOf"] if "type" in t]
        non_null = [t for t in types if t != "null"]
        if non_null:
            prop_type = non_null[0]

    result["type"] = prop_type

    # description
    if "description" in prop_schema:
        result["description"] = str(prop_schema["description"])

    # title fallback
    if "title" in prop_schema and "description" not in result:
        result["description"] = str(prop_schema["title"])

    # default
    if "default" in prop_schema:
        result["default"] = prop_schema["default"]

    # enum
    if "enum" in prop_schema:
        result["enum"] = prop_schema["enum"]

    # 对于 array 类型，添加 items
    if prop_type == "array" and "items" in prop_schema:
        result["items"] = _convert_json_schema_prop(prop_schema["items"])

    return result


def _signature_to_openai_schema(func) -> dict:
    """
    从函数签名和类型注解自动生成 OpenAI function parameters schema。

    Python type → JSON Schema type 映射：
    - str → "string"
    - int → "integer"
    - float → "number"
    - bool → "boolean"
    - list → "array" (items: string)
    - Optional[X] → X (从 required 中移除)
    """
    result: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    try:
        sig = inspect.signature(func)
        hints = {}
        try:
            hints = get_type_hints(func)
        except Exception:
            pass
    except Exception:
        return result

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls", "session_id", "job_dir", "context"):
            continue

        type_hint = hints.get(param_name)
        prop = _type_hint_to_prop(param.annotation, type_hint)

        # 检查是否有默认值 → 非必填
        has_default = param.default is not inspect.Parameter.empty

        if has_default:
            if param.default is not None:
                prop["default"] = param.default
        else:
            # 必填
            result["required"].append(param_name)

        result["properties"][param_name] = prop

    if not result["required"]:
        del result["required"]

    return result


_PYTHON_TO_JSON_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _type_hint_to_prop(annotation, type_hint=None) -> dict:
    """将 Python 类型注解转为 OpenAI property schema。"""
    target = type_hint or annotation

    # 处理 Optional / Union with None
    if hasattr(target, "__origin__"):
        origin = target.__origin__
        args = getattr(target, "__args__", ())

        # Optional[X] = Union[X, None]
        if origin is type(None):
            return {"type": "string"}

        # 检查是不是 Union
        import typing
        if hasattr(typing, "Union") and origin is typing.Union:
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                return _type_hint_to_prop(non_none[0])
            return {"type": "string"}

        # List[X]
        if origin is list:
            return {"type": "array", "items": {"type": "string"}}

        # Dict
        if origin is dict:
            return {"type": "object"}

    # 直接映射
    if target in _PYTHON_TO_JSON_TYPE:
        return {"type": _PYTHON_TO_JSON_TYPE[target]}

    # 字符串形式的注解（如 "str", "int"）
    if isinstance(target, str):
        json_type = _PYTHON_TO_JSON_TYPE.get(
            {"str": str, "int": int, "float": float, "bool": bool, "list": list}.get(target)
        )
        return {"type": json_type or "string"}

    return {"type": "string"}

def get_tool_meta(name: str) -> dict:
    return TOOL_META.get(name, {
        "name": name,
        "description": "",
        "category": "general",
        "tags": [],
        "task_types": [],
        "timeout": None,
        "max_memory_mb": None,
        "recovery_strategies": [],
        "racing_group": None,
    })

def get_tool_schema_by_name(name: str) -> dict:
    for item in TOOLS_SCHEMA:
        fn = item.get("function", {})
        if fn.get("name") == name:
            return item
    return None

def get_tools_schema_by_categories(
    categories: list,
    include_file_io: bool = True,
    include_system: bool = False,
    fallback_all: bool = False
) -> List[dict]:
    """
    根据 category 过滤 tools schema。
    """
    normalized = set()
    for c in categories or []:
        normalized.add(normalize_tool_category(c))

    if include_file_io:
        normalized.add("file_io")

    if include_system:
        normalized.add("system")

    filtered = []

    for item in TOOLS_SCHEMA:
        fn = item.get("function", {})
        name = fn.get("name", "")
        meta = get_tool_meta(name)
        category = meta.get("category", "general")

        if category in normalized:
            filtered.append(item)

    if not filtered and fallback_all:
        return TOOLS_SCHEMA

    return filtered

def get_tool_brief_by_categories(
    categories: list = None,
    include_file_io: bool = True,
    fallback_all: bool = True
) -> List[dict]:
    """
    给 Planner 看简化工具列表，避免塞完整 schema。
    """
    if categories:
        schemas = get_tools_schema_by_categories(
            categories=categories,
            include_file_io=include_file_io,
            fallback_all=fallback_all
        )
    else:
        schemas = TOOLS_SCHEMA

    brief = []

    for item in schemas:
        fn = item.get("function", {})
        name = fn.get("name", "")
        meta = get_tool_meta(name)
        brief.append({
            "name": name,
            "description": fn.get("description", ""),
            "category": meta.get("category", "general"),
            "tags": meta.get("tags", []),
        })

    return brief