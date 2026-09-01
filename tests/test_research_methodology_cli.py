import json

import pytest
from test_research_methodology import ROOT, sample_prereg

from commodity.cli import build_parser
from commodity.research_methodology import (
    MethodologyError,
    audit_leakage,
    build_results,
    canonical_prereg_sha256,
    record_sealed_opening,
    register_inference_entry,
    render_executive_summary,
    render_executive_summary_from_interpretation,
    validate_research_line,
    verification_finding,
    verify_interpretation_metadata,
    verify_results,
)


def bounded_leakage_checks(root) -> dict:
    names = (
        "pit_cutoffs", "vintage_timing", "roll_contract_identity", "release_calendar",
        "overlapping_horizons", "event_windows", "join_cardinality", "feature_availability",
    )
    checks = {}
    for name in names:
        path = root / f"{name}.json"
        path.write_text('{"observed": 0}\n', encoding="utf-8")
        import hashlib
        checks[name] = {"operator": "eq", "expected": 0, "evidence_path": str(path), "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return checks


def numeric_raw_evidence() -> dict:
    return {
        "primary": {"effect": 0.15, "p_value": 0.01, "alpha": 0.05, "scientific_mepi": 0.10},
        "metrics": {},
    }


def test_experiment_cli_exposes_full_governed_surface() -> None:
    parser = build_parser()
    commands = [
        ["experiment", "verify", "--prereg", "x.json"],
        ["experiment", "verify-power", "--prereg", "x.json"],
        ["experiment", "register", "exp", "--prereg", "x.json"],
        ["experiment", "freeze", "exp", "--prereg", "x.json", "--tag", "t", "--output", "o.json"],
        ["experiment", "can-run", "--prereg", "p.json", "--freeze", "f.json"],
        ["experiment", "open-sealed", "exp", "sw-1", "--prereg", "p.json", "--freeze", "f.json", "--artifacts-exposed", "metrics.json"],
        ["experiment", "build-results", "--prereg", "p.json", "--freeze", "f.json", "--run-evidence", "run.json", "--checks", "checks.json", "--output", "r.json"],
        ["experiment", "verify-results", "--prereg", "p.json", "--results", "r.json"],
        ["experiment", "audit-leakage", "--checks", "c.json"],
        ["experiment", "reproduce", "--reference", "a.json", "--candidate", "b.json", "--tolerance", "t.json"],
        ["experiment", "executive-summary", "--prereg", "p.json", "--results", "r.json", "--interpretation", "i.md", "--output", "o.md"],
    ]
    for argv in commands:
        assert callable(parser.parse_args(argv).func)


def test_programme_ledger_registration_is_append_only_by_identity() -> None:
    prereg = sample_prereg()
    ledger = {"schema_version": 1, "programme_id": "commodity-ng", "entries": [], "family_inference": []}
    updated = register_inference_entry(ledger, prereg)
    assert ledger["entries"] == []
    assert updated["entries"][0]["experiment_id"] == prereg["experiment_id"]
    with pytest.raises(MethodologyError, match="already exists"):
        register_inference_entry(updated, prereg)


def test_sealed_window_opening_is_counted_and_exhausted() -> None:
    registry = {"schema_version": 1, "windows": [{
        "sealed_window_id": "sw-1", "eligibility": "eligible", "permitted_openings": 1, "openings": []
    }]}
    updated = record_sealed_opening(registry, "sw-1", "exp-1", ["metrics.json"])
    assert updated["windows"][0]["eligibility"] == "exhausted"
    assert updated["windows"][0]["openings"][0]["opening_number"] == 1
    assert registry["windows"][0]["openings"] == []


def test_checked_findings_cannot_overclaim_no_leakage() -> None:
    with pytest.raises(MethodologyError, match="universal"):
        verification_finding("CHECKED", "pit", "No leakage detected")
    finding = verification_finding("CHECKED", "pit", "No known PIT violation detected by the declared check.")
    assert finding["truth_class"] == "CHECKED"


def test_results_bind_exact_prereg_and_machine_derive_evidence(tmp_path) -> None:
    prereg = sample_prereg()
    findings = audit_leakage(bounded_leakage_checks(tmp_path))
    results = build_results(
        prereg,
        run_id="run-1",
        code={"commit_sha": "abc", "working_tree_dirty": False},
        data={"dataset_id": "d1", "vintage_id": "v1", "split_id": "split-1"},
        model={"family": "baseline", "configuration_id": "ridge-v1", "checkpoint_id": None},
        environment={"runtime": "python"},
        raw_evidence=numeric_raw_evidence(),
        verification=findings,
        coherence={"audit_completed": True},
        artifacts=[],
    )
    verified = verify_results(prereg, results)
    assert verified["scientific_evidence"] == "E2"
    results["scientific_evidence"] = "E6"
    with pytest.raises(MethodologyError, match="machine-derived"):
        verify_results(prereg, results)


def test_interpretation_binds_both_scientific_artifacts() -> None:
    prereg = sample_prereg()
    results = build_results(
        prereg, run_id="run-1", code={}, data={}, model={}, environment={},
        raw_evidence={"evidence_flags": {}}, verification=[], coherence={}, artifacts=[]
    )
    import hashlib

    from commodity.provenance import canonical_json_bytes
    metadata = {
        "schema_version": 2,
        "experiment_id": prereg["experiment_id"],
        "prereg_sha256": canonical_prereg_sha256(prereg),
        "results_sha256": hashlib.sha256(canonical_json_bytes(results)).hexdigest(),
        "human_disposition": "hold",
        "observed_vs_expected": "Observed evidence was weaker than the preregistered expectation.",
        "disconfirmers_observed": ["sample adequacy"],
        "post_result_literature_snapshot_ref": {
            "path": "research/literature/front-curve-271-post-result-triangulation-v1.json",
            "sha256": hashlib.sha256((ROOT / "research/literature/front-curve-271-post-result-triangulation-v1.json").read_bytes()).hexdigest(),
        },
        "external_triangulation": "Independent literature does not override the governed evidence threshold.",
    }
    verify_interpretation_metadata(metadata, prereg, results)


def test_executive_summary_has_exact_big_picture_arc() -> None:
    sections = {
        "Where this fits": "This tests one storage question inside the natural-gas research programme and helps decide whether fundamentals deserve more scarce confirmation evidence.",
        "Where the idea came from": "The idea comes from storage-market logic, external research, and an unresolved gap in our current evidence map about whether release surprises carry useful information.",
        "What we tested": "We tested whether a point-in-time storage surprise signal improves the frozen next-session forecast relative to the declared simple benchmark.",
        "What we saw": "The run completed under the frozen design and produced a modest benchmark-relative signal, but uncertainty remains material and the evidence does not yet justify a trading claim.",
        "What it means for the bigger picture": "The result raises confidence that storage information is worth continued study without changing the overall programme thesis or granting execution authority.",
        "What next": "The next step is to decide whether genuinely independent confirmation has enough expected information value to justify spending another protected observation window.",
    }
    text = render_executive_summary(sections)
    assert [line[3:] for line in text.splitlines() if line.startswith("## ")] == list(sections)


def test_research_line_requires_evidence_basis_and_stopping_rules() -> None:
    line = {
        "research_line_id": "storage",
        "selection_basis": "high_value_gap",
        "stopping_rules": {
            "negative_evidence": "stop after declared threshold",
            "feasible_power": "hold if inadequate",
            "economic_relevance": "stop if below MEPI",
            "confirmation_capacity": "stop if exhausted",
            "expected_information_value": "stop if low",
        },
    }
    validate_research_line(line)
    line["selection_basis"] = "technical_novelty"
    with pytest.raises(MethodologyError, match="selection_basis"):
        validate_research_line(line)


def test_generated_summary_is_projection_of_bound_interpretation() -> None:
    prereg = sample_prereg()
    results = build_results(
        prereg, run_id="run-1", code={}, data={}, model={}, environment={},
        raw_evidence={"evidence_flags": {}}, verification=[], coherence={}, artifacts=[]
    )
    import hashlib

    from commodity.provenance import canonical_json_bytes
    metadata = {
        "schema_version": 2,
        "experiment_id": prereg["experiment_id"],
        "prereg_sha256": canonical_prereg_sha256(prereg),
        "results_sha256": hashlib.sha256(canonical_json_bytes(results)).hexdigest(),
        "human_disposition": "hold",
        "observed_vs_expected": "Observed evidence was weaker than the preregistered expectation.",
        "disconfirmers_observed": ["sample adequacy"],
        "post_result_literature_snapshot_ref": {
            "path": "research/literature/front-curve-271-post-result-triangulation-v1.json",
            "sha256": hashlib.sha256((ROOT / "research/literature/front-curve-271-post-result-triangulation-v1.json").read_bytes()).hexdigest(),
        },
        "external_triangulation": "Independent literature does not override the governed evidence threshold.",
    }
    bodies = {
        "Where this fits": "This experiment sits inside the natural-gas programme and tests whether storage information deserves more scarce independent confirmation evidence.",
        "Where the idea came from": "The idea came from storage-market economics, external work, and a clear unresolved gap in the programme evidence map.",
        "What we tested": "We tested a frozen point-in-time storage signal against the declared baseline using the preregistered target and horizon.",
        "What we saw": "The run completed correctly, but the evidence remained weak and did not clear the preregistered practical threshold.",
        "What it means for the bigger picture": "This reduces confidence in this exact slice without ruling out the broader storage research line or changing trading authority.",
        "What next": "Hold this slice and spend the next independent observations only if a materially different storage mechanism has higher expected information value.",
    }
    text = "# Interpretation\n\n```json\n" + json.dumps(metadata) + "\n```\n\n" + "\n\n".join(f"## {key}\n{value}" for key, value in bodies.items()) + "\n"
    summary = render_executive_summary_from_interpretation(text, prereg, results)
    assert "# Executive Summary" in summary
    assert "## What next" in summary


def test_confirmatory_execution_requires_exact_frozen_preregistration() -> None:
    from commodity.research_methodology import assert_confirmatory_execution_allowed
    prereg = sample_prereg()
    sha = canonical_prereg_sha256(prereg)
    ledger = register_inference_entry({"schema_version": 1, "programme_id": "commodity-ng", "entries": [], "family_inference": []}, prereg)
    freeze = {
        "schema_version": 1,
        "experiment_id": prereg["experiment_id"],
        "frozen": True,
        "prereg_sha256": sha,
        "programme_context": {"status": "selected_and_feasible", "sha256": "1" * 64},
        "binding": {"preregistration_remote_bound": "verified", "prereg_sha256": sha},
    }
    result = assert_confirmatory_execution_allowed(prereg, freeze, ledger, {"schema_version": 1, "windows": []})
    assert result["allowed"] is True
    freeze["prereg_sha256"] = "0" * 64
    with pytest.raises(MethodologyError, match="freeze prereg identity mismatch"):
        assert_confirmatory_execution_allowed(prereg, freeze, ledger, {"schema_version": 1, "windows": []})



def test_results_method_compliance_fails_on_detected_leakage_and_is_incomplete_on_missing_checks() -> None:
    prereg = sample_prereg()
    failed = build_results(
        prereg, run_id="r-fail", code={}, data={}, model={}, environment={},
        raw_evidence={"evidence_flags": {}},
        verification=[verification_finding("CHECKED", "pit_cutoffs", "Declared PIT cutoff check detected a violation.")],
        coherence={"enhanced_audit_required": False, "audit_completed": True}, artifacts=[]
    )
    assert failed["method_compliance"] == "FAILED"
    incomplete = build_results(
        prereg, run_id="r-inc", code={}, data={}, model={}, environment={},
        raw_evidence={"evidence_flags": {}},
        verification=[verification_finding("CHECKED", "pit_cutoffs", "Declared PIT cutoff check is incomplete.")],
        coherence={"enhanced_audit_required": False, "audit_completed": True}, artifacts=[]
    )
    assert incomplete["method_compliance"] == "INCOMPLETE"


def test_results_require_completed_enhanced_coherence_audit_when_triggered() -> None:
    prereg = sample_prereg()
    prereg["coherence_triggers"] = [
        {"id": "too_good", "direction": "unexpectedly_good", "metric": "benchmark_improvement", "operator": "gte", "threshold": 0.10},
        {"id": "wrong_sign", "direction": "unexpectedly_bad", "metric": "mechanism_sign", "operator": "lte", "threshold": -0.01},
    ]
    raw = numeric_raw_evidence()
    raw["metrics"] = {"benchmark_improvement": 0.12, "mechanism_sign": 1.0}
    results = build_results(
        prereg, run_id="r-coherence", code={}, data={}, model={}, environment={},
        raw_evidence=raw, verification=[], coherence={"audit_completed": False}, artifacts=[]
    )
    assert results["method_compliance"] == "INCOMPLETE"


def test_build_results_cli_requires_exact_execution_gate_inputs() -> None:
    args = build_parser().parse_args([
        "experiment", "build-results", "--prereg", "p.json", "--freeze", "f.json",
        "--run-evidence", "run.json", "--checks", "checks.json", "--output", "r.json",
    ])
    assert str(args.freeze).endswith("f.json")
    assert args.ledger.as_posix().endswith("config/programme_inference_ledger.json")
    assert args.sealed_registry.as_posix().endswith("config/sealed_windows.json")


def test_freeze_cli_carries_sealed_registry_gate() -> None:
    args = build_parser().parse_args([
        "experiment", "freeze", "exp", "--prereg", "p.json", "--tag", "experiment/exp/v1",
        "--output", "freeze.json",
    ])
    assert args.sealed_registry.as_posix().endswith("config/sealed_windows.json")


def test_build_results_rejects_invalid_schema_before_writing_immutable_artifact(tmp_path) -> None:
    prereg = sample_prereg()
    prereg_sha = canonical_prereg_sha256(prereg)
    ledger = register_inference_entry(
        {"schema_version": 1, "programme_id": "commodity-ng", "entries": [], "family_inference": []},
        prereg,
    )
    freeze = {
        "schema_version": 1,
        "experiment_id": prereg["experiment_id"],
        "frozen": True,
        "prereg_sha256": prereg_sha,
        "programme_context": {"status": "selected_and_feasible", "sha256": "1" * 64},
        "binding": {"preregistration_remote_bound": "verified", "prereg_sha256": prereg_sha},
    }
    checks = bounded_leakage_checks(tmp_path)
    run = {
        "run_id": "run-invalid-schema",
        "code": {},
        "data": {},
        "model": {},
        "environment": {},
        "raw_evidence": {"evidence_flags": {}},
        "coherence": {"enhanced_audit_required": False},
    }
    paths = {
        "prereg": tmp_path / "prereg.json",
        "freeze": tmp_path / "freeze.json",
        "ledger": tmp_path / "ledger.json",
        "sealed": tmp_path / "sealed.json",
        "run": tmp_path / "run.json",
        "checks": tmp_path / "checks.json",
        "output": tmp_path / "results.json",
    }
    for key, value in (("prereg", prereg), ("freeze", freeze), ("ledger", ledger), ("sealed", {"schema_version": 1, "windows": []}), ("run", run), ("checks", checks)):
        paths[key].write_text(json.dumps(value), encoding="utf-8")
    args = build_parser().parse_args([
        "experiment", "build-results", "--prereg", str(paths["prereg"]),
        "--freeze", str(paths["freeze"]), "--ledger", str(paths["ledger"]),
        "--sealed-registry", str(paths["sealed"]), "--run-evidence", str(paths["run"]),
        "--checks", str(paths["checks"]), "--output", str(paths["output"]),
    ])
    with pytest.raises(MethodologyError, match="identity|results.schema.json"):
        args.func(args)
    assert not paths["output"].exists()
    assert json.loads(paths["ledger"].read_text(encoding="utf-8"))["entries"][0]["outcome"] is None


def test_inference_outcome_is_recorded_once_and_design_influence_is_monotonic() -> None:
    from commodity.research_methodology import (
        mark_inference_influenced_design,
        record_inference_outcome,
    )

    prereg = sample_prereg()
    ledger = register_inference_entry(
        {"schema_version": 1, "programme_id": "commodity-ng", "entries": [], "family_inference": []},
        prereg,
    )
    closed = record_inference_outcome(ledger, prereg["experiment_id"], "E2:VERIFIED")
    assert closed["entries"][0]["outcome"] == "E2:VERIFIED"
    with pytest.raises(MethodologyError, match="already recorded"):
        record_inference_outcome(closed, prereg["experiment_id"], "E3:VERIFIED")
    influenced = mark_inference_influenced_design(closed, prereg["experiment_id"])
    assert influenced["entries"][0]["influenced_later_design"] is True
