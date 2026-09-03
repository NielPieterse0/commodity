from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from commodity.research_metrics import (
    MetricsContractError,
    compare_context,
    compute_context_id,
    evaluate_closeout,
    evaluate_comparisons,
    render_markdown_summary,
    validate_ledger,
    validate_stage,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _policy(*, tolerance: float = 0.0) -> dict:
    return {
        "policy_id": "v1-regression-policy",
        "metric_policies": {
            "rmse": {
                "direction": "lower",
                "required": True,
                "absolute_tolerance": tolerance,
                "relative_tolerance": 0.0,
            },
            "direction_accuracy": {
                "direction": "higher",
                "required": False,
                "absolute_tolerance": 0.0,
                "relative_tolerance": 0.0,
            },
        },
    }


def _stage(stage_id: str, sequence: int, rmse: float, *, evidence_status: str = "native") -> dict:
    stage = {
        "stage_id": stage_id,
        "sequence": sequence,
        "label": stage_id,
        "evidence_status": evidence_status,
        "context_id": "",
        "context": {
            "forecast": {
                "target": "target_ret_1",
                "horizon": "1 trading session",
                "prediction_timestamp_semantics": "after market close",
                "target_timestamp_semantics": "next completed daily market bar",
                "information_cutoff_semantics": "strict point in time",
            },
            "dataset": {
                "dataset_id": "full-v1",
                "freeze_id": "freeze-1",
                "dataset_sha256": SHA_A,
                "rows": 960,
                "oos_rows": 204,
                "oos_start": "2025-10-24T00:00:00+00:00",
                "oos_end": "2026-08-12T00:00:00+00:00",
                "coverage_signature_sha256": SHA_B,
            },
            "evaluation": {
                "protocol_id": "phase-d-v1",
                "protocol_sha256": SHA_C,
                "split_id": "expanding-41-fold",
                "split_sha256": SHA_B,
                "baseline_id": "naive",
                "baseline_configuration_id": "config/models.json#naive",
            },
            "availability": {
                "rule_id": "v1-pit-availability",
                "rule_sha256": SHA_C,
            },
            "features": {
                "definition_id": "v1-feature-set",
                "definition_sha256": SHA_A,
                "feature_family_ids": ["market", "storage", "weather"],
            },
            "model": {
                "family": "ridge",
                "configuration_id": "config/models.json#ridge",
            },
        },
        "metrics": {
            "rmse": {"value": rmse, "unit": "return", "direction": "lower"},
            "direction_accuracy": {
                "value": 0.51,
                "unit": "fraction",
                "direction": "higher",
            },
        },
        "methodology_change_summary": "No hard evaluation-context change.",
        "interpretations": [],
        "evidence": {
            "code_revision": "deadbeef",
            "config_sha256": SHA_A,
            "artifact_sha256s": [SHA_B],
            "reproducibility_status": "passed",
            "source_refs": ["git-history:docs/development/example/evidence.json"],
        },
    }
    stage["context_id"] = compute_context_id(stage)
    return stage


def _reidentify(stage: dict) -> dict:
    stage["context_id"] = compute_context_id(stage)
    return stage


def _ledger(stages: list[dict], *, tolerance: float = 0.0) -> dict:
    return {
        "schema_version": 1,
        "ledger_id": "commodity-longitudinal-research-metrics",
        "comparison_policy": _policy(tolerance=tolerance),
        "stages": stages,
    }


def test_schema_accepts_valid_governed_ledger() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "contracts/research_metrics.schema.json").read_text(encoding="utf-8-sig"))
    Draft202012Validator(schema).validate(_ledger([_stage("v1", 1, 0.10)]))


def test_runtime_ledger_validation_enforces_canonical_json_schema() -> None:
    ledger = _ledger([_stage("v1", 1, 0.10)])
    del ledger["ledger_id"]
    with pytest.raises(MetricsContractError, match="research_metrics.schema.json"):
        validate_ledger(ledger)


def test_context_identity_is_deterministic_and_methodology_change_stays_comparable() -> None:
    first = _stage("a", 1, 0.10)
    second = copy.deepcopy(first)
    second["stage_id"] = "b"
    second["sequence"] = 2
    second["context"]["model"]["configuration_id"] = "config/models.json#hist_gradient_boosting"
    _reidentify(second)

    assert compute_context_id(first) == first["context_id"]
    assert second["context_id"] != first["context_id"]
    result = compare_context(first, second)
    assert result["status"] == "comparable"
    assert result["methodology_movements"] == ["model.configuration_id"]


def test_hard_context_change_is_non_comparable() -> None:
    first = _stage("a", 1, 0.10)
    second = copy.deepcopy(first)
    second["stage_id"] = "b"
    second["sequence"] = 2
    second["context"]["evaluation"]["split_sha256"] = SHA_C
    _reidentify(second)

    result = compare_context(first, second)
    assert result["status"] == "non_comparable"
    assert "evaluation.split_sha256" in result["hard_context_changes"]


def test_partial_historical_context_fails_closed_as_insufficient() -> None:
    historical = _stage("v0", 0, 0.08, evidence_status="partial")
    historical["context"]["availability"]["rule_sha256"] = None
    _reidentify(historical)
    current = _stage("v1", 1, 0.10)

    assert compare_context(historical, current)["status"] == "insufficient_context"
    gate = evaluate_closeout(current, [historical], _policy())
    assert gate["status"] == "blocked"
    assert "previous_stage_comparison_missing_required_context" in gate["blockers"]


def test_regression_detection_checks_previous_and_best_comparable_stage() -> None:
    best = _stage("best", 1, 0.08)
    previous = _stage("previous", 2, 0.09)
    current = _stage("current", 3, 0.095)

    result = evaluate_comparisons(current, [best, previous], _policy())
    regressions = [item for item in result["metric_comparisons"] if item["status"] == "regression"]
    rmse_refs = {
        (item["comparison_kind"], item["reference_stage_id"])
        for item in regressions
        if item["metric"] == "rmse"
    }
    assert rmse_refs == {("previous_stage", "previous"), ("best_comparable", "best")}


def test_materiality_tolerance_prevents_noise_from_becoming_regression() -> None:
    previous = _stage("previous", 1, 0.10)
    current = _stage("current", 2, 0.105)
    result = evaluate_comparisons(current, [previous], _policy(tolerance=0.01))
    rmse = next(item for item in result["metric_comparisons"] if item["metric"] == "rmse")
    assert rmse["status"] == "unchanged"


def test_closeout_blocks_uninterpreted_material_regression() -> None:
    previous = _stage("previous", 1, 0.08)
    current = _stage("current", 2, 0.10)

    gate = evaluate_closeout(current, [previous], _policy())
    assert gate["status"] == "blocked"
    assert any(item.startswith("material_regression_requires_interpretation") for item in gate["blockers"])


def test_closeout_accepts_explained_regression() -> None:
    previous = _stage("previous", 1, 0.08)
    current = _stage("current", 2, 0.10)
    current["interpretations"].append(
        {
            "comparison_kind": "previous_stage",
            "reference_stage_id": "previous",
            "metric": "rmse",
            "classification": "methodology_tightening",
            "explanation": "The stricter evaluation protocol removed optimistic leakage.",
            "accepted": True,
            "tracking_ref": None,
        }
    )

    assert evaluate_closeout(current, [previous], _policy())["status"] == "passed"


def test_likely_defect_regression_requires_tracking_and_explicit_acceptance() -> None:
    previous = _stage("previous", 1, 0.08)
    current = _stage("current", 2, 0.10)
    current["interpretations"].append(
        {
            "comparison_kind": "previous_stage",
            "reference_stage_id": "previous",
            "metric": "rmse",
            "classification": "likely_defect",
            "explanation": "Unexpected deterioration requires defect triage.",
            "accepted": False,
            "tracking_ref": None,
        }
    )

    gate = evaluate_closeout(current, [previous], _policy())
    assert gate["status"] == "blocked"
    assert any(item.startswith("regression_requires_tracking_ref") for item in gate["blockers"])
    assert any(item.startswith("regression_not_resolved_or_accepted") for item in gate["blockers"])

    current["interpretations"][0]["accepted"] = True
    current["interpretations"][0]["tracking_ref"] = "#99"
    assert evaluate_closeout(current, [previous], _policy())["status"] == "passed"


def test_required_metric_missing_blocks_closeout() -> None:
    current = _stage("current", 1, 0.10)
    del current["metrics"]["rmse"]
    gate = evaluate_closeout(current, [], _policy())
    assert gate["status"] == "blocked"
    assert "missing_required_metric:rmse" in gate["blockers"]


def test_validate_ledger_rejects_duplicate_stage_identity() -> None:
    first = _stage("same", 1, 0.10)
    second = _stage("same", 2, 0.09)
    with pytest.raises(MetricsContractError, match="Duplicate stage_id"):
        validate_ledger(_ledger([first, second]))


def test_markdown_summary_is_generated_from_ledger() -> None:
    first = _stage("v0", 1, 0.08)
    second = _stage("v1", 2, 0.10)
    text = render_markdown_summary(_ledger([first, second]))
    assert "Generated from the governed longitudinal metrics ledger" in text
    assert "| v0 |" in text
    assert "| v1 |" in text
    assert "rmse" in text


def test_feature_family_order_does_not_change_context_identity_or_comparability() -> None:
    first = _stage("a", 1, 0.10)
    second = copy.deepcopy(first)
    second["stage_id"] = "b"
    second["sequence"] = 2
    second["context"]["features"]["feature_family_ids"] = ["weather", "market", "storage"]
    _reidentify(second)

    assert second["context_id"] == first["context_id"]
    assert compare_context(first, second)["methodology_movements"] == []


def test_non_finite_metric_is_rejected_fail_closed() -> None:
    stage = _stage("bad", 1, 0.10)
    stage["metrics"]["rmse"]["value"] = float("nan")
    with pytest.raises(MetricsContractError, match="finite"):
        validate_stage(stage)


def test_first_stage_with_required_metrics_can_close_out() -> None:
    stage = _stage("first", 1, 0.10)
    gate = evaluate_closeout(stage, [], _policy())
    assert gate["status"] == "passed"
    assert gate["blockers"] == []
    assert gate["previous_context"] is None


def test_invalid_metric_policy_is_rejected_before_comparison() -> None:
    ledger = _ledger([_stage("v1", 1, 0.10)])
    ledger["comparison_policy"]["metric_policies"]["rmse"]["absolute_tolerance"] = float("inf")
    with pytest.raises(MetricsContractError, match="finite non-negative"):
        validate_ledger(ledger)


def test_native_stage_requires_artifact_and_source_identity() -> None:
    stage = _stage("native", 1, 0.10)
    stage["evidence"]["artifact_sha256s"] = []
    with pytest.raises(MetricsContractError, match="artifact and source"):
        validate_stage(stage)


def test_regression_gate_uses_most_recent_comparable_baseline_across_context_break() -> None:
    previous_comparable = _stage("previous-comparable", 1, 0.08)
    intervening = _stage("intervening-incomparable", 2, 0.50)
    intervening["context"]["evaluation"]["split_sha256"] = SHA_C
    _reidentify(intervening)
    current = _stage("current", 3, 0.10)

    result = evaluate_comparisons(
        current,
        [previous_comparable, intervening],
        _policy(),
    )
    regression = next(
        item
        for item in result["metric_comparisons"]
        if item["metric"] == "rmse" and item["baseline_kind"] == "previous_comparable"
    )

    assert regression["reference_stage_id"] == "previous-comparable"
    assert regression["status"] == "regression"
    assert regression["reason_code"] == "material_regression"
    assert result["previous_context"]["status"] == "non_comparable"


def test_previous_comparable_baseline_skips_stage_without_the_metric() -> None:
    with_metric = _stage("with-metric", 1, 0.08)
    without_metric = _stage("without-metric", 2, 0.50)
    del without_metric["metrics"]["rmse"]
    current = _stage("current", 3, 0.10)

    result = evaluate_comparisons(current, [with_metric, without_metric], _policy())
    regression = next(
        item
        for item in result["metric_comparisons"]
        if item["metric"] == "rmse" and item["baseline_kind"] == "previous_comparable"
    )

    assert regression["reference_stage_id"] == "with-metric"
    assert regression["status"] == "regression"


def test_closeout_fails_closed_when_latest_stage_lacks_required_context_identity() -> None:
    current = _stage("current", 1, 0.10, evidence_status="partial")
    current["context"]["evaluation"]["baseline_configuration_id"] = None
    _reidentify(current)

    gate = evaluate_closeout(current, [], _policy())

    assert gate["status"] == "blocked"
    assert (
        "current_stage_missing_required_context_identity:evaluation.baseline_configuration_id"
        in gate["blockers"]
    )
    assert "current_stage_missing_required_context_identity" in gate["alarm_reason_codes"]


def test_closeout_blocks_material_regression_when_interpretation_is_not_accepted() -> None:
    previous = _stage("previous", 1, 0.08)
    current = _stage("current", 2, 0.10)
    current["interpretations"].append(
        {
            "comparison_kind": "previous_stage",
            "reference_stage_id": "previous",
            "metric": "rmse",
            "classification": "methodology_tightening",
            "explanation": "Candidate explanation exists but has not been accepted.",
            "accepted": False,
            "tracking_ref": None,
        }
    )

    gate = evaluate_closeout(current, [previous], _policy())

    assert gate["status"] == "blocked"
    assert any(item.startswith("regression_not_accepted") for item in gate["blockers"])
    assert "regression_not_accepted" in gate["alarm_reason_codes"]


def test_comparison_reason_codes_distinguish_missing_identity_from_hard_change() -> None:
    current = _stage("current", 3, 0.10)
    missing = _stage("missing", 1, 0.08, evidence_status="partial")
    missing["context"]["availability"]["rule_sha256"] = None
    _reidentify(missing)
    changed = _stage("changed", 2, 0.08)
    changed["context"]["evaluation"]["split_sha256"] = SHA_C
    _reidentify(changed)

    missing_result = evaluate_comparisons(current, [missing], _policy())
    changed_result = evaluate_comparisons(current, [changed], _policy())

    assert missing_result["previous_context"]["reason_code"] == "missing_required_context_identity"
    assert changed_result["previous_context"]["reason_code"] == "hard_context_changed"
