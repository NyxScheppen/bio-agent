# Phase 2: 统一工具执行生命周期

## 概述

所有工具执行现在经过统一的 `run_tool_with_lifecycle()` 包装器，确保每次工具调用都有完整的生命周期管理。

### 生命周期流程

```
创建 ToolExecutionContext（自动 job_id / job_dir）
    ↓
注入 runtime 参数（session_id, job_dir, context）
    ↓
执行工具函数
    ↓
捕获异常 → 构造 error ToolResult
    ↓
归一化为标准 ToolResult（Phase 1）
    ↓
自动扫描 job_dir 中生成的文件
    ↓
合并 output_files（显式 + 自动收集）
    ↓
填充 provenance（tool_name, parameters, started_at, finished_at, runtime）
    ↓
返回标准 ToolResult
```

## 核心组件

### 1. ToolExecutionContext (`tool_context.py`)

每次工具执行自动创建的上下文容器：

```python
from app.agent.tool_context import create_tool_context

ctx = create_tool_context(
    tool_name="run_survival_analysis",
    session_id="abc123",
    parameters={"file_path": "data.csv", "gene": "TP53"},
)
# ctx.job_id   → "run_survival_analysis_a1b2c3d4"
# ctx.job_dir  → "D:/.../storage/generated/abc123/run_survival_analysis_a1b2c3d4/"
# ctx.started_at → "2024-01-01T12:00:00"
```

**job_dir 结构：**
- 有 session_id：`generated/{session_id}/{job_id}/`
- 无 session_id：`generated/{job_id}/`

### 2. run_tool_with_lifecycle (`tool_runner.py`)

工具统一执行入口：

```python
from app.agent.tool_runner import run_tool_with_lifecycle

result = run_tool_with_lifecycle(
    tool_name="my_tool",
    func=my_tool_function,
    function_args={"file_path": "data.csv", "top_n": 20},
    session_id="abc123",
)
# result is always a ToolResult
```

**自动参数注入：**
如果工具函数签名包含以下参数，会自动注入：
- `session_id` → 会话 ID
- `job_dir` → 输出目录路径
- `context` → ToolExecutionContext 对象

```python
def my_tool(file_path: str, job_dir: str = "", context=None):
    # job_dir 被自动注入
    output_path = Path(job_dir) / "result.csv"
    ...
```

### 3. collect_generated_files (`tool_runner.py`)

自动扫描 job_dir 中的生成文件：

**支持的文件扩展名：**
`.png` `.jpg` `.jpeg` `.svg` `.gif` `.webp` `.pdf` `.csv` `.tsv` `.txt` `.xlsx` `.xls` `.rds` `.rdata` `.json` `.zip`

```python
from app.agent.tool_runner import collect_generated_files

files = collect_generated_files("/path/to/job_dir")
# [{"name": "result.csv", "url": "/files/generated/...", ...}, ...]
```

### 4. merge_output_files (`tool_runner.py`)

合并工具显式返回的 output_files 和自动收集的文件，按名称去重。优先保留显式返回的。

## Executor 集成

`executor_agent.py` 已更新为使用 `run_tool_with_lifecycle()`：

```python
# 旧代码
raw_tool_result = func(**function_args)
# normalize_tool_result(...)

# 新代码
normalized_result = run_tool_with_lifecycle(
    tool_name=function_name,
    func=func,
    function_args=function_args,
    session_id=session_id,
)
```

自动恢复（scan_system_config / probe_unknown_file）现在直接向 `ToolResult.warnings` 追加恢复信息。

## 向后兼容

- 不接收 `job_dir` / `session_id` / `context` 的旧工具完全兼容
- Executor 的自动恢复逻辑保持不变
- Phase 1 的 `normalize_tool_result` 依然可用，且在生命周期内自动调用

## 测试

```bash
cd D:/Desktop/bio_test
.venv/Scripts/python.exe backend/tests/test_tool_lifecycle.py
```

### 测试覆盖（13 个测试）

| 测试 | 验证内容 |
|------|---------|
| `test_create_tool_context` | ToolExecutionContext 创建与字段 |
| `test_create_tool_context_no_session` | 无 session_id 时的默认行为 |
| `test_create_tool_context_job_dir_unique` | 每次调用生成唯一 job_id/job_dir |
| `test_run_tool_with_lifecycle_success` | 正常执行返回 success ToolResult |
| `test_run_tool_with_lifecycle_injects_job_dir` | job_dir 参数自动注入 |
| `test_run_tool_with_lifecycle_injects_session_id` | session_id 参数自动注入 |
| `test_run_tool_with_lifecycle_error` | 异常捕获为 error ToolResult |
| `test_run_tool_with_lifecycle_error_dict` | error dict 正确转换 |
| `test_collect_generated_files` | 文件扫描（含递归） |
| `test_collect_generated_files_empty` | 空目录处理 |
| `test_collect_generated_files_nonexistent` | 不存在的目录处理 |
| `test_lifecycle_auto_file_collection` | 自动收集未显式声明的文件 |
| `test_lifecycle_merge_no_duplicates` | 去重逻辑 |

## 文件清单

### 新增文件
- `backend/app/agent/tool_context.py` — ToolExecutionContext + create_tool_context
- `backend/app/agent/tool_runner.py` — run_tool_with_lifecycle + collect_generated_files + merge_output_files
- `backend/tests/test_tool_lifecycle.py` — 13 个生命周期测试
- `docs/tool_lifecycle.md` — 本文档

### 修改文件
- `backend/app/agent/executor_agent.py` — 使用 run_tool_with_lifecycle 替代直接调用
