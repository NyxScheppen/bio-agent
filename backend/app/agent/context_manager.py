import json
import re
from typing import Any, Dict, List

from app.core.config import MODEL_NAME
from app.agent.llm_client import client
from app.agent.agent_utils import sanitize_final_answer

SESSION_MEMORY: Dict[str, Dict[str, Any]] = {}

CONTEXT_SUMMARIZER_PROMPT = """
你是会话上下文压缩器。请把较早历史压缩成简洁摘要。

只保留：
1. 用户的项目目标
2. 已上传/提到的文件名
3. 已确认的列名、分组名、基因名、参数
4. 已经完成的分析和生成文件
5. 用户偏好和模式
6. 仍未解决的问题

不要编造没有出现过的信息。
输出中文摘要，不要超过 1200 字。
"""

def _normalize_session_key(session_id: str = None) -> str:
    """
    标准化 session_id。

    重要修复：
    以前没有 session_id 时会返回 "__default__"，
    这会导致所有没传 session_id 的请求共享同一个后端记忆桶，
    从而出现“删除会话后 AI 仍然记得旧内容”的串会话问题。

    现在策略：
    - 没有合法 session_id：返回空字符串
    - 返回空字符串表示禁用长期 session memory
    """
    if not session_id:
        return ""

    key = str(session_id).strip()
    if not key:
        return ""

    if "/" in key or "\\" in key or ".." in key:
        return ""

    return key

def _empty_session_state() -> Dict[str, Any]:
    """
    返回临时空状态。
    注意：这个状态不会写入 SESSION_MEMORY。
    """
    return {
        "summary": "",
        "turn_count": 0,
    }

def has_valid_session_id(session_id: str = None) -> bool:
    return bool(_normalize_session_key(session_id))

def filter_chat_history(history_messages: list) -> list:
    filtered = []

    for msg in history_messages or []:
        role = msg.get("role")
        content = msg.get("content", "")

        if role not in ("user", "assistant", "system"):
            continue
        if not content:
            continue

        filtered.append({
            "role": role,
            "content": str(content),
        })

    return filtered

def get_latest_user_message(history_messages: list) -> str:
    for msg in reversed(history_messages or []):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""

def get_session_state(session_id: str = None) -> Dict[str, Any]:
    """
    获取当前 session 的内存状态。

    如果没有合法 session_id，不创建、不读取共享默认记忆。
    """
    key = _normalize_session_key(session_id)

    if not key:
        return _empty_session_state()

    if key not in SESSION_MEMORY:
        SESSION_MEMORY[key] = {
            "summary": "",
            "turn_count": 0,
        }

    return SESSION_MEMORY[key]

def maybe_compact_context(history_messages: list, session_id: str = None) -> Dict[str, Any]:
    """
    压缩上下文。

    注意：
    - 有合法 session_id：摘要会写入对应 SESSION_MEMORY[session_id]
    - 没有合法 session_id：只返回最近上下文，不写入长期记忆
    """
    key = _normalize_session_key(session_id)
    state = get_session_state(session_id)
    filtered = filter_chat_history(history_messages)

    latest_user_message = get_latest_user_message(filtered)
    recent_messages = filtered[-8:]
    older_messages = filtered[:-8]

    if key and older_messages:
        old_text = json.dumps(older_messages, ensure_ascii=False)
        previous_summary = state.get("summary", "")

        messages = [
            {"role": "system", "content": CONTEXT_SUMMARIZER_PROMPT},
            {
                "role": "user",
                "content": (
                    "已有摘要：\n"
                    f"{previous_summary}\n\n"
                    "需要继续压缩的较早历史：\n"
                    f"{old_text}"
                ),
            },
        ]

        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0,
            )
            new_summary = resp.choices[0].message.content or ""
            state["summary"] = sanitize_final_answer(new_summary)
        except Exception as e:
            print(f"⚠️ 上下文压缩失败: {e}")

    if key:
        state["turn_count"] = int(state.get("turn_count", 0)) + 1

    return {
        "summary": state.get("summary", "") if key else "",
        "recent_messages": recent_messages,
        "latest_user_message": latest_user_message,
    }

def extract_numbered_choices(text: str) -> Dict[str, str]:
    """
    从 assistant 最终回复中提取编号选项。

    支持：
    1. 做 A
    1、做 A
    1) 做 A
    （1）做 A
    - 1. 做 A
    """
    if not text:
        return {}

    choices = {}
    patterns = [
        r"^\s*(?:[-*]\s*)?(\d+)[\.\、\)]\s+(.+?)\s*$",
        r"^\s*（(\d+)）\s*(.+?)\s*$",
        r"^\s*\((\d+)\)\s*(.+?)\s*$",
    ]

    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue

        for pat in patterns:
            m = re.match(pat, line)
            if m:
                idx = m.group(1).strip()
                content = m.group(2).strip()
                if 1 <= len(content) <= 300:
                    choices[idx] = content
                break

    return choices

def normalize_short_choice(text: str) -> str:
    if not text:
        return ""

    s = str(text).strip()

    if re.fullmatch(r"\d{1,2}", s):
        return s

    m = re.fullmatch(r"(选|选择|做|执行|继续|我要|就选)?\s*第?\s*(\d{1,2})\s*(个|项|条)?", s)
    if m:
        return m.group(2)

    chinese_num_map = {
        "一": "1",
        "二": "2",
        "两": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
        "十": "10",
    }

    m = re.fullmatch(r"(选|选择|做|执行|继续|我要|就选)?\s*第?\s*([一二两三四五六七八九十])\s*(个|项|条)?", s)
    if m:
        return chinese_num_map.get(m.group(2), "")

    return ""

def compact_output_files(output_files: List[Dict[str, Any]], max_files: int = 20) -> List[Dict[str, Any]]:
    compact = []

    for f in output_files or []:
        if not isinstance(f, dict):
            continue

        compact.append({
            "name": f.get("name", ""),
            "url": f.get("url", ""),
            "relative_path": f.get("relative_path", ""),
            "size_bytes": f.get("size_bytes", ""),
        })

        if len(compact) >= max_files:
            break

    return compact

def remember_agent_turn(
    session_id: str = None,
    final_answer: str = "",
    router_result: Dict[str, Any] = None,
    planner_result: Dict[str, Any] = None,
    executor_result: Dict[str, Any] = None,
):
    """
    把本轮 Agent 的最终输出和关键结构化结果写入 session memory。

    重要修复：
    没有合法 session_id 时直接跳过，不再写入 "__default__"。
    """
    key = _normalize_session_key(session_id)
    if not key:
        print("⚠️ remember_agent_turn skipped: empty or invalid session_id")
        return

    state = get_session_state(session_id)

    router_result = router_result or {}
    planner_result = planner_result or {}
    executor_result = executor_result or {}

    output_files = compact_output_files(executor_result.get("output_files", []))
    pending_choices = extract_numbered_choices(final_answer)

    state["last_assistant_answer"] = final_answer or ""
    state["pending_choices"] = pending_choices
    state["last_router_result"] = router_result
    state["last_planner_result"] = planner_result
    state["last_output_files"] = output_files

    tool_summaries = []
    for obs in executor_result.get("tool_observations", []) or []:
        if not isinstance(obs, dict):
            continue

        tool_summaries.append({
            "tool": obs.get("tool", ""),
            "args": obs.get("args", {}),
            "result_summary": str(obs.get("result_summary", ""))[:1200],
            "output_files": compact_output_files(obs.get("output_files", []), max_files=10),
        })

        if len(tool_summaries) >= 10:
            break

    state["last_tool_observations"] = tool_summaries

    old_summary = state.get("summary", "") or ""
    memory_line = ""

    if final_answer:
        memory_line += f"\n上一轮助手最终回复摘要：{final_answer[:800]}"

    if pending_choices:
        memory_line += "\n上一轮编号选项："
        for k, v in pending_choices.items():
            memory_line += f"\n{k}. {v}"

    if output_files:
        memory_line += "\n上一轮生成文件："
        for f in output_files:
            memory_line += f"\n- {f.get('name')}：{f.get('url') or f.get('relative_path')}"

    merged = (old_summary + "\n" + memory_line).strip()

    if len(merged) > 3000:
        merged = merged[-3000:]

    state["summary"] = merged

def build_session_memory_system_message(session_id: str = None) -> str:
    """
    构造后端 Session Memory system message。

    重要修复：
    - 没有合法 session_id：不注入
    - 当前 session 没有真实记忆：不注入
    """
    key = _normalize_session_key(session_id)
    if not key:
        return ""

    state = get_session_state(session_id)

    has_memory = any([
        state.get("summary"),
        state.get("last_assistant_answer"),
        state.get("pending_choices"),
        state.get("last_output_files"),
        state.get("last_planner_result"),
    ])

    if not has_memory:
        return ""

    lines = []
    lines.append("【后端 Session Memory】")
    lines.append("这些信息来自后端保存的上一轮 Agent 状态，用于理解用户的省略表达。不要把它当作新用户请求。")

    summary = state.get("summary", "")
    if summary:
        lines.append("")
        lines.append("当前会话压缩摘要：")
        lines.append(str(summary)[:1200])

    last_answer = state.get("last_assistant_answer", "")
    if last_answer:
        lines.append("")
        lines.append("上一轮助手最终回复：")
        lines.append(str(last_answer)[:1500])

    pending_choices = state.get("pending_choices", {})
    if pending_choices:
        lines.append("")
        lines.append("上一轮可选编号：")
        for k, v in pending_choices.items():
            lines.append(f"{k}. {v}")

    last_output_files = state.get("last_output_files", [])
    if last_output_files:
        lines.append("")
        lines.append("上一轮生成文件：")
        for f in last_output_files:
            name = f.get("name", "")
            url = f.get("url", "") or f.get("relative_path", "")
            lines.append(f"- {name}: {url}")

    last_plan = state.get("last_planner_result", {})
    if last_plan:
        objective = str(last_plan.get("objective", "")).strip()
        if objective:
            lines.append("")
            lines.append("上一轮 Planner 目标：")
            lines.append(objective[:500])

    return "\n".join(lines)

def enrich_context_with_session_memory(
    context_pack: Dict[str, Any],
    session_id: str = None,
) -> Dict[str, Any]:
    """
    给 context_pack 注入当前 session 的后端记忆。

    重要修复：
    如果没有 session_id 或当前 session 没有记忆，不注入任何 memory system message。
    """
    memory_msg = build_session_memory_system_message(session_id)
    if not memory_msg:
        return context_pack

    recent_messages = context_pack.get("recent_messages", []) or []

    enriched_recent = [
        {
            "role": "system",
            "content": memory_msg,
        }
    ] + recent_messages

    new_pack = dict(context_pack)
    new_pack["recent_messages"] = enriched_recent
    new_pack["session_memory"] = memory_msg

    return new_pack

def resolve_short_user_reply(
    context_pack: Dict[str, Any],
    session_id: str = None,
) -> Dict[str, Any]:
    """
    解析用户短回复，比如：
    - 1
    - 选 2
    - 第三个

    重要修复：
    没有合法 session_id 时不解析上一轮编号，避免跨会话选择串扰。
    """
    key = _normalize_session_key(session_id)
    if not key:
        return context_pack

    latest = context_pack.get("latest_user_message", "") or ""
    choice_id = normalize_short_choice(latest)

    if not choice_id:
        return context_pack

    state = get_session_state(session_id)
    pending_choices = state.get("pending_choices", {}) or {}

    if choice_id not in pending_choices:
        return context_pack

    choice_text = pending_choices[choice_id]

    resolved_message = (
        f"用户回复了编号选择：{choice_id}。\n"
        f"根据上一轮助手给出的选项，编号 {choice_id} 对应：{choice_text}\n"
        f"请将本轮用户意图理解为：继续执行/展开这个选项。\n"
        f"用户原始输入：{latest}"
    )

    recent_messages = context_pack.get("recent_messages", []) or []

    new_recent = []
    replaced = False

    for msg in recent_messages:
        if msg.get("role") == "user" and msg.get("content") == latest:
            new_recent.append({
                "role": "user",
                "content": resolved_message,
            })
            replaced = True
        else:
            new_recent.append(msg)

    if not replaced:
        new_recent.append({
            "role": "user",
            "content": resolved_message,
        })

    new_pack = dict(context_pack)
    new_pack["latest_user_message"] = resolved_message
    new_pack["recent_messages"] = new_recent
    new_pack["resolved_short_reply"] = {
        "choice_id": choice_id,
        "choice_text": choice_text,
        "raw_user_message": latest,
    }

    return new_pack

def clear_session_memory(session_id: str = None):
    """
    清理指定 session 的后端内存。

    额外兼容：
    删除 "__default__"，用于清理旧版本遗留污染。
    """
    key = _normalize_session_key(session_id)

    if key:
        SESSION_MEMORY.pop(key, None)

    # 清理旧版本可能产生的共享默认记忆桶
    SESSION_MEMORY.pop("__default__", None)

    print(f"🧹 clear_session_memory: session_id={session_id}, key={key}, remaining_keys={list(SESSION_MEMORY.keys())}")

def clear_all_session_memory():
    """
    清空所有后端 session memory。
    """
    SESSION_MEMORY.clear()
    print("🧹 clear_all_session_memory: all session memory cleared")

def debug_session_memory_keys() -> list:
    """
    调试用：查看当前所有内存 key。
    """
    return list(SESSION_MEMORY.keys())

def debug_get_session_memory(session_id: str = None) -> Dict[str, Any]:
    """
    调试用：查看指定 session memory。
    """
    key = _normalize_session_key(session_id)
    if not key:
        return {}

    return SESSION_MEMORY.get(key, {})