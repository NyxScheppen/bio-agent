# Phase 1: 统一工具返回格式 ToolResult

## 概述

`ToolResult` 是全项目统一的工具返回协议，所有工具（无论是 Python 代码还是 R 子进程）最终都应返回标准 `ToolResult` 或其等价 dict。

目标：替代当前散乱的 `dict` / `JSON string` / 自定义返回结构。

## 数据结构

### ToolResult（顶层）

```python
class ToolResult(BaseModel):
    status: str = "success"           # "success" | "error" | "partial"
    message: str = ""                 # 人类可读的简短描述
    summary: Dict[str, Any] = {}      # 结构化摘要（关键统计数字等）
    tables: List[ResultTable] = []    # 结果表格列表
    figures: List[ResultFigure] = []  # 结果图表列表
    output_files: List[OutputFile] = []  # 所有输出文件（前端据此展示）
    warnings: List[str] = []          # 非致命警告
    errors: List[str] = []            # 错误信息
    provenance: ToolProvenance        # 执行溯源
```

### OutputFile

```python
class OutputFile(BaseModel):
    name: str = ""                    # 文件名，如 "result.csv"
    url: str = ""                     # 前端可访问 URL，如 "/files/generated/abc/result.csv"
    relative_path: str = ""           # 相对路径，如 "generated/abc/result.csv"
    size_bytes: Optional[int] = None  # 文件大小（字节）
    file_type: str = ""               # "image" | "table" | "text" | "pdf" | "r_data" | "archive" | "other"
    description: str = ""             # 文件描述
```

### ToolProvenance

```python
class ToolProvenance(BaseModel):
    tool_name: str = ""               # 工具名
    tool_category: str = ""           # 工具类别
    parameters: Dict[str, Any] = {}   # 调用参数
    started_at: Optional[str] = None  # ISO 8601 开始时间
    finished_at: Optional[str] = None # ISO 8601 结束时间
    runtime_seconds: Optional[float] = None
    input_files: List[Dict] = []      # 输入文件
    software_versions: Dict = {}      # 软件版本
    workflow_id: str = ""
    job_id: str = ""
```

## 使用方法

### 1. 工具直接返回 ToolResult（推荐新工具使用）

```python
from app.agent.tool_result import make_success_result, make_error_result

def my_new_tool(file_path: str, threshold: float = 0.05):
    # ... 执行分析 ...
    return make_success_result(
        message="分析完成",
        output_files=[
            {"name": "result.csv", "url": "/files/generated/x/result.csv",
             "relative_path": "generated/x/result.csv"}
        ],
        summary={"up": 150, "down": 80}
    )

def my_failing_tool():
    return make_error_result(
        message="找不到 Rscript",
        errors=["R 未安装或未在 PATH 中"]
    )
```

### 2. 工具返回旧格式 dict（向后兼容）

Executor 会自动调用 `normalize_tool_result()` 转换旧格式 dict 为 `ToolResult`：

```python
# 旧格式（仍然兼容）：
return {
    "status": "success",
    "message": "OK",
    "output_files": [{"name": "a.csv", "url": "/files/a.csv"}]
}

# 或更老的格式（没有 status 字段，视为 success）：
return {
    "columns": 10,
    "rows": 100,
    "output_files": [...]
}
```

### 3. 规范化工具返回（Executor 内部）

Executor 在每次工具调用后自动执行：

```python
from app.agent.tool_result import normalize_tool_result

normalized_result = normalize_tool_result(
    raw_tool_result,
    tool_name=function_name,
    tool_category="survival",
    session_id=session_id,
    started_at="2024-01-01T00:00:00"
)
```

`normalize_tool_result()` 支持：
- 已经是 `ToolResult` → 直接返回（补充 provenance）
- `dict`（有 status 字段）→ 映射为标准字段
- `dict`（无 status 字段）→ 视为 success，内容合并到 summary
- JSON 字符串 → 解析后递归处理
- `list` → 提取文件列表
- `None` / 其他类型 → 兜底包装

## 与旧格式的兼容方式

### Executor 兼容

`executor_agent.py` 已修改为：
1. 工具调用后统一调用 `normalize_tool_result()`
2. `extract_output_files()` 已适配 `ToolResult` 对象
3. `build_compact_tool_summary()` 已适配 `ToolResult` 对象
4. 错误检测函数（`is_error_result` 等）已适配

### 代码兼容

`agent_utils.py` 中 `extract_output_files()` 可同时处理：
- `ToolResult` 对象 → 提取 `.output_files`
- `OutputFile` Pydantic 对象 → 自动转 dict
- 旧 dict → 递归提取
- JSON 字符串 → 解析后提取

## 测试

```bash
# 从项目根目录运行
cd D:\Desktop\bio_test
.\.venv\Scripts\python.exe backend\tests\test_tool_result.py

# 或使用 pytest
.\.venv\Scripts\python.exe -m pytest backend\tests\test_tool_result.py -v
```

### 测试覆盖（18 个测试）

| 测试 | 验证内容 |
|------|---------|
| `test_normalize_tool_result_from_dict` | 有 status 的 dict → ToolResult |
| `test_normalize_tool_result_no_status` | 无 status 的 dict → 视为 success |
| `test_normalize_tool_result_error` | error dict → ToolResult |
| `test_normalize_tool_result_from_json_string` | JSON 字符串 → ToolResult |
| `test_normalize_tool_result_json_error_string` | JSON 错误字符串 → ToolResult |
| `test_normalize_tool_result_extract_output_files` | 多文件提取，type 推断 |
| `test_normalize_tool_result_empty_output_files` | 无文件场景 |
| `test_make_error_result` | 快捷错误构造 |
| `test_make_error_result_single_error` | 单条错误自动填充 |
| `test_make_success_result` | 快捷成功构造 |
| `test_normalize_tool_result_with_automatic_recovery` | 自动恢复包装处理 |
| `test_normalize_tool_result_already_toolresult` | 传递 ToolResult 时补充 provenance |
| `test_normalize_tool_result_list_input` | list 类型包装 |
| `test_coerce_output_file` | 字段变体兼容 |
| `test_tool_result_to_legacy_dict` | 向后兼容 legacy dict 转换 |
| `test_provenance_fields` | provenance 字段完整性 |
| `test_normalize_plain_string` | 纯文本包装 |
| `test_normalize_none` | None 兜底 |

## 文件清单

### 新增文件

- `backend/app/agent/tool_result.py` — ToolResult 模型 + normalize/make_success/make_error 函数
- `backend/tests/test_tool_result.py` — 18 个单元测试
- `docs/tool_result_standard.md` — 本文档

### 修改文件

- `backend/app/agent/executor_agent.py` — 工具调用后使用 normalize_tool_result
- `backend/app/agent/agent_utils.py` — extract_output_files / build_compact_tool_summary 适配 ToolResult

## 迁移指南

### 新工具

直接使用 `make_success_result()` / `make_error_result()` 或构建 `ToolResult` 对象。

### 已有工具

无需立即修改。Executor 会自动调用 `normalize_tool_result()` 转换旧 dict 格式。

### 逐步迁移建议

1. 按类别逐步更新工具返回格式
2. 优先迁移高频工具（survival、transcriptome、enrichment）
3. 每次迁移后运行测试确保兼容
4. 最终移除 `normalize_tool_result` 中的兼容分支（长期目标）
