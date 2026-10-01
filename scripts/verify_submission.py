"""Fail CI when the source tree is incomplete or contains submission hazards."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    ".gitlab-ci.yml",
    "LICENSE",
    "README.md",
    "README.en.md",
    "CONTRIBUTING.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/IGEM_SUBMISSION.md",
    "docs/assets/bioai-agent-interface.png",
    "renv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/src/App.tsx",
    "backend/app/main.py",
    "backend/static/index.html",
}
FORBIDDEN_DIRS = (
    "graphify-out/",
    "backend/storage/",
    "backend/db_data/",
    "backend/uploads/",
    "backend/generated/",
)
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}
FORBIDDEN_FILES = {"runtime/run_backend.bat"}
TEAM_NAME = "iGEM 2026 Team LZU GANSU"
SOFTWARE_REPOSITORY = "gitlab.igem.org/2026/software/lzu-gansu/bio-agent"
WORKSPACE_PATH_PATTERN = re.compile(
    r"(?i)(?:[a-z]:[\\/](?:users|desktop|documents|downloads|projects|workspaces)[\\/]|/(?:home|users)/[^/\s]+/)"
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return sorted({line.replace("\\", "/") for line in result.stdout.splitlines() if line})


def main() -> int:
    files = tracked_files()
    errors: list[str] = []
    file_set = set(files)

    for required in sorted(REQUIRED - file_set):
        errors.append(f"missing required file: {required}")

    for name in files:
        lower = name.lower()
        path = PurePosixPath(lower)
        if lower.startswith(FORBIDDEN_DIRS):
            errors.append(f"runtime/developer artifact is included: {name}")
        if path.suffix in FORBIDDEN_SUFFIXES:
            errors.append(f"secret or database file is included: {name}")
        if path.name.startswith(".env") and path.name != ".env_example":
            errors.append(f"environment secret file is included: {name}")
        if lower in FORBIDDEN_FILES:
            errors.append(f"machine-generated launcher is included: {name}")

        candidate = ROOT / name
        try:
            if candidate.is_file() and candidate.stat().st_size <= 2 * 1024 * 1024:
                content = candidate.read_bytes()
                if b"\0" not in content:
                    text = content.decode("utf-8", errors="ignore")
                    if WORKSPACE_PATH_PATTERN.search(text):
                        errors.append(f"machine-specific absolute path is included: {name}")
        except OSError as exc:
            errors.append(f"cannot inspect submission file {name}: {exc}")

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8") if (ROOT / "LICENSE").exists() else ""
    if "MIT License" not in license_text or "Permission is hereby granted" not in license_text:
        errors.append("LICENSE is not a complete MIT license")
    if TEAM_NAME not in license_text:
        errors.append(f"LICENSE is not attributed to {TEAM_NAME}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    if "待定" in readme.partition("## 📄 License")[2]:
        errors.append("README license section is still marked pending")
    english_readme = (
        (ROOT / "README.en.md").read_text(encoding="utf-8")
        if (ROOT / "README.en.md").exists()
        else ""
    )
    for filename, text in (("README.md", readme), ("README.en.md", english_readme)):
        if TEAM_NAME not in text or "2026.igem.wiki/lzu-gansu" not in text:
            errors.append(f"{filename} is missing verified LZU GANSU team attribution")
        if SOFTWARE_REPOSITORY not in text:
            errors.append(f"{filename} is missing the dedicated iGEM software repository URL")

    for lockfile in ("frontend/package-lock.json", "renv.lock"):
        try:
            json.loads((ROOT / lockfile).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON lockfile {lockfile}: {exc}")

    api_source = ROOT / "frontend/src/api.ts"
    if api_source.exists() and "127.0.0.1" in api_source.read_text(encoding="utf-8"):
        errors.append("frontend production API source embeds a developer host")

    try:
        index = (ROOT / "backend/static/index.html").read_text(encoding="utf-8")
        for marker in ('src="/assets/', 'href="/assets/'):
            for fragment in index.split(marker)[1:]:
                asset = fragment.split('"', 1)[0]
                if not (ROOT / "backend/static/assets" / asset).is_file():
                    errors.append(f"built frontend references missing asset: {asset}")
    except OSError as exc:
        errors.append(f"cannot inspect built frontend: {exc}")

    if errors:
        print("Submission verification failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"Submission verification passed ({len(files)} source/build files inspected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
