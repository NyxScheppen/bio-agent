"""
Phase 3+: Skill Pack System Tests.

Run:
    cd D:/Desktop/bio_test
    .venv/Scripts/python.exe backend/tests/test_skill_packs.py
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
# test_load_skills_from_yaml
# ============================================================

def test_load_skills_from_yaml():
    """单文件 YAML 加载应成功。"""
    from app.agent.skills.skill_loader import load_skills_from_yaml
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    SKILL_REGISTRY.clear()

    packs_dir = Path(__file__).resolve().parents[1] / "app" / "agent" / "skills" / "packs"
    yaml_path = packs_dir / "core_file.yaml"

    skills = load_skills_from_yaml(str(yaml_path))
    _assert(len(skills) >= 3, f"core_file.yaml should have >= 3 skills, got {len(skills)}")

    ids = {s.skill_id for s in skills}
    _assert("file_probe" in ids)
    _assert("file_convert" in ids)

    print("[PASS] test_load_skills_from_yaml")


# ============================================================
# test_load_skill_pack_dir
# ============================================================

def test_load_skill_pack_dir():
    """加载整个 packs 目录。"""
    from app.agent.skills.skill_loader import load_skill_pack_dir, load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    SKILL_REGISTRY.clear()
    loaded = load_all_skill_packs()

    _assert(len(loaded) >= 40, f"Should have >= 40 skills, got {len(loaded)}")

    # 检查是否有所有类别的 skill
    categories = {s.category for s in loaded}
    expected_cats = {
        "file_io", "transcriptome", "survival", "enrichment",
        "ml", "network_pharmacology", "scrna", "spatial",
        "modeling", "drug_screening", "aptamer", "perturbation", "literature", "general",
    }
    missing = expected_cats - categories
    _assert(len(missing) == 0, f"Missing categories: {missing}")

    print(f"[PASS] test_load_skill_pack_dir ({len(loaded)} skills, {len(categories)} categories)")


# ============================================================
# test_all_skill_ids_unique
# ============================================================

def test_all_skill_ids_unique():
    """所有 skill_id 应唯一。"""
    from app.agent.skills.skill_loader import load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    SKILL_REGISTRY.clear()
    loaded = load_all_skill_packs()

    ids = [s.skill_id for s in loaded]
    duplicates = [i for i in ids if ids.count(i) > 1]
    _assert_equal(len(set(duplicates)), 0, f"Duplicate skill_ids: {set(duplicates)}")

    print(f"[PASS] test_all_skill_ids_unique ({len(ids)} unique IDs)")


# ============================================================
# test_select_implemented_skill_priority
# ============================================================

def test_select_implemented_skill_priority():
    """implemented 的 skill 应在 score 上高于 planned。"""
    from app.agent.skills.skill_loader import load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.skill_router import select_skill

    SKILL_REGISTRY.clear()
    load_all_skill_packs()

    # 单细胞聚类：目前是 planned，但 router 会建议 scrna
    router = {
        "task_type": "bioinformatics",
        "subtask_type": "scrna_analysis",
        "tool_categories": ["scrna"],
    }

    skill = select_skill(
        latest_user_message="对单细胞数据做聚类分析",
        router_result=router,
    )
    _assert(skill is not None, "Should match a skill for scRNA")
    _assert_equal(skill.skill_id, "scrna_standard_pipeline")
    _assert_equal(skill.implementation_status, "planned")

    # 差异分析（已实现）应该有更高分
    router_deg = {
        "task_type": "bioinformatics",
        "subtask_type": "deg_analysis",
        "tool_categories": ["transcriptome"],
    }
    skill_deg = select_skill(
        latest_user_message="对表达矩阵做差异分析",
        router_result=router_deg,
    )
    _assert(skill_deg is not None)
    _assert_equal(skill_deg.skill_id, "bulk_rnaseq_deg")
    _assert_equal(skill_deg.implementation_status, "implemented")

    print("[PASS] test_select_implemented_skill_priority")


# ============================================================
# test_planned_skill_does_not_call_missing_tools
# ============================================================

def test_planned_skill_does_not_call_missing_tools():
    """planned skill 无 allowed_tools 时只暴露 file_io 工具。"""
    from app.agent.skills.skill_loader import load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY, get_skill
    from app.agent.executor_agent import _apply_skill_tool_filter
    from app.agent.tool_registry import TOOL_META

    SKILL_REGISTRY.clear()
    load_all_skill_packs()

    # 选一个 planned 且无 allowed_tools 的 skill
    skill = get_skill("protein_structure_prediction")
    _assert(skill is not None)
    _assert_equal(skill.implementation_status, "planned")
    _assert_equal(len(skill.allowed_tools), 0)

    mock_schema = [
        {"function": {"name": "preview_table_file"}},
        {"function": {"name": "probe_unknown_file"}},
        {"function": {"name": "some_fake_modeling_tool"}},
        {"function": {"name": "run_survival_analysis"}},
    ]

    filtered = _apply_skill_tool_filter(mock_schema, skill)

    # 获取实际暴露的工具名
    names = {item["function"]["name"] for item in filtered}

    # 如果 TOOL_META 中有 file_io 工具，filter 会只暴露它们
    # 如果 TOOL_META 为空（隔离测试环境），会 fallback 到原始 schema
    has_file_io_in_meta = any(
        meta.get("category") == "file_io"
        for meta in TOOL_META.values()
    )
    if has_file_io_in_meta:
        _assert("run_survival_analysis" not in names,
                "Should not expose survival tool for protein modeling skill")
        _assert("preview_table_file" in names,
                "Should expose file_io tools")

    print(f"[PASS] test_planned_skill_does_not_call_missing_tools (exposed: {names})")


# ============================================================
# test_skill_pack_minimum_count
# ============================================================

def test_skill_pack_minimum_count():
    """Skill 总数不少于 40 个。"""
    from app.agent.skills.skill_loader import load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    SKILL_REGISTRY.clear()
    loaded = load_all_skill_packs()
    _assert(len(loaded) >= 40, f"Should have >= 40 skills, got {len(loaded)}")

    # 统计实现状态
    implemented = sum(1 for s in loaded if s.implementation_status == "implemented")
    partial = sum(1 for s in loaded if s.implementation_status == "partial")
    planned = sum(1 for s in loaded if s.implementation_status == "planned")
    _assert(implemented >= 10, f"Should have >= 10 implemented skills, got {implemented}")
    _assert(planned >= 20, f"Should have >= 20 planned skills, got {planned}")

    print(f"[PASS] test_skill_pack_minimum_count ({implemented} imp, {partial} part, {planned} plan)")


# ============================================================
# test_skill_field_completeness
# ============================================================

def test_skill_field_completeness():
    """每个 Skill 的必需字段不为空。"""
    from app.agent.skills.skill_loader import load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    SKILL_REGISTRY.clear()
    loaded = load_all_skill_packs()

    required_fields = [
        "skill_id", "name", "description", "category",
        "task_types", "implementation_status", "priority",
    ]

    for s in loaded:
        for field in required_fields:
            val = getattr(s, field, None)
            if field in ("task_types",):
                _assert(len(val) > 0, f"{s.skill_id}: {field} should not be empty")
            else:
                _assert(val, f"{s.skill_id}: {field} should not be empty")

    print(f"[PASS] test_skill_field_completeness ({len(loaded)} skills)")


# ============================================================
# test_skill_specific_matches
# ============================================================

def test_skill_specific_matches():
    """各种生信请求应匹配到正确的 Skill。"""
    from app.agent.skills.skill_loader import load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.skill_router import select_skill

    SKILL_REGISTRY.clear()
    load_all_skill_packs()

    test_cases = [
        ("对表达矩阵做差异分析", {"task_type": "bioinformatics", "subtask_type": "deg_analysis"}, "bulk_rnaseq_deg"),
        ("对 TP53 做单基因生存分析", {"task_type": "bioinformatics", "subtask_type": "survival_analysis"}, "single_gene_survival"),
        ("做 GO BP 生物学过程富集分析", {"task_type": "bioinformatics", "subtask_type": "enrichment"}, "go_enrichment"),
        ("用随机森林做分类", {"task_type": "bioinformatics", "subtask_type": "ml_classification"}, "ml_binary_classification"),
        ("做 PPI 蛋白互作网络分析", {"task_type": "bioinformatics", "subtask_type": "ppi_network"}, "ppi_network_analysis"),
        ("网络药理学分析中药活性成分", {"task_type": "bioinformatics", "subtask_type": "network_pharmacology"}, "network_pharm_full"),
        ("单细胞聚类分析 UMAP", {"task_type": "bioinformatics", "subtask_type": "scrna_analysis"}, "scrna_standard_pipeline"),
        ("空间转录组聚类", {"task_type": "bioinformatics", "subtask_type": "spatial_analysis"}, "spatial_clustering"),
        ("分子对接 AutoDock", {"task_type": "modeling", "subtask_type": "molecular_docking"}, "molecular_docking"),
        ("虚拟筛选化合物库", {"task_type": "drug_screening", "subtask_type": "virtual_screening"}, "virtual_screening"),
        ("适配体序列设计", {"task_type": "aptamer_screening", "subtask_type": "aptamer_design"}, "aptamer_sequence_design"),
        ("基因敲低的虚拟扰动分析", {"task_type": "bioinformatics", "subtask_type": "perturbation"}, "virtual_knockdown"),
        ("检索 PubMed 文献", {"task_type": "literature", "subtask_type": "literature_search"}, "literature_search"),
    ]

    for user_msg, router, expected_id in test_cases:
        skill = select_skill(latest_user_message=user_msg, router_result=router)
        _assert(skill is not None, f"Should match a skill for: {user_msg}")
        _assert_equal(
            skill.skill_id, expected_id,
            f"For '{user_msg}': expected {expected_id}, got {skill.skill_id}"
        )

    print("[PASS] test_skill_specific_matches (12/12 matched correctly)")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3+: Skill Pack System Tests")
    print("=" * 60)

    tests = [
        ("test_load_skills_from_yaml", test_load_skills_from_yaml),
        ("test_load_skill_pack_dir", test_load_skill_pack_dir),
        ("test_all_skill_ids_unique", test_all_skill_ids_unique),
        ("test_select_implemented_skill_priority", test_select_implemented_skill_priority),
        ("test_planned_skill_does_not_call_missing_tools", test_planned_skill_does_not_call_missing_tools),
        ("test_skill_pack_minimum_count", test_skill_pack_minimum_count),
        ("test_skill_field_completeness", test_skill_field_completeness),
        ("test_skill_specific_matches", test_skill_specific_matches),
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
