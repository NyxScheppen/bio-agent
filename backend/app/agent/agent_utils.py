import json
import inspect
import re
from typing import Any, Dict, List, Tuple, Union

from app.agent.agent_constants import (
    MAX_TOOL_CONTENT_CHARS,
    MAX_FINAL_ANSWER_CHARS,
    IMAGE_EXTS,
    PDF_EXTS,
    DOWNLOADABLE_EXTS,
)

# 延迟导入，避免循环引用
_TOOL_RESULT_IMPORTED = False
ToolResult = None
OutputFile = None


def _ensure_tool_result_types():
    """延迟导入 ToolResult 类型，避免循环引用。"""
    global _TOOL_RESULT_IMPORTED, ToolResult, OutputFile
    if not _TOOL_RESULT_IMPORTED:
        from app.agent.tool_result import ToolResult as _ToolResult, OutputFile as _OutputFile
        ToolResult = _ToolResult
        OutputFile = _OutputFile
        _TOOL_RESULT_IMPORTED = True


def safe_json_loads(value: str) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]

    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except Exception:
        return str(value)


def parse_tool_result(tool_result: Any) -> Any:
    if isinstance(tool_result, dict):
        return tool_result

    if isinstance(tool_result, str):
        s = tool_result.strip()
        if not s:
            return ""
        try:
            return json.loads(s)
        except Exception:
            return tool_result

    return tool_result


def safe_message_content(value: Any, max_chars: int = MAX_TOOL_CONTENT_CHARS) -> str:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(to_jsonable(value), ensure_ascii=False, default=str)
        except Exception:
            text = str(value)

    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n...[工具返回内容过长，已截断。完整结果请查看生成文件或使用预览工具。]"

    return text


def sanitize_final_answer(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r":contentReference\[[^\]]+\]\{?[^}\n]*\}?", "", text)
    text = re.sub(r"\[oaicite:[^\]]+\]", "", text)

    if len(text) > MAX_FINAL_ANSWER_CHARS:
        text = text[:MAX_FINAL_ANSWER_CHARS] + "\n\n...[回答过长，已截断]"

    return text.strip()


def inject_runtime_args(func, function_args: dict, session_id: str = None) -> dict:
    if function_args is None:
        function_args = {}

    try:
        sig = inspect.signature(func)
        params = sig.parameters
        if session_id and "session_id" in params:
            function_args["session_id"] = session_id
    except Exception:
        pass

    return function_args


def _normalize_output_file_item(file_obj: Any) -> Dict[str, Any] | None:
    """
    尽量把工具返回的文件对象归一化。
    允许字段名有轻微差异，但最终至少保留：
    - name
    - url
    - relative_path

    支持：
    - dict（旧格式）
    - OutputFile（Pydantic 模型）
    """
    if file_obj is None:
        return None

    # 处理 Pydantic OutputFile 对象
    if not isinstance(file_obj, (dict, str, int, float, bool, list, type(None))):
        if hasattr(file_obj, "model_dump"):
            file_obj = file_obj.model_dump()
        elif hasattr(file_obj, "dict"):
            file_obj = file_obj.dict()
        else:
            return None

    if not isinstance(file_obj, dict):
        return None

    name = str(file_obj.get("name") or "").strip()
    url = str(file_obj.get("url") or "").strip()
    relative_path = str(file_obj.get("relative_path") or "").strip()
    path = str(file_obj.get("path") or "").strip()
    size_bytes = file_obj.get("size_bytes", "")

    if not name and relative_path:
        name = relative_path.replace("\\", "/").split("/")[-1]
    if not name and path:
        name = path.replace("\\", "/").split("/")[-1]
    if not name and url:
        name = url.split("?")[0].rstrip("/").split("/")[-1]

    if url.startswith("/files/") and not relative_path:
        relative_path = url[len("/files/"):].strip("/")

    if relative_path.startswith("/files/"):
        relative_path = relative_path[len("/files/"):].strip("/")

    if relative_path and not url:
        url = f"/files/{relative_path}"

    if not name and not url and not relative_path:
        return None

    normalized = {
        "name": name,
        "url": url,
        "relative_path": relative_path,
    }

    if size_bytes != "":
        normalized["size_bytes"] = size_bytes

    # 保留原始可能有用字段
    for key in ["type", "file_type", "path"]:
        if key in file_obj and file_obj.get(key) not in (None, ""):
            normalized[key] = file_obj.get(key)

    return normalized


def _dedupe_output_files(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []

    for f in files or []:
        nf = _normalize_output_file_item(f)
        if not nf:
            continue

        key = (
            str(nf.get("relative_path", "")),
            str(nf.get("url", "")),
            str(nf.get("name", "")),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(nf)

    return result


def extract_output_files(tool_result: Any) -> List[Dict[str, Any]]:
    """
    递归提取工具返回中的 output_files。

    支持：
    1. ToolResult 对象（Phase 1 标准格式）
    2. dict 直接返回
    3. JSON 字符串
    4. list 嵌套
    5. automatic_recovery 包装
    6. original_tool_result / result / data 等嵌套包装
    """
    if tool_result is None:
        return []

    # --- 处理标准 ToolResult 对象 ---
    if isinstance(tool_result, type(None)):
        return []
    if not isinstance(tool_result, (str, int, float, bool, list, dict)):
        # 可能是 ToolResult 或其他自定义对象
        if hasattr(tool_result, "output_files"):
            files = []
            ofs = getattr(tool_result, "output_files", [])
            for f in (ofs or []):
                if isinstance(f, dict):
                    files.append(f)
                elif hasattr(f, "model_dump"):
                    files.append(f.model_dump())
                elif hasattr(f, "dict"):
                    files.append(f.dict())
            return _dedupe_output_files(files)

    # 先尽量解析字符串 JSON
    data = parse_tool_result(tool_result)

    if isinstance(data, list):
        files = []
        for item in data:
            files.extend(extract_output_files(item))
        return _dedupe_output_files(files)

    if not isinstance(data, dict):
        return []

    files = []

    # 1. 直接 output_files
    direct_files = data.get("output_files", [])
    if isinstance(direct_files, list):
        for item in direct_files:
            if isinstance(item, dict):
                files.append(item)
            elif hasattr(item, "model_dump"):
                # Pydantic v2
                files.append(item.model_dump())
            elif hasattr(item, "dict"):
                # Pydantic v1
                files.append(item.dict())

    # 2. 某些工具可能返回 output_images / output_pdfs
    for key in ["output_images", "output_pdfs"]:
        extra_files = data.get(key, [])
        if isinstance(extra_files, list):
            for item in extra_files:
                if isinstance(item, dict):
                    files.append(item)
                elif hasattr(item, "model_dump"):
                    files.append(item.model_dump())

    # 3. 递归检查常见嵌套字段
    nested_keys = [
        "original_tool_result",
        "result",
        "tool_result",
        "data",
        "payload",
        "response",
        "automatic_recovery",
    ]

    for key in nested_keys:
        if key in data:
            files.extend(extract_output_files(data.get(key)))

    return _dedupe_output_files(files)


def split_output_files(output_files: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    image_files = []
    pdf_files = []
    downloadable_files = []

    for f in output_files:
        name = str(f.get("name", "") or "")
        url = str(f.get("url", "") or "")
        lower_name = name.lower()

        if not name or not url:
            continue

        if lower_name.endswith(IMAGE_EXTS):
            image_files.append(f)
        if lower_name.endswith(PDF_EXTS):
            pdf_files.append(f)
        if lower_name.endswith(DOWNLOADABLE_EXTS):
            downloadable_files.append(f)

    return image_files, pdf_files, downloadable_files


def build_file_display_hint(output_files: List[Dict[str, Any]]) -> str:
    if not output_files:
        return ""

    image_files, pdf_files, downloadable_files = split_output_files(output_files)

    lines = []
    lines.append("")
    lines.append("【真实生成文件提示】")
    lines.append("下面这些文件来自工具返回的 output_files。")
    lines.append("只有这些文件可以被声称为已生成。")
    lines.append("不要编造不存在的图片、PDF 或下载链接。")
    lines.append("如果用户要求显示图片，必须优先使用下面真实图片 url，以 Markdown 图片格式展示。")

    if image_files:
        lines.append("")
        lines.append("可直接在对话中展示的图片：")
        for f in image_files:
            name = str(f.get("name", "image"))
            url = str(f.get("url", ""))
            size = f.get("size_bytes", "")
            size_part = f"，大小 {size} bytes" if size != "" else ""
            lines.append(f"- {name}{size_part}")
            lines.append(f"  Markdown展示：![{name}]({url})")
            lines.append(f"  下载链接：[{name}]({url})")
    else:
        lines.append("")
        lines.append("本次 output_files 中没有发现 png/jpg/jpeg/svg/gif/webp 图片文件。")
        lines.append("如果用户要求显示图片，不能说图片已生成，应说明没有发现图片文件，并重新运行画图代码。")

    if pdf_files:
        lines.append("")
        lines.append("可下载 PDF：")
        for f in pdf_files:
            name = str(f.get("name", "file.pdf"))
            url = str(f.get("url", ""))
            lines.append(f"- [{name}]({url})")

    other_downloads = []
    for f in downloadable_files:
        name = str(f.get("name", ""))
        lower = name.lower()
        if not lower.endswith(IMAGE_EXTS) and not lower.endswith(PDF_EXTS):
            other_downloads.append(f)

    if other_downloads:
        lines.append("")
        lines.append("其他可下载结果文件：")
        for f in other_downloads:
            name = str(f.get("name", "file"))
            url = str(f.get("url", ""))
            lines.append(f"- [{name}]({url})")

    lines.append("")
    lines.append("最终回复要求：")
    lines.append("1. 如果有图片，必须使用：![图片说明](真实url)")
    lines.append("2. 下载链接必须使用：[文件名](真实url)")
    lines.append("3. 不要输出 :contentReference、oaicite、index 等引用占位符")
    lines.append("4. 不要把 JSON 元数据当作图片或下载文件")
    lines.append("5. 如果没有图片文件，必须明确说没有发现图片，不要假装生成成功")

    return "\n".join(lines)


def build_compact_tool_summary(tool_result: Any) -> str:
    # --- 处理标准 ToolResult 对象 ---
    if not isinstance(tool_result, (str, int, float, bool, list, dict, type(None))):
        if hasattr(tool_result, "model_dump"):
            # Pydantic v2
            data = tool_result.model_dump()
        elif hasattr(tool_result, "dict"):
            # Pydantic v1
            data = tool_result.dict()
        elif hasattr(tool_result, "output_files"):
            data = {
                "status": getattr(tool_result, "status", ""),
                "message": getattr(tool_result, "message", ""),
                "output_files": [f.model_dump() if hasattr(f, "model_dump") else f for f in (getattr(tool_result, "output_files", None) or [])],
            }
        else:
            return safe_message_content(str(tool_result))
    else:
        data = parse_tool_result(tool_result)

    if not isinstance(data, dict):
        return safe_message_content(data)

    compact = {}

    for key in [
        "status",
        "message",
        "error_message",
        "job_id",
        "job_dir",
        "note",
        "file_path",
        "file_name",
        "shape",
        "columns",
        "total_columns",
        "columns_truncated",
        "preview_rows",
        "preview",
        "output_files",
        "output_images",
        "output_pdfs",
        "warnings",
        "errors",
    ]:
        if key in data:
            compact[key] = data[key]

    if "stdout" in data:
        compact["stdout"] = safe_message_content(data.get("stdout"), max_chars=3000)
    if "stderr" in data:
        compact["stderr"] = safe_message_content(data.get("stderr"), max_chars=3000)

    if not compact:
        compact = data

    return safe_message_content(compact)


def maybe_add_markdown_guidance(messages: list):
    messages.append({
        "role": "system",
        "content": (
            "【输出格式提醒】\n"
            "如果需要输出 Markdown 表格，必须使用标准多行表格格式，例如：\n\n"
            "| 文件 | 说明 |\n"
            "|---|---|\n"
            "| result.csv | 结果表 |\n\n"
            "表格前后保留空行。不要把整张表压缩成一行。"
        )
    })


def extract_json_object(text: str) -> Dict[str, Any]:
    if not text:
        return {}

    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            return {}

    return {}

def get_real_image_urls(output_files: List[Dict[str, Any]]) -> set:
    urls = set()

    image_suffixes = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp")

    for f in output_files or []:
        if not isinstance(f, dict):
            continue

        name = str(f.get("name", "") or "").lower()
        url = str(f.get("url", "") or "")

        if not url:
            continue

        if name.endswith(image_suffixes) or url.lower().split("?")[0].endswith(image_suffixes):
            urls.add(url)

    return urls

def remove_fake_markdown_images(text: str, output_files: List[Dict[str, Any]]) -> str:
    if not text:
        return ""

    real_urls = get_real_image_urls(output_files)
    image_pattern = r"!\[([^\]]*)\]\(([^)]+)\)"

    removed = []

    def repl(match):
        alt = match.group(1)
        url = match.group(2).strip()

        if url in real_urls:
            return match.group(0)

        removed.append({"alt": alt, "url": url})
        return ""

    cleaned = re.sub(image_pattern, repl, text)

    if removed:
        cleaned = cleaned.strip()
        cleaned += (
            "\n\n注意：有图片引用未出现在真实 output_files 中，我已经拦截。"
            "只有工具真实返回的图片链接才能展示。"
        )

    return cleaned.strip()