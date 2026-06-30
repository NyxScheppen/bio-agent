import json
import hashlib
from typing import Any, Dict

from app.core.config import MODEL_NAME
from app.agent.llm_client import client
from app.agent.task_prompts import EXECUTOR_ROLE_PROMPT, build_domain_prompt
from app.agent.tool_registry import TOOL_REGISTRY, get_tool_meta
from typing import Optional as Opt
from app.agent.skills.skill_models import SkillSpec
from app.agent.category_router import resolve_tool_categories, filter_tools_schema_by_plan
from app.agent.tool_result import make_error_result
from app.agent.tool_runner import run_tool_with_lifecycle, execute_recovery_strategies
from app.agent.agent_constants import (
    MAX_TOOL_TIMEOUT_SECONDS,
)
from app.agent.agent_utils import (
    safe_json_loads,
    build_compact_tool_summary,
    extract_output_files,
    build_file_display_hint,
    sanitize_final_answer,
    maybe_add_markdown_guidance,
)


DEFAULT_MAX_TOOL_ROUNDS = 8
BIOINFO_MIN_TOOL_ROUNDS = 10
BIOINFO_COMPLEX_MIN_TOOL_ROUNDS = 14
HARD_MAX_TOOL_ROUNDS = 20

# Phase 4: 护栏常量
MAX_CONSECUTIVE_ERRORS = 3               # 熔断器阈值
MAX_IDEMPOTENT_CALLS = 3                 # 空转检测阈值


FATAL_TOOL_ERROR_KEYWORDS = [
    "unexpected keyword argument",
    "missing required positional argument",
    "got an unexpected",
    "is not json serializable",
    "object of type",
    "takes no keyword arguments",
    "tool does not exist",
    "工具不存在",
]


def make_error_result_from_nonexistent_tool(function_name: str, session_id: str = None) -> Any:
    """
    工具不存在时构造标准 error ToolResult。

    使用 Phase 2 的生命周期格式但跳过实际执行。
    """
    return make_error_result(
        message=f"工具 `{function_name}` 不存在于 TOOL_REGISTRY",
        errors=[f"工具不存在: {function_name}"],
    )


def _apply_skill_tool_filter(
    tools_schema: list,
    skill: Any,  # SkillSpec
) -> list:
    """
    根据 Skill.allowed_tools 白名单过滤工具 schema。

    规则：
    1. 如果 skill 没有 allowed_tools → 不过滤
    2. 如果 skill 有 allowed_tools → 只暴露白名单内的工具
    3. 如果 skill 有 banned_tools → 排除黑名单工具
    4. 对于 planned skill 且 allowed_tools 为空 → 只允许 file_io 类的工具
    5. 过滤后为空 → fallback 到原始 schema
    """
    if not skill or not hasattr(skill, "allowed_tools"):
        return tools_schema

    allowed = set(skill.allowed_tools or [])
    status = getattr(skill, "implementation_status", "planned")

    # planned skill 无显式工具时，只暴露已注册的 file_io 工具
    if status == "planned" and not allowed:
        from app.agent.tool_registry import TOOL_META
        allowed = {
            name for name, meta in TOOL_META.items()
            if meta.get("category") == "file_io"
        }

    # 仍然为空 → 不过滤
    if not allowed:
        return tools_schema

    banned = set(skill.banned_tools or [])
    filtered = []
    for item in tools_schema or []:
        fn = item.get("function", {})
        name = fn.get("name", "")
        if name in allowed and name not in banned:
            filtered.append(item)

    if filtered:
        print(
            f"[Executor] Skill tool filter: {len(tools_schema)} -> "
            f"{len(filtered)} (status={status})"
        )
        return filtered

    print("[Executor] Skill tool filter resulted in empty, falling back")
    return tools_schema


def build_executor_messages(
    context_pack: Dict[str, Any],
    router_result: Dict[str, Any],
    planner_result: Dict[str, Any]
) -> list:
    categories = resolve_tool_categories(
        context_pack=context_pack,
        router_result=router_result,
        planner_result=planner_result
    )

    domain_prompt = build_domain_prompt(categories)

    messages = [
        {"role": "system", "content": domain_prompt},
        {"role": "system", "content": EXECUTOR_ROLE_PROMPT},
        {
            "role": "system",
            "content": (
                "【本轮启用工具组】\n"
                f"{json.dumps(categories, ensure_ascii=False)}\n\n"
                "【Router 判断】\n"
                f"{json.dumps(router_result, ensure_ascii=False, default=str)}\n\n"
                "【Planner 执行计划】\n"
                f"{json.dumps(planner_result, ensure_ascii=False, default=str)}\n\n"
                "请严格按计划执行，只使用当前可见工具。"
            )
        }
    ]

    if context_pack.get("summary"):
        messages.append({
            "role": "system",
            "content": "【压缩后的较早上下文】\n" + context_pack["summary"]
        })

    messages.extend(context_pack.get("recent_messages", []))
    maybe_add_markdown_guidance(messages)

    return messages


def tool_schema_names(tools_schema: list) -> set:
    names = set()
    for item in tools_schema or []:
        fn = item.get("function", {})
        name = fn.get("name", "")
        if name:
            names.add(name)
    return names


def _coerce_to_text(tool_result: Any) -> str:
    """将任意工具返回转为文本用于错误检测。"""
    if tool_result is None:
        return ""
    if isinstance(tool_result, str):
        return tool_result
    if isinstance(tool_result, dict):
        return json.dumps(tool_result, ensure_ascii=False, default=str)
    if hasattr(tool_result, "model_dump"):
        return json.dumps(tool_result.model_dump(), ensure_ascii=False, default=str)
    if hasattr(tool_result, "dict"):
        return json.dumps(tool_result.dict(), ensure_ascii=False, default=str)
    return str(tool_result)


def result_looks_like_r_environment_error(tool_result: Any) -> bool:
    text = _coerce_to_text(tool_result).lower()
    keywords = [
        "rscript",
        "rscript.exe",
        "rscript not found",
        "找不到 r",
        "找不到r",
        "there is no package",
        "package",
        "library(",
        "r execution",
        "r 执行",
        "r环境",
        "r 环境",
    ]
    return any(k in text for k in keywords)


def result_looks_like_file_parse_error(tool_result: Any) -> bool:
    text = _coerce_to_text(tool_result).lower()
    keywords = [
        "文件不存在",
        "no such file",
        "cannot open",
        "无法读取",
        "读取失败",
        "parse",
        "delimiter",
        "encoding",
        "格式",
        "not a valid",
        "缺少列",
        "missing column",
    ]
    return any(k in text for k in keywords)


def guess_file_arg(function_args: dict) -> str:
    """
    从工具参数中猜一个文件路径，用于失败后 probe。
    """
    if not isinstance(function_args, dict):
        return ""

    preferred_keys = [
        "file_path",
        "expression_file",
        "count_file",
        "group_file",
        "input_file",
        "data_file",
    ]

    for k in preferred_keys:
        v = function_args.get(k)
        if isinstance(v, str) and v:
            return v

    for _, v in function_args.items():
        if isinstance(v, str) and any(v.lower().endswith(x) for x in [".csv", ".tsv", ".txt", ".xlsx", ".xls", ".gz", ".zip"]):
            return v

    return ""


def get_effective_max_tool_rounds(
    router_result: Dict[str, Any],
    planner_result: Dict[str, Any]
) -> int:
    try:
        rounds = int(planner_result.get("max_tool_rounds", DEFAULT_MAX_TOOL_ROUNDS))
    except Exception:
        rounds = DEFAULT_MAX_TOOL_ROUNDS

    if rounds <= 0:
        rounds = DEFAULT_MAX_TOOL_ROUNDS

    task_type = str(router_result.get("task_type", "")).lower()
    complexity = str(router_result.get("complexity", "")).lower()
    subtask_type = str(router_result.get("subtask_type", "")).lower()
    objective = str(planner_result.get("objective", "")).lower()

    bio_keywords = [
        "geo",
        "deg",
        "differential",
        "expression",
        "limma",
        "survival",
        "seurat",
        "single cell",
        "single-cell",
        "转录组",
        "表达矩阵",
        "差异表达",
        "富集分析",
        "生存分析",
        "单细胞",
        "空间转录组",
        "机器学习",
        "r分析",
    ]

    is_bio_task = (
        task_type in ["bioinformatics", "file_processing"]
        or subtask_type in ["deg_analysis", "file_probe"]
        or any(k in objective for k in bio_keywords)
    )

    if is_bio_task:
        rounds = max(rounds, BIOINFO_MIN_TOOL_ROUNDS)

    if is_bio_task and complexity in ["complex", "high"]:
        rounds = max(rounds, BIOINFO_COMPLEX_MIN_TOOL_ROUNDS)

    rounds = max(1, min(rounds, HARD_MAX_TOOL_ROUNDS))
    return rounds


def is_error_result(tool_result: Any) -> bool:
    # 处理 Pydantic / ToolResult 对象
    if not isinstance(tool_result, (str, int, float, bool, list, dict, type(None))):
        if hasattr(tool_result, "status"):
            return str(getattr(tool_result, "status", "")).lower() == "error"
        return False
    if isinstance(tool_result, dict):
        return str(tool_result.get("status", "")).lower() == "error"
    return False


def is_fatal_tool_error(tool_result: Any) -> bool:
    # 处理 Pydantic / ToolResult 对象
    if not isinstance(tool_result, (str, int, float, bool, list, dict, type(None))):
        if hasattr(tool_result, "model_dump"):
            d = tool_result.model_dump()
        elif hasattr(tool_result, "dict"):
            d = tool_result.dict()
        else:
            return False
    elif isinstance(tool_result, dict):
        d = tool_result
    else:
        return False

    text = "\n".join([
        str(d.get("message", "")),
        str(d.get("stderr", "")),
        str(d.get("stdout", "")),
        str(d.get("tool", "")),
    ]).lower()

    return any(keyword in text for keyword in FATAL_TOOL_ERROR_KEYWORDS)


def make_fatal_executor_text(function_name: str, tool_result: Any) -> str:
    # 处理 ToolResult 对象
    if not isinstance(tool_result, (str, int, float, bool, list, dict, type(None))):
        if hasattr(tool_result, "model_dump"):
            d = tool_result.model_dump()
        elif hasattr(tool_result, "dict"):
            d = tool_result.dict()
        else:
            d = {}
    elif isinstance(tool_result, dict):
        d = tool_result
    else:
        d = {}

    message = str(d.get("message", "")).strip()
    stderr = str(d.get("stderr", "")).strip()

    parts = [
        f"执行工具 `{function_name}` 时遇到后端级错误，已停止继续重试，避免浪费轮次。"
    ]

    if message:
        parts.append(f"错误信息：{message}")

    if stderr:
        parts.append(f"stderr：{stderr[:800]}")

    parts.append("建议优先检查工具函数签名、参数 schema、路径配置或依赖安装情况。")

    return "\n".join(parts)


def dedupe_output_files(files: list) -> list:
    seen = set()
    result = []

    for f in files or []:
        if not isinstance(f, dict):
            continue

        key = (
            f.get("url", ""),
            f.get("relative_path", ""),
            f.get("name", "")
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(f)

    return result


def run_executor_agent(
    context_pack: Dict[str, Any],
    router_result: Dict[str, Any],
    planner_result: Dict[str, Any],
    session_id: str = None,
    selected_skill: Opt[SkillSpec] = None,
) -> Dict[str, Any]:
    messages = build_executor_messages(context_pack, router_result, planner_result)

    executor_tools_schema = filter_tools_schema_by_plan(
        router_result=router_result,
        planner_result=planner_result,
        context_pack=context_pack,
    )

    # --- Skill 工具白名单限制 ---
    if selected_skill and selected_skill.allowed_tools:
        executor_tools_schema = _apply_skill_tool_filter(
            executor_tools_schema,
            selected_skill,
        )

    print(
        "\n🧰 [Executor Tools] "
        + json.dumps(
            [
                {
                    "name": item.get("function", {}).get("name", ""),
                    "category": get_tool_meta(item.get("function", {}).get("name", "")).get("category", "")
                }
                for item in executor_tools_schema
            ],
            ensure_ascii=False
        )
    )
    if selected_skill:
        print(f"🎯 [Executor] Skill: {selected_skill.skill_id}, allowed_tools={selected_skill.allowed_tools}")

    tool_observations = []
    all_output_files = []
    final_executor_text = ""

    # ---- Phase 1.1: 并行执行检测 ----
    available_tool_names_set = tool_schema_names(executor_tools_schema)

    parallel_groups = planner_result.get("parallel_groups")
    if parallel_groups and len(parallel_groups) > 0:
        print(f"\n⚡ [Executor] Parallel mode: {len(parallel_groups)} groups detected")
        return _run_parallel_execution(
            planner_result=planner_result,
            parallel_groups=parallel_groups,
            available_tool_names=available_tool_names_set,
            executor_tools_schema=executor_tools_schema,
            session_id=session_id,
            context_pack=context_pack,
            router_result=router_result,
            messages=messages,
        )

    max_rounds = get_effective_max_tool_rounds(router_result, planner_result)
    print(f"🧮 [Executor] effective_max_tool_rounds={max_rounds}")

    fatal_stop = False

    # Phase 4.1: 空转检测指纹
    _call_fingerprints: Dict[str, int] = {}
    # Phase 4.3: 熔断器
    consecutive_errors = 0

    for round_idx in range(max_rounds):
        print(f"\n🔁 [Executor] round={round_idx + 1}/{max_rounds}")

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=executor_tools_schema,
            tool_choice="auto",
            temperature=0
        )

        response_message = response.choices[0].message

        assistant_message = {
            "role": "assistant",
            "content": response_message.content or ""
        }

        if response_message.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments or "{}"
                    }
                }
                for tool_call in response_message.tool_calls
            ]

        messages.append(assistant_message)

        if not response_message.tool_calls:
            final_executor_text = response_message.content or ""
            break

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = safe_json_loads(tool_call.function.arguments or "{}")

            # ---- Phase 4.1: 空转检测 ----
            fingerprint = _make_call_fingerprint(function_name, function_args)
            _call_fingerprints[fingerprint] = _call_fingerprints.get(fingerprint, 0) + 1
            if _call_fingerprints[fingerprint] >= MAX_IDEMPOTENT_CALLS:
                print(f"🛑 [Executor] Idempotent no-progress: {function_name} x{_call_fingerprints[fingerprint]}")
                final_executor_text = (
                    f"检测到工具 `{function_name}` 使用相同参数重复调用 "
                    f"{_call_fingerprints[fingerprint]} 次无进展，已终止。"
                )
                fatal_stop = True
                break

            print(f"\n👉 [Executor] 调用工具: {function_name}")
            print(f"👉 [原始参数] {function_args}")

            func = TOOL_REGISTRY.get(function_name)

            if not func:
                # 工具不存在，直接构造 error
                normalized_result = make_error_result_from_nonexistent_tool(
                    function_name, session_id
                )
            else:
                # Phase 2: 使用生命周期包装器执行工具
                normalized_result = run_tool_with_lifecycle(
                    tool_name=function_name,
                    func=func,
                    function_args=function_args,
                    session_id=session_id,
                )

            # --- Feature 3: 统一恢复策略 ---
            available_tool_names = tool_schema_names(executor_tools_schema)

            if is_error_result(normalized_result):
                normalized_result = execute_recovery_strategies(
                    tool_result=normalized_result,
                    tool_name=function_name,
                    function_args=function_args,
                    available_tool_names=available_tool_names,
                    session_id=session_id,
                )

                # 收集恢复工具生成的输出文件
                for record in normalized_result.retry_records:
                    # 恢复工具的 observation 单独记录
                    rec_obs = {
                        "tool": record.recovery_tool,
                        "args": record.recovery_args,
                        "result_summary": record.recovery_result_summary,
                        "output_files": [],
                        "status": "recovery",
                        "job_id": record.recovery_job_id,
                    }
                    tool_observations.append(rec_obs)

            # --- 收集输出文件 ---
            output_files = extract_output_files(normalized_result)
            all_output_files.extend(output_files)

            # --- 构建紧凑描述 ---
            compact_tool_content = build_compact_tool_summary(normalized_result)

            file_display_hint = build_file_display_hint(output_files)
            if file_display_hint:
                tool_content_for_model = compact_tool_content + "\n\n" + file_display_hint
            else:
                tool_content_for_model = compact_tool_content

            print(f"[工具返回] {tool_content_for_model[:800]}...")

            # --- 记录观察 ---
            tool_observations.append({
                "tool": function_name,
                "args": function_args,
                "result_summary": compact_tool_content,
                "output_files": output_files,
                "status": normalized_result.status,
                "warnings": normalized_result.warnings,
                "errors": normalized_result.errors,
                "job_id": normalized_result.provenance.job_id,
                "job_dir": normalized_result.summary.get("job_dir", ""),
                "retry_records": [
                    r.model_dump() if hasattr(r, "model_dump") else r
                    for r in (normalized_result.retry_records or [])
                ],
            })

            # --- 追加到消息历史 ---
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": tool_content_for_model
            })

            # --- 致命错误检查 ---
            if is_error_result(normalized_result) and is_fatal_tool_error(normalized_result):
                print(f"[Executor] fatal tool error detected: {function_name}")
                final_executor_text = make_fatal_executor_text(function_name, normalized_result)
                fatal_stop = True
                break

            # ---- Phase 4.3: 熔断器 ----
            if is_error_result(normalized_result):
                consecutive_errors += 1

                # Phase 4.4: 自动记录失败模式
                _record_failure_for_improvement(
                    function_name,
                    normalized_result,
                    session_id,
                )

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"🛑 [Executor] Circuit breaker: {consecutive_errors} consecutive errors")
                    final_executor_text = (
                        f"连续 {MAX_CONSECUTIVE_ERRORS} 个工具调用失败，已触发熔断保护。"
                        f"最后一个错误来自 `{function_name}`。"
                    )
                    fatal_stop = True
                    break
            else:
                consecutive_errors = max(0, consecutive_errors - 1)

        if fatal_stop:
            break

    if not final_executor_text:
        final_executor_text = (
            f"Executor 已达到最大执行轮次（{max_rounds}），"
            "可能任务较复杂、工具调用未收敛，或中间存在重复试探。"
        )

    return {
        "executor_text": sanitize_final_answer(final_executor_text),
        "tool_observations": tool_observations,
        "output_files": dedupe_output_files(all_output_files)
    }


# ============================================================
# Phase 1.1: 并行执行
# ============================================================

def _run_parallel_execution(
    planner_result: Dict[str, Any],
    parallel_groups: list,
    available_tool_names: set,
    executor_tools_schema: list,
    session_id: str,
    context_pack: Dict[str, Any],
    router_result: Dict[str, Any],
    messages: list,
) -> Dict[str, Any]:
    """
    并行执行模式：用 parallel_executor 按批次并发执行 Planner 步骤。
    """
    from app.agent.parallel_executor import execute_parallel_steps, _topological_batches

    steps = planner_result.get("steps", [])
    step_dependencies = planner_result.get("step_dependencies")

    # 拓扑排序分组
    batches = _topological_batches(steps, step_dependencies)
    print(f"⚡ [Parallel] {len(steps)} steps → {len(batches)} batches")

    # 并行执行
    observations, output_files = execute_parallel_steps(
        batches=batches,
        available_tool_names=available_tool_names,
        session_id=session_id,
    )

    # 检查是否有 racing candidate steps
    for obs in observations:
        if obs.get("status") == "error":
            # 对失败的步骤尝试竞速恢复
            pass  # racing 只在主动选择时触发

    # 生成执行摘要
    success_count = sum(1 for o in observations if o.get("status") == "success")
    error_count = sum(1 for o in observations if o.get("status") == "error")
    executor_text = (
        f"并行执行完成：{len(observations)} 个工具调用，"
        f"{success_count} 成功，{error_count} 失败。"
    )

    return {
        "executor_text": sanitize_final_answer(executor_text),
        "tool_observations": observations,
        "output_files": dedupe_output_files(output_files),
    }


# ============================================================
# Phase 4.1: 空转检测指纹
# ============================================================

def _make_call_fingerprint(tool_name: str, function_args: dict) -> str:
    """为工具调用生成指纹，用于检测重复调用。"""
    args_str = json.dumps(function_args, ensure_ascii=False, sort_keys=True, default=str)
    fingerprint = f"{tool_name}:{args_str}"
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


# ============================================================
# Phase 4.4: 自改进失败记录
# ============================================================

def _record_failure_for_improvement(
    tool_name: str,
    tool_result: Any,
    session_id: str,
) -> None:
    """
    将工具有失败自动记录到 skill_improver，供后续分析。

    静默执行 —— 任何异常都不影响主流程。
    """
    try:
        from app.agent.skill_improver import record_failure

        # 提取简短错误模式
        error_pattern = _extract_error_pattern(tool_name, tool_result)
        job_id = ""
        if hasattr(tool_result, "provenance"):
            job_id = getattr(tool_result.provenance, "job_id", "")

        record_failure(
            tool_name=tool_name,
            error_pattern=error_pattern,
            session_id=session_id or "",
            job_id=job_id,
        )
    except Exception:
        pass


def _extract_error_pattern(tool_name: str, tool_result: Any) -> str:
    """从工具有结果中提取简短错误模式标签。"""
    # 处理 ToolResult 对象
    errors = []
    message = ""

    if hasattr(tool_result, "errors"):
        errors = getattr(tool_result, "errors", []) or []
    if hasattr(tool_result, "message"):
        message = getattr(tool_result, "message", "") or ""

    if isinstance(tool_result, dict):
        errors = tool_result.get("errors", []) or []
        message = tool_result.get("message", "") or ""

    text = " ".join([str(e) for e in errors] + [message]).lower()

    # 按优先级匹配错误模式
    patterns = [
        ("file not found", "file_missing"),
        ("no such file", "file_missing"),
        ("文件不存在", "file_missing"),
        ("timeout", "timeout"),
        ("超时", "timeout"),
        ("timed out", "timeout"),
        ("missing column", "missing_column"),
        ("找不到列", "missing_column"),
        ("unknown column", "missing_column"),
        ("there is no package", "r_package_missing"),
        ("package", "r_package_missing"),
        ("encoding", "encoding_error"),
        ("decode", "encoding_error"),
        ("unicodedecode", "encoding_error"),
        ("rscript not found", "r_missing"),
        ("找不到 r", "r_missing"),
        ("parse", "parse_error"),
        ("解析", "parse_error"),
        ("unexpected keyword", "signature_error"),
        ("missing required", "signature_error"),
    ]

    for keyword, label in patterns:
        if keyword in text:
            return label

    # 兜底
    return "unknown_error"