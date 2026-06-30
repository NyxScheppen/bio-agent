import json
from typing import Any, Dict, Optional

from app.core.config import MODEL_NAME
from app.agent.llm_client import client
from app.agent.task_prompts import REPORTER_PROMPT, build_domain_prompt
from app.agent.category_router import resolve_tool_categories
from app.agent.skills.skill_models import SkillSpec
from app.agent.agent_utils import (
    build_file_display_hint,
    maybe_add_markdown_guidance,
    sanitize_final_answer,
    remove_fake_markdown_images,
)


def run_reporter_agent(
    context_pack: Dict[str, Any],
    router_result: Dict[str, Any],
    planner_result: Dict[str, Any],
    executor_result: Dict[str, Any],
    selected_skill: Optional[SkillSpec] = None,
) -> str:
    output_files = executor_result.get("output_files", [])
    file_display_hint = build_file_display_hint(output_files)

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
        "planner_result": planner_result,
        "executor_text": executor_result.get("executor_text", ""),
        "tool_observations": executor_result.get("tool_observations", []),
        "real_file_display_hint": file_display_hint
    }

    # --- Skill 报告模板注入 ---
    if selected_skill and selected_skill.report_sections:
        payload["report_template"] = _build_report_template(selected_skill)

    messages = [
        {"role": "system", "content": domain_prompt},
        {"role": "system", "content": REPORTER_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}
    ]

    maybe_add_markdown_guidance(messages)

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.2
        )
        final_text = sanitize_final_answer(resp.choices[0].message.content or "")
        final_text = remove_fake_markdown_images(
            final_text,
            executor_result.get("output_files", [])
        )
        return final_text
    except Exception as e:
        fallback = executor_result.get("executor_text", "")
        if fallback:
            return sanitize_final_answer(fallback)
        return f"分析流程已执行，但生成最终报告时失败：{str(e)}"


def _build_report_template(skill: SkillSpec) -> str:
    """
    从 Skill.report_sections 构建报告模板提示。
    """
    sections = sorted(skill.report_sections, key=lambda s: s.order)

    lines = [
        "\n【Skill 报告模板】",
        f"当前任务属于 {skill.name}。请按以下结构组织最终报告：",
        ""
    ]

    for sec in sections:
        lines.append(f"## {sec.title}")
        lines.append(f"  (内容提示: {sec.content_hint})")
        lines.append("")

    lines.append("请确保每个章节都有实际内容，不编造不存在的图表或结果。")
    lines.append("如果某章节在当前分析中没有对应结果，可跳过或说明原因。")

    return "\n".join(lines)