from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_documented_capability_counts_match_runtime():
    from app import tools  # noqa: F401
    from app.agent.commands import COMMANDS
    from app.agent.skills.skill_loader import load_all_skill_packs
    from app.agent.skills.skill_registry import SKILL_REGISTRY

    SKILL_REGISTRY.clear()
    skills = load_all_skill_packs()
    status_counts = {
        status: sum(skill.implementation_status == status for skill in skills)
        for status in ("implemented", "partial", "planned")
    }
    categories = {skill.category for skill in skills}
    pack_count = len(list((PROJECT_ROOT / "backend/app/agent/skills/packs").glob("*.yaml")))

    clean_registry_count = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import app.tools; "
                "from app.agent.tool_registry import TOOL_REGISTRY; "
                "print(len(TOOL_REGISTRY))"
            ),
        ],
        cwd=PROJECT_ROOT / "backend",
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert clean_registry_count == "40"
    assert len(COMMANDS) == 21
    assert len(skills) == 54
    assert status_counts == {"implemented": 22, "partial": 3, "planned": 29}
    assert len(categories) == 15
    assert pack_count == 16


def test_r_installer_uses_its_own_directory_as_project_root():
    script = (PROJECT_ROOT / "install_r_packages.R").read_text(encoding="utf-8")

    assert 'project_root <- normalizePath(dirname(script_path)' in script
    assert 'file.path(dirname(script_path), "..")' not in script


def test_help_and_commands_expose_capability_status():
    from app.agent.commands import build_help_response, resolve_command

    help_text = build_help_response()["help_text"]
    assert "`/risk` [已实现]" in help_text
    assert "`/geo` [部分实现]" in help_text
    assert "`/scrna` [已实现]" in help_text
    assert "`/spatial` [已实现]" in help_text
    assert "`/perturb` [已实现]" in help_text

    scrna = resolve_command("/scrna analyze 10x")
    geo = resolve_command("/geo parse uploaded series_matrix")
    assert scrna["implementation_status"] == "implemented"
    assert "availability_message" not in scrna
    assert geo["implementation_status"] == "partial"


def test_scrna_command_enables_tool_execution():
    from app.agent.router_agent import _try_resolve_command

    result = _try_resolve_command("/scrna analyze 10x")
    assert result["suggested_mode"] == "tool_execution"
    assert result["capability_status"] == "implemented"
    assert result["command_skill"] == "scrna_standard_pipeline"


def test_natural_language_planned_skill_stops_before_planner(monkeypatch):
    import app.agent.bio_agent as bio_agent
    from app.agent.skills.skill_models import SkillSpec

    context = {
        "latest_user_message": "做单细胞聚类",
        "summary": "",
        "recent_messages": [],
    }
    monkeypatch.setattr(bio_agent, "maybe_compact_context", lambda *_args, **_kwargs: dict(context))
    monkeypatch.setattr(bio_agent, "enrich_context_with_session_memory", lambda context_pack, **_: context_pack)
    monkeypatch.setattr(bio_agent, "resolve_short_user_reply", lambda context_pack, **_: context_pack)
    monkeypatch.setattr(bio_agent, "run_router_agent", lambda _: {
        "task_type": "bioinformatics",
        "subtask_type": "scrna_analysis",
        "suggested_mode": "tool_execution",
    })
    monkeypatch.setattr(bio_agent, "select_skill", lambda **_: SkillSpec(
        skill_id="scrna_standard_pipeline",
        name="单细胞标准分析流程",
        implementation_status="planned",
    ))
    monkeypatch.setattr(
        bio_agent,
        "run_planner_agent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("planner must not run")),
    )
    monkeypatch.setattr(bio_agent, "remember_agent_turn", lambda **_: None)

    result = bio_agent._run_bio_agent_sync([], session_id="planned-test")
    assert "规划阶段" in result["answer"]
    assert result["files"] == []


def test_ml_tools_reject_unsupported_algorithms_before_r_execution(monkeypatch):
    import app.tools.ml_tools as ml_tools

    monkeypatch.setattr(
        ml_tools,
        "run_r_analysis",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("R must not run")),
    )
    single = ml_tools.run_ml_classification_model("missing.csv", "label", "xgboost")
    multiple = ml_tools.run_multi_model_comparison(
        "missing.csv", "label", ["rf", "xgboost"]
    )
    empty = ml_tools.run_multi_model_comparison("missing.csv", "label", [])

    assert single.status == "error" and single.errors == ["unsupported_algorithm"]
    assert multiple.status == "error" and multiple.errors == ["unsupported_algorithm"]
    assert empty.status == "error" and empty.errors == ["invalid_algorithms"]


def test_ml_templates_define_dataframe_before_feature_columns(monkeypatch):
    import app.tools.ml_tools as ml_tools

    captured = []

    def capture(r_code, **_kwargs):
        captured.append(r_code)
        return {"status": "success"}

    monkeypatch.setattr(ml_tools, "run_r_analysis", capture)

    ml_tools.run_ml_classification_model("data.csv", "label", "logistic")
    ml_tools.run_ml_feature_selection_lasso("data.csv", "label")
    ml_tools.run_multi_model_comparison("data.csv", "label", ["logistic"])

    assert len(captured) == 3
    for r_code in captured:
        read_pos = r_code.index("df <- fread(")
        validate_pos = r_code.index('if (!("label" %in% colnames(df)))')
        features_pos = r_code.index('feature_cols <- setdiff(colnames(df), "label")')
        assert read_pos < validate_pos < features_pos


def test_network_report_runtime_dependency_and_rendering(tmp_path):
    import pandas as pd
    import tabulate  # noqa: F401 - pandas.DataFrame.to_markdown runtime dependency

    from app.tools.network_pharmacology_tools import _write_report

    report_path = tmp_path / "ppi_report.md"
    _write_report(
        out_path=report_path,
        herbs="",
        disease="",
        ob_threshold=0,
        dl_threshold=0,
        active_compound_count=0,
        drug_target_count=2,
        disease_target_count=0,
        intersection_count=2,
        ppi_edge_count=1,
        core_df=pd.DataFrame(
            [{"gene": "TP53", "degree": 1, "betweenness": 0.0}]
        ),
        string_status="success",
    )

    text = report_path.read_text(encoding="utf-8")
    assert "TP53" in text
    assert "STRING" in text


def test_enrichment_templates_isolate_go_kegg_and_use_current_msigdbr_api(monkeypatch):
    import app.tools.enrichment_tools as enrichment_tools

    captured = []

    def capture(r_code, **kwargs):
        captured.append((r_code, kwargs))
        return {"status": "success"}

    monkeypatch.setattr(enrichment_tools, "run_r_analysis", capture)
    monkeypatch.setattr(
        enrichment_tools,
        "_diagnose_dns",
        lambda host: {
            "host": host,
            "status": "ok",
            "addresses": ["203.0.113.10"],
            "sinkhole_addresses": [],
            "error": "",
            "reason": "public_addresses_resolved",
        },
    )

    enrichment_tools.run_go_kegg_enrichment("genes.csv")
    enrichment_tools.run_gsea_analysis("ranked.csv")

    go_code, go_kwargs = captured[0]
    gsea_code, gsea_kwargs = captured[1]
    assert "enrichment_status.csv" in go_code
    assert go_code.count("tryCatch({") >= 4
    assert 'component = c("GO", "KEGG")' in go_code
    assert "options(timeout = 30L)" in go_code
    assert "for (attempt in seq_len(2L))" in go_code
    assert go_kwargs.get("timeout", 300) == 300

    assert 'collection = "H"' in gsea_code
    assert 'category = "H"' not in gsea_code
    assert 'Sys.setenv(R_USER_CACHE_DIR = msigdb_cache_root)' in gsea_code
    assert "BiocParallel::register(BiocParallel::SerialParam())" in gsea_code
    assert '"ncbi_gene" %in% colnames(m_df)' in gsea_code
    assert '"entrez_gene" %in% colnames(m_df)' in gsea_code
    assert "is.finite(df$score)" in gsea_code
    assert "if (nrow(df2) < 10L)" in gsea_code
    assert "if (max_gene_set_overlap < 10L)" in gsea_code
    assert '"pos"' in gsea_code
    assert '"neg"' in gsea_code
    assert '"std"' in gsea_code
    assert "scoreType = score_type" in gsea_code
    assert "minGSSize = 10" in gsea_code
    assert "options(timeout = 600L)" in gsea_code
    assert gsea_kwargs["timeout"] == enrichment_tools.GSEA_R_TIMEOUT_SECONDS
    assert gsea_kwargs["timeout"] > 600
    from app.agent.tool_registry import get_tool_meta

    assert (
        get_tool_meta("run_gsea_analysis")["timeout"]
        == enrichment_tools.GSEA_R_TIMEOUT_SECONDS
    )


def test_gsea_dns_diagnostic_flags_sinkhole_answers(monkeypatch):
    import socket

    import app.tools.enrichment_tools as enrichment_tools

    monkeypatch.setattr(
        enrichment_tools.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("0.0.0.0", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::", 443, 0, 0)),
        ],
    )

    diagnostic = enrichment_tools._diagnose_dns("zenodo.org")

    assert diagnostic["status"] == "sinkhole"
    assert diagnostic["reason"] == "resolved_to_non_routable_address"
    assert diagnostic["sinkhole_addresses"] == [
        "0.0.0.0",
        "10.0.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "::",
    ]


def test_gsea_dns_diagnostic_accepts_public_addresses(monkeypatch):
    import socket

    import app.tools.enrichment_tools as enrichment_tools

    monkeypatch.setattr(
        enrichment_tools.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                6,
                "",
                ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
            ),
        ],
    )

    diagnostic = enrichment_tools._diagnose_dns("zenodo.org")

    assert diagnostic["status"] == "ok"
    assert diagnostic["sinkhole_addresses"] == []
    assert len(diagnostic["addresses"]) == 2


def test_gsea_dns_diagnostic_reports_resolution_error(monkeypatch):
    import app.tools.enrichment_tools as enrichment_tools

    def fail_resolution(*_args, **_kwargs):
        raise OSError("temporary resolver failure")

    monkeypatch.setattr(enrichment_tools.socket, "getaddrinfo", fail_resolution)

    diagnostic = enrichment_tools._diagnose_dns("zenodo.org")

    assert diagnostic["status"] == "error"
    assert diagnostic["reason"] == "dns_resolution_failed"
    assert diagnostic["addresses"] == []
    assert diagnostic["error"] == "temporary resolver failure"


def test_gsea_dns_failure_returns_diagnostic_without_starting_r(monkeypatch):
    import app.tools.enrichment_tools as enrichment_tools

    diagnostic = {
        "host": "zenodo.org",
        "status": "sinkhole",
        "addresses": ["0.0.0.0", "::"],
        "sinkhole_addresses": ["0.0.0.0", "::"],
        "error": "",
        "reason": "resolved_to_non_routable_address",
    }
    monkeypatch.setattr(enrichment_tools, "_diagnose_dns", lambda _host: diagnostic)
    monkeypatch.setattr(
        enrichment_tools,
        "_diagnose_msigdb_cache",
        lambda: {"cache_dir": "X:/missing", "archive_present": False, "archives": []},
    )

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("R must not start when the dependency DNS is sinkholed")

    monkeypatch.setattr(enrichment_tools, "run_r_analysis", must_not_run)

    result = enrichment_tools.run_gsea_analysis("ranked.csv")

    assert result["status"] == "error"
    assert result["errors"] == ["gsea_dependency_dns_unavailable"]
    assert result["summary"]["failure_stage"] == "dns_resolution"
    assert result["summary"]["dns_diagnostic"] == diagnostic
    assert "不是 HTTP 402" in result["message"]


def test_gsea_r_dns_failure_is_reclassified_with_stable_error_code():
    from app.tools.enrichment_tools import _annotate_gsea_result

    diagnostic = {
        "host": "zenodo.org",
        "status": "ok",
        "addresses": ["192.0.2.1"],
        "sinkhole_addresses": [],
        "error": "",
        "reason": "public_addresses_resolved",
    }
    result = _annotate_gsea_result(
        {
            "status": "error",
            "message": "R execution failed",
            "stderr": "curl: (6) Could not resolve host: zenodo.org",
        },
        diagnostic,
        {"cache_dir": "X:/cache", "archive_present": False, "archives": []},
    )

    assert result["summary"]["failure_stage"] == "dns_resolution"
    assert result["errors"] == ["gsea_dependency_dns_unavailable"]
    assert "不是 HTTP 402" in result["message"]


def test_gsea_analysis_failure_has_message_and_stable_error_code():
    from app.tools.enrichment_tools import _annotate_gsea_result

    result = _annotate_gsea_result(
        {"status": "error", "returncode": 1, "stderr": "unexpected analysis error"},
        {
            "host": "zenodo.org",
            "status": "ok",
            "addresses": ["192.0.2.1"],
            "sinkhole_addresses": [],
            "error": "",
            "reason": "public_addresses_resolved",
        },
        {"cache_dir": "X:/cache", "archive_present": False, "archives": []},
    )

    assert result["summary"]["failure_stage"] == "analysis"
    assert result["errors"] == ["gsea_analysis_failed"]
    assert result["message"] == "GSEA 分析失败，请查看 stderr 与 gsea_diagnostics.csv。"


def test_gsea_mapping_precheck_returns_structured_input_error(tmp_path):
    from app.tools.enrichment_tools import _annotate_gsea_result

    (tmp_path / "gsea_diagnostics.csv").write_text(
        '"metric","value"\n'
        '"unique_input_gene_count","80"\n'
        '"mapped_entrez_count","5"\n'
        '"mapping_rate","0.062500"\n',
        encoding="utf-8",
    )
    result = _annotate_gsea_result(
        {"status": "error", "job_dir": str(tmp_path), "stderr": "mapping failed"},
        {
            "host": "zenodo.org",
            "status": "error",
            "addresses": [],
            "sinkhole_addresses": [],
            "error": "getaddrinfo failed",
            "reason": "dns_resolution_failed",
        },
        {
            "cache_dir": str(tmp_path),
            "archive_present": True,
            "archives": ["msigdb.2026.1.zip"],
        },
    )

    assert result["summary"]["failure_stage"] == "input_validation"
    assert result["errors"] == ["gsea_insufficient_mapped_genes"]
    assert "5/80" in result["message"]
    assert "6.2%" in result["message"]


def test_gsea_can_use_project_cache_when_dns_is_unavailable(monkeypatch):
    import app.tools.enrichment_tools as enrichment_tools

    captured = {}
    monkeypatch.setattr(
        enrichment_tools,
        "_diagnose_dns",
        lambda _host: {
            "host": "zenodo.org",
            "status": "sinkhole",
            "addresses": ["0.0.0.0"],
            "sinkhole_addresses": ["0.0.0.0"],
            "error": "",
            "reason": "resolved_to_non_routable_address",
        },
    )
    monkeypatch.setattr(
        enrichment_tools,
        "_diagnose_msigdb_cache",
        lambda: {
            "cache_dir": "X:/cache",
            "archive_present": True,
            "archives": ["msigdb.2026.1.zip"],
        },
    )

    def capture(_r_code, **kwargs):
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(enrichment_tools, "run_r_analysis", capture)

    result = enrichment_tools.run_gsea_analysis("ranked.csv")

    assert result["status"] == "success"
    assert result["summary"]["using_cache_without_dns"] is True
    assert result["summary"]["cache_diagnostic"]["archive_present"] is True
    assert captured["timeout"] == enrichment_tools.GSEA_R_TIMEOUT_SECONDS


def test_enrichment_component_failure_returns_partial_status(tmp_path):
    from app.tools.enrichment_tools import _annotate_enrichment_component_status

    (tmp_path / "enrichment_status.csv").write_text(
        '"component","status","message"\n'
        '"GO","success",""\n'
        '"KEGG","error","cannot read from connection"\n',
        encoding="utf-8",
    )

    result = _annotate_enrichment_component_status(
        {"status": "success", "job_dir": str(tmp_path), "output_files": []}
    )

    assert result["status"] == "partial"
    assert result["summary"]["components"]["GO"]["status"] == "success"
    assert result["summary"]["components"]["KEGG"]["status"] == "error"
    assert result["warnings"] == ["KEGG: cannot read from connection"]


def test_enrichment_completed_branch_survives_outer_timeout_status(tmp_path):
    from app.tools.enrichment_tools import _annotate_enrichment_component_status

    (tmp_path / "enrichment_status.csv").write_text(
        '"component","status","message","attempts"\n'
        '"GO","success","","1"\n'
        '"KEGG","error","2 attempts failed: timeout","2"\n',
        encoding="utf-8",
    )

    result = _annotate_enrichment_component_status(
        {
            "status": "error",
            "message": "R 执行超时（>300 秒）",
            "job_dir": str(tmp_path),
        }
    )

    assert result["status"] == "partial"
    assert result["message"] == "GO/KEGG 富集部分完成，请查看组件状态。"
    assert result["summary"]["runner_status"] == "error"
    assert result["summary"]["runner_message"] == "R 执行超时（>300 秒）"
    assert result["summary"]["runner_timed_out"] is True
    assert result["summary"]["components"]["KEGG"]["attempts"] == "2"


def test_server_browser_url_handles_wildcard_and_ipv6_hosts():
    from app.server import browser_url

    assert browser_url("0.0.0.0", 9000) == "http://127.0.0.1:9000"
    assert browser_url("::", 9000) == "http://127.0.0.1:9000"
    assert browser_url("::1", 9000) == "http://[::1]:9000"
    assert browser_url("localhost", 9000) == "http://localhost:9000"
    assert browser_url("localhost", 9000, cache_token="build 1") == (
        "http://localhost:9000/?v=build+1"
    )


def test_server_run_opens_cache_busted_frontend(monkeypatch):
    import app.server as server

    captured = {}

    class FakeTimer:
        daemon = False

        def __init__(self, interval, function, args):
            captured["timer"] = (interval, function, args)

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(server, "frontend_build_token", lambda: "build 1")
    monkeypatch.setattr(server.threading, "Timer", FakeTimer)
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: None)

    server.run(open_browser=True)

    assert captured["timer"][2] == (
        server.browser_url(cache_token="build 1"),
    )
    assert captured["started"] is True


def test_readme_and_dependency_contracts_are_current():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    start_script = (PROJECT_ROOT / "start_app.bat").read_text(encoding="utf-8")

    assert "Python** 3.11 / 3.12" in readme
    assert "40 个注册工具" in readme
    assert "22 个已实现、3 个部分实现、29 个规划中" in readme
    assert "GEO 数据下载" not in readme
    assert "XGBoost" not in readme
    assert "PyYAML==" in requirements
    assert "networkx==" in requirements
    assert "py -3.10" not in start_script
    assert "-m app.server --open-browser" in start_script
