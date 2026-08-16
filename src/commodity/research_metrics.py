from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class MetricsContractError(ValueError):
    """Raised when longitudinal metrics evidence is incomplete or inconsistent."""


HARD_CONTEXT_FIELDS = (
    "forecast.target",
    "forecast.horizon",
    "forecast.prediction_timestamp_semantics",
    "forecast.target_timestamp_semantics",
    "forecast.information_cutoff_semantics",
    "dataset.dataset_sha256",
    "dataset.oos_rows",
    "dataset.oos_start",
    "dataset.oos_end",
    "dataset.coverage_signature_sha256",
    "evaluation.protocol_id",
    "evaluation.protocol_sha256",
    "evaluation.split_id",
    "evaluation.split_sha256",
    "evaluation.baseline_id",
    "evaluation.baseline_configuration_id",
    "availability.rule_id",
    "availability.rule_sha256",
)

METHODOLOGY_FIELDS = (
    "features.definition_sha256",
    "features.feature_family_ids",
    "model.family",
    "model.configuration_id",
)

INTERPRETATION_CLASSES = {
    "expected_intentional",
    "methodology_tightening",
    "likely_defect",
    "unresolved",
    "genuine_model_or_data_change",
}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_path(value: dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise MetricsContractError(f"Missing required metrics context field: {dotted}")
        current = current[part]
    return current


def _normalize_context_value(field: str, value: Any) -> Any:
    if field == "features.feature_family_ids" and isinstance(value, list):
        return sorted(value)
    return value


def _normalized_context(context: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(context, sort_keys=True))
    families = _read_path(normalized, "features.feature_family_ids")
    if isinstance(families, list):
        normalized["features"]["feature_family_ids"] = sorted(families)
    return normalized


def compute_context_id(stage: dict[str, Any]) -> str:
    context = stage.get("context")
    if not isinstance(context, dict):
        raise MetricsContractError("Stage requires a context object")
    for field in HARD_CONTEXT_FIELDS + METHODOLOGY_FIELDS:
        _read_path(context, field)
    return f"ctx-{_canonical_hash(_normalized_context(context))[:24]}"


def _validate_metric(name: str, metric: dict[str, Any]) -> None:
    if not isinstance(metric, dict):
        raise MetricsContractError(f"Metric {name!r} must be an object")
    value = metric.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricsContractError(f"Metric {name!r} requires a numeric value")
    if not math.isfinite(float(value)):
        raise MetricsContractError(f"Metric {name!r} requires a finite numeric value")
    if metric.get("direction") not in {"lower", "higher"}:
        raise MetricsContractError(f"Metric {name!r} requires direction lower|higher")
    if not isinstance(metric.get("unit"), str) or not metric["unit"]:
        raise MetricsContractError(f"Metric {name!r} requires a unit")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _validate_metric_policy(name: str, policy: Any) -> None:
    if not isinstance(policy, dict):
        raise MetricsContractError(f"Metric policy {name!r} must be an object")
    if policy.get("direction") not in {"lower", "higher"}:
        raise MetricsContractError(f"Metric policy {name!r} requires direction lower|higher")
    if not isinstance(policy.get("required"), bool):
        raise MetricsContractError(f"Metric policy {name!r} requires boolean required")
    for key in ("absolute_tolerance", "relative_tolerance"):
        value = policy.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MetricsContractError(f"Metric policy {name!r} requires numeric {key}")
        if not math.isfinite(float(value)) or float(value) < 0:
            raise MetricsContractError(f"Metric policy {name!r} requires finite non-negative {key}")


def validate_stage(stage: dict[str, Any]) -> None:
    if not isinstance(stage.get("stage_id"), str) or not stage["stage_id"]:
        raise MetricsContractError("Stage requires stage_id")
    if not isinstance(stage.get("sequence"), int) or stage["sequence"] < 0:
        raise MetricsContractError("Stage requires a non-negative integer sequence")
    if stage.get("evidence_status") not in {"native", "backfilled", "partial"}:
        raise MetricsContractError("Stage requires evidence_status native|backfilled|partial")
    metrics = stage.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise MetricsContractError("Stage requires at least one metric")
    for name, metric in metrics.items():
        _validate_metric(name, metric)
    expected_context_id = compute_context_id(stage)
    if stage.get("context_id") != expected_context_id:
        raise MetricsContractError(
            f"Stage {stage['stage_id']!r} context_id mismatch; expected {expected_context_id}"
        )
    if stage["evidence_status"] == "native":
        for field in HARD_CONTEXT_FIELDS:
            if _read_path(stage["context"], field) is None:
                raise MetricsContractError(f"Native stage requires context field: {field}")
    evidence = stage.get("evidence")
    if not isinstance(evidence, dict):
        raise MetricsContractError("Stage requires evidence")
    for key in (
        "code_revision",
        "config_sha256",
        "artifact_sha256s",
        "reproducibility_status",
        "source_refs",
    ):
        if key not in evidence:
            raise MetricsContractError(f"Stage evidence requires {key}")
    code_revision = evidence["code_revision"]
    if code_revision is not None and (not isinstance(code_revision, str) or not code_revision):
        raise MetricsContractError("Stage evidence code_revision must be non-empty or null")
    config_sha256 = evidence["config_sha256"]
    if config_sha256 is not None and not _is_sha256(config_sha256):
        raise MetricsContractError("Stage evidence config_sha256 must be a SHA-256 or null")
    artifact_sha256s = evidence["artifact_sha256s"]
    if not isinstance(artifact_sha256s, list) or any(
        not _is_sha256(value) for value in artifact_sha256s
    ):
        raise MetricsContractError("Stage evidence artifact_sha256s must contain SHA-256 values")
    if evidence["reproducibility_status"] not in {
        "passed",
        "failed",
        "not_reproduced",
        "unknown",
    }:
        raise MetricsContractError("Stage evidence has invalid reproducibility_status")
    source_refs = evidence["source_refs"]
    if not isinstance(source_refs, list) or any(
        not isinstance(value, str) or not value for value in source_refs
    ):
        raise MetricsContractError("Stage evidence source_refs must contain non-empty strings")
    if stage["evidence_status"] == "native":
        if not code_revision or not _is_sha256(config_sha256):
            raise MetricsContractError("Native stage requires code and config identity evidence")
        if not artifact_sha256s or not source_refs:
            raise MetricsContractError("Native stage requires artifact and source evidence")
    if not isinstance(stage.get("methodology_change_summary"), str) or not stage[
        "methodology_change_summary"
    ].strip():
        raise MetricsContractError("Stage requires methodology_change_summary")
    interpretations = stage.get("interpretations", [])
    if not isinstance(interpretations, list):
        raise MetricsContractError("Stage interpretations must be a list")
    for item in interpretations:
        if not isinstance(item, dict):
            raise MetricsContractError("Regression interpretation must be an object")
        if item.get("comparison_kind") not in {"previous_stage", "best_comparable"}:
            raise MetricsContractError("Regression interpretation has invalid comparison_kind")
        if not isinstance(item.get("reference_stage_id"), str) or not item["reference_stage_id"]:
            raise MetricsContractError("Regression interpretation requires reference_stage_id")
        if not isinstance(item.get("metric"), str) or not item["metric"]:
            raise MetricsContractError("Regression interpretation requires metric")
        if item.get("classification") not in INTERPRETATION_CLASSES:
            raise MetricsContractError("Invalid regression interpretation classification")
        if not isinstance(item.get("explanation"), str) or not item["explanation"].strip():
            raise MetricsContractError("Regression interpretation requires explanation")
        if not isinstance(item.get("accepted"), bool):
            raise MetricsContractError("Regression interpretation requires boolean accepted")
        tracking_ref = item.get("tracking_ref")
        if tracking_ref is not None and (not isinstance(tracking_ref, str) or not tracking_ref):
            raise MetricsContractError("Regression interpretation tracking_ref must be non-empty or null")


def compare_context(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    changed: list[str] = []
    methodology: list[str] = []
    for field in HARD_CONTEXT_FIELDS:
        try:
            left = _read_path(previous["context"], field)
            right = _read_path(current["context"], field)
        except (KeyError, MetricsContractError):
            missing.append(field)
            continue
        left = _normalize_context_value(field, left)
        right = _normalize_context_value(field, right)
        if left is None or right is None:
            missing.append(field)
        elif left != right:
            changed.append(field)
    for field in METHODOLOGY_FIELDS:
        try:
            left = _read_path(previous["context"], field)
            right = _read_path(current["context"], field)
        except (KeyError, MetricsContractError):
            missing.append(field)
            continue
        left = _normalize_context_value(field, left)
        right = _normalize_context_value(field, right)
        if left is None or right is None:
            missing.append(field)
        elif left != right:
            methodology.append(field)
    if missing:
        status = "insufficient_context"
        reason_code = "missing_required_context_identity"
    elif changed:
        status = "non_comparable"
        reason_code = "hard_context_changed"
    else:
        status = "comparable"
        reason_code = "comparable_context"
    return {
        "status": status,
        "reason_code": reason_code,
        "missing_fields": sorted(set(missing)),
        "hard_context_changes": changed,
        "methodology_movements": methodology,
    }


def _metric_comparison(
    previous: dict[str, Any],
    current: dict[str, Any],
    metric_name: str,
    policy: dict[str, Any],
    *,
    comparison_kind: str,
    baseline_kind: str,
) -> dict[str, Any]:
    context = compare_context(previous, current)
    base = {
        "comparison_kind": comparison_kind,
        "baseline_kind": baseline_kind,
        "metric": metric_name,
        "reference_stage_id": previous["stage_id"],
        "context_status": context["status"],
        "context_changes": context["hard_context_changes"],
        "methodology_movements": context["methodology_movements"],
    }
    if context["status"] != "comparable":
        return {
            **base,
            "status": "not_comparable",
            "reason_code": context["reason_code"],
        }
    previous_metric = previous.get("metrics", {}).get(metric_name)
    current_metric = current.get("metrics", {}).get(metric_name)
    if previous_metric is None or current_metric is None:
        return {**base, "status": "unavailable", "reason_code": "metric_unavailable"}
    _validate_metric(metric_name, previous_metric)
    _validate_metric(metric_name, current_metric)
    if previous_metric["unit"] != current_metric["unit"]:
        return {
            **base,
            "status": "not_comparable",
            "reason": "metric_unit_changed",
            "reason_code": "metric_unit_changed",
        }
    if previous_metric["direction"] != current_metric["direction"]:
        return {
            **base,
            "status": "not_comparable",
            "reason": "metric_direction_changed",
            "reason_code": "metric_direction_changed",
        }
    if current_metric["direction"] != policy["direction"]:
        raise MetricsContractError(f"Policy direction mismatch for metric {metric_name!r}")
    previous_value = float(previous_metric["value"])
    current_value = float(current_metric["value"])
    delta = current_value - previous_value
    absolute_tolerance = float(policy.get("absolute_tolerance", 0.0))
    relative_tolerance = float(policy.get("relative_tolerance", 0.0))
    if absolute_tolerance < 0 or relative_tolerance < 0:
        raise MetricsContractError("Regression tolerances must be non-negative")
    materiality = max(absolute_tolerance, abs(previous_value) * relative_tolerance)
    if policy["direction"] == "lower":
        deterioration = delta > materiality
        improvement = delta < -materiality
    else:
        deterioration = delta < -materiality
        improvement = delta > materiality
    status = "regression" if deterioration else "improvement" if improvement else "unchanged"
    reason_code = {
        "regression": "material_regression",
        "improvement": "material_improvement",
        "unchanged": "within_tolerance",
    }[status]
    return {
        **base,
        "status": status,
        "reason_code": reason_code,
        "previous_value": previous_value,
        "current_value": current_value,
        "delta": delta,
        "materiality": materiality,
    }


def _previous_reference(
    history: Iterable[dict[str, Any]],
    current: dict[str, Any],
    metric_name: str,
    direction: str,
) -> dict[str, Any] | None:
    current_metric = current.get("metrics", {}).get(metric_name)
    if current_metric is None:
        return None
    for stage in reversed(list(history)):
        if compare_context(stage, current)["status"] != "comparable":
            continue
        metric = stage.get("metrics", {}).get(metric_name)
        if metric is None:
            continue
        if metric.get("unit") != current_metric.get("unit") or metric.get("direction") != direction:
            continue
        return stage
    return None


def _best_reference(
    history: Iterable[dict[str, Any]], current: dict[str, Any], metric_name: str, direction: str
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for stage in history:
        if compare_context(stage, current)["status"] != "comparable":
            continue
        metric = stage.get("metrics", {}).get(metric_name)
        current_metric = current.get("metrics", {}).get(metric_name)
        if metric is None or current_metric is None:
            continue
        if metric.get("unit") != current_metric.get("unit") or metric.get("direction") != direction:
            continue
        candidates.append(stage)
    if not candidates:
        return None

    def metric_value(item: dict[str, Any]) -> float:
        return float(item["metrics"][metric_name]["value"])

    return (
        min(candidates, key=metric_value)
        if direction == "lower"
        else max(candidates, key=metric_value)
    )


def evaluate_comparisons(
    current: dict[str, Any], history: list[dict[str, Any]], policy: dict[str, Any]
) -> dict[str, Any]:
    validate_stage(current)
    for stage in history:
        validate_stage(stage)
    metric_policies = policy.get("metric_policies")
    if not isinstance(metric_policies, dict) or not metric_policies:
        raise MetricsContractError("comparison_policy requires metric_policies")
    for metric_name, metric_policy in metric_policies.items():
        _validate_metric_policy(metric_name, metric_policy)
    previous_stage = history[-1] if history else None
    results: list[dict[str, Any]] = []
    for metric_name, metric_policy in metric_policies.items():
        if metric_policy.get("required", False) and metric_name not in current["metrics"]:
            results.append(
                {
                    "comparison_kind": "current",
                    "baseline_kind": "current",
                    "metric": metric_name,
                    "status": "missing_required_metric",
                    "reason_code": "missing_required_metric",
                    "reference_stage_id": None,
                }
            )
            continue
        if metric_name not in current["metrics"]:
            continue
        previous_comparable = _previous_reference(
            history,
            current,
            metric_name,
            metric_policy["direction"],
        )
        if previous_comparable is not None:
            results.append(
                _metric_comparison(
                    previous_comparable,
                    current,
                    metric_name,
                    metric_policy,
                    comparison_kind="previous_stage",
                    baseline_kind="previous_comparable",
                )
            )
        best = _best_reference(history, current, metric_name, metric_policy["direction"])
        if best is not None and (
            previous_comparable is None or best["stage_id"] != previous_comparable["stage_id"]
        ):
            results.append(
                _metric_comparison(
                    best,
                    current,
                    metric_name,
                    metric_policy,
                    comparison_kind="best_comparable",
                    baseline_kind="best_historical_comparable",
                )
            )
    previous_context = (
        compare_context(previous_stage, current) if previous_stage is not None else None
    )
    return {"previous_context": previous_context, "metric_comparisons": results}


def _find_interpretation(stage: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any] | None:
    for item in stage.get("interpretations", []):
        if (
            item.get("comparison_kind") == comparison["comparison_kind"]
            and item.get("metric") == comparison["metric"]
            and item.get("reference_stage_id") == comparison["reference_stage_id"]
        ):
            return item
    return None


def _missing_required_context_identities(stage: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    context = stage.get("context")
    if not isinstance(context, dict):
        return list(HARD_CONTEXT_FIELDS)
    for field in HARD_CONTEXT_FIELDS:
        try:
            value = _read_path(context, field)
        except MetricsContractError:
            missing.append(field)
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


def evaluate_closeout(
    current: dict[str, Any], history: list[dict[str, Any]], policy: dict[str, Any]
) -> dict[str, Any]:
    evaluated = evaluate_comparisons(current, history, policy)
    blockers: list[str] = []
    for field in _missing_required_context_identities(current):
        blockers.append(f"current_stage_missing_required_context_identity:{field}")
    previous_context = evaluated["previous_context"]
    if previous_context is not None:
        if previous_context["status"] == "insufficient_context":
            blockers.append("previous_stage_comparison_missing_required_context")
        elif previous_context["status"] == "non_comparable":
            summary = current["methodology_change_summary"].strip().lower()
            if summary in {"none", "n/a", "not applicable", "no change"}:
                blockers.append("non_comparable_previous_stage_requires_methodology_explanation")
    for comparison in evaluated["metric_comparisons"]:
        if comparison["status"] == "missing_required_metric":
            blockers.append(f"missing_required_metric:{comparison['metric']}")
            continue
        if comparison["status"] != "regression":
            continue
        interpretation = _find_interpretation(current, comparison)
        key = (
            f"{comparison['comparison_kind']}:{comparison['reference_stage_id']}:"
            f"{comparison['metric']}"
        )
        if interpretation is None:
            blockers.append(f"material_regression_requires_interpretation:{key}")
            continue
        classification = interpretation["classification"]
        accepted = interpretation.get("accepted") is True
        if not accepted:
            blockers.append(f"regression_not_accepted:{key}")
        if classification in {"likely_defect", "unresolved"}:
            if not interpretation.get("tracking_ref"):
                blockers.append(f"regression_requires_tracking_ref:{key}")
            if not accepted:
                blockers.append(f"regression_not_resolved_or_accepted:{key}")
    alarm_reason_codes = sorted({blocker.split(":", 1)[0] for blocker in blockers})
    return {
        **evaluated,
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "alarm_reason_codes": alarm_reason_codes,
    }


def validate_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("schema_version") != 1:
        raise MetricsContractError("Longitudinal metrics ledger requires schema_version=1")
    policy = ledger.get("comparison_policy")
    if not isinstance(policy, dict) or not policy.get("policy_id"):
        raise MetricsContractError("Ledger requires comparison_policy.policy_id")
    metric_policies = policy.get("metric_policies")
    if not isinstance(metric_policies, dict) or not metric_policies:
        raise MetricsContractError("Ledger requires comparison_policy.metric_policies")
    for metric_name, metric_policy in metric_policies.items():
        _validate_metric_policy(metric_name, metric_policy)
    stages = ledger.get("stages")
    if not isinstance(stages, list):
        raise MetricsContractError("Ledger stages must be a list")
    stage_ids: set[str] = set()
    sequences: set[int] = set()
    previous_sequence = -1
    for stage in stages:
        validate_stage(stage)
        if stage["stage_id"] in stage_ids:
            raise MetricsContractError(f"Duplicate stage_id: {stage['stage_id']}")
        if stage["sequence"] in sequences:
            raise MetricsContractError(f"Duplicate stage sequence: {stage['sequence']}")
        if stage["sequence"] <= previous_sequence:
            raise MetricsContractError("Ledger stages must be strictly ordered by sequence")
        stage_ids.add(stage["stage_id"])
        sequences.add(stage["sequence"])
        previous_sequence = stage["sequence"]
        for metric_name, metric_policy in metric_policies.items():
            metric = stage["metrics"].get(metric_name)
            if metric is not None and metric["direction"] != metric_policy.get("direction"):
                raise MetricsContractError(f"Metric policy direction mismatch: {metric_name}")


def load_ledger(path: Path) -> dict[str, Any]:
    ledger = json.loads(path.read_text(encoding="utf-8"))
    validate_ledger(ledger)
    return ledger


def latest_closeout(ledger: dict[str, Any]) -> dict[str, Any]:
    validate_ledger(ledger)
    stages = ledger["stages"]
    if not stages:
        raise MetricsContractError("Cannot close out an empty longitudinal metrics ledger")
    return evaluate_closeout(stages[-1], stages[:-1], ledger["comparison_policy"])


def render_markdown_summary(ledger: dict[str, Any]) -> str:
    validate_ledger(ledger)
    metric_names = list(ledger["comparison_policy"]["metric_policies"])
    header = [
        "Stage",
        "Context",
        "Previous",
        "Methodology movement",
        *metric_names,
        "Regressions",
    ]
    lines = [
        "# Longitudinal Research Metrics",
        "",
        "Generated from the governed longitudinal metrics ledger; do not edit this summary as authority.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    history: list[dict[str, Any]] = []
    for stage in ledger["stages"]:
        evaluated = evaluate_comparisons(stage, history, ledger["comparison_policy"])
        previous_context = evaluated["previous_context"]
        previous_status = previous_context["status"] if previous_context else "first_stage"
        methodology_movements = (
            previous_context["methodology_movements"] if previous_context else []
        )
        methodology_text = ", ".join(methodology_movements) if methodology_movements else "none"
        metric_values = []
        for metric_name in metric_names:
            metric = stage["metrics"].get(metric_name)
            metric_values.append("n/a" if metric is None else str(metric["value"]))
        regressions = [
            f"{item['comparison_kind']}:{item['metric']}"
            for item in evaluated["metric_comparisons"]
            if item["status"] == "regression"
        ]
        regression_text = ", ".join(sorted(set(regressions))) if regressions else "none"
        row = [
            stage["stage_id"],
            f"`{stage['context_id']}`",
            previous_status,
            methodology_text,
            *metric_values,
            regression_text,
        ]
        lines.append("| " + " | ".join(row) + " |")
        history.append(stage)
    lines.extend(["", f"Policy: `{ledger['comparison_policy']['policy_id']}`", ""])
    return "\n".join(lines)