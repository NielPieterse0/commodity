from pathlib import Path

import pytest

from commodity.kronos import KronosCheckpointAdapter
from commodity.kronos_confirmation import (
    AUDIT_RELEASE_PATH,
    KronosConfirmationError,
    load_confirmation_freeze,
    require_independent_release,
    validate_confirmation_freeze,
)

ROOT = Path(__file__).resolve().parents[1]


def test_confirmation_freeze_reconstructs_without_inference() -> None:
    freeze = validate_confirmation_freeze(ROOT)
    assert freeze["experiment_id"] == "kronos-180-corrected-three-checkpoint-v1"
    assert freeze["freeze_issue"] == 182
    assert freeze["audit_issue"] == 183
    assert freeze["freeze_self_authorizes_execution"] is False


def test_confirmation_source_manifest_binds_corrected_execution() -> None:
    freeze = load_confirmation_freeze(ROOT)
    files = freeze["implementation_authority"]["source_manifest"]["files"]
    assert set(files) == {
        "config/models.json",
        "src/commodity/kronos.py",
        "src/commodity/v2_kronos.py",
        "src/commodity/roll_safe_market.py",
        "src/commodity/kronos_confirmation.py",
    }


def test_three_models_are_exact_and_share_one_inference_profile() -> None:
    freeze = load_confirmation_freeze(ROOT)
    models = freeze["models"]
    assert [models[name]["model_id"] for name in ("mini", "small", "base")] == [
        "NeoQuasar/Kronos-mini",
        "NeoQuasar/Kronos-small",
        "NeoQuasar/Kronos-base",
    ]
    assert KronosCheckpointAdapter.ALLOWED_MODEL_KEYS == {
        "kronos_mini",
        "kronos_small",
        "kronos_base",
    }
    assert freeze["common_execution"]["inference"] == {
        "T": 1.0,
        "top_p": 0.9,
        "sample_count": 1,
        "verbose": False,
    }
    assert freeze["common_execution"]["checkpoint_specific_tuning_permitted"] is False


def test_identical_rows_target_and_nine_primary_comparisons_are_frozen() -> None:
    freeze = load_confirmation_freeze(ROOT)
    data = freeze["data_and_target"]
    assert data["oos_rows"] == 204
    assert data["forecast_target"] == "target_ret_1"
    assert data["forecast_horizon"] == "1 trading session"
    assert data["all_models_use_identical_scored_rows"] is True
    comparisons = freeze["evaluation"]["primary_comparisons"]
    assert len(comparisons) == len(set(comparisons)) == 9


def test_artifact_namespaces_are_distinct_and_do_not_reuse_82() -> None:
    freeze = load_confirmation_freeze(ROOT)
    artifacts = freeze["artifacts"]
    namespaces = [artifacts[name] for name in ("mini", "small", "base")]
    assert len(set(namespaces)) == 3
    assert artifacts["historical_82_namespace_prohibited"] not in namespaces


def test_independent_audit_release_binds_exact_freeze(tmp_path: Path) -> None:
    freeze = load_confirmation_freeze(ROOT)
    release = ROOT / AUDIT_RELEASE_PATH
    assert release.is_file()
    audited = require_independent_release(ROOT, freeze)
    assert audited["audit_issue"] == 183
    assert audited["state"] == "independent_audit_passed"
    assert audited["execution_authorized"] is True

    blocked_root = tmp_path / "blocked"
    (blocked_root / "config").mkdir(parents=True)
    (blocked_root / "config" / "kronos_confirmation.json").write_bytes(
        (ROOT / "config" / "kronos_confirmation.json").read_bytes()
    )
    with pytest.raises(KronosConfirmationError, match="#183 audit release"):
        require_independent_release(blocked_root, freeze)

    stale_root = tmp_path / "stale"
    (stale_root / "config").mkdir(parents=True)
    stale_config = (ROOT / "config" / "kronos_confirmation.json").read_text(
        encoding="utf-8"
    ).replace("frozen_pending_independent_audit", "tampered_after_audit")
    (stale_root / "config" / "kronos_confirmation.json").write_text(
        stale_config, encoding="utf-8"
    )
    stale_release = stale_root / AUDIT_RELEASE_PATH
    stale_release.parent.mkdir(parents=True)
    stale_release.write_bytes(release.read_bytes())
    with pytest.raises(KronosConfirmationError, match="does not bind this exact freeze"):
        require_independent_release(stale_root, freeze)

    incomplete_root = tmp_path / "incomplete"
    (incomplete_root / "config").mkdir(parents=True)
    (incomplete_root / "config" / "kronos_confirmation.json").write_bytes(
        (ROOT / "config" / "kronos_confirmation.json").read_bytes()
    )
    incomplete_release = incomplete_root / AUDIT_RELEASE_PATH
    incomplete_release.parent.mkdir(parents=True)
    incomplete_release.write_text(
        release.read_text(encoding="utf-8").replace(
            '  "execution_authorized": true,\n', ""
        ),
        encoding="utf-8",
    )
    with pytest.raises(KronosConfirmationError, match="has not authorized"):
        require_independent_release(incomplete_root, freeze)


def test_decision_rule_cannot_be_rescued_by_diagnostics_or_tuning() -> None:
    freeze = load_confirmation_freeze(ROOT)
    decision = freeze["decision_rule"]
    assert freeze["evaluation"]["correlation_and_direction_role"] == (
        "diagnostic_non_rescuing"
    )
    assert decision["post_result_tuning_calibration_fusion_permitted"] is False
    assert decision["followup_requires_new_experiment"] is True
    assert "no_post_result_metric_or_multiplicity_changes" in freeze["prohibitions"]
