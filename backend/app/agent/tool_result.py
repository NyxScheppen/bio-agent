"""
标准工具返回协议 ToolResult。

本模块定义了全项目统一的工具返回格式，替代散乱的 dict / JSON string / 自定义返回结构。

所有工具最终都应返回标准 ToolResult 或其等价 dict。

向后兼容：
- 旧工具返回的 dict（无论有无 status 字段）均可被 normalize_tool_result() 转换
- JSON 字符串会被自动解析
- 嵌套的 original_tool_result / automatic_recovery 会被递归处理
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ============================================================
# 核心 Pydantic 模型
# ============================================================

class OutputFile(BaseModel):
    """标准输出文件描述。兼容前端 files 数组格式。"""
    name: str = ""
    url: str = ""
    relative_path: str = ""
    size_bytes: Optional[int] = None
    file_type: str = ""
    description: str = ""


class ResultTable(BaseModel):
    """分析结果中的表格描述。"""
    name: str = ""
    file: Optional[OutputFile] = None
    rows: Optional[int] = None
    columns: Optional[int] = None
    description: str = ""


class ResultFigure(BaseModel):
    """分析结果中的图表描述。"""
    name: str = ""
    file: Optional[OutputFile] = None
    figure_type: str = ""  # e.g., "heatmap", "volcano", "km_curve", "barplot"
    description: str = ""


class ResourceUsage(BaseModel):
    """工具执行资源消耗快照 (Feature 1: Resource Limits)."""
    timeout_limit_seconds: Optional[int] = None
    timeout_triggered: bool = False
    max_memory_mb: Optional[int] = None          # 配置的内存阈值
    peak_memory_mb: Optional[float] = None        # 实际峰值内存
    start_memory_mb: Optional[float] = None       # 执行开始时的进程内存
    end_memory_mb: Optional[float] = None         # 执行结束时的进程内存
    cpu_percent: Optional[float] = None           # 平均 CPU 占比


class ToolProvenance(BaseModel):
    """工具执行溯源信息，记录工具如何被执行、用了什么参数、输入输出等。"""
    tool_name: str = ""
    tool_category: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None       # ISO 8601
    finished_at: Optional[str] = None      # ISO 8601
    runtime_seconds: Optional[float] = None
    input_files: List[Dict[str, Any]] = Field(default_factory=list)
    software_versions: Dict[str, Any] = Field(default_factory=dict)
    workflow_id: str = ""
    job_id: str = ""
    resource_usage: Optional[ResourceUsage] = None  # Feature 1


class RetryRecord(BaseModel):
    """单次恢复/重试记录 (Feature 3: Retry Strategies)."""
    attempt: int = 0
    original_tool: str = ""
    error_description: str = ""
    recovery_tool: str = ""
    recovery_args: Dict[str, Any] = Field(default_factory=dict)
    recovery_result_status: str = ""   # "success" | "error" | "skipped"
    recovery_result_summary: str = ""
    recovery_job_id: str = ""
    timestamp: str = ""                # ISO 8601


class ToolResult(BaseModel):
    """统一工具返回协议。

    字段说明：
    - status: "success" | "error" | "partial"
    - message: 人类可读的简短描述
    - summary: 结构化摘要（如关键统计数字）
    - tables: 结果表格列表
    - figures: 结果图表列表
    - output_files: 所有输出文件列表（前端据此展示下载/图片）
    - warnings: 非致命警告列表
    - errors: 错误信息列表
    - provenance: 执行溯源
    - retry_records: 恢复/重试记录列表 (Feature 3)
    """
    status: str = "success"
    message: str = ""
    summary: Dict[str, Any] = Field(default_factory=dict)
    tables: List[ResultTable] = Field(default_factory=list)
    figures: List[ResultFigure] = Field(default_factory=list)
    output_files: List[OutputFile] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    provenance: ToolProvenance = Field(default_factory=ToolProvenance)
    retry_records: List[RetryRecord] = Field(default_factory=list)


# ============================================================
# 构造函数
# ============================================================

def make_tool_result(
    status: str = "success",
    message: str = "",
    summary: Optional[Dict[str, Any]] = None,
    tables: Optional[List[Union[ResultTable, Dict[str, Any]]]] = None,
    figures: Optional[List[Union[ResultFigure, Dict[str, Any]]]] = None,
    output_files: Optional[List[Union[OutputFile, Dict[str, Any]]]] = None,
    warnings: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
    provenance: Optional[Union[ToolProvenance, Dict[str, Any]]] = None,
    **kwargs,
) -> ToolResult:
    """
    构造标准 ToolResult。

    用法：
        make_tool_result(status="success", message="分析完成", output_files=[...])
        make_tool_result(status="error", message="找不到文件", errors=["file not found"])
    """
    # 处理 output_files
    parsed_output_files: List[OutputFile] = []
    for f in (output_files or []):
        if isinstance(f, OutputFile):
            parsed_output_files.append(f)
        elif isinstance(f, dict):
            parsed_output_files.append(_coerce_output_file(f))
        # 忽略非 dict 项

    # 处理 tables
    parsed_tables: List[ResultTable] = []
    for t in (tables or []):
        if isinstance(t, ResultTable):
            parsed_tables.append(t)
        elif isinstance(t, dict):
            parsed_tables.append(ResultTable(**t))

    # 处理 figures
    parsed_figures: List[ResultFigure] = []
    for f in (figures or []):
        if isinstance(f, ResultFigure):
            parsed_figures.append(f)
        elif isinstance(f, dict):
            parsed_figures.append(ResultFigure(**f))

    # 处理 provenance
    parsed_provenance: ToolProvenance
    if isinstance(provenance, ToolProvenance):
        parsed_provenance = provenance
    elif isinstance(provenance, dict):
        parsed_provenance = ToolProvenance(**provenance)
    else:
        parsed_provenance = ToolProvenance()

    return ToolResult(
        status=status,
        message=message,
        summary=summary or {},
        tables=parsed_tables,
        figures=parsed_figures,
        output_files=parsed_output_files,
        warnings=warnings or [],
        errors=errors or [],
        provenance=parsed_provenance,
    )


def make_success_result(
    message: str = "分析完成",
    output_files: Optional[List[Union[OutputFile, Dict[str, Any]]]] = None,
    **kwargs,
) -> ToolResult:
    """快捷构造成功的 ToolResult。"""
    return make_tool_result(
        status="success",
        message=message,
        output_files=output_files,
        **kwargs,
    )


def make_error_result(
    message: str = "工具执行失败",
    errors: Optional[List[str]] = None,
    output_files: Optional[List[Union[OutputFile, Dict[str, Any]]]] = None,
    **kwargs,
) -> ToolResult:
    """快捷构造失败的 ToolResult。"""
    return make_tool_result(
        status="error",
        message=message,
        errors=errors or [message],
        output_files=output_files,
        **kwargs,
    )


def _coerce_output_file(data: Dict[str, Any]) -> OutputFile:
    """
    将任意 dict 尽量转成 OutputFile。

    能处理旧工具返回的多种字段名变体：
    - path → relative_path
    - type / file_type → file_type
    - size / size_bytes → size_bytes
    """
    name = str(data.get("name") or "").strip()
    url = str(data.get("url") or "").strip()
    relative_path = str(data.get("relative_path") or "").strip()
    path = str(data.get("path") or "").strip()

    # 从 url 反推 relative_path
    if (not relative_path) and url.startswith("/files/"):
        relative_path = url[len("/files/"):].strip("/")

    # 从 path 反推
    if not relative_path and path:
        relative_path = path.replace("\\", "/")

    # 从 relative_path 反推 url
    if relative_path and not url:
        url = f"/files/{relative_path}"

    # 反推 name
    if not name:
        if relative_path:
            name = Path(relative_path).name
        elif url:
            name = Path(url.split("?")[0]).name

    size_bytes = data.get("size_bytes") or data.get("size")
    try:
        size_bytes = int(size_bytes) if size_bytes is not None and size_bytes != "" else None
    except (ValueError, TypeError):
        size_bytes = None

    file_type = str(data.get("file_type") or data.get("type") or "").strip()
    if not file_type and name:
        file_type = _guess_file_type(name)

    description = str(data.get("description") or "").strip()

    return OutputFile(
        name=name,
        url=url,
        relative_path=relative_path,
        size_bytes=size_bytes,
        file_type=file_type,
        description=description,
    )


def _guess_file_type(filename: str) -> str:
    """根据扩展名推断文件类型。"""
    ext = Path(filename).suffix.lower()
    image_exts = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
    table_exts = {".csv", ".tsv", ".xlsx", ".xls"}
    text_exts = {".txt", ".md", ".log"}
    pdf_exts = {".pdf"}
    r_exts = {".rds", ".rdata", ".rda"}
    archive_exts = {".zip", ".gz", ".tar", ".tar.gz"}

    if ext in image_exts:
        return "image"
    if ext in table_exts:
        return "table"
    if ext in text_exts:
        return "text"
    if ext in pdf_exts:
        return "pdf"
    if ext in r_exts:
        return "r_data"
    if ext in archive_exts:
        return "archive"
    return "other"


# ============================================================
# 归一化函数（核心）
# ============================================================

def normalize_tool_result(
    raw_result: Any,
    tool_name: str = "",
    tool_category: str = "",
    session_id: str = "",
    job_id: str = "",
    started_at: Optional[str] = None,
) -> ToolResult:
    """
    将任意工具返回归一化为标准 ToolResult。

    这是 Executor 调用工具后必须调用的统一入口。

    支持输入：
    1. 已经是 ToolResult → 直接返回（补充 provenance）
    2. dict（有 status 字段）→ 映射为标准字段
    3. dict（无 status 字段）→ 视为成功，原 dict 内容合并到 summary
    4. JSON 字符串 → 解析后递归处理
    5. list → 尝试从中提取 output_files
    6. 其他类型 → 视为成功，内容放入 message

    Args:
        raw_result: 工具原始返回
        tool_name: 工具名（用于 provenance）
        tool_category: 工具类别
        session_id: 会话 ID
        job_id: 任务 ID
        started_at: 开始时间 ISO 字符串
    """
    finished_at = datetime.now().isoformat()

    # --- 已经是 ToolResult ---
    if isinstance(raw_result, ToolResult):
        tr = raw_result
        # 补充 provenance（不覆盖已有值）
        if not tr.provenance.tool_name:
            tr.provenance.tool_name = tool_name
        if not tr.provenance.tool_category:
            tr.provenance.tool_category = tool_category
        if not tr.provenance.job_id:
            tr.provenance.job_id = job_id
        if not tr.provenance.started_at:
            tr.provenance.started_at = started_at
        if not tr.provenance.finished_at:
            tr.provenance.finished_at = finished_at
        return tr

    # --- JSON 字符串 ---
    if isinstance(raw_result, str):
        s = raw_result.strip()
        if s:
            try:
                parsed = json.loads(s)
                return normalize_tool_result(
                    parsed,
                    tool_name=tool_name,
                    tool_category=tool_category,
                    session_id=session_id,
                    job_id=job_id,
                    started_at=started_at,
                )
            except (json.JSONDecodeError, ValueError):
                pass
        # 纯文本字符串
        return _build_from_plain_value(
            raw_result,
            tool_name=tool_name,
            tool_category=tool_category,
            job_id=job_id,
            started_at=started_at,
            finished_at=finished_at,
        )

    # --- list ---
    if isinstance(raw_result, list):
        # 尝试提取 output_files
        output_files = _extract_output_files_from_list(raw_result)
        return make_tool_result(
            status="success",
            message=f"工具返回 {len(raw_result)} 条记录",
            output_files=output_files,
            summary={"item_count": len(raw_result)},
            provenance=ToolProvenance(
                tool_name=tool_name,
                tool_category=tool_category,
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at,
            ),
        )

    # --- dict ---
    if isinstance(raw_result, dict):
        return _normalize_dict_result(
            raw_result,
            tool_name=tool_name,
            tool_category=tool_category,
            job_id=job_id,
            started_at=started_at,
            finished_at=finished_at,
        )

    # --- 其他类型（int、float、bool、None 等）---
    return _build_from_plain_value(
        raw_result,
        tool_name=tool_name,
        tool_category=tool_category,
        job_id=job_id,
        started_at=started_at,
        finished_at=finished_at,
    )


def _normalize_dict_result(
    data: Dict[str, Any],
    tool_name: str = "",
    tool_category: str = "",
    job_id: str = "",
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
) -> ToolResult:
    """
    处理 dict 类型的工具返回。

    策略：
    1. 先处理嵌套包装（original_tool_result / automatic_recovery）
    2. 再按 status 字段判断
    3. 迁移常见字段到 ToolResult
    """
    # --- 递归解包 automatic_recovery ---
    recovery_items = data.get("automatic_recovery", [])
    recovery_warnings: List[str] = []

    if isinstance(recovery_items, list):
        for item in recovery_items:
            if isinstance(item, dict):
                rec_tool = item.get("recovery_tool", "")
                rec_error = item.get("error", "")
                if rec_error:
                    recovery_warnings.append(f"自动恢复失败 [{rec_tool}]: {rec_error}")
                elif rec_tool:
                    recovery_warnings.append(f"自动调用恢复工具: {rec_tool}")

    # --- 有 original_tool_result 时，先递归处理内层 ---
    if "original_tool_result" in data:
        inner = data["original_tool_result"]
        inner_tr = normalize_tool_result(
            inner,
            tool_name=tool_name,
            tool_category=tool_category,
            job_id=job_id,
            started_at=started_at,
        )
        # 添加 recovery warnings
        if recovery_warnings:
            inner_tr.warnings.extend(recovery_warnings)
        # 保留 outer 中可能有的额外字段
        if not inner_tr.provenance.job_id and data.get("job_id"):
            pass  # 不覆盖（provenance 中的 job_id 已在递归中处理）
        return inner_tr

    # --- 判断 status ---
    status = str(data.get("status", "")).lower()
    if status not in ("success", "error", "partial"):
        # 没有明确 status，视为成功
        status = "success"

    # --- 提取通用字段 ---
    message = str(data.get("message") or data.get("error_message") or "")
    if not message:
        if status == "error":
            message = str(data.get("stderr") or data.get("stdout") or "工具执行出错")
        elif status == "success":
            message = "分析完成"

    # --- 提取 output_files ---
    output_files: List[OutputFile] = []
    direct_files = data.get("output_files") or data.get("output_images") or data.get("output_pdfs") or []
    if isinstance(direct_files, list):
        for f in direct_files:
            if isinstance(f, dict):
                output_files.append(_coerce_output_file(f))
            elif isinstance(f, OutputFile):
                output_files.append(f)

    # --- 提取 errors / warnings ---
    errors: List[str] = []
    if isinstance(data.get("errors"), list):
        errors = [str(e) for e in data["errors"]]
    elif status == "error":
        error_msg = str(data.get("stderr") or data.get("message") or "")
        if error_msg:
            errors = [error_msg]

    warnings_list: List[str] = []
    if isinstance(data.get("warnings"), list):
        warnings_list = [str(w) for w in data["warnings"]]
    # 把 recovery warnings 合并进去
    warnings_list.extend(recovery_warnings)
    # 如果 returncode != 0 且有 stderr
    returncode = data.get("returncode")
    if returncode is not None and returncode != 0 and not errors:
        stderr = str(data.get("stderr") or "")
        if stderr.strip():
            warnings_list.append(f"R 进程返回码 {returncode}，stderr: {stderr[:500]}")

    # --- 构建 summary ---
    summary: Dict[str, Any] = {}
    # 从旧 dict 中迁移有意义的字段到 summary
    summary_keys = [
        "note", "file_path", "file_name", "shape", "columns",
        "total_columns", "columns_truncated", "preview_rows",
        "job_id", "job_dir", "returncode",
        "preprocess_info", "deg_count", "significant_count",
    ]
    for k in summary_keys:
        if k in data:
            summary[k] = data[k]

    # 如果 data 中有其他业务字段（status/message/output_files 等已处理的不重复放）
    already_handled = {
        "status", "message", "error_message", "output_files",
        "output_images", "output_pdfs", "errors", "warnings",
        "stdout", "stderr", "original_tool_result", "automatic_recovery",
        "rscript", "r_libs_user", "storage_dir", "upload_dir", "generated_dir",
        *summary_keys,
    }
    extra_summary = {k: v for k, v in data.items() if k not in already_handled}
    # 只保留 JSON 安全的字段
    for k, v in extra_summary.items():
        if k not in summary and _is_json_safe(v):
            summary[k] = v

    # --- 构建 provenance ---
    prov = ToolProvenance(
        tool_name=tool_name,
        tool_category=tool_category,
        job_id=job_id or str(data.get("job_id") or ""),
        started_at=started_at,
        finished_at=finished_at,
    )

    # 如果有 runtime 相关信息
    if data.get("runtime_seconds"):
        try:
            prov.runtime_seconds = float(data["runtime_seconds"])
        except (ValueError, TypeError):
            pass

    return ToolResult(
        status=status,
        message=message,
        summary=summary,
        output_files=output_files,
        warnings=warnings_list,
        errors=errors,
        provenance=prov,
    )


def _build_from_plain_value(
    value: Any,
    tool_name: str = "",
    tool_category: str = "",
    job_id: str = "",
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
) -> ToolResult:
    """非 dict/list/ToolResult 的返回值兜底处理。"""
    if value is None:
        return make_tool_result(
            status="success",
            message="工具执行完成（无返回值）",
            provenance=ToolProvenance(
                tool_name=tool_name,
                tool_category=tool_category,
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at or datetime.now().isoformat(),
            ),
        )

    msg = str(value)[:2000]
    return make_tool_result(
        status="success",
        message=msg[:200],
        summary={"raw_value": msg},
        provenance=ToolProvenance(
            tool_name=tool_name,
            tool_category=tool_category,
            job_id=job_id,
            started_at=started_at,
            finished_at=finished_at or datetime.now().isoformat(),
        ),
    )


def _extract_output_files_from_list(items: List[Any]) -> List[OutputFile]:
    """从 list 中尝试提取文件对象。"""
    files: List[OutputFile] = []
    for item in items:
        if isinstance(item, dict):
            # 如果 dict 有 name/url/relative_path 任一，视为文件
            if any(k in item for k in ("name", "url", "relative_path")):
                files.append(_coerce_output_file(item))
            elif "output_files" in item:
                nested = item["output_files"]
                if isinstance(nested, list):
                    for nf in nested:
                        if isinstance(nf, dict):
                            files.append(_coerce_output_file(nf))
        elif isinstance(item, OutputFile):
            files.append(item)
    return files


def _is_json_safe(value: Any) -> bool:
    """检查值是否可以安全地 JSON 序列化。"""
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return True
    except Exception:
        return False


# ============================================================
# 将 ToolResult 转为旧格式（向后兼容辅助）
# ============================================================

def tool_result_to_legacy_dict(tr: ToolResult) -> Dict[str, Any]:
    """
    将 ToolResult 转回旧工具返回的 dict 格式。

    用于需要兼容旧 extract_output_files / build_compact_tool_summary 的场景。
    """
    output_files_dicts: List[Dict[str, Any]] = []
    for f in tr.output_files:
        d = {
            "name": f.name,
            "url": f.url,
            "relative_path": f.relative_path,
        }
        if f.size_bytes is not None:
            d["size_bytes"] = f.size_bytes
        if f.file_type:
            d["type"] = f.file_type
        if f.description:
            d["description"] = f.description
        output_files_dicts.append(d)

    result: Dict[str, Any] = {
        "status": tr.status,
        "message": tr.message,
        "output_files": output_files_dicts,
    }

    if tr.summary:
        result.update(tr.summary)
    if tr.warnings:
        result["warnings"] = tr.warnings
    if tr.errors:
        result["errors"] = tr.errors

    return result
