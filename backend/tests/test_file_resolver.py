"""
Phase: 安全加固 — resolve_file_path 路径穿越 containment 回归测试。

运行方式（在 backend 目录下）：
    python -m pytest tests/test_file_resolver.py -v

或（不依赖 pytest）：
    python tests/test_file_resolver.py
"""

import sys
from pathlib import Path

# 确保 backend 在 sys.path 中
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.file_resolver import resolve_file_path, STORAGE_DIR


# ============================================================
# 辅助断言
# ============================================================

def _assert(condition, msg=""):
    if not condition:
        raise AssertionError(f"FAIL: {msg}" if msg else "FAIL")


def _assert_equal(a, b, msg=""):
    _assert(a == b, f"{msg}: expected {b!r}, got {a!r}")


# ============================================================
# 测试用例
# ============================================================

def test_resolve_uploads_inside_storage():
    """uploads/ 前缀应解析到 storage 内，不被 containment 误拦。"""
    p = resolve_file_path("uploads/test.csv")
    _assert(p is not None, "uploads 路径不应被拦截")
    _assert_equal(p, STORAGE_DIR / "uploads" / "test.csv")


def test_resolve_generated_inside_storage():
    """generated/ 前缀应解析到 storage 内。"""
    p = resolve_file_path("generated/abc/plot.png")
    _assert(p is not None, "generated 路径不应被拦截")
    _assert_equal(p, STORAGE_DIR / "generated" / "abc" / "plot.png")


def test_resolve_traversal_blocked():
    """../.env 相对路径穿越应返回 None（文件不存在哨兵）。"""
    p = resolve_file_path("../.env")
    _assert(p is None, "路径穿越应被拦截")


def test_resolve_absolute_outside_blocked():
    """storage 外的绝对路径（backend/.env）应被拦截。"""
    p = resolve_file_path(str(BACKEND_DIR / ".env"))
    _assert(p is None, "storage 外绝对路径应被拦截")


def test_resolve_absolute_inside_storage_ok():
    """storage 内的绝对路径应放行。"""
    inside = STORAGE_DIR / "generated" / "x" / "a.png"
    p = resolve_file_path(str(inside))
    _assert(p is not None, "storage 内绝对路径不应被拦截")
    _assert_equal(p, inside)


def test_resolve_empty_returns_none():
    """空输入应返回 None。"""
    p = resolve_file_path("")
    _assert(p is None, "空输入应返回 None")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    tests = [
        ("test_resolve_uploads_inside_storage", test_resolve_uploads_inside_storage),
        ("test_resolve_generated_inside_storage", test_resolve_generated_inside_storage),
        ("test_resolve_traversal_blocked", test_resolve_traversal_blocked),
        ("test_resolve_absolute_outside_blocked", test_resolve_absolute_outside_blocked),
        ("test_resolve_absolute_inside_storage_ok", test_resolve_absolute_inside_storage_ok),
        ("test_resolve_empty_returns_none", test_resolve_empty_returns_none),
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

    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)} tests")

    if failed > 0:
        sys.exit(1)
