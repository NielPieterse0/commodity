"""Owner-approved B2 bucket default: 365 days COMPLIANCE, fail-closed.

Use only on an authorized external-network execution lane.
Without --apply this command performs read-only inspection.
Never emit access credentials, untrusted exception messages or object data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backblaze_b2_preflight import create_client, read_env, safe_code
from botocore.exceptions import BotoCoreError, ClientError

_APPROVED_DAYS = 365
_APPROVED_MODE = "COMPLIANCE"


def retention_state(config: dict) -> str:
    lock = config.get("ObjectLockConfiguration", {})
    if lock.get("ObjectLockEnabled") != "Enabled":
        raise ValueError("object_lock_not_enabled")
    retention = lock.get("Rule", {}).get("DefaultRetention")
    if not retention:
        return "unset"
    if retention == {"Mode": _APPROVED_MODE, "Days": _APPROVED_DAYS}:
        return "approved_existing"
    raise ValueError("conflicting_default_retention")


def inspect_or_apply(client: object, bucket: str, *, apply: bool) -> dict:
    """Read current policy; mutate only unset policy with explicit approval."""
    before = client.get_object_lock_configuration(Bucket=bucket)
    state = retention_state(before)
    if state == "approved_existing":
        return {
            "status": "verified_approved_existing",
            "mode": _APPROVED_MODE,
            "days": _APPROVED_DAYS,
            "mutation_performed": False,
        }
    if not apply:
        return {
            "status": "approved_change_pending",
            "mode": _APPROVED_MODE,
            "days": _APPROVED_DAYS,
            "mutation_performed": False,
        }
    client.put_object_lock_configuration(
        Bucket=bucket,
        ObjectLockConfiguration={
            "ObjectLockEnabled": "Enabled",
            "Rule": {
                "DefaultRetention": {
                    "Mode": _APPROVED_MODE,
                    "Days": _APPROVED_DAYS,
                }
            },
        },
    )
    after = client.get_object_lock_configuration(Bucket=bucket)
    if retention_state(after) != "approved_existing":
        raise ValueError("post_write_verification_failed")
    return {
        "status": "verified_approved_applied",
        "mode": _APPROVED_MODE,
        "days": _APPROVED_DAYS,
        "mutation_performed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        required=True,
        type=Path,
        help="Ignored local env containing existing Backblaze settings",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the explicitly approved 365-day Compliance default if unset",
    )
    args = parser.parse_args()
    try:
        settings = read_env(args.env_file)
        client = create_client(settings)
        result = inspect_or_apply(
            client,
            bucket=settings["BACKBLAZE_B2_BUCKET_NAME"],
            apply=args.apply,
        )
        result["storage_archive_verified"] = False
        result["object_versions_verified"] = 0
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"].startswith("verified_") else 3
    except (ValueError, BotoCoreError, ClientError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_code": safe_code(exc)
                    if not isinstance(exc, ValueError)
                    else str(exc)
                    if str(exc)
                    in {
                        "object_lock_not_enabled",
                        "conflicting_default_retention",
                        "post_write_verification_failed",
                    }
                    else "local_precondition_failed",
                    "mutation_success_not_claimed": True,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
