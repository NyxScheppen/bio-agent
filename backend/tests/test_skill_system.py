"""
Phase 3+: Skill System Unit Tests.

Run:
    cd D:/Desktop/bio_test
    .venv/Scripts/python.exe backend/tests/test_skill_system.py
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _assert(condition, msg=""):
    if not condition:
        raise AssertionError(f"FAIL: {msg}" if msg else "FAIL")


def _assert_equal(a, b, msg=""):
    _assert(a == b, f"{msg}: expected {b!r}, got {a!r}")


# ============================================================
# test_builtin_skills_loaded
# ============================================================

def test_builtin_skills_loaded():
    """49 个 Skill 应从 YAML packs 加载。"""
    from app.agent.skills.skill_registry import SKILL_REGISTRY, list_skills
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    ids = register_all_builtin_skills()

    # 至少应有 40 个 skill
    _assert(len(ids) >= 40, f"Should have >= 40 skills, got {len(ids)}")

    # 5 个核心 skill 必须存在
    core = {"file_probe", "bulk_rnaseq_deg", "single_gene_survival",
            "go_enrichment", "ml_binary_classification"}
    for cid in core:
        _assert(cid in ids, f"Core skill {cid} should be loaded")

    all_skills = list_skills()
    _assert(len(all_skills) >= 40)

    for skill in all_skills:
        _assert(skill.skill_id, "skill_id should not be empty")
        _assert(skill.name, "name should not be empty")
        _assert(skill.category, "category should not be empty")
        _assert(skill.enabled, "should be enabled")

    print(f"[PASS] test_builtin_skills_loaded ({len(ids)} skills)")


# ============================================================
# test_select_bulk_deg_skill
# ============================================================

def test_select_bulk_deg_skill():
    """Router 返回 bioinformatics + deg_analysis 时应匹配 bulk_rnaseq_deg。"""
    from app.agent.skills.skill_router import select_skill
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    router = {
        "task_type": "bioinformatics",
        "subtask_type": "deg_analysis",
        "complexity": "medium",
        "tool_categories": ["transcriptome"],
    }

    skill = select_skill(
        latest_user_message="对表达矩阵做差异分析，control vs treated",
        router_result=router,
    )

    _assert(skill is not None, "Should match a skill")
    _assert_equal(skill.skill_id, "bulk_rnaseq_deg")
    print("[PASS] test_select_bulk_deg_skill")


# ============================================================
# test_select_single_gene_survival_skill
# ============================================================

def test_select_single_gene_survival_skill():
    """用户请求生存分析时应匹配 single_gene_survival。"""
    from app.agent.skills.skill_router import select_skill
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    router = {
        "task_type": "bioinformatics",
        "subtask_type": "survival_analysis",
        "tool_categories": ["survival"],
    }

    skill = select_skill(
        latest_user_message="对 TP53 做单基因生存分析，用 KM 曲线",
        router_result=router,
    )

    _assert(skill is not None, "Should match a skill")
    _assert_equal(skill.skill_id, "single_gene_survival")
    print("[PASS] test_select_single_gene_survival_skill")


def test_select_ml_skill():
    """用户请求 ML 分类时应匹配 ml_binary_classification。"""
    from app.agent.skills.skill_router import select_skill
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    router = {
        "task_type": "bioinformatics",
        "subtask_type": "ml_classification",
        "tool_categories": ["ml"],
    }

    skill = select_skill(
        latest_user_message="用随机森林分类样本",
        router_result=router,
    )

    _assert(skill is not None)
    # YAML 中该 skill ID 为 ml_binary_classification
    _assert_equal(skill.skill_id, "ml_binary_classification")
    print("[PASS] test_select_ml_skill")


# ============================================================
# test_skill_no_match_fallback
# ============================================================

def test_skill_no_match_fallback():
    """不匹配任何 Skill 时返回 None（fallback 到自由规划）。"""
    from app.agent.skills.skill_router import select_skill
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    router = {
        "task_type": "unclear",
        "subtask_type": "unknown",
        "tool_categories": ["general"],
    }

    skill = select_skill(
        latest_user_message="",
        router_result=router,
        min_score=0.40,
    )

    _assert(skill is None, "Empty message with unclear router should not match")
    print("[PASS] test_skill_no_match_fallback")


# ============================================================
# test_planner_receives_skill
# ============================================================

def test_planner_receives_skill():
    """Planner 在收到 selected_skill 时应输出 skill 相关信息。"""
    from app.agent.planner_agent import run_planner_agent
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    from app.agent.skills.skill_registry import get_skill
    skill = get_skill("single_gene_survival")
    _assert(skill is not None)

    context = {
        "summary": "",
        "recent_messages": [],
        "latest_user_message": "对 TP53 做生存分析",
    }
    router = {
        "task_type": "bioinformatics",
        "subtask_type": "survival_analysis",
        "tool_categories": ["survival"],
        "need_clarification": False,
        "clarification_question": "",
    }

    # Without skill
    result_no_skill = run_planner_agent(context, router)
    _assert("skill_id" not in result_no_skill or result_no_skill.get("skill_id") is None,
            "No skill means no skill_id in result")

    # With skill
    result_with_skill = run_planner_agent(context, router, selected_skill=skill)
    _assert_equal(result_with_skill.get("skill_id"), "single_gene_survival")
    _assert("skill_parameter_rules" in result_with_skill)

    print("[PASS] test_planner_receives_skill")


# ============================================================
# test_executor_skill_allowed_tools
# ============================================================

def test_executor_skill_allowed_tools():
    """Executor 在有 skill.allowed_tools 时应过滤工具。"""
    from app.agent.executor_agent import _apply_skill_tool_filter
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    from app.agent.skills.skill_registry import get_skill
    skill = get_skill("file_probe")
    _assert(skill is not None)

    # Mock tool schema
    mock_schema = [
        {"function": {"name": "preview_table_file"}},
        {"function": {"name": "probe_unknown_file"}},
        {"function": {"name": "run_survival_analysis"}},  # not in file_probe
        {"function": {"name": "run_deg_analysis"}},       # not in file_probe
    ]

    filtered = _apply_skill_tool_filter(mock_schema, skill)
    _assert_equal(len(filtered), 2)
    names = {item["function"]["name"] for item in filtered}
    _assert("preview_table_file" in names)
    _assert("probe_unknown_file" in names)
    _assert("run_survival_analysis" not in names)
    _assert("run_deg_analysis" not in names)

    print("[PASS] test_executor_skill_allowed_tools")


def test_executor_skill_allowed_tools_empty_fallback():
    """当 skill.allowed_tools 过滤后为空时，应 fallback 到原 schema。"""
    from app.agent.executor_agent import _apply_skill_tool_filter

    class FakeSkill:
        allowed_tools = ["non_existent_tool"]
        banned_tools = []

    mock_schema = [
        {"function": {"name": "some_other_tool"}},
    ]

    filtered = _apply_skill_tool_filter(mock_schema, FakeSkill())
    # Should fallback to original
    _assert_equal(len(filtered), 1)
    _assert_equal(filtered[0]["function"]["name"], "some_other_tool")

    print("[PASS] test_executor_skill_allowed_tools_empty_fallback")


# ============================================================
# test_skill_registry_operations
# ============================================================

def test_skill_registry_operations():
    """测试 get_skill / find_skills_by_category / find_skills_by_task_type。"""
    from app.agent.skills.skill_registry import (
        SKILL_REGISTRY, register_skill, get_skill,
        find_skills_by_category, find_skills_by_task_type,
    )
    from app.agent.skills.skill_models import SkillSpec
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    # get_skill
    s = get_skill("bulk_rnaseq_deg")
    _assert(s is not None)
    _assert_equal(s.name, "Bulk RNA-seq 差异表达分析")

    # get non-existent
    s_none = get_skill("nonexistent")
    _assert(s_none is None)

    # find by category (YAML packs have 5 transcriptome skills now)
    transcriptome = find_skills_by_category("transcriptome")
    _assert(len(transcriptome) >= 5, f"Should have >=5 transcriptome skills, got {len(transcriptome)}")
    ids = {s.skill_id for s in transcriptome}
    _assert("bulk_rnaseq_deg" in ids)

    # find by task_type only
    bio_skills = find_skills_by_task_type("bioinformatics")
    _assert(len(bio_skills) >= 10, f"Should have >=10 bioinfo skills, got {len(bio_skills)}")

    # find by task_type + subtask_type (exact match, may return multiple)
    survival_skills = find_skills_by_task_type("bioinformatics", "survival_analysis")
    _assert(len(survival_skills) >= 1, "Should have at least 1 survival skill")
    surv_ids = {s.skill_id for s in survival_skills}
    _assert("single_gene_survival" in surv_ids)

    # subtask_type only (deg_analysis matches bulk_rnaseq_deg and deseq2_count_deg)
    deg_skills = find_skills_by_task_type("", "deg_analysis")
    _assert(len(deg_skills) >= 1, "Should have at least 1 deg skill")
    deg_ids = {s.skill_id for s in deg_skills}
    _assert("bulk_rnaseq_deg" in deg_ids)

    print("[PASS] test_skill_registry_operations")


# ============================================================
# test_skill_spec_fields
# ============================================================

def test_skill_spec_fields():
    """验证 SkillSpec 各字段完整。"""
    from app.agent.skills.skill_registry import SKILL_REGISTRY, get_skill
    from app.agent.skills.builtin_skills import register_all_builtin_skills

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()

    for sid in ["file_probe", "bulk_rnaseq_deg", "single_gene_survival",
                 "go_enrichment", "ml_binary_classification"]:
        s = get_skill(sid)
        _assert(s is not None, f"Skill {sid} should exist")
        _assert(s.skill_id, f"{sid}: skill_id")
        _assert(s.name, f"{sid}: name")
        _assert(s.category, f"{sid}: category")
        _assert(s.description, f"{sid}: description")
        _assert(len(s.task_types) > 0, f"{sid}: task_types")
        _assert(len(s.allowed_tools) > 0, f"{sid}: allowed_tools")
        _assert(s.max_tool_rounds > 0, f"{sid}: max_tool_rounds")
        _assert(len(s.report_sections) > 0, f"{sid}: report_sections")
        _assert(s.enabled, f"{sid}: enabled")

    print("[PASS] test_skill_spec_fields")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3+: Skill System Unit Tests")
    print("=" * 60)

    tests = [
        ("test_builtin_skills_loaded", test_builtin_skills_loaded),
        ("test_select_bulk_deg_skill", test_select_bulk_deg_skill),
        ("test_select_single_gene_survival_skill", test_select_single_gene_survival_skill),
        ("test_select_ml_skill", test_select_ml_skill),
        ("test_skill_no_match_fallback", test_skill_no_match_fallback),
        ("test_planner_receives_skill", test_planner_receives_skill),
        ("test_executor_skill_allowed_tools", test_executor_skill_allowed_tools),
        ("test_executor_skill_allowed_tools_empty_fallback", test_executor_skill_allowed_tools_empty_fallback),
        ("test_skill_registry_operations", test_skill_registry_operations),
        ("test_skill_spec_fields", test_skill_spec_fields),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'=' * 60}")

    if failed > 0:
        sys.exit(1)
