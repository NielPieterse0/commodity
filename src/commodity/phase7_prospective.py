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
    expected = {"learning_rate": 0.05, "max_iter": 20, "max_leaf_nodes": 15, "random_state": 0}
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
    *,
    freeze_landed_at: str,
    contract_multiplier: float,
    min_train_rows: int,
    horizon_sessions: int,
) -> pd.DataFrame:
    """Fit only on frozen pre-2023 outcomes and forecast one outcome-blind live origin.

    `training_origins` must contain only the already-consumed development sample.
    The current origin must not contain any realized target/P&L value. This deliberately
    refuses to filter later outcomes silently: if 2023+ outcomes are supplied at all,
    inference fails closed instead of risking protected-history leakage.
    """
    if horizon_sessions != 5:
        raise Phase7ProspectiveError("Phase 7 must preserve the frozen five-session horizon")
    multiplier = float(contract_multiplier)
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise Phase7ProspectiveError("contract_multiplier must be positive and finite")
    if min_train_rows < 1:
        raise Phase7ProspectiveError("min_train_rows must be positive")
    if len(current_origin) != 1:
        raise Phase7ProspectiveError("prospective market forecast requires exactly one current origin")

    required_training = {"target_end_timestamp", "target_path_move_per_mmbtu", *feature_columns}
    missing_training = sorted(required_training - set(training_origins.columns))
    if missing_training:
        raise Phase7ProspectiveError(f"training origins missing columns: {missing_training}")
    training = training_origins.copy()
    training["target_end_timestamp"] = _utc_series(training, "target_end_timestamp", "training origins")
    if (training["target_end_timestamp"] >= _FROZEN_DEVELOPMENT_CUTOFF).any():
        raise Phase7ProspectiveError("reserved 2023+ outcomes are forbidden in prospective baseline fitting")
    if len(training) < min_train_rows:
        raise Phase7ProspectiveError(
            f"prospective baseline has {len(training)} training rows; requires {min_train_rows}"
        )
    y_train = pd.to_numeric(training["target_path_move_per_mmbtu"], errors="coerce")
    if not np.isfinite(y_train.to_numpy(dtype=float)).all():
        raise Phase7ProspectiveError("training outcomes contain non-finite values")
    x_train = _finite_features(training, feature_columns, "training origins")

    current = current_origin.copy()
    required_current = {
        "trade_date",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "fill_contract_id",
        "target_end_timestamp",
        *feature_columns,
    }
    missing_current = sorted(required_current - set(current.columns))
    if missing_current:
        raise Phase7ProspectiveError(f"current origin missing columns: {missing_current}")
    for column in _FORBIDDEN_CURRENT_OUTCOMES.intersection(current.columns):
        if current[column].notna().any():
            raise Phase7ProspectiveError(f"current origin must be outcome-blind: {column}")

    for column in ("trade_date", "signal_timestamp", "fill_trade_date", "fill_timestamp", "target_end_timestamp"):
        current[column] = _utc_series(current, column, "current origin")
    freeze = pd.to_datetime(freeze_landed_at, utc=True, errors="coerce")
    if pd.isna(freeze):
        raise Phase7ProspectiveError("freeze_landed_at must be a valid timestamp")
    row = current.iloc[0]
    signal = pd.Timestamp(row["signal_timestamp"])
    fill = pd.Timestamp(row["fill_timestamp"])
    target_end = pd.Timestamp(row["target_end_timestamp"])
    if signal <= pd.Timestamp(freeze):
        raise Phase7ProspectiveError("prospective baseline signal must occur strictly after landed freeze")
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

    training_columns = ["target_end_timestamp", "target_path_move_per_mmbtu", *feature_columns]
    training_ordered = training.sort_values("target_end_timestamp", kind="stable").reset_index(drop=True)
    training_sha256 = _frame_sha256(training_ordered, training_columns)
    current_columns = [
        "trade_date",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "fill_contract_id",
        "target_end_timestamp",
        *feature_columns,
    ]
    current_sha256 = _frame_sha256(current, current_columns)
    input_payload = json.dumps(
        {
            "candidate_id": str(candidate["id"]),
            "training_sha256": training_sha256,
            "current_origin_sha256": current_sha256,
            "horizon_sessions": horizon_sessions,
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
    output["predicted_gross_pnl_usd"] = prediction * multiplier
    output["uncertainty_per_mmbtu"] = uncertainty
    output["uncertainty_usd"] = uncertainty * multiplier
    output["training_rows"] = len(training)
    output["latest_training_target_end"] = pd.Timestamp(training["target_end_timestamp"].max())
    output["training_snapshot_sha256"] = training_sha256
    output["input_snapshot_sha256"] = input_snapshot_sha256
    output["forecast_id"] = forecast_id
    output["horizon_sessions"] = horizon_sessions
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
