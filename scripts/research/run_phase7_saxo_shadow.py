from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from commodity.config import data_config
from commodity.providers.saxo import (
    SaxoLiveMarketDataClient,
    probe_live_execution_target,
    resolve_continuous_future,
)

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME = ROOT / "research" / "programmes" / "003-natural-gas-trading-decision-system"
CANONICAL_LEDGER = PROGRAMME / "phase7-prospective-ledger.jsonl"
PHASE7_SCRIPT = ROOT / "scripts" / "research" / "run_phase7_frozen_evaluation.py"
DEFAULT_SHADOW_LEDGER = (
    ROOT / "data" / "raw" / "snapshots" / "saxo-live" / "phase7-saxo-shadow-ledger.jsonl"
)
READINESS_EVIDENCE = ROOT / ".work" / "changes" / "380-phase7-zero-spend-market-data" / "phase7-saxo-live-readiness.json"


def _phase7_module():
    spec = importlib.util.spec_from_file_location("phase7_frozen_evaluation_for_saxo", PHASE7_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Phase-7 frozen-evaluation implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _canonical_bytes(event: dict[str, Any]) -> bytes:
    return json.dumps(
        event, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def read_shadow_events(ledger: Path) -> tuple[str, list[dict[str, Any]]]:
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
                raise TypeError(f"invalid Saxo shadow row {line_number}")
            if envelope.get("previous_record_sha256") != previous_hash:
                raise ValueError(f"Saxo shadow chain break at row {line_number}")
            observed = hashlib.sha256(
                bytes.fromhex(previous_hash) + _canonical_bytes(event)
            ).hexdigest()
            if envelope.get("record_sha256") != observed:
                raise ValueError(f"Saxo shadow hash mismatch at row {line_number}")
            copied = dict(event)
            copied["record_sha256"] = observed
            events.append(copied)
            previous_hash = observed
    return previous_hash, events


def _append_shadow_event(event: dict[str, Any], ledger: Path) -> dict[str, Any]:
    previous_hash, _ = read_shadow_events(ledger)
    record_hash = hashlib.sha256(
        bytes.fromhex(previous_hash) + _canonical_bytes(event)
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


def _decision_by_id(canonical_ledger: Path, record_id: str) -> dict[str, Any]:
    module = _phase7_module()
    _, events = module._read_prospective_events(canonical_ledger)
    matches = [
        event for event in events
        if event.get("event_type") == "decision" and str(event.get("record_id")) == record_id
    ]
    if len(matches) != 1:
        raise ValueError("Saxo shadow capture requires exactly one existing Phase-7 decision")
    return matches[0]


def _product_config(contract_id: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    source = data_config()["sources"]["saxo_henry_hub_live_probe"]
    products = sorted(
        source["products"], key=lambda item: len(str(item["base_identifier"])), reverse=True,
    )
    for product in products:
        base = str(product["base_identifier"])
        if contract_id.startswith(base):
            return base, product, source
    raise ValueError(f"unsupported Saxo shadow contract: {contract_id}")


def _resolve_contract(
    client: SaxoLiveMarketDataClient, contract_id: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    base, product, source = _product_config(contract_id)
    summaries = client.search_contract_futures(str(product["search_keywords"]))
    parent = resolve_continuous_future(summaries, expected_symbol=base)
    space = client.futures_space(int(parent["Identifier"]))
    if str(space.get("BaseIdentifier")) != base:
        raise ValueError(f"Saxo futures-space mismatch for {base}")
    matches = [item for item in space.get("Elements", []) if item.get("Symbol") == contract_id]
    if len(matches) != 1:
        raise ValueError(f"Saxo LIVE contract mapping is not unique: {contract_id}")
    return base, matches[0], source


def _normalized_sample(payload: dict[str, Any]) -> dict[str, Any]:
    samples = payload.get("Data", [])
    if not isinstance(samples, list) or not samples:
        raise ValueError("Saxo LIVE chart snapshot did not return a price sample")
    sample = samples[-1]
    if not isinstance(sample, dict):
        raise TypeError("Saxo LIVE chart sample must be an object")
    return {
        "time": sample.get("Time"),
        "open": sample.get("Open"),
        "high": sample.get("High"),
        "low": sample.get("Low"),
        "close": sample.get("Close"),
        "volume": sample.get("Volume"),
    }


def capture_decision_shadow(
    *,
    client: SaxoLiveMarketDataClient,
    record_id: str,
    canonical_ledger: Path = CANONICAL_LEDGER,
    shadow_ledger: Path = DEFAULT_SHADOW_LEDGER,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    if client.provider_id != "saxo_openapi_live":
        raise ValueError("Saxo Phase-7 shadow capture requires the LIVE read-only provider")
    decision = _decision_by_id(canonical_ledger, record_id)
    written = _parse_utc(recorded_at or datetime.now(UTC).isoformat())
    decision_written = _parse_utc(str(decision["recorded_at"]))
    if written < decision_written:
        raise ValueError("Saxo shadow observation cannot predate the persisted Phase-7 decision")
    contract_id = str(decision["contract_id"])
    base, element, source = _resolve_contract(client, contract_id)
    horizon = int(source["shadow_capture_horizon_minutes"])
    snapshot = client.chart_snapshot(int(element["Uic"]), horizon=horizon)
    chart_info = snapshot.get("ChartInfo", {})
    display = snapshot.get("DisplayAndFormat", {})
    sample = _normalized_sample(snapshot)
    planned_fill = _parse_utc(str(decision["planned_fill_timestamp"]))
    seconds_from_fill = (written - planned_fill).total_seconds()
    event = {
        "event_type": "saxo_execution_shadow",
        "recorded_at": written.isoformat(),
        "phase7_record_id": record_id,
        "phase7_decision_record_sha256": decision["record_sha256"],
        "decision_timestamp": decision["decision_timestamp"],
        "planned_fill_timestamp": decision["planned_fill_timestamp"],
        "seconds_from_planned_fill": seconds_from_fill,
        "contract_id": contract_id,
        "intended_position": decision.get("intended_position"),
        "saxo_provider": client.provider_id,
        "saxo_product_base": base,
        "saxo_uic": int(element["Uic"]),
        "saxo_expiry_date": element.get("ExpiryDate"),
        "saxo_display_symbol": display.get("Symbol"),
        "exchange_id": chart_info.get("ExchangeId"),
        "delayed_by_minutes": chart_info.get("DelayedByMinutes"),
        "chart_horizon_minutes": horizon,
        "chart_sample": sample,
        "canonical_scientific_source": False,
        "phase7_decision_source_allowed": False,
        "phase7_settlement_source_allowed": False,
        "order_submission_attempted": False,
    }
    return _append_shadow_event(event, shadow_ledger)


def verify_live_readiness(
    client: SaxoLiveMarketDataClient, *, evidence_path: Path = READINESS_EVIDENCE,
) -> dict[str, Any]:
    report = probe_live_execution_target(client)
    report["phase7_role"] = "execution_target_shadow_only"
    report["frozen_databento_scientific_contract_unchanged"] = True
    report["live_capital_authorized"] = False
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report


def shadow_status(ledger: Path = DEFAULT_SHADOW_LEDGER) -> dict[str, Any]:
    tail_hash, events = read_shadow_events(ledger)
    return {
        "shadow_ledger": str(ledger),
        "event_count": len(events),
        "tail_record_sha256": tail_hash,
        "canonical_scientific_source": False,
        "phase7_settlement_source_allowed": False,
        "live_trading_allowed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Saxo LIVE and record execution-target shadow observations for Phase 7"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify-live", help="verify LIVE account and NG/MNG read access")
    verify.add_argument("--evidence", type=Path, default=READINESS_EVIDENCE)
    capture = sub.add_parser(
        "capture-decision", help="record a broker-native shadow snapshot for a persisted Phase-7 decision"
    )
    capture.add_argument("record_id")
    capture.add_argument("--canonical-ledger", type=Path, default=CANONICAL_LEDGER)
    capture.add_argument("--shadow-ledger", type=Path, default=DEFAULT_SHADOW_LEDGER)
    status = sub.add_parser("status", help="validate and summarize the local Saxo shadow ledger")
    status.add_argument("--shadow-ledger", type=Path, default=DEFAULT_SHADOW_LEDGER)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "verify-live":
        result = verify_live_readiness(SaxoLiveMarketDataClient(), evidence_path=args.evidence)
    elif args.command == "capture-decision":
        result = capture_decision_shadow(
            client=SaxoLiveMarketDataClient(),
            record_id=args.record_id,
            canonical_ledger=args.canonical_ledger,
            shadow_ledger=args.shadow_ledger,
        )
    else:
        result = shadow_status(args.shadow_ledger)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
