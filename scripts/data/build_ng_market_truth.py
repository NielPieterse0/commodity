"""Explicit-manifest, development-only Databento market-truth build.

Inputs are separately staged, private, pre-2023 decoded CSV files. Never scan a
provider archive or attempt to open confirmation namespace objects.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import errno
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from commodity.market_truth import (
    build_market_truth,
    normalize_ng_databento,
    publish_parquet,
)
from commodity.market_truth.attestation import SourceBuildAttestation
from commodity.market_truth.core import (
    MAX_DEVELOPMENT_DATE,
    MarketTruthError,
    _evidence,
)
from commodity.market_truth.ng import (
    databento_ng_settlement_eligible,
    normalize_ng_databento_record,
)

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_INPUT_ROOT = ROOT / ".work" / "runtime" / "market_truth_development"
SCHEMAS = {"definitions": "definition", "bars": "ohlcv-1d", "statistics": "statistics"}
# Small inputs preserve the original eager code path; large inputs stream to disk.
MAX_EAGER_CSV_BYTES = 16 * 1024 * 1024
MAX_SOURCE_MANIFEST_BYTES = 1024 * 1024


@contextmanager
def _private_stage(parent: Path, *, prefix: str) -> Iterator[Path]:
    """Remove only an empty stage; never recursively delete a replaced path."""
    stage = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    identity = os.stat(stage, follow_symlinks=False)
    try:
        yield stage
    finally:
        try:
            current = os.stat(stage, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise MarketTruthError("private stage pathname retargeted")
            stage.rmdir()
        except (OSError, MarketTruthError):
            # Never recursively delete a substituted or incomplete stage.
            # Retain failed work and tell the operator where it remains.
            print(f"MARKET_TRUTH_STAGE_RETAINED: {stage}", file=sys.stderr)


def _inside(path: Path, root: Path) -> Path:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise MarketTruthError("input outside approved development-only root") from exc
    if path.is_symlink():
        raise MarketTruthError("symlinked input file prohibited")
    return path


def _preflight(payload: dict, manifest_path: Path) -> dict[str, Path]:
    _inside(manifest_path, ALLOWED_INPUT_ROOT)
    permitted_keys = {
        "schema_version",
        "evidence_class",
        "protected_confirmation_accessed",
        "dataset",
        "product_code",
        "max_trade_date",
        "inputs",
    }
    if not isinstance(payload, dict) or set(payload) != permitted_keys:
        raise MarketTruthError("source manifest does not match strict contract")
    if (
        payload.get("schema_version") != 1
        or payload.get("evidence_class") != "development"
    ):
        raise MarketTruthError("development source attestation required")
    if payload.get("protected_confirmation_accessed") is not False:
        raise MarketTruthError("protected evidence flag must be explicit false")
    if payload.get("dataset") != "GLBX.MDP3" or payload.get("product_code") != "NG":
        raise MarketTruthError("unexpected Databento source identity")
    if payload.get("max_trade_date") is None:
        raise MarketTruthError("attested pre-2023 source bound required")
    try:
        end = date.fromisoformat(str(payload["max_trade_date"]))
    except ValueError as exc:
        raise MarketTruthError("invalid attested date bound") from exc
    if end > MAX_DEVELOPMENT_DATE:
        raise MarketTruthError(
            "protected_confirmation_boundary: attested data crosses 2022"
        )
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != set(SCHEMAS):
        raise MarketTruthError(
            "requires exactly definition, bar and statistic input sets"
        )
    approved = {}
    for name, schema in SCHEMAS.items():
        record = inputs[name]
        if (
            not isinstance(record, dict)
            or set(record) != {"schema", "relative_path", "sha256", "row_count"}
            or record.get("schema") != schema
        ):
            raise MarketTruthError("incorrect input schema declaration")
        if type(record.get("row_count")) is not int or record["row_count"] < 1:
            raise MarketTruthError("invalid input row_count")
        digest = record.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise MarketTruthError("missing input SHA-256")
        relative = record.get("relative_path")
        if not isinstance(relative, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+[.]csv", relative
        ):
            raise MarketTruthError("input must be explicitly declared flat CSV")
        path = _inside(ALLOWED_INPUT_ROOT / relative, ALLOWED_INPUT_ROOT)
        if not path.is_file():
            raise MarketTruthError("declared source is not a file")
        approved[name] = path
    return approved


def _read_checked_csv(path: Path, expected_sha256: str) -> list[dict]:
    """Parse the exact bounded bytes hashed, without a second pathname open."""
    with path.open("rb") as reader:
        source_bytes = reader.read(MAX_EAGER_CSV_BYTES + 1)
    if len(source_bytes) > MAX_EAGER_CSV_BYTES:
        raise MarketTruthError("eager raw input exceeds size limit")
    if hashlib.sha256(source_bytes).hexdigest() != expected_sha256:
        raise MarketTruthError("raw input SHA-256 mismatch")
    try:
        with io.StringIO(source_bytes.decode("utf-8"), newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if (
                not reader.fieldnames
                or len(reader.fieldnames) != len(set(reader.fieldnames))
                or any(not field.strip() or field != field.strip() for field in reader.fieldnames)
            ):
                raise MarketTruthError("missing or duplicate checked CSV headers")
            data = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise MarketTruthError("malformed checked CSV record")
                data.append(row)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise MarketTruthError("invalid checked source CSV encoding or format") from exc
    if not data:
        raise MarketTruthError("empty approved input")
    return data


def _publish_no_replace(candidate_dir: Path, output_dir: Path) -> None:
    """Publish a finished dataset atomically; never replace another directory."""
    if os.name == "nt":
        # Windows rename fails if the destination already exists.
        os.rename(candidate_dir, output_dir)
        return
    if sys.platform != "linux":
        raise MarketTruthError("atomic no-replace dataset publication unavailable")
    try:
        rename = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise MarketTruthError("atomic no-replace dataset publication unavailable") from exc
    rename.argtypes = (
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
    )
    rename.restype = ctypes.c_int
    # Resolve each immediate parent once to an actual directory descriptor.
    # The kernel uses these pinned directories, not a second absolute-path
    # lookup at publication time. Trusted-ancestor ownership is a separate gate.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    src_fd = os.open(candidate_dir.parent, flags)
    try:
        dest_fd = os.open(output_dir.parent, flags)
        try:
            for descriptor, parent in (
                (src_fd, candidate_dir.parent), (dest_fd, output_dir.parent)
            ):
                opened = os.fstat(descriptor)
                current = os.stat(parent, follow_symlinks=False)
                if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                    raise MarketTruthError("dataset publication parent changed")
            # RENAME_NOREPLACE prevents collision with even an empty directory.
            if rename(
                src_fd, os.fsencode(candidate_dir.name),
                dest_fd, os.fsencode(output_dir.name), 1,
            ):
                code = ctypes.get_errno()
                if code == errno.EEXIST:
                    raise MarketTruthError("refusing overwrite of existing development dataset")
                if code in {errno.ENOSYS, errno.EINVAL}:
                    raise MarketTruthError("atomic no-replace dataset publication unavailable")
                raise OSError(code, os.strerror(code), str(output_dir))
            # Detect the parent moving *after* the first check but before the
            # atomic rename. Roll back through the pinned descriptors so a
            # successful return cannot describe a moved publication path.
            parent_changed = False
            for descriptor, parent in (
                (src_fd, candidate_dir.parent), (dest_fd, output_dir.parent)
            ):
                opened = os.fstat(descriptor)
                try:
                    current = os.stat(parent, follow_symlinks=False)
                except OSError:
                    parent_changed = True
                    break
                if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                    parent_changed = True
                    break
            if parent_changed:
                if rename(
                    dest_fd, os.fsencode(output_dir.name),
                    src_fd, os.fsencode(candidate_dir.name), 1,
                ):
                    raise MarketTruthError("dataset publication parent changed; rollback failed")
                raise MarketTruthError("dataset publication parent changed; rolled back")
        finally:
            os.close(dest_fd)
    finally:
        os.close(src_fd)


def _assert_atomic_publication_supported(parent: Path) -> None:
    """Reject unsupported filesystems before expensive streaming ingestion."""
    with _private_stage(parent, prefix=".market-truth-atomic-probe-") as probe_root:
        source = probe_root / "candidate"
        source.mkdir()
        try:
            _publish_no_replace(source, probe_root / "published")
        finally:
            for empty in (source, probe_root / "published"):
                try:
                    empty.rmdir()
                except OSError:
                    pass


def _adapt_bar_availability(bars: list[dict]) -> list[dict]:
    """Provider-configured conservative trade-date 23:59 UTC bound."""
    adapted = []
    for row in bars:
        out = dict(row)
        try:
            trade_day = date.fromisoformat(str(row["trade_date"]))
        except ValueError as exc:
            raise MarketTruthError("trade_date required from decoded source") from exc
        if trade_day > MAX_DEVELOPMENT_DATE:
            raise MarketTruthError(
                "protected_confirmation_boundary: bar outside development"
            )
        if not out.get("available_at"):
            out["available_at"] = (
                datetime.combine(trade_day, datetime.min.time(), tzinfo=UTC)
                .replace(hour=23, minute=59)
                .isoformat()
            )
        adapted.append(out)
    return adapted


def _adapt_statistics_dates(stats: list[dict]) -> list[dict]:
    normalized = []
    for row in stats:
        out = dict(row)
        if not out.get("trade_date"):
            if not out.get("ts_ref"):
                raise MarketTruthError("statistic trade_date/ts_ref missing")
            out["trade_date"] = str(out["ts_ref"])[:10]
        normalized.append(out)
    return normalized


def build_from_manifest(
    manifest_path: Path, output_dir: Path, *, streaming: bool = False
) -> dict:
    # Enforce namespace *before* reading even the manifest bytes.
    manifest_path = _inside(manifest_path, ALLOWED_INPUT_ROOT)
    with manifest_path.open("rb") as stream:
        source_bytes = stream.read(MAX_SOURCE_MANIFEST_BYTES + 1)
    if len(source_bytes) > MAX_SOURCE_MANIFEST_BYTES:
        raise MarketTruthError("source manifest exceeds size limit")
    payload = json.loads(source_bytes.decode("utf-8"))
    source_manifest_sha256 = hashlib.sha256(source_bytes).hexdigest()
    paths = _preflight(payload, manifest_path)
    streaming = streaming or sum(
        path.stat().st_size for path in paths.values()
    ) > MAX_EAGER_CSV_BYTES
    if (
        output_dir.is_symlink()
        or output_dir.resolve().is_relative_to(ALLOWED_INPUT_ROOT.resolve()) is False
    ):
        raise MarketTruthError("output outside approved development-only root")
    if output_dir.exists():
        raise MarketTruthError("refusing overwrite of existing development dataset")
    config_sha256 = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ("config/data_platform.json", "config/data_sources.json")
    }
    if streaming:
        from commodity.market_truth.streaming import build_streaming_parquet

        # The generic transformer emits a non-admissible candidate and cannot
        # mint development or protected-boundary claims from caller input.
        # Source-owner preflight controls the final declaration before the
        # candidate is atomically published. Research admission STILL requires
        # an independent, immutable-source catalog approval in the reader.
        # Probe on the nearest existing approved ancestor first, so an
        # unsupported filesystem cannot leave newly created output parents.
        probe_parent = output_dir.parent
        while not probe_parent.exists():
            probe_parent = probe_parent.parent
        _assert_atomic_publication_supported(probe_parent)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        with _private_stage(
            output_dir.parent, prefix=".market-truth-owner-"
        ) as stage:
            candidate_dir = stage / "candidate"
            candidate = build_streaming_parquet(
                paths, payload["inputs"], candidate_dir,
                source_manifest_path=manifest_path,
                config_sha256=config_sha256,
                normalize_row=normalize_ng_databento_record,
                governance=SourceBuildAttestation(
                    dataset_scope="development_pre2023",
                    protected_confirmation_accessed=payload["protected_confirmation_accessed"],
                    source_manifest_sha256=source_manifest_sha256,
                ),
            )
            if any(key in candidate for key in
                   ("dataset_scope", "protected_confirmation_accessed")):
                raise MarketTruthError("generic transform cannot assert source authority")
            if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != source_manifest_sha256:
                raise MarketTruthError("source manifest mutated during build")
            candidate_file = candidate_dir / "manifest.json"
            if json.loads(candidate_file.read_bytes()) != candidate:
                raise MarketTruthError("generic candidate manifest changed")
            declared = {k: v for k, v in candidate.items() if k != "content_sha256"}
            if _evidence(declared) != candidate["content_sha256"]:
                raise MarketTruthError("generic candidate identity mismatch")
            declared.update({
                "dataset_scope": "development_pre2023",
                # Preflight requires literal False; never rewrite source truth.
                "protected_confirmation_accessed": payload["protected_confirmation_accessed"],
            })
            declared["content_sha256"] = _evidence(declared)
            candidate_file.write_text(
                json.dumps(declared, sort_keys=True, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )
            if output_dir.exists() or output_dir.is_symlink():
                raise MarketTruthError("refusing overwrite of existing development dataset")
            _publish_no_replace(candidate_dir, output_dir)
            return declared
    sources = {
        name: _read_checked_csv(paths[name], payload["inputs"][name]["sha256"])
        for name in SCHEMAS
    }
    for name in SCHEMAS:
        if len(sources[name]) != payload["inputs"][name]["row_count"]:
            raise MarketTruthError(
                "source-to-output audit input count mismatch: " + name
            )
    prepared = normalize_ng_databento(
        sources["definitions"],
        _adapt_bar_availability(sources["bars"]),
        _adapt_statistics_dates(sources["statistics"]),
    )
    store = build_market_truth(
        *prepared,
        source_hashes={name: payload["inputs"][name]["sha256"] for name in SCHEMAS},
        settlement_policy=databento_ng_settlement_eligible,
    )
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != source_manifest_sha256:
        raise MarketTruthError("source manifest mutated during build")
    return publish_parquet(
        store,
        output_dir,
        source_manifest_sha256=source_manifest_sha256,
        source_counts={name: len(sources[name]) for name in SCHEMAS},
        config_sha256=config_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--streaming", action="store_true",
                        help="force bounded disk-backed ingestion for parity checks")
    arguments = parser.parse_args(argv)
    try:
        output = build_from_manifest(
            arguments.source_manifest, arguments.output, streaming=arguments.streaming
        )
    except (MarketTruthError, OSError, json.JSONDecodeError) as exc:
        print("MARKET_TRUTH_BUILD_BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
