"""
YAML Skill Pack Loader.

Loads SkillSpec definitions from YAML files, converting from
human-friendly YAML format to SkillSpec Pydantic models.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.agent.skills.skill_models import (
    SkillSpec,
    SkillExample,
    SkillClarificationRule,
    SkillParameterRule,
    SkillReportSection,
)
from app.agent.skills.skill_registry import register_skill, SKILL_REGISTRY


def _get_packs_dir() -> Path:
    """Get the packs directory relative to this loader."""
    return Path(__file__).resolve().parent / "packs"


def load_skills_from_yaml(path: str) -> List[SkillSpec]:
    """
    Load skills from a single YAML file.

    Expected YAML structure:
        skills:
          - skill_id: "my_skill"
            name: "My Skill"
            ...

    Returns:
        List of registered SkillSpec instances.
    """
    path = Path(path)
    if not path.exists():
        print(f"[skill_loader] File not found: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        print(f"[skill_loader] Invalid YAML in {path}")
        return []

    skills_data = data.get("skills", [])
    if isinstance(skills_data, dict):
        # Handle single skill
        skills_data = [skills_data]
    if not isinstance(skills_data, list):
        print(f"[skill_loader] No skills list in {path}")
        return []

    loaded = []
    for raw in skills_data:
        if not isinstance(raw, dict):
            continue
        try:
            spec = _yaml_dict_to_skillspec(raw)
            register_skill(spec)
            loaded.append(spec)
        except Exception as e:
            skill_id = raw.get("skill_id", "?")
            print(f"[skill_loader] Failed to parse skill '{skill_id}' in {path}: {e}")

    return loaded


def load_skill_pack_dir(pack_dir: str = None) -> List[SkillSpec]:
    """
    Load all YAML skill packs AND SKILL.md files from a directory.

    Recursively scans for .yaml, .yml, and .md files.

    Args:
        pack_dir: Directory path (defaults to packs/ adjacent to this file)

    Returns:
        All registered SkillSpec instances.
    """
    if pack_dir:
        target = Path(pack_dir)
    else:
        target = _get_packs_dir()

    if not target.exists() or not target.is_dir():
        print(f"[skill_loader] Pack directory not found: {target}")
        return []

    all_loaded = []
    yaml_files = sorted(
        list(target.glob("*.yaml")) + list(target.glob("*.yml")) +
        list(target.glob("**/*.yaml")) + list(target.glob("**/*.yml"))
    )
    # Deduplicate (glob ** already includes root)
    yaml_files = sorted(set(yaml_files))

    for yf in yaml_files:
        loaded = load_skills_from_yaml(str(yf))
        all_loaded.extend(loaded)

    # Phase 2.1: SKILL.md 格式支持
    md_files = sorted(
        list(target.glob("*.md")) + list(target.glob("**/*.md"))
    )
    md_files = sorted(set(md_files))

    for mf in md_files:
        # 跳过非 SKILL.md 的普通 markdown
        if not mf.name.upper().startswith("SKILL"):
            continue
        loaded = load_skills_from_markdown(str(mf))
        all_loaded.extend(loaded)

    return all_loaded


def load_all_skill_packs(pack_dir: str = None) -> List[SkillSpec]:
    """Load all skill packs and return summary."""
    loaded = load_skill_pack_dir(pack_dir)

    implemented = sum(1 for s in loaded if s.implementation_status == "implemented")
    partial = sum(1 for s in loaded if s.implementation_status == "partial")
    planned = sum(1 for s in loaded if s.implementation_status == "planned")

    print(
        f"[skill_loader] Loaded {len(loaded)} skills: "
        f"{implemented} implemented, {partial} partial, {planned} planned"
    )

    return loaded


# ============================================================
# Phase 2.1: SKILL.md 格式加载
# ============================================================

def load_skills_from_markdown(path: str) -> List[SkillSpec]:
    """
    从 SKILL.md 文件加载技能定义。

    格式: YAML frontmatter + Markdown body
    ---
    skill_id: my_skill
    name: My Skill
    ...
    ---
    # Markdown description...
    """
    import re

    path = Path(path)
    if not path.exists():
        print(f"[skill_loader] File not found: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 YAML frontmatter
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        print(f"[skill_loader] No YAML frontmatter in {path}")
        return []

    yaml_text = match.group(1)
    try:
        data = yaml.safe_load(yaml_text)
    except Exception as e:
        print(f"[skill_loader] Failed to parse SKILL.md YAML in {path}: {e}")
        return []

    if not isinstance(data, dict):
        return []

    # 提取 Markdown body 作为 description 补充
    body = content[match.end():].strip()
    if body and not data.get("description"):
        # 用第一段作为 description
        first_para = body.split("\n\n")[0].strip()
        if first_para.startswith("#"):
            first_para = body.split("\n\n")[1].strip() if "\n\n" in body else ""
        data["description"] = first_para[:500] if first_para else ""

    # 如果是单 skill（有 skill_id 字段），包装为列表
    if "skill_id" in data:
        data = {"skills": [data]}
    elif "skills" not in data:
        return []

    loaded = []
    skills_data = data.get("skills", [])
    if isinstance(skills_data, dict):
        skills_data = [skills_data]

    for raw in (skills_data or []):
        if not isinstance(raw, dict):
            continue
        try:
            spec = _yaml_dict_to_skillspec(raw)
            register_skill(spec)
            loaded.append(spec)
        except Exception as e:
            skill_id = raw.get("skill_id", "?")
            print(f"[skill_loader] Failed to parse skill '{skill_id}' in {path}: {e}")

    return loaded


def load_skills_from_directory(skills_dir: str) -> List[SkillSpec]:
    """
    从用户自定义目录加载所有 Skill（.yaml / .yml / SKILL.md）。

    Phase 2.3: Marketplace 准备 — 支持用户投递 skill 文件。

    Args:
        skills_dir: 包含 skill 文件的目录路径

    Returns:
        注册的 SkillSpec 列表
    """
    target = Path(skills_dir)
    if not target.exists() or not target.is_dir():
        return []

    all_loaded = []

    # YAML 文件
    for yf in sorted(target.glob("*.yaml")) + sorted(target.glob("*.yml")):
        loaded = load_skills_from_yaml(str(yf))
        all_loaded.extend(loaded)

    # SKILL.md 文件
    for mf in sorted(target.glob("*.md")):
        if "skill" in mf.name.lower():
            loaded = load_skills_from_markdown(str(mf))
            all_loaded.extend(loaded)

    return all_loaded


# ============================================================
# YAML → SkillSpec conversion
# ============================================================

def _yaml_dict_to_skillspec(d: Dict[str, Any]) -> SkillSpec:
    """Convert a YAML dict into a SkillSpec instance."""

    # Helper to parse sub-models from list of dicts
    def parse_examples(exs) -> List[SkillExample]:
        result = []
        for ex in (exs or []):
            if isinstance(ex, dict):
                result.append(SkillExample(
                    user_input=str(ex.get("user_input", "")),
                    expected_skill_id=str(ex.get("expected_skill_id", "")),
                    description=str(ex.get("description", "")),
                ))
        return result

    def parse_clarification(rules) -> List[SkillClarificationRule]:
        result = []
        for r in (rules or []):
            if isinstance(r, str):
                # Short form: just a condition string
                result.append(SkillClarificationRule(condition=r, question_template=r))
            elif isinstance(r, dict):
                result.append(SkillClarificationRule(
                    condition=str(r.get("condition", "")),
                    question_template=str(r.get("question_template", r.get("question", ""))),
                    priority=str(r.get("priority", "required")),
                ))
        return result

    def parse_params(rules) -> List[SkillParameterRule]:
        result = []
        for r in (rules or []):
            if isinstance(r, dict):
                result.append(SkillParameterRule(
                    param_name=str(r.get("param_name", "")),
                    strategy=str(r.get("strategy", "from_user")),
                    rule_description=str(r.get("rule_description", r.get("description", ""))),
                    default_value=r.get("default_value", r.get("default")),
                    alternatives=[str(a) for a in (r.get("alternatives", []) or [])],
                ))
        return result

    def parse_sections(secs) -> List[SkillReportSection]:
        result = []
        for s in (secs or []):
            if isinstance(s, dict):
                result.append(SkillReportSection(
                    section_id=str(s.get("section_id", "")),
                    title=str(s.get("title", "")),
                    content_hint=str(s.get("content_hint", "")),
                    order=int(s.get("order", 0)),
                ))
        return result

    def str_list(val) -> List[str]:
        if val is None:
            return []
        if isinstance(val, list):
            return [str(v) for v in val]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return []

    # Build SkillSpec
    return SkillSpec(
        skill_id=str(d.get("skill_id", "")),
        name=str(d.get("name", "")),
        category=str(d.get("category", "general")),
        description=str(d.get("description", "")),
        task_types=str_list(d.get("task_types", [])),
        subtask_types=str_list(d.get("subtask_types", [])),
        trigger_keywords=str_list(d.get("trigger_keywords", d.get("triggers", []))),
        trigger_keywords_cn=str_list(d.get("trigger_keywords_cn", [])),
        required_inputs=str_list(d.get("required_inputs", [])),
        optional_inputs=str_list(d.get("optional_inputs", [])),
        default_workflow_id=str(d.get("default_workflow_id", "")),
        allowed_tools=str_list(d.get("allowed_tools", [])),
        banned_tools=str_list(d.get("banned_tools", [])),
        tool_categories=str_list(d.get("tool_categories", [])),
        max_tool_rounds=int(d.get("max_tool_rounds", 8)),
        parameter_rules=parse_params(d.get("parameter_rules", [])),
        clarification_rules=parse_clarification(d.get("clarification_rules", [])),
        qc_rules=str_list(d.get("qc_rules", [])),
        safety_rules=str_list(d.get("safety_rules", [])),
        report_sections=parse_sections(d.get("report_sections", [])),
        output_expectations=str_list(d.get("output_expectations", [])),
        examples=parse_examples(d.get("examples", [])),
        enabled=bool(d.get("enabled", True)),
        version=str(d.get("version", "1.0")),
        implementation_status=str(d.get("implementation_status", "planned")),
        priority=str(d.get("priority", "medium")),
        ui_schema=d.get("ui_schema", {}) or {},
    )
