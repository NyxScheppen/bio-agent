def detect_file_type(filename: str) -> str:
    """
    根据扩展名判断文件类型
    """
    ext = filename.split(".")[-1].lower()

    if ext in {"png", "jpg", "jpeg", "svg"}:
        return "image"
    if ext in {"csv", "xlsx", "tsv"}:
        return "table"
    if ext in {"txt", "rds", "pdb"}:
        return "text"
    return "other"