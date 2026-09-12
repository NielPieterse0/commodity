from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research" / "run_phase7_prospective_operations.py"


def _module():
    spec = importlib.util.spec_from_file_location("phase7_prospective_operations", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decision(module, record_id: str = "prospective-1") -> dict[str, object]:
    phase7 = module._phase7_module()
    return {
        "record_id": record_id,
        "decision_timestamp": "2026-09-13T12:00:00Z",
        "target_end_timestamp": "2026-09-18T12:00:00Z",
        "candidate_config_id": "s-veto__l-none__p-half__u-none",
        "phase7_contract_sha256": phase7._sha256(module.CONTRACT),
        "input_snapshot_sha256": "a" * 64,
        "forecast_id": "forecast-2026-09-13",
        "predicted_gross_pnl_usd": 250.0,
        "contract_id": "NGX6",
        "intended_position": -0.5,
        "fill_rule": "first_retained_interval_open_strictly_after_all_inputs_available",
        "cost_profile_id": "base",
        "risk_state": "active",
        "source_freshness_ok": True,
        "source_completeness_ok": True,
        "skip_or_miss_reason": None,
    }


def _outcome(module, record_id: str = "prospective-1") -> dict[str, object]:
    record = _decision(module, record_id)
    record.update(
        {
            "outcome_timestamp": "2026-09-18T12:00:00Z",
            "actual_position": -0.5,
            "fill_price": 3.25,
            "transaction_cost_usd": 15.0,
            "net_pnl_usd": 125.0,
        }
    )
    return record


def test_decision_requires_full_forecast_and_input_identity(tmp_path: Path) -> None:
    module = _module()
    record = _decision(module)
    del record["forecast_id"]
    try:
        module.append_decision(
            record,
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-13T12:00:01Z",
        )
    except ValueError as exc:
        assert "forecast_id" in str(exc)
    else:
        raise AssertionError("thin prospective decision was accepted")


def test_complete_decision_is_bound_before_later_settlement(tmp_path: Path) -> None:
    module = _module()
    ledger = tmp_path / "prospective.jsonl"
    decision = _decision(module)
    appended = module.append_decision(
        decision,
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    assert appended["event_type"] == "decision"
    assert appended["forecast_id"] == decision["forecast_id"]
    assert appended["input_snapshot_sha256"] == "a" * 64
    assert appended["target_end_timestamp"] == "2026-09-18T12:00:00Z"

    settled = module.append_outcome(
        _outcome(module),
        ledger=ledger,
        recorded_at="2026-09-18T12:00:01Z",
    )
    assert settled["event_type"] == "outcome"
    assert settled["decision_record_sha256"] == appended["record_sha256"]

    status = module.ledger_status(ledger)
    assert status["decision_events"] == 1
    assert status["settled_outcomes"] == 1
    assert status["pending_decisions"] == 0
    assert status["active_exposure_outcomes"] == 1
    assert status["short_exposure_outcomes"] == 1
    assert status["net_pnl_usd"] == 125.0
    assert status["phase8_entry_eligible"] is False


def test_settlement_rejects_decision_time_identity_drift(tmp_path: Path) -> None:
    module = _module()
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module),
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    outcome = _outcome(module)
    outcome["input_snapshot_sha256"] = "b" * 64
    try:
        module.append_outcome(
            outcome,
            ledger=ledger,
            recorded_at="2026-09-18T12:00:01Z",
        )
    except ValueError as exc:
        assert "input_snapshot_sha256" in str(exc)
    else:
        raise AssertionError("settlement accepted drift from the persisted decision")


def test_outcome_cannot_precede_frozen_target_end(tmp_path: Path) -> None:
    module = _module()
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module),
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    outcome = _outcome(module)
    outcome["outcome_timestamp"] = "2026-09-18T11:59:59Z"
    try:
        module.append_outcome(
            outcome,
            ledger=ledger,
            recorded_at="2026-09-18T12:00:01Z",
        )
    except ValueError as exc:
        assert "target_end_timestamp" in str(exc)
    else:
        raise AssertionError("outcome before target end was accepted")
