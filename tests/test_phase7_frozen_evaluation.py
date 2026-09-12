from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research" / "run_phase7_frozen_evaluation.py"


def _module():
    spec = importlib.util.spec_from_file_location("phase7_frozen_evaluation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase7_freeze_audit_preserves_protected_history() -> None:
    module = _module()
    result = module.build_freeze_audit()
    assert result["protected_confirmation_accessed"] is False
    assert result["reserved_2023_plus_outcomes_accessed"] is False
    assert result["phase8_entry_eligible"] is False
    assert result["historical_development_replay"]["row_count"] == 2790
    assert result["historical_development_replay"]["period_end"] == "2022-12-30"
    assert abs(result["historical_development_replay"]["net_pnl_usd"] - 16555.0) < 1e-6
    assert abs(result["historical_development_replay"]["transaction_cost_usd"] - 7575.0) < 1e-6

def test_prospective_records_must_follow_landed_freeze() -> None:
    module = _module()
    contract_sha = module._sha256(module.CONTRACT)
    record = {
        "record_id": "example-1",
        "decision_timestamp": "2026-09-13T12:00:00Z",
        "outcome_timestamp": "2026-09-18T12:00:00Z",
        "candidate_config_id": "s-veto__l-none__p-half__u-none",
        "phase7_contract_sha256": contract_sha,
        "contract_id": "NG-example",
        "intended_position": 1,
        "actual_position": 1,
        "fill_price": 3.0,
        "transaction_cost_usd": 30.0,
        "net_pnl_usd": 100.0,
        "risk_state": "active",
        "source_freshness_ok": True,
        "source_completeness_ok": True,
        "skip_or_miss_reason": None,
    }
    module.validate_prospective_record(
        record, freeze_landed_at="2026-09-12T12:00:00Z", contract_sha256=contract_sha
    )
    record["decision_timestamp"] = "2026-09-12T11:59:59Z"
    try:
        module.validate_prospective_record(
            record, freeze_landed_at="2026-09-12T12:00:00Z", contract_sha256=contract_sha
        )
    except ValueError as exc:
        assert "strictly after landed freeze" in str(exc)
    else:
        raise AssertionError("pre-freeze prospective record was accepted")