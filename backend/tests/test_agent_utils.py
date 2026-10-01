"""
Phase 2: 重复逻辑合并 — to_plain_dict / result_status / is_error_result 单元测试。

运行方式（在 backend 目录下）：
    python -m pytest tests/test_agent_utils.py -v

或（不依赖 pytest）：
    python tests/test_agent_utils.py
"""

import sys
from pathlib import Path

# 确保 backend 在 sys.path 中
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import BaseModel

from app.agent.agent_utils import to_plain_dict, result_status, is_error_result


# ============================================================
# 辅助断言
# ============================================================

def _assert(condition, msg=""):
    if not condition:
        raise AssertionError(f"FAIL: {msg}" if msg else "FAIL")


def _assert_equal(a, b, msg=""):
    _assert(a == b, f"{msg}: expected {b!r}, got {a!r}")


# ============================================================
# 测试夹具对象
# ============================================================

class _V2Model(BaseModel):
    """pydantic v2 模型，暴露 model_dump()。"""
    status: str = "success"
    name: str = "x"


class _V1Like:
    """仅暴露 dict() 的旧式对象。"""

    def dict(self):
        return {"status": "error", "legacy": True}


class _Plain:
    """既无 model_dump 也无 dict 的普通对象。"""
    pass


class _WithStatus:
    """带 status 属性的普通对象。"""

    def __init__(self):
        self.status = "ERROR"


# ============================================================
# to_plain_dict
# ============================================================

def test_to_plain_dict():
    """dict / pydantic v2 / v1 风格对象均解包为普通 dict。"""
    d = {"a": 1}
    _assert(to_plain_dict(d) is d, "dict 应原样返回")
    _assert_equal(to_plain_dict(_V2Model()), {"status": "success", "name": "x"})
    _assert_equal(to_plain_dict(_V1Like()), {"status": "error", "legacy": True})
    print("[PASS] test_to_plain_dict")


def test_to_plain_dict_edge_cases():
    """None / 普通对象 / 标量均应返回 None。"""
    _assert(to_plain_dict(None) is None)
    _assert(to_plain_dict(_Plain()) is None)
    _assert(to_plain_dict("text") is None)
    _assert(to_plain_dict(42) is None)
    print("[PASS] test_to_plain_dict_edge_cases")


# ============================================================
# result_status
# ============================================================

def test_result_status_dict():
    """从 dict 读取 status 字段并小写。"""
    _assert_equal(result_status({"status": "success"}), "success")
    _assert_equal(result_status({"status": "ERROR"}), "error")
    _assert_equal(result_status({"message": "ok"}), "")
    _assert_equal(result_status({"status": None}), "")
    print("[PASS] test_result_status_dict")


def test_result_status_objects():
    """从对象属性读取 status，无 status 或 None 时返回空串。"""
    _assert_equal(result_status(_WithStatus()), "error")
    _assert_equal(result_status(_Plain()), "")
    _assert_equal(result_status(None), "")
    print("[PASS] test_result_status_objects")


# ============================================================
# is_error_result
# ============================================================

def test_is_error_result():
    """仅 status == error（大小写不敏感）时为 True。"""
    _assert(is_error_result({"status": "error"}))
    _assert(is_error_result({"status": "ERROR"}))
    _assert(not is_error_result({"status": "success"}))
    _assert(not is_error_result(None))
    print("[PASS] test_is_error_result")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2: AgentUtils Primitives Unit Tests")
    print("=" * 60)

    tests = [
        ("test_to_plain_dict", test_to_plain_dict),
        ("test_to_plain_dict_edge_cases", test_to_plain_dict_edge_cases),
        ("test_result_status_dict", test_result_status_dict),
        ("test_result_status_objects", test_result_status_objects),
        ("test_is_error_result", test_is_error_result),
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
