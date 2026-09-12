from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME = ROOT / "research" / "programmes" / "003-natural-gas-trading-decision-system"
CONTRACT = PROGRAMME / "phase7-frozen-evaluation-v1.json"
CHANGE = ROOT / ".work" / "changes" / "361-frozen-evaluation"
LEDGER = ROOT / ".work" / "changes" / "359-stacking-policy" / "phase5-results" / "selected-standard-ledger.csv"
AUDIT = CHANGE / "phase7-freeze-audit.json"

BOUND_FILES = {
    "phase5_authority_sha256": PROGRAMME / "phase5-stacking-policy-v1.json",
    "phase6_authority_sha256": PROGRAMME / "phase6-controlled-expansion-v1.json",
    "phase4_specialist_authority_sha256": PROGRAMME / "phase4-foundation-specialists-v1.json",
}
CONFIG_FILES = {
    "models": ROOT / "config" / "models.json",
    "research_dataset": ROOT / "config" / "research_dataset.json",
    "simulation": ROOT / "config" / "simulation.json",
    "trading_policy": ROOT / "config" / "trading-policy.json",
    "assumptions": ROOT / "config" / "assumptions.json",
}

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def verify_bound_identity(contract: dict[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    expected_candidate = contract["frozen_candidate"]
    for key, path in BOUND_FILES.items():
        observed[key] = _sha256(path)
        if observed[key] != expected_candidate[key]:
            raise ValueError(f"frozen candidate identity drift: {key}")
    for key, path in CONFIG_FILES.items():
        observed[key] = _sha256(path)
        if observed[key] != contract["bound_configuration_sha256"][key]:
            raise ValueError(f"frozen configuration drift: {key}")
    return observed

def audit_development_ledger(contract: dict[str, Any]) -> dict[str, Any]:
    expected = contract["historical_evidence"]["adaptive_development"]
    rows = 0
    net_pnl = 0.0
    transaction_cost = 0.0
    first_date: str | None = None
    last_date: str | None = None
    with LEDGER.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            trade_date = str(row["trade_date"])[0:10]
            if trade_date >= "2023-01-01":
                raise ValueError("protected 2023+ outcome row is not permitted in the development audit")
            first_date = trade_date if first_date is None else min(first_date, trade_date)
            last_date = trade_date if last_date is None else max(last_date, trade_date)
            net_pnl += float(row["net_pnl_usd"])
            transaction_cost += float(row["transaction_cost_usd"])
            rows += 1
    observed = {
        "row_count": rows,
        "period_start": first_date,
        "period_end": last_date,
        "net_pnl_usd": net_pnl,
        "transaction_cost_usd": transaction_cost,
        "selected_standard_ledger_sha256": _sha256(LEDGER),
    }
    for key in ("row_count", "period_start", "period_end", "selected_standard_ledger_sha256"):
        if observed[key] != expected[key]:
            raise ValueError(f"development ledger identity drift: {key}")
    for key in ("net_pnl_usd", "transaction_cost_usd"):
        if abs(float(observed[key]) - float(expected[key])) > 1e-6:
            raise ValueError(f"development ledger accounting drift: {key}")
    return observed

def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def validate_prospective_record(
    record: dict[str, Any], *, freeze_landed_at: str, contract_sha256: str
) -> None:
    required = {
        "record_id", "decision_timestamp", "outcome_timestamp", "candidate_config_id",
        "phase7_contract_sha256", "contract_id", "intended_position", "actual_position",
        "fill_price", "transaction_cost_usd", "net_pnl_usd", "risk_state",
        "source_freshness_ok", "source_completeness_ok", "skip_or_miss_reason",
    }
    missing = sorted(required.difference(record))
    if missing:
        raise ValueError(f"prospective record missing fields: {missing}")
    decision = _parse_utc(str(record["decision_timestamp"]))
    outcome = _parse_utc(str(record["outcome_timestamp"]))
    freeze = _parse_utc(freeze_landed_at)
    if decision <= freeze:
        raise ValueError("prospective decision must occur strictly after landed freeze")
    if outcome <= decision:
        raise ValueError("outcome timestamp must follow decision timestamp")
    if record["candidate_config_id"] != "s-veto__l-none__p-half__u-none":
        raise ValueError("candidate identity mismatch")
    if record["phase7_contract_sha256"] != contract_sha256:
        raise ValueError("Phase-7 contract identity mismatch")


def _canonical_event_bytes(event: dict[str, Any]) -> bytes:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _read_prospective_events(ledger: Path) -> tuple[str, list[dict[str, Any]]]:
    previous_hash = "0" * 64
    events: list[dict[str, Any]] = []
    if not ledger.exists():
        return previous_hash, events
    with ledger.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            envelope = json.loads(line)
            event = envelope.get("event")
            if not isinstance(event, dict):
                raise TypeError(f"invalid prospective ledger row {line_number}")
            if envelope.get("previous_record_sha256") != previous_hash:
                raise ValueError(f"prospective ledger chain break at row {line_number}")
            observed = hashlib.sha256(
                bytes.fromhex(previous_hash) + _canonical_event_bytes(event)
            ).hexdigest()
            if envelope.get("record_sha256") != observed:
                raise ValueError(f"prospective ledger hash mismatch at row {line_number}")
            event = dict(event)
            event["record_sha256"] = observed
            events.append(event)
            previous_hash = observed
    return previous_hash, events


def _append_prospective_event(event: dict[str, Any], *, ledger: Path) -> dict[str, Any]:
    previous_hash, _ = _read_prospective_events(ledger)
    record_hash = hashlib.sha256(
        bytes.fromhex(previous_hash) + _canonical_event_bytes(event)
    ).hexdigest()
    envelope = {
        "schema_version": 1,
        "previous_record_sha256": previous_hash,
        "record_sha256": record_hash,
        "event": event,
    }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
    return {**envelope, **event}


def append_prospective_decision(
    record: dict[str, Any], *, ledger: Path, recorded_at: str | None = None
) -> dict[str, Any]:
    """Persist a frozen decision before its outcome can be known."""
    contract = _read_contract()
    landing = contract.get("freeze_landing")
    if not isinstance(landing, dict) or not landing.get("merged_at"):
        raise ValueError("prospective logging requires exact landed freeze identity")
    required = {
        "record_id", "decision_timestamp", "candidate_config_id", "phase7_contract_sha256",
        "contract_id", "intended_position", "risk_state", "source_freshness_ok",
        "source_completeness_ok",
    }
    missing = sorted(required.difference(record))
    if missing:
        raise ValueError(f"prospective decision missing fields: {missing}")
    decision = _parse_utc(str(record["decision_timestamp"]))
    freeze = _parse_utc(str(landing["merged_at"]))
    written = _parse_utc(recorded_at or datetime.now(UTC).isoformat())
    if decision <= freeze:
        raise ValueError("prospective decision must occur strictly after landed freeze")
    if written < decision:
        raise ValueError("decision cannot be recorded before its decision timestamp")
    if record["candidate_config_id"] != "s-veto__l-none__p-half__u-none":
        raise ValueError("candidate identity mismatch")
    if record["phase7_contract_sha256"] != _sha256(CONTRACT):
        raise ValueError("Phase-7 contract identity mismatch")
    _, events = _read_prospective_events(ledger)
    record_id = str(record["record_id"])
    if any(str(event.get("record_id")) == record_id for event in events):
        raise ValueError("prospective record_id already exists")
    event = {"event_type": "decision", "recorded_at": written.isoformat(), **record}
    return _append_prospective_event(event, ledger=ledger)


def append_prospective_outcome(
    record: dict[str, Any], *, ledger: Path, recorded_at: str | None = None
) -> dict[str, Any]:
    """Settle a previously persisted decision without rewriting it."""
    contract = _read_contract()
    landing = contract.get("freeze_landing")
    if not isinstance(landing, dict) or not landing.get("merged_at"):
        raise ValueError("prospective logging requires exact landed freeze identity")
    validate_prospective_record(
        record,
        freeze_landed_at=str(landing["merged_at"]),
        contract_sha256=_sha256(CONTRACT),
    )
    written = _parse_utc(recorded_at or datetime.now(UTC).isoformat())
    outcome = _parse_utc(str(record["outcome_timestamp"]))
    if written < outcome:
        raise ValueError("outcome cannot be recorded before its outcome timestamp")
    _, events = _read_prospective_events(ledger)
    record_id = str(record["record_id"])
    decisions = [event for event in events if event.get("event_type") == "decision" and str(event.get("record_id")) == record_id]
    if len(decisions) != 1:
        raise ValueError("prospective outcome requires exactly one preexisting decision")
    if any(event.get("event_type") == "outcome" and str(event.get("record_id")) == record_id for event in events):
        raise ValueError("prospective outcome already exists")
    decision = decisions[0]
    if _parse_utc(str(decision["recorded_at"])) >= outcome:
        raise ValueError("preexisting decision must be recorded before outcome timestamp")
    for key in ("decision_timestamp", "candidate_config_id", "phase7_contract_sha256", "contract_id", "intended_position", "risk_state", "source_freshness_ok", "source_completeness_ok"):
        if record[key] != decision[key]:
            raise ValueError(f"prospective outcome decision identity mismatch: {key}")
    event = {
        "event_type": "outcome",
        "recorded_at": written.isoformat(),
        "decision_record_sha256": decision["record_sha256"],
        **record,
    }
    return _append_prospective_event(event, ledger=ledger)


def build_freeze_audit() -> dict[str, Any]:
    contract = _read_contract()
    if contract["protected_confirmation_accessed"] is not False:
        raise ValueError("Phase-7 freeze preparation must not claim protected outcome access")
    identity = verify_bound_identity(contract)
    development = audit_development_ledger(contract)
    landing = contract.get("freeze_landing")
    if not isinstance(landing, dict) or not landing.get("merge_commit_sha") or not landing.get("merged_at"):
        raise ValueError("Phase-7 active audit requires exact freeze landing identity")
    return {
        "schema_version": 1,
        "programme_id": contract["programme_id"],
        "phase": 7,
        "issue": 361,
        "status": "freeze_contract_verified_prospective_active",
        "phase7_contract_sha256": _sha256(CONTRACT),
        "protected_confirmation_accessed": False,
        "freeze_landing": landing,
        "bound_identity": identity,
        "historical_development_replay": development,
        "reserved_2023_plus_outcomes_accessed": False,
        "prospective_status": "active_after_exact_freeze_landing",
        "phase8_entry_eligible": False,
    }


def main() -> None:
    result = build_freeze_audit()
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()