import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/development/v2-activation-preregistration/activation-contract.json"
MANIFEST = ROOT / "docs/development/v2-activation-preregistration/statistical-evaluator.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_activation_binds_exact_statistical_evaluator_manifest() -> None:
    contract = _load(CONTRACT)
    rule = contract["frozen_execution_rules"]["uncertainty_significance_rule"]

    assert rule["evaluator_manifest"] == "docs/development/v2-activation-preregistration/statistical-evaluator.json"
    assert rule["evaluator_manifest_sha256"] == _sha256(MANIFEST)
    assert rule["common_evaluator_source_preflight_required"] is True


def test_statistical_evaluator_sources_are_exact_bound() -> None:
    manifest = _load(MANIFEST)
    identity = manifest["source_identity"]

    assert identity["checkout_rule"].startswith("core.autocrlf=false")
    for relative_path in identity["paths"]:
        path = ROOT / relative_path
        assert _sha256(path) == identity["sha256"][relative_path]


def test_primary_and_secondary_inference_roles_are_fully_bound() -> None:
    contract = _load(CONTRACT)
    manifest = _load(MANIFEST)
    rule = contract["frozen_execution_rules"]["uncertainty_significance_rule"]
    primary = manifest["primary_inference"]
    secondary = manifest["secondary_inference"]

    assert rule["primary_callable"] == primary["callable"]
    assert rule["primary_p_value_field"] == primary["bh_input_field"] == "p_value"
    assert rule["primary_p_value_semantics"] == "two_sided_centered_bootstrap"
    assert primary["paired_statistic"] == "baseline_rmse_minus_challenger_rmse"
    assert "truncate to exactly n" in primary["sampling"]
    assert rule["secondary_callable"] == secondary["callable"]
    assert rule["secondary_p_value_field"] == secondary["p_value_field"]
    assert secondary["tail"] == "one_sided_improvement"
    assert secondary["null_enumeration"] == (
        "exact sign enumeration over all 2^n complete-block sign assignments; at most 20 complete blocks"
    )
    assert secondary["null_includes_observed_assignment"] is True
    assert secondary["p_value_method"] == "(1 + count(null >= observed)) / (len(null) + 1)"
    assert secondary["tie_rule"] == "null >= observed"
    assert secondary["enters_bh"] is False
    assert secondary["independent_promotion_gate"] is False
    assert secondary["rescue_authority"] is False


def test_statistical_evaluator_drift_is_fail_closed() -> None:
    contract = _load(CONTRACT)
    stop_rules = {item["id"]: item for item in contract["stop_failure_criteria"]}

    assert stop_rules["statistical_evaluator_drift"]["action"] == "stop"
    assert contract["execution_authorized"] is False
    assert not any(contract["empirical_release_gate"]["release_state"].values())
