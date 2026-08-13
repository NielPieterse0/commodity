import json
from pathlib import Path

import pytest

from commodity.snapshots import SnapshotIntegrityError, SnapshotWriter, verify_snapshot


def test_snapshot_writer_is_immutable_and_verifiable(tmp_path: Path) -> None:
    writer = SnapshotWriter(tmp_path, "eia", "snap")
    artifact = writer.write_bytes("NG.zip", b"stable-source-bytes")
    manifest = writer.finalize({"source_id": "eia_bulk_ng", "retrieved_at": "2026-08-13T08:00:00Z"})
    assert artifact.read_bytes() == b"stable-source-bytes"
    assert verify_snapshot(manifest)["artifact_count"] == 1
    with pytest.raises(FileExistsError):
        writer.finalize({"source_id": "other"})


def test_snapshot_detects_tampering(tmp_path: Path) -> None:
    writer = SnapshotWriter(tmp_path, "eia", "snap")
    artifact = writer.write_bytes("data.csv", b"a,b\n1,2\n")
    manifest = writer.finalize({"source_id": "eia"})
    artifact.write_bytes(b"tampered")
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(manifest)


def test_snapshot_manifest_does_not_require_or_store_credentials(tmp_path: Path) -> None:
    writer = SnapshotWriter(tmp_path, "eia", "snap")
    writer.write_bytes("data.csv", b"x\n1\n")
    manifest = writer.finalize({"source_id": "eia", "query": {"route": "natural-gas/prod"}})
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert "api_key" not in json.dumps(payload).lower()


def test_snapshot_manifest_rejects_secret_bearing_metadata(tmp_path: Path) -> None:
    writer = SnapshotWriter(tmp_path, "eia", "snap")
    writer.write_bytes("data.csv", b"x\n1\n")
    with pytest.raises(SnapshotIntegrityError, match="Secret-bearing"):
        writer.finalize({"query": {"api_key": "must-not-be-written"}})
