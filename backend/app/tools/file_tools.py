import os
import csv
import gzip
import json
import pandas as pd

from app.agent.tool_registry import register_tool
from app.utils.file_resolver import resolve_file_path, debug_file_context


MAX_PREVIEW_ROWS = 10
MAX_RETURN_COLUMNS = 80


def _safe_file_size(real_path):
    try:
        size_bytes = os.path.getsize(real_path)
        if size_bytes < 1024:
            return {
                "bytes": size_bytes,
                "human": f"{size_bytes} B"
            }
        if size_bytes < 1024 * 1024:
            return {
                "bytes": size_bytes,
                "human": f"{size_bytes / 1024:.2f} KB"
            }
        if size_bytes < 1024 * 1024 * 1024:
            return {
                "bytes": size_bytes,
                "human": f"{size_bytes / 1024 / 1024:.2f} MB"
            }
        return {
            "bytes": size_bytes,
            "human": f"{size_bytes / 1024 / 1024 / 1024:.2f} GB"
        }
    except Exception:
        return {
            "bytes": None,
            "human": "unknown"
        }


def _truncate_columns(columns, max_columns=MAX_RETURN_COLUMNS):
    columns = list(columns)
    return {
        "columns": columns[:max_columns],
        "total_columns": len(columns),
        "columns_truncated": len(columns) > max_columns
    }


def _count_text_table_rows(real_path, compressed=False):
    """
    统计文本表格数据行数。
    返回值不包含 header 行。
    """
    opener = gzip.open if compressed else open

    try:
        with opener(real_path, "rt", encoding="utf-8", errors="replace", newline="") as f:
            total_lines = sum(1 for _ in f)

        return max(total_lines - 1, 0)
    except Exception:
        return None


def _count_csv_rows(real_path):
    """
    CSV 行数统计。
    不把整个文件读入内存。
    返回值不包含 header 行。
    """
    try:
        with open(real_path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            total_rows = sum(1 for _ in reader)

        return max(total_rows - 1, 0)
    except Exception:
        return _count_text_table_rows(real_path, compressed=False)


def _read_table_preview(real_path, nrows=5):
    """
    只读取表格前几行，不读取全表。
    """
    suffix = real_path.suffix.lower()
    name_lower = real_path.name.lower()

    if name_lower.endswith(".csv"):
        df = pd.read_csv(real_path, nrows=nrows)
        total_rows = _count_csv_rows(real_path)
        return df, total_rows, "csv"

    if name_lower.endswith(".tsv") or name_lower.endswith(".txt"):
        df = pd.read_csv(real_path, sep="\t", nrows=nrows)
        total_rows = _count_text_table_rows(real_path, compressed=False)
        return df, total_rows, "tsv/txt"

    if name_lower.endswith(".csv.gz"):
        df = pd.read_csv(real_path, compression="gzip", nrows=nrows)
        total_rows = _count_text_table_rows(real_path, compressed=True)
        return df, total_rows, "csv.gz"

    if name_lower.endswith(".tsv.gz") or name_lower.endswith(".txt.gz"):
        df = pd.read_csv(real_path, sep="\t", compression="gzip", nrows=nrows)
        total_rows = _count_text_table_rows(real_path, compressed=True)
        return df, total_rows, "tsv/txt.gz"

    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(real_path, nrows=nrows)

        # Excel 精确统计总行数比较贵，这里用 pandas 只读列信息会较麻烦。
        # 为了避免超大 xlsx 卡死，先返回 preview shape。
        total_rows = None
        return df, total_rows, "excel"

    raise ValueError(f"暂不支持预览该文件类型: {real_path.name}")


def _build_preview_response(real_path, df, total_rows, file_type, nrows):
    col_info = _truncate_columns(df.columns.tolist())

    if total_rows is None:
        shape = {
            "rows": None,
            "columns": len(df.columns),
            "note": "未统计总行数，仅返回预览。"
        }
    else:
        shape = {
            "rows": int(total_rows),
            "columns": len(df.columns)
        }

    return {
        "status": "success",
        "file_path": str(real_path),
        "file_name": real_path.name,
        "file_type": file_type,
        "file_size": _safe_file_size(real_path),
        "shape": shape,
        "columns": col_info["columns"],
        "total_columns": col_info["total_columns"],
        "columns_truncated": col_info["columns_truncated"],
        "preview_rows": min(nrows, len(df)),
        "preview": df.head(nrows).where(pd.notnull(df), None).to_dict(orient="records"),
        "note": (
            "为避免请求体过大，本工具只返回少量预览数据，不返回完整表格。"
            "完整数据请通过 file_path 对应文件继续分析或下载。"
        )
    }


@register_tool(
    name="read_csv_data",
    description="安全读取 CSV 文件：只返回文件形状、列名和前几行预览，不返回完整数据，避免大文件导致接口 413。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件名或路径，例如 test.csv"
            },
            "nrows": {
                "type": "integer",
                "description": "预览行数，默认 5，最大 10",
                "default": 5
            }
        },
        "required": ["file_path"]
    }
)
def read_csv_data(file_path: str, nrows: int = 5, session_id: str = None):
    real_path = resolve_file_path(file_path, session_id)

    if not real_path.exists():
        return {
            "status": "error",
            "message": f"文件不存在：{file_path}",
            "debug": debug_file_context(file_path, session_id)
        }

    try:
        nrows = int(nrows or 5)
        nrows = max(1, min(nrows, MAX_PREVIEW_ROWS))

        name_lower = real_path.name.lower()
        if not name_lower.endswith(".csv") and not name_lower.endswith(".csv.gz"):
            return {
                "status": "error",
                "message": f"read_csv_data 仅支持 CSV / CSV.GZ 文件，当前文件是：{real_path.name}",
                "suggestion": "如果要预览 tsv/txt/xlsx，请使用 preview_table_file。"
            }

        df, total_rows, file_type = _read_table_preview(real_path, nrows=nrows)
        return _build_preview_response(real_path, df, total_rows, file_type, nrows)

    except Exception as e:
        return {
            "status": "error",
            "message": f"读取 CSV 失败：{str(e)}",
            "debug": debug_file_context(file_path, session_id)
        }


@register_tool(
    name="load_large_bio_data",
    description="读取大型生信文件（txt/csv/gz），适合 GEO series_matrix 预读。只返回前 20 行，避免大文件撑爆上下文。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件名，例如 GSE84402_series_matrix.txt.gz"
            }
        },
        "required": ["file_path"]
    }
)
def load_large_bio_data(file_path: str, session_id: str = None):
    real_path = resolve_file_path(file_path, session_id)

    if not real_path.exists():
        debug = debug_file_context(file_path, session_id)
        return (
            f"❌ 找不到文件: {file_path}\n"
            f"解析后路径: {debug['resolved_path']}\n"
            f"当前工作目录: {debug['cwd']}"
        )

    try:
        if str(real_path).endswith(".gz"):
            with gzip.open(real_path, "rt", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    lines.append(line.rstrip("\n"))
                    if i >= 19:
                        break

            return {
                "status": "success",
                "file_path": str(real_path),
                "file_name": real_path.name,
                "file_size": _safe_file_size(real_path),
                "preview_line_count": len(lines),
                "preview": lines,
                "note": "仅返回前 20 行预览，避免大型 GEO 文件导致请求体过大。"
            }

        with open(real_path, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                lines.append(line.rstrip("\n"))
                if i >= 19:
                    break

        return {
            "status": "success",
            "file_path": str(real_path),
            "file_name": real_path.name,
            "file_size": _safe_file_size(real_path),
            "preview_line_count": len(lines),
            "preview": lines,
            "note": "仅返回前 20 行预览，避免大型文件导致请求体过大。"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"读取失败: {str(e)}",
            "debug": debug_file_context(file_path, session_id)
        }


@register_tool(
    name="preview_table_file",
    description="安全预览表格文件（csv/tsv/txt/xlsx/gz），返回真实行数、列名、前几行，不返回完整数据。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件名或路径，例如 expression_matrix.csv"
            },
            "nrows": {
                "type": "integer",
                "description": "预览行数，默认 5，最大 10",
                "default": 5
            }
        },
        "required": ["file_path"]
    }
)
def preview_table_file(file_path: str, nrows: int = 5, session_id: str = None):
    real_path = resolve_file_path(file_path, session_id)

    if not real_path.exists():
        return {
            "status": "error",
            "message": f"文件不存在: {file_path}",
            "debug": debug_file_context(file_path, session_id)
        }

    try:
        nrows = int(nrows or 5)
        nrows = max(1, min(nrows, MAX_PREVIEW_ROWS))

        df, total_rows, file_type = _read_table_preview(real_path, nrows=nrows)
        return _build_preview_response(real_path, df, total_rows, file_type, nrows)

    except Exception as e:
        return {
            "status": "error",
            "message": f"预览失败: {str(e)}",
            "debug": debug_file_context(file_path, session_id)
        }