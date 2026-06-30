import re
from app.utils.file_utils import detect_file_type

def extract_generated_files_from_reply(reply: str):
    """
    从模型回复中提取文件引用。
    支持：
    - 文件名：a.png
    - 相对路径：pheno_analysis/a.png
    - generated 开头路径：generated/pheno_analysis/a.png
    """
    if not reply:
        return []

    pattern = r'[\w\-./\\]+\.(?:png|jpg|jpeg|svg|csv|txt|rds|xlsx|tsv|pdb|pdf)'
    all_files = re.findall(pattern, reply)

    clean_files = []
    seen = set()

    for f in all_files:
        ref = str(f).strip().replace("\\", "/")

        # 去掉开头的 ./ 之类
        while ref.startswith("./"):
            ref = ref[2:]

        # 防止出现 /generated/... 这种写法
        if ref.startswith("/generated/"):
            ref = ref[1:]

        if ref not in seen:
            clean_files.append(ref)
            seen.add(ref)

    return clean_files

def build_file_url(relative_path: str) -> str:
    """
    根据相对路径生成可访问 URL
    例如：
    generated/pheno_analysis/a.png
    -> /files/generated/pheno_analysis/a.png
    """
    clean_path = str(relative_path).replace("\\", "/").lstrip("/")
    return f"/files/{clean_path}"

def append_markdown_if_missing(reply: str, filename: str, relative_path: str) -> str:
    """
    如果回复里还没有对应文件 URL，则自动补一个 markdown 链接。
    图片补图片 markdown，其它补下载链接。
    """
    url = build_file_url(relative_path)
    file_type = detect_file_type(filename)

    if url in reply:
        return reply

    if file_type == "image":
        return reply + f"\n![{filename}]({url})\n"
    else:
        return reply + f"\n[{filename}]({url})\n"

def build_file_list(file_refs: list):
    """
    兼容保留函数：
    如果传入的是相对路径列表，则构造前端 files。
    但方案 A 下建议优先在 chat_service 中解析真实文件路径。
    """
    files = []
    for ref in file_refs:
        clean_ref = str(ref).replace("\\", "/").strip()
        name = clean_ref.split("/")[-1]

        files.append({
            "url": build_file_url(clean_ref),
            "name": name,
            "type": detect_file_type(name),
            "relative_path": clean_ref
        })

    return files