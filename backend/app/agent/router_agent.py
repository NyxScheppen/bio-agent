import json
from typing import Any, Dict

from app.core.config import MODEL_NAME
from app.agent.llm_client import client
from app.agent.agent_utils import extract_json_object
from app.agent.task_prompts import ROUTER_PROMPT


def call_json_agent(system_prompt: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}
    ]

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0
        )
        content = resp.choices[0].message.content or ""
        return extract_json_object(content)
    except Exception as e:
        return {"error": str(e)}


def run_router_agent(context_pack: Dict[str, Any]) -> Dict[str, Any]:
    # Phase 5.3: 斜杠命令预处理
    latest = context_pack.get("latest_user_message", "")
    command_result = _try_resolve_command(latest)
    if command_result:
        print(f"\n⚡ [Router] Command resolved: {command_result.get('command', '')}")
        return command_result

    payload = {
        "context_summary": context_pack.get("summary", ""),
        "recent_messages": context_pack.get("recent_messages", []),
        "latest_user_message": context_pack.get("latest_user_message", "")
    }

    result = call_json_agent(ROUTER_PROMPT, payload)

    if not result:
        result = {
            "task_type": "unclear",
            "subtask_type": "unknown",
            "complexity": "medium",
            "need_clarification": True,
            "clarification_question": "我需要你再明确一下具体要做什么分析，以及是否已经上传了对应数据文件。",
            "reason": "Router 未能解析任务",
            "risk_flags": ["router_parse_failed"],
            "suggested_mode": "ask_user"
        }

    return result


def _try_resolve_command(latest_user_message: str) -> Dict[str, Any] | None:
    """
    Phase 5.3: 尝试将用户消息解析为斜杠命令。

    成功返回 Router-like dict（跳过 LLM 调用），失败返回 None。
    """
    try:
        from app.agent.commands import resolve_command
        cmd = resolve_command(latest_user_message)
        if not cmd:
            return None

        # /help 特殊处理
        if cmd.get("task_type") == "general" and cmd.get("help_text"):
            return {
                "task_type": "general",
                "subtask_type": "help",
                "complexity": "simple",
                "need_clarification": False,
                "clarification_question": "",
                "reason": f"命令: /help",
                "risk_flags": [],
                "suggested_mode": "answer_only",
                "tool_categories": ["general"],
                "help_text": cmd.get("help_text", ""),
            }

        skill = cmd.get("skill", "")
        task_type = cmd.get("task_type", "bioinformatics")
        tool_categories = cmd.get("tool_categories", [])

        if skill:
            # 有 Skill 映射 → 强制 tool_execution
            return {
                "task_type": task_type,
                "subtask_type": skill,
                "complexity": "medium",
                "need_clarification": False,
                "clarification_question": "",
                "reason": f"命令: {cmd.get('command', '')}",
                "risk_flags": [],
                "suggested_mode": "tool_execution",
                "tool_categories": tool_categories if tool_categories else ["general"],
                "command_skill": skill,
            }

        # 无 Skill 但有 task_type
        return {
            "task_type": task_type,
            "subtask_type": "command",
            "complexity": "simple",
            "need_clarification": False,
            "clarification_question": "",
            "reason": f"命令: {cmd.get('command', '')}",
            "risk_flags": [],
            "suggested_mode": "tool_execution" if tool_categories else "answer_only",
            "tool_categories": tool_categories or ["general"],
        }

    except Exception:
        return None