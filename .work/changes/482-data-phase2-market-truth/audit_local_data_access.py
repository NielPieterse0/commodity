"""Read-only local access preflight for owner-retained Phase 2 original/final data.

Reuse the pinned local source and Parquet identity planner. No provider calls,
cloud writes, source rebuilds, protected 2023+ enumeration or extra copies.
"""
from __future__ import annotations

import json
from pathlib import Path

from backblaze_b2_archive_plan import build_plan


def audit_local_access() -> dict:
    plan = build_plan()
    families = {"original_source": 0, "final_parquet": 0, "final_manifest": 0}
    for entry in plan["objects"]:
        candidate = Path(entry["local_path"])
        if (not candidate.is_file() or candidate.is_symlink()
                or candidate.stat().st_size != entry["bytes"]):
            raise ValueError("local_dataset_reference_unavailable")
        families[entry["kind"]] += 1
    if families != {"original_source": 39, "final_parquet": 3, "final_manifest": 1}:
        raise ValueError("local_source_or_final_incomplete")
    return {"status": "LOCAL_PATHS_SIZES_AVAILABLE_HASH_PINS_PREVIOUSLY_VERIFIED",
            "source_files": 39, "processed_tables": 3, "manifest_files": 1,
            "bytes": plan["total_bytes"], "external_backups_required": False,
            "hashes_recomputed": False, "protected_2023plus_accessed": False}


if __name__ == "__main__":
    print(json.dumps(audit_local_access(), sort_keys=True))
