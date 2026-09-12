from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME = ROOT / "research" / "programmes" / "003-natural-gas-trading-decision-system"
CONTRACT = PROGRAMME / "phase7-frozen-evaluation-v1.json"
DEFAULT_LEDGER = PROGRAMME / "phase7-prospective-ledger.jsonl"
PHASE7_SCRIPT = ROOT / "scripts" / "research" / "run_phase7_frozen_evaluation.py"

_ALLOWED_POSITIONS = {-1.0, -0.5, 0.0, 0.5, 1.0}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_DECISION_FIELDS = (
    "record_id",
    "decision_timestamp",
    "target_end_timestamp",
    "candidate_config_id",
    "phase7_contract_sha256",
    "input_snapshot_sha256",
    "forecast_id",
    "predicted_gross_pnl_usd",
    "contract_id",
    "intended_position",
    "fill_rule",
    "cost_profile_id",
    "risk_state",
    "source_freshness_ok",
    "source_completeness_ok",
    "skip_or_miss_reason",
)


def _phase7_module():
    spec = importlib.util.spec_from_file_location("phase7_frozen_evaluation", PHASE7_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Phase-7 frozen-evaluation implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _finite_float(value: object, label: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def _validate_decision_payload(record: dict[str, Any], module: Any) -> None:
    missing = [field for field in _DECISION_FIELDS if field not in record]
    if missing:
        raise ValueError(f"prospective decision missing operational fields: {missing}")

    contract = _load_json(CONTRACT)
    decision = module._parse_utc(str(record["decision_timestamp"]))
    target_end = module._parse_utc(str(record["target_end_timestamp"]))
    freeze = module._parse_utc(str(contract["freeze_landing"]["merged_at"]))
    if decision <= freeze:
        raise ValueError("prospective decision must occur strictly after landed freeze")
    if target_end <= decision:
        raise ValueError("target_end_timestamp must follow decision_timestamp")

    expected_candidate = str(contract["frozen_candidate"]["config_id"])
    if str(record["candidate_config_id"]) != expected_candidate:
        raise ValueError("candidate identity mismatch")
    if str(record["phase7_contract_sha256"]) != module._sha256(CONTRACT):
        raise ValueError("Phase-7 contract identity mismatch")

    input_hash = str(record["input_snapshot_sha256"])
    if _SHA256_RE.fullmatch(input_hash) is None:
        raise ValueError("input_snapshot_sha256 must be a lowercase SHA-256 hex digest")
    if not str(record["forecast_id"]).strip():
        raise ValueError("forecast_id must be non-empty")
    _finite_float(record["predicted_gross_pnl_usd"], "predicted_gross_pnl_usd")

    intended = _finite_float(record["intended_position"], "intended_position")
    if intended not in _ALLOWED_POSITIONS:
        raise ValueError("intended_position is outside the frozen position levels")
    if not str(record["contract_id"]).strip():
        raise ValueError("contract_id must be non-empty")
    if not str(record["fill_rule"]).strip():
        raise ValueError("fill_rule must be non-empty")
    if not str(record["cost_profile_id"]).strip():
        raise ValueError("cost_profile_id must be non-empty")
    if not str(record["risk_state"]).strip():
        raise ValueError("risk_state must be non-empty")
    if not isinstance(record["source_freshness_ok"], bool):
        raise TypeError("source_freshness_ok must be boolean")
    if not isinstance(record["source_completeness_ok"], bool):
        raise TypeError("source_completeness_ok must be boolean")


def append_decision(
    record: dict[str, Any], *, ledger: Path = DEFAULT_LEDGER, recorded_at: str | None = None
) -> dict[str, Any]:
    """Validate and durably append one complete prospective decision event."""
    module = _phase7_module()
    _validate_decision_payload(record, module)
    return module.append_prospective_decision(record, ledger=ledger, recorded_at=recorded_at)


def _decision_for_record(module: Any, ledger: Path, record_id: str) -> dict[str, Any]:
    _, events = module._read_prospective_events(ledger)
    decisions = [
        event
        for event in events
        if event.get("event_type") == "decision" and str(event.get("record_id")) == record_id
    ]
    if len(decisions) != 1:
        raise ValueError("prospective outcome requires exactly one complete preexisting decision")
    return decisions[0]


def append_outcome(
    record: dict[str, Any], *, ledger: Path = DEFAULT_LEDGER, recorded_at: str | None = None
) -> dict[str, Any]:
    """Settle a complete prospective decision while binding all decision-time facts."""
    module = _phase7_module()
    outcome_required = {
        *_DECISION_FIELDS,
        "outcome_timestamp",
        "actual_position",
        "fill_price",
        "transaction_cost_usd",
        "net_pnl_usd",
    }
    missing = sorted(outcome_required.difference(record))
    if missing:
        raise ValueError(f"prospective outcome missing operational fields: {missing}")

    _validate_decision_payload(record, module)
    decision = _decision_for_record(module, ledger, str(record["record_id"]))
    for key in _DECISION_FIELDS:
        if record[key] != decision[key]:
            raise ValueError(f"prospective outcome decision identity mismatch: {key}")

    outcome = module._parse_utc(str(record["outcome_timestamp"]))
    target_end = module._parse_utc(str(record["target_end_timestamp"]))
    if outcome < target_end:
        raise ValueError("outcome_timestamp cannot precede target_end_timestamp")

    actual = _finite_float(record["actual_position"], "actual_position")
    if actual not in _ALLOWED_POSITIONS:
        raise ValueError("actual_position is outside the frozen position levels")
    transaction_cost = _finite_float(record["transaction_cost_usd"], "transaction_cost_usd")
    if transaction_cost < 0:
        raise ValueError("transaction_cost_usd must be non-negative")
    _finite_float(record["net_pnl_usd"], "net_pnl_usd")
    if record["fill_price"] is not None:
        fill_price = _finite_float(record["fill_price"], "fill_price")
        if fill_price <= 0:
            raise ValueError("fill_price must be positive when present")

    return module.append_prospective_outcome(record, ledger=ledger, recorded_at=recorded_at)


def ledger_status(ledger: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    module = _phase7_module()
    tail_hash, events = module._read_prospective_events(ledger)
    decisions = [event for event in events if event.get("event_type") == "decision"]
    outcomes = [event for event in events if event.get("event_type") == "outcome"]
    settled_ids = {str(event["record_id"]) for event in outcomes}
    pending = [event for event in decisions if str(event["record_id"]) not in settled_ids]

    active = [event for event in outcomes if abs(float(event["actual_position"])) > 0.0]
    long_count = sum(float(event["actual_position"]) > 0.0 for event in active)
    short_count = sum(float(event["actual_position"]) < 0.0 for event in active)
    net_pnl = sum(float(event["net_pnl_usd"]) for event in outcomes)
    first_decision = min((str(event["decision_timestamp"]) for event in decisions), default=None)

    return {
        "ledger": str(ledger),
        "tail_record_sha256": tail_hash,
        "decision_events": len(decisions),
        "settled_outcomes": len(outcomes),
        "pending_decisions": len(pending),
        "active_exposure_outcomes": len(active),
        "long_exposure_outcomes": int(long_count),
        "short_exposure_outcomes": int(short_count),
        "net_pnl_usd": float(net_pnl),
        "first_decision_timestamp": first_decision,
        "phase8_entry_eligible": False,
        "eligibility_note": (
            "Coverage counters are operational diagnostics only. Phase-8 eligibility still requires "
            "the frozen 365-day, independent-episode, logging-fidelity, economic and risk gates."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the frozen Phase-7 prospective evidence ledger")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    sub = parser.add_subparsers(dest="command", required=True)

    decision = sub.add_parser("decision", help="append a decision before its outcome exists")
    decision.add_argument("payload", type=Path)
    decision.add_argument("--recorded-at")

    outcome = sub.add_parser("outcome", help="settle a previously persisted decision")
    outcome.add_argument("payload", type=Path)
    outcome.add_argument("--recorded-at")

    sub.add_parser("status", help="validate the hash chain and report operational counters")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "decision":
        result = append_decision(_load_json(args.payload), ledger=args.ledger, recorded_at=args.recorded_at)
    elif args.command == "outcome":
        result = append_outcome(_load_json(args.payload), ledger=args.ledger, recorded_at=args.recorded_at)
    else:
        result = ledger_status(args.ledger)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
