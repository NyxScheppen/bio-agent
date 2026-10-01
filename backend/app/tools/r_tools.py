import os
import re
import uuid
import subprocess
from pathlib import Path

from app.core.runtime_paths import (
    PROJECT_ROOT,
    STORAGE_DIR,
    GENERATED_DIR,
    UPLOAD_DIR,
    R_LIBS_USER,
    find_rscript,
    build_r_subprocess_env,
)
from app.utils.file_utils import build_file_url
from app.utils.storage_contracts import StorageValidationError, validate_session_id

MAX_R_OUTPUT_CHARS = 12000
_R_COLUMN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


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


def r_escape_string_content(value) -> str:
    """Escape a Python value for use inside an existing R string literal."""
    text = str(value if value is not None else "")
    replacements = {
        "\\": "\\\\",
        '"': '\\"',
        "\r": "\\r",
        "\n": "\\n",
        "\t": "\\t",
        "\b": "\\b",
        "\f": "\\f",
    }
    return "".join(
        replacements.get(char, f"\\u{ord(char):04x}" if ord(char) < 32 else char)
        for char in text
    )


def r_string_literal(value) -> str:
    return f'"{r_escape_string_content(value)}"'


def r_character_vector(values) -> str:
    return "c(" + ", ".join(r_string_literal(value) for value in values) + ")"


def validate_r_column_name(value: str) -> str:
    text = str(value or "")
    if not _R_COLUMN_PATTERN.fullmatch(text):
        raise ValueError(
            f"R 列名只能包含字母、数字、下划线和点，且不能以数字开头: {text!r}"
        )
    return text


def validate_r_column_names(values) -> list[str]:
    return [validate_r_column_name(value) for value in (values or [])]


def _resolve_job_dir(job_dir: str | None, job_subdir: str | None) -> tuple[str, Path]:
    generated_root = Path(GENERATED_DIR).resolve()
    if job_dir:
        resolved = Path(job_dir).resolve()
        try:
            resolved.relative_to(generated_root)
        except ValueError as exc:
            raise ValueError("R 输出目录必须位于 generated 目录内") from exc
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved.name, resolved

    label = _normalize_job_subdir(job_subdir) or "r_job"
    job_id = f"{label}_{uuid.uuid4().hex[:12]}"
    resolved = generated_root / job_id
    resolved.mkdir(parents=True, exist_ok=False)
    return job_id, resolved


def prepare_r_job_dir(job_dir: str | None = None, job_subdir: str | None = None) -> Path:
    """Return a validated generated-directory path before an R job starts.

    Most tools let ``run_r_analysis`` create the directory. Archive-backed tools
    need the lifecycle-owned directory earlier so they can stage validated input
    without extracting into uploads or a process-wide temporary directory.
    """
    return _resolve_job_dir(job_dir, job_subdir)[1]


def _session_id_from_job_dir(job_dir: Path) -> str:
    """Infer lifecycle ownership from generated/{session_id}/{job_id}."""
    try:
        relative = job_dir.resolve().relative_to(Path(GENERATED_DIR).resolve())
    except (OSError, ValueError):
        return ""
    if len(relative.parts) < 2:
        return ""
    try:
        return validate_session_id(relative.parts[0])
    except StorageValidationError:
        return ""


def collect_output_files(job_dir: Path):
    files = []

    for p in job_dir.rglob("*"):
        if not p.is_file() or p.name == "analysis.R" or p.name.startswith("."):
            continue
        try:
            if any(part.startswith(".omics-input-") for part in p.relative_to(job_dir).parts):
                continue
        except ValueError:
            continue
        try:
            rel_to_generated = p.relative_to(GENERATED_DIR).as_posix()
            url = build_file_url(f"generated/{rel_to_generated}")
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


def run_r_analysis(
    r_code: str,
    timeout: int = 300,
    job_subdir: str = None,
    job_dir: str = None,
):
    """Execute trusted, application-generated R code for registered domain tools.

    This function is intentionally not registered as an Agent tool. R code has the
    privileges of the R process, so in-process function masking is not a security
    sandbox for model- or user-supplied arbitrary code.
    """
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
    job_id, job_dir = _resolve_job_dir(job_dir, job_subdir)
    session_id = _session_id_from_job_dir(job_dir)
    session_upload_dir = (
        (Path(UPLOAD_DIR) / session_id).resolve()
        if session_id else Path(UPLOAD_DIR).resolve()
    )
    session_generated_dir = (
        (Path(GENERATED_DIR) / session_id).resolve()
        if session_id else Path(GENERATED_DIR).resolve()
    )

    script_path = job_dir / "analysis.R"

    project_root_r = r_string_literal(_as_r_path(PROJECT_ROOT))
    storage_dir_r = r_string_literal(_as_r_path(STORAGE_DIR))
    upload_dir_r = r_string_literal(_as_r_path(UPLOAD_DIR))
    generated_root_r = r_string_literal(_as_r_path(GENERATED_DIR))
    job_dir_r = r_string_literal(_as_r_path(job_dir))
    r_libs_user_r = r_string_literal(_as_r_path(R_LIBS_USER))
    session_id_r = r_string_literal(session_id)
    session_upload_dir_r = r_string_literal(_as_r_path(session_upload_dir))
    session_generated_dir_r = r_string_literal(_as_r_path(session_generated_dir))
    session_scoped_r = "TRUE" if session_id else "FALSE"

    r_prelude = f'''
options(encoding = "UTF-8")

PROJECT_ROOT <- normalizePath({project_root_r}, winslash = "/", mustWork = FALSE)
STORAGE_DIR <- normalizePath({storage_dir_r}, winslash = "/", mustWork = FALSE)
UPLOAD_DIR <- normalizePath({upload_dir_r}, winslash = "/", mustWork = FALSE)
GENERATED_ROOT <- normalizePath({generated_root_r}, winslash = "/", mustWork = FALSE)
GENERATED_DIR <- normalizePath({job_dir_r}, winslash = "/", mustWork = FALSE)
R_LIBS_USER <- normalizePath({r_libs_user_r}, winslash = "/", mustWork = FALSE)
SESSION_ID <- {session_id_r}
SESSION_UPLOAD_DIR <- normalizePath({session_upload_dir_r}, winslash = "/", mustWork = FALSE)
SESSION_GENERATED_DIR <- normalizePath({session_generated_dir_r}, winslash = "/", mustWork = FALSE)
SESSION_SCOPED <- {session_scoped_r}

Sys.setenv(PROJECT_ROOT = PROJECT_ROOT)
Sys.setenv(STORAGE_DIR = STORAGE_DIR)
Sys.setenv(UPLOAD_DIR = UPLOAD_DIR)
Sys.setenv(GENERATED_ROOT = GENERATED_ROOT)
Sys.setenv(GENERATED_DIR = GENERATED_DIR)
Sys.setenv(R_LIBS_USER = R_LIBS_USER)
Sys.setenv(SESSION_ID = SESSION_ID)
Sys.setenv(SESSION_UPLOAD_DIR = SESSION_UPLOAD_DIR)
Sys.setenv(SESSION_GENERATED_DIR = SESSION_GENERATED_DIR)

.libPaths(unique(c(R_LIBS_USER, .libPaths())))

cat("[R DEBUG] PROJECT_ROOT=", Sys.getenv("PROJECT_ROOT"), "\\n", sep = "")
cat("[R DEBUG] STORAGE_DIR=", Sys.getenv("STORAGE_DIR"), "\\n", sep = "")
cat("[R DEBUG] UPLOAD_DIR=", Sys.getenv("UPLOAD_DIR"), "\\n", sep = "")
cat("[R DEBUG] GENERATED_ROOT=", Sys.getenv("GENERATED_ROOT"), "\\n", sep = "")
cat("[R DEBUG] GENERATED_DIR=", Sys.getenv("GENERATED_DIR"), "\\n", sep = "")
cat("[R DEBUG] R_LIBS_USER=", Sys.getenv("R_LIBS_USER"), "\\n", sep = "")
cat("[R DEBUG] SESSION_ID=", Sys.getenv("SESSION_ID"), "\\n", sep = "")
cat("[R DEBUG] .libPaths=", paste(.libPaths(), collapse = " | "), "\\n", sep = "")

smart_read <- function(fp) {{
  fp <- as.character(fp)

  if (!nzchar(fp)) {{
    stop("smart_read 收到空路径")
  }}

  candidates <- if (SESSION_SCOPED) {{
    unique(c(
      fp,
      file.path(Sys.getenv("STORAGE_DIR"), fp),
      file.path(Sys.getenv("SESSION_UPLOAD_DIR"), fp),
      file.path(Sys.getenv("SESSION_GENERATED_DIR"), fp),
      file.path(Sys.getenv("GENERATED_DIR"), fp)
    ))
  }} else {{
    unique(c(
      fp,
      file.path(Sys.getenv("STORAGE_DIR"), fp),
      file.path(Sys.getenv("UPLOAD_DIR"), fp),
      file.path(Sys.getenv("GENERATED_DIR"), fp),
      file.path(Sys.getenv("GENERATED_ROOT"), fp)
    ))
  }}

  allowed_input_roots <- if (SESSION_SCOPED) {{
    c(Sys.getenv("SESSION_UPLOAD_DIR"), Sys.getenv("SESSION_GENERATED_DIR"))
  }} else {{
    c(Sys.getenv("STORAGE_DIR"))
  }}
  allowed_input_roots <- normalizePath(
    allowed_input_roots,
    winslash = "/",
    mustWork = FALSE
  )

  for (p in candidates) {{
    if (!is.na(p) && nzchar(p) && file.exists(p)) {{
      resolved <- normalizePath(p, winslash = "/", mustWork = TRUE)
      in_scope <- vapply(
        allowed_input_roots,
        function(root) identical(resolved, root) || startsWith(resolved, paste0(root, "/")),
        logical(1)
      )
      if (any(in_scope)) {{
        return(resolved)
      }}
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
  output <- normalizePath(file.path(Sys.getenv("GENERATED_DIR"), filename), winslash = "/", mustWork = FALSE)
  root <- normalizePath(Sys.getenv("GENERATED_DIR"), winslash = "/", mustWork = TRUE)
  if (!(identical(output, root) || startsWith(output, paste0(root, "/")))) {{
    stop("安全限制：输出文件必须位于当前 job 目录")
  }}
  output
}}

setwd(GENERATED_DIR)

# ===== 纵深防护：这里只保护应用生成的 R 模板，不构成任意代码沙箱 =====

.base_ns <- asNamespace("base")
.blocked_process_call <- function(...) stop("安全限制：分析模板禁止执行外部命令")
for (.name in c("system", "system2", "shell", "shell.exec")) {{
  if (exists(.name, envir = .base_ns, inherits = FALSE)) {{
    unlockBinding(.name, .base_ns)
    assign(.name, .blocked_process_call, envir = .base_ns)
    lockBinding(.name, .base_ns)
  }}
}}

.file_guard <- local({{
  original_file <- base::file
  storage_allow_roots <- if (SESSION_SCOPED) {{
    Sys.getenv(c("SESSION_UPLOAD_DIR", "SESSION_GENERATED_DIR", "GENERATED_DIR"))
  }} else {{
    Sys.getenv(c("STORAGE_DIR", "UPLOAD_DIR", "GENERATED_ROOT", "GENERATED_DIR"))
  }}
  allow_roots <- unique(c(
    storage_allow_roots,
    Sys.getenv("R_LIBS_USER"),
    .libPaths(),
    tempdir(),
    R.home()
  ))
  allow_roots <- allow_roots[nzchar(allow_roots)]
  allow_roots <- normalizePath(allow_roots, winslash = "/", mustWork = FALSE)

  function(description = "", ...) {{
    if (is.character(description) && length(description) == 1 && nzchar(description)
        && !grepl("^[a-zA-Z][a-zA-Z0-9+.-]*://", description)) {{
      p <- normalizePath(description, winslash = "/", mustWork = FALSE)
      in_root <- vapply(
        allow_roots,
        function(root) identical(p, root) || startsWith(p, paste0(root, "/")),
        logical(1)
      )
      if (!any(in_root)) {{
        stop("安全限制：禁止访问 storage 目录外的文件: ", description)
      }}
    }}
    original_file(description, ...)
  }}
}})

unlockBinding("file", .base_ns)
assign("file", .file_guard, envir = .base_ns)
lockBinding("file", .base_ns)
rm(.file_guard, .blocked_process_call, .base_ns, .name)
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
