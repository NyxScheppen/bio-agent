"""
Skill System - Higher-level task capability packages.

A Skill encapsulates:
- Trigger conditions (task_type, keywords)
- Required inputs
- Default workflow
- Allowed tools
- Parameter rules
- QC rules
- Report template

Skills are loaded from YAML packs in the packs/ directory via skill_loader.
"""

from app.agent.skills.skill_models import (
    SkillSpec,
    SkillExample,
    SkillClarificationRule,
    SkillParameterRule,
    SkillReportSection,
)
from app.agent.skills.skill_registry import (
    SKILL_REGISTRY,
    register_skill,
    get_skill,
    list_skills,
    find_skills_by_category,
    find_skills_by_task_type,
)
from app.agent.skills.skill_router import select_skill


def ensure_skills_loaded(pack_dir: str = None) -> list:
    """
    确保内置 Skills 已从 YAML packs 加载。

    幂等：如果 SKILL_REGISTRY 已有 skill，只补充尚未加载的。
    首次调用时从 packs/ 目录加载所有 YAML。

    Returns:
        当前所有 skill_id 列表
    """
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    if SKILL_REGISTRY:
        # 已加载，返回现有
        return sorted(SKILL_REGISTRY.keys())

    # 从 YAML packs 加载
    from app.agent.skills.skill_loader import load_all_skill_packs
    load_all_skill_packs(pack_dir)

    return sorted(SKILL_REGISTRY.keys())
