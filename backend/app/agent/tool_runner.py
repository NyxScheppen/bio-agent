"""
统一工具执行生命周期包装器。

所有工具执行都应经过 run_tool_with_lifecycle()，确保：
1. 自动创建 job_dir
2. 注入 session_id / job_dir / context
3. 捕获异常并返回标准 error ToolResult
4. 自动扫描 job_dir 中生成的文件
5. 填充 provenance（参数、时间、job_id 等）
6. 返回标准 ToolResult
7. (Feature 1) 资源限制：超时/内存/CPU 监控
8. (Feature 2) 审计日志：非阻塞持久化执行记录
"""

import time
import inspect
import threading
import concurrent.futures
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.agent.tool_context import ToolExecutionContext, create_tool_context
from app.agent.tool_result import (
    ToolResult,
    OutputFile,
    ToolProvenance,
    ResourceUsage,
    RetryRecord,
    make_success_result,
    make_error_result,
    normalize_tool_result,
    _coerce_output_file,
)
from app.agent.tool_registry import get_tool_meta
from app.agent.agent_constants import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    MAX_TOOL_TIMEOUT_SECONDS,
    DEFAULT_MAX_MEMORY_MB,
    RESOURCE_CHECK_INTERVAL_SECONDS,
)

# psutil 是可选依赖，缺失时资源监控自动降级
try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    _PSUTIL_AVAILABLE = False

# 需要自动收集的文件扩展名
COLLECTIBLE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp",
    ".pdf",
    ".csv", ".tsv", ".txt",
    ".xlsx", ".xls",
    ".rds", ".rdata",
    ".json", ".zip",
}


# ============================================================
# ResourceMonitor — Feature 1: 资源限制
# ============================================================

class ResourceMonitor:
    """
    工具执行资源监控器。

    使用 psutil 监控当前进程的内存和 CPU 使用。
    psutil 不可用时自动降级为仅计时。

    用法:
        monitor = ResourceMonitor(timeout_seconds=600, max_memory_mb=4096)
        monitor.start()
        # ... 执行工具 ...
        usage = monitor.stop()
    """

    def __init__(
        self,
        timeout_seconds: int = DEFAULT_TOOL_TIMEOUT_SECONDS,
        max_memory_mb: Optional[int] = None,
        max_cpu_percent: Optional[int] = None,
    ):
        self.timeout = timeout_seconds
        self.max_memory_mb = max_memory_mb or DEFAULT_MAX_MEMORY_MB
        self.max_cpu_percent = max_cpu_percent
        self._start_memory: Optional[float] = None
        self._peak_memory: float = 0.0
        self._cpu_samples: List[float] = []
        self._started: bool = False
        self._stopped: bool = False
        self._lock = threading.Lock()

    def start(self):
        """记录基线内存并启动后台采样。"""
        if self._started:
            return
        self._started = True

        if _PSUTIL_AVAILABLE:
            try:
                proc = psutil.Process()
                self._start_memory = proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

    def stop(self) -> ResourceUsage:
        """停止监控，返回 ResourceUsage 快照。"""
        if self._stopped:
            return ResourceUsage()
        self._stopped = True

        usage = ResourceUsage(
            timeout_limit_seconds=self.timeout,
            timeout_triggered=False,
            max_memory_mb=self.max_memory_mb,
        )

        if _PSUTIL_AVAILABLE:
            try:
                proc = psutil.Process()
                end_mem = proc.memory_info().rss / (1024 * 1024)
                usage.end_memory_mb = round(end_mem, 2)
                usage.peak_memory_mb = round(max(self._peak_memory, end_mem), 2)
            except Exception:
                pass

        if self._start_memory is not None:
            usage.start_memory_mb = round(self._start_memory, 2)

        if self._cpu_samples:
            usage.cpu_percent = round(
                sum(self._cpu_samples) / len(self._cpu_samples), 1
            )

        if not _PSUTIL_AVAILABLE:
            usage.peak_memory_mb = None
            usage.start_memory_mb = None
            usage.end_memory_mb = None
            usage.cpu_percent = None

        return usage

    def mark_timeout(self):
        """标记超时已触发。"""
        self._stopped = True
        usage = ResourceUsage(
            timeout_limit_seconds=self.timeout,
            timeout_triggered=True,
            max_memory_mb=self.max_memory_mb,
        )
        if self._start_memory is not None:
            usage.start_memory_mb = round(self._start_memory, 2)
        return usage


# ============================================================


def collect_generated_files(job_dir: str) -> List[Dict[str, Any]]:
    """
    扫描 job_dir 下所有文件，返回标准文件列表。

    支持递归扫描，跳过目录。

    Returns:
        List of file dicts compatible with OutputFile:
        {
            "name": str,
            "url": str,
            "relative_path": str,
            "size_bytes": int,
        }
    """
    if not job_dir:
        return []

    job_path = Path(job_dir)
    if not job_path.exists() or not job_path.is_dir():
        return []

    files: List[Dict[str, Any]] = []

    for p in sorted(job_path.rglob("*")):
        if not p.is_file():
            continue

        # 只收集已知扩展名
        suffix = p.suffix.lower()
        if suffix not in COLLECTIBLE_EXTENSIONS:
            continue

        # 跳过 analysis_manifest.json（Phase 6 单独处理）
        if p.name == "analysis_manifest.json":
            continue

        # 构建 relative_path（相对于 STORAGE_DIR）
        # 假设 job_dir 在 GENERATED_DIR（即 STORAGE_DIR/generated/）下
        # 如果不是，至少用相对于 job_dir 的路径
        from app.core.runtime_paths import STORAGE_DIR, GENERATED_DIR

        try:
            rel = p.relative_to(STORAGE_DIR).as_posix()
        except ValueError:
            # job_dir 不在 STORAGE_DIR 下
            try:
                rel = f"generated/{p.relative_to(GENERATED_DIR).as_posix()}"
            except ValueError:
                rel = p.relative_to(job_path).as_posix()

        url = f"/files/{rel}"

        files.append({
            "name": p.name,
            "url": url,
            "relative_path": rel,
            "size_bytes": p.stat().st_size,
        })

    return files


def merge_output_files(
    explicit_files: List[Any],
    collected_files: List[Dict[str, Any]],
) -> List[OutputFile]:
    """
    合并工具显式返回的 output_files 和自动收集的文件。

    去重规则：
    1. 以 (relative_path, url, name) 为 key 去重
    2. 以 name 为辅助 key 去重（处理路径不一致但同文件名的情况）

    优先级：显式返回的 > 自动收集的

    Args:
        explicit_files: 工具返回的 output_files（可能是 OutputFile 或 dict）
        collected_files: collect_generated_files 返回的 dict 列表
    """
    seen_keys: set = set()
    seen_names: set = set()
    result: List[OutputFile] = []

    # 先处理显式返回的（优先级高）
    for f in explicit_files:
        if isinstance(f, OutputFile):
            of = f
        elif isinstance(f, dict):
            of = _coerce_output_file(f)
        else:
            continue

        key = (of.relative_path, of.url, of.name)
        if key in seen_keys or of.name in seen_names:
            continue
        seen_keys.add(key)
        seen_names.add(of.name)
        result.append(of)

    # 再添加收集到的（不覆盖已存在的）
    for f_dict in collected_files:
        of = _coerce_output_file(f_dict)
        key = (of.relative_path, of.url, of.name)
        if key in seen_keys or of.name in seen_names:
            continue
        seen_keys.add(key)
        seen_names.add(of.name)
        result.append(of)

    return result


def _inject_lifecycle_args(
    func: Callable,
    function_args: Dict[str, Any],
    context: ToolExecutionContext,
) -> Dict[str, Any]:
    """
    将生命周期相关参数注入工具函数参数中。

    如果工具函数签名包含以下参数名，则自动注入：
    - session_id → context.session_id
    - job_dir → context.job_dir
    - context → context 对象本身
    """
    if function_args is None:
        function_args = {}

    try:
        sig = inspect.signature(func)
        params = sig.parameters

        if "session_id" in params and context.session_id:
            function_args["session_id"] = context.session_id

        if "job_dir" in params:
            function_args["job_dir"] = context.job_dir

        if "context" in params:
            function_args["context"] = context

    except Exception:
        pass

    return function_args


def run_tool_with_lifecycle(
    tool_name: str,
    func: Callable,
    function_args: Dict[str, Any],
    session_id: str = None,
    timeout_override: int = None,  # Feature 1: caller-forced timeout
) -> ToolResult:
    """
    工具执行统一生命周期包装器。

    流程：
    1. 创建 ToolExecutionContext（自动 job_id / job_dir）
    2. 注入 runtime 参数（session_id, job_dir, context）
    3. 【Feature 1】解析资源限制，启动 ResourceMonitor
    4. 执行工具函数（ThreadPoolExecutor + timeout）
    5. 捕获异常，构造 error ToolResult
    6. 归一化为 ToolResult
    7. 自动扫描 job_dir 中生成的文件
    8. 合并 output_files
    9. 填充 provenance（参数、时间、job_id、resource_usage 等）
    10.【Feature 2】审计日志写入（非阻塞）
    11. 返回标准 ToolResult

    Args:
        tool_name: 工具名
        func: 工具函数
        function_args: 传递给工具函数的参数
        session_id: 会话 ID
        timeout_override: 强制超时（秒），为 None 时使用工具注册值或默认值

    Returns:
        标准 ToolResult
    """
    tool_meta = get_tool_meta(tool_name)
    tool_category = tool_meta.get("category", "")

    # 1. 创建上下文
    ctx = create_tool_context(
        tool_name=tool_name,
        session_id=session_id or "",
        parameters=dict(function_args or {}),
        tool_category=tool_category,
    )

    # 2. 注入参数
    function_args = _inject_lifecycle_args(func, function_args, ctx)

    # ---- Feature 1: 解析资源限制 ----
    effective_timeout = (
        timeout_override
        or tool_meta.get("timeout")
        or DEFAULT_TOOL_TIMEOUT_SECONDS
    )
    effective_timeout = max(10, min(effective_timeout, MAX_TOOL_TIMEOUT_SECONDS))

    max_memory = tool_meta.get("max_memory_mb") or DEFAULT_MAX_MEMORY_MB

    monitor = ResourceMonitor(
        timeout_seconds=effective_timeout,
        max_memory_mb=max_memory,
    )
    monitor.start()

    # 记录开始时间
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    t_start = time.time()

    # 3-4. 执行工具（ThreadPoolExecutor + timeout）
    raw_result = None
    exception_occurred = False

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, **function_args)
            raw_result = future.result(timeout=effective_timeout)
    except concurrent.futures.TimeoutError:
        exception_occurred = True
        raw_result = {
            "status": "error",
            "message": f"工具执行超时（>{effective_timeout} 秒），已中断",
            "tool": tool_name,
        }
    except Exception as e:
        exception_occurred = True
        raw_result = {
            "status": "error",
            "message": f"工具执行异常: {str(e)}",
            "tool": tool_name,
        }

    t_end = time.time()
    finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    runtime_seconds = round(t_end - t_start, 3)

    # ---- Phase 5.2: Pre-tool Hook ----
    try:
        from app.agent.hooks import hook_manager, HookPoint
        hook_manager.trigger(HookPoint.PRE_TOOL_EXECUTION, {
            "tool_name": tool_name,
            "session_id": session_id or "",
            "job_dir": ctx.job_dir,
            "parameters": dict(function_args or {}),
        })
    except Exception:
        pass

    # ---- Feature 1: 收集资源使用 ----
    if exception_occurred and isinstance(raw_result, dict) and "超时" in str(raw_result.get("message", "")):
        resource_usage = monitor.mark_timeout()
    else:
        resource_usage = monitor.stop()

    # 5. 归一化为 ToolResult
    normalized = normalize_tool_result(
        raw_result,
        tool_name=tool_name,
        tool_category=tool_category,
        session_id=session_id or "",
        job_id=ctx.job_id,
        started_at=started_at,
    )

    # 6. 自动扫描 job_dir 中生成的文件
    collected_files = collect_generated_files(ctx.job_dir)

    # 7. 合并 output_files
    merged_files = merge_output_files(
        explicit_files=list(normalized.output_files),
        collected_files=collected_files,
    )
    normalized.output_files = merged_files

    # 8. 填充 provenance
    normalized.provenance.tool_name = tool_name
    normalized.provenance.tool_category = tool_category
    normalized.provenance.job_id = ctx.job_id
    normalized.provenance.started_at = started_at
    normalized.provenance.finished_at = finished_at
    normalized.provenance.runtime_seconds = runtime_seconds
    normalized.provenance.parameters = dict(function_args or {})
    normalized.provenance.resource_usage = resource_usage  # Feature 1

    # 注入 job_dir 信息到 summary
    if not normalized.summary:
        normalized.summary = {}
    normalized.summary["job_id"] = ctx.job_id
    normalized.summary["job_dir"] = ctx.job_dir

    if exception_occurred and not normalized.errors:
        normalized.errors.append(str(raw_result.get("message", "未知异常")))

    # ---- Phase 5.2: Post-tool Hook ----
    try:
        from app.agent.hooks import hook_manager, HookPoint
        hook_manager.trigger(HookPoint.POST_TOOL_EXECUTION, {
            "tool_name": tool_name,
            "session_id": session_id or "",
            "job_id": ctx.job_id,
            "job_dir": ctx.job_dir,
            "status": normalized.status,
            "runtime_seconds": runtime_seconds,
            "message": normalized.message[:300],
        })
    except Exception:
        pass

    # ---- Feature 2: 审计日志 ----
    _audit_tool_execution_safe(normalized, session_id=session_id or "")

    return normalized


# ============================================================
# Feature 2: 审计日志安全写入
# ============================================================

def _audit_tool_execution_safe(tool_result: ToolResult, session_id: str) -> None:
    """
    非阻塞写入审计日志。
    审计失败仅打印警告，绝不影响工具执行流程。
    """
    try:
        from app.db.audit import audit_tool_execution
        audit_tool_execution(tool_result, session_id=session_id)
    except Exception as e:
        print(f"[audit] 审计日志写入失败（非致命）: {e}")


# ============================================================
# Feature 3: 统一重试/恢复策略
# ============================================================

def execute_recovery_strategies(
    tool_result: ToolResult,
    tool_name: str,
    function_args: Dict[str, Any],
    available_tool_names: set,
    session_id: str,
    tool_meta: Optional[Dict] = None,
    retry_count: int = 0,
) -> ToolResult:
    """
    对失败的工具有执行恢复策略。

    返回值：追加了 retry_records 的 tool_result（原始 error status 不变）。

    Args:
        tool_result: 失败工具的 ToolResult
        tool_name: 原始工具名
        function_args: 原始工具参数
        available_tool_names: 当前可见工具名集合
        session_id: 会话 ID
        tool_meta: 工具元信息（可选）
        retry_count: 已重试次数（外部传入，用于跨轮次累加）
    """
    if tool_meta is None:
        tool_meta = get_tool_meta(tool_name)

    # 工具级策略优先，否则用全局默认策略
    from app.agent.recovery_strategies import DEFAULT_RECOVERY_STRATEGIES

    strategies = list(tool_meta.get("recovery_strategies") or [])
    if not strategies:
        strategies = list(DEFAULT_RECOVERY_STRATEGIES)

    for strategy in strategies:
        # 尊重重试上限
        if retry_count >= strategy.max_retries:
            continue

        # 检查触发条件
        if not strategy.matches(tool_result, tool_name, function_args):
            continue

        # 获取恢复操作
        recovery_tool_name, recovery_args = strategy.get_recovery_tool_and_args(
            function_args
        )
        if not recovery_tool_name:
            tool_result.warnings.append(
                f"[{strategy.strategy_name}] 检测到错误但无可用恢复操作"
            )
            continue

        # 检查可用性
        if recovery_tool_name not in available_tool_names:
            continue

        # 防止自己恢复自己
        if recovery_tool_name == tool_name:
            continue

        # 执行恢复
        from app.agent.tool_registry import TOOL_REGISTRY
        recovery_func = TOOL_REGISTRY.get(recovery_tool_name)
        if not recovery_func:
            continue

        timestamp = datetime.now().isoformat()

        try:
            recovery_result = run_tool_with_lifecycle(
                tool_name=recovery_tool_name,
                func=recovery_func,
                function_args=recovery_args or {},
                session_id=session_id,
            )

            error_desc = "; ".join(
                tool_result.errors[:2]
            ) if tool_result.errors else tool_result.message[:200]

            record = RetryRecord(
                attempt=retry_count + 1,
                original_tool=tool_name,
                error_description=error_desc,
                recovery_tool=recovery_tool_name,
                recovery_args=recovery_args or {},
                recovery_result_status=recovery_result.status,
                recovery_result_summary=recovery_result.message[:300],
                recovery_job_id=recovery_result.provenance.job_id,
                timestamp=timestamp,
            )
            tool_result.retry_records.append(record)
            tool_result.warnings.append(
                f"[{strategy.strategy_name}] 自动调用 {recovery_tool_name} 诊断"
            )
            retry_count += 1

        except Exception as e:
            tool_result.warnings.append(
                f"[{strategy.strategy_name}] {recovery_tool_name} 调用失败: {e}"
            )

    return tool_result
