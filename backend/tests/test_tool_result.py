"""
Phase 1: ToolResult 统一工具返回格式 单元测试。

运行方式（在 backend 目录下）：
    python -m pytest tests/test_tool_result.py -v

或（不依赖 pytest）：
    python tests/test_tool_result.py
"""

import json
import sys
from pathlib import Path

# 确保 backend 在 sys.path 中
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent.tool_result import (
    OutputFile,
    ResultTable,
    ResultFigure,
    ToolProvenance,
    ToolResult,
    make_tool_result,
    make_success_result,
    make_error_result,
    normalize_tool_result,
    tool_result_to_legacy_dict,
    _coerce_output_file,
)


# ============================================================
# 辅助断言
# ============================================================

def _assert(condition, msg=""):
    """简单的断言辅助，兼容无 pytest 环境。"""
    if not condition:
        raise AssertionError(f"FAIL: {msg}" if msg else "FAIL")


def _assert_equal(a, b, msg=""):
    _assert(a == b, f"{msg}: expected {b}, got {a}")


# ============================================================
# test_normalize_tool_result_from_dict
# ============================================================

def test_normalize_tool_result_from_dict():
    """从普通 dict 归一化（有 status 字段）。"""
    raw = {
        "status": "success",
        "message": "分析完成",
        "output_files": [
            {"name": "result.csv", "url": "/files/generated/abc/result.csv",
             "relative_path": "generated/abc/result.csv", "size_bytes": 1024}
        ],
        "job_id": "job_001",
    }
    tr = normalize_tool_result(raw, tool_name="test_tool", tool_category="general")
    _assert_equal(tr.status, "success")
    _assert_equal(tr.message, "分析完成")
    _assert_equal(len(tr.output_files), 1)
    _assert_equal(tr.output_files[0].name, "result.csv")
    _assert_equal(tr.output_files[0].size_bytes, 1024)
    _assert_equal(tr.provenance.tool_name, "test_tool")
    _assert_equal(tr.provenance.tool_category, "general")
    print("[PASS] test_normalize_tool_result_from_dict")


def test_normalize_tool_result_no_status():
    """dict 没有 status 字段，应视为 success。"""
    raw = {
        "columns": 10,
        "rows": 100,
        "output_files": [{"name": "heatmap.png", "url": "/files/generated/x/heatmap.png"}],
    }
    tr = normalize_tool_result(raw, tool_name="preview_tool")
    _assert_equal(tr.status, "success")
    _assert_equal(tr.output_files[0].name, "heatmap.png")
    # columns/rows 应迁移到 summary
    _assert_equal(tr.summary.get("columns"), 10)
    _assert_equal(tr.summary.get("rows"), 100)
    print("[PASS] test_normalize_tool_result_no_status")


def test_normalize_tool_result_error():
    """dict 有 status: error。"""
    raw = {
        "status": "error",
        "message": "找不到文件",
        "stderr": "Error in file: No such file or directory",
    }
    tr = normalize_tool_result(raw, tool_name="file_read")
    _assert_equal(tr.status, "error")
    _assert_equal(tr.message, "找不到文件")
    _assert(len(tr.errors) > 0)
    print("[PASS] test_normalize_tool_result_error")


# ============================================================
# test_normalize_tool_result_from_json_string
# ============================================================

def test_normalize_tool_result_from_json_string():
    """JSON 字符串应被解析为 dict 再归一化。"""
    raw = json.dumps({
        "status": "success",
        "message": "JSON 字符串返回",
        "output_files": [{"name": "plot.png", "url": "/files/generated/xyz/plot.png"}],
    })
    tr = normalize_tool_result(raw, tool_name="json_tool")
    _assert_equal(tr.status, "success")
    _assert_equal(tr.message, "JSON 字符串返回")
    _assert_equal(len(tr.output_files), 1)
    _assert_equal(tr.output_files[0].name, "plot.png")
    print("[PASS] test_normalize_tool_result_from_json_string")


def test_normalize_tool_result_json_error_string():
    """JSON 字符串表示错误。"""
    raw = json.dumps({"status": "error", "message": "R 崩溃", "stderr": "segmentation fault"})
    tr = normalize_tool_result(raw, tool_name="r_tool")
    _assert_equal(tr.status, "error")
    _assert_equal(tr.message, "R 崩溃")
    _assert(len(tr.errors) > 0)
    print("[PASS] test_normalize_tool_result_json_error_string")


# ============================================================
# test_normalize_tool_result_extract_output_files
# ============================================================

def test_normalize_tool_result_extract_output_files():
    """确保 output_files 被正确提取。"""
    raw = {
        "status": "success",
        "output_files": [
            {"name": "a.csv", "url": "/files/g/a.csv"},
            {"name": "b.png", "url": "/files/g/b.png", "type": "image", "size_bytes": 2048},
            {"name": "c.pdf", "url": "/files/g/c.pdf"},
        ],
    }
    tr = normalize_tool_result(raw, tool_name="multi_output")
    _assert_equal(len(tr.output_files), 3)
    names = {f.name for f in tr.output_files}
    _assert("a.csv" in names)
    _assert("b.png" in names)
    _assert("c.pdf" in names)

    # 检查 type 推断
    csv_file = [f for f in tr.output_files if f.name == "a.csv"][0]
    _assert_equal(csv_file.file_type, "table")

    png_file = [f for f in tr.output_files if f.name == "b.png"][0]
    _assert_equal(png_file.file_type, "image")
    _assert_equal(png_file.size_bytes, 2048)

    pdf_file = [f for f in tr.output_files if f.name == "c.pdf"][0]
    _assert_equal(pdf_file.file_type, "pdf")
    print("[PASS] test_normalize_tool_result_extract_output_files")


def test_normalize_tool_result_empty_output_files():
    """无 output_files 时为空列表。"""
    raw = {"status": "success", "message": "ok"}
    tr = normalize_tool_result(raw, tool_name="no_output")
    _assert_equal(tr.status, "success")
    _assert_equal(len(tr.output_files), 0)
    print("[PASS] test_normalize_tool_result_empty_output_files")


# ============================================================
# test_make_error_result
# ============================================================

def test_make_error_result():
    """测试 make_error_result 快捷构造。"""
    tr = make_error_result(
        message="执行超时",
        errors=["timeout after 300s", "partial output may exist"],
    )
    _assert_equal(tr.status, "error")
    _assert_equal(tr.message, "执行超时")
    _assert_equal(len(tr.errors), 2)
    _assert("timeout after 300s" in tr.errors)
    print("[PASS] test_make_error_result")


def test_make_error_result_single_error():
    """单条错误时自动填充 errors。"""
    tr = make_error_result(message="Rscript not found")
    _assert_equal(tr.status, "error")
    _assert_equal(tr.errors[0], "Rscript not found")
    print("[PASS] test_make_error_result_single_error")


# ============================================================
# test_make_success_result
# ============================================================

def test_make_success_result():
    """测试 make_success_result。"""
    tr = make_success_result(
        message="差异分析完成",
        output_files=[{"name": "deg.csv", "url": "/files/g/deg.csv"}],
        summary={"up": 150, "down": 80},
    )
    _assert_equal(tr.status, "success")
    _assert_equal(tr.message, "差异分析完成")
    _assert_equal(len(tr.output_files), 1)
    _assert_equal(tr.summary.get("up"), 150)
    _assert_equal(tr.summary.get("down"), 80)
    print("[PASS] test_make_success_result")


# ============================================================
# test_normalize_tool_result_with_automatic_recovery
# ============================================================

def test_normalize_tool_result_with_automatic_recovery():
    """Executor 创建的 automatic_recovery 包装应被正确处理。"""
    raw = {
        "original_tool_result": {
            "status": "error",
            "message": "R 执行报错: there is no package called 'survival'",
            "stderr": "Error in library(survival): there is no package called 'survival'",
        },
        "automatic_recovery": [
            {"recovery_tool": "scan_system_config", "result": {"rscript": "/usr/bin/Rscript"}}
        ],
    }
    tr = normalize_tool_result(raw, tool_name="test_tool")
    _assert_equal(tr.status, "error")
    # warnings 中应有恢复信息
    _assert(len(tr.warnings) > 0)
    recovery_text = " ".join(tr.warnings)
    _assert("scan_system_config" in recovery_text)
    print("[PASS] test_normalize_tool_result_with_automatic_recovery")


# ============================================================
# test_normalize_tool_result_already_toolresult
# ============================================================

def test_normalize_tool_result_already_toolresult():
    """已经是 ToolResult 对象时，应直接返回并补充 provenance。"""
    tr1 = make_success_result(message="already done")
    _assert_equal(tr1.provenance.tool_name, "")

    tr2 = normalize_tool_result(tr1, tool_name="outer_tool", tool_category="survival")
    _assert_equal(tr2.status, "success")
    _assert_equal(tr2.message, "already done")
    _assert_equal(tr2.provenance.tool_name, "outer_tool")
    _assert_equal(tr2.provenance.tool_category, "survival")
    # finished_at 应被填充
    _assert(tr2.provenance.finished_at is not None)
    print("[PASS] test_normalize_tool_result_already_toolresult")


# ============================================================
# test_normalize_tool_result_list_input
# ============================================================

def test_normalize_tool_result_list_input():
    """list 类型输入应包装成 ToolResult。"""
    raw = [
        {"name": "file1.csv", "url": "/files/g/file1.csv"},
        {"name": "file2.png", "url": "/files/g/file2.png"},
    ]
    tr = normalize_tool_result(raw, tool_name="list_tool")
    _assert_equal(tr.status, "success")
    _assert_equal(len(tr.output_files), 2)
    _assert_equal(tr.summary.get("item_count"), 2)
    print("[PASS] test_normalize_tool_result_list_input")


# ============================================================
# test_coerce_output_file
# ============================================================

def test_coerce_output_file():
    """_coerce_output_file 应处理多种字段变体。"""
    # path → relative_path
    of = _coerce_output_file({"name": "f.csv", "path": "generated/abc/f.csv"})
    _assert_equal(of.relative_path, "generated/abc/f.csv")
    _assert("files/generated" in of.url or of.url == "/files/generated/abc/f.csv")

    # type → file_type
    of2 = _coerce_output_file({"name": "p.png", "url": "/files/p.png", "type": "image"})
    _assert_equal(of2.file_type, "image")

    # no name, infer from url
    of3 = _coerce_output_file({"url": "/files/generated/x/data.csv"})
    _assert_equal(of3.name, "data.csv")
    _assert_equal(of3.file_type, "table")

    print("[PASS] test_coerce_output_file")


# ============================================================
# test_tool_result_to_legacy_dict
# ============================================================

def test_tool_result_to_legacy_dict():
    """向后兼容：tool_result_to_legacy_dict 应返回旧格式。"""
    tr = make_success_result(
        message="OK",
        output_files=[{"name": "test.csv", "url": "/files/g/test.csv"}],
        warnings=["sample size small"],
    )
    legacy = tool_result_to_legacy_dict(tr)
    _assert(isinstance(legacy, dict))
    _assert_equal(legacy["status"], "success")
    _assert_equal(legacy["message"], "OK")
    _assert_equal(len(legacy["output_files"]), 1)
    _assert_equal(legacy["output_files"][0]["name"], "test.csv")
    _assert_equal(legacy["warnings"], ["sample size small"])
    print("[PASS] test_tool_result_to_legacy_dict")


# ============================================================
# test_provenance_fields
# ============================================================

def test_provenance_fields():
    """provenance 应包含 started_at 和 finished_at。"""
    tr = normalize_tool_result(
        {"status": "success"},
        tool_name="my_tool",
        tool_category="survival",
        started_at="2024-01-01T00:00:00",
    )
    _assert_equal(tr.provenance.tool_name, "my_tool")
    _assert_equal(tr.provenance.tool_category, "survival")
    _assert(tr.provenance.finished_at is not None, "finished_at should be populated")
    print("[PASS] test_provenance_fields")


# ============================================================
# test_normalize_plain_string
# ============================================================

def test_normalize_plain_string():
    """纯文本字符串应被包装。"""
    tr = normalize_tool_result("analysis done", tool_name="simple_tool")
    _assert_equal(tr.status, "success")
    _assert("analysis done" in tr.message)
    print("[PASS] test_normalize_plain_string")


# ============================================================
# test_normalize_none
# ============================================================

def test_normalize_none():
    """None 应返回 success 且空 message。"""
    tr = normalize_tool_result(None, tool_name="void_tool")
    _assert_equal(tr.status, "success")
    print("[PASS] test_normalize_none")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1: ToolResult Unit Tests")
    print("=" * 60)

    tests = [
        ("test_normalize_tool_result_from_dict", test_normalize_tool_result_from_dict),
        ("test_normalize_tool_result_no_status", test_normalize_tool_result_no_status),
        ("test_normalize_tool_result_error", test_normalize_tool_result_error),
        ("test_normalize_tool_result_from_json_string", test_normalize_tool_result_from_json_string),
        ("test_normalize_tool_result_json_error_string", test_normalize_tool_result_json_error_string),
        ("test_normalize_tool_result_extract_output_files", test_normalize_tool_result_extract_output_files),
        ("test_normalize_tool_result_empty_output_files", test_normalize_tool_result_empty_output_files),
        ("test_make_error_result", test_make_error_result),
        ("test_make_error_result_single_error", test_make_error_result_single_error),
        ("test_make_success_result", test_make_success_result),
        ("test_normalize_tool_result_with_automatic_recovery", test_normalize_tool_result_with_automatic_recovery),
        ("test_normalize_tool_result_already_toolresult", test_normalize_tool_result_already_toolresult),
        ("test_normalize_tool_result_list_input", test_normalize_tool_result_list_input),
        ("test_coerce_output_file", test_coerce_output_file),
        ("test_tool_result_to_legacy_dict", test_tool_result_to_legacy_dict),
        ("test_provenance_fields", test_provenance_fields),
        ("test_normalize_plain_string", test_normalize_plain_string),
        ("test_normalize_none", test_normalize_none),
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

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'=' * 60}")

    if failed > 0:
        sys.exit(1)
