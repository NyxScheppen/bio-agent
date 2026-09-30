import json
import socket
from pathlib import Path

import pytest


def _public_dns_record(host, port, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/internal.pdf",
        "http://169.254.169.254/latest/meta-data.pdf",
        "http://[::1]/internal.pdf",
        "http://localhost/internal.pdf",
    ],
)
def test_pdf_download_rejects_non_public_targets(url):
    from app.tools.literature_tools import download_open_access_pdf

    result = json.loads(download_open_access_pdf(url))

    assert result["status"] == "error"
    assert "公网" in result["message"]


def test_pdf_download_rejects_invalid_port():
    from app.tools.literature_tools import download_open_access_pdf

    result = json.loads(download_open_access_pdf("https://papers.example:0/paper.pdf"))

    assert result["status"] == "error"
    assert "端口无效" in result["message"]


def test_pdf_download_rejects_dns_answers_containing_private_ip(monkeypatch):
    from app.tools import literature_tools

    def mixed_dns(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", port)),
        ]

    monkeypatch.setattr(literature_tools.socket, "getaddrinfo", mixed_dns)

    with pytest.raises(ValueError, match="非公网"):
        literature_tools._validate_public_download_url("https://papers.example/paper.pdf")


def test_pdf_download_revalidates_redirect_targets(monkeypatch):
    from app.tools import literature_tools

    calls = []

    def redirect_once(parts, pinned_ip, timeout=30):
        calls.append((parts.hostname, pinned_ip))
        return 302, {"Location": "http://127.0.0.1/internal.pdf"}, b""

    monkeypatch.setattr(literature_tools.socket, "getaddrinfo", _public_dns_record)
    monkeypatch.setattr(literature_tools, "_request_pinned_url", redirect_once)

    with pytest.raises(ValueError, match="非公网"):
        literature_tools._download_public_pdf("https://papers.example/paper.pdf")

    assert calls == [("papers.example", "93.184.216.34")]


def test_pdf_extension_does_not_bypass_content_signature(monkeypatch):
    from app.tools import literature_tools

    monkeypatch.setattr(literature_tools.socket, "getaddrinfo", _public_dns_record)
    monkeypatch.setattr(
        literature_tools,
        "_request_pinned_url",
        lambda parts, pinned_ip, timeout=30: (
            200,
            {"Content-Type": "text/html"},
            b"<html>secret response</html>",
        ),
    )

    with pytest.raises(ValueError, match="有效 PDF"):
        literature_tools._download_public_pdf("https://papers.example/paper.pdf")


def test_arbitrary_r_code_runner_is_not_agent_callable():
    from app import tools  # noqa: F401
    from app.agent.tool_registry import TOOL_REGISTRY, TOOLS_SCHEMA

    assert "run_r_analysis" not in TOOL_REGISTRY
    assert all(
        item.get("function", {}).get("name") != "run_r_analysis"
        for item in TOOLS_SCHEMA
    )


def _configure_resolver_storage(monkeypatch, tmp_path):
    from app.utils import file_resolver

    storage = tmp_path / "storage"
    uploads = storage / "uploads"
    generated = storage / "generated"
    temp = storage / "temp"
    for directory in (uploads, generated, temp):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(file_resolver, "STORAGE_DIR", storage)
    monkeypatch.setattr(file_resolver, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(file_resolver, "GENERATED_DIR", generated)
    monkeypatch.setattr(file_resolver, "TEMP_DIR", temp)
    monkeypatch.setattr(file_resolver, "_STORAGE_ROOT", storage.resolve())
    return file_resolver, storage, uploads, generated


def test_session_file_wins_without_global_same_name_scan(monkeypatch, tmp_path):
    resolver, _, uploads, generated = _configure_resolver_storage(monkeypatch, tmp_path)
    session_file = uploads / "victim" / "same.csv"
    global_file = generated / "other" / "same.csv"
    session_file.parent.mkdir(parents=True)
    global_file.parent.mkdir(parents=True)
    session_file.write_text("session", encoding="utf-8")
    global_file.write_text("global", encoding="utf-8")

    resolved = resolver.resolve_file_path("same.csv", session_id="victim")

    assert resolved == session_file


def test_session_lookup_never_falls_back_to_another_session(monkeypatch, tmp_path):
    resolver, storage, uploads, _ = _configure_resolver_storage(monkeypatch, tmp_path)
    other_file = uploads / "other" / "same.csv"
    other_file.parent.mkdir(parents=True)
    other_file.write_text("other", encoding="utf-8")

    resolved = resolver.resolve_file_path("same.csv", session_id="victim")

    assert resolved == storage / "same.csv"
    assert resolved != other_file


def test_invalid_session_key_fails_closed(monkeypatch, tmp_path):
    resolver, _, uploads, _ = _configure_resolver_storage(monkeypatch, tmp_path)
    other_file = uploads / "other" / "same.csv"
    other_file.parent.mkdir(parents=True)
    other_file.write_text("other", encoding="utf-8")

    assert resolver.resolve_file_path("same.csv", session_id="../other") is None


def test_explicit_other_session_upload_path_is_rejected(monkeypatch, tmp_path):
    resolver, _, uploads, _ = _configure_resolver_storage(monkeypatch, tmp_path)
    other_file = uploads / "other" / "same.csv"
    other_file.parent.mkdir(parents=True)
    other_file.write_text("other", encoding="utf-8")

    assert (
        resolver.resolve_file_path("uploads/other/same.csv", session_id="victim")
        is None
    )


def test_session_relative_traversal_is_rejected(monkeypatch, tmp_path):
    resolver, _, uploads, _ = _configure_resolver_storage(monkeypatch, tmp_path)
    other_file = uploads / "other" / "same.csv"
    other_file.parent.mkdir(parents=True)
    other_file.write_text("other", encoding="utf-8")

    assert resolver.resolve_file_path("../other/same.csv", session_id="victim") is None


def test_generic_task_and_file_input_do_not_select_skill(monkeypatch):
    from app.agent.skills import skill_router
    from app.agent.skills.skill_models import SkillSpec

    skill = SkillSpec(
        skill_id="input_only",
        name="Input only",
        task_types=["bioinformatics"],
        required_inputs=["expression_matrix"],
        implementation_status="implemented",
    )
    monkeypatch.setattr(skill_router, "SKILL_REGISTRY", {skill.skill_id: skill})

    selected = skill_router.select_skill(
        "please help",
        {"task_type": "bioinformatics", "subtask_type": "unknown"},
        available_files=["expression.csv"],
    )

    assert selected is None


def test_portable_build_excludes_common_secret_files():
    script = (Path(__file__).resolve().parents[2] / "build_portable.bat").read_text(
        encoding="utf-8"
    ).lower()

    for pattern in (
        '".env.*"',
        '"*.pem"',
        '"*.key"',
        '"*.pfx"',
        '"*.p12"',
        '"id_rsa"',
        '"id_ed25519"',
        '"*secret*"',
        '"*credential*"',
    ):
        assert pattern in script
