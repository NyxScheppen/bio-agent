import stat
import zipfile
from pathlib import Path

import pytest

from app.agent.tool_registry import get_tool_meta
from app.agent.tool_runner import collect_generated_files
from app.tools import omics_input, perturbation_tools, scrna_tools, spatial_tools
from app.tools.omics_input import OmicsInputError, PreparedOmicsInput


HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


def _zip(path: Path, members: dict[str, bytes], compression=zipfile.ZIP_STORED) -> Path:
    with zipfile.ZipFile(path, "w", compression=compression) as bundle:
        for name, content in members.items():
            bundle.writestr(name, content)
    return path


def _prepare(monkeypatch, tmp_path: Path, archive: Path, input_type: str):
    generated = tmp_path / "generated"
    job_dir = generated / "session" / "job"
    monkeypatch.setattr(omics_input, "GENERATED_DIR", generated)
    monkeypatch.setattr(
        omics_input,
        "resolve_file_path",
        lambda _path, session_id=None: archive,
    )
    return omics_input.prepare_omics_input(
        archive.name,
        input_type=input_type,
        job_dir=job_dir,
        session_id="session",
    )


def test_prepare_valid_10x_zip_and_cleanup(monkeypatch, tmp_path):
    archive = _zip(tmp_path / "tenx.zip", {
        "sample/filtered_feature_bc_matrix/matrix.mtx.gz": b"matrix",
        "sample/filtered_feature_bc_matrix/barcodes.tsv.gz": b"barcodes",
        "sample/filtered_feature_bc_matrix/features.tsv.gz": b"features",
    })

    prepared = _prepare(monkeypatch, tmp_path, archive, "scrna")
    assert prepared.input_kind == "mtx_dir"
    assert prepared.path.name == "filtered_feature_bc_matrix"
    assert (prepared.path / "matrix.mtx.gz").is_file()
    assert (prepared.path / "barcodes.tsv.gz").is_file()
    assert (prepared.path / "features.tsv.gz").is_file()
    assert prepared.cleanup_dir and prepared.cleanup_dir.exists()
    prepared.cleanup()
    assert not prepared.cleanup_dir.exists()


def test_prepare_valid_10x_h5(monkeypatch, tmp_path):
    source = tmp_path / "filtered_feature_bc_matrix.h5"
    source.write_bytes(HDF5_MAGIC + b"fake-h5-body")

    prepared = _prepare(monkeypatch, tmp_path, source, "scrna")
    assert prepared.input_kind == "h5"
    assert prepared.path == source.resolve()
    assert prepared.cleanup_dir is None


def test_prepare_valid_visium_zip(monkeypatch, tmp_path):
    archive = _zip(tmp_path / "visium.zip", {
        "outs/filtered_feature_bc_matrix.h5": HDF5_MAGIC + b"fake-h5-body",
        "outs/spatial/tissue_positions.csv": b"barcode,in_tissue,array_row,array_col,pxl_row_in_fullres,pxl_col_in_fullres\n",
        "outs/spatial/scalefactors_json.json": b"{}",
        "outs/spatial/tissue_lowres_image.png": b"not-decoded-by-preflight",
    })

    prepared = _prepare(monkeypatch, tmp_path, archive, "visium")
    assert prepared.input_kind == "visium_dir"
    assert prepared.path.name == "outs"
    prepared.cleanup()


@pytest.mark.parametrize("unsafe_name", ["../matrix.mtx", "/matrix.mtx", "C:/matrix.mtx"])
def test_zip_rejects_unsafe_paths(monkeypatch, tmp_path, unsafe_name):
    archive = _zip(tmp_path / "unsafe.zip", {unsafe_name: b"bad"})
    with pytest.raises(OmicsInputError, match="Unsafe ZIP member path"):
        _prepare(monkeypatch, tmp_path, archive, "scrna")


def test_zip_rejects_case_insensitive_duplicates(monkeypatch, tmp_path):
    archive = _zip(tmp_path / "duplicate.zip", {
        "data/matrix.mtx": b"one",
        "DATA/MATRIX.MTX": b"two",
    })
    with pytest.raises(OmicsInputError, match="duplicate case-insensitive"):
        _prepare(monkeypatch, tmp_path, archive, "scrna")


def test_zip_rejects_symlinks(monkeypatch, tmp_path):
    archive = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        info = zipfile.ZipInfo("data/matrix.mtx")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, "target")
    with pytest.raises(OmicsInputError, match="symlinks"):
        _prepare(monkeypatch, tmp_path, archive, "scrna")


def test_zip_rejects_entry_budget_before_extraction(monkeypatch, tmp_path):
    archive = _zip(tmp_path / "many.zip", {"a": b"1", "b": b"2"})
    monkeypatch.setattr(omics_input, "MAX_ARCHIVE_ENTRIES", 1)
    with pytest.raises(OmicsInputError, match="too many entries"):
        _prepare(monkeypatch, tmp_path, archive, "scrna")


def test_zip_rejects_high_compression_ratio(monkeypatch, tmp_path):
    archive = _zip(
        tmp_path / "bomb.zip",
        {"data/matrix.mtx": b"A" * (1024 * 1024)},
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(OmicsInputError, match="compression ratio"):
        _prepare(monkeypatch, tmp_path, archive, "scrna")


def test_zip_rejects_missing_10x_and_visium_layouts(monkeypatch, tmp_path):
    archive = _zip(tmp_path / "missing.zip", {"notes.txt": b"not a dataset"})
    with pytest.raises(OmicsInputError, match="complete 10X matrix"):
        _prepare(monkeypatch, tmp_path, archive, "scrna")
    with pytest.raises(OmicsInputError, match="complete Visium output"):
        _prepare(monkeypatch, tmp_path, archive, "visium")


def test_private_staged_inputs_are_not_collected_as_outputs(tmp_path):
    job_dir = tmp_path / "job"
    private = job_dir / ".omics-input-deadbeef"
    private.mkdir(parents=True)
    (private / "matrix.mtx").write_text("private", encoding="utf-8")
    (job_dir / "result.csv").write_text("result", encoding="utf-8")

    outputs = collect_generated_files(str(job_dir))
    assert [item["name"] for item in outputs] == ["result.csv"]


def test_scrna_atomic_pipeline_builds_qc_clustering_and_marker_code(monkeypatch, tmp_path):
    h5 = tmp_path / "input.h5"
    h5.write_bytes(HDF5_MAGIC)
    job_dir = tmp_path / "generated" / "session" / "job"
    job_dir.mkdir(parents=True)
    captured = {}

    monkeypatch.setattr(scrna_tools, "prepare_r_job_dir", lambda *_: job_dir)
    monkeypatch.setattr(
        scrna_tools,
        "prepare_omics_input",
        lambda **_: PreparedOmicsInput(h5, "h5"),
    )
    monkeypatch.setattr(
        scrna_tools,
        "run_r_analysis",
        lambda code, **kwargs: captured.update(code=code, kwargs=kwargs) or {"status": "success", "output_files": []},
    )

    result = scrna_tools.run_scrna_standard_pipeline(
        "input.h5",
        min_features=100,
        max_features=5000,
        max_mt_percent=15,
    )
    assert result["status"] == "success"
    assert "Read10X_h5" in captured["code"]
    assert "Matrix::readMM" in captured["code"]
    assert "obj$nFeature_RNA >= 100" in captured["code"]
    assert "obj$nFeature_RNA <= 5000" in captured["code"]
    assert "obj$percent.mt <= 15.0" in captured["code"]
    assert "FindAllMarkers" in captured["code"]
    assert "scrna_software_versions.csv" in captured["code"]
    assert get_tool_meta("run_scrna_standard_pipeline")["category"] == "scrna"


def test_visium_atomic_pipeline_is_honest_about_clustering(monkeypatch, tmp_path):
    visium_dir = tmp_path / "visium"
    visium_dir.mkdir()
    job_dir = tmp_path / "generated" / "session" / "job"
    job_dir.mkdir(parents=True)
    captured = {}

    monkeypatch.setattr(spatial_tools, "prepare_r_job_dir", lambda *_: job_dir)
    monkeypatch.setattr(
        spatial_tools,
        "prepare_omics_input",
        lambda **_: PreparedOmicsInput(visium_dir, "visium_dir"),
    )
    monkeypatch.setattr(
        spatial_tools,
        "run_r_analysis",
        lambda code, **kwargs: captured.update(code=code, kwargs=kwargs) or {"status": "success", "output_files": []},
    )

    result = spatial_tools.run_visium_standard_pipeline("visium.zip", feature_genes=["TP53"])
    assert result["status"] == "success"
    assert "Load10X_Spatial" in captured["code"]
    assert "SCTransform" in captured["code"]
    assert "not spatial-aware clustering" in captured["code"]
    assert "SpatialFeaturePlot" in captured["code"]
    assert get_tool_meta("run_visium_standard_pipeline")["category"] == "spatial"


def test_perturbation_tools_distinguish_scaling_from_observed_response(monkeypatch):
    captured = []
    monkeypatch.setattr(
        perturbation_tools,
        "run_r_analysis",
        lambda code, **kwargs: captured.append(code) or {"status": "success"},
    )

    scaling = perturbation_tools.run_expression_scaling_scenario("expr.csv", "TP53", 0.7)
    observed = perturbation_tools.run_observed_perturbation_response_analysis(
        "expr.csv",
        "meta.csv",
        "control",
        "treated",
    )
    assert scaling["status"] == observed["status"] == "success"
    assert "predicts_downstream_response = FALSE" in captured[0]
    assert "not a knockout prediction" in captured[0]
    assert "library(DESeq2)" in captured[1]
    assert "row.names = samples" in captured[1]
    assert "estimateDispersionsGeneEst" in captured[1]
    assert "library(limma)" in captured[1]
    assert "not a virtual perturbation prediction" in captured[1]
    assert get_tool_meta("run_expression_scaling_scenario")["category"] == "perturbation"
    assert get_tool_meta("run_observed_perturbation_response_analysis")["category"] == "perturbation"


def test_omics_parameter_validation_happens_before_r(monkeypatch):
    monkeypatch.setattr(
        perturbation_tools,
        "run_r_analysis",
        lambda *_args, **_kwargs: pytest.fail("R must not run"),
    )
    with pytest.raises(ValueError, match="scaling_ratio"):
        perturbation_tools.run_expression_scaling_scenario("expr.csv", "TP53", 1.1)
    with pytest.raises(ValueError, match="must be different"):
        perturbation_tools.run_observed_perturbation_response_analysis(
            "expr.csv", "meta.csv", "same", "same"
        )


def test_deseq2_small_matrix_uses_full_variance_stabilization(monkeypatch):
    import app.tools.transcriptome_tools as transcriptome_tools

    captured = {}
    monkeypatch.setattr(
        transcriptome_tools,
        "run_r_analysis",
        lambda code, **kwargs: captured.update(code=code) or {"status": "success"},
    )
    transcriptome_tools.run_deseq2_count_deg_analysis(
        "counts.csv", "groups.csv", "control", "treated"
    )
    assert "nrow(dds) < 1000" in captured["code"]
    assert "varianceStabilizingTransformation" in captured["code"]
