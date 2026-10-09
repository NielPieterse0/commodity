import io
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
MANIFEST_SCHEMA = ROOT / "contracts" / "raw_artifact_manifest.schema.json"


def _schema() -> dict:
    return json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(self, path: str, bucket: str, key: str, ExtraArgs: dict | None = None) -> None:
        self.objects[(bucket, key)] = Path(path).read_bytes()

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def download_file(self, bucket: str, key: str, path: str) -> None:
        Path(path).write_bytes(self.objects[(bucket, key)])


def test_raw_artifact_entry_is_sha_bound_and_schema_valid(tmp_path: Path) -> None:
    from commodity.raw_archive import build_local_artifact_entry

    raw = tmp_path / "source.csv"
    raw.write_bytes(b"date,value\n2022-01-01,3.5\n")
    entry = build_local_artifact_entry(
        raw,
        source_id="example_source",
        provider="example",
        retrieved_at="2026-10-07T09:00:00Z",
        local_relative_path="data/raw/source.csv",
        licensing_class="private_research",
    )
    manifest = {
        "schema_version": 1,
        "manifest_id": "test",
        "authority": "raw_bytes_identity_and_durability_only",
        "artifacts": [entry],
    }
    Draft202012Validator(_schema()).validate(manifest)
    assert len(entry["sha256"]) == 64
    assert entry["raw_artifact_id"].endswith(entry["sha256"])
    assert entry["byte_size"] == raw.stat().st_size


def test_raw_artifact_hash_mismatch_and_identity_replacement_fail_closed(tmp_path: Path) -> None:
    from commodity.raw_archive import (
        assert_manifest_immutable,
        build_local_artifact_entry,
        verify_artifact_bytes,
    )

    first = tmp_path / "first.bin"
    first.write_bytes(b"original")
    entry = build_local_artifact_entry(
        first, source_id="source", provider="provider",
        retrieved_at="2026-10-07T09:00:00Z",
        local_relative_path="data/raw/first.bin", licensing_class="private_research",
    )
    changed = tmp_path / "changed.bin"
    changed.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_artifact_bytes(entry, changed)

    candidate = dict(entry)
    candidate["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="immutable"):
        assert_manifest_immutable(entry, candidate)


def test_offsite_and_restore_verification_preserve_hash_identity(tmp_path: Path) -> None:
    from commodity.raw_archive import (
        build_local_artifact_entry,
        record_offsite_verification,
        verify_restore,
    )

    source = tmp_path / "source.bin"
    source.write_bytes(b"durable-evidence")
    entry = build_local_artifact_entry(
        source, source_id="source", provider="provider",
        retrieved_at="2026-10-07T09:00:00Z",
        local_relative_path="data/raw/source.bin", licensing_class="private_research",
    )
    durable = record_offsite_verification(
        entry, archive_provider="google_drive_existing_capacity",
        remote_object_id="drive-file-id", portable_uri="gdrive://drive-file-id",
        verified_sha256=entry["sha256"], verified_at="2026-10-07T09:10:00Z",
    )
    restored = tmp_path / "restored.bin"
    restored.write_bytes(source.read_bytes())
    verified = verify_restore(durable, restored, verified_at="2026-10-07T09:20:00Z")
    assert verified["durability_status"] == "durably_acquired"
    assert verified["restore"]["status"] == "verified"


def test_protected_and_development_archive_namespaces_cannot_be_shared() -> None:
    from commodity.raw_archive import assert_archive_namespace_separation

    assert_archive_namespace_separation(
        development_namespace="commodity-raw-development",
        protected_namespace="commodity-raw-protected",
        development_credential_ref="COMMODITY_RAW_DEV_CREDENTIAL",
        protected_credential_ref="COMMODITY_RAW_PROTECTED_CREDENTIAL",
    )
    with pytest.raises(ValueError, match="namespace"):
        assert_archive_namespace_separation(
            development_namespace="commodity-raw",
            protected_namespace="commodity-raw",
            development_credential_ref="DEV",
            protected_credential_ref="PROTECTED",
        )
    with pytest.raises(ValueError, match="credential"):
        assert_archive_namespace_separation(
            development_namespace="commodity-raw-development",
            protected_namespace="commodity-raw-protected",
            development_credential_ref="SHARED",
            protected_credential_ref="SHARED",
        )


def test_s3_compatible_archive_upload_rehash_and_restore(tmp_path: Path) -> None:
    from commodity.raw_archive import (
        build_local_artifact_entry,
        restore_s3_artifact,
        s3_object_key,
        upload_and_verify_s3,
    )

    raw = tmp_path / "source.bin"
    raw.write_bytes(b"off-machine-development-evidence")
    entry = build_local_artifact_entry(
        raw,
        source_id="example/source",
        provider="example",
        retrieved_at="2026-10-07T09:00:00Z",
        local_relative_path="data/raw/source.bin",
        licensing_class="private_research",
    )
    client = _FakeS3()
    durable = upload_and_verify_s3(
        entry,
        raw,
        client=client,
        bucket="commodity-dev",
        archive_provider="s3_test",
        verified_at="2026-10-07T09:10:00Z",
    )
    key = s3_object_key(entry)
    assert durable["durability_status"] == "durably_acquired"
    assert durable["offsite"]["portable_uri"] == f"s3://commodity-dev/{key}"

    restored_path = tmp_path / "restore" / "source.bin"
    restored = restore_s3_artifact(
        durable,
        restored_path,
        client=client,
        bucket="commodity-dev",
        key=key,
        verified_at="2026-10-07T09:20:00Z",
    )
    assert restored["restore"]["status"] == "verified"
    assert restored_path.read_bytes() == raw.read_bytes()


def test_development_s3_settings_accept_supabase_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    from commodity.raw_archive import development_s3_settings_from_env

    monkeypatch.setenv("COMMODITY_RAW_DEV_S3_BUCKET", "commodity-raw-development")
    monkeypatch.setenv("SUPABASE_ENDPOINT", "https://example.storage.supabase.co/storage/v1/s3")
    monkeypatch.setenv("SUPABASE_REGION", "eu-central-1")
    monkeypatch.setenv("SUPABASE_ACCESS_KEY_ID", "test-access-id")
    monkeypatch.setenv("SUPABASE_ACCESS_KEY", "test-secret")
    settings = development_s3_settings_from_env()

    assert settings["bucket"] == "commodity-raw-development"
    assert settings["provider"] == "supabase_storage_s3"
    assert settings["endpoint_url"] == "https://example.storage.supabase.co/storage/v1/s3"
    assert settings["region"] == "eu-central-1"
    assert settings["access_key_id"] == "test-access-id"
    assert settings["secret_access_key"] == "test-secret"


def test_development_s3_adapter_fails_closed_on_remote_corruption_and_protected_data(
    tmp_path: Path,
) -> None:
    from commodity.raw_archive import (
        build_local_artifact_entry,
        s3_object_key,
        upload_and_verify_s3,
    )

    raw = tmp_path / "source.bin"
    raw.write_bytes(b"expected")
    entry = build_local_artifact_entry(
        raw,
        source_id="source",
        provider="provider",
        retrieved_at="2026-10-07T09:00:00Z",
        local_relative_path="data/raw/source.bin",
        licensing_class="private_research",
    )
    corrupt = _FakeS3()

    def corrupt_upload(path: str, bucket: str, key: str, ExtraArgs: dict | None = None) -> None:
        corrupt.objects[(bucket, key)] = b"corrupted"

    corrupt.upload_file = corrupt_upload  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="offsite"):
        upload_and_verify_s3(
            entry,
            raw,
            client=corrupt,
            bucket="commodity-dev",
            archive_provider="s3_test",
            verified_at="2026-10-07T09:10:00Z",
        )

    protected = dict(entry)
    protected["evidence_class"] = "protected_confirmation"
    with pytest.raises(ValueError, match="refuses protected"):
        s3_object_key(protected)
