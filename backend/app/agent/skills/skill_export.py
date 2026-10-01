"""
技能导出工具 (Phase 2.3: Marketplace 准备).

将已注册 Skill 导出为独立的 SKILL.md 文件，
格式兼容 anbeime/skill 社区标准。

用法:
    from app.agent.skills.skill_export import export_all_skills
    export_all_skills("D:/my_skills/")
"""

import json
import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.skills.skill_registry import list_skills
from app.agent.skills.skill_models import SkillSpec


def _skill_to_frontmatter(skill: SkillSpec) -> Dict[str, Any]:
    """将 SkillSpec 转为 YAML frontmatter 字典。"""
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "category": skill.category,
        "description": skill.description,
        "version": skill.version,
        "priority": skill.priority,
        "implementation_status": skill.implementation_status,
        "task_types": skill.task_types,
        "subtask_types": skill.subtask_types,
        "trigger_keywords": skill.trigger_keywords,
        "trigger_keywords_cn": skill.trigger_keywords_cn,
        "required_inputs": skill.required_inputs,
        "optional_inputs": skill.optional_inputs,
        "allowed_tools": skill.allowed_tools,
        "banned_tools": skill.banned_tools,
        "tool_categories": skill.tool_categories,
        "max_tool_rounds": skill.max_tool_rounds,
        "default_workflow_id": skill.default_workflow_id or None,
        "qc_rules": skill.qc_rules,
        "safety_rules": skill.safety_rules,
        "output_expectations": skill.output_expectations,
        "clarification_rules": [
            {
                "condition": r.condition,
                "question_template": r.question_template,
                "priority": r.priority,
            }
            for r in (skill.clarification_rules or [])
        ],
        "parameter_rules": [
            {
                "param_name": r.param_name,
                "strategy": r.strategy,
                "rule_description": r.rule_description,
                "default_value": r.default_value,
                "alternatives": r.alternatives,
            }
            for r in (skill.parameter_rules or [])
        ],
        "report_sections": [
            {
                "section_id": s.section_id,
                "title": s.title,
                "content_hint": s.content_hint,
                "order": s.order,
            }
            for s in sorted(skill.report_sections, key=lambda x: x.order)
            if skill.report_sections
        ],
        "examples": [
            {
                "user_input": e.user_input,
                "expected_skill_id": e.expected_skill_id,
            }
            for e in (skill.examples or [])
        ],
    }


def _build_markdown_body(skill: SkillSpec) -> str:
    """构建 SKILL.md 的 Markdown body。"""
    lines = [
        f"# {skill.name}",
        "",
        skill.description,
        "",
        "## 工作流",
        f"- 默认工作流: `{skill.default_workflow_id or 'auto'}`",
        f"- 最大工具有轮次: {skill.max_tool_rounds}",
        f"- 工具有类别: {', '.join(skill.tool_categories or [])}",
        "",
        "## 可用工具",
    ]

    for t in (skill.allowed_tools or []):
        lines.append(f"- `{t}`")

    if skill.required_inputs:
        lines.append("")
        lines.append("## 必需输入")
        for inp in skill.required_inputs:
            lines.append(f"- {inp}")

    if skill.clarification_rules:
        lines.append("")
        lines.append("## 追问规则")
        for r in skill.clarification_rules:
            lines.append(f"- **{r.condition}**: {r.question_template}")

    if skill.report_sections:
        lines.append("")
        lines.append("## 报告结构")
        for s in sorted(skill.report_sections, key=lambda x: x.order):
            lines.append(f"### {s.title}")
            lines.append(f"{s.content_hint}")

    if skill.safety_rules:
        lines.append("")
        lines.append("## 安全规则")
        for r in skill.safety_rules:
            lines.append(f"- ⚠️ {r}")

    if skill.examples:
        lines.append("")
        lines.append("## 示例")
        for e in skill.examples:
            lines.append(f"- 用户: _{e.user_input}_")

    return "\n".join(lines)


def export_skill_to_markdown(skill: SkillSpec, output_path: str) -> str:
    """
    将单个 Skill 导出为 SKILL.md 文件。

    Args:
        skill: SkillSpec 实例
        output_path: 输出文件路径（.md）

    Returns:
        写入的文件路径
    """
    frontmatter = _skill_to_frontmatter(skill)
    # 移除 None 值
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None and v != [] and v != ""}

    yaml_header = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    body = _build_markdown_body(skill)

    content = f"---\n{yaml_header}---\n\n{body}\n"

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return str(path)


def export_all_skills(output_dir: str, enabled_only: bool = True) -> List[str]:
    """
    将所有已注册 Skill 导出为独立 SKILL.md 文件。

    Args:
        output_dir: 输出目录
        enabled_only: 只导出启用的 Skill

    Returns:
        导出的文件路径列表
    """
    skills = list_skills(enabled_only=enabled_only)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    exported = []
    for skill in skills:
        filename = f"{skill.skill_id}.md"
        filepath = export_skill_to_markdown(skill, str(output / filename))
        exported.append(filepath)

    # 生成 manifest
    manifest = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "skill_count": len(exported),
        "skills": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "category": s.category,
                "file": f"{s.skill_id}.md",
                "version": s.version,
            }
            for s in skills
        ],
    }
    manifest_path = output / "skills_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[skill_export] Exported {len(exported)} skills to {output_dir}")
    return exported
