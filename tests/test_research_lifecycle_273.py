from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from commodity.research_lifecycle import (
    LIFECYCLE_STAGES,
    assert_revisit_preflight_current,
    evaluate_revisit_registry,
    validate_exploratory_run,
    validate_literature_snapshot,
)
from commodity.research_methodology import MethodologyError

ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_methodology_declares_exact_fifteen_stage_lifecycle() -> None:
    methodology = _json("config/research_methodology.json")
    assert tuple(methodology["lifecycle_stages"]) == LIFECYCLE_STAGES
    assert len(LIFECYCLE_STAGES) == 15


def test_original_271_is_legacy_only_and_successor_is_governed() -> None:
    legacy = _json("research/exploratory/front-curve-feasibility-271.json")
    with pytest.raises(MethodologyError, match="governed schema_version 3"):
        validate_exploratory_run(legacy)
    validate_exploratory_run(legacy, allow_legacy=True)
    successor = _json("research/exploratory/front-curve-feasibility-273-conformance.json")
    with pytest.raises(MethodologyError, match="schema_version 3 with data assurance"):
        validate_exploratory_run(successor)
    validate_exploratory_run(successor, allow_legacy=True)
    assured = copy.deepcopy(successor)
    assured["schema_version"] = 3
    with pytest.raises(MethodologyError, match="requires data_assurance_ref"):
        validate_exploratory_run(assured)
    assert successor["lineage"]["predecessor_record"].endswith("front-curve-feasibility-271.json")
    assert successor["execution"]["protected_outcomes_accessed"] is False


def test_literature_claims_must_resolve_to_quality_sources() -> None:
    snapshot = _json("research/literature/front-curve-271-conformance-v1.json")
    validate_literature_snapshot(snapshot)
    broken = copy.deepcopy(snapshot)
    broken["claim_map"][0]["source_ids"] = ["missing-source"]
    with pytest.raises(MethodologyError, match="unknown sources"):
        validate_literature_snapshot(broken)


def test_non_go_successor_cannot_claim_protected_access() -> None:
    record = _json("research/exploratory/front-curve-feasibility-273-conformance.json")
    broken = copy.deepcopy(record)
    broken["execution"]["protected_outcomes_accessed"] = True
    with pytest.raises(MethodologyError, match="non-GO"):
        validate_exploratory_run(broken, allow_legacy=True)


def test_exploratory_expectations_must_be_literature_derived() -> None:
    record = _json("research/exploratory/front-curve-feasibility-273-conformance.json")
    broken = copy.deepcopy(record)
    broken["expectations"]["expected"].append("post-hoc invented expectation")
    with pytest.raises(MethodologyError, match="literature-derived"):
        validate_exploratory_run(broken, allow_legacy=True)


def test_active_triggers_have_current_evaluation_history() -> None:
    registry = _json("config/research_revisit_triggers.json")
    assert_revisit_preflight_current(registry)
    active_ids = {item["trigger_id"] for item in registry["triggers"] if item["status"] == "active"}
    evaluated_ids = {item["trigger_id"] for item in registry["evaluation_history"]}
    assert active_ids <= evaluated_ids
    assert all(item["satisfied"] is False for item in registry["evaluation_history"])


def test_non_numeric_revisit_metric_fails_closed() -> None:
    registry = _json("config/research_revisit_triggers.json")
    registry["evaluation_history"] = []
    evidence = _json("research/exploratory/front-curve-feasibility-273-conformance.json")
    evidence["feasibility"]["evidence"]["rows"]["scoreable_targets"] = "unknown"
    with pytest.raises(MethodologyError, match="requires numeric"):
        evaluate_revisit_registry(
            registry,
            evidence_loader=lambda _path: evidence,
            evaluated_at="2026-09-02T00:00:00+02:00",
        )


def test_satisfied_trigger_requires_traceable_successor() -> None:
    registry = _json("config/research_revisit_triggers.json")
    registry["triggers"] = [
        item for item in registry["triggers"] if item["trigger_id"].startswith("front-curve-")
    ]
    registry["evaluation_history"] = []
    evidence = _json("research/exploratory/front-curve-feasibility-273-conformance.json")
    evidence["feasibility"]["evidence"]["rows"]["scoreable_targets"] = 1500
    loader = lambda _path: evidence
    with pytest.raises(MethodologyError, match="traceable successor"):
        evaluate_revisit_registry(registry, evidence_loader=loader, evaluated_at="2026-09-02T00:00:00+02:00")
    updated = evaluate_revisit_registry(
        registry, evidence_loader=loader, evaluated_at="2026-09-02T00:00:00+02:00",
        successor_refs={"front-curve-development-rows": "issue:future-successor"},
    )
    first = next(item for item in updated["triggers"] if item["trigger_id"] == "front-curve-development-rows")
    assert first["status"] == "released"
