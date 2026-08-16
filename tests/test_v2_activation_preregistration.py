import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "docs" / "development" / "v2-activation-preregistration"
LEDGER = ROOT / "artifacts" / "research-metrics" / "longitudinal-ledger.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _contract() -> dict:
    return _load(V2 / "activation-contract-draft.json")


def _ledger() -> dict:
    return _load(LEDGER)


def test_v2_contract_is_agent2_preparation_only_and_blocked_on_15() -> None:
    contract = _contract()
    assert contract["status"] == "prepared_78_resolved_blocked_on_15_not_frozen"
    assert contract["execution_authorized"] is False
    assert contract["hard_dependencies"]["78"]["satisfied"] is True
    assert contract["hard_dependencies"]["15"]["satisfied"] is False
    assert contract["longitudinal_metrics_binding"]["primary_v1_control"]["frozen_stage_id"] is None
    assert contract["longitudinal_metrics_binding"]["primary_v1_control"]["freeze_allowed"] is False
    assert all(
        released is False
        for released in contract["release_state"].values()
        if isinstance(released, bool)
    )


def test_v2_contract_inherits_landed_78_metric_policy_exactly() -> None:
    contract = _contract()
    ledger = _ledger()
    binding = contract["longitudinal_metrics_binding"]
    policies = ledger["comparison_policy"]["metric_policies"]
    required = [name for name, policy in policies.items() if policy["required"]]
    optional = [name for name, policy in policies.items() if not policy["required"]]

    assert binding["authority_contract"] == "contracts/research_metrics.schema.json"
    assert binding["authority_ledger"] == "artifacts/research-metrics/longitudinal-ledger.json"
    assert binding["comparison_kinds"] == ["previous_stage", "best_comparable"]
    assert binding["integration_source"]["landing_pr"] == 95
    assert binding["integration_source"]["policy_id"] == ledger["comparison_policy"]["policy_id"]
    assert binding["metric_ids"]["required"]["resolved_ids"] == required
    assert binding["metric_ids"]["required"]["policies"] == {name: policies[name] for name in required}
    assert binding["metric_ids"]["optional"]["resolved_ids"] == optional
    assert binding["metric_ids"]["optional"]["policies"] == {name: policies[name] for name in optional}
    assert required == ["model_rmse", "baseline_rmse", "rmse_improvement_vs_baseline"]


def test_v2_contract_resolves_phase_d_hard_context_without_freezing_v2() -> None:
    contract = _contract()
    ledger = _ledger()
    phase_d = next(stage for stage in ledger["stages"] if stage["stage_id"] == "phase-d-full-v1-hist-gb")
    ctx = phase_d["context"]
    resolved = contract["resolved_authoritative_values"]

    assert resolved["forecast_target"] == ctx["forecast"]["target"]
    assert resolved["forecast_horizon"] == ctx["forecast"]["horizon"]
    assert resolved["dataset_id"] == ctx["dataset"]["dataset_id"]
    assert resolved["data_vintage_id"] == ctx["dataset"]["freeze_id"]
    assert resolved["dataset_sha256"] == ctx["dataset"]["dataset_sha256"]
    assert resolved["protocol_id"] == ctx["evaluation"]["protocol_id"]
    assert resolved["split_id"] == ctx["evaluation"]["split_id"]
    assert resolved["baseline_id"] == ctx["evaluation"]["baseline_id"]
    assert resolved["availability_rule_id"] == ctx["availability"]["rule_id"]
    assert resolved["planned_primary_v1_control_stage_id"] == phase_d["stage_id"]


def test_v2_mutable_execution_fields_remain_unfrozen_and_fail_closed() -> None:
    contract = _contract()
    unresolved = contract["unresolved_preregistration_fields"]
    assert unresolved["candidate_ids"] == {"82": None, "83": None, "84": None}
    assert unresolved["component_control_ids"] == {"indicators_only": None, "kronos_only": None}
    for key in (
        "compute_cost_cap",
        "data_cost_cap",
        "deterministic_artifact_namespace",
        "exact_code_revision",
        "leakage_guard",
        "material_improvement_rule",
        "multiple_testing_rule",
        "seed_semantics",
        "uncertainty_significance_rule",
    ):
        assert unresolved[key] is None
    stop_ids = {item["id"] for item in contract["stop_failure_criteria"]}
    assert {
        "metric_identity_unresolved",
        "comparator_unresolved",
        "hard_context_identity_missing",
        "preregistration_field_unresolved",
        "independent_review_missing",
    } <= stop_ids


def test_agent2_slice_does_not_contain_agent3_audit_artifacts() -> None:
    assert not (V2 / "inherited-hypothesis-dispositions.json").exists()
    assert not (V2 / "review-checklist.md").exists()
