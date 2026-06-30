import json
from app.tools.system_tools import scan_system_config

def get_system_info():
    """
    返回当前后端机器的环境信息
    """
    raw = scan_system_config()
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}