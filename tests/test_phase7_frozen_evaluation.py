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

def _prospective_record(module, record_id: str = "example-1") -> dict[str, object]:
    return {
        "record_id": record_id,
        "decision_timestamp": "2026-09-13T12:00:00Z",
        "outcome_timestamp": "2026-09-18T12:00:00Z",
        "candidate_config_id": "s-veto__l-none__p-half__u-none",
        "phase7_contract_sha256": module._sha256(module.CONTRACT),
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


def test_prospective_records_must_follow_landed_freeze() -> None:
    module = _module()
    record = _prospective_record(module)
    module.validate_prospective_record(
        record,
        freeze_landed_at="2026-09-12T12:00:00Z",
        contract_sha256=module._sha256(module.CONTRACT),
    )
    record["decision_timestamp"] = "2026-09-12T11:59:59Z"
    try:
        module.validate_prospective_record(
            record,
            freeze_landed_at="2026-09-12T12:00:00Z",
            contract_sha256=module._sha256(module.CONTRACT),
        )
    except ValueError as exc:
        assert "strictly after landed freeze" in str(exc)
    else:
        raise AssertionError("pre-freeze prospective record was accepted")


def test_prospective_decision_is_persisted_before_outcome_settlement(tmp_path: Path) -> None:
    module = _module()
    ledger = tmp_path / "prospective.jsonl"
    record = _prospective_record(module)
    decision = module.append_prospective_decision(
        {
            key: record[key]
            for key in (
                "record_id", "decision_timestamp", "candidate_config_id",
                "phase7_contract_sha256", "contract_id", "intended_position", "risk_state",
                "source_freshness_ok", "source_completeness_ok",
            )
        },
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    assert decision["event_type"] == "decision"
    assert decision["recorded_at"] < record["outcome_timestamp"]

    settled = module.append_prospective_outcome(
        record,
        ledger=ledger,
        recorded_at="2026-09-18T12:00:01Z",
    )
    assert settled["event_type"] == "outcome"
    assert settled["decision_record_sha256"] == decision["record_sha256"]
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2


def test_prospective_outcome_requires_preexisting_decision(tmp_path: Path) -> None:
    module = _module()
    try:
        module.append_prospective_outcome(
            _prospective_record(module),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-18T12:00:01Z",
        )
    except ValueError as exc:
        assert "exactly one preexisting decision" in str(exc)
    else:
        raise AssertionError("outcome was accepted without a preexisting decision")


def test_decision_and_settlement_timing_boundaries_are_strict(tmp_path: Path) -> None:
    module = _module()
    record = _prospective_record(module)
    decision_record = {
        key: record[key]
        for key in (
            "record_id", "decision_timestamp", "candidate_config_id",
            "phase7_contract_sha256", "contract_id", "intended_position", "risk_state",
            "source_freshness_ok", "source_completeness_ok",
        )
    }
    decision_record["decision_timestamp"] = "2026-09-12T04:30:20Z"
    try:
        module.append_prospective_decision(
            decision_record,
            ledger=tmp_path / "freeze-boundary.jsonl",
            recorded_at="2026-09-12T04:30:21Z",
        )
    except ValueError as exc:
        assert "strictly after landed freeze" in str(exc)
    else:
        raise AssertionError("decision at the exact freeze boundary was accepted")

    ledger = tmp_path / "settlement-boundary.jsonl"
    decision_record["decision_timestamp"] = record["decision_timestamp"]
    module.append_prospective_decision(
        decision_record,
        ledger=ledger,
        recorded_at="2026-09-18T12:00:00Z",
    )
    try:
        module.append_prospective_outcome(
            record,
            ledger=ledger,
            recorded_at="2026-09-18T12:00:01Z",
        )
    except ValueError as exc:
        assert "recorded before outcome timestamp" in str(exc)
    else:
        raise AssertionError("settlement accepted a decision not recorded before outcome")


def test_duplicate_outcome_is_rejected(tmp_path: Path) -> None:
    module = _module()
    ledger = tmp_path / "prospective.jsonl"
    record = _prospective_record(module)
    decision_record = {
        key: record[key]
        for key in (
            "record_id", "decision_timestamp", "candidate_config_id",
            "phase7_contract_sha256", "contract_id", "intended_position", "risk_state",
            "source_freshness_ok", "source_completeness_ok",
        )
    }
    module.append_prospective_decision(
        decision_record,
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    module.append_prospective_outcome(
        record,
        ledger=ledger,
        recorded_at="2026-09-18T12:00:01Z",
    )
    try:
        module.append_prospective_outcome(
            record,
            ledger=ledger,
            recorded_at="2026-09-18T12:00:02Z",
        )
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("duplicate outcome was accepted")