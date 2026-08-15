from __future__ import annotations

import copy

import pytest


def _config() -> dict:
    return {
        "dataset": {
            "dataset_id": "dataset-1",
            "freeze_id": "freeze-1",
            "dataset_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "required_evidence_mode": "evaluation_pit",
            "require_research_evaluation_eligible": True,
            "require_research_promotion_ineligible": True,
        },
        "robustness": {
            "max_adjusted_p_value": 0.05,
            "require_positive_rmse_improvement": True,
            "require_positive_ci_lower": True,
            "minimum_positive_periods": 2,
            "minimum_positive_regimes": 2,
            "edge_claim_requires_all_criteria": True,
        },
    }


def _manifest() -> dict:
    return {
        "dataset_id": "dataset-1",
        "freeze_id": "freeze-1",
        "dataset_sha256": "a" * 64,
        "evidence_mode": "evaluation_pit",
        "research_evaluation_eligible": True,
        "research_promotion_eligible": False,
    }


def test_dataset_gate_requires_exact_frozen_evaluation_identity() -> None:
    from commodity.phase_d_run import validate_phase_d_dataset_manifest

    validate_phase_d_dataset_manifest(_manifest(), _config(), manifest_sha256="b" * 64)
    changed = _manifest()
    changed["dataset_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="dataset_sha256"):
        validate_phase_d_dataset_manifest(changed, _config(), manifest_sha256="b" * 64)
    changed = _manifest()
    changed["research_promotion_eligible"] = True
    with pytest.raises(ValueError, match="promotion"):
        validate_phase_d_dataset_manifest(changed, _config(), manifest_sha256="b" * 64)


def test_robustness_requires_significance_and_cross_slice_consistency() -> None:
    from commodity.phase_d_run import apply_robustness_criteria

    result = {
        "baseline_model": "naive",
        "candidate_comparisons": [
            {
                "model": "naive", "rmse_improvement": 0.0, "ci_lower": 0.0,
                "adjusted_p_value": 1.0, "period_rmse_improvements": [0.0, 0.0, 0.0],
                "regime_rmse_improvements": {"low": 0.0, "medium": 0.0, "high": 0.0},
            },
            {
                "model": "ridge", "rmse_improvement": 0.01, "ci_lower": 0.002,
                "adjusted_p_value": 0.03, "period_rmse_improvements": [0.01, 0.02, -0.01],
                "regime_rmse_improvements": {"low": 0.01, "medium": 0.02, "high": -0.01},
            },
            {
                "model": "hist_gb", "rmse_improvement": 0.02, "ci_lower": -0.001,
                "adjusted_p_value": 0.01, "period_rmse_improvements": [0.02, 0.03, 0.01],
                "regime_rmse_improvements": {"low": 0.01, "medium": 0.02, "high": 0.03},
            },
        ],
        "ablation_effects": [
            {
                "model": "ridge", "family": "weather", "rmse_improvement": 0.005,
                "ci_lower": 0.001, "adjusted_p_value": 0.04,
                "period_rmse_improvements": [0.01, 0.01, -0.01],
                "regime_rmse_improvements": {"low": 0.01, "medium": 0.01, "high": -0.01},
            }
        ],
    }

    assessed = apply_robustness_criteria(copy.deepcopy(result), _config())

    assert assessed["robustness"]["robust_edge_models"] == ["ridge"]
    assert assessed["robustness"]["disposition"] == "robust_edge_detected"
    assert assessed["candidate_comparisons"][1]["robust"] is True
    assert assessed["candidate_comparisons"][2]["robust"] is False
    assert assessed["ablation_effects"][0]["material_incremental_value"] is True
