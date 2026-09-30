import pytest


def test_duplicate_skill_registration_fails_closed():
    from app.agent.skills.skill_models import SkillSpec
    from app.agent.skills.skill_registry import (
        DuplicateSkillError,
        SKILL_REGISTRY,
        register_skill,
    )

    SKILL_REGISTRY.clear()
    register_skill(SkillSpec(skill_id="duplicate", name="first"))
    with pytest.raises(DuplicateSkillError):
        register_skill(SkillSpec(skill_id="duplicate", name="second"))


def test_builtin_skill_registration_is_idempotent():
    from app.agent.skills.builtin_skills import register_all_builtin_skills
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    SKILL_REGISTRY.clear()
    first = register_all_builtin_skills()
    second = register_all_builtin_skills()
    assert second == sorted(set(first))
    assert len(SKILL_REGISTRY) == len(first)


def test_all_skill_tool_references_exist():
    from app import tools  # noqa: F401
    from app.agent.skills.skill_loader import (
        load_all_skill_packs,
        validate_skill_tool_references,
    )
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.tool_registry import TOOL_REGISTRY

    SKILL_REGISTRY.clear()
    skills = load_all_skill_packs()
    validate_skill_tool_references(skills, TOOL_REGISTRY)


def test_implemented_skill_with_empty_allowlist_fails_closed():
    from app.agent.skills.skill_models import SkillSpec
    from app.agent.skills.tool_policy import allowed_tool_names_for_skill

    skill = SkillSpec(
        skill_id="bad_implemented_skill",
        name="Bad implemented skill",
        implementation_status="implemented",
    )
    assert allowed_tool_names_for_skill(skill, {"run_r_analysis"}) == set()


def test_duplicate_tool_registration_fails_closed():
    from app.agent.tool_registry import (
        DuplicateToolError,
        TOOL_META,
        TOOL_REGISTRY,
        TOOLS_SCHEMA,
        register_tool,
    )

    name = "contract_test_duplicate_tool"
    TOOL_REGISTRY.pop(name, None)
    TOOL_META.pop(name, None)
    TOOLS_SCHEMA[:] = [
        schema for schema in TOOLS_SCHEMA
        if schema.get("function", {}).get("name") != name
    ]
    try:
        @register_tool(name=name, description="first")
        def first_tool():
            return "first"

        with pytest.raises(DuplicateToolError):
            @register_tool(name=name, description="second")
            def second_tool():
                return "second"
    finally:
        TOOL_REGISTRY.pop(name, None)
        TOOL_META.pop(name, None)
        TOOLS_SCHEMA[:] = [
            schema for schema in TOOLS_SCHEMA
            if schema.get("function", {}).get("name") != name
        ]


def test_unrelated_request_does_not_select_skill():
    from app.agent.skills.builtin_skills import register_all_builtin_skills
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.skill_router import select_skill

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()
    selected = select_skill(
        "tomorrow weather in London",
        {"task_type": "weather", "subtask_type": "forecast"},
    )
    assert selected is None


def test_generic_router_type_is_not_enough_to_select_skill():
    from app.agent.skills.builtin_skills import register_all_builtin_skills
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.skill_router import select_skill

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()
    assert select_skill(
        "please help with this",
        {"task_type": "bioinformatics", "subtask_type": "unknown"},
    ) is None


def test_stale_uploaded_file_does_not_hijack_unrelated_request():
    from app.agent.skills.builtin_skills import register_all_builtin_skills
    from app.agent.skills.skill_registry import SKILL_REGISTRY
    from app.agent.skills.skill_router import select_skill

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()
    assert select_skill(
        "tomorrow weather in London",
        {"task_type": "weather", "subtask_type": "forecast"},
        available_files=["counts.csv"],
    ) is None


def test_short_ascii_keyword_requires_token_boundary():
    from app.agent.skills.skill_models import SkillSpec
    from app.agent.skills.skill_registry import SKILL_REGISTRY, register_skill
    from app.agent.skills.skill_router import select_skill

    SKILL_REGISTRY.clear()
    register_skill(
        SkillSpec(
            skill_id="r_task",
            name="R task",
            trigger_keywords=["R"],
            implementation_status="implemented",
        )
    )
    assert select_skill("tomorrow weather", {}) is None
    assert select_skill("run R analysis", {}).skill_id == "r_task"


def test_uploaded_files_are_extracted_for_skill_routing():
    from app.agent.bio_agent import _available_files_from_context

    context = {
        "summary": "",
        "latest_user_message": "请分析上传的数据",
        "recent_messages": [{
            "role": "system",
            "content": "1. 文件名: counts.csv | 类型: csv | 相对路径: uploads/s/counts.csv",
        }],
    }
    assert _available_files_from_context(context) == ["counts.csv"]


def test_skill_prompt_propagates_safety_and_expected_outputs():
    from app.agent.planner_agent import _build_skill_planner_prompt
    from app.agent.skills.skill_models import SkillSpec

    skill = SkillSpec(
        skill_id="safe_skill",
        name="Safe skill",
        safety_rules=["SAFETY_SENTINEL"],
        output_expectations=["OUTPUT_SENTINEL.csv"],
    )
    prompt = _build_skill_planner_prompt(skill)
    assert "SAFETY_SENTINEL" in prompt
    assert "OUTPUT_SENTINEL.csv" in prompt
    assert "不得据此编造" in prompt


def test_planner_rejects_malformed_shape_and_caps_rounds(monkeypatch):
    import app.agent.planner_agent as planner
    from app.agent.skills.skill_models import SkillSpec

    skill = SkillSpec(skill_id="limited", name="Limited", max_tool_rounds=4)
    monkeypatch.setattr(
        planner,
        "call_json_agent",
        lambda *_: {"steps": "not-a-list", "max_tool_rounds": 20},
    )
    result = planner.run_planner_agent(
        {"latest_user_message": "x"},
        {"suggested_mode": "tool_execution"},
        selected_skill=skill,
    )
    assert result["steps"] == []
    assert result["max_tool_rounds"] == 4
    assert result["skill_max_tool_rounds"] == 4
    assert isinstance(result["available_tools"], list)


def test_executor_never_exceeds_skill_round_cap():
    from app.agent.executor_agent import get_effective_max_tool_rounds

    rounds = get_effective_max_tool_rounds(
        {"task_type": "bioinformatics", "complexity": "complex"},
        {
            "objective": "complex expression analysis",
            "max_tool_rounds": 20,
            "skill_max_tool_rounds": 4,
        },
    )
    assert rounds == 4


def test_delegator_rejects_malformed_planner_steps():
    from app.agent.delegator_agent import run_delegator_agent

    result = run_delegator_agent({}, {"steps": "not-a-list"})
    assert result["should_delegate"] is False
    assert result["sub_tasks"] == []


def test_delegator_receives_planner_tool_list(monkeypatch):
    import app.agent.delegator_agent as delegator

    captured = {}

    def fake_call(_prompt, payload):
        captured.update(payload)
        return {"should_delegate": False, "reason": "serial", "sub_tasks": []}

    monkeypatch.setattr(delegator, "call_json_agent", fake_call)
    delegator.run_delegator_agent(
        {"latest_user_message": "x"},
        {
            "objective": "x",
            "available_tools": [{"name": "preview_table_file"}],
            "steps": [
                {"step_id": index + 1, "goal": str(index), "preferred_tools": [], "parameters": {}}
                for index in range(3)
            ],
        },
    )
    assert captured["available_tools"] == ["preview_table_file"]


def test_unknown_planner_step_reference_is_rejected():
    from app.agent.delegator_agent import _steps_to_sub_tasks

    steps = [{
        "step_id": 1,
        "goal": "x",
        "preferred_tools": ["preview_table_file"],
        "parameters": {"file_path": "$step_99"},
    }]
    with pytest.raises(ValueError, match="未知步骤"):
        _steps_to_sub_tasks(steps, {}, [[1]])


def test_reporter_role_receives_reporter_only_rules():
    from app.agent.task_prompts import build_domain_prompt

    marker = "最终回复必须使用 Markdown 图片格式"
    assert marker not in build_domain_prompt(["general"])
    assert marker in build_domain_prompt(["general"], agent_role="reporter")


def test_malformed_router_output_falls_back(monkeypatch):
    import app.agent.router_agent as router

    monkeypatch.setattr(
        router,
        "call_json_agent",
        lambda *_: {"task_type": [], "need_clarification": "no"},
    )
    result = router.run_router_agent({"latest_user_message": "plain request"})
    assert result["task_type"] == "unclear"
    assert result["need_clarification"] is True


def test_empty_router_output_falls_back(monkeypatch):
    import app.agent.router_agent as router

    monkeypatch.setattr(router, "call_json_agent", lambda *_: {})
    result = router.run_router_agent({"latest_user_message": "plain request"})
    assert result["task_type"] == "unclear"
    assert result["suggested_mode"] == "ask_user"


def test_planner_rejects_unknown_dependencies():
    from app.agent.planner_agent import _is_valid_planner_result

    assert not _is_valid_planner_result({
        "execution_mode": "tool_execution",
        "steps": [{
            "step_id": 1,
            "preferred_tools": [],
            "parameters": {},
        }],
        "step_dependencies": {"1": [99]},
        "parallel_groups": [],
    })


def test_geo_download_skill_is_not_claimed_as_fully_implemented():
    from app.agent.skills.builtin_skills import register_all_builtin_skills
    from app.agent.skills.skill_registry import SKILL_REGISTRY, get_skill

    SKILL_REGISTRY.clear()
    register_all_builtin_skills()
    skill = get_skill("geo_data_download")
    assert skill is not None
    assert skill.implementation_status == "partial"
    assert any("不支持按 accession 联网下载" in rule for rule in skill.safety_rules)


def test_file_recovery_uses_a_registered_tool():
    from app import tools  # noqa: F401
    from app.agent.recovery_strategies import EncodingRecovery, FileParseRecovery
    from app.agent.tool_registry import TOOL_REGISTRY

    for strategy in (FileParseRecovery(), EncodingRecovery()):
        tool_name, args = strategy.get_recovery_tool_and_args(
            {"file_path": "counts.csv"}
        )
        assert tool_name == "preview_table_file"
        assert tool_name in TOOL_REGISTRY
        assert args == {"file_path": "counts.csv"}
