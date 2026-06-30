"""
Skill Router — score and select the best matching Skill.

Scoring dimensions (each 0–1, weighted):
1. task_type match  — weight 0.35
2. subtask_type match — weight 0.25
3. keyword match — weight 0.25
4. input availability — weight 0.15

Returns the highest-scoring Skill if score >= threshold, else None (fallback).
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.agent.skills.skill_models import SkillSpec
from app.agent.skills.skill_registry import SKILL_REGISTRY

# 最低分数阈值，低于此值视为不匹配
MIN_SKILL_SCORE = 0.15


def select_skill(
    latest_user_message: str = "",
    router_result: Optional[Dict[str, Any]] = None,
    available_files: Optional[List[str]] = None,
    min_score: float = MIN_SKILL_SCORE,
) -> Optional[SkillSpec]:
    """
    根据用户消息和 Router 结果选择最佳 Skill。

    Args:
        latest_user_message: 用户最新消息
        router_result: Router Agent 的输出
        available_files: 可用文件名列表
        min_score: 最低匹配分数阈值

    Returns:
        最佳匹配的 SkillSpec，若无匹配返回 None
    """
    router_result = router_result or {}
    available_files = available_files or []

    task_type = str(router_result.get("task_type", "") or "").lower()
    subtask_type = str(router_result.get("subtask_type", "") or "").lower()

    candidates: List[SkillSpec] = [
        s for s in SKILL_REGISTRY.values() if s.enabled
    ]

    if not candidates:
        return None

    scored: List[Tuple[SkillSpec, float]] = []

    for skill in candidates:
        score = _score_skill(
            skill=skill,
            user_message=latest_user_message,
            task_type=task_type,
            subtask_type=subtask_type,
            available_files=available_files,
        )
        if score >= min_score:
            scored.append((skill, score))

    if not scored:
        return None

    # 按分数降序排列
    scored.sort(key=lambda x: x[1], reverse=True)

    best_skill, best_score = scored[0]

    print(
        f"[skill_router] Selected: {best_skill.skill_id} "
        f"(score={best_score:.3f})"
    )

    if len(scored) > 1:
        runner_up = scored[1]
        print(
            f"[skill_router] Runner-up: {runner_up[0].skill_id} "
            f"(score={runner_up[1]:.3f})"
        )

    return best_skill


def _score_skill(
    skill: SkillSpec,
    user_message: str,
    task_type: str,
    subtask_type: str,
    available_files: List[str],
) -> float:
    """
    对单个 Skill 打分。

    基础分 = weighted(task_type, keyword, input)
    实现状态加成：
    - implemented: +0.15
    - partial: +0.10
    - planned: +0.0

    Returns:
        0.0 ~ 1.0+ 的分数
    """
    scores = {
        "task_type": _score_task_type(skill, task_type, subtask_type),
        "keyword": _score_keywords(skill, user_message),
        "input": _score_inputs(skill, available_files),
    }

    weights = {
        "task_type": 0.45,
        "keyword": 0.35,
        "input": 0.20,
    }

    total = sum(scores[k] * weights[k] for k in scores)

    # 实现状态加成：implemented/partial 优先于 planned
    status_bonus = {
        "implemented": 0.15,
        "partial": 0.10,
        "planned": 0.0,
    }
    total += status_bonus.get(skill.implementation_status, 0.0)

    return round(total, 4)


def _score_task_type(
    skill: SkillSpec,
    task_type: str,
    subtask_type: str,
) -> float:
    """根据 Router 的 task_type / subtask_type 打分。"""
    if not task_type and not subtask_type:
        return 0.0

    s_tasks = [t.lower() for t in skill.task_types]
    s_subtasks = [t.lower() for t in skill.subtask_types]

    task_match = task_type in s_tasks if task_type else False
    subtask_match = subtask_type in s_subtasks if subtask_type else False

    if task_match and subtask_match:
        return 1.0
    if task_match:
        return 0.7
    if subtask_match:
        return 0.5

    # 如果 skill 的 task_types 包含 "general"，给少量分
    if "general" in s_tasks:
        return 0.15

    return 0.0


def _score_keywords(skill: SkillSpec, user_message: str) -> float:
    """根据用户消息中的关键词匹配打分。"""
    if not user_message:
        # 无用户消息，靠 task_type 匹配决定，给中间分
        return 0.3

    text = user_message.lower()

    all_keywords = (
        list(skill.trigger_keywords) +
        list(skill.trigger_keywords_cn)
    )

    if not all_keywords:
        return 0.3  # 无关键词规则，中性分

    hit_count = 0
    for kw in all_keywords:
        kw_lower = kw.lower()
        if kw_lower in text:
            hit_count += 1

    if hit_count == 0:
        return 0.0

    # 命中率 + 覆盖率
    coverage = hit_count / len(all_keywords)
    return min(1.0, coverage * 1.5)


def _score_inputs(skill: SkillSpec, available_files: List[str]) -> float:
    """根据可用文件匹配打分。"""
    required = skill.required_inputs
    if not required:
        return 0.5  # 无输入要求，中性分

    if not available_files:
        return 0.0

    files_lower = [f.lower() for f in available_files]

    # 检查是否有符合要求的文件（文件名或类型匹配）
    hit = 0
    for req in required:
        req_lower = req.lower()
        for f in files_lower:
            # 检查文件名包含或文件类型匹配
            if req_lower in f or f.endswith(req_lower):
                hit += 1
                break

    return hit / len(required)
