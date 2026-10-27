"""Offline, credential-free tests for the Phase 2 B2 preflight."""

from datetime import UTC
from unittest.mock import Mock

import pytest
from backblaze_b2_preflight import inspect_remote, read_env, safe_code

ENV = """BACKBLAZE_B2_ENDPOINT=s3.eu-central-003.backblazeb2.com
BACKBLAZE_B2_KEY_ID=dummy-key-id
BACKBLAZE_B2_KEY_NAME=research-uploader
BACKBLAZE_B2_BUCKET_NAME=commodity-phase2-archive
BACKBLAZE_B2_APPLICATION_KEY=DO_NOT_LOG_FAKE_SECRET
"""


def test_config_valid_and_no_sensitive_output(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "is_file", lambda _: True)
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: ENV)
    settings = read_env(Path("ignored"))
    assert settings["BACKBLAZE_B2_APPLICATION_KEY"] == "DO_NOT_LOG_FAKE_SECRET"
    assert settings["BACKBLAZE_B2_ENDPOINT"] == "s3.eu-central-003.backblazeb2.com"


def test_config_rejects_missing_secret(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "is_file", lambda _: True)
    monkeypatch.setattr(
        Path, "read_text", lambda *a, **k: ENV.replace("DO_NOT_LOG_FAKE_SECRET", "")
    )
    with pytest.raises(ValueError, match="required Backblaze"):
        read_env(Path("ignored"))


def test_config_rejects_host_substitution(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "is_file", lambda _: True)
    monkeypatch.setattr(
        Path, "read_text", lambda *a, **k: ENV.replace("backblazeb2.com", "evil.test")
    )
    with pytest.raises(ValueError, match="allowed EU Central"):
        read_env(Path("ignored"))


def test_remote_read_only_and_does_not_claim_archive(monkeypatch):
    import boto3

    client = Mock()
    client.head_bucket.return_value = {}
    client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled",
            "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 30}},
        }
    }
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    settings = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in ENV.strip().splitlines()
    }
    result = inspect_remote(settings)
    assert result["object_lock_enabled"] is True
    assert result["default_compliance_retention"] is True
    assert result["immutable_versions_verified"] == 0
    assert result["restore_drills_verified"] == 0
    assert client.method_calls[0][0] == "head_bucket"
    assert client.method_calls[1][0] == "get_object_lock_configuration"
    assert len(client.method_calls) == 2


def test_error_code_never_echoes_exception_text():
    assert safe_code(ValueError("DO_NOT_LOG_FAKE_SECRET")) == "ValueError"


def test_bucket_read_retention_permission_denied_is_unknown(monkeypatch):
    import boto3
    from botocore.exceptions import ClientError

    client = Mock()
    client.get_object_lock_configuration.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "do not disclose"}}, "GetLock"
    )
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    settings = dict(line.split("=", 1) for line in ENV.strip().splitlines())
    result = inspect_remote(settings)
    assert result["bucket_access"] == "verified"
    assert result["object_lock_enabled"] is None
    assert result["default_compliance_retention"] is None
    assert result["object_lock_error"] == "AccessDenied"
    assert result["archive_durability_verified"] is False


def _version_client(payload=b"sample", mode="COMPLIANCE", version_id="v1", days=30):
    from datetime import datetime, timedelta
    from io import BytesIO

    client = Mock()
    client.get_object_retention.return_value = {
        "Retention": {
            "Mode": mode,
            "RetainUntilDate": datetime.now(UTC) + timedelta(days=days),
        }
    }
    client.get_object.return_value = {
        "VersionId": version_id,
        "Body": BytesIO(payload),
    }
    return client


def test_exact_object_version_compliance_and_remote_hash():
    import hashlib

    from backblaze_b2_preflight import verify_locked_version

    client = _version_client()
    outcome = verify_locked_version(
        client,
        bucket="commodity-phase2-archive",
        key="phase2/pre2023/raw/fixture.csv",
        version_id="v1",
        sha256=hashlib.sha256(b"sample").hexdigest(),
        byte_size=6,
    )
    assert outcome["immutable_versions_verified"] == 1
    assert outcome["restore_drills_verified"] == 0
    assert outcome["archive_durability_verified"] is False
    assert client.get_object.call_args.kwargs["VersionId"] == "v1"
    assert client.get_object_retention.call_args.kwargs["VersionId"] == "v1"


def test_fails_closed_for_governance_retention():
    import hashlib

    from backblaze_b2_preflight import verify_locked_version

    with pytest.raises(ValueError, match="active compliance"):
        verify_locked_version(
            _version_client(mode="GOVERNANCE"),
            bucket="test-bucket",
            key="phase2/pre2023/raw/test.csv",
            version_id="v1",
            sha256=hashlib.sha256(b"sample").hexdigest(),
            byte_size=6,
        )


def test_fails_closed_for_expired_retention():
    import hashlib

    from backblaze_b2_preflight import verify_locked_version

    with pytest.raises(ValueError, match="active compliance"):
        verify_locked_version(
            _version_client(days=-1),
            bucket="test-bucket",
            key="phase2/pre2023/raw/test.csv",
            version_id="v1",
            sha256=hashlib.sha256(b"sample").hexdigest(),
            byte_size=6,
        )


def test_fails_closed_for_wrong_version_or_remote_bytes():
    import hashlib

    from backblaze_b2_preflight import verify_locked_version

    params = {
        "bucket": "test-bucket",
        "key": "phase2/pre2023/raw/test.csv",
        "version_id": "v1",
        "sha256": hashlib.sha256(b"sample").hexdigest(),
        "byte_size": 6,
    }
    with pytest.raises(ValueError, match="version identity"):
        verify_locked_version(_version_client(version_id="v2"), **params)
    with pytest.raises(ValueError, match="content differs"):
        verify_locked_version(_version_client(payload=b"SAMPLE"), **params)


@pytest.mark.parametrize(
    "key",
    [
        "phase2/2023/holdout.csv",
        "protected/2024/example.csv",
        "phase2/pre2023/../2024/holdout.csv",
    ],
)
def test_refuses_protected_or_traversal_keys(key):
    import hashlib

    from backblaze_b2_preflight import verify_locked_version

    client = _version_client()
    with pytest.raises(ValueError, match="pre-2023"):
        verify_locked_version(
            client,
            bucket="test-bucket",
            key=key,
            version_id="v1",
            sha256=hashlib.sha256(b"sample").hexdigest(),
            byte_size=6,
        )
    client.get_object.assert_not_called()
    client.get_object_retention.assert_not_called()


def test_bucket_lock_enabled_without_default_does_not_prove_immutability(monkeypatch):
    import boto3

    client = Mock()
    client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
    }
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    settings = dict(line.split("=", 1) for line in ENV.strip().splitlines())
    result = inspect_remote(settings)
    assert result["object_lock_enabled"] is True
    assert result["default_compliance_retention"] is False
    assert result["immutable_versions_verified"] == 0
    assert result["archive_durability_verified"] is False
