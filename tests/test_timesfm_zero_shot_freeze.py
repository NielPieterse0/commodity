import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads(
        (ROOT / "docs/development/timesfm-zero-shot-preregistration/contract.json").read_text(
            encoding="utf-8"
        )
    )


def _candidate() -> dict:
    return _contract()["experiment"]


def _model() -> dict:
    return _contract()["model"]


def test_timesfm_2_5_source_and_checkpoint_are_exactly_pinned() -> None:
    cfg = _model()
    assert cfg["enabled"] is False
    assert cfg["checkpoint_preflight_enabled"] is True
    assert cfg["source_revision"] == "3dae50b20d7a724981e8ea36cda75578f80dd2dc"
    assert cfg["model_id"] == "google/timesfm-2.5-200m-pytorch"
    assert cfg["model_revision"] == "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
    assert cfg["local_files_only"] is True
    assert cfg["checkpoint_artifacts"]["model"]["sha256"] == (
        "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8"
    )


def test_timesfm_zero_shot_variants_and_inference_are_frozen() -> None:
    candidate = _candidate()
    assert candidate["context_lengths"] == [128, 256, 512, 1024]
    assert candidate["longer_context_in_this_experiment_permitted"] is False
    assert set(candidate["representations"]) == {
        "settlement_level",
        "log_settlement",
        "log_return",
        "garman_klass_variance",
    }
    assert candidate["representations"]["garman_klass_variance"]["role"] == (
        "auxiliary_volatility_task"
    )
    inference = candidate["inference"]
    assert inference["backend"] == "pytorch"
    assert inference["torch_compile"] is False
    assert inference["max_horizon"] == 1
    assert inference["normalize_inputs"] is True
    assert inference["use_continuous_quantile_head"] is True
    assert inference["force_flip_invariance"] is True
    assert inference["fix_quantile_crossing"] is True
    assert inference["quantile_output_layout"] == "index_0_mean_then_q10_through_q90"


def test_timesfm_uses_frozen_204_row_same_contract_identity() -> None:
    candidate = _candidate()
    data = candidate["data_identity"]
    assert data["dataset_sha256"] == (
        "0c0a39b3669215b4bdc45a0fdedf90697f0c2c92690cb33700bd0bc47c80a45f"
    )
    assert data["oos_rows"] == 204
    assert data["split_rule"] == "first_252_rows_context_only_last_204_rows_scored"
    assert candidate["single_contract_required"] is True
    assert candidate["cross_contract_history_permitted"] is False
    assert candidate["cross_contract_target_permitted"] is False


def test_timesfm_primary_family_and_baselines_cannot_be_selected_post_result() -> None:
    candidate = _candidate()
    evaluation = candidate["evaluation"]
    assert evaluation["primary_metric"] == "rmse_on_next_session_log_return"
    assert evaluation["multiple_testing"] == {
        "method": "benjamini_hochberg",
        "family": "F198_TIMESFM_ZERO_SHOT",
        "post_result_regrouping_permitted": False,
        "members": 24,
        "max_adjusted_p_value": 0.05,
    }
    assert evaluation["representation_selection_after_results_permitted"] is False
    assert evaluation["context_selection_after_results_permitted"] is False
    assert evaluation["baselines"]["zero_return_naive"]["rmse"] == 0.0453230577562102
    assert evaluation["baselines"]["phase_d_full_v1_hist_gb"]["rmse"] == 0.04650733779411404


def test_timesfm_freeze_does_not_authorize_prediction_generation() -> None:
    candidate = _candidate()
    assert candidate["execution_authorized"] is False
    assert candidate["freeze_self_authorizes_execution"] is False
    assert candidate["fine_tuning_permitted"] is False
    assert candidate["xreg_permitted"] is False
    assert "no_prediction_generation_before_freeze_commit" in candidate["prohibitions"]
    assert "no_post_result_context_selection" in candidate["prohibitions"]
    assert "no_post_result_representation_selection" in candidate["prohibitions"]


def test_timesfm_freeze_binds_exact_authority_bytes() -> None:
    import hashlib

    freeze = json.loads(
        (ROOT / "docs/development/timesfm-zero-shot-preregistration/freeze.json").read_text(
            encoding="utf-8"
        )
    )
    for field, relative in {
        "contract_sha256": "docs/development/timesfm-zero-shot-preregistration/contract.json",
        "preregistration_sha256": "docs/development/timesfm-zero-shot-preregistration/preregistration.md",
    }.items():
        raw = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        assert hashlib.sha256(raw).hexdigest() == freeze[field]
    assert freeze["timesfm_results_inspected"] is False
    assert freeze["prediction_generation_authorized"] is False


def test_timesfm_contract_owns_local_model_identity_and_fails_closed_on_roll_gaps() -> None:
    candidate = _candidate()
    assert candidate["model_authority"].endswith("contract.json#model")
    lifecycle = candidate["contract_selection"]
    assert lifecycle["target_contract"].startswith("same contract_id selected at the cutoff")
    assert lifecycle["missing_same_contract_target"] == (
        "fail_entire_experiment_without_scoring_or_row_drop"
    )
    assert lifecycle["row_drop_allowed"] is False
    assert lifecycle["cross_contract_substitution_allowed"] is False
    coverage = candidate["history_coverage"]
    assert coverage["minimum_same_contract_rows"] == 20
    assert coverage["required_scored_row_coverage"] == 1.0
    assert coverage["context_lengths_are_caps_not_minima"] is True


def test_timesfm_keep_branches_have_closed_inference_families() -> None:
    evaluation = _candidate()["evaluation"]
    assert len(evaluation["primary_hypotheses"]) == 24
    assert len(evaluation["distribution_hypotheses"]) == 12
    assert len(evaluation["complementarity_hypotheses"]) == 12
    assert evaluation["distribution_family"]["members"] == 12
    assert evaluation["complementarity_family"]["members"] == 12
    assert evaluation["complementarity_family"]["fitted_or_post_result_blend_weights_permitted"] is False
    assert evaluation["volatility_claim_role"] == "secondary_descriptive_non_promotional"
    decision = _candidate()["decision_rule"]
    assert decision["volatility_can_keep_return_programme"] is False
    assert decision["post_result_variant_selection_permitted"] is False
