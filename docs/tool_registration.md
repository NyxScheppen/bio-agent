# Phase 3: 简化工具注册

## 概述

扩展了 `register_tool` 装饰器，支持三种注册方式，让新增工具更简单、更规范。

## 三种注册方式

### 方式 1：旧写法（完全兼容）

```python
from app.agent.tool_registry import register_tool

@register_tool(
    name="my_tool",
    description="My analysis tool",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Input file"}
        },
        "required": ["file_path"]
    },
    category="file_io",
    tags=["preview"],
)
def my_tool(file_path: str):
    ...
```

`schema_source = "manual"`

### 方式 2：Pydantic params_model

```python
from pydantic import BaseModel, Field
from app.agent.tool_registry import register_tool

class MyParams(BaseModel):
    gene: str = Field(description="Gene name")
    threshold: float = Field(default=0.05, description="P-value cutoff")
    top_n: int = Field(default=20)

@register_tool(
    name="my_analysis",
    description="Gene analysis tool",
    category="survival",
    params_model=MyParams,
    tags=["cox", "survival"],
)
def my_analysis(gene: str, threshold: float = 0.05, top_n: int = 20):
    ...
```

`schema_source = "pydantic_model"`

Schema 由 `model_json_schema()` (Pydantic v2) 或 `schema()` (Pydantic v1) 自动生成，自动转换为 OpenAI function parameters 格式。

### 方式 3：函数签名自动推导（最简）

```python
@register_tool(
    name="count_bases",
    description="Count DNA/RNA bases",
    category="basic",
    tags=["sequence"],
)
def count_bases(sequence: str, include_gaps: bool = False):
    ...
```

`schema_source = "function_signature"`

自动从函数签名生成：
- `str` → `"string"`
- `int` → `"integer"`
- `float` → `"number"`
- `bool` → `"boolean"`
- `list` → `"array"`
- 无默认值 → `required`
- `Optional[X]` → 非必填
- 自动跳过 `session_id` / `job_dir` / `context` / `self`

## Schema 优先级

1. 显式 `parameters` dict → 直接用
2. `params_model` Pydantic 模型 → 自动转换
3. 都没有 → 从函数签名推导

## 工具自动发现

```python
from app.agent.tool_discovery import auto_discover_tools

# 替代旧的 from app import tools
auto_discover_tools("app.tools")
```

功能：
- 递归扫描 `app.tools` 下所有 `.py` 模块
- 跳过 `__init__.py` 和 `__pycache__`
- 避免重复注册（幂等调用）
- 返回加载的模块名列表

## 文件清单

### 修改文件
- `backend/app/agent/tool_registry.py` — 扩展 register_tool 支持 params_model + 函数签名推导 + 3 个 schema 生成函数

### 新增文件
- `backend/app/agent/tool_discovery.py` — auto_discover_tools 自动发现
- `backend/app/tools/example_pydantic_tool.py` — 三种注册方式示例
- `backend/tests/test_tool_registration.py` — 7 个测试
- `docs/tool_registration.md` — 本文档

## 测试

```bash
cd D:/Desktop/bio_test
.venv/Scripts/python.exe backend/tests/test_tool_registration.py
```

## 验收结果

| 标准 | 状态 |
|------|------|
| 旧工具注册方式不失效 | ✅ `test_register_tool_old_style` |
| 新工具可用 Pydantic params_model | ✅ `test_register_tool_pydantic_model` |
| Pydantic Optional 正确处理 | ✅ `test_register_tool_pydantic_optional` |
| 无 parameters 时函数签名生成 schema | ✅ `test_register_tool_signature_schema` |
| session_id/job_dir/context 自动跳过 | ✅ `test_register_tool_signature_skips_injected` |
| 自动发现工具 | ✅ `test_auto_discover_tools` (16 modules, 45 tools) |
| 自动发现幂等 | ✅ `test_auto_discover_tools_idempotent` |
| 全量回归 | ✅ Phase 1 (18) + Phase 2 (13) + Phase 3 (7) = 38/38 |
