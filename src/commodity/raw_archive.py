from __future__ import annotations

import hashlib
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

_SAFE_KEY_PART = re.compile(r"[^A-Za-z0-9._-]+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_local_artifact_entry(
    path: Path,
    *,
    source_id: str,
    provider: str,
    retrieved_at: str,
    local_relative_path: str,
    licensing_class: str,
    evidence_class: str = "development",
    source_vintage_id: str | None = None,
    source_revision_id: str | None = None,
    acquisition_recipe_id: str | None = None,
    source_uri: str | None = None,
    media_type: str | None = None,
    compression: str | None = None,
    cloud_replication_allowed: bool = True,
) -> dict[str, Any]:
    if evidence_class not in {"development", "protected_confirmation"}:
        raise ValueError(f"unsupported evidence_class: {evidence_class}")
    digest = sha256_file(path)
    status = "local_only" if cloud_replication_allowed else "replication_prohibited_by_license"
    verification = "not_uploaded" if cloud_replication_allowed else "replication_prohibited"
    return {
        "raw_artifact_id": f"raw-sha256:{digest}",
        "source_id": source_id,
        "provider": provider,
        "source_vintage_id": source_vintage_id,
        "source_revision_id": source_revision_id,
        "acquisition_recipe_id": acquisition_recipe_id,
        "source_uri": source_uri,
        "retrieved_at": retrieved_at,
        "original_filename": path.name,
        "media_type": media_type,
        "compression": compression,
        "byte_size": path.stat().st_size,
        "sha256": digest,
        "local": {"relative_path": local_relative_path, "hash_verified": True},
        "licensing_class": licensing_class,
        "cloud_replication_allowed": cloud_replication_allowed,
        "evidence_class": evidence_class,
        "durability_status": status,
        "offsite": {
            "archive_provider": None,
            "remote_object_id": None,
            "portable_uri": None,
            "uploaded_at": None,
            "verified_sha256": None,
            "verified_at": None,
            "verification_status": verification,
        },
        "restore": {"status": "not_tested", "verified_at": None, "verified_sha256": None},
        "notes": None,
    }


def verify_artifact_bytes(entry: dict[str, Any], path: Path) -> str:
    actual = sha256_file(path)
    expected = str(entry["sha256"])
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: expected {expected}, got {actual}")
    if path.stat().st_size != int(entry["byte_size"]):
        raise ValueError("byte-size mismatch for raw artifact")
    return actual


def assert_manifest_immutable(existing: dict[str, Any], candidate: dict[str, Any]) -> None:
    if existing.get("raw_artifact_id") != candidate.get("raw_artifact_id"):
        raise ValueError("raw artifact immutable identity changed")
    if existing.get("sha256") != candidate.get("sha256"):
        raise ValueError("raw artifact immutable SHA-256 changed")
    for key in ("source_id", "provider", "source_vintage_id", "source_revision_id"):
        if existing.get(key) != candidate.get(key):
            raise ValueError(f"raw artifact immutable source identity changed: {key}")


def record_offsite_verification(
    entry: dict[str, Any],
    *,
    archive_provider: str,
    remote_object_id: str,
    portable_uri: str,
    verified_sha256: str,
    verified_at: str,
    uploaded_at: str | None = None,
) -> dict[str, Any]:
    if not bool(entry.get("cloud_replication_allowed", True)):
        raise ValueError("cloud replication is prohibited by the artifact license")
    if verified_sha256 != entry["sha256"]:
        raise ValueError("offsite SHA-256 verification does not match local identity")
    updated = deepcopy(entry)
    updated["offsite"] = {
        "archive_provider": archive_provider,
        "remote_object_id": remote_object_id,
        "portable_uri": portable_uri,
        "uploaded_at": uploaded_at or verified_at,
        "verified_sha256": verified_sha256,
        "verified_at": verified_at,
        "verification_status": "verified",
    }
    updated["durability_status"] = "durably_acquired"
    return updated


def verify_restore(
    entry: dict[str, Any],
    restored_path: Path,
    *,
    verified_at: str,
) -> dict[str, Any]:
    actual = verify_artifact_bytes(entry, restored_path)
    updated = deepcopy(entry)
    updated["restore"] = {
        "status": "verified",
        "verified_at": verified_at,
        "verified_sha256": actual,
    }
    return updated


def s3_object_key(entry: dict[str, Any], *, prefix: str = "raw") -> str:
    if entry.get("evidence_class") != "development":
        raise ValueError("development archive adapter refuses protected-confirmation artifacts")
    source = _SAFE_KEY_PART.sub("_", str(entry["source_id"])).strip("._") or "source"
    filename = _SAFE_KEY_PART.sub("_", Path(str(entry["original_filename"])).name)
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{source}/{entry['sha256']}/{filename}"


def development_s3_settings_from_env() -> dict[str, str | None]:
    bucket = os.environ.get("COMMODITY_RAW_DEV_S3_BUCKET")
    if not bucket:
        raise RuntimeError("COMMODITY_RAW_DEV_S3_BUCKET is required for the development archive")
    endpoint_url = os.environ.get("COMMODITY_RAW_DEV_S3_ENDPOINT_URL") or os.environ.get(
        "SUPABASE_ENDPOINT"
    )
    region = os.environ.get("COMMODITY_RAW_DEV_S3_REGION") or os.environ.get("SUPABASE_REGION")
    access_key_id = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get(
        "SUPABASE_ACCESS_KEY_ID"
    )
    secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get(
        "SUPABASE_ACCESS_KEY"
    )
    provider = os.environ.get("COMMODITY_RAW_DEV_S3_PROVIDER")
    if not provider and endpoint_url and "supabase.co" in endpoint_url:
        provider = "supabase_storage_s3"
    return {
        "bucket": bucket,
        "provider": provider or "s3_compatible",
        "endpoint_url": endpoint_url,
        "region": region,
        "prefix": os.environ.get("COMMODITY_RAW_DEV_S3_PREFIX", "raw"),
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
    }


def build_s3_client(
    *,
    endpoint_url: str | None = None,
    region: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
) -> Any:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("boto3 is required for the S3-compatible raw archive adapter") from exc

    kwargs: dict[str, Any] = {
        "endpoint_url": endpoint_url,
        "region_name": region,
        "config": Config(s3={"addressing_style": "path"}),
    }
    if access_key_id:
        kwargs["aws_access_key_id"] = access_key_id
    if secret_access_key:
        kwargs["aws_secret_access_key"] = secret_access_key
    return boto3.client("s3", **kwargs)


def verify_s3_remote_bytes(
    client: Any,
    *,
    bucket: str,
    key: str,
    expected_sha256: str,
    expected_size: int,
) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    finally:
        close = getattr(body, "close", None)
        if close is not None:
            close()
    actual = digest.hexdigest()
    if size != expected_size:
        raise ValueError(f"offsite byte-size mismatch: expected {expected_size}, got {size}")
    if actual != expected_sha256:
        raise ValueError(f"offsite SHA-256 mismatch: expected {expected_sha256}, got {actual}")
    return actual


def upload_and_verify_s3(
    entry: dict[str, Any],
    path: Path,
    *,
    client: Any,
    bucket: str,
    archive_provider: str,
    verified_at: str,
    prefix: str = "raw",
) -> dict[str, Any]:
    verify_artifact_bytes(entry, path)
    key = s3_object_key(entry, prefix=prefix)
    client.upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={"Metadata": {"sha256": str(entry["sha256"])}},
    )
    remote_hash = verify_s3_remote_bytes(
        client,
        bucket=bucket,
        key=key,
        expected_sha256=str(entry["sha256"]),
        expected_size=int(entry["byte_size"]),
    )
    return record_offsite_verification(
        entry,
        archive_provider=archive_provider,
        remote_object_id=f"{bucket}/{key}",
        portable_uri=f"s3://{bucket}/{key}",
        verified_sha256=remote_hash,
        verified_at=verified_at,
    )


def restore_s3_artifact(
    entry: dict[str, Any],
    destination: Path,
    *,
    client: Any,
    bucket: str,
    key: str,
    verified_at: str,
) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"restore destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, key, str(destination))
    return verify_restore(entry, destination, verified_at=verified_at)


def assert_archive_namespace_separation(
    *,
    development_namespace: str,
    protected_namespace: str,
    development_credential_ref: str,
    protected_credential_ref: str,
) -> None:
    if development_namespace == protected_namespace:
        raise ValueError("development and protected archive namespace must be separate")
    if development_credential_ref == protected_credential_ref:
        raise ValueError("development and protected archive credential references must be separate")
