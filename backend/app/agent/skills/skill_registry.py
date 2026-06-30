"""
Skill Registry — manage all registered skills.

Provides:
- register_skill(spec) — register a SkillSpec
- get_skill(skill_id) — get by ID
- list_skills() — list all enabled skills
- find_skills_by_category(category) — filter by category
- find_skills_by_task_type(task_type) — filter by task_type or subtask_type
"""

from typing import Dict, List, Optional

from app.agent.skills.skill_models import SkillSpec

# 全局 skill 注册表
SKILL_REGISTRY: Dict[str, SkillSpec] = {}


def register_skill(spec: SkillSpec) -> SkillSpec:
    """
    注册一个 Skill。

    Args:
        spec: SkillSpec 实例

    Returns:
        注册后的 SkillSpec（可用于链式调用）

    Raises:
        ValueError: 如果 skill_id 重复
    """
    if not spec.skill_id:
        raise ValueError("SkillSpec.skill_id is required")

    if spec.skill_id in SKILL_REGISTRY:
        # 允许覆盖但打印警告
        print(f"[skill_registry] Overwriting existing skill: {spec.skill_id}")

    SKILL_REGISTRY[spec.skill_id] = spec
    return spec


def get_skill(skill_id: str) -> Optional[SkillSpec]:
    """根据 skill_id 获取 Skill。"""
    return SKILL_REGISTRY.get(skill_id)


def list_skills(enabled_only: bool = True) -> List[SkillSpec]:
    """列出所有 Skill。"""
    skills = list(SKILL_REGISTRY.values())
    if enabled_only:
        skills = [s for s in skills if s.enabled]
    return sorted(skills, key=lambda s: s.name)


def find_skills_by_category(category: str) -> List[SkillSpec]:
    """按类别查找 Skill。"""
    category = category.lower().strip()
    return [
        s for s in SKILL_REGISTRY.values()
        if s.enabled and s.category.lower() == category
    ]


def find_skills_by_task_type(task_type: str, subtask_type: str = "") -> List[SkillSpec]:
    """
    按 task_type 和 subtask_type 查找 Skill。

    匹配优先级（只返回最高优先级匹配）：
    1. task_type + subtask_type 精确匹配（同时匹配最多）
    2. task_type 匹配
    3. subtask_type 匹配
    """
    task_type = task_type.lower().strip()
    subtask_type = subtask_type.lower().strip()

    exact: List[SkillSpec] = []
    task_only: List[SkillSpec] = []
    subtask_only: List[SkillSpec] = []

    for s in SKILL_REGISTRY.values():
        if not s.enabled:
            continue

        s_tasks = [t.lower() for t in s.task_types]
        s_subtasks = [t.lower() for t in s.subtask_types]

        task_match = task_type in s_tasks if task_type else False
        subtask_match = subtask_type in s_subtasks if subtask_type else False

        if task_match and subtask_match:
            exact.append(s)
        elif task_match:
            task_only.append(s)
        elif subtask_match:
            subtask_only.append(s)

    if exact:
        return exact
    if task_only:
        return task_only
    return subtask_only


def list_skill_ids() -> List[str]:
    """列出所有已注册 skill 的 ID。"""
    return sorted(SKILL_REGISTRY.keys())
