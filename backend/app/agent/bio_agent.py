import json
from typing import Any, Dict, List, Optional

from app.core.config import MODEL_NAME
from app.agent.llm_client import client
from app.agent.agent_utils import sanitize_final_answer
from app.agent.context_manager import (
    maybe_compact_context,
    enrich_context_with_session_memory,
    resolve_short_user_reply,
    remember_agent_turn,
)
from app.agent.router_agent import run_router_agent
from app.agent.planner_agent import run_planner_agent
from app.agent.executor_agent import run_executor_agent
from app.agent.reporter_agent import run_reporter_agent
from app.agent.category_router import resolve_tool_categories
from app.agent.task_prompts import REPORTER_PROMPT, build_domain_prompt

# Skill system
from app.agent.skills.skill_models import SkillSpec
from app.agent.skills.skill_registry import SKILL_REGISTRY
from app.agent.skills.skill_router import select_skill
from app.agent.skills.builtin_skills import register_all_builtin_skills

# 触发 tools 下所有模块的工具注册
from app import tools  # noqa

# 注册内置 Skills（仅首次）
if not SKILL_REGISTRY:
    register_all_builtin_skills()

def _dedupe_files(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    去重文件列表，避免同一个文件被重复返回给前端。
    """
    result = []
    seen = set()

    for f in files or []:
        if not isinstance(f, dict):
            continue

        key = (
            str(f.get("relative_path", "")),
            str(f.get("url", "")),
            str(f.get("name", "")),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(f)

    return result

def _make_agent_result(answer: str, files: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """
    统一 Agent 返回格式。

    重要：
    以前 run_bio_agent 只返回字符串 final_answer，
    导致 chat_service 只能从文本中解析图片路径。
    如果模型没有把图片路径写进最终回答，前端就拿不到图片。

    现在统一返回：
    {
        "answer": "...",
        "files": [...]
    }
    """
    return {
        "answer": sanitize_final_answer(answer or ""),
        "files": _dedupe_files(files or []),
    }

async def run_bio_agent(history_messages: list, session_id: str = None) -> Dict[str, Any]:
    """
    Multi-Agent 主入口：
    1. 压缩上下文
    2. 注入 session memory
    3. 解析短回复，例如 “1 / 选1 / 第一个”
    4. Router 判断任务
    5. Planner 制定计划
    6. Executor 调用工具
    7. Reporter 生成最终回复
    8. 写回 session memory
    9. 返回 answer + files，确保前端能拿到真实生成文件
    """
    context_pack = maybe_compact_context(
        history_messages,
        session_id=session_id
    )

    context_pack = enrich_context_with_session_memory(
        context_pack=context_pack,
        session_id=session_id
    )

    context_pack = resolve_short_user_reply(
        context_pack=context_pack,
        session_id=session_id
    )

    router_result = run_router_agent(context_pack)
    print(f"\n🧭 [Router] {json.dumps(router_result, ensure_ascii=False, default=str)}")

    # Phase 3+: Skill 选择（在 Router 之后、Planner 之前）
    selected_skill: Optional[SkillSpec] = select_skill(
        latest_user_message=context_pack.get("latest_user_message", ""),
        router_result=router_result,
    )
    if selected_skill:
        print(f"\n🎯 [Skill] {selected_skill.skill_id} — {selected_skill.name}")
    else:
        print("\n🎯 [Skill] No skill matched, using free-planning fallback")

    planner_result = run_planner_agent(context_pack, router_result, selected_skill=selected_skill)
    print(f"\n📝 [Planner] {json.dumps(planner_result, ensure_ascii=False, default=str)}")

    # ---- Phase 3.2: Delegator Agent (复杂任务委派检查) ----
    from app.agent.agent_constants import FEATURE_FLAGS
    if FEATURE_FLAGS.get("sub_agent_delegation", False):
        complexity = router_result.get("complexity", "")
        steps = planner_result.get("steps", [])
        if complexity in ("complex",) and len(steps) >= 3:
            delegator_result = run_delegator_agent(context_pack, planner_result)
            print(f"\n🔀 [Delegator] {json.dumps(delegator_result, ensure_ascii=False, default=str)}")
            if delegator_result.get("should_delegate"):
                planner_result["delegate_to_sub_agents"] = True
                planner_result["sub_tasks"] = delegator_result.get("sub_tasks", [])
            else:
                planner_result["delegate_to_sub_agents"] = False

    execution_mode = (
        planner_result.get("execution_mode")
        or router_result.get("suggested_mode")
        or "tool_execution"
    )

    if execution_mode == "ask_user":
        question = (
            planner_result.get("user_question_if_any")
            or router_result.get("clarification_question")
            or "我需要你补充一下关键信息后才能继续分析。"
        )

        final_answer = sanitize_final_answer(
            f"{question}\n\n请补充信息后再次发送消息，我会继续帮你分析。"
        )

        remember_agent_turn(
            session_id=session_id,
            final_answer=final_answer,
            router_result=router_result,
            planner_result=planner_result,
            executor_result={}
        )

        return _make_agent_result(final_answer, files=[])

    if execution_mode == "answer_only":
        categories = resolve_tool_categories(
            context_pack=context_pack,
            router_result=router_result,
            planner_result=planner_result
        )

        domain_prompt = build_domain_prompt(categories)

        payload = {
            "context_summary": context_pack.get("summary", ""),
            "latest_user_message": context_pack.get("latest_user_message", ""),
            "tool_categories": categories,
            "router_result": router_result,
            "planner_result": planner_result
        }

        messages = [
            {"role": "system", "content": domain_prompt},
            {"role": "system", "content": REPORTER_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, default=str)
            }
        ]

        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.2
            )
            final_answer = sanitize_final_answer(
                resp.choices[0].message.content or ""
            )
        except Exception as e:
            final_answer = f"生成回答失败：{str(e)}"

        remember_agent_turn(
            session_id=session_id,
            final_answer=final_answer,
            router_result=router_result,
            planner_result=planner_result,
            executor_result={}
        )

        return _make_agent_result(final_answer, files=[])

    executor_result = run_executor_agent(
        context_pack=context_pack,
        router_result=router_result,
        planner_result=planner_result,
        session_id=session_id,
        selected_skill=selected_skill,
    )

    print(
        f"\n⚙️ [Executor Summary] "
        f"{json.dumps(executor_result, ensure_ascii=False, default=str)[:1500]}"
    )

    final_answer = run_reporter_agent(
        context_pack=context_pack,
        router_result=router_result,
        planner_result=planner_result,
        executor_result=executor_result,
        selected_skill=selected_skill,
    )

    final_answer = sanitize_final_answer(final_answer)

    output_files = executor_result.get("output_files", []) or []
    output_files = _dedupe_files(output_files)

    print(
        "\n📦 [BioAgent Output Files] "
        + json.dumps(output_files, ensure_ascii=False, default=str)[:2000]
    )

    remember_agent_turn(
        session_id=session_id,
        final_answer=final_answer,
        router_result=router_result,
        planner_result=planner_result,
        executor_result=executor_result
    )

    return _make_agent_result(final_answer, files=output_files)