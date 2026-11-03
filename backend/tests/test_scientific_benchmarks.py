"""
生信数值正确性基准测试（Known-Result Benchmarks）。

目的：用「已知结果的确定性计算」验证工具链的数值正确性，弥补「管道测试只验流程、
不验数值」的短板——这是回答 iGEM 评委「你的测试测管道还是数值」的直接证据。

范围说明：本仓库的 R 分析（DESeq2 / limma / 生存分析等）遵循 CLAUDE.md 约定，不在
自动测试里依赖真实 R / 真实文件系统；其数值正确性按 docs/README_FEATURE_VERIFICATION.md
用已知数据集人工验证。这里覆盖的是纯 Python、无外部依赖的确定性计算核心。

运行：
    cd path/to/bio_test
    .venv/Scripts/python.exe backend/tests/test_scientific_benchmarks.py
    # 或在 pytest 下随全量测试一起运行
"""

import json
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


def test_gc_content_v1_all_gc():
    """GC 含量：全 GC 序列应为 100.0。"""
    from app.tools.basic_tools import calculate_gc_content

    result = json.loads(calculate_gc_content("GCGC"))
    _assert_equal(result["status"], "success")
    _assert_equal(result["gc_content_percentage"], 100.0)


def test_gc_content_v1_mixed():
    """GC 含量：GCGCATAT 含 4 个 GC、共 8 碱基，应为 50.0。"""
    from app.tools.basic_tools import calculate_gc_content

    result = json.loads(calculate_gc_content("GCGCATAT"))
    _assert_equal(result["gc_content_percentage"], 50.0)


def test_gc_content_v2_known():
    """GC 含量 v2：ATGC 含 2 个 GC、共 4 碱基，应为 50.0。"""
    from app.tools.example_pydantic_tool import calculate_gc_content_v2

    result = calculate_gc_content_v2("ATGC")
    _assert_equal(result["status"], "success")
    _assert_equal(result["summary"]["gc_count"], 2)
    _assert_equal(result["summary"]["total_bases"], 4)
    _assert_equal(result["summary"]["gc_content"], 50.0)


def test_count_sequence_bases_known():
    """碱基统计：AATTGGCC 各 2 个，总量 8。"""
    from app.tools.example_pydantic_tool import count_sequence_bases

    result = count_sequence_bases("AATTGGCC")
    _assert_equal(result["summary"]["total"], 8)
    _assert_equal(
        result["summary"]["counts"],
        {"A": 2, "T": 2, "G": 2, "C": 2, "U": 0},
    )


def test_reverse_complement_known():
    """反向互补：ATGC 的互补序列（读序反转后取补）为 GCAT。"""
    from app.tools.example_pydantic_tool import reverse_complement_v2

    result = reverse_complement_v2("ATGC")
    _assert_equal(result["summary"]["length"], 4)
    _assert_equal(result["summary"]["result"], "GCAT")


if __name__ == "__main__":
    print("=" * 60)
    print("Scientific numerical benchmarks")
    print("=" * 60)

    tests = [
        ("test_gc_content_v1_all_gc", test_gc_content_v1_all_gc),
        ("test_gc_content_v1_mixed", test_gc_content_v1_mixed),
        ("test_gc_content_v2_known", test_gc_content_v2_known),
        ("test_count_sequence_bases_known", test_count_sequence_bases_known),
        ("test_reverse_complement_known", test_reverse_complement_known),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"[PASS] {name}")
        except Exception as e:
            failed += 1
            print(f"[FAIL] {name}: {e}")

    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed > 0:
        sys.exit(1)