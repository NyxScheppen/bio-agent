from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_VERSION_CHECK = (
    "import sys; raise SystemExit(0 if sys.version_info[:2] "
    "in ((3, 11), (3, 12)) else 1)"
)


def test_batch_launchers_do_not_escape_comparators_inside_python_code():
    for filename in ("start_app.bat", "check_env.bat"):
        source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        assert "^<" not in source
        assert SUPPORTED_VERSION_CHECK in source


def test_supported_version_check_runs_through_cmd_on_windows():
    if sys.platform != "win32":
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        probe = Path(temp_dir) / "version_probe.cmd"
        probe.write_text(
            "@echo off\n"
            "(\n"
            f'    "{sys.executable}" -c "{SUPPORTED_VERSION_CHECK}"\n'
            ")\n"
            "exit /b %errorlevel%\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(probe)],
            check=False,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stderr
