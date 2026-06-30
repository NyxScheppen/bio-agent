"""
Phase 2: Tool Lifecycle Unit Tests.

Run:
    cd D:/Desktop/bio_test
    .venv/Scripts/python.exe backend/tests/test_tool_lifecycle.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _assert(condition, msg=""):
    if not condition:
        raise AssertionError(f"FAIL: {msg}" if msg else "FAIL")


def _assert_equal(a, b, msg=""):
    _assert(a == b, f"{msg}: expected {b!r}, got {a!r}")


def _assert_in(item, container, msg=""):
    _assert(item in container, f"{msg}: {item!r} not in {container!r}")


# ============================================================
# test_create_tool_context
# ============================================================

def test_create_tool_context():
    """创建 ToolExecutionContext 并验证字段。"""
    from app.agent.tool_context import create_tool_context, ToolExecutionContext

    ctx = create_tool_context(
        tool_name="test_tool",
        session_id="session_abc",
        parameters={"file_path": "data.csv", "threshold": 0.05},
        tool_category="survival",
    )
    _assert_equal(ctx.tool_name, "test_tool")
    _assert_equal(ctx.tool_category, "survival")
    _assert_equal(ctx.session_id, "session_abc")
    _assert_equal(ctx.parameters.get("file_path"), "data.csv")
    _assert(ctx.job_id is not None and len(ctx.job_id) > 0, "job_id should not be empty")
    _assert(ctx.job_dir is not None and len(ctx.job_dir) > 0, "job_dir should not be empty")
    _assert(Path(ctx.job_dir).exists(), f"job_dir should exist: {ctx.job_dir}")
    _assert(ctx.started_at is not None, "started_at should be set")
    _assert("generated" in ctx.job_dir.lower() or "generated" in str(ctx.job_dir), f"job_dir should be under generated: {ctx.job_dir}")

    print("[PASS] test_create_tool_context")


def test_create_tool_context_no_session():
    """无 session_id 时也能正常创建。"""
    from app.agent.tool_context import create_tool_context

    ctx = create_tool_context(tool_name="standalone", parameters={})
    _assert_equal(ctx.session_id, "")
    _assert(ctx.job_id.startswith("standalone_"), f"job_id should start with tool_name: {ctx.job_id}")
    _assert(Path(ctx.job_dir).exists())

    print("[PASS] test_create_tool_context_no_session")


def test_create_tool_context_job_dir_unique():
    """两个 context 应有不同的 job_id 和 job_dir。"""
    from app.agent.tool_context import create_tool_context

    ctx1 = create_tool_context(tool_name="tool_a")
    ctx2 = create_tool_context(tool_name="tool_a")

    _assert(ctx1.job_id != ctx2.job_id, "job_ids should be unique")
    _assert(ctx1.job_dir != ctx2.job_dir, "job_dirs should be unique")

    print("[PASS] test_create_tool_context_job_dir_unique")


# ============================================================
# test_run_tool_with_lifecycle_success
# ============================================================

def test_run_tool_with_lifecycle_success():
    """正常工具执行应返回 success ToolResult。"""
    from app.agent.tool_runner import run_tool_with_lifecycle
    from app.agent.tool_result import ToolResult

    def my_tool(file_path: str, threshold: float = 0.05):
        return {
            "status": "success",
            "message": "分析完成",
            "output_files": [
                {"name": "result.csv", "relative_path": "generated/x/result.csv"}
            ],
            "up_genes": 150,
            "down_genes": 80,
        }

    result = run_tool_with_lifecycle(
        tool_name="my_tool",
        func=my_tool,
        function_args={"file_path": "data.csv", "threshold": 0.05},
        session_id="test_session",
    )

    _assert(isinstance(result, ToolResult), f"Expected ToolResult, got {type(result)}")
    _assert_equal(result.status, "success")
    _assert_equal(result.message, "分析完成")
    _assert_equal(len(result.output_files), 1)
    _assert_equal(result.output_files[0].name, "result.csv")
    _assert_equal(result.provenance.tool_name, "my_tool")
    _assert(result.provenance.runtime_seconds is not None, "runtime should be set")
    _assert(result.provenance.runtime_seconds >= 0, "runtime should be >= 0")
    _assert(result.provenance.started_at is not None)
    _assert(result.provenance.finished_at is not None)
    _assert_equal(result.summary.get("up_genes"), 150)
    _assert_equal(result.summary.get("down_genes"), 80)
    # job_id / job_dir 应被注入到 summary
    _assert("job_id" in result.summary)
    _assert("job_dir" in result.summary)

    print("[PASS] test_run_tool_with_lifecycle_success")


def test_run_tool_with_lifecycle_injects_job_dir():
    """工具函数接受 job_dir 参数时应自动注入。"""
    from app.agent.tool_runner import run_tool_with_lifecycle

    received_job_dir = []

    def my_tool(file_path: str, job_dir: str = ""):
        received_job_dir.append(job_dir)
        return {"status": "success"}

    result = run_tool_with_lifecycle(
        tool_name="inject_test",
        func=my_tool,
        function_args={"file_path": "x.csv"},
        session_id="s1",
    )

    _assert_equal(result.status, "success")
    _assert(len(received_job_dir) == 1, "job_dir should be injected")
    _assert(received_job_dir[0] != "", "injected job_dir should not be empty")
    _assert(Path(received_job_dir[0]).exists(), "injected job_dir should exist")

    print("[PASS] test_run_tool_with_lifecycle_injects_job_dir")


def test_run_tool_with_lifecycle_injects_session_id():
    """工具函数接受 session_id 参数时应自动注入。"""
    from app.agent.tool_runner import run_tool_with_lifecycle

    received_sid = []

    def my_tool(file_path: str, session_id: str = ""):
        received_sid.append(session_id)
        return {"status": "success"}

    result = run_tool_with_lifecycle(
        tool_name="sid_test",
        func=my_tool,
        function_args={"file_path": "x.csv"},
        session_id="abc123",
    )

    _assert_equal(result.status, "success")
    _assert_equal(received_sid[0], "abc123")

    print("[PASS] test_run_tool_with_lifecycle_injects_session_id")


# ============================================================
# test_run_tool_with_lifecycle_error
# ============================================================

def test_run_tool_with_lifecycle_error():
    """工具抛出异常应返回 error ToolResult。"""
    from app.agent.tool_runner import run_tool_with_lifecycle
    from app.agent.tool_result import ToolResult

    def failing_tool():
        raise RuntimeError("something went wrong")

    result = run_tool_with_lifecycle(
        tool_name="failing_tool",
        func=failing_tool,
        function_args={},
        session_id=None,
    )

    _assert(isinstance(result, ToolResult))
    _assert_equal(result.status, "error")
    _assert("something went wrong" in result.message or any("something went wrong" in e for e in result.errors))
    _assert(result.provenance.tool_name == "failing_tool")
    _assert(result.provenance.runtime_seconds is not None)

    print("[PASS] test_run_tool_with_lifecycle_error")


def test_run_tool_with_lifecycle_error_dict():
    """工具返回 error status dict 应正确转换。"""
    from app.agent.tool_runner import run_tool_with_lifecycle

    def error_tool(**kwargs):
        return {
            "status": "error",
            "message": "找不到文件",
            "stderr": "No such file: data.csv",
        }

    result = run_tool_with_lifecycle(
        tool_name="error_tool",
        func=error_tool,
        function_args={"file_path": "data.csv"},
        session_id="s1",
    )

    _assert_equal(result.status, "error")
    _assert_equal(result.message, "找不到文件")
    _assert(len(result.errors) > 0)

    print("[PASS] test_run_tool_with_lifecycle_error_dict")


# ============================================================
# test_collect_generated_files
# ============================================================

def test_collect_generated_files():
    """扫描 job_dir 中生成的文件。"""
    from app.agent.tool_runner import collect_generated_files

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建一些文件
        (Path(tmpdir) / "result.csv").write_text("a,b,c\n1,2,3")
        (Path(tmpdir) / "plot.png").write_text("fake png")
        (Path(tmpdir) / "heatmap.jpg").write_text("fake jpg")
        (Path(tmpdir) / "notes.md").write_text("markdown")  # 不应被收集
        (Path(tmpdir) / "data.rds").write_bytes(b"r binary")

        # 子目录
        sub = Path(tmpdir) / "subdir"
        sub.mkdir()
        (sub / "nested.pdf").write_text("pdf")

        files = collect_generated_files(tmpdir)

        # 应该收集 csv, png, jpg, rds, pdf
        names = {f["name"] for f in files}
        _assert_in("result.csv", names)
        _assert_in("plot.png", names)
        _assert_in("heatmap.jpg", names)
        _assert_in("data.rds", names)
        _assert_in("nested.pdf", names)  # 递归
        # notes.md 不应被收集
        _assert("notes.md" not in names)

        # 检查字段格式
        for f in files:
            _assert("name" in f)
            _assert("url" in f)
            _assert("relative_path" in f)
            _assert("size_bytes" in f or f.get("size_bytes") is not None)

    print("[PASS] test_collect_generated_files")


def test_collect_generated_files_empty():
    """空目录返回空列表。"""
    from app.agent.tool_runner import collect_generated_files

    with tempfile.TemporaryDirectory() as tmpdir:
        files = collect_generated_files(tmpdir)
        _assert_equal(len(files), 0)

    print("[PASS] test_collect_generated_files_empty")


def test_collect_generated_files_nonexistent():
    """不存在的目录返回空列表。"""
    from app.agent.tool_runner import collect_generated_files

    files = collect_generated_files("/nonexistent/path/xyz")
    _assert_equal(len(files), 0)

    print("[PASS] test_collect_generated_files_nonexistent")


# ============================================================
# test_lifecycle_auto_file_collection
# ============================================================

def test_lifecycle_auto_file_collection():
    """
    工具在 job_dir 中创建文件但未显式返回 output_files 时，
    生命周期应自动扫描并添加到 ToolResult。
    """
    from app.agent.tool_runner import run_tool_with_lifecycle

    def lazy_tool(job_dir: str = ""):
        # 在 job_dir 中写入文件但不返回 output_files
        if job_dir:
            (Path(job_dir) / "analysis.csv").write_text("x,y\n1,2")
            (Path(job_dir) / "figure.png").write_text("chart")
        return {"status": "success", "message": "done"}  # 无 output_files

    result = run_tool_with_lifecycle(
        tool_name="lazy_tool",
        func=lazy_tool,
        function_args={},
        session_id="auto_collect_test",
    )

    _assert_equal(result.status, "success")
    # 应自动收集到 analysis.csv 和 figure.png
    names = {f.name for f in result.output_files}
    _assert_in("analysis.csv", names, "should auto-collect analysis.csv")
    _assert_in("figure.png", names, "should auto-collect figure.png")

    print("[PASS] test_lifecycle_auto_file_collection")


def test_lifecycle_merge_no_duplicates():
    """
    如果工具显式返回 output_files 且生命周期也收集到同名文件，
    不应重复。
    """
    from app.agent.tool_runner import run_tool_with_lifecycle

    def explicit_tool(job_dir: str = ""):
        if job_dir:
            (Path(job_dir) / "result.csv").write_text("a,b\n1,2")
        return {
            "status": "success",
            "output_files": [
                {"name": "result.csv", "relative_path": "generated/xyz/result.csv"}
            ],
        }

    result = run_tool_with_lifecycle(
        tool_name="explicit_tool",
        func=explicit_tool,
        function_args={},
        session_id="dedup_test",
    )

    csv_files = [f for f in result.output_files if f.name == "result.csv"]
    _assert_equal(len(csv_files), 1, "result.csv should not be duplicated")

    print("[PASS] test_lifecycle_merge_no_duplicates")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2: Tool Lifecycle Unit Tests")
    print("=" * 60)

    tests = [
        ("test_create_tool_context", test_create_tool_context),
        ("test_create_tool_context_no_session", test_create_tool_context_no_session),
        ("test_create_tool_context_job_dir_unique", test_create_tool_context_job_dir_unique),
        ("test_run_tool_with_lifecycle_success", test_run_tool_with_lifecycle_success),
        ("test_run_tool_with_lifecycle_injects_job_dir", test_run_tool_with_lifecycle_injects_job_dir),
        ("test_run_tool_with_lifecycle_injects_session_id", test_run_tool_with_lifecycle_injects_session_id),
        ("test_run_tool_with_lifecycle_error", test_run_tool_with_lifecycle_error),
        ("test_run_tool_with_lifecycle_error_dict", test_run_tool_with_lifecycle_error_dict),
        ("test_collect_generated_files", test_collect_generated_files),
        ("test_collect_generated_files_empty", test_collect_generated_files_empty),
        ("test_collect_generated_files_nonexistent", test_collect_generated_files_nonexistent),
        ("test_lifecycle_auto_file_collection", test_lifecycle_auto_file_collection),
        ("test_lifecycle_merge_no_duplicates", test_lifecycle_merge_no_duplicates),
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
