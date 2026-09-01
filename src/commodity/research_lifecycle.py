from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from commodity.research_methodology import MethodologyError

LIFECYCLE_STAGES = (
    "helicopter_view",
    "gap",
    "evidence_led_zoom_in",
    "quality_literature",
    "mechanism",
    "hypothesis",
    "expected_and_disconfirming_observations",
    "feasibility",
    "preregister_and_freeze_if_applicable",
    "execute",
    "verify",
    "compare_observed_vs_expected",
    "external_post_result_triangulation",
    "programme_conclusion",
    "active_revisit_triggers",
)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MethodologyError(f"expected JSON object: {path}")
    return value


def _validate(payload: dict[str, Any], schema_name: str) -> None:
    schema = _load_json(_root() / "contracts" / schema_name)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        detail = "; ".join(error.message for error in errors[:5])
        raise MethodologyError(f"{schema_name} validation failed: {detail}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compare(value: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return value == expected
    try:
        if isinstance(value, bool) or isinstance(expected, bool):
            raise TypeError("boolean is not a numeric comparison value")
        left = float(value)
        right = float(expected)
    except (TypeError, ValueError) as exc:
        raise MethodologyError(
            f"comparison operator {operator!r} requires numeric metric and threshold values"
        ) from exc
    if operator == "gte":
        return left >= right
    if operator == "lte":
        return left <= right
    if operator == "gt":
        return left > right
    if operator == "lt":
        return left < right
    raise MethodologyError(f"unsupported comparison operator: {operator!r}")


def validate_literature_snapshot(snapshot: dict[str, Any]) -> None:
    _validate(snapshot, "literature_snapshot.schema.json")
    source_ids = {item["source_id"] for item in snapshot["sources"]}
    if len(source_ids) != len(snapshot["sources"]):
        raise MethodologyError("literature source_id values must be unique")
    for mapping in snapshot["claim_map"]:
        unknown = set(mapping["source_ids"]) - source_ids
        if unknown:
            raise MethodologyError(f"literature claim references unknown sources: {sorted(unknown)}")


def validate_literature_ref(ref: dict[str, Any]) -> dict[str, Any]:
    path = _root() / str(ref.get("path", ""))
    if not path.is_file():
        raise MethodologyError(f"literature snapshot does not exist: {ref.get('path')}")
    actual = sha256_file(path)
    if actual.lower() != str(ref.get("sha256", "")).lower():
        raise MethodologyError("literature snapshot sha256 mismatch")
    snapshot = _load_json(path)
    validate_literature_snapshot(snapshot)
    return snapshot


def validate_exploratory_run(record: dict[str, Any], *, allow_legacy: bool = False) -> None:
    _validate(record, "exploratory_run.schema.json")
    version = int(record.get("schema_version", 0))
    if version == 1:
        if not allow_legacy:
            raise MethodologyError("new exploratory research must use governed schema_version 2")
        return
    if tuple(record["lifecycle"]) != LIFECYCLE_STAGES:
        raise MethodologyError("exploratory lifecycle must contain the 15 governed stages in order")
    snapshot = validate_literature_ref(record["literature_snapshot_ref"])
    expected = set(record["expectations"]["expected"])
    disconfirming = set(record["expectations"]["disconfirming"])
    if not expected.issubset(set(snapshot["expected_observations"])):
        raise MethodologyError("exploratory expectations must be literature-derived")
    if not disconfirming.issubset(set(snapshot["disconfirming_observations"])):
        raise MethodologyError("exploratory disconfirmers must be literature-derived")
    decision = record["feasibility"]["decision"]
    accessed = record["execution"]["protected_outcomes_accessed"]
    prereg_ref = record["execution"].get("preregistration_ref")
    if decision != "go" and accessed:
        raise MethodologyError("non-GO exploratory research cannot access protected outcomes")
    if accessed and not prereg_ref:
        raise MethodologyError("protected outcome access requires a frozen preregistration reference")
    if decision in {"hold", "defer"} and not record["revisit_triggers"]:
        raise MethodologyError("HOLD/DEFER requires active revisit triggers")


def _nested(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise MethodologyError(f"trigger metric is missing: {dotted_path}")
        value = value[part]
    return value


def evaluate_revisit_registry(
    registry: dict[str, Any],
    *,
    evidence_loader: Callable[[str], dict[str, Any]] | None = None,
    evaluated_at: str | None = None,
    successor_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    _validate(registry, "revisit_triggers.schema.json")
    load = evidence_loader or (lambda relative: _load_json(_root() / relative))
    stamp = evaluated_at or datetime.now(UTC).isoformat()
    successors = successor_refs or {}
    updated = copy.deepcopy(registry)
    history = updated["evaluation_history"]
    for trigger in updated["triggers"]:
        if trigger["status"] not in {"active", "satisfied"}:
            continue
        evidence = load(trigger["evidence_input"])
        observed = _nested(evidence, trigger["metric"])
        satisfied = _compare(observed, trigger["operator"], trigger["threshold"])
        evaluation_id = f"{trigger['trigger_id']}:{stamp}"
        prior = [item for item in history if item["evaluation_id"] == evaluation_id]
        if prior:
            continue
        successor_ref = successors.get(trigger["trigger_id"])
        if satisfied and not successor_ref:
            raise MethodologyError(
                f"satisfied revisit trigger requires traceable successor: {trigger['trigger_id']}"
            )
        history.append({
            "evaluation_id": evaluation_id,
            "evaluated_at": stamp,
            "trigger_id": trigger["trigger_id"],
            "observed": observed,
            "satisfied": satisfied,
            "evidence_ref": trigger["evidence_input"],
            "successor_ref": successor_ref,
        })
        trigger["status"] = "released" if satisfied else "active"
    return updated


def assert_governed_research_preflight() -> None:
    registry_path = _root() / "config" / "research_revisit_triggers.json"
    if registry_path.exists():
        assert_revisit_preflight_current(_load_json(registry_path))


def assert_revisit_preflight_current(registry: dict[str, Any]) -> None:
    _validate(registry, "revisit_triggers.schema.json")
    by_trigger: dict[str, list[dict[str, Any]]] = {}
    for item in registry["evaluation_history"]:
        by_trigger.setdefault(item["trigger_id"], []).append(item)
    for trigger in registry["triggers"]:
        if trigger["status"] != "active":
            continue
        evaluations = by_trigger.get(trigger["trigger_id"], [])
        if not evaluations:
            raise MethodologyError(f"active revisit trigger has never been evaluated: {trigger['trigger_id']}")
        latest = max(evaluations, key=lambda item: item["evaluated_at"])
        evidence = _load_json(_root() / trigger["evidence_input"])
        observed = _nested(evidence, trigger["metric"])
        current = _compare(observed, trigger["operator"], trigger["threshold"])
        if latest["observed"] != observed or latest["satisfied"] != current:
            raise MethodologyError(f"revisit trigger evaluation is stale: {trigger['trigger_id']}")
        if current:
            raise MethodologyError(
                f"active revisit trigger is satisfied but has no released successor: {trigger['trigger_id']}"
            )
