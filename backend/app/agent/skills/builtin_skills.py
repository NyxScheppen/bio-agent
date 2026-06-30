"""
Built-in Skills - 现在从 YAML packs 加载。

加载方式：
    from app.agent.skills.builtin_skills import register_all_builtin_skills
    register_all_builtin_skills()

或者直接使用 ensure_skills_loaded():
    from app.agent.skills import ensure_skills_loaded
    ensure_skills_loaded()
"""

from app.agent.skills.skill_registry import SKILL_REGISTRY, register_skill


# ============================================================
# 向后兼容：保留 5 个核心 Skill 的 Python 定义作为 fallback
# 当 YAML 加载失败时使用
# ============================================================

def _create_fallback_skills() -> list:
    """
    当 YAML 加载失败时，创建旧版硬编码 Skill 作为 fallback。
    正常情况下不调用此函数。
    """
    from app.agent.skills.skill_models import (
        SkillSpec, SkillExample, SkillClarificationRule,
        SkillParameterRule, SkillReportSection,
    )

    return [
        SkillSpec(
            skill_id="file_probe", name="文件探测", category="file_io",
            description="探测文件结构",
            task_types=["file_processing"], subtask_types=["file_probe"],
            allowed_tools=["preview_table_file", "probe_unknown_file"],
            max_tool_rounds=4, implementation_status="implemented", priority="high",
        ),
        SkillSpec(
            skill_id="bulk_rnaseq_deg", name="Bulk RNA-seq 差异分析", category="transcriptome",
            description="Bulk RNA-seq 差异表达分析",
            task_types=["bioinformatics"], subtask_types=["deg_analysis"],
            allowed_tools=["run_bulk_rnaseq_deg_analysis", "preview_table_file"],
            max_tool_rounds=14, implementation_status="implemented", priority="high",
        ),
        SkillSpec(
            skill_id="single_gene_survival", name="单基因生存分析", category="survival",
            description="单基因生存分析",
            task_types=["bioinformatics"], subtask_types=["survival_analysis"],
            allowed_tools=["run_single_gene_survival_analysis", "preview_table_file"],
            max_tool_rounds=10, implementation_status="implemented", priority="high",
        ),
        SkillSpec(
            skill_id="enrichment_analysis", name="富集分析", category="enrichment",
            description="GO/KEGG 富集分析",
            task_types=["bioinformatics"], subtask_types=["enrichment"],
            allowed_tools=["run_enrichment_analysis", "preview_table_file"],
            max_tool_rounds=8, implementation_status="implemented", priority="high",
        ),
        SkillSpec(
            skill_id="ml_classification", name="机器学习分类", category="ml",
            description="ML 分类模型",
            task_types=["bioinformatics"], subtask_types=["ml_classification"],
            allowed_tools=["run_ml_classification", "preview_table_file"],
            max_tool_rounds=12, implementation_status="implemented", priority="high",
        ),
    ]


def register_all_builtin_skills() -> list:
    """
    注册所有内置 Skill。

    优先从 YAML packs 加载，失败时使用 Python fallback。
    返回注册的 skill_id 列表。
    """
    from app.agent.skills.skill_loader import load_all_skill_packs

    try:
        loaded = load_all_skill_packs()
        if loaded:
            return [s.skill_id for s in loaded]
    except Exception as e:
        print(f"[builtin_skills] YAML loading failed: {e}, using fallback")

    # Fallback: 使用旧版硬编码
    SKILL_REGISTRY.clear()
    fallback = _create_fallback_skills()
    for s in fallback:
        register_skill(s)
    print(f"[builtin_skills] Registered {len(fallback)} fallback skills")
    return [s.skill_id for s in fallback]
