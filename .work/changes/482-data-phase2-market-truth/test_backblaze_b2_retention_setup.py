"""Credential-free retention setup tests using an isolated S3 client fake."""

from unittest.mock import Mock

import pytest
from backblaze_b2_retention_setup import inspect_or_apply, retention_state
from botocore.exceptions import ClientError


def state(mode=None, days=None, enabled=True):
    result = {"ObjectLockEnabled": "Enabled" if enabled else "Disabled"}
    if mode:
        result["Rule"] = {"DefaultRetention": {"Mode": mode, "Days": days}}
    return {"ObjectLockConfiguration": result}


def client_with(*configs):
    client = Mock()
    client.get_object_lock_configuration.side_effect = list(configs)
    return client


def test_inspect_unset_is_read_only():
    client = client_with(state())
    result = inspect_or_apply(client, "commodity-phase2-archive", apply=False)
    assert result == {
        "status": "approved_change_pending",
        "mode": "COMPLIANCE",
        "days": 365,
        "mutation_performed": False,
    }
    client.put_object_lock_configuration.assert_not_called()


def test_apply_exact_365_compliance_and_verify_readback():
    client = client_with(state(), state("COMPLIANCE", 365))
    result = inspect_or_apply(client, "commodity-phase2-archive", apply=True)
    assert result["status"] == "verified_approved_applied"
    client.put_object_lock_configuration.assert_called_once_with(
        Bucket="commodity-phase2-archive",
        ObjectLockConfiguration={
            "ObjectLockEnabled": "Enabled",
            "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 365}},
        },
    )
    assert client.get_object_lock_configuration.call_count == 2


def test_exact_existing_default_is_idempotent():
    client = client_with(state("COMPLIANCE", 365))
    result = inspect_or_apply(client, "commodity-phase2-archive", apply=True)
    assert result["status"] == "verified_approved_existing"
    assert result["mutation_performed"] is False
    client.put_object_lock_configuration.assert_not_called()


@pytest.mark.parametrize(
    "config",
    [
        state(enabled=False),
        state("GOVERNANCE", 365),
        state("COMPLIANCE", 180),
        state("COMPLIANCE", 366),
        state("GOVERNANCE", 1),
        state("COMPLIANCE", 365, enabled=False),
    ],
)
def test_refuse_disabled_or_conflicting_default(config):
    client = client_with(config)
    with pytest.raises(
        ValueError, match="(?:object_lock_not_enabled|conflicting_default_retention)"
    ):
        inspect_or_apply(client, "commodity-phase2-archive", apply=True)
    client.put_object_lock_configuration.assert_not_called()


def test_post_write_failed_verification_is_not_success():
    client = client_with(state(), state())
    with pytest.raises(ValueError, match="post_write_verification_failed"):
        inspect_or_apply(client, "commodity-phase2-archive", apply=True)
    client.put_object_lock_configuration.assert_called_once()


def test_missing_bucket_permission_does_not_attempt_mutation():
    client = Mock()
    client.get_object_lock_configuration.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "SECRET"}},
        "GetObjectLockConfiguration",
    )
    with pytest.raises(ClientError):
        inspect_or_apply(client, "commodity-phase2-archive", apply=True)
    client.put_object_lock_configuration.assert_not_called()


def test_rule_validation_requires_exact_days_and_mode():
    assert retention_state(state("COMPLIANCE", 365)) == "approved_existing"
    assert retention_state(state()) == "unset"
    with pytest.raises(ValueError, match="conflicting_default_retention"):
        retention_state(state("COMPLIANCE", 364))
