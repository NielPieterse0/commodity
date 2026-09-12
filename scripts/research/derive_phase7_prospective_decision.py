from __future__ import annotations

import hashlib
import json
import math
import re
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.market_only_phase2 import (
    _build_segmented_decision_origins,
    _candidate_model,
    _canonicalize_one_origin_per_fill,
    _forecast_id,
    _frame_sha256,
)
from commodity.stacking_policy import PolicyConfig, apply_specialist_modifiers
from commodity.trading_decision_v0 import ExecutionCostAssumptions

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME = ROOT / "research" / "programmes" / "003-natural-gas-trading-decision-system"
PHASE2_CONFIG = ROOT / "config" / "phase2_market_only.json"
MODELS_CONFIG = ROOT / "config" / "models.json"
PHASE2_BASELINE = PROGRAMME / "phase2-market-only-baseline-v1.json"
PHASE7_CONTRACT = PROGRAMME / "phase7-frozen-evaluation-v1.json"
CANDIDATE_ID = "histgb-core-v1"
POLICY_ID = "s-veto__l-none__p-half__u-none"
PROTECTED_START = pd.Timestamp("2023-01-01T00:00:00Z")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ARCHIVE_RE = re.compile(
    r"glbx-mdp3-(\d{8})-(\d{8})\.(definition|statistics|ohlcv-1d)\.dbn\.zst$"
)
_DATABENTO_SCHEMAS = ("definition", "statistics", "ohlcv-1d")


class DecisionDerivationError(ValueError):
    """Raised when a prospective decision cannot be derived from frozen inputs."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DecisionDerivationError(f"expected JSON object: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc(value: object, label: str) -> pd.Timestamp:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise DecisionDerivationError(f"{label} must be a timezone-aware timestamp")
    return pd.Timestamp(parsed)


def _finite(value: object, label: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise DecisionDerivationError(f"{label} must be finite")
    return parsed


def frozen_feature_columns() -> list[str]:
    baseline = _load_json(PHASE2_BASELINE)["baseline_freeze"]
    columns = baseline.get("feature_columns")
    if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns):
        raise DecisionDerivationError("frozen Phase-2 feature columns are invalid")
    return list(columns)


def _frozen_candidate() -> dict[str, Any]:
    cfg = _load_json(PHASE2_CONFIG)
    matches = [item for item in cfg["candidates"] if item.get("id") == CANDIDATE_ID]
    if len(matches) != 1:
        raise DecisionDerivationError("frozen Phase-2 candidate identity is unavailable")
    baseline = _load_json(PHASE2_BASELINE)["baseline_freeze"]
    if matches[0] != baseline["candidate"]:
        raise DecisionDerivationError("frozen Phase-2 candidate configuration drifted")
    if list(cfg["feature_sets"]["core"]) != frozen_feature_columns():
        raise DecisionDerivationError("frozen core feature set drifted")
    return matches[0]


def _base_costs() -> ExecutionCostAssumptions:
    cfg = _load_json(PHASE2_CONFIG)
    profile = cfg["cost_profiles"]["base"]
    return ExecutionCostAssumptions(
        commission_usd_per_side=float(profile["commission_usd_per_side"]),
        exchange_clearing_fees_usd_per_side=float(profile["exchange_clearing_fees_usd_per_side"]),
        half_spread_ticks_per_side=float(profile["half_spread_ticks_per_side"]),
        slippage_ticks_per_side=float(profile["slippage_ticks_per_side"]),
        initial_margin_usd_per_contract=float(profile["initial_margin_usd_per_contract"]),
        tick_value_usd=float(cfg["execution_contract"]["tick_value_usd"]),
    )


def _frozen_policy() -> PolicyConfig:
    return PolicyConfig(
        config_id=POLICY_ID,
        short_mode="veto",
        long_mode="none",
        path_mode="half",
        uncertainty_mode="none",
    )


def prospective_kronos_path_eligible(origin_sequence_index: int) -> bool:
    if origin_sequence_index < 0:
        raise DecisionDerivationError("prospective origin sequence index must be non-negative")
    serving = _load_json(PHASE7_CONTRACT).get("prospective_serving_contract")
    if not isinstance(serving, dict):
        raise DecisionDerivationError("prospective serving contract is unavailable")
    rule = serving.get("kronos_path_availability")
    if not isinstance(rule, dict):
        raise DecisionDerivationError("prospective Kronos path-availability rule is unavailable")
    cycle = int(rule.get("cycle_length", 0))
    residues = rule.get("active_residues_zero_based")
    if cycle <= 0 or not isinstance(residues, list):
        raise DecisionDerivationError("prospective Kronos path-availability rule is invalid")
    active = {int(value) for value in residues}
    if any(value < 0 or value >= cycle for value in active):
        raise DecisionDerivationError("prospective Kronos path residues are outside the cycle")
    return origin_sequence_index % cycle in active


def _validate_specialist_identity(specialists: dict[str, Any]) -> None:
    models = _load_json(MODELS_CONFIG)["models"]
    timesfm = models["timesfm_2_5"]
    kronos = models["kronos_base"]
    expected = {
        "timesfm_model_id": timesfm["model_id"],
        "timesfm_model_revision": timesfm["model_revision"],
        "timesfm_checkpoint_sha256": timesfm["checkpoint_artifacts"]["model"]["sha256"],
        "kronos_model_id": kronos["model_id"],
        "kronos_model_revision": kronos["model_revision"],
        "kronos_model_checkpoint_sha256": kronos["checkpoint_artifacts"]["model"]["sha256"],
        "kronos_tokenizer_revision": kronos["tokenizer_revision"],
        "kronos_tokenizer_checkpoint_sha256": kronos["checkpoint_artifacts"]["tokenizer"]["sha256"],
        "kronos_inference_profile": "upstream_usage_defaults",
    }
    for key, value in expected.items():
        if specialists.get(key) != value:
            raise DecisionDerivationError(f"specialist identity mismatch: {key}")


def load_verified_training_origins(checkpoint_root: Path) -> pd.DataFrame:
    baseline = _load_json(PHASE2_BASELINE)["baseline_freeze"]
    cfg = _load_json(PHASE2_CONFIG)
    features_path = checkpoint_root / "inputs" / "features.parquet"
    session_path = checkpoint_root / "inputs" / "session-path.parquet"
    if not features_path.is_file() or not session_path.is_file():
        raise DecisionDerivationError("frozen Phase-2 checkpoint inputs are missing")
    features = pd.read_parquet(features_path)
    session = pd.read_parquet(session_path)
    if _frame_sha256(features) != baseline["features_sha256"]:
        raise DecisionDerivationError("frozen Phase-2 feature checkpoint hash mismatch")
    if _frame_sha256(session) != baseline["session_path_sha256"]:
        raise DecisionDerivationError("frozen Phase-2 session checkpoint hash mismatch")
    origins, _ = _build_segmented_decision_origins(
        session,
        features,
        horizon_sessions=int(cfg["execution_contract"]["horizon_sessions"]),
    )
    origins, _ = _canonicalize_one_origin_per_fill(origins)
    target_end = pd.to_datetime(origins["target_end_timestamp"], utc=True, errors="coerce")
    if target_end.isna().any() or (target_end >= PROTECTED_START).any():
        raise DecisionDerivationError("training targets must remain fully inside 2022 or earlier")
    return origins.reset_index(drop=True)


def preflight_databento_freshness(
    databento_root: Path, *, required_trade_date: pd.Timestamp
) -> dict[str, Any]:
    required = _utc(required_trade_date, "required_trade_date").normalize()
    latest: pd.Timestamp | None = None
    for path in Path(databento_root).rglob("*.ohlcv-1d.dbn.zst"):
        match = _ARCHIVE_RE.search(path.name)
        if match is None:
            continue
        candidate = pd.Timestamp(match.group(2), tz="UTC")
        latest = candidate if latest is None or candidate > latest else latest
    if latest is None:
        return {"fresh": False, "latest_trade_date": None, "reason": "prospective_market_source_missing"}
    fresh = latest >= required
    return {
        "fresh": bool(fresh),
        "latest_trade_date": latest.date().isoformat(),
        "reason": None if fresh else "prospective_market_source_stale",
    }


def verified_databento_source_snapshot(
    databento_root: Path, *, required_trade_date: pd.Timestamp
) -> dict[str, Any]:
    """Bind one decision to exact complete Databento partition triples on disk."""
    root = Path(databento_root).resolve()
    required = _utc(required_trade_date, "required_trade_date").normalize()
    selected: list[dict[str, str]] = []
    selected_key: tuple[str, str] | None = None
    latest_dates: list[pd.Timestamp] = []

    for schema in _DATABENTO_SCHEMAS:
        candidates: list[tuple[pd.Timestamp, pd.Timestamp, Path]] = []
        for path in sorted((root / schema).glob("*/*.dbn.zst")):
            match = _ARCHIVE_RE.fullmatch(path.name)
            if match is None or match.group(3) != schema:
                continue
            start = pd.Timestamp(match.group(1), tz="UTC")
            end = pd.Timestamp(match.group(2), tz="UTC")
            candidates.append((start, end, path.resolve()))
        if not candidates:
            raise DecisionDerivationError(f"prospective Databento {schema} source is missing")
        latest_dates.append(max(end for _, end, _ in candidates))
        covering = [item for item in candidates if item[0] <= required <= item[1]]
        if len(covering) != 1:
            raise DecisionDerivationError(
                f"prospective Databento {schema} source must have exactly one partition covering "
                f"{required.date().isoformat()}"
            )
        start, end, path = covering[0]
        key = (start.date().isoformat(), end.date().isoformat())
        if selected_key is None:
            selected_key = key
        elif key != selected_key:
            raise DecisionDerivationError(
                "prospective Databento definition/statistics/OHLCV partitions are not aligned"
            )
        selected.append(
            {
                "schema": schema,
                "path": path.relative_to(root).as_posix(),
                "sha256": _file_sha256(path),
                "start_trade_date": key[0],
                "end_trade_date": key[1],
            }
        )

    latest = min(latest_dates)
    if latest < required:
        raise DecisionDerivationError("prospective Databento source is stale")
    manifest = {
        "schema_version": 1,
        "provider": "databento",
        "dataset": "GLBX.MDP3",
        "required_trade_date": required.date().isoformat(),
        "partition_key": None if selected_key is None else list(selected_key),
        "files": selected,
    }
    return {
        "sha256": _json_sha256(manifest),
        "latest_trade_date": latest.date().isoformat(),
        "complete": True,
        "manifest": manifest,
    }


_CALLER_OUTPUT_FIELDS = {
    "record_id", "target_end_timestamp", "candidate_config_id", "phase7_contract_sha256",
    "input_snapshot_sha256", "forecast_id", "predicted_gross_pnl_usd", "baseline_position",
    "prior_position", "intended_position", "policy_modifiers", "fill_rule", "cost_profile_id",
    "risk_state", "source_freshness_ok", "source_completeness_ok", "skip_reason",
}
_OUTCOME_FIELDS = {
    "outcome_timestamp", "actual_contract_id", "actual_position", "fill_price",
    "transaction_cost_usd", "net_pnl_usd", "miss_reason", "actual_path_move_per_mmbtu",
    "actual_gross_pnl_usd", "target_path_move_per_mmbtu",
}


def _validated_bundle(
    bundle: dict[str, Any], *, origin_sequence_index: int
) -> dict[str, Any]:
    forbidden_output = sorted(_CALLER_OUTPUT_FIELDS.intersection(bundle))
    if forbidden_output:
        raise DecisionDerivationError(
            f"caller-supplied decision output is forbidden: {forbidden_output}"
        )
    forbidden_outcome = sorted(_OUTCOME_FIELDS.intersection(bundle))
    if forbidden_outcome:
        raise DecisionDerivationError(f"outcome field is forbidden at decision time: {forbidden_outcome}")
    required = {
        "decision_timestamp", "planned_fill_timestamp", "target_session_timestamps",
        "current_origin", "specialists", "source_snapshot",
    }
    missing = sorted(required.difference(bundle))
    if missing:
        raise DecisionDerivationError(f"prospective derivation bundle missing fields: {missing}")
    decision = _utc(bundle["decision_timestamp"], "decision_timestamp")
    planned_fill = _utc(bundle["planned_fill_timestamp"], "planned_fill_timestamp")
    if planned_fill <= decision:
        raise DecisionDerivationError("planned fill must occur strictly after the decision")
    freeze = _utc(_load_json(PHASE7_CONTRACT)["freeze_landing"]["merged_at"], "freeze landing")
    if decision <= freeze:
        raise DecisionDerivationError("decision must occur strictly after the landed Phase-7 freeze")
    horizon = bundle["target_session_timestamps"]
    if not isinstance(horizon, list) or len(horizon) != 5:
        raise DecisionDerivationError("prospective target must contain exactly five future sessions")
    horizon_times = [_utc(value, "target session timestamp") for value in horizon]
    if any(right <= left for left, right in pairwise(horizon_times)):
        raise DecisionDerivationError("target session timestamps must be strictly increasing")
    if horizon_times[0] <= planned_fill:
        raise DecisionDerivationError("target sessions must occur after the planned fill")

    origin = bundle["current_origin"]
    specialists = bundle["specialists"]
    source = bundle["source_snapshot"]
    if not isinstance(origin, dict) or not isinstance(specialists, dict) or not isinstance(source, dict):
        raise DecisionDerivationError("current_origin, specialists and source_snapshot must be objects")
    if _OUTCOME_FIELDS.intersection(origin) or _OUTCOME_FIELDS.intersection(specialists):
        raise DecisionDerivationError("outcome field is forbidden inside decision-time inputs")
    for key in ("trade_date", "available_at", "contract_id", "features"):
        if key not in origin:
            raise DecisionDerivationError(f"current_origin missing field: {key}")
    available = _utc(origin["available_at"], "current_origin.available_at")
    if available > decision:
        raise DecisionDerivationError("current origin is not available at decision time")
    if not str(origin["contract_id"]).strip():
        raise DecisionDerivationError("current origin contract_id must be non-empty")
    features = origin["features"]
    if not isinstance(features, dict) or set(features) != set(frozen_feature_columns()):
        raise DecisionDerivationError("current origin must contain exactly the frozen core features")
    for name in frozen_feature_columns():
        _finite(features[name], name)

    for key in ("sha256", "latest_trade_date", "complete"):
        if key not in source:
            raise DecisionDerivationError(f"source_snapshot missing field: {key}")
    if _SHA_RE.fullmatch(str(source["sha256"])) is None:
        raise DecisionDerivationError("source snapshot SHA-256 is invalid")
    if not isinstance(source["complete"], bool):
        raise DecisionDerivationError("source snapshot completeness must be boolean")
    latest_trade_date = _utc(source["latest_trade_date"], "source latest_trade_date").normalize()
    origin_trade_date = _utc(origin["trade_date"], "current_origin.trade_date").normalize()
    source_freshness_ok = bool(latest_trade_date >= origin_trade_date)
    source_completeness_ok = bool(source["complete"])
    sources_ok = source_freshness_ok and source_completeness_ok

    required_specialists = {
        "prediction_time",
        "timesfm_point_return",
        "timesfm_interval_width",
        "timesfm_model_id",
        "timesfm_model_revision",
        "timesfm_checkpoint_sha256",
        "kronos_close_return",
        "kronos_terminal_return",
        "kronos_path_generated",
        "kronos_model_id",
        "kronos_model_revision",
        "kronos_model_checkpoint_sha256",
        "kronos_tokenizer_revision",
        "kronos_tokenizer_checkpoint_sha256",
        "kronos_inference_profile",
    }
    if set(specialists) != required_specialists:
        raise DecisionDerivationError("specialist decision inputs do not match the frozen policy contract")
    _validate_specialist_identity(specialists)
    prediction_time = _utc(specialists["prediction_time"], "specialist prediction_time")
    if prediction_time > decision or prediction_time != available:
        raise DecisionDerivationError("specialist outputs must be aligned to the frozen decision origin")
    for key in ("timesfm_point_return", "timesfm_interval_width", "kronos_close_return"):
        _finite(specialists[key], key)
    if not isinstance(specialists["kronos_path_generated"], bool):
        raise DecisionDerivationError("kronos_path_generated must be boolean")
    path_expected = prospective_kronos_path_eligible(origin_sequence_index) if sources_ok else False
    if bool(specialists["kronos_path_generated"]) != path_expected:
        raise DecisionDerivationError("Kronos path generation does not match the preregistered cadence")
    terminal = specialists["kronos_terminal_return"]
    if path_expected:
        _finite(terminal, "kronos_terminal_return")
    elif terminal is not None:
        raise DecisionDerivationError("inactive Kronos path origin must keep terminal return unavailable")

    normalized = json.loads(json.dumps(bundle))
    normalized["decision_timestamp"] = decision.isoformat()
    normalized["planned_fill_timestamp"] = planned_fill.isoformat()
    normalized["target_session_timestamps"] = [value.isoformat() for value in horizon_times]
    normalized["current_origin"]["available_at"] = available.isoformat()
    normalized["current_origin"]["trade_date"] = origin_trade_date.isoformat()
    normalized["specialists"]["prediction_time"] = prediction_time.isoformat()
    normalized["source_snapshot"]["latest_trade_date"] = latest_trade_date.date().isoformat()
    normalized["source_freshness_ok"] = source_freshness_ok
    normalized["source_completeness_ok"] = source_completeness_ok
    normalized["path_counter_advanced"] = sources_ok
    normalized["prospective_origin_index"] = origin_sequence_index if sources_ok else None
    normalized["kronos_path_eligible"] = path_expected
    return normalized


def _validate_training_origins(training_origins: pd.DataFrame) -> pd.DataFrame:
    required = {*frozen_feature_columns(), "target_path_move_per_mmbtu", "target_end_timestamp"}
    missing = sorted(required.difference(training_origins.columns))
    if missing:
        raise DecisionDerivationError(f"training origins missing fields: {missing}")
    frame = training_origins.copy()
    target_end = pd.to_datetime(frame["target_end_timestamp"], utc=True, errors="coerce")
    if target_end.isna().any() or (target_end >= PROTECTED_START).any():
        raise DecisionDerivationError("training targets must remain fully inside 2022 or earlier")
    values = frame[frozen_feature_columns()].apply(pd.to_numeric, errors="coerce")
    target = pd.to_numeric(frame["target_path_move_per_mmbtu"], errors="coerce")
    if values.isna().any().any() or target.isna().any():
        raise DecisionDerivationError("training origins contain non-numeric values")
    return frame


def derive_decision(
    bundle: dict[str, Any],
    *,
    training_origins: pd.DataFrame,
    prior_position: float = 0.0,
    risk_state: str = "active",
    origin_sequence_index: int = 0,
) -> dict[str, Any]:
    normalized = _validated_bundle(bundle, origin_sequence_index=origin_sequence_index)
    training = _validate_training_origins(training_origins)
    candidate = _frozen_candidate()
    feature_columns = frozen_feature_columns()
    model = _candidate_model(candidate)
    if model is None:
        raise DecisionDerivationError("frozen market baseline must be a fitted model")
    model.fit(training[feature_columns], training["target_path_move_per_mmbtu"].astype(float))
    current = pd.DataFrame([normalized["current_origin"]["features"]], columns=feature_columns)
    prediction = float(model.predict(current).iloc[0])
    multiplier = float(_load_json(PHASE2_CONFIG)["execution_contract"]["contract_multiplier_mmbtu"])
    predicted_gross = prediction * multiplier
    costs = _base_costs()
    if abs(predicted_gross) <= costs.round_trip_usd:
        baseline_position = 0.0
        baseline_skip = "predicted_gross_pnl_not_above_round_trip_cost"
    else:
        baseline_position = 1.0 if predicted_gross > 0 else -1.0
        baseline_skip = None

    specialists = normalized["specialists"]
    terminal_value = specialists["kronos_terminal_return"]
    policy = apply_specialist_modifiers(
        baseline_position=baseline_position,
        timesfm_point_return=float(specialists["timesfm_point_return"]),
        kronos_close_return=float(specialists["kronos_close_return"]),
        kronos_terminal_return=None if terminal_value is None else float(terminal_value),
        timesfm_interval_width=float(specialists["timesfm_interval_width"]),
        config=_frozen_policy(),
        uncertainty_state=None,
    )
    sources_ok = bool(normalized["source_freshness_ok"] and normalized["source_completeness_ok"])
    intended = float(policy.position) if sources_ok and risk_state == "active" else 0.0
    if not sources_ok:
        skip_reason = "source_stale_or_incomplete"
    elif risk_state != "active":
        skip_reason = "risk_killed_until_explicit_operator_restart"
    elif intended == 0.0:
        skip_reason = baseline_skip or "specialist_veto"
    else:
        skip_reason = None

    decision = _utc(normalized["decision_timestamp"], "decision_timestamp")
    planned_fill = _utc(normalized["planned_fill_timestamp"], "planned_fill_timestamp")
    input_hash = _json_sha256(normalized)
    contract_id = str(normalized["current_origin"]["contract_id"])
    phase7 = _load_json(PHASE7_CONTRACT)
    serving = phase7["prospective_serving_contract"]
    record_seed = {
        "candidate": POLICY_ID,
        "serving_deployment_identity": serving["deployment_identity"],
        "decision_timestamp": decision.isoformat(),
        "planned_fill_timestamp": planned_fill.isoformat(),
        "contract_id": contract_id,
        "prospective_origin_index": normalized["prospective_origin_index"],
        "input_snapshot_sha256": input_hash,
    }
    cfg = _load_json(PHASE2_CONFIG)
    return {
        "record_id": _json_sha256(record_seed)[:24],
        "decision_timestamp": decision.isoformat(),
        "planned_fill_timestamp": planned_fill.isoformat(),
        "target_end_timestamp": normalized["target_session_timestamps"][-1],
        "horizon_sessions": 5,
        "candidate_config_id": POLICY_ID,
        "prospective_serving_deployment_id": str(serving["deployment_identity"]),
        "prospective_origin_index": normalized["prospective_origin_index"],
        "path_counter_advanced": bool(normalized["path_counter_advanced"]),
        "kronos_path_eligible": bool(normalized["kronos_path_eligible"]),
        "phase7_contract_sha256": _file_sha256(PHASE7_CONTRACT),
        "input_snapshot_sha256": input_hash,
        "decision_input_snapshot": normalized,
        "source_snapshot_sha256": str(normalized["source_snapshot"]["sha256"]),
        "forecast_id": _forecast_id(CANDIDATE_ID, planned_fill),
        "market_model_id": CANDIDATE_ID,
        "predicted_path_move_per_mmbtu": prediction,
        "predicted_gross_pnl_usd": predicted_gross,
        "baseline_position": baseline_position,
        "prior_position": float(prior_position),
        "intended_position": intended,
        "policy_modifiers": list(policy.modifiers),
        "contract_id": contract_id,
        "fill_rule": str(cfg["execution_contract"]["execution_open_rule"]),
        "cost_profile_id": "base",
        "risk_state": str(risk_state),
        "source_freshness_ok": bool(normalized["source_freshness_ok"]),
        "source_completeness_ok": bool(normalized["source_completeness_ok"]),
        "skip_reason": skip_reason,
        "derivation": {
            "method": "phase7_frozen_candidate_v1",
            "serving_deployment_identity": str(serving["deployment_identity"]),
            "phase2_freeze_sha256": str(_load_json(PHASE2_BASELINE)["baseline_freeze"]["freeze_sha256"]),
            "policy_refit_cadence": str(phase7["frozen_candidate"]["policy_refit_cadence"]),
            "training_cutoff": "2022-12-31",
            "origin_sequence_index": normalized["prospective_origin_index"],
            "kronos_path_eligible": bool(normalized["kronos_path_eligible"]),
            "kronos_path_cycle_length": int(serving["kronos_path_availability"]["cycle_length"]),
            "kronos_path_active_residues": list(serving["kronos_path_availability"]["active_residues_zero_based"]),
            "outcome_fields_consumed": False,
        },
    }
