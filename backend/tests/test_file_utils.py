"""
Phase 2: 重复逻辑合并 — build_file_url 单元测试。

运行方式（在 backend 目录下）：
    python -m pytest tests/test_file_utils.py -v

或（不依赖 pytest）：
    python tests/test_file_utils.py
"""

import sys
from pathlib import Path

# 确保 backend 在 sys.path 中
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.file_utils import build_file_url


# ============================================================
# 辅助断言
# ============================================================

def _assert_equal(a, b, msg=""):
    if a != b:
        raise AssertionError(f"FAIL: {msg}: expected {b!r}, got {a!r}")


# ============================================================
# build_file_url
# ============================================================

def test_build_file_url_basic():
    """相对路径拼接为 /files/ 前缀 URL。"""
    _assert_equal(build_file_url("generated/abc/a.png"), "/files/generated/abc/a.png")
    _assert_equal(build_file_url("uploads/s/1.csv"), "/files/uploads/s/1.csv")
    print("[PASS] test_build_file_url_basic")


def test_build_file_url_normalization():
    """反斜杠归一为正斜杠，前导斜杠被去掉。"""
    _assert_equal(build_file_url("generated\\abc\\a.png"), "/files/generated/abc/a.png")
    _assert_equal(build_file_url("/generated/abc"), "/files/generated/abc")
    _assert_equal(build_file_url("/generated\\abc"), "/files/generated/abc")
    print("[PASS] test_build_file_url_normalization")


def test_build_file_url_edge_cases():
    """空路径 / 纯斜杠路径的边界行为。"""
    _assert_equal(build_file_url(""), "/files/")
    _assert_equal(build_file_url("/"), "/files/")
    print("[PASS] test_build_file_url_edge_cases")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2: FileUtils Unit Tests")
    print("=" * 60)

    tests = [
        ("test_build_file_url_basic", test_build_file_url_basic),
        ("test_build_file_url_normalization", test_build_file_url_normalization),
        ("test_build_file_url_edge_cases", test_build_file_url_edge_cases),
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
