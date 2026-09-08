from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

SNAPSHOT_ID = "bhlr-2025-real-time-forecasting"
SOURCE_ZIP = "Forecasting_Natural_Gas_Prices_in_Real_Time_(replication_data)_resouces_1788880431.2305923.zip"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def zip_members(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            data = archive.read(member)
            out.append({"path": member.filename, "bytes": len(data), "sha256": sha256_bytes(data)})
    return out


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    original = root / "original"
    resources = root / "resources"

    originals = [
        original / SOURCE_ZIP,
        original / "BHLR_real-time_database.xlsx",
        original / "BHLR_online_appendix.pdf",
    ]
    extracted = sorted(path for path in resources.iterdir() if path.is_file())

    outer_members = zip_members(original / SOURCE_ZIP)
    nested = {
        "schema_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "archives": [
            {
                **file_record(root, resources / "bhlr_codes.zip"),
                "member_count": len(zip_members(resources / "bhlr_codes.zip")),
                "members": zip_members(resources / "bhlr_codes.zip"),
            },
            {
                **file_record(root, resources / "bhlr_nowcasts.zip"),
                "member_count": len(zip_members(resources / "bhlr_nowcasts.zip")),
                "members": zip_members(resources / "bhlr_nowcasts.zip"),
            },
        ],
    }
    nested_path = root / "nested-archive-members.json"
    nested_path.write_text(json.dumps(nested, indent=2) + "\n", encoding="utf-8")

    standalone_db = file_record(root, original / "BHLR_real-time_database.xlsx")
    archive_db = file_record(root, resources / "bhlr_real-time_database.xlsx")
    citation = (resources / "citation.txt").read_text(encoding="utf-8").strip()
    manifest = {
        "schema_version": 1,
        "snapshot_id": SNAPSHOT_ID,
        "provider": "journal_data_archive",
        "source_id": "LIT-BHLR-RTDB",
        "source_doi": "10.15456/jae.2025266.1900967125",
        "source_urls": [
            "https://doi.org/10.15456/jae.2025266.1900967125",
            "https://sites.google.com/site/cjsbaumeister/research",
        ],
        "source_title": "Forecasting Natural Gas Prices in Real Time (replication data)",
        "source_version": "1.0",
        "source_citation": citation,
        "dataset_license": "CC BY 4.0",
        "license_basis": "Commodity issue #336 source authority",
        "acquisition_mode": "operator_supplied_manual_download",
        "acquired_on": "2026-09-08",
        "linked_research_issue": 327,
        "import_issue": 336,
        "original_artifacts": [file_record(root, path) for path in originals],
        "outer_archive_members": outer_members,
        "extracted_artifacts": [file_record(root, path) for path in extracted],
        "nested_archive_manifest": file_record(root, nested_path),
        "database_identity": {
            "standalone": standalone_db,
            "archive_copy": archive_db,
            "byte_identical": standalone_db["bytes"] == archive_db["bytes"]
            and standalone_db["sha256"] == archive_db["sha256"],
        },
        "verification": {
            "outer_archive_members_match_extracted_bytes": all(
                next(
                    record for record in manifest_records(extracted, root)
                    if record["path"] == member["path"]
                )["sha256"] == member["sha256"]
                for member in outer_members
            ),
            "standalone_database_matches_archive_copy": standalone_db["sha256"] == archive_db["sha256"],
            "sealed_confirmation_data_touched": False,
            "model_scoring_performed": False,
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def manifest_records(paths: list[Path], root: Path) -> list[dict[str, object]]:
    return [file_record(root, path) for path in paths]


if __name__ == "__main__":
    main()
