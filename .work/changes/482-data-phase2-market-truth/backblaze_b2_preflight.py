"""Read-only Backblaze B2 Object Lock commissioning preflight for Phase 2.

Never prints credentials; never modifies a bucket or an object.
Live calls require an approved external-network execution lane.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

_KEYS = (
    "BACKBLAZE_B2_ENDPOINT",
    "BACKBLAZE_B2_KEY_ID",
    "BACKBLAZE_B2_KEY_NAME",
    "BACKBLAZE_B2_BUCKET_NAME",
    "BACKBLAZE_B2_APPLICATION_KEY",
)


def read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("environment file is missing")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in _KEYS:
            if key in values:
                raise ValueError("duplicate Backblaze environment setting")
            values[key] = value.strip().strip('"').strip("'")
    if any(not values.get(key) for key in _KEYS):
        raise ValueError("required Backblaze environment setting missing or empty")
    endpoint = values["BACKBLAZE_B2_ENDPOINT"].removeprefix("https://")
    if not re.fullmatch(r"s3\.eu-central-\d{3}\.backblazeb2\.com", endpoint):
        raise ValueError("Backblaze S3 endpoint is not an allowed EU Central host")
    if not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9.-]{4,62}", values["BACKBLAZE_B2_BUCKET_NAME"]
    ):
        raise ValueError("Backblaze bucket name is invalid")
    values["BACKBLAZE_B2_ENDPOINT"] = endpoint
    return values


def safe_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = str(response.get("Error", {}).get("Code", "ClientError"))
        if re.fullmatch(r"[A-Za-z0-9_-]{1,48}", code):
            return code
    return type(exc).__name__


def inspect_remote(settings: dict[str, str]) -> dict[str, object]:
    client = create_client(settings)
    bucket = settings["BACKBLAZE_B2_BUCKET_NAME"]
    result: dict[str, object] = {
        "bucket_access": "unverified",
        "object_lock_enabled": None,
        "default_compliance_retention": None,
        "immutable_versions_verified": 0,
        "restore_drills_verified": 0,
        "archive_durability_verified": False,
    }
    try:
        client.head_bucket(Bucket=bucket)
        result["bucket_access"] = "verified"
    except (BotoCoreError, ClientError, OSError) as exc:
        result["bucket_access"] = "failed_" + safe_code(exc)
        return result
    try:
        config = client.get_object_lock_configuration(Bucket=bucket)
        lock = config.get("ObjectLockConfiguration", {})
        result["object_lock_enabled"] = lock.get("ObjectLockEnabled") == "Enabled"
        default = lock.get("Rule", {}).get("DefaultRetention", {})
        result["default_compliance_retention"] = default.get("Mode") == "COMPLIANCE"
        result["default_retention_days"] = default.get("Days")
        result["default_retention_years"] = default.get("Years")
    except (BotoCoreError, ClientError, OSError) as exc:
        # Bucket-scoped upload keys may not have readBucketRetentions.
        # Permission denial is unknown, not proof Object Lock is disabled.
        result["object_lock_error"] = safe_code(exc)
    return result


def verify_locked_version(
    client: object,
    *,
    bucket: str,
    key: str,
    version_id: str,
    sha256: str,
    byte_size: int,
) -> dict[str, object]:
    """Verify one explicitly identified pre-2023 version without listing objects."""
    if not key.startswith("phase2/pre2023/") or ".." in key.split("/"):
        raise ValueError("only explicitly identified pre-2023 objects are in scope")
    if not version_id or version_id.lower() == "null":
        raise ValueError("an immutable non-null object version is required")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256) or byte_size < 0:
        raise ValueError("a pinned SHA-256 and nonnegative exact size are required")

    arguments = {"Bucket": bucket, "Key": key, "VersionId": version_id}
    retention = client.get_object_retention(**arguments)["Retention"]
    until = retention.get("RetainUntilDate")
    if (
        retention.get("Mode") != "COMPLIANCE"
        or not isinstance(until, datetime)
        or until.tzinfo is None
        or until <= datetime.now(UTC)
    ):
        raise ValueError("exact object version has no active compliance retention")

    response = client.get_object(**arguments)
    body = response["Body"]
    digest = hashlib.sha256()
    total = 0
    try:
        if response.get("VersionId") != version_id:
            raise ValueError("version identity does not match the pinned version")
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if total > byte_size:
                raise ValueError("remote object exceeds pinned size")
    finally:
        body.close()
    if total != byte_size or digest.hexdigest() != sha256:
        raise ValueError("remote object content differs from pinned source bytes")
    return {
        "exact_version_retention": "COMPLIANCE",
        "exact_version_retention_active": True,
        "exact_version_bytes_sha256_verified": True,
        "exact_version_size_verified": True,
        "immutable_versions_verified": 1,
        "archive_durability_verified": False,
        "restore_drills_verified": 0,
    }


def create_client(settings: dict[str, str]):
    """Build the B2 client; secrets never become part of a receipt."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url="https://" + settings["BACKBLAZE_B2_ENDPOINT"],
        region_name=settings["BACKBLAZE_B2_ENDPOINT"].split(".")[1],
        aws_access_key_id=settings["BACKBLAZE_B2_KEY_ID"],
        aws_secret_access_key=settings["BACKBLAZE_B2_APPLICATION_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 2},
        ),
    )


def inspect_pinned_version(
    settings: dict[str, str],
    *,
    key: str,
    version_id: str,
    sha256: str,
    byte_size: int,
) -> dict[str, object]:
    return verify_locked_version(
        create_client(settings),
        bucket=settings["BACKBLAZE_B2_BUCKET_NAME"],
        key=key,
        version_id=version_id,
        sha256=sha256,
        byte_size=byte_size,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument(
        "--live", action="store_true", help="Read-only B2 calls; external lane only"
    )
    parser.add_argument("--object-key", help="Explicit phase2/pre2023/ object key")
    parser.add_argument("--version-id", help="Pinned immutable object version ID")
    parser.add_argument("--sha256", help="Expected exact object SHA-256")
    parser.add_argument("--byte-size", type=int, help="Expected exact object size")
    args = parser.parse_args()
    try:
        settings = read_env(args.env_file)
        result: dict[str, object] = {
            "status": "configuration_valid_not_remote_verified",
            "settings_present": True,
            "remote_mutations": 0,
            "credentials_disclosed": False,
            "archive_durability_verified": False,
        }
        version_args = (args.object_key, args.version_id, args.sha256, args.byte_size)
        verify_version = any(x is not None for x in version_args)
        if verify_version and (not args.live or any(x is None for x in version_args)):
            raise ValueError("version audit requires --live and all four version pins")
        if args.live:
            result.update(inspect_remote(settings))
            result["status"] = "read_only_bucket_configuration"
            if verify_version:
                result.update(
                    inspect_pinned_version(
                        settings,
                        key=args.object_key,
                        version_id=args.version_id,
                        sha256=args.sha256,
                        byte_size=args.byte_size,
                    )
                )
                result["status"] = "read_only_exact_version_verification"
        print(json.dumps(result, sort_keys=True))
        if not args.live:
            return 0
        if verify_version:
            return 0 if result.get("immutable_versions_verified") == 1 else 2
        return (
            0
            if (
                result.get("bucket_access") == "verified"
                and result.get("object_lock_enabled") is True
            )
            else 2
        )
    except (ValueError, BotoCoreError, ClientError, OSError) as exc:
        print(json.dumps({"status": "preflight_failed", "error_code": safe_code(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
