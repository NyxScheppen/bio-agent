"""Multi-Agent contracts, dependency scheduling, delegation, and racing tests."""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Callable

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent.agent_constants import FEATURE_FLAGS  # noqa: E402
from app.agent.bio_agent import (  # noqa: E402
    _normalize_execution_mode,
    _run_delegated_tasks,
)
from app.agent.delegator_agent import _steps_to_sub_tasks  # noqa: E402
from app.agent.executor_agent import _apply_skill_tool_filter  # noqa: E402
from app.agent.parallel_executor import (  # noqa: E402
    _build_execution_batches,
    _resolve_step_references,
    execute_parallel_steps,
)
from app.agent.sub_agent_manager import (  # noqa: E402
    SubAgentManager,
    SubAgentResult,
    SubAgentTask,
)
from app.agent.skills.skill_models import SkillSpec  # noqa: E402
from app.agent.tool_result import (  # noqa: E402
    ResourceUsage,
    make_error_result,
    make_success_result,
)


def _assert(condition: bool, message: str = "") -> None:
    if not condition:
        raise AssertionError(message or "assertion failed")


def _assert_equal(actual: Any, expected: Any, message: str = "") -> None:
    _assert(actual == expected, message or f"expected {expected!r}, got {actual!r}")


def _patched(module: Any, name: str, value: Any) -> Callable[[], None]:
    original = getattr(module, name)
    setattr(module, name, value)
    return lambda: setattr(module, name, original)


def test_execution_mode_alias() -> None:
    _assert_equal(_normalize_execution_mode("direct_answer"), "answer_only")
    _assert_equal(_normalize_execution_mode("ask_user"), "ask_user")
    _assert_equal(_normalize_execution_mode("unexpected"), "tool_execution")


def test_router_and_planner_errors_fall_back_safely() -> None:
    import app.agent.planner_agent as planner
    import app.agent.router_agent as router

    restore_router = _patched(
        router,
        "call_json_agent",
        lambda *args, **kwargs: {"error": "offline"},
    )
    restore_planner = _patched(
        planner,
        "call_json_agent",
        lambda *args, **kwargs: {"error": "offline"},
    )
    try:
        router_result = router.run_router_agent({"latest_user_message": "task"})
        planner_result = planner.run_planner_agent(
            {"latest_user_message": "task"},
            router_result,
        )
    finally:
        restore_planner()
        restore_router()

    _assert_equal(router_result["suggested_mode"], "ask_user")
    _assert_equal(planner_result["execution_mode"], "ask_user")
    _assert_equal(planner_result["steps"], [])


def test_delegator_converts_ids_to_task_indexes() -> None:
    steps = [
        {"step_id": 10, "preferred_tools": ["a"], "parameters": {"path": "x"}},
        {"step_id": 20, "preferred_tools": ["b"], "parameters": {"path": "$step_10"}},
    ]
    tasks = _steps_to_sub_tasks(steps, {"20": [10]})
    _assert_equal(tasks[1]["depends_on"], [0])
    _assert_equal(tasks[1]["args"], {"path": "$step_0"})


def test_delegator_preserves_parallel_group_allowlist() -> None:
    steps = [
        {"step_id": 1, "preferred_tools": ["a"], "parameters": {}},
        {"step_id": 2, "preferred_tools": ["b"], "parameters": {}},
        {"step_id": 3, "preferred_tools": ["c"], "parameters": {}},
    ]
    tasks = _steps_to_sub_tasks(steps, {}, [[1, 3]])
    _assert_equal(tasks[0]["depends_on"], [])
    _assert_equal(tasks[2]["depends_on"], [])
    _assert_equal(tasks[1]["depends_on"], [])
    _assert_equal(tasks[1]["schedule_after"], [0, 2])


def test_orchestrator_schedule_barrier_does_not_cascade_failure() -> None:
    from app.agent.orchestrator import Orchestrator

    calls = []

    class BatchManager(SubAgentManager):
        def spawn_and_collect_all(
            self,
            tasks: list[SubAgentTask],
            session_id: str = "",
        ) -> list[SubAgentResult]:
            calls.append([task.goal for task in tasks])
            return [
                SubAgentResult(
                    task_index=index,
                    goal=task.goal,
                    tool=task.tool,
                    status="error" if task.goal == "first" else "success",
                    message="done",
                )
                for index, task in enumerate(tasks)
            ]

    orchestrator = Orchestrator(manager=BatchManager())
    orchestrator.add_task("0", "first", "a")
    orchestrator.add_task("1", "later", "b", schedule_after=["0", "2"])
    orchestrator.add_task("2", "third", "c")
    result = orchestrator.run_all()

    _assert_equal(calls, [["first", "third"], ["later"]])
    _assert_equal([item["task_id"] for item in result["failed"]], ["0"])
    _assert_equal(
        [item["task_id"] for item in result["completed"]],
        ["1", "2"],
    )


def test_orchestrator_preserves_planner_parameters() -> None:
    from app.agent.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.add_tasks_from_planner(
        [{
            "step_id": 2,
            "goal": "analyze",
            "preferred_tools": ["tool"],
            "parameters": {"path": "input.csv"},
        }],
        {"2": []},
    )
    _assert_equal(orchestrator.tasks["2"].args, {"path": "input.csv"})
    _assert_equal(orchestrator.tasks["2"].depends_on, [])


def test_delegated_tasks_reach_sub_agent_manager() -> None:
    import app.agent.bio_agent as bio_module
    import app.agent.orchestrator as module

    calls = []

    class CaptureManager(SubAgentManager):
        def spawn_and_collect_all(
            self,
            tasks: list[SubAgentTask],
            session_id: str = "",
        ) -> list[SubAgentResult]:
            calls.append((tasks[0].tool, tasks[0].args, session_id))
            return [
                SubAgentResult(
                    task_index=0,
                    goal=tasks[0].goal,
                    tool=tasks[0].tool,
                    status="success",
                    message="done",
                )
            ]

    bio_module.TOOL_REGISTRY["demo"] = lambda x: x
    restore = _patched(module, "sub_agent_manager", CaptureManager())
    try:
        result = _run_delegated_tasks([
            {"goal": "work", "tool": "demo", "args": {"x": 1}, "depends_on": []},
        ], "parent")
    finally:
        restore()
        bio_module.TOOL_REGISTRY.pop("demo", None)

    _assert_equal(calls, [("demo", {"x": 1}, "parent")])
    _assert_equal(result["tool_observations"][0]["status"], "success")


def test_delegation_enforces_skill_tool_policy() -> None:
    import app.agent.bio_agent as module

    calls = []
    module.TOOL_REGISTRY["safe"] = lambda: None
    module.TOOL_REGISTRY["unsafe"] = lambda: calls.append("unsafe")
    skill = SkillSpec(
        skill_id="restricted",
        implementation_status="implemented",
        allowed_tools=["safe"],
        banned_tools=["unsafe"],
    )
    try:
        result = _run_delegated_tasks([{
            "goal": "must reject",
            "tool": "unsafe",
            "args": {},
            "depends_on": [],
        }], "parent", selected_skill=skill)
    finally:
        module.TOOL_REGISTRY.pop("safe", None)
        module.TOOL_REGISTRY.pop("unsafe", None)

    _assert_equal(calls, [])
    _assert_equal(result["tool_observations"][0]["status"], "error")
    _assert_equal(result["tool_observations"][0]["errors"], ["delegated_tool_not_allowed"])


def test_skill_tool_policy_fails_closed() -> None:
    schema = [{"type": "function", "function": {"name": "unsafe"}}]
    skill = SkillSpec(
        skill_id="restricted",
        implementation_status="implemented",
        allowed_tools=["safe"],
    )
    _assert_equal(_apply_skill_tool_filter(schema, skill), [])


def test_sub_agent_invalid_and_cyclic_dependencies_are_blocked() -> None:
    manager = SubAgentManager()
    invalid = manager.spawn_and_collect_all([
        SubAgentTask(goal="invalid", tool="missing", depends_on=[99]),
    ])
    cyclic = manager.spawn_and_collect_all([
        SubAgentTask(goal="a", tool="missing", depends_on=[1]),
        SubAgentTask(goal="b", tool="missing", depends_on=[0]),
    ])
    _assert_equal(invalid[0].status, "blocked")
    _assert_equal([item.status for item in cyclic], ["blocked", "blocked"])


def test_sub_agent_failure_blocks_dependents() -> None:
    import app.agent.sub_agent_manager as module

    calls = []
    module.TOOL_REGISTRY["fail"] = lambda: None
    module.TOOL_REGISTRY["must_not_run"] = lambda: None

    def fake_runner(**kwargs: Any) -> Any:
        calls.append(kwargs["tool_name"])
        return make_error_result("failed")

    restore = _patched(module, "run_tool_with_lifecycle", fake_runner)
    try:
        results = SubAgentManager().spawn_and_collect_all([
            SubAgentTask(goal="first", tool="fail", max_retries=0),
            SubAgentTask(goal="second", tool="must_not_run", depends_on=[0]),
        ])
    finally:
        restore()
        module.TOOL_REGISTRY.pop("fail", None)
        module.TOOL_REGISTRY.pop("must_not_run", None)

    _assert_equal(calls, ["fail"])
    _assert_equal([item.status for item in results], ["error", "blocked"])


def test_sub_agent_retry_and_runtime() -> None:
    import app.agent.sub_agent_manager as module

    calls = []
    module.TOOL_REGISTRY["flaky"] = lambda: None

    def fake_runner(**kwargs: Any) -> Any:
        calls.append(kwargs.get("timeout_override"))
        if len(calls) == 1:
            return make_error_result("retry")
        return make_success_result("ok")

    restore = _patched(module, "run_tool_with_lifecycle", fake_runner)
    try:
        result = SubAgentManager().spawn_and_collect_all([
            SubAgentTask(goal="retry", tool="flaky", max_retries=1, timeout=17),
        ])[0]
    finally:
        restore()
        module.TOOL_REGISTRY.pop("flaky", None)

    _assert_equal(calls, [17, 17])
    _assert_equal((result.status, result.attempts), ("success", 2))
    _assert(result.runtime_seconds >= 0)


def test_sub_agent_timeout_is_never_retried() -> None:
    import app.agent.sub_agent_manager as module

    calls = []
    module.TOOL_REGISTRY["slow"] = lambda: None

    def fake_runner(**kwargs: Any) -> Any:
        calls.append(kwargs["tool_name"])
        result = make_error_result("timeout")
        result.provenance.resource_usage = ResourceUsage(timeout_triggered=True)
        return result

    restore = _patched(module, "run_tool_with_lifecycle", fake_runner)
    try:
        result = SubAgentManager().spawn_and_collect_all([
            SubAgentTask(goal="slow", tool="slow", max_retries=3),
        ])[0]
    finally:
        restore()
        module.TOOL_REGISTRY.pop("slow", None)

    _assert_equal(calls, ["slow"])
    _assert_equal((result.status, result.attempts), ("timeout", 1))
    _assert_equal(SubAgentTask().max_retries, 0)


def test_parallel_groups_and_cycle_validation() -> None:
    steps = [{"step_id": 1}, {"step_id": 2}, {"step_id": 3}]
    batches = _build_execution_batches(steps, {}, [[1, 3]])
    _assert_equal([[step["step_id"] for step in batch] for batch in batches], [[1, 3], [2]])
    try:
        _build_execution_batches(steps[:2], {"1": [2], "2": [1]}, [])
    except ValueError as exc:
        _assert("循环依赖" in str(exc))
    else:
        raise AssertionError("cycle should be rejected")


def test_parallel_failure_blocks_downstream() -> None:
    import app.agent.parallel_executor as module

    calls = []
    module.TOOL_REGISTRY["first"] = lambda: None
    module.TOOL_REGISTRY["second"] = lambda path: None

    def fake_runner(**kwargs: Any) -> Any:
        calls.append(kwargs["tool_name"])
        return make_error_result("upstream failed")

    restore = _patched(module, "run_tool_with_lifecycle", fake_runner)
    old_racing = FEATURE_FLAGS["waterfall_racing"]
    FEATURE_FLAGS["waterfall_racing"] = False
    try:
        steps = [
            {"step_id": 1, "tool": "first", "parameters": {}},
            {"step_id": 2, "tool": "second", "parameters": {"path": "$step_1"}},
        ]
        batches = _build_execution_batches(steps, {"2": [1]}, [])
        observations, _ = execute_parallel_steps(
            batches,
            {"first", "second"},
            "session",
            dependencies={"2": [1]},
        )
    finally:
        FEATURE_FLAGS["waterfall_racing"] = old_racing
        restore()
        module.TOOL_REGISTRY.pop("first", None)
        module.TOOL_REGISTRY.pop("second", None)

    _assert_equal(calls, ["first"])
    _assert_equal([item["status"] for item in observations], ["error", "blocked"])


def test_parallel_step_rejects_missing_parameters() -> None:
    import app.agent.parallel_executor as module

    module.TOOL_REGISTRY["demo"] = lambda required: required
    old_racing = FEATURE_FLAGS["waterfall_racing"]
    FEATURE_FLAGS["waterfall_racing"] = False
    try:
        observations, _ = execute_parallel_steps(
            [[{"step_id": 1, "tool": "demo"}]],
            {"demo"},
            "session",
        )
    finally:
        FEATURE_FLAGS["waterfall_racing"] = old_racing
        module.TOOL_REGISTRY.pop("demo", None)

    _assert_equal(observations[0]["status"], "error")
    _assert_equal(observations[0]["errors"], ["invalid_parameters"])


def test_nested_step_references_are_strict() -> None:
    previous = {
        1: {
            "status": "success",
            "result_summary": "summary",
            "output_files": [{"relative_path": "generated/result.csv"}],
        }
    }
    resolved = _resolve_step_references({"nested": ["$step_1"]}, previous)
    _assert_equal(resolved, {"nested": ["generated/result.csv"]})
    try:
        _resolve_step_references({"path": "$step_2"}, previous)
    except ValueError:
        return
    raise AssertionError("unknown reference should fail")


def test_step_reference_requires_declared_dependency() -> None:
    previous = {
        1: {
            "status": "success",
            "result_summary": "summary",
            "output_files": [],
        }
    }
    try:
        _resolve_step_references(
            {"path": "$step_1"},
            previous,
            allowed_reference_ids=set(),
        )
    except ValueError as exc:
        _assert("未声明依赖" in str(exc))
    else:
        raise AssertionError("undeclared reference should fail")


def test_orchestrator_blocks_undeclared_step_reference() -> None:
    from app.agent.orchestrator import Orchestrator

    calls = []

    class CaptureManager(SubAgentManager):
        def spawn_and_collect_all(
            self,
            tasks: list[SubAgentTask],
            session_id: str = "",
        ) -> list[SubAgentResult]:
            calls.append([task.goal for task in tasks])
            return [
                SubAgentResult(
                    task_index=index,
                    goal=task.goal,
                    tool=task.tool,
                    status="success",
                    message="done",
                )
                for index, task in enumerate(tasks)
            ]

    orchestrator = Orchestrator(manager=CaptureManager())
    orchestrator.add_task("0", "source", "source_tool")
    orchestrator.add_task(
        "1",
        "consumer",
        "consumer_tool",
        args={"path": "$step_0"},
    )
    result = orchestrator.run_all()

    _assert_equal(calls, [["source"]])
    _assert_equal([item["task_id"] for item in result["completed"]], ["0"])
    _assert_equal([item["task_id"] for item in result["blocked"]], ["1"])
    _assert("未声明依赖" in result["blocked"][0]["reason"])


def test_racing_returns_first_success() -> None:
    import app.agent.racing_executor as module

    module.TOOL_REGISTRY["fast"] = lambda: None
    module.TOOL_REGISTRY["slow"] = lambda: None

    def fake_runner(**kwargs: Any) -> Any:
        time.sleep(0.03 if kwargs["tool_name"] == "fast" else 0.35)
        return make_success_result(kwargs["tool_name"])

    restore = _patched(module, "run_tool_with_lifecycle", fake_runner)
    try:
        started = time.monotonic()
        result = module.race_tools(["fast", "slow"], {}, timeout=2)
        elapsed = time.monotonic() - started
    finally:
        restore()
        module.TOOL_REGISTRY.pop("fast", None)
        module.TOOL_REGISTRY.pop("slow", None)

    _assert_equal(result.winner_tool_name, "fast")
    _assert(elapsed < 0.2, f"race returned too late: {elapsed:.3f}s")
    _assert(not result.all_completed)


def test_racing_filters_incompatible_signatures() -> None:
    import app.agent.racing_executor as module

    module.TOOL_REGISTRY["uses_a"] = lambda a: a
    module.TOOL_REGISTRY["uses_b"] = lambda b: b
    module.TOOL_META["uses_a"] = {"racing_group": "demo"}
    module.TOOL_META["uses_b"] = {"racing_group": "demo"}
    try:
        candidates = module.get_compatible_racing_candidates(
            "uses_a",
            {"uses_a", "uses_b"},
            {"a": 1},
        )
    finally:
        module.TOOL_REGISTRY.pop("uses_a", None)
        module.TOOL_REGISTRY.pop("uses_b", None)
        module.TOOL_META.pop("uses_a", None)
        module.TOOL_META.pop("uses_b", None)

    _assert_equal(candidates, ["uses_a"])


def test_async_entry_does_not_block_event_loop() -> None:
    import app.agent.bio_agent as module

    def slow_sync(*args: Any, **kwargs: Any) -> dict:
        time.sleep(0.15)
        return {"answer": "ok", "files": []}

    async def scenario() -> tuple[dict, float]:
        restore = _patched(module, "_run_bio_agent_sync", slow_sync)
        started = time.monotonic()
        try:
            task = asyncio.create_task(module.run_bio_agent([]))
            await asyncio.sleep(0.02)
            tick_elapsed = time.monotonic() - started
            return await task, tick_elapsed
        finally:
            restore()

    result, tick_elapsed = asyncio.run(scenario())
    _assert_equal(result["answer"], "ok")
    _assert(tick_elapsed < 0.1, f"event loop was blocked: {tick_elapsed:.3f}s")


if __name__ == "__main__":
    tests = [
        value for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    failures = []
    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
        except Exception as exc:
            failures.append((test.__name__, exc))
            print(f"[FAIL] {test.__name__}: {exc}")
    print(f"Results: {len(tests) - len(failures)} passed, {len(failures)} failed")
    if failures:
        raise SystemExit(1)
