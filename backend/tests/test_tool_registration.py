"""
Phase 3: Tool Registration Unit Tests.

Run:
    cd D:/Desktop/bio_test
    .venv/Scripts/python.exe backend/tests/test_tool_registration.py
"""

import json
import sys
from pathlib import Path
from typing import Optional

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
# test_register_tool_old_style
# ============================================================

def test_register_tool_old_style():
    """旧写法 register_tool 应正常工作。"""
    from app.agent.tool_registry import register_tool, TOOL_REGISTRY, TOOL_META, TOOLS_SCHEMA

    name = "_test_old_style"

    @register_tool(
        name=name,
        description="Old style test tool",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Input file"}
            },
            "required": ["file_path"]
        },
        category="file_io",
        tags=["test"],
    )
    def _test_old_style_func(file_path: str):
        return {"status": "success"}

    assert name in TOOL_REGISTRY
    meta = TOOL_META[name]
    _assert_equal(meta["category"], "file_io")
    _assert_equal(meta["schema_source"], "manual")
    _assert_equal(meta["tags"], ["test"])

    print("[PASS] test_register_tool_old_style")


# ============================================================
# test_register_tool_pydantic_model
# ============================================================

def test_register_tool_pydantic_model():
    """Pydantic params_model 应自动生成 OpenAI schema。"""
    from pydantic import BaseModel, Field
    from app.agent.tool_registry import register_tool, TOOL_REGISTRY, TOOL_META, TOOLS_SCHEMA

    class MyParams(BaseModel):
        gene: str = Field(description="Gene name")
        threshold: float = Field(default=0.05, description="P-value cutoff")
        top_n: int = Field(default=20)

    name = "_test_pydantic_model"

    @register_tool(
        name=name,
        description="Test pydantic model tool",
        category="survival",
        params_model=MyParams,
        tags=["pydantic"],
    )
    def _test_pydantic_model_func(gene: str, threshold: float = 0.05, top_n: int = 20):
        return {"status": "success"}

    assert name in TOOL_REGISTRY
    meta = TOOL_META[name]
    _assert_equal(meta["category"], "survival")
    _assert_equal(meta["schema_source"], "pydantic_model")
    _assert("params_model" in meta)

    # Check schema
    schema_item = None
    for item in TOOLS_SCHEMA:
        if item["function"]["name"] == name:
            schema_item = item
            break
    _assert(schema_item is not None, "Schema not found in TOOLS_SCHEMA")

    params = schema_item["function"]["parameters"]
    _assert_equal(params["type"], "object")
    _assert_in("gene", params["properties"])
    _assert_in("threshold", params["properties"])
    _assert_in("top_n", params["properties"])
    _assert_equal(params["properties"]["gene"]["type"], "string")
    _assert_equal(params["properties"]["threshold"]["type"], "number")
    _assert_equal(params["properties"]["threshold"]["default"], 0.05)
    _assert_equal(params["properties"]["top_n"]["type"], "integer")
    _assert_equal(params["properties"]["top_n"]["default"], 20)
    _assert_in("gene", params.get("required", []))
    _assert("threshold" not in params.get("required", []))  # has default

    print("[PASS] test_register_tool_pydantic_model")


def test_register_tool_pydantic_optional():
    """Pydantic Optional 字段应从 required 中排除。"""
    from pydantic import BaseModel, Field
    from app.agent.tool_registry import register_tool, TOOLS_SCHEMA

    class OptParams(BaseModel):
        name: str = Field(description="Required name")
        description: Optional[str] = Field(default=None, description="Optional description")

    name = "_test_pydantic_optional"

    @register_tool(
        name=name,
        description="Test optional",
        params_model=OptParams,
    )
    def _test_pydantic_optional_func(name: str, description: Optional[str] = None):
        return {"status": "success"}

    for item in TOOLS_SCHEMA:
        if item["function"]["name"] == name:
            params = item["function"]["parameters"]
            _assert_in("name", params.get("required", []))
            _assert("description" not in params.get("required", []))
            break

    print("[PASS] test_register_tool_pydantic_optional")


# ============================================================
# test_register_tool_signature_schema
# ============================================================

def test_register_tool_signature_schema():
    """从函数签名自动生成 schema。"""
    from app.agent.tool_registry import register_tool, TOOL_REGISTRY, TOOL_META, TOOLS_SCHEMA

    name = "_test_signature_schema"

    @register_tool(
        name=name,
        description="Signature test tool",
        category="general",
        tags=["signature"],
    )
    def _test_signature_func(
        file_path: str,
        top_n: int = 20,
        threshold: float = 0.05,
        verbose: bool = False,
        labels: list = None,
    ):
        return {"status": "success"}

    assert name in TOOL_REGISTRY
    meta = TOOL_META[name]
    _assert_equal(meta["schema_source"], "function_signature")

    for item in TOOLS_SCHEMA:
        if item["function"]["name"] == name:
            params = item["function"]["parameters"]
            _assert_equal(params["type"], "object")
            _assert_in("file_path", params["properties"])
            _assert_in("top_n", params["properties"])
            _assert_in("threshold", params["properties"])
            _assert_in("verbose", params["properties"])
            _assert_equal(params["properties"]["file_path"]["type"], "string")
            _assert_equal(params["properties"]["top_n"]["type"], "integer")
            _assert_equal(params["properties"]["threshold"]["type"], "number")
            _assert_equal(params["properties"]["verbose"]["type"], "boolean")
            _assert_equal(params["properties"]["top_n"]["default"], 20)
            # file_path should be required (no default)
            _assert_in("file_path", params.get("required", []))
            _assert("top_n" not in params.get("required", []))
            break

    print("[PASS] test_register_tool_signature_schema")


def test_register_tool_signature_skips_injected():
    """函数签名 schema 应跳过 session_id/job_dir/context/self。"""
    from app.agent.tool_registry import register_tool, TOOLS_SCHEMA

    name = "_test_skip_injected"

    @register_tool(
        name=name,
        description="Skip injected params",
    )
    def _test_skip_func(data: str, session_id: str = "", job_dir: str = "", context=None):
        return {"status": "success"}

    for item in TOOLS_SCHEMA:
        if item["function"]["name"] == name:
            params = item["function"]["parameters"]
            _assert_in("data", params["properties"])
            _assert("session_id" not in params["properties"])
            _assert("job_dir" not in params["properties"])
            _assert("context" not in params["properties"])
            break

    print("[PASS] test_register_tool_signature_skips_injected")


# ============================================================
# test_auto_discover_tools
# ============================================================

def test_auto_discover_tools():
    """auto_discover_tools 应发现并注册工具。"""
    from app.agent.tool_discovery import auto_discover_tools
    from app.agent.tool_registry import TOOL_REGISTRY

    count_before = len(TOOL_REGISTRY)

    loaded = auto_discover_tools("app.tools")

    count_after = len(TOOL_REGISTRY)

    _assert(len(loaded) > 0, "Should load at least some modules")
    _assert(count_after >= count_before, "Should not lose tools")

    print(f"[PASS] test_auto_discover_tools ({len(loaded)} modules, {count_after} tools)")


def test_auto_discover_tools_idempotent():
    """两次调用 auto_discover 不会重复注册工具。"""
    from app.agent.tool_discovery import auto_discover_tools
    from app.agent.tool_registry import TOOL_REGISTRY, _LOADED_TOOL_MODULES

    count_before = len(TOOL_REGISTRY)
    modules_before = len(_LOADED_TOOL_MODULES)

    loaded = auto_discover_tools("app.tools")

    count_after = len(TOOL_REGISTRY)
    modules_after = len(_LOADED_TOOL_MODULES)

    # 第二次调用不应注册新工具
    _assert_equal(
        count_after, count_before,
        "Second call should not register new tools"
    )

    print("[PASS] test_auto_discover_tools_idempotent")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3: Tool Registration Unit Tests")
    print("=" * 60)

    tests = [
        ("test_register_tool_old_style", test_register_tool_old_style),
        ("test_register_tool_pydantic_model", test_register_tool_pydantic_model),
        ("test_register_tool_pydantic_optional", test_register_tool_pydantic_optional),
        ("test_register_tool_signature_schema", test_register_tool_signature_schema),
        ("test_register_tool_signature_skips_injected", test_register_tool_signature_skips_injected),
        ("test_auto_discover_tools", test_auto_discover_tools),
        ("test_auto_discover_tools_idempotent", test_auto_discover_tools_idempotent),
    ]

    passed = 0
    failed = 0

    for test_name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {test_name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'=' * 60}")

    if failed > 0:
        sys.exit(1)
