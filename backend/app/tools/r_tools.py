import os
import uuid
import subprocess
from pathlib import Path

from app.agent.tool_registry import register_tool
from app.core.runtime_paths import (
    PROJECT_ROOT,
    STORAGE_DIR,
    GENERATED_DIR,
    UPLOAD_DIR,
    R_LIBS_USER,
    find_rscript,
    build_r_subprocess_env,
)

MAX_R_OUTPUT_CHARS = 12000


def _truncate_text(text: str, max_chars: int = MAX_R_OUTPUT_CHARS) -> str:
    if text is None:
        return ""

    text = str(text)
    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n...[R 输出过长，已截断。完整结果请优先查看生成文件。]"


def _normalize_timeout(timeout) -> int:
    try:
        timeout = int(timeout)
    except Exception:
        timeout = 300

    if timeout < 10:
        return 10
    if timeout > 3600:
        return 3600
    return timeout


def _normalize_job_subdir(job_subdir: str = None) -> str:
    if not job_subdir:
        return ""

    job_subdir = str(job_subdir).strip()
    if not job_subdir:
        return ""

    if "/" in job_subdir or "\\" in job_subdir or ".." in job_subdir:
        return ""

    return job_subdir


def _as_r_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def collect_output_files(job_dir: Path):
    files = []

    for p in job_dir.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel_to_generated = p.relative_to(GENERATED_DIR).as_posix()
            url = f"/files/generated/{rel_to_generated}"
        except Exception:
            url = ""

        files.append({
            "name": p.name,
            "path": str(p),
            "relative_path": f"generated/{p.relative_to(GENERATED_DIR).as_posix()}" if p.is_relative_to(GENERATED_DIR) else str(p.relative_to(job_dir).as_posix()),
            "url": url,
            "size_bytes": p.stat().st_size,
        })

    return files


@register_tool(
    name="run_r_analysis",
    description="执行 R 代码进行生信分析。系统会自动创建本次任务输出目录，并返回生成文件列表。",
    parameters={
        "type": "object",
        "properties": {
            "r_code": {
                "type": "string",
                "description": "纯 R 代码"
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 300",
                "default": 300
            },
            "job_subdir": {
                "type": "string",
                "description": "可选，输出子目录名；为空时自动生成 job_id",
                "default": ""
            }
        },
        "required": ["r_code"]
    },
    timeout=3600,
    max_memory_mb=8192,
)
def run_r_analysis(r_code: str, timeout: int = 300, job_subdir: str = None):
    rscript = find_rscript()

    if not rscript:
        return {
            "status": "error",
            "message": "找不到 Rscript。请检查 R 是否安装，或设置 RSCRIPT_PATH。",
            "debug": {
                "project_root": str(PROJECT_ROOT),
                "storage_dir": str(STORAGE_DIR),
                "upload_dir": str(UPLOAD_DIR),
                "generated_dir": str(GENERATED_DIR),
                "r_libs_user": str(R_LIBS_USER),
                "path": os.environ.get("PATH", ""),
            },
        }

    timeout = _normalize_timeout(timeout)
    safe_job_subdir = _normalize_job_subdir(job_subdir)

    job_id = safe_job_subdir or f"r_job_{uuid.uuid4().hex[:12]}"
    job_dir = GENERATED_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    script_path = job_dir / "analysis.R"

    r_prelude = f'''
options(encoding = "UTF-8")

PROJECT_ROOT <- normalizePath("{_as_r_path(PROJECT_ROOT)}", winslash = "/", mustWork = FALSE)
STORAGE_DIR <- normalizePath("{_as_r_path(STORAGE_DIR)}", winslash = "/", mustWork = FALSE)
UPLOAD_DIR <- normalizePath("{_as_r_path(UPLOAD_DIR)}", winslash = "/", mustWork = FALSE)
GENERATED_ROOT <- normalizePath("{_as_r_path(GENERATED_DIR)}", winslash = "/", mustWork = FALSE)
GENERATED_DIR <- normalizePath("{_as_r_path(job_dir)}", winslash = "/", mustWork = FALSE)
R_LIBS_USER <- normalizePath("{_as_r_path(R_LIBS_USER)}", winslash = "/", mustWork = FALSE)

Sys.setenv(PROJECT_ROOT = PROJECT_ROOT)
Sys.setenv(STORAGE_DIR = STORAGE_DIR)
Sys.setenv(UPLOAD_DIR = UPLOAD_DIR)
Sys.setenv(GENERATED_ROOT = GENERATED_ROOT)
Sys.setenv(GENERATED_DIR = GENERATED_DIR)
Sys.setenv(R_LIBS_USER = R_LIBS_USER)

.libPaths(unique(c(R_LIBS_USER, .libPaths())))

cat("[R DEBUG] PROJECT_ROOT=", Sys.getenv("PROJECT_ROOT"), "\\n", sep = "")
cat("[R DEBUG] STORAGE_DIR=", Sys.getenv("STORAGE_DIR"), "\\n", sep = "")
cat("[R DEBUG] UPLOAD_DIR=", Sys.getenv("UPLOAD_DIR"), "\\n", sep = "")
cat("[R DEBUG] GENERATED_ROOT=", Sys.getenv("GENERATED_ROOT"), "\\n", sep = "")
cat("[R DEBUG] GENERATED_DIR=", Sys.getenv("GENERATED_DIR"), "\\n", sep = "")
cat("[R DEBUG] R_LIBS_USER=", Sys.getenv("R_LIBS_USER"), "\\n", sep = "")
cat("[R DEBUG] .libPaths=", paste(.libPaths(), collapse = " | "), "\\n", sep = "")

smart_read <- function(fp) {{
  fp <- as.character(fp)

  if (!nzchar(fp)) {{
    stop("smart_read 收到空路径")
  }}

  candidates <- unique(c(
    fp,
    file.path(Sys.getenv("PROJECT_ROOT"), fp),
    file.path(Sys.getenv("STORAGE_DIR"), fp),
    file.path(Sys.getenv("UPLOAD_DIR"), fp),
    file.path(Sys.getenv("GENERATED_DIR"), fp),
    file.path(Sys.getenv("GENERATED_ROOT"), fp)
  ))

  for (p in candidates) {{
    if (!is.na(p) && nzchar(p) && file.exists(p)) {{
      return(normalizePath(p, winslash = "/", mustWork = TRUE))
    }}
  }}

  stop(paste(
    "文件不存在:",
    fp,
    "\\nPROJECT_ROOT=", Sys.getenv("PROJECT_ROOT"),
    "\\nSTORAGE_DIR=", Sys.getenv("STORAGE_DIR"),
    "\\nUPLOAD_DIR=", Sys.getenv("UPLOAD_DIR"),
    "\\nGENERATED_DIR=", Sys.getenv("GENERATED_DIR"),
    "\\nTried=", paste(candidates, collapse = " | ")
  ))
}}

save_to_job <- function(filename) {{
  normalizePath(file.path(Sys.getenv("GENERATED_DIR"), filename), winslash = "/", mustWork = FALSE)
}}

setwd(GENERATED_DIR)
'''

    full_r_code = r_prelude + "\n\n" + str(r_code or "")
    script_path.write_text(full_r_code, encoding="utf-8")

    env = build_r_subprocess_env()

    try:
        proc = subprocess.run(
            [rscript, str(script_path)],
            cwd=str(job_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "status": "error",
            "message": f"R 执行超时（>{timeout} 秒）",
            "rscript": rscript,
            "job_id": job_id,
            "job_dir": str(job_dir),
            "stdout": _truncate_text(getattr(e, "stdout", "") or ""),
            "stderr": _truncate_text(getattr(e, "stderr", "") or ""),
            "output_files": collect_output_files(job_dir),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"R 执行失败：{str(e)}",
            "rscript": rscript,
            "job_id": job_id,
            "job_dir": str(job_dir),
            "upload_dir": str(UPLOAD_DIR),
            "generated_dir": str(GENERATED_DIR),
            "r_libs_user": str(R_LIBS_USER),
        }

    output_files = collect_output_files(job_dir)

    return {
        "status": "success" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "stdout": _truncate_text(proc.stdout),
        "stderr": _truncate_text(proc.stderr),
        "rscript": rscript,
        "job_id": job_id,
        "job_dir": str(job_dir),
        "storage_dir": str(STORAGE_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "generated_dir": str(GENERATED_DIR),
        "r_libs_user": str(R_LIBS_USER),
        "output_files": output_files,
    }