def detect_file_type(filename: str) -> str:
    """
    根据扩展名判断文件类型。

    委托 tool_result._guess_file_type，保证全项目只用一个 file_type 词表
    （image/table/text/pdf/r_data/archive/other）。
    """
    from app.agent.tool_result import _guess_file_type
    return _guess_file_type(filename)


def build_file_url(relative_path: str) -> str:
    """
    根据相对路径生成可访问 URL。

    例如 generated/pheno_analysis/a.png -> /files/generated/pheno_analysis/a.png
    """
    clean_path = str(relative_path).replace("\\", "/").lstrip("/")
    return f"/files/{clean_path}"