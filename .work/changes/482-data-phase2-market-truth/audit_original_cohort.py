"""Verify exact pre-2023 Databento archive bytes against independent #448 record.

Read only. Never glob or open protected 2023+ archive objects. Explicitly
iterate the 39 SHA-256-pinned, dated inputs from the 2010-2022 receipt.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from commodity.market_truth.protected_reads import protected_table_reads

CHANGE = Path(__file__).resolve().parent
CHECKOUT = CHANGE.parents[2]
PRIMARY = CHECKOUT.parents[2]
STAGE = CHECKOUT / ".work/runtime/market_truth_development"
SOURCE = PRIMARY / "data/raw/snapshots/databento/ng-full-history-v1"
ISSUE448 = CHECKOUT / (
    "research/programmes/004-v2-maximum-reproducible-one-month-return/"
    "issue448-source-pit-evidence-v1.json"
)
FAMILIES = {
    "definition": "definition",
    "ohlcv-1d": "ohlcv_1d",
    "statistics": "statistics",
}
# Established by the earlier independently recorded full-history curated build;
# this pin is owned by reviewed code, never by the mutable input manifest.
EXPECTED_CURATED_MANIFEST_SHA256 = (
    "8a86789673c8458c5745f14b550f3c16b6e4885cac026578cb2989cbc80e5240"
)


def validate_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not re.fullmatch(
        r"GLBX-20260813-[A-Z0-9]{10}", job_id
    ):
        raise ValueError("invalid archive acquisition job ID")
    return job_id


def validate_archive_filename(filename: str, family: str) -> int:
    """Require the exact original annual download range, not just a valid year."""
    if family not in FAMILIES:
        raise ValueError("unexpected source family")
    match = re.fullmatch(
        r"glbx-mdp3-(20[0-9]{6})-(20[0-9]{6})\."
        + re.escape(family) + r"\.dbn\.zst",
        filename,
    )
    if match is None:
        raise ValueError("unexpected path, source year or file format")
    start, end = match.groups()
    year = int(start[:4])
    if not 2010 <= year <= 2022:
        raise ValueError("protected source year")
    expected_start = "20100606" if year == 2010 else f"{year}0101"
    if (start, end) != (expected_start, f"{year}1231"):
        raise ValueError("unexpected original archive date range")
    return year


def bounded_archive_path(path: Path, *, parent: Path, root: Path) -> Path:
    """Reject symlink/reparse/path retarget before opening any source bytes."""
    if not path.is_file() or path.is_symlink():
        raise ValueError("source input missing or symlinked")
    if not path.is_relative_to(root):
        raise ValueError("source path outside approved root")
    ancestors = [path.parent, *path.parent.parents]
    if root not in ancestors and path.parent != root:
        raise ValueError("source path parent outside approved root")
    for directory in ancestors:
        if directory.is_symlink():
            raise ValueError("source directory symlink prohibited")
        if directory == root:
            break
    resolved = path.resolve(strict=True)
    if resolved.parent != parent.resolve(strict=True):
        raise ValueError("source source-directory retarget detected")
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("source escaped approved pre-2023 archive")
    return path


def sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing/nonregular or symlinked source file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_checked_json(path: Path) -> tuple[dict, str]:
    """Parse and hash one bounded, guard-protected byte snapshot."""
    with protected_table_reads([path]):
        if path.is_symlink() or not path.is_file():
            raise ValueError("untrusted JSON evidence path")
        with path.open("rb") as stream:
            source = stream.read(1_048_576 + 1)
    if len(source) > 1_048_576:
        raise ValueError("oversized evidence JSON")
    try:
        decoded = json.loads(source.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid evidence JSON") from exc
    if not isinstance(decoded, dict):
        raise TypeError("JSON evidence must be an object")
    return decoded, hashlib.sha256(source).hexdigest()


def require_pinned_curated_manifest(digest: str) -> None:
    """Reject coordinated changes to a CSV and its own mutable manifest."""
    if digest != EXPECTED_CURATED_MANIFEST_SHA256:
        raise ValueError("curated manifest independently pinned hash mismatch")


def verify_curated_inputs(
    manifest: dict, stage: Path
) -> tuple[dict[str, int], dict[str, int]]:
    """Prove complete exact bytes and row counts for all decoded inputs."""
    if set(manifest.get("inputs", {})) != {"definitions", "bars", "statistics"}:
        raise ValueError("curated input source family set must be exactly three")
    csv_sizes: dict[str, int] = {}
    csv_rows: dict[str, int] = {}
    distinct_paths: set[str] = set()
    for family, declared in manifest["inputs"].items():
        rel = declared["relative_path"]
        if not re.fullmatch(r"[a-z0-9-]+[.]csv", rel):
            raise ValueError("malformed normalized input filename")
        if rel in distinct_paths:
            raise ValueError("duplicate normalized CSV source path")
        distinct_paths.add(rel)
        path = stage / rel
        with protected_table_reads([path]):
            bounded_archive_path(path, parent=stage, root=stage)
            if sha256(path) != declared["sha256"]:
                raise ValueError("curated decoded input does not match manifest")
            if type(declared["row_count"]) is not int or declared["row_count"] <= 0:
                raise ValueError("invalid declared curated row count")
            previous_limit = csv.field_size_limit()
            csv.field_size_limit(1024 * 1024)
            try:
                with path.open("r", encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream, strict=True)
                    if (
                        not reader.fieldnames
                        or len(reader.fieldnames) != len(set(reader.fieldnames))
                        or any(not field.strip() or field != field.strip() for field in reader.fieldnames)
                    ):
                        raise ValueError("missing or duplicate curated CSV header")
                    count = 0
                    for row in reader:
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError("malformed curated CSV record")
                        count += 1
            finally:
                csv.field_size_limit(previous_limit)
            if sha256(path) != declared["sha256"] or count != declared["row_count"]:
                raise ValueError("curated CSV mutated or row count mismatched")
            csv_rows[family] = count
            csv_sizes[family] = path.stat().st_size
    return csv_sizes, csv_rows


def audit() -> dict:
    receipt_path = STAGE / "raw-stage-receipt.json"
    lineage_path = STAGE / "full-source-lineage.json"
    receipt, receipt_bytes_sha = read_checked_json(receipt_path)
    lineage, _ = read_checked_json(lineage_path)
    old, _ = read_checked_json(ISSUE448)
    acquisition_path = SOURCE / "acquisition-state.json"
    acquisition, _ = read_checked_json(acquisition_path)
    if acquisition.get("request", {}).get("symbol") != "NG.FUT":
        raise ValueError("unexpected original acquisition cohort")
    job_ids = {
        family: validate_job_id(acquisition["jobs"][family]["id"])
        for family in FAMILIES
    }
    if receipt_bytes_sha != lineage["raw_copy_receipt_sha256"]:
        raise ValueError("source receipt changed after lineage validation")
    objects = receipt["raw_objects"]
    if (
        receipt.get("schema_version") != 1
        or receipt.get("dataset") != "GLBX.MDP3"
        or receipt.get("product_code") != "NG"
        or receipt.get("evidence_class") != "development"
        or receipt.get("protected_confirmation_accessed") is not False
        or receipt.get("year_range") != [2010, 2022]
        or len(objects) != 39
    ):
        raise ValueError("source receipt cohort or protected scope invalid")
    seen: set[tuple[int, str]] = set()
    sums: Counter[str] = Counter()
    for entry in objects:
        family = entry["family"]
        filename = entry["filename"]
        year = validate_archive_filename(filename, family)
        if (year, family) in seen:
            raise ValueError("duplicate year/family in manifest")
        seen.add((year, family))
        previous_sha = old["databento"]["years"][str(year)]["hashes"][
            FAMILIES[family]
        ]
        if entry["sha256"] != previous_sha:
            raise ValueError("historical #448 versus new receipt hash mismatch")
        origin_parent = SOURCE / family / job_ids[family]
        stage_parent = STAGE / "raw_checked" / family
        for location, parent, root in (
            (origin_parent / filename, origin_parent, SOURCE),
            (stage_parent / filename, stage_parent, STAGE / "raw_checked"),
        ):
            # Retained Windows file and ancestor-directory read handles stop
            # pathname replacement throughout identity, size and digest reads.
            with protected_table_reads([location]):
                bounded_archive_path(location, parent=parent, root=root)
                if location.stat().st_size != entry["bytes"]:
                    raise ValueError("archive size mismatch")
                if sha256(location) != previous_sha:
                    raise ValueError("archive identity mismatch")
        sums[family] += entry["bytes"]
    if seen != {(year, family) for year in range(2010, 2023)
               for family in FAMILIES}:
        raise ValueError("missing year/family")
    if sum(sums.values()) != receipt["bytes_total"] or sum(sums.values()) != 1211127256:
        raise ValueError("source receipt byte total mismatch")
    source_manifest = STAGE / "source-manifest-full-2010-2022-curated.json"
    if source_manifest.is_symlink() or not source_manifest.is_file():
        raise ValueError("curated input manifest missing or symlinked")
    manifest, manifest_sha256 = read_checked_json(source_manifest)
    require_pinned_curated_manifest(manifest_sha256)
    if manifest.get("protected_confirmation_accessed") is not False:
        raise ValueError("curated output source crosses protected scope")
    csv_sizes, csv_rows = verify_curated_inputs(manifest, STAGE)
    return {
        "status": "PASS_SOURCE_BYTES_NOT_INDEPENDENT_REFERENCE_DATES",
        "original_archive_files_verified": len(seen),
        "staged_archive_files_verified": len(seen),
        "archived_bytes_per_copy": sum(sums.values()),
        "years": [2010, 2022],
        "independent_prior_archive_hash_reference": str(ISSUE448.relative_to(CHECKOUT)),
        "original_archive_cohort_receipt_sha256": receipt_bytes_sha,
        "normalized_curated_inputs_sha256_verified": len(csv_sizes),
        "normalized_input_bytes": csv_sizes,
        "normalized_input_rows": csv_rows,
        "normalized_input_manifest_sha256": manifest_sha256,
        "protected_2023_plus_accessed": False,
        "independent_historical_trading_dates_verified": 0,
        "source_semantic_fitness_approved": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
