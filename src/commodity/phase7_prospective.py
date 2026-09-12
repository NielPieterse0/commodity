from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd

from commodity.models.baselines import HistGradientBoostingReturnModel


class Phase7ProspectiveError(ValueError):
    """Raised when prospective inference would violate the frozen evidence boundary."""


_FROZEN_DEVELOPMENT_CUTOFF = pd.Timestamp("2023-01-01T00:00:00Z")
_FROZEN_PHASE7_LANDING = pd.Timestamp("2026-09-12T04:30:20Z")
_FROZEN_CONTRACT_MULTIPLIER = 10_000.0
_FROZEN_MIN_TRAIN_ROWS = 504
_FROZEN_HORIZON_SESSIONS = 5
_FROZEN_CORE_FEATURES = [
    "feature_ret_1",
    "feature_ret_5",
    "feature_ret_20",
    "feature_vol_5",
    "feature_vol_20",
    "feature_range_pct",
    "feature_ma_gap_5",
    "feature_ma_gap_20",
    "feature_season_sin",
    "feature_season_cos",
    "feature_selected_dte",
    "feature_roll_event",
]
_FORBIDDEN_CURRENT_OUTCOMES = {
    "target_path_move_per_mmbtu",
    "actual_path_move_per_mmbtu",
    "actual_gross_pnl_usd",
    "net_pnl_usd",
}


def _utc_series(frame: pd.DataFrame, column: str, label: str) -> pd.Series:
    values = pd.to_datetime(frame[column], utc=True, errors="coerce")
    if values.isna().any():
        raise Phase7ProspectiveError(f"{label} contains invalid {column}")
    return values


def _finite_features(frame: pd.DataFrame, columns: list[str], label: str) -> pd.DataFrame:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise Phase7ProspectiveError(f"{label} missing frozen features: {missing}")
    result = frame[columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(result.to_numpy(dtype=float)).all():
        raise Phase7ProspectiveError(f"{label} contains non-finite frozen features")
    return result


def _frame_sha256(frame: pd.DataFrame, columns: list[str]) -> str:
    normalized = frame[columns].copy()
    for column in columns:
        if "timestamp" in column or column.endswith("_date"):
            parsed = pd.to_datetime(normalized[column], utc=True, errors="coerce")
            if parsed.notna().all():
                normalized[column] = parsed.map(lambda value: value.isoformat())
    payload = normalized.to_json(
        orient="records",
        date_format="iso",
        date_unit="us",
        double_precision=15,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate(candidate: dict[str, Any]) -> HistGradientBoostingReturnModel:
    if str(candidate.get("id")) != "histgb-core-v1":
        raise Phase7ProspectiveError("Phase 7 market baseline must remain histgb-core-v1")
    if str(candidate.get("model")) != "hist_gb" or str(candidate.get("feature_set")) != "core":
        raise Phase7ProspectiveError("Phase 7 market baseline identity drift")
    params = dict(candidate.get("parameters", {}))
    expected = {
        "learning_rate": 0.05,
        "max_iter": 20,
        "max_leaf_nodes": 15,
        "random_state": 0,
    }
    observed = {
        "learning_rate": float(params.get("learning_rate", 0.05)),
        "max_iter": int(params.get("max_iter", 20)),
        "max_leaf_nodes": int(params.get("max_leaf_nodes", 15)),
        "random_state": int(params.get("random_state", 0)),
    }
    if observed != expected:
        raise Phase7ProspectiveError("Phase 7 histgb-core-v1 parameters drifted from the freeze")
    return HistGradientBoostingReturnModel(**observed)


def forecast_frozen_market_baseline(
    training_origins: pd.DataFrame,
    current_origin: pd.DataFrame,
    candidate: dict[str, Any],
    feature_columns: list[str],
) -> pd.DataFrame:
    """Fit only on frozen pre-2023 outcomes and forecast one outcome-blind live origin.

    The Phase-7 landing timestamp, five-session horizon, 10,000 MMBtu multiplier,
    504-row minimum, core feature set, candidate identity and model parameters are
    fixed here rather than caller-controlled. `training_origins` must contain only
    the already-consumed development sample. The current origin must not contain
    any realized target/P&L value. Supplying any reserved 2023+ outcome fails closed.
    """
    if feature_columns != _FROZEN_CORE_FEATURES:
        raise Phase7ProspectiveError("Phase 7 market feature set drifted from frozen core")
    if len(current_origin) != 1:
        raise Phase7ProspectiveError("prospective market forecast requires exactly one current origin")

    training_identity = [
        "trade_date",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "fill_contract_id",
        "target_end_timestamp",
        "target_path_move_per_mmbtu",
        *feature_columns,
    ]
    missing_training = sorted(set(training_identity) - set(training_origins.columns))
    if missing_training:
        raise Phase7ProspectiveError(f"training origins missing columns: {missing_training}")
    training = training_origins.copy()
    for column in (
        "trade_date",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "target_end_timestamp",
    ):
        training[column] = _utc_series(training, column, "training origins")
    if (training["target_end_timestamp"] >= _FROZEN_DEVELOPMENT_CUTOFF).any():
        raise Phase7ProspectiveError(
            "reserved 2023+ outcomes are forbidden in prospective baseline fitting"
        )
    if len(training) < _FROZEN_MIN_TRAIN_ROWS:
        raise Phase7ProspectiveError(
            f"prospective baseline has {len(training)} training rows; "
            f"requires {_FROZEN_MIN_TRAIN_ROWS}"
        )
    if training["fill_contract_id"].astype(str).str.strip().eq("").any():
        raise Phase7ProspectiveError("training origins contain empty fill contract identity")
    y_train = pd.to_numeric(training["target_path_move_per_mmbtu"], errors="coerce")
    if not np.isfinite(y_train.to_numpy(dtype=float)).all():
        raise Phase7ProspectiveError("training outcomes contain non-finite values")
    x_train = _finite_features(training, feature_columns, "training origins")

    current = current_origin.copy()
    current_identity = [
        "trade_date",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "fill_contract_id",
        "target_end_timestamp",
        *feature_columns,
    ]
    missing_current = sorted(set(current_identity) - set(current.columns))
    if missing_current:
        raise Phase7ProspectiveError(f"current origin missing columns: {missing_current}")
    for column in _FORBIDDEN_CURRENT_OUTCOMES.intersection(current.columns):
        if current[column].notna().any():
            raise Phase7ProspectiveError(f"current origin must be outcome-blind: {column}")

    for column in (
        "trade_date",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "target_end_timestamp",
    ):
        current[column] = _utc_series(current, column, "current origin")
    row = current.iloc[0]
    signal = pd.Timestamp(row["signal_timestamp"])
    fill = pd.Timestamp(row["fill_timestamp"])
    target_end = pd.Timestamp(row["target_end_timestamp"])
    if signal <= _FROZEN_PHASE7_LANDING:
        raise Phase7ProspectiveError(
            "prospective baseline signal must occur strictly after landed freeze"
        )
    if fill <= signal:
        raise Phase7ProspectiveError("prospective fill must occur strictly after signal availability")
    if target_end <= fill:
        raise Phase7ProspectiveError("prospective target end must follow the executable fill")
    if not str(row["fill_contract_id"]).strip():
        raise Phase7ProspectiveError("prospective fill contract must be known at decision time")
    x_current = _finite_features(current, feature_columns, "current origin")

    model = _candidate(candidate)
    model.fit(x_train, y_train.astype(float))
    prediction = float(model.predict(x_current).iloc[0])
    train_prediction = model.predict(x_train).to_numpy(dtype=float)
    residual = y_train.to_numpy(dtype=float) - train_prediction
    uncertainty = float(np.std(residual, ddof=1)) if len(residual) > 1 else 0.0
    if not math.isfinite(prediction) or not math.isfinite(uncertainty):
        raise Phase7ProspectiveError("prospective baseline produced a non-finite forecast")

    training_ordered = training.sort_values(
        ["target_end_timestamp", "fill_timestamp", "fill_contract_id"], kind="stable"
    ).reset_index(drop=True)
    training_sha256 = _frame_sha256(training_ordered, training_identity)
    current_sha256 = _frame_sha256(current, current_identity)
    input_payload = json.dumps(
        {
            "candidate_id": str(candidate["id"]),
            "training_sha256": training_sha256,
            "current_origin_sha256": current_sha256,
            "horizon_sessions": _FROZEN_HORIZON_SESSIONS,
            "contract_multiplier": _FROZEN_CONTRACT_MULTIPLIER,
            "freeze_landed_at": _FROZEN_PHASE7_LANDING.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    input_snapshot_sha256 = hashlib.sha256(input_payload.encode("utf-8")).hexdigest()
    forecast_payload = (
        f"phase7-prospective-market-v1\0{candidate['id']}\0{fill.isoformat()}\0"
        f"{input_snapshot_sha256}"
    )
    forecast_id = hashlib.sha256(forecast_payload.encode("utf-8")).hexdigest()[:20]

    output = current.copy()
    output["candidate_id"] = str(candidate["id"])
    output["model_id"] = str(candidate["id"])
    output["prediction"] = prediction
    output["predicted_path_move_per_mmbtu"] = prediction
    output["predicted_gross_pnl_usd"] = prediction * _FROZEN_CONTRACT_MULTIPLIER
    output["uncertainty_per_mmbtu"] = uncertainty
    output["uncertainty_usd"] = uncertainty * _FROZEN_CONTRACT_MULTIPLIER
    output["training_rows"] = len(training)
    output["latest_training_target_end"] = pd.Timestamp(training["target_end_timestamp"].max())
    output["training_snapshot_sha256"] = training_sha256
    output["input_snapshot_sha256"] = input_snapshot_sha256
    output["forecast_id"] = forecast_id
    output["horizon_sessions"] = _FROZEN_HORIZON_SESSIONS
    return output[
        [
            "trade_date",
            "signal_timestamp",
            "fill_trade_date",
            "fill_timestamp",
            "fill_contract_id",
            "target_end_timestamp",
            "forecast_id",
            "candidate_id",
            "model_id",
            "prediction",
            "predicted_path_move_per_mmbtu",
            "predicted_gross_pnl_usd",
            "uncertainty_per_mmbtu",
            "uncertainty_usd",
            "training_rows",
            "latest_training_target_end",
            "training_snapshot_sha256",
            "input_snapshot_sha256",
            "horizon_sessions",
        ]
    ].reset_index(drop=True)
