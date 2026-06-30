import re
from pathlib import Path
from typing import Any, Dict, List

from app.agent.bio_agent import run_bio_agent
from app.db import crud
from app.core.paths import STORAGE_DIR, GENERATED_DIR
from app.utils.file_utils import detect_file_type
from app.utils.response_formatter import (
    extract_generated_files_from_reply,
    append_markdown_if_missing
)

def extract_file_marker_from_message(content: str) -> str:
    """
    从前端消息里提取 [文件:xxx] 标记
    例如：
    发送的文件：[文件:test.csv] 请帮我分析
    """
    if not content:
        return ""

    match = re.search(r"\[文件:(.*?)\]", content)
    if match:
        return match.group(1).strip()
    return ""

def generate_session_title(first_user_message: str = "", first_uploaded_filename: str = "") -> str:
    """
    优先使用第一个上传文件名，否则使用第一句用户消息
    """
    if first_uploaded_filename:
        return first_uploaded_filename.strip()[:80]

    text = (first_user_message or "").strip()
    if not text:
        return "新会话"

    text = re.sub(r"发送的文件：\s*\[文件:.*?\]\s*", "", text).strip()
    text = text.replace("\n", " ").replace("\r", " ").strip()
    text = " ".join(text.split())
    text = text.lstrip("#*- ").strip()

    if not text:
        return "新会话"

    if len(text) > 30:
        text = text[:30] + "..."

    return text

def resolve_generated_files(file_refs: list):
    """
    根据模型回复里提到的文件名或相对路径，
    在 GENERATED_DIR 下递归查找真实文件。

    这是旧兜底逻辑：
    如果 Agent 没有显式返回 files，才靠文本解析找文件。
    """
    files = []
    seen = set()

    for ref in file_refs or []:
        if not ref:
            continue

        ref = str(ref).replace("\\", "/").strip()

        if ref.startswith("/files/"):
            ref = ref[len("/files/"):]

        if ref.startswith("generated/"):
            full_path = Path(STORAGE_DIR) / ref
            if full_path.exists() and full_path.is_file():
                relative_path = full_path.relative_to(STORAGE_DIR).as_posix()
                if relative_path not in seen:
                    seen.add(relative_path)
                    files.append({
                        "url": f"/files/{relative_path}",
                        "name": full_path.name,
                        "type": detect_file_type(full_path.name),
                        "relative_path": relative_path
                    })
            continue

        if "/" in ref:
            full_path = Path(GENERATED_DIR) / ref
            if full_path.exists() and full_path.is_file():
                relative_path = full_path.relative_to(STORAGE_DIR).as_posix()
                if relative_path not in seen:
                    seen.add(relative_path)
                    files.append({
                        "url": f"/files/{relative_path}",
                        "name": full_path.name,
                        "type": detect_file_type(full_path.name),
                        "relative_path": relative_path
                    })
            continue

        matches = [p for p in Path(GENERATED_DIR).rglob(ref) if p.is_file()]
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # 只取最新的少量文件，避免历史同名文件全被捞出来
        for path in matches[:3]:
            relative_path = path.relative_to(STORAGE_DIR).as_posix()
            if relative_path in seen:
                continue

            seen.add(relative_path)
            files.append({
                "url": f"/files/{relative_path}",
                "name": path.name,
                "type": detect_file_type(path.name),
                "relative_path": relative_path
            })

    return files
def normalize_agent_file(file_obj: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    统一 Agent / Tool 返回的文件结构，确保前端能识别。

    目标格式：
    {
        "url": "/files/generated/xxx/plot.png",
        "name": "plot.png",
        "type": "image",
        "relative_path": "generated/xxx/plot.png"
    }
    """
    if not isinstance(file_obj, dict):
        return None

    name = str(file_obj.get("name") or "").strip()
    relative_path = str(file_obj.get("relative_path") or "").strip()
    url = str(file_obj.get("url") or "").strip()
    path = str(file_obj.get("path") or "").strip()

    if url.startswith("http://") or url.startswith("https://"):
        # 如果是完整 URL，尽量从 /files/ 后面提 relative_path
        if "/files/" in url:
            relative_path = url.split("/files/", 1)[1].strip("/")
            url = f"/files/{relative_path}"

    if url.startswith("/files/") and not relative_path:
        relative_path = url[len("/files/"):].strip("/")

    if relative_path.startswith("/files/"):
        relative_path = relative_path[len("/files/"):].strip("/")

    relative_path = relative_path.replace("\\", "/")

    if path and not relative_path:
        try:
            p = Path(path)
            if p.exists():
                relative_path = p.relative_to(STORAGE_DIR).as_posix()
        except Exception:
            pass

    if relative_path and not url:
        url = f"/files/{relative_path}"

    if not name:
        if relative_path:
            name = Path(relative_path).name
        elif path:
            name = Path(path).name
        elif url:
            name = Path(url).name

    if not name and not relative_path and not url:
        return None

    file_type = str(file_obj.get("type") or file_obj.get("file_type") or "").strip()
    if not file_type:
        file_type = detect_file_type(name or relative_path or url)

    return {
        "url": url,
        "name": name,
        "type": file_type,
        "relative_path": relative_path
    }

def dedupe_files(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    文件去重。
    """
    result = []
    seen = set()

    for f in files or []:
        nf = normalize_agent_file(f)
        if not nf:
            continue

        key = (
            nf.get("relative_path", ""),
            nf.get("url", ""),
            nf.get("name", "")
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(nf)

    return result

def merge_files(*file_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并多个文件列表并去重。
    """
    merged = []
    for file_list in file_lists:
        merged.extend(file_list or [])
    return dedupe_files(merged)

def build_uploaded_files_context(session_id: str, attached_files: list) -> str:
    """
    把当前会话上传文件整理成给 Agent 的上下文文本
    """
    if not attached_files:
        return ""

    lines = [
        f"当前会话 session_id: {session_id}",
        "当前会话已上传文件如下："
    ]

    for idx, f in enumerate(attached_files, start=1):
        filename = f.get("filename", "")
        relative_path = f.get("relative_path") or f"uploads/{session_id}/{filename}"
        file_type = f.get("type", "other")
        abs_hint = str(Path(STORAGE_DIR) / relative_path)

        lines.append(
            f"{idx}. 文件名: {filename} | 类型: {file_type} | 相对路径: {relative_path} | 绝对路径参考: {abs_hint}"
        )

    lines.append("如果用户要求分析文件，请优先基于上述文件路径读取数据。")
    lines.append("不要声称“找不到文件”，除非你已经明确检查过这些路径不存在。")

    return "\n".join(lines)

def prepend_file_context(messages: list, file_context: str) -> list:
    """
    把文件上下文注入消息最前面
    """
    if not file_context:
        return messages

    return [
        {
            "role": "system",
            "content": file_context
        },
        *messages
    ]

def fallback_attached_files_from_db(db, session_id: str) -> list:
    """
    如果前端 attached_files 没传到，则尝试从数据库按 session 回查 upload 文件记录
    """
    results = []

    if not session_id:
        return results

    if hasattr(crud, "get_files_by_session"):
        try:
            db_files = crud.get_files_by_session(db, session_id)
            for f in db_files:
                if getattr(f, "source_type", "") != "upload":
                    continue
                results.append({
                    "filename": f.filename,
                    "relative_path": f.relative_path,
                    "type": getattr(f, "file_type", "other")
                })
            return results
        except Exception as e:
            print(f"⚠️ get_files_by_session 查询失败: {e}")

    upload_dir = Path(STORAGE_DIR) / "uploads" / session_id
    if upload_dir.exists() and upload_dir.is_dir():
        for p in sorted(upload_dir.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file():
                results.append({
                    "filename": p.name,
                    "relative_path": f"uploads/{session_id}/{p.name}",
                    "type": detect_file_type(p.name)
                })

    return results

def normalize_frontend_messages(messages: list) -> list:
    """
    标准化前端消息角色。
    前端可能用 ai，后端 OpenAI 格式需要 assistant。
    """
    standard_messages = []

    for msg in messages or []:
        frontend_role = msg.get("role", "user")
        safe_role = "assistant" if frontend_role == "ai" else frontend_role

        if safe_role not in ("user", "assistant", "system"):
            safe_role = "user"

        standard_messages.append({
            "role": safe_role,
            "content": str(msg.get("content", ""))
        })

    return standard_messages

def append_files_markdown(answer: str, files: List[Dict[str, Any]]) -> str:
    """
    确保回答里包含文件链接。

    注意：
    前端通常主要看 response.files 来展示图片。
    这里追加 markdown 是为了让聊天气泡里也能点开文件。
    """
    answer = str(answer or "")

    for f in files or []:
        name = f.get("name", "")
        relative_path = f.get("relative_path", "")

        if not name or not relative_path:
            continue

        answer = append_markdown_if_missing(
            reply=answer,
            filename=name,
            relative_path=relative_path
        )

    return answer

async def handle_chat(db, session_id: str, messages: list, attached_files: list | None = None):
    """
    聊天总业务流程：
    1. 创建会话
    2. 标准化前端消息角色
    3. 自动设置会话标题
    4. 注入当前会话上传文件上下文
    5. 调 Agent，并传入 session_id
    6. 直接接收 Agent 返回的 files，避免前端找不到图片
    7. 兜底从 answer 文本中解析文件
    8. 保存聊天记录和文件记录
    9. 返回 reply + files
    """
    if not session_id:
        raise ValueError("handle_chat 缺少 session_id，禁止使用空 session_id 发起会话，避免记忆串号。")

    crud.create_session(db, session_id=session_id)

    attached_files = attached_files or []
    standard_messages = normalize_frontend_messages(messages)

    if not attached_files:
        attached_files = fallback_attached_files_from_db(db, session_id)

    print(f"🧾 handle_chat session_id={session_id}")
    print(f"🧾 attached_files={attached_files}")

    session_obj = crud.get_session(db, session_id)
    if session_obj and (not session_obj.title or session_obj.title == "新会话"):
        first_uploaded_filename = attached_files[0]["filename"] if attached_files else ""

        first_user_message = ""
        embedded_file_name = ""

        for msg in standard_messages:
            if msg["role"] == "user" and msg["content"].strip():
                first_user_message = msg["content"].strip()
                embedded_file_name = extract_file_marker_from_message(first_user_message)
                break

        title = generate_session_title(
            first_user_message=first_user_message,
            first_uploaded_filename=first_uploaded_filename or embedded_file_name
        )
        crud.ensure_session_title(db, session_id, title)

    file_context = build_uploaded_files_context(session_id, attached_files)
    agent_messages = prepend_file_context(standard_messages, file_context)

    print("🧠 注入给 Agent 的文件上下文：")
    print(file_context if file_context else "(空)")

    agent_result = await run_bio_agent(
        agent_messages,
        session_id=session_id
    )

    # 兼容旧版 run_bio_agent 返回字符串；
    # 新版返回 {"answer": "...", "files": [...]}
    if isinstance(agent_result, dict):
        answer = str(agent_result.get("answer") or "")
        agent_files = agent_result.get("files") or []
    else:
        answer = str(agent_result or "")
        agent_files = []

    answer = answer.encode("utf-8", "ignore").decode("utf-8")
    answer = answer.replace("\x00", "")

   # 旧兜底：只有当 Agent 没有显式返回 files 时，才从最终文本里解析文件。
    if agent_files:
        text_files = []
    else:
        file_refs = extract_generated_files_from_reply(answer)
        text_files = resolve_generated_files(file_refs)

    # 新主链路：优先使用 Agent / Executor 真实返回的 output_files。
    files = merge_files(agent_files, text_files)

    print(
        "📦 handle_chat files returned to frontend="
        + str(files[:20])
    )

    answer = append_files_markdown(answer, files)

    if standard_messages:
        last_user_msg = standard_messages[-1]
        if last_user_msg["role"] == "user":
            crud.save_message(db, session_id, "user", last_user_msg["content"])

    crud.save_message(db, session_id, "assistant", answer)

    for f in files:
        relative_path = f.get("relative_path", "")
        name = f.get("name", "")
        file_type = f.get("type", "other")

        if not relative_path or not name:
            continue

        crud.save_file_record(
            db=db,
            session_id=session_id,
            filename=name,
            relative_path=relative_path,
            file_type=file_type,
            source_type="generated"
        )

    current_session = crud.get_session(db, session_id)

    return {
        "reply": answer,
        "files": files,
        "session_id": session_id,
        "title": current_session.title if current_session else "新会话"
    }