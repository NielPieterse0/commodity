"""Off-network-prepared, operator-run exact-version B2 archive commissioning.

Local KIS Work must never execute this networked script. Use only in an
authorized external-network lane after independently verifying free capacity.
Never outputs secrets. Checkpoint is ignored local state; nothing is admitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from audit_original_cohort import protected_table_reads
from backblaze_b2_archive_plan import PLAN_PATH, STAGE, build_plan
from backblaze_b2_preflight import (
    create_client,
    read_env,
    safe_code,
    verify_locked_version,
)
from backblaze_b2_retention_setup import retention_state
from botocore.exceptions import BotoCoreError, ClientError

RECEIPT_PATH = STAGE / "backblaze-b2-exact-version-checkpoint.json"
EARLIEST_SAFE_RETENTION = timedelta(days=364)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checkpoint(payload: dict) -> None:
    if STAGE.is_symlink() or not STAGE.is_dir():
        raise ValueError("unsafe_archive_runtime_directory")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=STAGE,
        prefix="b2-checkpoint-", suffix=".pending", delete=False,
    ) as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        pending = Path(stream.name)
    os.replace(pending, RECEIPT_PATH)


def load_checkpoint(plan_digest: str) -> dict:
    if STAGE.is_symlink() or RECEIPT_PATH.is_symlink():
        raise ValueError("unsafe_archive_runtime_directory")
    if not RECEIPT_PATH.exists():
        return {"schema_version": 1, "issue": 482, "plan_sha256": plan_digest,
                "entries": {}, "research_admission": False}
    saved = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    if (saved.get("plan_sha256") != plan_digest or saved.get("issue") != 482
            or saved.get("research_admission") is not False
            or not isinstance(saved.get("entries"), dict)):
        raise ValueError("archive_checkpoint_mismatched")
    return saved


def _verify_version(client: object, bucket: str, obj: dict, version_id: str) -> None:
    retention = client.get_object_retention(
        Bucket=bucket, Key=obj["key"], VersionId=version_id)["Retention"]
    until = retention.get("RetainUntilDate")
    if (retention.get("Mode") != "COMPLIANCE" or not isinstance(until, datetime)
            or until.tzinfo is None
            or until.astimezone(UTC) - datetime.now(UTC) < EARLIEST_SAFE_RETENTION):
        raise ValueError("version_retention_not_365_day_compliance")
    proof = verify_locked_version(client, bucket=bucket, key=obj["key"],
                                  version_id=version_id, sha256=obj["sha256"],
                                  byte_size=obj["bytes"])
    if proof["immutable_versions_verified"] != 1:
        raise ValueError("remote_exact_version_verification_failed")


def _require_fresh_object_key(client: object, bucket: str, key: str) -> None:
    # Never mint redundant immutable versions when one may already exist.
    # A failed HEAD with 403 is NOT proof that the key is absent.
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if safe_code(exc) in {"404", "NoSuchKey", "NotFound"}:
            return
        raise
    raise ValueError("remote_object_key_already_exists_reconcile_manually")


def _upload_one(client: object, bucket: str, obj: dict) -> str:
    path = Path(obj["local_path"])
    _require_fresh_object_key(client, bucket, obj["key"])
    with protected_table_reads([path]):
        if path.is_symlink() or path.stat().st_size != obj["bytes"]:
            raise ValueError("local_source_identity_changed")
        if _sha256_file(path) != obj["sha256"]:
            raise ValueError("source_bytes_mismatch")
        with path.open("rb") as stream:
            response = client.put_object(
                Bucket=bucket, Key=obj["key"], Body=stream,
                ContentLength=obj["bytes"], Metadata={"sha256": obj["sha256"]})
    version = response.get("VersionId")
    if not isinstance(version, str) or not version or version.lower() == "null":
        raise ValueError("remote_object_has_no_version_id")
    return version


def apply_archive(
    *, client: object, bucket: str, plan: dict,
    verified_free_remaining_bytes: int, verified_free_egress_bytes: int,
    checkpoint: dict,
) -> dict:
    if retention_state(client.get_object_lock_configuration(Bucket=bucket)) != "approved_existing":
        raise ValueError("bucket_retention_not_365_day_compliance")
    entries = checkpoint["entries"]
    objects = plan["objects"]
    known_keys = {row["key"] for row in objects}
    if not set(entries).issubset(known_keys):
        raise ValueError("checkpoint_contains_unexpected_keys")
    pending = sum(row["bytes"] for row in objects if row["key"] not in entries)
    expected_readback = sum(row["bytes"] for row in objects)
    if verified_free_remaining_bytes < pending or verified_free_remaining_bytes < 0:
        raise ValueError("free_capacity_not_sufficient_or_unverified")
    if verified_free_egress_bytes < expected_readback or verified_free_egress_bytes < 0:
        raise ValueError("free_egress_not_sufficient_or_unverified")
    for obj in objects:
        key = obj["key"]
        current = entries.get(key)
        if current is not None:
            if (current.get("sha256") != obj["sha256"]
                    or current.get("bytes") != obj["bytes"]
                    or not isinstance(current.get("version_id"), str)):
                raise ValueError("checkpoint_entry_identity_changed")
            version_id = current["version_id"]
        else:
            version_id = _upload_one(client, bucket, obj)
            entries[key] = {"sha256": obj["sha256"], "bytes": obj["bytes"],
                            "version_id": version_id, "status": "awaiting_readback"}
            _write_checkpoint(checkpoint)
        _verify_version(client, bucket, obj, version_id)
        entries[key]["status"] = "remote_retention_and_sha256_verified"
        _write_checkpoint(checkpoint)
    return {"status": "exact_versions_verified_no_owner_admission",
            "verified_versions": len(entries), "expected_versions": len(objects),
            "remote_delete_refusal": "not_yet_independently_proven",
            "independent_restoration": "not_yet_proven",
            "owner_approval": False, "supabase_mutations": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--verified-free-remaining-bytes", type=int, default=-1)
    parser.add_argument("--verified-free-egress-bytes", type=int, default=-1)
    parser.add_argument("--apply", action="store_true", help="Upload only on authorized external lane")
    args = parser.parse_args()
    try:
        plan = build_plan()
        canonical = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        if not PLAN_PATH.is_file() or hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() != digest:
            raise ValueError("rebuild_local_archive_plan_first")
        checkpoint = load_checkpoint(digest)
        if not args.apply:
            print(json.dumps({"status": "local_dry_run_no_network", "object_count": len(plan["objects"]),
                              "total_bytes": plan["total_bytes"], "uploaded": 0}, sort_keys=True))
            return 0
        settings = read_env(args.env_file)
        result = apply_archive(
            client=create_client(settings),
            bucket=settings["BACKBLAZE_B2_BUCKET_NAME"],
            plan=plan, verified_free_remaining_bytes=args.verified_free_remaining_bytes,
            verified_free_egress_bytes=args.verified_free_egress_bytes,
            checkpoint=checkpoint)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError, ClientError, BotoCoreError) as exc:
        print(json.dumps({"status": "blocked_not_admitted", "error_code": safe_code(exc)
                          if not isinstance(exc, (ValueError, KeyError, TypeError)) else
                          str(exc) if isinstance(exc, ValueError) and
                          str(exc) in {"bucket_retention_not_365_day_compliance",
                                       "archive_checkpoint_mismatched",
                                       "free_capacity_not_sufficient_or_unverified",
                                       "free_egress_not_sufficient_or_unverified",
                                       "remote_object_key_already_exists_reconcile_manually",
                                       "local_source_identity_changed", "source_bytes_mismatch",
                                       "remote_object_has_no_version_id",
                                       "version_retention_not_365_day_compliance",
                                       "remote_exact_version_verification_failed",
                                       "checkpoint_entry_identity_changed",
                                       "checkpoint_contains_unexpected_keys",
                                       "rebuild_local_archive_plan_first"} else
                          "archive_precondition_failed"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
