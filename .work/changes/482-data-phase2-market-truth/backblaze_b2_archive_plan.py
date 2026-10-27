"""Construct a pinned, pre-2023 Backblaze B2 archive manifest without network access.

The output lives in ignored local runtime state, not in the approval catalog.
Original source hashes derive from independent #448 source evidence and the
exact 39-file receipt; final hashes derive from the frozen real dataset.
Planning never uploads, admits, signs, or enumerates protected 2023+ inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from audit_original_cohort import (
    EXPECTED_CURATED_MANIFEST_SHA256,
    FAMILIES,
    ISSUE448,
    SOURCE,
    STAGE,
    bounded_archive_path,
    read_checked_json,
    validate_archive_filename,
    validate_job_id,
)

RAW_RECEIPT_SHA256 = "5b4ce1596964b81010fe06a5adcc7cb820ec642ed4ae618708e271e2ab7aeda8"
DATASET_SHA256 = "943780ea8eaa7315157385c687e3939777089420c186fd7d8d4b7d781a1f5d94"
DATASET_DIR = STAGE / "market-truth-full-2010-2022-refactor-v3"
PLAN_PATH = STAGE / "backblaze-b2-archive-plan.json"
SHA_CHARS = set("0123456789abcdef")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(path: Path, key: str, sha256: str, size: int, kind: str) -> dict:
    if not key.startswith("phase2/pre2023/") or ".." in key.split("/"):
        raise ValueError("out_of_scope_object_key")
    if len(sha256) != 64 or set(sha256) - SHA_CHARS:
        raise ValueError("invalid_sha256_identity")
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise ValueError("missing_or_changed_archive_input")
    return {"kind": kind, "local_path": str(path), "key": key,
            "sha256": sha256, "bytes": size}


def build_plan() -> dict:
    receipt, receipt_sha = read_checked_json(STAGE / "raw-stage-receipt.json")
    if receipt_sha != RAW_RECEIPT_SHA256 or receipt.get("protected_confirmation_accessed") is not False:
        raise ValueError("raw_archive_receipt_not_pinned")
    acquisition, _ = read_checked_json(SOURCE / "acquisition-state.json")
    old, _ = read_checked_json(ISSUE448)
    if acquisition.get("request", {}).get("symbol") != "NG.FUT":
        raise ValueError("incorrect_market_source")
    job_ids = {family: validate_job_id(acquisition["jobs"][family]["id"])
               for family in FAMILIES}
    objects = receipt["raw_objects"]
    if len(objects) != 39 or receipt.get("year_range") != [2010, 2022]:
        raise ValueError("incorrect_original_cohort")
    seen = set()
    entries = []
    for item in objects:
        family = item["family"]
        year = validate_archive_filename(item["filename"], family)
        if (year, family) in seen:
            raise ValueError("duplicate_original_archive")
        seen.add((year, family))
        expected = old["databento"]["years"][str(year)]["hashes"][FAMILIES[family]]
        if item["sha256"] != expected:
            raise ValueError("independent_archive_digest_disagrees")
        parent = SOURCE / family / job_ids[family]
        path = bounded_archive_path(parent / item["filename"], parent=parent, root=SOURCE)
        entries.append(_entry(path, f"phase2/pre2023/source/{family}/{item['filename']}",
                              expected, item["bytes"], "original_source"))
    if seen != {(y, f) for y in range(2010, 2023) for f in FAMILIES}:
        raise ValueError("original_cohort_incomplete")
    if sum(e["bytes"] for e in entries) != 1211127256:
        raise ValueError("original_cohort_bytes_changed")

    source_manifest, manifest_sha = read_checked_json(
        STAGE / "source-manifest-full-2010-2022-curated.json")
    if (manifest_sha != EXPECTED_CURATED_MANIFEST_SHA256
            or source_manifest.get("protected_confirmation_accessed") is not False):
        raise ValueError("source_manifest_untrusted")
    final_manifest_path = DATASET_DIR / "manifest.json"
    final_manifest, _ = read_checked_json(final_manifest_path)
    if (final_manifest.get("content_sha256") != DATASET_SHA256
            or final_manifest.get("dataset_scope") != "development_pre2023"
            or final_manifest.get("protected_confirmation_accessed") is not False
            or final_manifest.get("source_manifest_sha256") != manifest_sha
            or set(final_manifest.get("tables", {})) != {"bars", "definitions", "statistics"}):
        raise ValueError("final_dataset_identity_disagrees")
    for name, item in sorted(final_manifest["tables"].items()):
        path = bounded_archive_path(DATASET_DIR / item["relative_path"],
                                    parent=DATASET_DIR, root=DATASET_DIR)
        if item["relative_path"] != name + ".parquet":
            raise ValueError("unexpected_final_table_path")
        entries.append(_entry(
            path, f"phase2/pre2023/final/{DATASET_SHA256}/{name}.parquet",
            item["sha256"], item["bytes"], "final_parquet"))
    entries.append(_entry(final_manifest_path,
                          f"phase2/pre2023/final/{DATASET_SHA256}/manifest.json",
                          _sha256(final_manifest_path), final_manifest_path.stat().st_size,
                          "final_manifest"))
    keys = [e["key"] for e in entries]
    if len(entries) != 43 or len(keys) != len(set(keys)):
        raise ValueError("archive_plan_duplicates_or_missing")
    return {"schema_version": 1, "issue": 482, "status": "planned_not_remote_verified",
            "dataset_content_sha256": DATASET_SHA256,
            "source_receipt_sha256": RAW_RECEIPT_SHA256, "protected_2023plus_read": False,
            "object_count": len(entries), "total_bytes": sum(x["bytes"] for x in entries),
            "object_lock_required": {"mode": "COMPLIANCE", "days": 365},
            "remote_versions_verified": 0, "objects": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PLAN_PATH)
    args = parser.parse_args()
    if args.output != PLAN_PATH:
        raise SystemExit("custom_output_disallowed_outside_ignored_phase2_runtime")
    plan = build_plan()
    document = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()
    if STAGE.is_symlink() or not STAGE.is_dir():
        raise ValueError("unsafe_archive_runtime_directory")
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=STAGE, prefix="b2-plan-", suffix=".pending", delete=False,
    ) as stream:
        stream.write(document)
        pending = Path(stream.name)
    os.replace(pending, PLAN_PATH)
    print(json.dumps({"status": plan["status"], "objects": plan["object_count"],
                      "bytes": plan["total_bytes"], "plan_sha256": hashlib.sha256(document).hexdigest(),
                      "remote_uploads": 0, "owner_approval": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
