from __future__ import annotations

import argparse
import hashlib
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
DERIVATION_SCRIPT = ROOT / "scripts" / "research" / "derive_phase7_prospective_decision.py"
TRADING_POLICY = ROOT / "config" / "trading-policy.json"
PHASE2_CONFIG = ROOT / "config" / "phase2_market_only.json"

_ALLOWED_POSITIONS = {-1.0, -0.5, 0.0, 0.5, 1.0}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_DECISION_FIELDS = (
    "record_id",
    "decision_timestamp",
    "planned_fill_timestamp",
    "target_end_timestamp",
    "horizon_sessions",
    "candidate_config_id",
    "prospective_serving_deployment_id",
    "prospective_origin_index",
    "path_counter_advanced",
    "kronos_path_eligible",
    "phase7_contract_sha256",
    "input_snapshot_sha256",
    "decision_input_snapshot",
    "source_snapshot_sha256",
    "forecast_id",
    "market_model_id",
    "predicted_path_move_per_mmbtu",
    "predicted_gross_pnl_usd",
    "baseline_position",
    "prior_position",
    "intended_position",
    "policy_modifiers",
    "contract_id",
    "fill_rule",
    "cost_profile_id",
    "risk_state",
    "source_freshness_ok",
    "source_completeness_ok",
    "skip_reason",
    "derivation",
)


def _phase7_module():
    spec = importlib.util.spec_from_file_location("phase7_frozen_evaluation", PHASE7_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Phase-7 frozen-evaluation implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CONTRACT = CONTRACT
    return module


def _derivation_module():
    spec = importlib.util.spec_from_file_location("phase7_prospective_derivation", DERIVATION_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Phase-7 decision-derivation implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PHASE7_CONTRACT = CONTRACT
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


def _json_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _position(value: object, label: str) -> float:
    parsed = _finite_float(value, label)
    if parsed not in _ALLOWED_POSITIONS:
        raise ValueError(f"{label} is outside the frozen position levels")
    return parsed


def _risk_contract() -> dict[str, Any]:
    policy = _load_json(TRADING_POLICY)
    policy_id = str(_load_json(CONTRACT)["frozen_candidate"]["risk_policy_id"])
    payload = policy["paper_risk_policies"].get(policy_id)
    if not isinstance(payload, dict):
        raise TypeError("frozen Phase-7 risk policy is unavailable")
    if payload.get("live_trading_allowed") is not False:
        raise ValueError("Phase-7 risk policy must prohibit live trading")
    return payload


def _cost_contract() -> tuple[float, float, float]:
    cfg = _load_json(PHASE2_CONFIG)
    profile = cfg["cost_profiles"]["base"]
    tick_value = float(cfg["execution_contract"]["tick_value_usd"])
    per_side = (
        float(profile["commission_usd_per_side"])
        + float(profile["exchange_clearing_fees_usd_per_side"])
        + (
            float(profile["half_spread_ticks_per_side"])
            + float(profile["slippage_ticks_per_side"])
        )
        * tick_value
    )
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    margin = float(profile["initial_margin_usd_per_contract"])
    return per_side, multiplier, margin


def _runtime_state(module: Any, ledger: Path) -> dict[str, Any]:
    _, events = module._read_prospective_events(ledger)
    sessions = [event for event in events if event.get("event_type") == "session"]
    risk = _risk_contract()
    if not sessions:
        capital = float(risk["capital_usd"])
        return {
            "prior_position": 0.0,
            "prior_contract_id": None,
            "equity_usd": capital,
            "peak_equity_usd": capital,
            "risk_state": "active",
            "kill_reason": None,
            "active_record_id": None,
            "active_forecast_id": None,
            "active_signal_position": 0.0,
            "active_signal_reason": "no_signal_yet",
            "active_target_end_timestamp": None,
            "last_session_timestamp": None,
            "last_next_session_timestamp": None,
        }
    last = sessions[-1]
    return {
        "prior_position": float(last["target_position"]),
        "prior_contract_id": last["contract_id"] if float(last["target_position"]) != 0.0 else None,
        "equity_usd": float(last["equity_usd"]),
        "peak_equity_usd": float(last["peak_equity_usd"]),
        "risk_state": str(last["risk_state"]),
        "kill_reason": last.get("kill_reason"),
        "active_record_id": last.get("active_record_id"),
        "active_forecast_id": last.get("active_forecast_id"),
        "active_signal_position": float(last.get("active_signal_position", 0.0)),
        "active_signal_reason": str(last.get("active_signal_reason", "forecast_signal")),
        "active_target_end_timestamp": last.get("active_target_end_timestamp"),
        "last_session_timestamp": last.get("session_timestamp"),
        "last_next_session_timestamp": last.get("next_session_timestamp"),
    }


def _prospective_start_boundary(module: Any, contract: dict[str, Any]) -> Any:
    serving = contract.get("prospective_serving_contract")
    if not isinstance(serving, dict) or serving.get("status") != "frozen_active":
        raise ValueError(
            "prospective decision logging is blocked until the serving-contract refreeze is landed and active"
        )
    if contract.get("status") != "prospective_active":
        raise ValueError("Phase 7 is not in an active prospective-evidence state")
    runtime_proof = serving.get("specialist_runtime_proof")
    if not isinstance(runtime_proof, dict) or runtime_proof.get("status") != "verified":
        raise ValueError("prospective specialist serving runtime is not verified for activation")
    if _SHA256_RE.fullmatch(str(runtime_proof.get("runtime_evidence_sha256", ""))) is None:
        raise ValueError("verified prospective specialist runtime requires exact evidence SHA-256")
    landing = serving.get("landing")
    required = {"pull_request", "head_sha", "merge_commit_sha", "merged_at"}
    if not isinstance(landing, dict) or required.difference(landing):
        raise ValueError("active prospective serving contract requires exact landed identity")
    if not isinstance(landing["pull_request"], int) or landing["pull_request"] <= 0:
        raise ValueError("prospective serving landing requires a positive pull-request number")
    for key in ("head_sha", "merge_commit_sha"):
        if _GIT_SHA_RE.fullmatch(str(landing[key])) is None:
            raise ValueError(f"prospective serving landing has invalid {key}")
    original = module._parse_utc(str(contract["freeze_landing"]["merged_at"]))
    serving_landed = module._parse_utc(str(landing["merged_at"]))
    if serving_landed < original:
        raise ValueError("prospective serving-contract landing cannot precede the original freeze")
    return serving_landed


def _validate_decision_payload(record: dict[str, Any], module: Any) -> None:
    missing = [field for field in _DECISION_FIELDS if field not in record]
    if missing:
        raise ValueError(f"prospective decision missing operational fields: {missing}")

    contract = _load_json(CONTRACT)
    module.verify_bound_identity(contract)
    decision = module._parse_utc(str(record["decision_timestamp"]))
    planned_fill = module._parse_utc(str(record["planned_fill_timestamp"]))
    target_end = module._parse_utc(str(record["target_end_timestamp"]))
    start_boundary = _prospective_start_boundary(module, contract)
    if decision <= start_boundary:
        raise ValueError("prospective decision must occur strictly after the landed serving freeze")
    if planned_fill <= decision:
        raise ValueError("planned_fill_timestamp must follow decision_timestamp")
    if target_end <= planned_fill:
        raise ValueError("target_end_timestamp must follow planned_fill_timestamp")
    if int(record["horizon_sessions"]) != int(contract["frozen_candidate"]["horizon_sessions"]):
        raise ValueError("prospective decision horizon does not match the frozen candidate")

    expected_candidate = str(contract["frozen_candidate"]["config_id"])
    if str(record["candidate_config_id"]) != expected_candidate:
        raise ValueError("candidate identity mismatch")
    serving = contract.get("prospective_serving_contract")
    if not isinstance(serving, dict):
        raise TypeError("prospective serving contract is unavailable")
    if str(record["prospective_serving_deployment_id"]) != str(serving["deployment_identity"]):
        raise ValueError("prospective serving deployment identity mismatch")
    if not isinstance(record["path_counter_advanced"], bool):
        raise TypeError("path_counter_advanced must be boolean")
    if not isinstance(record["kronos_path_eligible"], bool):
        raise TypeError("kronos_path_eligible must be boolean")
    origin_index = record["prospective_origin_index"]
    if record["path_counter_advanced"]:
        if not isinstance(origin_index, int) or origin_index < 0:
            raise ValueError("advanced prospective origin requires a non-negative integer index")
    elif origin_index is not None:
        raise ValueError("non-advanced prospective origin must not carry an origin index")
    if str(record["phase7_contract_sha256"]) != module._sha256(CONTRACT):
        raise ValueError("Phase-7 contract identity mismatch")

    input_hash = str(record["input_snapshot_sha256"])
    if _SHA256_RE.fullmatch(input_hash) is None:
        raise ValueError("input_snapshot_sha256 must be a lowercase SHA-256 hex digest")
    input_snapshot = record["decision_input_snapshot"]
    if not isinstance(input_snapshot, dict):
        raise TypeError("decision_input_snapshot must be an object")
    if _json_sha256(input_snapshot) != input_hash:
        raise ValueError("decision input snapshot hash mismatch")
    source_hash = str(record["source_snapshot_sha256"])
    if _SHA256_RE.fullmatch(source_hash) is None:
        raise ValueError("source_snapshot_sha256 must be a lowercase SHA-256 hex digest")
    if not str(record["forecast_id"]).strip():
        raise ValueError("forecast_id must be non-empty")
    if str(record["market_model_id"]) != "histgb-core-v1":
        raise ValueError("market model identity mismatch")
    _finite_float(record["predicted_path_move_per_mmbtu"], "predicted_path_move_per_mmbtu")
    _finite_float(record["predicted_gross_pnl_usd"], "predicted_gross_pnl_usd")
    derivation = record["derivation"]
    if not isinstance(derivation, dict):
        raise TypeError("derivation must be an object")
    if derivation.get("method") != "phase7_frozen_candidate_v1":
        raise ValueError("decision derivation method mismatch")
    if derivation.get("serving_deployment_identity") != serving["deployment_identity"]:
        raise ValueError("decision derivation serving identity mismatch")
    if derivation.get("origin_sequence_index") != origin_index:
        raise ValueError("decision derivation prospective origin index mismatch")
    rule = serving["kronos_path_availability"]
    cycle = int(rule["cycle_length"])
    residues = {int(value) for value in rule["active_residues_zero_based"]}
    expected_path = bool(record["path_counter_advanced"] and origin_index % cycle in residues)
    if bool(record["kronos_path_eligible"]) != expected_path:
        raise ValueError("prospective Kronos path eligibility violates the frozen cadence")
    if derivation.get("kronos_path_eligible") != expected_path:
        raise ValueError("decision derivation Kronos path eligibility mismatch")
    if derivation.get("outcome_fields_consumed") is not False:
        raise ValueError("prospective decision derivation may not consume outcome fields")

    _position(record["baseline_position"], "baseline_position")
    _position(record["prior_position"], "prior_position")
    intended = _position(record["intended_position"], "intended_position")
    modifiers = record["policy_modifiers"]
    if not isinstance(modifiers, list) or not all(
        isinstance(value, str) and value.strip() for value in modifiers
    ):
        raise TypeError("policy_modifiers must be a list of non-empty strings")

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

    sources_ok = bool(record["source_freshness_ok"] and record["source_completeness_ok"])
    if bool(record["path_counter_advanced"]) != sources_ok:
        raise ValueError("prospective origin counter must advance exactly on fresh complete decision inputs")
    skip_reason = record["skip_reason"]
    if not sources_ok and intended != 0.0:
        raise ValueError("stale or incomplete sources must fail closed to a flat intended position")
    if intended == 0.0 and (skip_reason is None or not str(skip_reason).strip()):
        raise ValueError("flat intended position requires an explicit decision-time skip_reason")
    if intended != 0.0 and skip_reason not in (None, ""):
        raise ValueError("active intended position cannot carry a decision-time skip_reason")


def _next_prospective_origin_index(module: Any, ledger: Path) -> int:
    _, events = module._read_prospective_events(ledger)
    advanced = [
        event for event in events
        if event.get("event_type") == "decision" and event.get("path_counter_advanced") is True
    ]
    observed = [event.get("prospective_origin_index") for event in advanced]
    if observed != list(range(len(observed))):
        raise ValueError("prospective origin index history is not contiguous")
    return len(observed)


def append_decision(
    record: dict[str, Any], *, ledger: Path = DEFAULT_LEDGER, recorded_at: str | None = None
) -> dict[str, Any]:
    """Validate and durably append one complete derived prospective decision."""
    module = _phase7_module()
    _validate_decision_payload(record, module)
    written = module._parse_utc(recorded_at or datetime.now(UTC).isoformat())
    planned_fill = module._parse_utc(str(record["planned_fill_timestamp"]))
    if written >= planned_fill:
        raise ValueError("prospective decision must be durably recorded before its planned fill")
    state = _runtime_state(module, ledger)
    if float(record["prior_position"]) != float(state["prior_position"]):
        raise ValueError("decision prior_position does not match persisted prospective state")
    if str(record["risk_state"]) != str(state["risk_state"]):
        raise ValueError("decision risk_state does not match persisted prospective state")
    if record["path_counter_advanced"]:
        expected_index = _next_prospective_origin_index(module, ledger)
        if int(record["prospective_origin_index"]) != expected_index:
            raise ValueError("prospective origin index does not match persisted cadence state")
    _, events = module._read_prospective_events(ledger)
    planned_fill = str(record["planned_fill_timestamp"])
    if any(
        event.get("event_type") == "decision"
        and str(event.get("planned_fill_timestamp")) == planned_fill
        for event in events
    ):
        raise ValueError("prospective planned_fill_timestamp already has a decision")
    return module.append_prospective_decision(record, ledger=ledger, recorded_at=recorded_at)


def _assert_prospective_serving_active() -> Any:
    module = _phase7_module()
    contract = _load_json(CONTRACT)
    module.verify_bound_identity(contract)
    return _prospective_start_boundary(module, contract)


def _reject_external_specialist_outputs(bundle: dict[str, Any]) -> None:
    forbidden = sorted(
        field for field in ("specialists", "specialist_runtime_provenance") if field in bundle
    )
    if forbidden:
        raise ValueError(
            "operational prospective derivation forbids caller-supplied specialist outputs: "
            f"{forbidden}"
        )


def derive_and_append_decision(
    bundle: dict[str, Any], *, checkpoint_root: Path, databento_root: Path,
    ledger: Path = DEFAULT_LEDGER,
) -> dict[str, Any]:
    """Fail closed until pinned specialist inference is integrated into this entrypoint."""
    _ = checkpoint_root, databento_root, ledger
    _assert_prospective_serving_active()
    if "source_snapshot" in bundle:
        raise ValueError("operational prospective derivation forbids caller-supplied source_snapshot")
    _reject_external_specialist_outputs(bundle)
    raise RuntimeError(
        "internal pinned TimesFM/Kronos serving inference is not yet integrated; "
        "prospective decision derivation remains blocked"
    )


def _decision_for_fill(module: Any, ledger: Path, session_timestamp: str) -> dict[str, Any] | None:
    _, events = module._read_prospective_events(ledger)
    session = module._parse_utc(session_timestamp)
    matches = [
        event for event in events
        if event.get("event_type") == "decision"
        and module._parse_utc(str(event.get("planned_fill_timestamp"))) == session
    ]
    if len(matches) > 1:
        raise ValueError("multiple prospective decisions target the same planned fill")
    return None if not matches else matches[0]


_SESSION_CALLER_EVIDENCE_FIELDS = {
    "contract_id",
    "next_selected_contract_id",
    "open_price",
    "next_open_same_contract",
    "source_snapshot_sha256",
    "source_freshness_ok",
    "source_completeness_ok",
}


def derive_and_append_session_observation(
    bundle: dict[str, Any], *, databento_root: Path, ledger: Path = DEFAULT_LEDGER,
) -> dict[str, Any]:
    """Fail closed until execution prices and source identity are internally derived."""
    _ = databento_root, ledger
    _assert_prospective_serving_active()
    forbidden = sorted(_SESSION_CALLER_EVIDENCE_FIELDS.intersection(bundle))
    if forbidden:
        raise ValueError(
            "operational session derivation forbids caller-supplied execution evidence: "
            f"{forbidden}"
        )
    raise RuntimeError(
        "internal Databento session-price derivation is not yet integrated; "
        "prospective session accounting remains blocked"
    )


def append_session_observation(
    observation: dict[str, Any], *, ledger: Path = DEFAULT_LEDGER,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Derive one daily held-position/risk row from observed execution prices."""
    serving_boundary = _assert_prospective_serving_active()
    module = _phase7_module()
    required = {
        "session_timestamp", "next_session_timestamp", "contract_id",
        "next_selected_contract_id", "open_price", "next_open_same_contract",
        "source_snapshot_sha256", "source_freshness_ok", "source_completeness_ok",
    }
    missing = sorted(required.difference(observation))
    if missing:
        raise ValueError(f"prospective session observation missing fields: {missing}")
    session = module._parse_utc(str(observation["session_timestamp"]))
    nxt = module._parse_utc(str(observation["next_session_timestamp"]))
    if session <= serving_boundary:
        raise ValueError("prospective session accounting must start after the landed serving freeze")
    if nxt <= session:
        raise ValueError("next_session_timestamp must follow session_timestamp")
    written = module._parse_utc(recorded_at or str(observation["next_session_timestamp"]))
    if written < nxt:
        raise ValueError("session observation cannot be recorded before next-session price exists")
    if not bool(observation["source_freshness_ok"] and observation["source_completeness_ok"]):
        raise ValueError("session accounting requires fresh and complete observed execution data")
    source_hash = str(observation["source_snapshot_sha256"])
    if _SHA256_RE.fullmatch(source_hash) is None:
        raise ValueError("session source_snapshot_sha256 must be a lowercase SHA-256 hex digest")
    current_contract = str(observation["contract_id"]).strip()
    next_contract = str(observation["next_selected_contract_id"]).strip()
    if not current_contract or not next_contract:
        raise ValueError("session contract identities must be non-empty")
    open_price = _finite_float(observation["open_price"], "open_price")
    next_open = _finite_float(observation["next_open_same_contract"], "next_open_same_contract")
    if open_price <= 0.0 or next_open <= 0.0:
        raise ValueError("session execution prices must be positive")

    state = _runtime_state(module, ledger)
    if state["last_next_session_timestamp"] is not None:
        expected = module._parse_utc(str(state["last_next_session_timestamp"]))
        if session != expected:
            raise ValueError("prospective session accounting must be chronological and gap-free")

    fresh = _decision_for_fill(module, ledger, session.isoformat())
    active_record_id = state["active_record_id"]
    active_forecast_id = state["active_forecast_id"]
    active_signal_position = float(state["active_signal_position"])
    active_signal_reason = str(state["active_signal_reason"])
    active_target_end = state["active_target_end_timestamp"]
    if fresh is not None:
        if str(fresh["contract_id"]) != current_contract:
            raise ValueError("planned decision contract does not match observed session contract")
        active_record_id = str(fresh["record_id"])
        active_forecast_id = str(fresh["forecast_id"])
        active_signal_position = float(fresh["intended_position"])
        active_signal_reason = str(fresh["skip_reason"] or "forecast_signal")
        active_target_end = str(fresh["target_end_timestamp"])
    elif active_target_end is not None:
        target_end = module._parse_utc(str(active_target_end))
        if session >= target_end:
            active_record_id = None
            active_forecast_id = None
            active_signal_position = 0.0
            active_signal_reason = "forecast_horizon_expired"
            active_target_end = None

    prior_position = float(state["prior_position"])
    risk_shutdown = str(state["risk_state"]) == "killed"
    target_position = 0.0 if risk_shutdown else active_signal_position
    no_trade_reason = active_signal_reason if target_position == 0.0 else None
    if risk_shutdown:
        no_trade_reason = "risk_killed_until_explicit_operator_restart"

    per_side, multiplier, margin = _cost_contract()
    equity_before = float(state["equity_usd"])
    if target_position != 0.0 and margin * abs(target_position) > equity_before:
        target_position = 0.0
        no_trade_reason = "insufficient_margin_assumption"
    previous_contract = state["prior_contract_id"]
    contract_changed = (
        prior_position != 0.0 and previous_contract is not None
        and str(previous_contract) != current_contract
    )
    order_delta = target_position - prior_position
    if contract_changed:
        execution_sides = abs(prior_position) + abs(target_position)
        roll_sides = execution_sides
    else:
        execution_sides = abs(order_delta)
        roll_sides = 0.0
    transaction_cost = execution_sides * per_side
    path_move = next_open - open_price
    gross_pnl = target_position * path_move * multiplier
    equity = equity_before - transaction_cost + gross_pnl
    net_pnl = gross_pnl - transaction_cost
    peak_equity = max(float(state["peak_equity_usd"]), equity)
    daily_loss = max(0.0, equity_before - equity)
    drawdown = 0.0 if peak_equity <= 0 else max(0.0, (peak_equity - equity) / peak_equity)

    risk = _risk_contract()
    trigger_reasons: list[str] = []
    if daily_loss >= float(risk["capital_usd"]) * float(risk["daily_loss_fraction"]):
        trigger_reasons.append("daily_loss_limit")
    if drawdown >= float(risk["peak_drawdown_kill_fraction"]):
        trigger_reasons.append("peak_drawdown_kill")
    risk_state = str(state["risk_state"])
    kill_reason = state["kill_reason"]
    if trigger_reasons and risk_state != "killed":
        risk_state = "killed"
        kill_reason = "+".join(trigger_reasons)

    event = {
        "event_type": "session",
        "recorded_at": written.isoformat(),
        "session_timestamp": session.isoformat(),
        "next_session_timestamp": nxt.isoformat(),
        "source_snapshot_sha256": source_hash,
        "contract_id": current_contract,
        "next_selected_contract_id": next_contract,
        "open_price": open_price,
        "next_open_same_contract": next_open,
        "path_move_per_mmbtu": path_move,
        "active_record_id": active_record_id,
        "active_forecast_id": active_forecast_id,
        "active_signal_position": active_signal_position,
        "active_signal_reason": active_signal_reason,
        "active_target_end_timestamp": active_target_end,
        "prior_target_position": prior_position,
        "target_position": target_position,
        "order_delta": order_delta,
        "execution_side_count": execution_sides,
        "roll_side_count": roll_sides,
        "transaction_cost_usd": transaction_cost,
        "gross_pnl_usd": gross_pnl,
        "net_pnl_usd": net_pnl,
        "equity_usd": equity,
        "peak_equity_usd": peak_equity,
        "daily_loss_usd": daily_loss,
        "drawdown_fraction": drawdown,
        "risk_shutdown": risk_shutdown,
        "risk_state": risk_state,
        "kill_reason": kill_reason,
        "no_trade_reason": no_trade_reason,
        "roll_at_open": contract_changed,
        "source_freshness_ok": True,
        "source_completeness_ok": True,
        "live_trading_allowed": False,
    }
    return module._append_prospective_event(event, ledger=ledger)


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
        "actual_contract_id",
        "actual_position",
        "fill_price",
        "transaction_cost_usd",
        "net_pnl_usd",
        "miss_reason",
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

    prior = _position(record["prior_position"], "prior_position")
    intended = _position(record["intended_position"], "intended_position")
    actual = _position(record["actual_position"], "actual_position")
    miss_reason = record["miss_reason"]
    if actual != intended and (miss_reason is None or not str(miss_reason).strip()):
        raise ValueError("actual_position drift from intended_position requires miss_reason")
    if actual == intended and miss_reason not in (None, ""):
        raise ValueError("matching actual/intended position cannot carry miss_reason")

    actual_contract_id = record["actual_contract_id"]
    if actual != 0.0 and (actual_contract_id is None or not str(actual_contract_id).strip()):
        raise ValueError("non-flat actual_position requires actual_contract_id")

    transaction_cost = _finite_float(record["transaction_cost_usd"], "transaction_cost_usd")
    if transaction_cost < 0:
        raise ValueError("transaction_cost_usd must be non-negative")
    _finite_float(record["net_pnl_usd"], "net_pnl_usd")

    position_change_completed = intended != prior and actual == intended
    if position_change_completed and record["fill_price"] is None:
        raise ValueError("completed position change requires fill_price")
    if record["fill_price"] is not None:
        fill_price = _finite_float(record["fill_price"], "fill_price")
        if fill_price <= 0:
            raise ValueError("fill_price must be positive when present")

    settlement = dict(record)
    settlement["skip_or_miss_reason"] = (
        miss_reason if miss_reason not in (None, "") else decision["skip_reason"]
    )
    return module.append_prospective_outcome(
        settlement,
        ledger=ledger,
        recorded_at=recorded_at,
    )


def ledger_status(ledger: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    module = _phase7_module()
    tail_hash, events = module._read_prospective_events(ledger)
    decisions = [event for event in events if event.get("event_type") == "decision"]
    outcomes = [event for event in events if event.get("event_type") == "outcome"]
    sessions = [event for event in events if event.get("event_type") == "session"]
    settled_ids = {str(event["record_id"]) for event in outcomes}
    pending = [event for event in decisions if str(event["record_id"]) not in settled_ids]

    active = [event for event in outcomes if abs(float(event["actual_position"])) > 0.0]
    long_count = sum(float(event["actual_position"]) > 0.0 for event in active)
    short_count = sum(float(event["actual_position"]) < 0.0 for event in active)
    episode_net_pnl = sum(float(event["net_pnl_usd"]) for event in outcomes)
    session_net_pnl = sum(float(event["net_pnl_usd"]) for event in sessions)
    transaction_cost = sum(float(event["transaction_cost_usd"]) for event in sessions)
    max_daily_loss = max((float(event["daily_loss_usd"]) for event in sessions), default=0.0)
    max_drawdown = max((float(event["drawdown_fraction"]) for event in sessions), default=0.0)
    risk = _risk_contract()
    capital = float(risk["capital_usd"])
    risk_state = str(sessions[-1]["risk_state"]) if sessions else "active"
    ending_equity = float(sessions[-1]["equity_usd"]) if sessions else capital
    kill_triggered = any(str(event["risk_state"]) == "killed" for event in sessions)
    unauthorized_restarts = 0
    previously_killed = False
    for event in sessions:
        if previously_killed and abs(float(event["target_position"])) > 0.0:
            unauthorized_restarts += 1
        previously_killed = previously_killed or str(event["risk_state"]) == "killed"
    first_decision = min((str(event["decision_timestamp"]) for event in decisions), default=None)
    contract = _load_json(CONTRACT)
    serving = contract.get("prospective_serving_contract", {})

    return {
        "ledger": str(ledger),
        "phase7_status": contract.get("status"),
        "prospective_serving_status": serving.get("status") if isinstance(serving, dict) else None,
        "tail_record_sha256": tail_hash,
        "decision_events": len(decisions),
        "settled_outcomes": len(outcomes),
        "pending_decisions": len(pending),
        "session_events": len(sessions),
        "active_exposure_outcomes": len(active),
        "long_exposure_outcomes": int(long_count),
        "short_exposure_outcomes": int(short_count),
        "episode_outcome_net_pnl_usd": float(episode_net_pnl),
        "net_pnl_usd": float(session_net_pnl),
        "transaction_cost_usd": float(transaction_cost),
        "ending_equity_usd": ending_equity,
        "max_daily_loss_usd": max_daily_loss,
        "max_daily_loss_fraction": 0.0 if capital <= 0 else max_daily_loss / capital,
        "max_drawdown_fraction": max_drawdown,
        "risk_state": risk_state,
        "kill_triggered": kill_triggered,
        "unauthorized_post_kill_restart_count": unauthorized_restarts,
        "economic_evidence_source": "daily_session_ledger",
        "first_decision_timestamp": first_decision,
        "phase8_entry_eligible": False,
        "eligibility_note": (
            "Daily session accounting is the economic/risk evidence source. Phase-8 eligibility "
            "still requires the frozen 365-day, independent-episode, directional-exposure and "
            "logging-fidelity gates; this status command never promotes Phase 8 by itself."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the frozen Phase-7 prospective evidence ledger")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    sub = parser.add_subparsers(dest="command", required=True)

    decision = sub.add_parser(
        "derive-decision",
        help="derive the frozen candidate from verified decision-time inputs and persist it",
    )
    decision.add_argument("bundle", type=Path)
    decision.add_argument("--checkpoint-root", type=Path, required=True)
    decision.add_argument("--databento-root", type=Path, required=True)

    session = sub.add_parser(
        "derive-session",
        help="derive one daily execution/risk-accounting interval from verified market data",
    )
    session.add_argument("bundle", type=Path)
    session.add_argument("--databento-root", type=Path, required=True)

    sub.add_parser("status", help="validate the hash chain and report operational counters")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "derive-decision":
        result = derive_and_append_decision(
            _load_json(args.bundle),
            checkpoint_root=args.checkpoint_root,
            databento_root=args.databento_root,
            ledger=args.ledger,
        )
    elif args.command == "derive-session":
        result = derive_and_append_session_observation(
            _load_json(args.bundle),
            databento_root=args.databento_root,
            ledger=args.ledger,
        )
    else:
        result = ledger_status(args.ledger)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
