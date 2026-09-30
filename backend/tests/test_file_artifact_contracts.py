import gzip
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import ChatSession, StoredFile


class MemoryUpload:
    def __init__(self, filename: str, content: bytes, declared_size=None):
        self.filename = filename
        self.file = io.BytesIO(content)
        self.size = len(content) if declared_size is None else declared_size


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def isolated_storage(monkeypatch, tmp_path):
    from app.services import chat_service, session_service
    from app.utils import storage_contracts

    storage = tmp_path / "storage"
    uploads = storage / "uploads"
    generated = storage / "generated"
    uploads.mkdir(parents=True)
    generated.mkdir(parents=True)

    monkeypatch.setattr(storage_contracts, "STORAGE_DIR", storage)
    monkeypatch.setattr(storage_contracts, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(storage_contracts, "GENERATED_DIR", generated)
    monkeypatch.setattr(chat_service, "STORAGE_DIR", storage)
    monkeypatch.setattr(session_service, "STORAGE_DIR", storage)
    monkeypatch.setattr(session_service, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(session_service, "GENERATED_DIR", generated)
    return storage, uploads, generated


@pytest.mark.parametrize(
    "session_id",
    ["", "..", "../other", "a/other", "a\\other", "_leading", "x" * 65],
)
def test_session_id_contract_rejects_unsafe_values(session_id):
    from app.utils.storage_contracts import StorageValidationError, validate_session_id

    with pytest.raises(StorageValidationError):
        validate_session_id(session_id)


@pytest.mark.parametrize("session_id", ["a", "A-1_test", "9" * 64])
def test_session_id_contract_accepts_portable_values(session_id):
    from app.utils.storage_contracts import validate_session_id

    assert validate_session_id(session_id) == session_id


@pytest.mark.parametrize(
    "filename",
    ["", ".", "CON", "CON.tar.gz", "nul.txt", "x" * 241],
)
def test_upload_filename_rejects_empty_reserved_or_oversized_names(filename):
    from app.utils.storage_contracts import StorageValidationError, normalize_upload_filename

    with pytest.raises(StorageValidationError):
        normalize_upload_filename(filename)


def test_concurrent_same_name_publication_never_overwrites(isolated_storage):
    from app.utils.storage_contracts import publish_staged_upload

    _, uploads, _ = isolated_storage
    session_dir = uploads / "same_name"
    session_dir.mkdir()

    staged = []
    for index in range(8):
        path = session_dir / f".upload-{index}.tmp"
        path.write_bytes(f"payload-{index}".encode())
        staged.append(path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        published = list(
            pool.map(
                lambda path: publish_staged_upload(session_dir, "data.csv", path),
                staged,
            )
        )

    assert len({path.name for path in published}) == 8
    assert {path.read_bytes() for path in published} == {
        f"payload-{index}".encode() for index in range(8)
    }


def test_upload_batch_rolls_back_files_and_database_on_actual_size_limit(
    monkeypatch,
    isolated_storage,
    db_session,
):
    from app.services import file_service

    _, uploads, _ = isolated_storage
    monkeypatch.setattr(file_service, "MAX_UPLOAD_FILE_BYTES", 5)
    monkeypatch.setattr(file_service, "MAX_UPLOAD_BATCH_BYTES", 100)

    with pytest.raises(file_service.UploadLimitError):
        file_service.save_upload_files(
            db_session,
            [
                MemoryUpload("first.csv", b"123", declared_size=None),
                MemoryUpload("second.csv", b"123456", declared_size=0),
            ],
            "rollback_case",
        )

    session_dir = uploads / "rollback_case"
    assert not list(session_dir.iterdir())
    assert db_session.query(ChatSession).count() == 0
    assert db_session.query(StoredFile).count() == 0


def test_upload_body_limit_rejects_before_endpoint_reads_body():
    from app.upload_limit import UploadBodyLimitMiddleware

    test_app = FastAPI()
    test_app.add_middleware(UploadBodyLimitMiddleware, max_body_bytes=5)
    endpoint_called = False

    @test_app.post("/api/upload")
    async def upload(request: Request):
        nonlocal endpoint_called
        endpoint_called = True
        return {"size": len(await request.body())}

    response = TestClient(test_app).post(
        "/api/upload",
        content=b"123456",
        headers={"content-type": "application/octet-stream"},
    )

    assert response.status_code == 413
    assert endpoint_called is False


def test_upload_body_limit_counts_stream_without_content_length():
    from app.upload_limit import UploadBodyLimitMiddleware

    endpoint_called = False
    response_messages = []
    request_messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )

    async def endpoint(scope, receive, send):
        nonlocal endpoint_called
        endpoint_called = True
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    async def receive():
        return next(request_messages)

    async def send(message):
        response_messages.append(message)

    import asyncio

    middleware = UploadBodyLimitMiddleware(endpoint, max_body_bytes=5)
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/upload",
                "headers": [],
            },
            receive,
            send,
        )
    )

    assert endpoint_called is True
    assert response_messages[0]["status"] == 413


def test_upload_returns_relative_url_and_delete_commit_failure_restores_file(
    monkeypatch,
    isolated_storage,
    db_session,
):
    from app.services import file_service

    result = file_service.save_upload_file(
        db_session,
        MemoryUpload("space name.csv", b"a,b\n1,2\n"),
        "restore_case",
    )
    target = isolated_storage[0] / result["relative_path"]
    assert result["url"] == "/files/uploads/restore_case/space%20name.csv"
    assert target.is_file()

    original_commit = db_session.commit

    def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        file_service.delete_uploaded_file(db_session, "restore_case", target.name)
    monkeypatch.setattr(db_session, "commit", original_commit)

    assert target.read_bytes() == b"a,b\n1,2\n"
    assert db_session.query(StoredFile).filter_by(session_id="restore_case").count() == 1


def test_listing_missing_session_does_not_create_directory(isolated_storage):
    from app.services.file_service import list_uploaded_files

    _, uploads, _ = isolated_storage
    assert list_uploaded_files("missing") == {"session_id": "missing", "files": []}
    assert not (uploads / "missing").exists()


def test_stored_file_route_blocks_traversal_and_active_content(
    isolated_storage,
):
    from app.main import app

    storage, uploads, generated = isolated_storage
    job_dir = generated / "serve_case" / "job"
    job_dir.mkdir(parents=True)
    (job_dir / "page.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    (job_dir / "plot.svg").write_text("<svg/>", encoding="utf-8")
    (job_dir / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (job_dir / ".upload-secret.tmp").write_text("partial", encoding="utf-8")
    secret = uploads / "other" / "secret.csv"
    secret.parent.mkdir(parents=True)
    secret.write_text("secret", encoding="utf-8")

    client = TestClient(app)
    for name in ("page.html", "plot.svg"):
        response = client.get(f"/files/generated/serve_case/job/{name}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["content-security-policy"].startswith("sandbox")

    png = client.get("/files/generated/serve_case/job/plot.png")
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.headers["x-content-type-options"] == "nosniff"

    head = client.head("/files/generated/serve_case/job/page.html")
    assert head.status_code == 200
    assert head.content == b""
    assert client.get(
        "/files/generated/serve_case/job/%2E%2E/%2E%2E/%2E%2E/uploads/other/secret.csv"
    ).status_code == 404
    assert client.get(
        "/files/generated/serve_case/job/.upload-secret.tmp"
    ).status_code == 404
    assert storage.exists()


def test_storage_contract_rejects_symlink_artifacts(
    monkeypatch,
    isolated_storage,
):
    from app.utils.storage_contracts import resolve_storage_relative_path

    storage, _, generated = isolated_storage
    outside = storage.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = generated / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        link.write_text("simulated link", encoding="utf-8")
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == link or original_is_symlink(path),
        )

    assert resolve_storage_relative_path(
        "generated/link.txt",
        require_exists=True,
    ) is None


def test_generated_reply_and_attachment_paths_are_session_scoped(isolated_storage):
    from app.services.chat_service import (
        normalize_agent_file,
        resolve_generated_files,
        validate_attached_files,
    )

    _, uploads, generated = isolated_storage
    own_output = generated / "victim" / "job" / "plot.png"
    other_output = generated / "other" / "job" / "plot.png"
    own_upload = uploads / "victim" / "data.csv"
    for path, content in (
        (own_output, b"own"),
        (other_output, b"other"),
        (own_upload, b"a,b\n1,2\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    assert resolve_generated_files(["generated/../uploads/other/secret.csv"], "victim") == []
    assert resolve_generated_files(["generated/other/job/plot.png"], "victim") == []
    assert resolve_generated_files(["plot.png"], "victim")[0]["relative_path"] == (
        "generated/victim/job/plot.png"
    )

    normalized = normalize_agent_file(
        {
            "name": "spoofed.html",
            "type": "text",
            "relative_path": "generated/victim/job/plot.png",
        },
        "victim",
    )
    assert normalized["name"] == "plot.png"
    assert normalized["type"] == "image"

    attached = validate_attached_files(
        "victim",
        [
            {"relative_path": "uploads/victim/data.csv"},
            {"relative_path": "generated/other/job/plot.png"},
            {"relative_path": "uploads/victim/missing.csv"},
        ],
    )
    assert [item["relative_path"] for item in attached] == [
        "uploads/victim/data.csv"
    ]


def test_tool_outputs_must_exist_inside_current_job(monkeypatch, tmp_path):
    from app.agent.tool_result import OutputFile
    from app.agent.tool_runner import restrict_output_files_to_job
    from app.core import runtime_paths

    storage = tmp_path / "storage"
    job_dir = storage / "generated" / "session" / "job"
    other_dir = storage / "generated" / "session" / "other"
    job_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    inside = job_dir / "inside.csv"
    outside = other_dir / "outside.csv"
    inside.write_text("inside", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    monkeypatch.setattr(runtime_paths, "STORAGE_DIR", storage)

    result = restrict_output_files_to_job(
        [
            OutputFile(name="fake", relative_path=str(inside)),
            OutputFile(name="outside.csv", relative_path=str(outside)),
            OutputFile(name="missing.csv", relative_path="missing.csv"),
        ],
        str(job_dir),
    )

    assert len(result) == 1
    assert result[0].name == "inside.csv"
    assert result[0].relative_path == "generated/session/job/inside.csv"
    assert result[0].size_bytes == len(b"inside")
    assert result[0].file_type == "table"


def test_invalid_explicit_output_cannot_hide_collected_file_with_same_name():
    from app.agent.tool_runner import run_tool_with_lifecycle

    def tool(job_dir: str = ""):
        Path(job_dir, "result.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        return {
            "status": "success",
            "output_files": [
                {
                    "name": "result.csv",
                    "relative_path": "generated/another/job/result.csv",
                }
            ],
        }

    result = run_tool_with_lifecycle(
        tool_name="invalid_explicit",
        func=tool,
        function_args={},
        session_id="artifact_case",
    )

    assert [item.name for item in result.output_files] == ["result.csv"]
    assert result.output_files[0].relative_path.startswith(
        "generated/artifact_case/invalid_explicit_"
    )


def test_r_template_values_are_escaped_and_formula_columns_are_strict(monkeypatch):
    from app.tools import single_gene_tools, survival_tools
    from app.tools.r_tools import r_string_literal

    captured = {}

    def capture(r_code, **kwargs):
        captured["r_code"] = r_code
        captured["kwargs"] = kwargs
        return {"status": "success"}

    monkeypatch.setattr(single_gene_tools, "run_r_analysis", capture)
    payload = 'TP53")); writeLines("INJECTED", "proof.txt"); #'
    result = single_gene_tools.run_single_gene_expression_analysis(
        "uploads/session/data.csv",
        "uploads/session/groups.csv",
        payload,
        job_dir="generated/session/job",
    )

    assert result["status"] == "success"
    assert payload not in captured["r_code"]
    assert '\\")); writeLines(\\"INJECTED\\"' in captured["r_code"]
    assert captured["kwargs"]["job_dir"] == "generated/session/job"
    assert r_string_literal('a"b\\c\n') == '"a\\"b\\\\c\\n"'

    with pytest.raises(ValueError, match="R 列名"):
        survival_tools.run_single_gene_survival_analysis(
            "data.csv",
            "gene); system('calc')",
            "time",
            "status",
        )

    with pytest.raises(ValueError, match="预处理模式"):
        single_gene_tools.run_single_gene_expression_analysis(
            "data.csv",
            "groups.csv",
            "TP53",
            expression_preprocess='auto\"); system(\"calc\"); #',
        )


def test_r_lifecycle_script_scopes_file_access_to_session(monkeypatch, tmp_path):
    from app.tools import r_tools

    storage = tmp_path / "storage"
    generated = storage / "generated"
    uploads = storage / "uploads"
    job_dir = generated / "scope_session" / "job_1"
    job_dir.mkdir(parents=True)
    uploads.mkdir(parents=True)

    monkeypatch.setattr(r_tools, "STORAGE_DIR", storage)
    monkeypatch.setattr(r_tools, "GENERATED_DIR", generated)
    monkeypatch.setattr(r_tools, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(r_tools, "find_rscript", lambda: "Rscript")
    monkeypatch.setattr(r_tools, "build_r_subprocess_env", lambda: {})
    monkeypatch.setattr(
        r_tools.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    result = r_tools.run_r_analysis("cat('ok')", job_dir=str(job_dir))
    script = (job_dir / "analysis.R").read_text(encoding="utf-8")

    assert result["status"] == "success"
    assert 'SESSION_ID <- "scope_session"' in script
    assert "SESSION_SCOPED <- TRUE" in script
    assert str(uploads / "scope_session").replace("\\", "/") in script
    assert str(generated / "scope_session").replace("\\", "/") in script


def test_preview_budgets_bound_plain_gzip_and_xlsx_work(monkeypatch, tmp_path):
    from app.tools import file_tools

    monkeypatch.setattr(file_tools, "MAX_PREVIEW_SCAN_BYTES", 20)
    monkeypatch.setattr(file_tools, "MAX_PREVIEW_DECOMPRESSED_BYTES", 30)
    monkeypatch.setattr(file_tools, "MAX_PREVIEW_LINE_BYTES", 10)

    plain = tmp_path / "large.csv"
    plain.write_bytes(b"a,b\n" + b"1,2\n" * 10)
    assert file_tools._count_csv_rows(plain) is None

    compressed = tmp_path / "large.csv.gz"
    with gzip.open(compressed, "wb") as stream:
        stream.write(b"a,b\n" + b"1,2\n" * 20)
    assert file_tools._count_text_table_rows(compressed, compressed=True) is None

    long_line = tmp_path / "line.csv"
    long_line.write_bytes(b"a" * 11 + b"\n")
    with pytest.raises(ValueError, match="单行"):
        file_tools._read_bounded_text_lines(long_line, compressed=False, count=1)

    workbook = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(workbook, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"x" * 31)
    with pytest.raises(ValueError, match="解压后"):
        file_tools._validate_excel_archive(workbook)


def test_generated_only_cleanup_preserves_upload_and_session(
    isolated_storage,
    db_session,
):
    from app.db import crud
    from app.services.session_service import delete_session_generated_files_only

    _, uploads, generated = isolated_storage
    upload = uploads / "cleanup" / "input.csv"
    output = generated / "cleanup" / "job" / "plot.png"
    upload.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    upload.write_text("input", encoding="utf-8")
    output.write_bytes(b"plot")

    crud.create_session(db_session, "cleanup")
    crud.save_file_record(
        db_session, "cleanup", "input.csv", "uploads/cleanup/input.csv", "table", "upload"
    )
    crud.save_file_record(
        db_session,
        "cleanup",
        "plot.png",
        "generated/cleanup/job/plot.png",
        "image",
        "generated",
    )

    result = delete_session_generated_files_only(db_session, "cleanup")

    assert result["status"] == "success"
    assert upload.is_file()
    assert not output.exists()
    assert db_session.query(ChatSession).filter_by(session_id="cleanup").one()
    records = db_session.query(StoredFile).filter_by(session_id="cleanup").all()
    assert [record.source_type for record in records] == ["upload"]


def test_shared_legacy_artifact_is_not_physically_deleted(
    isolated_storage,
    db_session,
):
    from app.db import crud
    from app.services.session_service import delete_session_with_files

    _, _, generated = isolated_storage
    shared = generated / "legacy_shared" / "report.csv"
    shared.parent.mkdir(parents=True)
    shared.write_text("shared", encoding="utf-8")

    for session_id in ("legacy_a", "legacy_b"):
        crud.create_session(db_session, session_id)
        crud.save_file_record(
            db_session,
            session_id,
            "report.csv",
            "generated/legacy_shared/report.csv",
            "table",
            "generated",
        )

    result = delete_session_with_files(db_session, "legacy_a")

    assert result["status"] == "success"
    assert shared.read_text(encoding="utf-8") == "shared"
    assert db_session.query(ChatSession).filter_by(session_id="legacy_a").first() is None
    assert db_session.query(StoredFile).filter_by(session_id="legacy_a").count() == 0
    assert db_session.query(StoredFile).filter_by(session_id="legacy_b").count() == 1
