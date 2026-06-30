import os
import json
import platform
import shutil
import subprocess

from app.agent.tool_registry import register_tool
from app.core.runtime_paths import (
    PROJECT_ROOT,
    BACKEND_ROOT,
    UPLOAD_DIR,
    GENERATED_DIR,
    R_LIBS_USER,
    find_rscript,
    check_rscript_version,
)

def _get_command_version(command, version_arg="--version"):
    try:
        result = subprocess.run(
            [command, version_arg],
            capture_output=True,
            text=True,
            timeout=10
        )
        text = (result.stdout or result.stderr).strip().split("\n")[0]
        return text
    except Exception:
        return None

@register_tool(
    name="scan_system_config",
    description="扫描当前后端运行环境的系统配置，包括 Python、R、Git、平台、CPU、UPLOAD_DIR、R_LIBS_USER 等",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    category="system",
    tags=["environment", "r", "rscript", "diagnostic"]
)
def scan_system_config():
    """
    注意：这里扫描的是当前运行后端的机器环境，不是浏览器访问者本机。
    """
    rscript_path = find_rscript()

    info = {
        "platform": platform.platform(),
        "python_path": shutil.which("python"),
        "python_version": platform.python_version(),

        "project_root": str(PROJECT_ROOT),
        "backend_root": str(BACKEND_ROOT),
        "current_working_directory": os.getcwd(),

        "upload_dir": str(UPLOAD_DIR),
        "upload_dir_exists": UPLOAD_DIR.exists(),

        "generated_dir": str(GENERATED_DIR),
        "generated_dir_exists": GENERATED_DIR.exists(),

        "r_libs_user": str(R_LIBS_USER),
        "r_libs_user_exists": R_LIBS_USER.exists(),

        "rscript_path": rscript_path,
        "rscript_exists": bool(rscript_path),
        "rscript_version": check_rscript_version(),

        "git_path": shutil.which("git"),
        "git_version": _get_command_version("git", "--version"),
        "cpu_count": os.cpu_count(),

        "env_UPLOAD_DIR": os.environ.get("UPLOAD_DIR", ""),
        "env_R_LIBS_USER": os.environ.get("R_LIBS_USER", ""),
        "env_RSCRIPT_PATH": os.environ.get("RSCRIPT_PATH", ""),
        "path_head": os.environ.get("PATH", "")[:1000],
    }

    return json.dumps(info, ensure_ascii=False, indent=2)