import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "docs" / "development" / "v2-activation-preregistration"
LEDGER = ROOT / "artifacts" / "research-metrics" / "longitudinal-ledger.json"
CANDIDATES = ROOT / "config" / "experiment_candidates.json"
PHASE_D = ROOT / "config" / "phase_d_evaluation.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _contract() -> dict:
    return _load(V2 / "activation-contract.json")


def test_v2_contract_is_refrozen_and_fail_closed_pending_successor_142() -> None:
    contract = _contract()
    assert contract["status"] == "frozen_pending_independent_142_audit"
    assert contract["execution_authorized"] is False
    assert contract["hard_dependencies"]["78"]["satisfied"] is True
    assert contract["hard_dependencies"]["15"]["satisfied"] is True
    assert contract["hard_dependencies"]["15"]["current_state"] == "closed_reconciled"
    gate = contract["empirical_release_gate"]
    assert gate["88"]["historical_issue"] == 88
    assert gate["88"]["successor_issue"] == 142
    assert gate["88"]["satisfied"] is False
    assert gate["88"]["current_state"] == "successor_142_pending_reaudit"
    assert gate["88"]["required_state"] == "independent_activation_audit_passed"
    assert gate["release_state"] == {"82": True, "83": False, "84": False, "85": False}


def test_kronos_target_interface_is_explicit_and_frozen() -> None:
    contract = _contract()
    target = contract["frozen_execution_rules"]["kronos_target_interface"]
    assert target == {
        "model_forecast_field": "close",
        "prediction_mapping": "log(predicted_close_next / observed_close_at_cutoff)",
        "prediction_role": "uncalibrated_close_return_proxy_for_target_ret_1",
        "actual_target": "selected_contract_settlement_log_return",
        "settlement_reconstruction_permitted": False,
        "calibration_permitted": False,
    }


def test_v2_contract_inherits_landed_78_metric_policy_exactly() -> None:
    contract = _contract()
    ledger = _load(LEDGER)
    binding = contract["longitudinal_metrics_binding"]
    policies = ledger["comparison_policy"]["metric_policies"]
    required = [name for name, policy in policies.items() if policy["required"]]
    optional = [name for name, policy in policies.items() if not policy["required"]]
    assert binding["policy_id"] == ledger["comparison_policy"]["policy_id"]
    assert binding["comparison_kinds"] == ["previous_stage", "best_comparable"]
    assert binding["required_metric_ids"] == required
    assert binding["optional_metric_ids"] == optional
    assert required == ["model_rmse", "baseline_rmse", "rmse_improvement_vs_baseline"]


def test_frozen_v1_control_matches_final_phase_d_context() -> None:
    contract = _contract()
    ledger = _load(LEDGER)
    phase_d = next(
        stage for stage in ledger["stages"]
        if stage["stage_id"] == "phase-d-full-v1-hist-gb"
    )
    control = contract["frozen_v1_control"]
    ctx = phase_d["context"]
    frozen = control["context_identity"]
    assert control["context_stage_id"] == phase_d["stage_id"]
    assert control["baseline_id"] == ctx["evaluation"]["baseline_id"]
    assert control["baseline_configuration_id"] == ctx["evaluation"]["baseline_configuration_id"]
    assert control["reference_rmse"] == phase_d["metrics"]["baseline_rmse"]["value"]
    assert frozen["dataset_id"] == ctx["dataset"]["dataset_id"]
    assert frozen["data_vintage_id"] == ctx["dataset"]["freeze_id"]
    assert frozen["split_id"] == ctx["evaluation"]["split_id"]
    assert frozen["availability_rule_id"] == ctx["availability"]["rule_id"]


def test_frozen_candidate_registry_matches_contract_identity_and_digest() -> None:
    contract = _contract()
    candidates = _load(CANDIDATES)
    normalized = CANDIDATES.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(normalized).hexdigest()
    frozen = contract["frozen_execution_rules"]["candidate_ids"]
    assert digest == contract["freeze"]["candidate_config_sha256"]
    assert candidates["freeze"]["state"] == "frozen"
    assert candidates["freeze"]["execution_authorized"] is False
    assert frozen == {
        "82": "v2-82-kronos-only",
        "83": "v2-83-indicators-only",
        "84": "v2-84-kronos-indicator-fusion",
    }
    assert candidates["candidates"][frozen["82"]]["execution_authorized"] is True
    assert candidates["candidates"][frozen["83"]]["execution_authorized"] is False
    assert candidates["candidates"][frozen["84"]]["execution_authorized"] is False


def test_frozen_statistical_and_cost_rules_are_complete_and_predeclared() -> None:
    contract = _contract()
    phase_d = _load(PHASE_D)
    rules = contract["frozen_execution_rules"]
    significance = rules["uncertainty_significance_rule"]
    multiplicity = rules["multiple_testing_rule"]
    robustness = rules["robustness_rule"]
    assert significance["method"] == phase_d["significance"]["method"]
    assert significance["block_size"] == phase_d["significance"]["block_size"]
    assert significance["resamples"] == phase_d["significance"]["resamples"]
    assert significance["confidence"] == phase_d["significance"]["confidence"]
    assert significance["seed"] == phase_d["significance"]["seed"]
    assert multiplicity["method"] == phase_d["significance"]["multiple_testing"]
    assert multiplicity["max_adjusted_p_value"] == phase_d["robustness"]["max_adjusted_p_value"]
    assert robustness["minimum_positive_periods"] == phase_d["robustness"]["minimum_positive_periods"]
    assert robustness["minimum_positive_regimes"] == phase_d["robustness"]["minimum_positive_regimes"]
    assert rules["compute_cost_cap"]["paid_compute_usd"] == 0
    assert rules["data_cost_cap"]["new_data_acquisition_usd"] == 0
    assert rules["seed_semantics"]["seed_search_permitted"] is False


def test_agent2_freeze_contains_no_agent3_audit_artifacts_or_open_15_gate() -> None:
    assert not (V2 / "activation-contract-draft.json").exists()
    assert not (V2 / "inherited-hypothesis-dispositions.json").exists()
    assert not (V2 / "review-checklist.md").exists()
    text = (V2 / "spec.md").read_text(encoding="utf-8")
    contract = (V2 / "activation-contract.json").read_text(encoding="utf-8")
    assert "#15 itself remains open" not in text
    assert "while #15 remains open" not in text
    assert '"current_state": "open"' not in contract
