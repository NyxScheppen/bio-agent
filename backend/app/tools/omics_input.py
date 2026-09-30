"""Secure preparation of uploaded 10X and Visium inputs."""

from __future__ import annotations

import gzip
import shutil
import stat
import struct
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from app.core.runtime_paths import GENERATED_DIR
from app.utils.file_resolver import resolve_file_path


MAX_ARCHIVE_ENTRIES = 512
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
_HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


class OmicsInputError(ValueError):
    """Raised when an uploaded omics input violates its format contract."""


@dataclass
class PreparedOmicsInput:
    path: Path
    input_kind: str
    cleanup_dir: Path | None = None

    def cleanup(self) -> None:
        if self.cleanup_dir is None or not self.cleanup_dir.exists():
            return
        generated_root = Path(GENERATED_DIR).resolve()
        cleanup_root = self.cleanup_dir.resolve()
        try:
            cleanup_root.relative_to(generated_root)
        except ValueError as exc:
            raise RuntimeError("Refusing to clean an input directory outside generated") from exc
        shutil.rmtree(cleanup_root)


def _validated_job_root(job_dir: str | Path) -> Path:
    root = Path(job_dir).resolve()
    try:
        root.relative_to(Path(GENERATED_DIR).resolve())
    except ValueError as exc:
        raise OmicsInputError("Omics job_dir must be inside generated") from exc
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_eocd_entry_count(path: Path) -> int:
    """Read the classic ZIP entry count without materializing the central directory."""
    file_size = path.stat().st_size
    tail_size = min(file_size, 65_557)
    with path.open("rb") as handle:
        handle.seek(file_size - tail_size)
        tail = handle.read(tail_size)

    signature = b"PK\x05\x06"
    position = tail.rfind(signature)
    while position >= 0:
        if position + 22 <= len(tail):
            fields = struct.unpack_from("<4s4H2LH", tail, position)
            comment_length = fields[-1]
            if position + 22 + comment_length == len(tail):
                disk_number, directory_disk = fields[1], fields[2]
                entries_on_disk, entries_total = fields[3], fields[4]
                if disk_number != 0 or directory_disk != 0 or entries_on_disk != entries_total:
                    raise OmicsInputError("Multi-disk ZIP archives are not supported")
                if entries_total == 0xFFFF:
                    raise OmicsInputError("ZIP64 archives are not supported")
                return entries_total
        position = tail.rfind(signature, 0, position)
    raise OmicsInputError("Invalid ZIP archive: end-of-central-directory record not found")


def _safe_member_path(filename: str) -> PurePosixPath:
    normalized = str(filename or "").replace("\\", "/")
    member = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or member.is_absolute()
        or any(part in {"", ".", ".."} for part in member.parts)
        or any(":" in part for part in member.parts)
    ):
        raise OmicsInputError(f"Unsafe ZIP member path: {filename!r}")
    return member


def _validate_zip_members(archive: Path, infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise OmicsInputError(
            f"ZIP contains too many entries ({len(infos)} > {MAX_ARCHIVE_ENTRIES})"
        )

    seen: set[str] = set()
    expanded_total = 0
    compressed_total = 0
    for info in infos:
        member = _safe_member_path(info.filename)
        key = member.as_posix().casefold().rstrip("/")
        if key in seen:
            raise OmicsInputError(f"ZIP contains duplicate case-insensitive path: {info.filename}")
        seen.add(key)

        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(unix_mode):
            raise OmicsInputError(f"ZIP symlinks are not allowed: {info.filename}")
        if info.flag_bits & 0x1:
            raise OmicsInputError("Encrypted ZIP entries are not supported")
        if info.file_size < 0 or info.compress_size < 0:
            raise OmicsInputError("ZIP contains an invalid member size")
        if info.file_size > MAX_MEMBER_BYTES:
            raise OmicsInputError(f"ZIP member is too large: {info.filename}")

        expanded_total += info.file_size
        compressed_total += info.compress_size
        if expanded_total > MAX_EXPANDED_BYTES:
            raise OmicsInputError("ZIP expanded-size budget exceeded")
        if info.file_size and info.compress_size == 0:
            raise OmicsInputError(f"ZIP member has an unsafe compression ratio: {info.filename}")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise OmicsInputError(f"ZIP member compression ratio is too high: {info.filename}")

    if compressed_total and expanded_total / compressed_total > MAX_COMPRESSION_RATIO:
        raise OmicsInputError("ZIP aggregate compression ratio is too high")


def _extract_validated_zip(archive: Path, destination: Path) -> None:
    declared_count = _read_eocd_entry_count(archive)
    if declared_count > MAX_ARCHIVE_ENTRIES:
        raise OmicsInputError(
            f"ZIP contains too many entries ({declared_count} > {MAX_ARCHIVE_ENTRIES})"
        )

    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if declared_count != len(infos):
            raise OmicsInputError("ZIP central-directory entry count is inconsistent")
        _validate_zip_members(archive, infos)

        written = 0
        for info in infos:
            relative = _safe_member_path(info.filename)
            target = destination.joinpath(*relative.parts)
            try:
                target.resolve().relative_to(destination.resolve())
            except ValueError as exc:
                raise OmicsInputError(f"ZIP member escapes extraction root: {info.filename}") from exc

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            member_written = 0
            with bundle.open(info, "r") as source, target.open("xb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    member_written += len(chunk)
                    written += len(chunk)
                    if member_written > MAX_MEMBER_BYTES or written > MAX_EXPANDED_BYTES:
                        raise OmicsInputError("ZIP expanded-size budget exceeded while extracting")
                    output.write(chunk)


def _validate_hdf5(path: Path) -> None:
    with path.open("rb") as handle:
        if handle.read(len(_HDF5_MAGIC)) != _HDF5_MAGIC:
            raise OmicsInputError("The .h5 input does not have a valid HDF5 signature")


def _find_10x_input(root: Path) -> tuple[Path, str]:
    matrix_sets: dict[Path, set[str]] = {}
    h5_files: list[Path] = []
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        lowered = candidate.name.casefold()
        if lowered in {"filtered_feature_bc_matrix.h5", "raw_feature_bc_matrix.h5"}:
            h5_files.append(candidate)
        base = lowered[:-3] if lowered.endswith(".gz") else lowered
        if base == "matrix.mtx":
            matrix_sets.setdefault(candidate.parent, set()).add("matrix")
        elif base == "barcodes.tsv":
            matrix_sets.setdefault(candidate.parent, set()).add("barcodes")
        elif base in {"features.tsv", "genes.tsv"}:
            matrix_sets.setdefault(candidate.parent, set()).add("features")

    complete_dirs = [path for path, parts in matrix_sets.items() if parts == {"matrix", "barcodes", "features"}]
    candidates: list[tuple[Path, str]] = [(path, "mtx_dir") for path in complete_dirs]
    candidates.extend((path, "h5") for path in h5_files)
    if not candidates:
        raise OmicsInputError(
            "ZIP does not contain one complete 10X matrix (matrix.mtx, barcodes.tsv, features.tsv) or 10X H5 file"
        )
    if len(candidates) != 1:
        raise OmicsInputError("ZIP contains multiple 10X matrices; upload one dataset per archive")
    if candidates[0][1] == "h5":
        _validate_hdf5(candidates[0][0])
    return candidates[0]


def _normalize_10x_text_files(matrix_dir: Path) -> None:
    """Compress uncompressed 10X text members for Seurat 5 Read10X."""
    for filename in ("matrix.mtx", "barcodes.tsv", "features.tsv", "genes.tsv"):
        source = matrix_dir / filename
        target = matrix_dir / f"{filename}.gz"
        if not source.is_file() or target.exists():
            continue
        with source.open("rb") as input_handle, gzip.open(target, "xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
        source.unlink()


def _find_visium_root(root: Path) -> Path:
    candidates: list[Path] = []
    for matrix_file in root.rglob("filtered_feature_bc_matrix.h5"):
        if not matrix_file.is_file():
            continue
        visium_root = matrix_file.parent
        spatial = visium_root / "spatial"
        positions = [spatial / "tissue_positions.csv", spatial / "tissue_positions_list.csv"]
        images = [spatial / "tissue_lowres_image.png", spatial / "tissue_hires_image.png"]
        if (
            spatial.is_dir()
            and any(path.is_file() for path in positions)
            and (spatial / "scalefactors_json.json").is_file()
            and any(path.is_file() for path in images)
        ):
            _validate_hdf5(matrix_file)
            candidates.append(visium_root)

    if not candidates:
        raise OmicsInputError(
            "ZIP is not a complete Visium output: filtered_feature_bc_matrix.h5 and required spatial files are missing"
        )
    if len(candidates) != 1:
        raise OmicsInputError("ZIP contains multiple Visium datasets; upload one dataset per archive")
    return candidates[0]


def prepare_omics_input(
    input_file: str,
    input_type: Literal["scrna", "visium"],
    job_dir: str | Path,
    session_id: str = "",
) -> PreparedOmicsInput:
    """Resolve and validate one uploaded H5/ZIP input for an atomic workflow."""
    source = resolve_file_path(input_file, session_id=session_id or None)
    if source is None or not source.is_file():
        raise OmicsInputError(f"Input file does not exist in the current session: {input_file}")

    suffix = source.suffix.casefold()
    if input_type == "scrna" and suffix in {".h5", ".hdf5"}:
        _validate_hdf5(source)
        return PreparedOmicsInput(path=source.resolve(), input_kind="h5")
    if suffix != ".zip":
        expected = "10X .h5 or .zip" if input_type == "scrna" else "Visium .zip"
        raise OmicsInputError(f"Unsupported input format; expected {expected}")

    job_root = _validated_job_root(job_dir)
    extraction_root = job_root / f".omics-input-{uuid.uuid4().hex[:10]}"
    extraction_root.mkdir(parents=False, exist_ok=False)
    try:
        _extract_validated_zip(source, extraction_root)
        if input_type == "scrna":
            path, kind = _find_10x_input(extraction_root)
            if kind == "mtx_dir":
                _normalize_10x_text_files(path)
        else:
            path, kind = _find_visium_root(extraction_root), "visium_dir"
        return PreparedOmicsInput(path=path.resolve(), input_kind=kind, cleanup_dir=extraction_root)
    except Exception:
        shutil.rmtree(extraction_root, ignore_errors=True)
        raise


def run_with_prepared_input(prepared: PreparedOmicsInput, runner, *args, **kwargs):
    """Run a tool and remove staged source data from both disk and its result."""
    cleanup_root = prepared.cleanup_dir.resolve() if prepared.cleanup_dir else None
    try:
        result = runner(*args, **kwargs)
        if cleanup_root is not None and isinstance(result, dict):
            kept = []
            for item in result.get("output_files", []) or []:
                raw_path = item.get("path") if isinstance(item, dict) else None
                try:
                    if raw_path and Path(raw_path).resolve().is_relative_to(cleanup_root):
                        continue
                except (OSError, ValueError):
                    continue
                kept.append(item)
            result["output_files"] = kept
        return result
    finally:
        prepared.cleanup()
