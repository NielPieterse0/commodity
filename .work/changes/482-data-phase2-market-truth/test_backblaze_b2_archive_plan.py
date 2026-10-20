"""Archive planning guards; no provider calls or historical dataset rebuilds."""
from pathlib import Path

import backblaze_b2_archive_plan as plan
import pytest


def test_reject_out_of_scope_keys_and_untrusted_hash(tmp_path: Path):
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"x")
    with pytest.raises(ValueError, match="out_of_scope_object_key"):
        plan._entry(sample, "phase2/2023/source", "a" * 64, 1, "original_source")
    with pytest.raises(ValueError, match="out_of_scope_object_key"):
        plan._entry(sample, "phase2/pre2023/../2023", "a" * 64, 1, "original_source")
    with pytest.raises(ValueError, match="invalid_sha256_identity"):
        plan._entry(sample, "phase2/pre2023/source/x", "not_sha256", 1, "original_source")
    with pytest.raises(ValueError, match="missing_or_changed_archive_input"):
        plan._entry(sample, "phase2/pre2023/source/x", "a" * 64, 2, "original_source")


def test_reject_symlink_source_if_supported(tmp_path: Path):
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"x")
    link = tmp_path / "linked.bin"
    try:
        link.symlink_to(sample)
    except (OSError, NotImplementedError):
        pytest.skip("symlink permission denied by Windows")
    with pytest.raises(ValueError, match="missing_or_changed_archive_input"):
        plan._entry(link, "phase2/pre2023/source/x", "a" * 64, 1, "original_source")


def test_archive_plan_is_exact_pre2023_cohort_and_not_admission():
    result = plan.build_plan()
    assert result["status"] == "planned_not_remote_verified"
    assert result["protected_2023plus_read"] is False
    assert result["remote_versions_verified"] == 0
    assert result["object_count"] == 43
    assert len({row["key"] for row in result["objects"]}) == 43
    assert {r["kind"] for r in result["objects"]} == {
        "original_source", "final_parquet", "final_manifest"
    }
    assert sum(row["kind"] == "original_source" for row in result["objects"]) == 39
    assert sum(row["kind"] == "final_parquet" for row in result["objects"]) == 3
    assert sum(row["kind"] == "final_manifest" for row in result["objects"]) == 1
    assert all(row["key"].startswith("phase2/pre2023/") for row in result["objects"])
    assert 1_200_000_000 < result["total_bytes"] < 1_400_000_000
    assert result["object_lock_required"] == {"mode": "COMPLIANCE", "days": 365}
