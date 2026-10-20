"""Credential-free B2 archive closeout tests: no external network or uploads."""
from __future__ import annotations

import hashlib
import io
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import backblaze_b2_archive_apply as uploader
import pytest
from botocore.exceptions import ClientError


def _client(payload: bytes = b"phase2") -> Mock:
    client = Mock()
    client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled",
            "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 365}},
        },
    }
    client.get_object_retention.return_value = {
        "Retention": {
            "Mode": "COMPLIANCE",
            "RetainUntilDate": datetime.now(UTC) + timedelta(days=365),
        },
    }
    client.get_object.return_value = {
        "VersionId": "v1", "Body": io.BytesIO(payload),
    }
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "absent"}}, "HeadObject"
    )
    client.put_object.return_value = {"VersionId": "v1"}
    return client


def _obj(tmp_path: Path, payload: bytes = b"phase2") -> dict:
    path = tmp_path / "artifact.parquet"
    path.write_bytes(payload)
    return {"local_path": str(path), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "key": "phase2/pre2023/final/a/artifact.parquet"}


def _checkpoint():
    return {"schema_version": 1, "issue": 482, "plan_sha256": "expected",
            "entries": {}, "research_admission": False}


def test_apply_preserves_version_and_verifies_remote_bytes(monkeypatch, tmp_path):
    client = _client()
    obj = _obj(tmp_path)
    monkeypatch.setattr(uploader, "_write_checkpoint", lambda data: None)
    monkeypatch.setattr(uploader, "protected_table_reads", lambda _: nullcontext())
    result = uploader.apply_archive(
        client=client, bucket="commodity-phase2-archive",
        plan={"objects": [obj]}, verified_free_egress_bytes=100, verified_free_remaining_bytes=100,
        checkpoint=_checkpoint())
    assert result["verified_versions"] == 1
    assert result["owner_approval"] is False
    assert result["remote_delete_refusal"] == "not_yet_independently_proven"
    client.put_object.assert_called_once()
    args = client.put_object.call_args.kwargs
    assert args["Metadata"] == {"sha256": obj["sha256"]}
    client.get_object.assert_called_once()


def test_capacity_gate_blocks_all_uploads(monkeypatch, tmp_path):
    client = _client()
    obj = _obj(tmp_path)
    monkeypatch.setattr(uploader, "_write_checkpoint", lambda data: None)
    with pytest.raises(ValueError, match="free_capacity_not_sufficient_or_unverified"):
        uploader.apply_archive(
            client=client, bucket="test", plan={"objects": [obj]},
            verified_free_egress_bytes=100, verified_free_remaining_bytes=obj["bytes"] - 1,
            checkpoint=_checkpoint())
    client.put_object.assert_not_called()


def test_existing_remote_key_requires_reconciliation(monkeypatch, tmp_path):
    client = _client()
    client.head_object.side_effect = None
    obj = _obj(tmp_path)
    monkeypatch.setattr(uploader, "_write_checkpoint", lambda data: None)
    with pytest.raises(ValueError, match="remote_object_key_already_exists"):
        uploader.apply_archive(
            client=client, bucket="test", plan={"objects": [obj]},
            verified_free_egress_bytes=100, verified_free_remaining_bytes=100, checkpoint=_checkpoint())
    client.put_object.assert_not_called()


def test_retention_downgrade_refused(monkeypatch, tmp_path):
    client = _client()
    obj = _obj(tmp_path)
    client.get_object_retention.return_value["Retention"]["RetainUntilDate"] = (
        datetime.now(UTC) + timedelta(days=180))
    checkpoint = _checkpoint()
    checkpoint["entries"][obj["key"]] = {
        "sha256": obj["sha256"], "bytes": obj["bytes"],
        "version_id": "v1", "status": "awaiting_readback"}
    monkeypatch.setattr(uploader, "_write_checkpoint", lambda data: None)
    with pytest.raises(ValueError, match="version_retention_not_365_day_compliance"):
        uploader.apply_archive(
            client=client, bucket="test", plan={"objects": [obj]},
            verified_free_egress_bytes=100, verified_free_remaining_bytes=0, checkpoint=checkpoint)
    client.put_object.assert_not_called()


def test_resume_rechecks_exact_existing_version_without_reupload(monkeypatch, tmp_path):
    client = _client()
    obj = _obj(tmp_path)
    checkpoint = _checkpoint()
    checkpoint["entries"][obj["key"]] = {
        "sha256": obj["sha256"], "bytes": obj["bytes"],
        "version_id": "v1", "status": "awaiting_readback"}
    monkeypatch.setattr(uploader, "_write_checkpoint", lambda data: None)
    result = uploader.apply_archive(
        client=client, bucket="test", plan={"objects": [obj]},
        verified_free_egress_bytes=100, verified_free_remaining_bytes=0, checkpoint=checkpoint)
    assert result["verified_versions"] == 1
    client.put_object.assert_not_called()
    assert checkpoint["entries"][obj["key"]]["status"] == (
        "remote_retention_and_sha256_verified"
    )


def test_mismatched_checkpoint_identity_denied(monkeypatch, tmp_path):
    client = _client()
    obj = _obj(tmp_path)
    checkpoint = _checkpoint()
    checkpoint["entries"][obj["key"]] = {
        "sha256": "f" * 64, "bytes": obj["bytes"],
        "version_id": "v1", "status": "verified"}
    monkeypatch.setattr(uploader, "_write_checkpoint", lambda data: None)
    with pytest.raises(ValueError, match="checkpoint_entry_identity_changed"):
        uploader.apply_archive(client=client, bucket="test", plan={"objects": [obj]},
                               verified_free_egress_bytes=100, verified_free_remaining_bytes=0, checkpoint=checkpoint)
    client.put_object.assert_not_called()

def test_checkpoint_atomically_records_exact_version_without_secrets(monkeypatch, tmp_path):
    target = tmp_path / "checkpoint.json"
    monkeypatch.setattr(uploader, "STAGE", tmp_path)
    monkeypatch.setattr(uploader, "RECEIPT_PATH", target)
    checkpoint = _checkpoint()
    checkpoint["entries"]["phase2/pre2023/source/x"] = {
        "version_id": "v1", "sha256": "a" * 64, "bytes": 1}
    uploader._write_checkpoint(checkpoint)
    assert uploader.load_checkpoint("expected") == checkpoint
    assert len(list(tmp_path.iterdir())) == 1
    with pytest.raises(ValueError, match="archive_checkpoint_mismatched"):
        uploader.load_checkpoint("different")


def test_checkpoint_rejects_symlink(monkeypatch, tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "checkpoint.json"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation denied")
    monkeypatch.setattr(uploader, "STAGE", tmp_path)
    monkeypatch.setattr(uploader, "RECEIPT_PATH", link)
    with pytest.raises(ValueError, match="unsafe_archive_runtime_directory"):
        uploader.load_checkpoint("expected")

def test_egress_budget_blocks_downloads_and_uploads(monkeypatch, tmp_path):
    client = _client()
    obj = _obj(tmp_path)
    monkeypatch.setattr(uploader, "_write_checkpoint", lambda data: None)
    with pytest.raises(ValueError, match="free_egress_not_sufficient_or_unverified"):
        uploader.apply_archive(
            client=client, bucket="test", plan={"objects": [obj]},
            verified_free_remaining_bytes=100, verified_free_egress_bytes=obj["bytes"] - 1,
            checkpoint=_checkpoint())
    client.put_object.assert_not_called()
    client.get_object.assert_not_called()
