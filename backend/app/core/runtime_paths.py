import os
import shutil
import subprocess
from pathlib import Path


def get_backend_root() -> Path:
    """
    当前文件位于 backend/app/core/runtime_paths.py
    parents[0] = core
    parents[1] = app
    parents[2] = backend
    """
    return Path(__file__).resolve().parents[2]


def get_project_root() -> Path:
    return get_backend_root().parent


BACKEND_ROOT = get_backend_root()
PROJECT_ROOT = get_project_root()

STORAGE_DIR = BACKEND_ROOT / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
GENERATED_DIR = STORAGE_DIR / "generated"
TEMP_DIR = STORAGE_DIR / "temp"

R_LIBS_USER = PROJECT_ROOT / "env" / "r_libs"


def find_rscript() -> str:
    """
    Python 侧 Rscript 定位逻辑。
    不只依赖 PATH，兼容本地安装、portable R、注册表等情况。
    """
    candidates = []

    env_rscript = os.environ.get("RSCRIPT_PATH")
    if env_rscript:
        candidates.append(Path(env_rscript))

    candidates.extend([
        PROJECT_ROOT / "env" / "R" / "bin" / "Rscript.exe",
        PROJECT_ROOT / "env" / "R" / "bin" / "x64" / "Rscript.exe",
        PROJECT_ROOT / "runtime" / "R" / "bin" / "Rscript.exe",
        PROJECT_ROOT / "runtime" / "R" / "bin" / "x64" / "Rscript.exe",
    ])

    which_rscript = shutil.which("Rscript")
    if which_rscript:
        candidates.append(Path(which_rscript))

    if os.name == "nt":
        try:
            import winreg

            reg_paths = [
                r"SOFTWARE\R-core\R",
                r"SOFTWARE\WOW6432Node\R-core\R",
            ]

            for reg_path in reg_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                        install_dir = Path(install_path)
                        candidates.extend([
                            install_dir / "bin" / "Rscript.exe",
                            install_dir / "bin" / "x64" / "Rscript.exe",
                        ])
                except Exception:
                    continue
        except Exception:
            pass

    if os.name == "nt":
        for base in [Path(r"C:\Program Files\R"), Path(r"C:\Program Files (x86)\R")]:
            if base.exists():
                for child in sorted(base.glob("R-*"), reverse=True):
                    candidates.extend([
                        child / "bin" / "Rscript.exe",
                        child / "bin" / "x64" / "Rscript.exe",
                    ])

        d_root = Path("D:/")
        if d_root.exists():
            for child in sorted(d_root.glob("R-*"), reverse=True):
                candidates.extend([
                    child / "bin" / "Rscript.exe",
                    child / "bin" / "x64" / "Rscript.exe",
                ])

    candidates.extend([
        Path("/usr/bin/Rscript"),
        Path("/usr/local/bin/Rscript"),
        Path("/opt/R/bin/Rscript"),
    ])

    seen = set()
    for candidate in candidates:
        try:
            resolved = str(candidate.resolve()) if candidate.exists() else str(candidate)
        except Exception:
            resolved = str(candidate)

        if resolved in seen:
            continue
        seen.add(resolved)

        try:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        except Exception:
            continue

    return ""


def build_r_subprocess_env() -> dict:
    """
    为 R 子进程准备统一环境。
    关键点：
    1. 路径统一到 backend/storage/*
    2. 注入 R_LIBS_USER
    3. 强制 UTF-8，避免 Windows 下 stdout/stderr 解码炸掉
    """
    env = os.environ.copy()

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    R_LIBS_USER.mkdir(parents=True, exist_ok=True)

    rscript = find_rscript()

    env["PROJECT_ROOT"] = str(PROJECT_ROOT)
    env["BACKEND_ROOT"] = str(BACKEND_ROOT)
    env["STORAGE_DIR"] = str(STORAGE_DIR)
    env["UPLOAD_DIR"] = str(UPLOAD_DIR)
    env["GENERATED_DIR"] = str(GENERATED_DIR)
    env["TEMP_DIR"] = str(TEMP_DIR)
    env["R_LIBS_USER"] = str(R_LIBS_USER)

    env["PYTHONIOENCODING"] = "utf-8"
    env["LANG"] = "en_US.UTF-8"
    env["LC_ALL"] = "en_US.UTF-8"

    if os.name == "nt":
        env["R_DEFAULT_PACKAGES"] = env.get("R_DEFAULT_PACKAGES", "datasets,utils,grDevices,graphics,stats,methods")
        env["R_USER"] = env.get("R_USER", str(PROJECT_ROOT))
        env["HOME"] = env.get("HOME", str(PROJECT_ROOT))

    if rscript:
        r_bin = str(Path(rscript).parent)
        env["PATH"] = r_bin + os.pathsep + env.get("PATH", "")

    return env


def check_rscript_version() -> str:
    rscript = find_rscript()
    if not rscript:
        return ""

    try:
        proc = subprocess.run(
            [rscript, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return (proc.stdout or proc.stderr or "").strip()
    except Exception as e:
        return f"Rscript found but version check failed: {e}"