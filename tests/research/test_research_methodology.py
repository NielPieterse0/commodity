import hashlib
import json
from pathlib import Path

import pytest

from commodity.research_methodology import (
    MethodologyError,
    canonical_prereg_sha256,
    classify_evidence,
    compute_effective_information,
    verify_power,
    verify_preregistration,
    verify_sealed_access,
)

ROOT = Path(__file__).resolve().parents[2]


def sample_prereg() -> dict:
    literature_path = ROOT / "tests" / "fixtures" / "literature-snapshot.json"
    literature = json.loads(literature_path.read_text(encoding="utf-8"))
    literature_sha = hashlib.sha256(literature_path.read_bytes()).hexdigest()
    scan_rel = "research/programmes/001-commodity-natural-gas/evidence-scans/programme-evidence-map-2026-08-29.json"
    scan_path = ROOT / scan_rel
    scan_sha = hashlib.sha256(scan_path.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "zoom_level": "L3",
        "experiment_id": "001-test-storage-v1",
        "programme_id": "001-commodity-natural-gas",
        "research_line_id": "008-next-defensible-edge",
        "slice_id": "slice-a",
        "evidence_scan_ref": {"path": scan_rel, "sha256": scan_sha, "scan_id": "programme-evidence-map-2026-08-29"},
        "literature_snapshot_ref": {"path": "tests/fixtures/literature-snapshot.json", "sha256": literature_sha},
        "orientation": {
            "big_picture_ref": "docs/big-picture.md",
            "where_this_fits": "Tests whether storage information deserves scarce confirmation evidence.",
            "origin_refs": ["programme-evidence-map-2026-08-29"],
            "programme_question": "Can storage information improve defensible natural-gas forecasts?",
        },
        "parent_question": "Does storage information improve next-session forecasting?",
        "uncertainty_reduced": "Whether the storage signal clears practical relevance.",
        "outside_scope": ["live trading"],
        "mechanism": "Storage surprises may shift near-term scarcity expectations.",
        "hypotheses": {"h0": "No useful benchmark-relative effect.", "h1": "Useful benchmark-relative effect."},
        "expectations": {
            "expected": literature["expected_observations"],
            "disconfirming": literature["disconfirming_observations"],
        },
        "post_result_triangulation": {"required": True, "independent_search_required": True},
        "mepi": {
            "scientific_mepi": {"formula": "absolute", "inputs": {"minimum_effect": 0.10}, "value": 0.10},
            "economic_mepi": {"formula": "cost_adjusted", "inputs": {"minimum_net_effect": 0.05, "cost": 0.03}, "value": 0.08},
        },
        "forecast": {
            "target": "next_session_return",
            "horizon": "1_session",
            "prediction_timestamp_semantics": "after_close",
            "target_timestamp_semantics": "next_close",
            "information_cutoff_semantics": "known_by_prediction_time",
        },
        "datasets": [{"id": "d1", "vintage": "v1", "split_id": "split-1", "role": "research_oos"}],
        "dependence": {"method": "ar1", "raw_n": 400, "parameters": {"rho": 0.2}},
        "power": {"method": "normal_effect_size", "alpha": 0.05, "target_power": 0.8, "minimum_effect": 0.18},
        "features": {"definition_id": "storage-v1", "preprocessing_id": "pit-v1", "information_families": ["storage"]},
        "model": {"family": "baseline", "configuration_id": "ridge-v1", "training_rules": "frozen"},
        "evaluation": {
            "claim_scope": "forecasting",
            "market_implied_relevant": False,
            "primary_metric": "rmse",
            "secondary_metrics": ["mae"],
            "inference_procedure": "moving_block_bootstrap",
            "programme_inference_procedure": "benjamini_hochberg",
            "statistical_family": "storage-return-v1",
            "candidate_family": ["baseline", "zero-return"],
            "benchmarks": [{"id": "zero-return", "type": "naive", "interpretation": "simple comparator"}],
        },
        "inference_ledger_entry_id": "inf-001",
        "sealed_window": {"sealed_window_id": None, "use": "none"},
        "coherence_triggers": [
            {"id": "implausibly_large_benchmark_improvement", "direction": "unexpectedly_good", "metric": "benchmark_improvement", "operator": "gte", "threshold": 0.50},
            {"id": "mechanism_sign_conflict", "direction": "unexpectedly_bad", "metric": "mechanism_sign", "operator": "lte", "threshold": -0.01},
            {"id": "few_observation_concentration", "direction": "both", "metric": "concentration_share", "operator": "gte", "threshold": 0.80},
        ],
        "outcome_logic": {"success": "primary clears MEPI and inference gate", "failure": "does not clear", "inconclusive": "power or checks incomplete"},
        "permitted_human_dispositions": ["advance", "replicate", "refine", "branch", "hold", "stop"],
        "reproduction": {
            "mode": "logical",
            "tolerance": {"absolute": 1e-9, "relative": 1e-9},
            "lockfile_identity": "pyproject-lock:test",
            "runtime_identity": "python:test-runtime",
            "model_checkpoint_identity": "ridge-v1:none",
            "hardware_sensitive_facts": [],
        },
        "lineage": {
            "programme_ref": "research/programmes/001-commodity-natural-gas/programme.json",
            "research_line_ref": "research/programmes/001-commodity-natural-gas/lines/008-next-defensible-edge/line.json",
            "predecessor_experiment_id": None,
            "successor_experiment_ids": [],
            "supersedes_prereg_sha256": None,
            "supersedes_prereg_path": "",
            "amendment_reason": "",
            "exploratory_ancestry": [],
        },
    }


def test_canonical_prereg_identity_ignores_key_order() -> None:
    prereg = sample_prereg()
    reordered = json.loads(json.dumps(prereg, sort_keys=True))
    assert canonical_prereg_sha256(prereg) == canonical_prereg_sha256(reordered)


def test_mepi_is_recomputed_not_trusted() -> None:
    prereg = sample_prereg()
    prereg["mepi"]["economic_mepi"]["value"] = 999
    with pytest.raises(MethodologyError, match="economic_mepi"):
        verify_preregistration(prereg)


def test_effective_information_is_generated_from_dependence() -> None:
    result = compute_effective_information(sample_prereg()["dependence"])
    assert result["raw_n"] == 400
    assert result["effective_information"] == pytest.approx(400 * 0.8 / 1.2)


def test_power_gate_uses_generated_effective_information() -> None:
    result = verify_power(sample_prereg())
    assert result["status"] == "passed"
    assert result["detectable_effect"] < 0.18


def test_prereg_cannot_contain_results_or_own_hash() -> None:
    for forbidden in ("results", "decision", "evidence_level", "prereg_sha256"):
        prereg = sample_prereg()
        prereg[forbidden] = {}
        with pytest.raises(MethodologyError, match="forbidden"):
            verify_preregistration(prereg)


def test_exploration_cannot_open_sealed_confirmation() -> None:
    with pytest.raises(MethodologyError, match="exploratory"):
        verify_sealed_access(
            {"sealed_window_id": "sw-1", "eligibility": "eligible", "permitted_openings": 1, "openings": []},
            use="exploratory",
        )


def test_evidence_level_is_machine_derived() -> None:
    assert classify_evidence({"interesting_signal": False}) == "E0"
    assert classify_evidence({"interesting_signal": True}) == "E1"
    assert classify_evidence({"interesting_signal": True, "statistical_support": True}) == "E2"
    assert classify_evidence({"interesting_signal": True, "statistical_support": True, "robust_forecasting": True, "economic_relevance": True, "replicated": True, "programme_level": True}) == "E6"


def test_opposite_sign_replication_does_not_promote_evidence() -> None:
    from commodity.research_methodology import derive_evidence_level

    raw = {
        "primary": {"effect": 0.2, "p_value": 0.01, "alpha": 0.05, "scientific_mepi": 0.1},
        "robustness": {"checks": [
            {"value": 1.0, "operator": "gte", "threshold": 0.5},
            {"value": 1.0, "operator": "gte", "threshold": 0.5},
        ]},
        "economics": {"net_effect": 0.2, "economic_mepi": 0.1},
        "replication": {"independent_results": [
            {"effect": -0.2, "p_value": 0.01, "alpha": 0.05, "scientific_mepi": 0.1}
        ]},
        "programme": {"adjusted_p_value": 0.01, "alpha": 0.05},
    }
    assert derive_evidence_level(raw) == "E4"


def test_governed_research_preflight_fails_when_canonical_registry_is_missing(monkeypatch, tmp_path) -> None:
    import commodity.research_lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "_root", lambda: tmp_path)
    with pytest.raises(MethodologyError, match="canonical research revisit-trigger registry is missing"):
        lifecycle.assert_governed_research_preflight("001-commodity-natural-gas")


def test_repository_has_new_methodology_contracts() -> None:
    expected = [
        "prereg.schema.json",
        "results.schema.json",
        "programme_inference.schema.json",
        "sealed_windows.schema.json",
        "exploratory_run.schema.json",
    ]
    for name in expected:
        assert (ROOT / "contracts" / name).exists(), name


def test_authority_map_names_new_future_experiment_owners() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "contracts/prereg.schema.json" in agents
    assert "research/programmes/<programme-id>/inference-ledger.json" in agents
    assert "sealed-windows.json" in agents
    assert "Historical material is evidence or context only" in agents


def test_future_experiment_artifact_directory_is_tracked_authority() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "research/programmes/<programme-id>/lines/<research-line-id>/experiments/<experiment-id>/" in agents
    programme = json.loads((ROOT / "research/programmes/001-commodity-natural-gas/programme.json").read_text(encoding="utf-8"))
    for ref in programme["line_refs"]:
        assert (ROOT / ref["path"]).parent.joinpath("experiments", ".gitkeep").exists()


def test_confirmatory_sealed_policy_must_resolve_eligible_window() -> None:
    from commodity.research_methodology import validate_sealed_policy

    prereg = sample_prereg()
    prereg["sealed_window"] = {"sealed_window_id": "sw-1", "use": "confirmatory"}
    registry = {"schema_version": 1, "windows": [
        {"sealed_window_id": "sw-1", "eligibility": "eligible", "permitted_openings": 1, "openings": []}
    ]}
    assert validate_sealed_policy(prereg, registry)["status"] == "eligible"
    registry["windows"][0]["eligibility"] = "exhausted"
    with pytest.raises(MethodologyError, match="not eligible"):
        validate_sealed_policy(prereg, registry)


def test_remote_prereg_binding_requires_clean_repository(monkeypatch, tmp_path) -> None:
    import commodity.research_methodology as methodology

    monkeypatch.setattr(methodology, "_git_text", lambda _root, *args: " M research/programmes/001-commodity-natural-gas/inference-ledger.json" if args[:2] == ("status", "--porcelain") else "")
    with pytest.raises(MethodologyError, match="clean repository"):
        methodology._require_clean_repository(tmp_path)


def test_freeze_programme_context_requires_selected_line_and_go_feasibility() -> None:
    from commodity.research_methodology import validate_programme_context

    prereg = sample_prereg()
    evidence = {
        "schema_version": 2, "programme_id": "001-commodity-natural-gas",
        "current_scan_id": "programme-evidence-map-2026-08-29",
        "research_line_refs": [{
            "research_line_id": "008-next-defensible-edge",
            "path": "research/programmes/001-commodity-natural-gas/lines/008-next-defensible-edge/line.json",
        }],
        "feasibility_map": [{
            "target": "next_session_return", "horizon": "1_session",
            "information_family": "storage", "feasibility": "go",
        }],
    }
    assert validate_programme_context(prereg, evidence)["status"] == "selected_and_feasible"
    evidence["feasibility_map"][0]["feasibility"] = "hold"
    with pytest.raises(MethodologyError, match="feasibility"):
        validate_programme_context(prereg, evidence)
