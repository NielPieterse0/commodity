from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from test_research_methodology import sample_prereg

import commodity.research_methodology as methodology


def _results_payload(prereg: dict, **overrides) -> dict:
    raw = {
        "primary": {"effect": 0.15, "p_value": 0.01, "alpha": 0.05, "scientific_mepi": 0.10},
        "robustness": {"checks": [
            {"name": "rmse_vs_baseline", "value": 0.12, "operator": "gte", "threshold": 0.10},
            {"name": "mae_vs_baseline", "value": 0.11, "operator": "gte", "threshold": 0.10},
        ]},
        "economics": {"net_effect": 0.09, "economic_mepi": 0.08},
        "replication": {"independent_results": [{"effect": 0.14, "p_value": 0.02, "alpha": 0.05, "scientific_mepi": 0.10}]},
        "programme": {"adjusted_p_value": 0.03, "alpha": 0.05},
        "metrics": {"benchmark_improvement": 0.12, "mechanism_sign": 1.0, "concentration_share": 0.20},
    }
    payload = {
        "schema_version": 1,
        "experiment_id": prereg["experiment_id"],
        "run_id": "run-260",
        "prereg_sha256": methodology.canonical_prereg_sha256(prereg),
        "code": {"commit_sha": "abc", "working_tree_dirty": False},
        "data": {"dataset_id": "d1", "vintage_id": "v1", "split_id": "split-1"},
        "features": {"definition_id": "storage-v1", "preprocessing_id": "pit-v1"},
        "model": {"family": "baseline", "configuration_id": "ridge-v1", "checkpoint_id": None},
        "environment": {"runtime": "python", "runtime_version": "3.11", "dependency_lock_sha256": "a" * 64, "hardware": {}, "tolerance_policy": {}},
        "raw_evidence": raw,
        "verification": [],
        "method_compliance": "VERIFIED",
        "scientific_evidence": "E6",
        "coherence": {"enhanced_audit_required": False, "triggered": [], "audit_completed": True},
        "family_inference": None,
        "artifacts": [],
    }
    payload.update(overrides)
    return payload


def test_preregistration_runs_json_schema_before_semantic_checks() -> None:
    prereg = sample_prereg()
    del prereg["outside_scope"]
    with pytest.raises(methodology.MethodologyError, match="prereg.schema.json"):
        methodology.verify_preregistration(prereg)


def test_big_picture_orientation_is_mandatory_before_freeze() -> None:
    prereg = sample_prereg()
    del prereg["orientation"]
    with pytest.raises(methodology.MethodologyError, match="orientation"):
        methodology.verify_preregistration(prereg)


def test_evidence_level_is_derived_from_numeric_evidence_not_flags() -> None:
    prereg = sample_prereg()
    results = _results_payload(prereg)
    assert methodology.derive_evidence_level(results["raw_evidence"]) == "E6"
    results["raw_evidence"]["evidence_flags"] = {"programme_level": True}
    results["raw_evidence"]["primary"]["p_value"] = 0.50
    assert methodology.derive_evidence_level(results["raw_evidence"]) == "E1"


def test_results_reject_dataset_split_feature_and_model_identity_mismatch() -> None:
    prereg = sample_prereg()
    results = _results_payload(prereg)
    methodology.verify_results(prereg, results)
    for section, key, wrong in (
        ("data", "dataset_id", "wrong-dataset"),
        ("data", "split_id", "wrong-split"),
        ("features", "definition_id", "wrong-features"),
        ("model", "family", "wrong-family"),
    ):
        broken = json.loads(json.dumps(results))
        broken[section][key] = wrong
        with pytest.raises(methodology.MethodologyError, match="identity"):
            methodology.verify_results(prereg, broken)


def _bounded_leakage_checks(root: Path) -> dict:
    names = (
        "pit_cutoffs", "vintage_timing", "roll_contract_identity", "release_calendar",
        "overlapping_horizons", "event_windows", "join_cardinality", "feature_availability",
    )
    checks = {}
    for name in names:
        path = root / f"{name}.json"
        path.write_text('{"observed": 0}\n', encoding="utf-8")
        checks[name] = {"operator": "eq", "expected": 0, "evidence_path": str(path), "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return checks


def test_leakage_audit_rejects_self_asserted_booleans_and_evaluates_evidence(tmp_path: Path) -> None:
    valid = _bounded_leakage_checks(tmp_path)
    booleans = {name: True for name in valid}
    with pytest.raises(methodology.MethodologyError, match="evidence"):
        methodology.audit_leakage(booleans)
    findings = methodology.audit_leakage(valid)
    assert len(findings) == 8
    assert all("passed" in item["message"].lower() for item in findings)


def test_programme_context_binds_scan_and_mepi() -> None:
    prereg = sample_prereg()
    evidence = {
        "schema_version": 1,
        "programme_id": prereg["programme_id"],
        "current_scan_id": "programme-evidence-map-2026-08-29",
        "research_lines": [{
            "research_line_id": prereg["research_line_id"], "status": "selected",
            "selection_basis": "high_value_gap", "evidence_refs": ["scan:storage"],
            "stopping_rules": {"negative_evidence": "stop", "feasible_power": "hold", "economic_relevance": "stop", "confirmation_capacity": "stop", "expected_information_value": "stop"},
        }],
        "feasibility_map": [{
            "target": "next_session_return", "horizon": "1_session", "information_family": "storage",
            "scientific_mepi": 0.10, "economic_mepi": 0.08, "feasibility": "go",
            "market_implied_benchmark_required": True,
        }],
    }
    with pytest.raises(methodology.MethodologyError, match="market-implied"):
        methodology.validate_programme_context(prereg, evidence)
    prereg["evaluation"]["benchmarks"].append({"id": "market", "type": "market_implied", "interpretation": "governed comparator"})
    assert methodology.validate_programme_context(prereg, evidence)["status"] == "selected_and_feasible"
    prereg["mepi"]["scientific_mepi"]["value"] = 0.11
    prereg["mepi"]["scientific_mepi"]["inputs"]["minimum_effect"] = 0.11
    with pytest.raises(methodology.MethodologyError, match="MEPI"):
        methodology.validate_programme_context(prereg, evidence)


def test_sealed_window_binds_exact_protected_identity_and_claim_usage() -> None:
    prereg = sample_prereg()
    prereg["sealed_window"] = {
        "sealed_window_id": "sw-1", "use": "confirmatory", "dataset_id": "d1",
        "start": "2026-09-01", "end": "2026-09-30", "content_sha256": "3" * 64,
    }
    registry = {"schema_version": 1, "windows": [{
        "sealed_window_id": "sw-1", "dataset_id": "d1", "start": "2026-09-01", "end": "2026-09-30",
        "content_sha256": "3" * 64, "eligibility": "eligible", "permitted_openings": 1, "openings": [],
    }]}
    assert methodology.validate_sealed_policy(prereg, registry)["status"] == "eligible"
    prereg["sealed_window"]["content_sha256"] = "4" * 64
    with pytest.raises(methodology.MethodologyError, match="identity"):
        methodology.validate_sealed_policy(prereg, registry)


def test_coherence_triggers_are_derived_from_observed_metrics() -> None:
    prereg = sample_prereg()
    prereg["coherence_triggers"] = [
        {"id": "too_good", "direction": "unexpectedly_good", "metric": "benchmark_improvement", "operator": "gte", "threshold": 0.10},
        {"id": "wrong_sign", "direction": "unexpectedly_bad", "metric": "mechanism_sign", "operator": "lte", "threshold": -0.01},
    ]
    observed = {"benchmark_improvement": 0.12, "mechanism_sign": 1.0}
    result = methodology.derive_coherence(prereg, observed)
    assert result["triggered"] == ["too_good"]
    assert result["enhanced_audit_required"] is True


def test_family_inference_is_bound_to_declared_candidate_family() -> None:
    prereg = sample_prereg()
    prereg["evaluation"]["programme_inference_procedure"] = "white_reality_check"
    raw = _results_payload(prereg)["raw_evidence"]
    raw["family_inference"] = {
        "procedure": "white_reality_check", "bootstrap_samples": 100, "block_length": 2, "seed": 7,
        "loss_differentials": {"baseline": [0.3, 0.2, 0.4, 0.3], "zero-return": [0.0, 0.1, -0.1, 0.0]},
    }
    record = methodology.run_family_inference(prereg, raw)
    assert record["family_id"] == prereg["evaluation"]["statistical_family"]
    raw["family_inference"]["loss_differentials"]["undeclared"] = [0.1, 0.1, 0.1, 0.1]
    with pytest.raises(methodology.MethodologyError, match="candidate family"):
        methodology.run_family_inference(prereg, raw)


def test_frozen_reference_resolves_exact_repo_artifact(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    artifact = root / "research" / "evidence-scans" / "scan.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"scan_id":"scan-1"}\n', encoding="utf-8")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    ref = {"path": "research/evidence-scans/scan.json", "sha256": sha, "scan_id": "scan-1"}
    assert methodology.verify_reference_artifact(ref, root)["sha256"] == sha
    ref["sha256"] = "0" * 64
    with pytest.raises(methodology.MethodologyError, match="hash"):
        methodology.verify_reference_artifact(ref, root)


def test_programme_evidence_map_updates_after_completed_experiment() -> None:
    prereg = sample_prereg()
    evidence = {
        "schema_version": 1, "programme_id": prereg["programme_id"], "current_scan_id": "scan-1",
        "research_lines": [{"research_line_id": prereg["research_line_id"], "status": "selected", "selection_basis": "high_value_gap", "evidence_refs": [], "stopping_rules": {"negative_evidence": "stop", "feasible_power": "hold", "economic_relevance": "stop", "confirmation_capacity": "stop", "expected_information_value": "stop"}}],
        "feasibility_map": [],
    }
    results = _results_payload(prereg)
    updated = methodology.update_programme_evidence_map(evidence, prereg, results, new_scan_id="scan-2")
    assert updated["current_scan_id"] == "scan-2"
    history = updated["research_lines"][0]["experiment_history"]
    assert history[-1]["experiment_id"] == prereg["experiment_id"]
    assert history[-1]["scientific_evidence"] == "E6"


def test_successor_lineage_requires_exact_predecessor_and_reason() -> None:
    prereg = sample_prereg()
    prereg["lineage"] = {"supersedes_prereg_sha256": "a" * 64, "supersedes_prereg_path": "research/experiments/old/prereg.json", "amendment_reason": "change target definition"}
    methodology.verify_lineage(prereg, known_predecessor_sha256="a" * 64)
    with pytest.raises(methodology.MethodologyError, match="predecessor"):
        methodology.verify_lineage(prereg, known_predecessor_sha256="b" * 64)
    prereg["lineage"]["amendment_reason"] = ""
    with pytest.raises(methodology.MethodologyError, match="reason"):
        methodology.verify_lineage(prereg, known_predecessor_sha256="a" * 64)


def test_reproduction_can_execute_declared_local_command(tmp_path: Path) -> None:
    output = tmp_path / "candidate.json"
    script = tmp_path / "emit.py"
    script.write_text(
        "import json,sys; json.dump({'dataset_id':'d1','prediction_id':'p1','result_id':'r1','values':{'rmse':1.0}}, open(sys.argv[1],'w'))",
        encoding="utf-8",
    )
    reference = {"dataset_id": "d1", "prediction_id": "p1", "result_id": "r1", "values": {"rmse": 1.0}}
    result = methodology.execute_reproduction(
        ["python", str(script), str(output)], output, reference, {"absolute": 0.0, "relative": 0.0}, cwd=tmp_path
    )
    assert result["status"] == "passed"
    assert result["executed"] is True


def test_completed_experiment_requires_executive_summary(tmp_path: Path) -> None:
    exp = tmp_path / "exp"
    exp.mkdir()
    for name in ("prereg.json", "results.json", "interpretation.md", "record.json"):
        (exp / name).write_text("{}\n", encoding="utf-8")
    with pytest.raises(methodology.MethodologyError, match="executive-summary"):
        methodology.verify_completion_artifacts(exp)
    (exp / "executive-summary.md").write_text("# Executive Summary\n", encoding="utf-8")
    assert methodology.verify_completion_artifacts(exp)["status"] == "complete"


def test_methodology_captures_agreed_finance_econometrics_canon() -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "research-methodology.md").read_text(encoding="utf-8")
    for required in ("White", "Hansen", "Model Confidence Set", "Harvey", "Newey-West"):
        assert required in text


def test_remote_binding_requires_cryptographic_tag_verification(monkeypatch, tmp_path: Path) -> None:
    prereg = sample_prereg()
    prereg_path = tmp_path / "prereg.json"
    prereg_path.write_text(json.dumps(prereg), encoding="utf-8")
    responses = {
        ("status", "--porcelain"): "",
        ("show", "HEAD:prereg.json"): json.dumps(prereg),
        ("rev-parse", "HEAD"): "a" * 40,
        ("rev-list", "-n", "1", "tag-1"): "a" * 40,
    }
    monkeypatch.setattr(methodology, "_git_text", lambda _root, *args: responses[args])
    class Result:
        returncode = 1
        stdout = ""
        stderr = "bad signature"
    monkeypatch.setattr(methodology.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(methodology.MethodologyError, match="signature"):
        methodology.verify_remote_prereg_binding(tmp_path, prereg_path, "tag-1")


def test_synthetic_confirmatory_lifecycle_closes_big_picture_to_programme_update(tmp_path: Path) -> None:
    prereg = sample_prereg()
    scan = tmp_path / "scan.json"
    literature = tmp_path / "literature.json"
    scan.write_text('{"scan_id":"programme-evidence-map-2026-08-29"}\n', encoding="utf-8")
    literature.write_text('{"snapshot_id":"lit-1"}\n', encoding="utf-8")
    prereg["evidence_scan_ref"] = {"path": "scan.json", "sha256": hashlib.sha256(scan.read_bytes()).hexdigest(), "scan_id": "programme-evidence-map-2026-08-29"}
    prereg["literature_snapshot_ref"] = {"path": "literature.json", "sha256": hashlib.sha256(literature.read_bytes()).hexdigest()}
    methodology.verify_preregistration(prereg)
    methodology.verify_reference_artifact(prereg["evidence_scan_ref"], tmp_path)
    methodology.verify_reference_artifact(prereg["literature_snapshot_ref"], tmp_path)
    programme = {
        "schema_version": 1, "programme_id": prereg["programme_id"], "current_scan_id": "programme-evidence-map-2026-08-29",
        "research_lines": [{"research_line_id": prereg["research_line_id"], "status": "selected", "selection_basis": "high_value_gap", "evidence_refs": ["scan"], "stopping_rules": {"negative_evidence": "stop", "feasible_power": "hold", "economic_relevance": "stop", "confirmation_capacity": "stop", "expected_information_value": "stop"}, "experiment_history": []}],
        "feasibility_map": [{"target": "next_session_return", "horizon": "1_session", "information_family": "storage", "scientific_mepi": 0.10, "economic_mepi": 0.08, "feasibility": "go", "market_implied_benchmark_required": False}],
    }
    assert methodology.validate_programme_context(prereg, programme)["status"] == "selected_and_feasible"
    ledger = methodology.register_inference_entry({"schema_version": 1, "programme_id": prereg["programme_id"], "entries": [], "family_inference": []}, prereg)
    sha = methodology.canonical_prereg_sha256(prereg)
    freeze = {"frozen": True, "experiment_id": prereg["experiment_id"], "prereg_sha256": sha, "programme_context": {"status": "selected_and_feasible", "sha256": "a" * 64}, "binding": {"preregistration_remote_bound": "verified", "prereg_sha256": sha}}
    assert methodology.assert_confirmatory_execution_allowed(prereg, freeze, ledger, {"schema_version": 1, "windows": []})["allowed"] is True
    raw = _results_payload(prereg)["raw_evidence"]
    raw["family_inference"] = {"procedure": "benjamini_hochberg", "alpha": 0.05, "pvalues": {"baseline": 0.01, "zero-return": 0.30}}
    results = methodology.build_results(
        prereg, run_id="synthetic-run", code={"commit_sha": "abc", "working_tree_dirty": False},
        data={"dataset_id": "d1", "vintage_id": "v1", "split_id": "split-1"},
        model={"family": "baseline", "configuration_id": "ridge-v1", "checkpoint_id": None}, environment={},
        raw_evidence=raw, verification=methodology.audit_leakage(_bounded_leakage_checks(tmp_path)), coherence={"audit_completed": True}, artifacts=[]
    )
    assert methodology.verify_results(prereg, results)["status"] == "verified"
    ledger = methodology.record_family_inference(ledger, results["family_inference"])
    ledger = methodology.record_inference_outcome(ledger, prereg["experiment_id"], f"{results['scientific_evidence']}:{results['method_compliance']}")
    assert ledger["family_inference"]
    updated = methodology.update_programme_evidence_map(programme, prereg, results, new_scan_id="scan-after-synthetic")
    assert updated["research_lines"][0]["experiment_history"][-1]["experiment_id"] == prereg["experiment_id"]
    assert updated["current_scan_id"] == "scan-after-synthetic"
