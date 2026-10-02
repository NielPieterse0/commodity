from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from commodity import v2_optimization as v2

_PROTECTED_START = pd.Timestamp("2023-01-01", tz="UTC")


def _stable_id(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def _utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _require_development_timestamp(value: object, label: str) -> pd.Timestamp:
    stamp = _utc(value)
    if stamp >= _PROTECTED_START:
        raise ValueError(f"issue431 protected timestamp in {label}: {stamp}")
    return stamp


def build_cost_assumptions(
    base: object,
    *,
    half_spread_ticks_per_side: float,
    slippage_ticks_per_side: float,
) -> object:
    spread = float(half_spread_ticks_per_side)
    slippage = float(slippage_ticks_per_side)
    if spread < 0.0 or slippage < 0.0:
        raise ValueError("issue431 execution friction cannot be negative")
    values = {
        "commission_usd_per_side": float(base.commission_usd_per_side),
        "exchange_clearing_fees_usd_per_side": float(base.exchange_clearing_fees_usd_per_side),
        "half_spread_ticks_per_side": spread,
        "slippage_ticks_per_side": slippage,
        "initial_margin_usd_per_contract": float(base.initial_margin_usd_per_contract),
        "tick_value_usd": float(base.tick_value_usd),
    }
    return type(base)(**values)


def _decision_trade_date_column(decisions: pd.DataFrame) -> str:
    for column in ("fill_trade_date", "trade_date"):
        if column in decisions.columns:
            return column
    raise ValueError("issue431 decisions lack an executable trade-date column")


def _path_index(path: pd.DataFrame) -> tuple[pd.DataFrame, dict[pd.Timestamp, int]]:
    required = {"trade_date", "session_open", "contract_id"}
    missing = sorted(required - set(path.columns))
    if missing:
        raise ValueError(f"issue431 path lacks execution columns: {missing}")
    work = path.copy().reset_index(drop=True)
    work["trade_date"] = pd.to_datetime(work["trade_date"], utc=True, errors="raise")
    work["session_open"] = pd.to_datetime(work["session_open"], utc=True, errors="raise")
    if work["trade_date"].duplicated().any() or not work["trade_date"].is_monotonic_increasing:
        raise ValueError("issue431 path dates must be unique and chronological")
    if len(work) and work["trade_date"].max() >= _PROTECTED_START:
        raise ValueError("issue431 path crosses protected confirmation")
    return work, {pd.Timestamp(value): index for index, value in enumerate(work["trade_date"])}


def expand_execution_decisions(
    path: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    delay_sessions: int,
    roll_gap_sessions: int,
    miss_every_nth_order: int,
) -> tuple[pd.DataFrame, dict[str, int]]:
    delay = int(delay_sessions)
    roll_gap = int(roll_gap_sessions)
    miss_n = int(miss_every_nth_order)
    if delay < 0 or roll_gap < 0 or miss_n < 0 or miss_n == 1:
        raise ValueError("issue431 execution stress parameters are invalid")
    work_path, date_to_index = _path_index(path)
    if decisions.empty:
        raise ValueError("issue431 execution decisions are empty")
    date_column = _decision_trade_date_column(decisions)
    work_decisions = decisions.copy().sort_values(date_column, kind="stable")
    work_decisions[date_column] = pd.to_datetime(work_decisions[date_column], utc=True, errors="raise")
    if work_decisions[date_column].duplicated().any():
        raise ValueError("issue431 source decisions must be unique by fill date")
    if len(work_decisions) and work_decisions[date_column].max() >= _PROTECTED_START:
        raise ValueError("issue431 source decisions cross protected confirmation")

    updates: dict[int, dict[str, Any]] = {}
    expired_before_fill = 0
    delayed_beyond_path = 0
    source_change_count = 0
    pre_missed_changes = 0
    previous_source_position = 0.0
    for row in work_decisions.to_dict("records"):
        source_date = pd.Timestamp(row[date_column])
        source_index = date_to_index.get(source_date)
        if source_index is None:
            raise ValueError(f"issue431 source decision is not on session path: {source_date}")
        fill_index = source_index + delay
        if fill_index >= len(work_path):
            delayed_beyond_path += 1
            continue
        fill_open = pd.Timestamp(work_path.loc[fill_index, "session_open"])
        target_end_raw = row.get("target_end_timestamp")
        target_end = None if target_end_raw is None or pd.isna(target_end_raw) else _utc(target_end_raw)
        if target_end is not None and fill_open >= target_end:
            expired_before_fill += 1
            continue
        payload = dict(row)
        requested_position = float(payload["signal_requested_position"])
        is_source_change = not math.isclose(
            requested_position, previous_source_position, rel_tol=0.0, abs_tol=1e-12
        )
        if is_source_change:
            source_change_count += 1
        payload["liquidity_missed"] = bool(
            is_source_change and miss_n > 1 and source_change_count % miss_n == 0
        )
        if payload["liquidity_missed"]:
            pre_missed_changes += 1
        previous_source_position = requested_position
        payload["source_trade_date"] = source_date
        payload["target_end_timestamp"] = target_end
        updates[fill_index] = payload

    active_position = 0.0
    active_target_end: pd.Timestamp | None = None
    active_forecast_id: str | None = None
    active_reason = "no_signal_yet"
    previous_output = 0.0
    previous_contract: str | None = None
    roll_gap_remaining = 0
    order_change_count = 0
    forced_flat_roll_sessions = 0
    records: list[dict[str, Any]] = []

    for index, session in work_path.iterrows():
        session_open = pd.Timestamp(session["session_open"])
        if active_target_end is not None and session_open >= active_target_end:
            active_position = 0.0
            active_target_end = None
            active_forecast_id = None
            active_reason = "forecast_horizon_expired"
        update = updates.get(index)
        if update is not None:
            if bool(update.get("liquidity_missed", False)):
                active_reason = "liquidity_missed_position_change"
            else:
                active_position = float(update["signal_requested_position"])
                active_target_end = update.get("target_end_timestamp")
                forecast = update.get("forecast_id")
                active_forecast_id = None if forecast is None or pd.isna(forecast) else str(forecast)
                active_reason = str(update.get("signal_reason", "forecast_signal"))

        current_contract = str(session["contract_id"])
        contract_changed = previous_contract is not None and current_contract != previous_contract
        if contract_changed and roll_gap > 0:
            roll_gap_remaining = max(roll_gap_remaining, roll_gap)
        requested = active_position
        reason = active_reason
        if roll_gap_remaining > 0:
            requested = 0.0
            reason = "roll_gap_stress"
            roll_gap_remaining -= 1
            forced_flat_roll_sessions += 1

        if not math.isclose(requested, previous_output, rel_tol=0.0, abs_tol=1e-12):
            order_change_count += 1

        records.append(
            {
                "trade_date": pd.Timestamp(session["trade_date"]),
                "signal_requested_position": float(requested),
                "forecast_id": active_forecast_id,
                "signal_reason": reason,
            }
        )
        previous_output = float(requested)
        previous_contract = current_contract

    output = pd.DataFrame(records)
    diagnostics = {
        "delay_sessions": delay,
        "roll_gap_sessions": roll_gap,
        "miss_every_nth_order": miss_n,
        "expired_before_delayed_fill": expired_before_fill,
        "delayed_beyond_path": delayed_beyond_path,
        "source_decisions": len(work_decisions),
        "expanded_sessions": len(output),
        "position_change_attempts": source_change_count,
        "missed_position_changes": pre_missed_changes,
        "forced_flat_roll_sessions": forced_flat_roll_sessions,
    }
    return output, diagnostics


def _training_frame(
    frame: pd.DataFrame,
    current_fill: pd.Timestamp,
    *,
    refit_mode: str,
    rolling_train_sessions: int | None,
) -> pd.DataFrame:
    training = frame.loc[frame["target_end_timestamp"] < current_fill].copy()
    if refit_mode in {"fixed", "expanding"}:
        return training
    if refit_mode != "rolling" or rolling_train_sessions is None:
        raise ValueError("issue431 rolling refit requires rolling_train_sessions")
    rows = int(rolling_train_sessions)
    if rows < 20:
        raise ValueError("issue431 rolling training window is too short")
    return training.tail(rows).copy()


def _sample_weights(training: pd.DataFrame, half_life_sessions: int | None) -> np.ndarray | None:
    if half_life_sessions is None:
        return None
    half_life = int(half_life_sessions)
    if half_life < 1:
        raise ValueError("issue431 decay half-life must be positive")
    ages = np.arange(len(training) - 1, -1, -1, dtype=float)
    return np.power(0.5, ages / float(half_life))


def _label_series(
    frame: pd.DataFrame,
    config: Mapping[str, object],
    *,
    round_trip_per_mmbtu: float,
    dead_band_per_mmbtu: float,
) -> pd.Series:
    return v2._issue425_labels(
        frame,
        role=str(config["target.target_role"]),
        dead_band_per_mmbtu=dead_band_per_mmbtu,
        round_trip_per_mmbtu=round_trip_per_mmbtu,
    )


def _dead_band(training: pd.DataFrame, config: Mapping[str, object]) -> float:
    role = str(config["target.target_role"])
    quantile = float(config["target.dead_band_quantile"])
    if quantile == 0.0:
        return 0.0
    if role not in {"direction", "direction_plus_volatility", "cost_aware_utility"}:
        raise ValueError("issue431 dead band is invalid for target role")
    return float(training["issue425_realized_cumulative"].abs().quantile(quantile))


def _economic_scale(training: pd.DataFrame, config: Mapping[str, object]) -> float:
    role = str(config["target.target_role"])
    aggregation = str(config["target.aggregation"])
    if role != "direction" and aggregation != "path_summary":
        return 1.0
    scale = float(training["issue425_realized_cumulative"].abs().median())
    return scale if math.isfinite(scale) and scale > 0.0 else 1.0


def _calibration_factor(y_train: np.ndarray, prediction: np.ndarray) -> float:
    predicted_scale = float(np.median(np.abs(prediction)))
    target_scale = float(np.median(np.abs(y_train)))
    if predicted_scale <= 1e-12 or not math.isfinite(predicted_scale) or not math.isfinite(target_scale):
        return 1.0
    return float(np.clip(target_scale / predicted_scale, 0.5, 2.0))


def _feature_drift(row: pd.Series, training: pd.DataFrame, feature_columns: Sequence[str]) -> bool:
    x = training[list(feature_columns)].astype(float)
    mean = x.mean(axis=0)
    std = x.std(axis=0, ddof=0).replace(0.0, np.nan)
    current = pd.to_numeric(row[list(feature_columns)], errors="raise").astype(float)
    z = ((current - mean) / std).abs().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return bool((z > 3.0).mean() >= 0.25)


def _history_drift(
    history: Sequence[Mapping[str, object]],
    current_fill: pd.Timestamp,
    trigger: str,
) -> bool:
    completed = [row for row in history if _utc(row["target_end_timestamp"]) < current_fill]
    if len(completed) < 20:
        return False
    recent = completed[-20:]
    actual = np.asarray([float(row["actual_target"]) for row in recent], dtype=float)
    predicted = np.asarray([float(row["prediction"]) for row in recent], dtype=float)
    if trigger == "performance_degradation":
        return bool(np.mean(np.sign(actual) == np.sign(predicted)) < 0.45)
    if trigger == "residual_distribution":
        recent_mae = float(np.mean(np.abs(actual - predicted)))
        reference = float(np.median([float(row["training_residual_mae"]) for row in recent]))
        return bool(reference > 0.0 and recent_mae > 1.5 * reference)
    return False


def adaptive_forecast_window(
    origins: pd.DataFrame,
    feature_columns: Sequence[str],
    config: Mapping[str, object],
    *,
    start_timestamp: pd.Timestamp,
    boundary_timestamp: pd.Timestamp,
    contract_multiplier: float,
    round_trip_usd: float,
    minimum_training_rows: int,
    refit_mode: str,
    retrain_every_sessions: int,
    rolling_train_sessions: int | None,
    decay_half_life_sessions: int | None,
    recalibration_cadence_sessions: int | None,
    drift_trigger: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    start = _require_development_timestamp(start_timestamp, "adaptation start")
    boundary = _utc(boundary_timestamp)
    if boundary > _PROTECTED_START:
        raise ValueError("issue431 adaptation boundary crosses protected confirmation")
    mode = str(refit_mode)
    if mode not in {"fixed", "expanding", "rolling"}:
        raise ValueError(f"issue431 unsupported refit mode: {mode}")
    cadence = int(retrain_every_sessions)
    if cadence < 1:
        raise ValueError("issue431 retrain cadence must be positive")
    trigger = str(drift_trigger)
    if trigger not in {"off", "feature_distribution", "residual_distribution", "performance_degradation"}:
        raise ValueError(f"issue431 unsupported drift trigger: {trigger}")
    if str(config.get("model.model_id")) != "ridge":
        raise ValueError("issue431 adaptation is frozen to the promoted ridge parent")

    frame = origins.copy()
    for column in ("signal_timestamp", "fill_timestamp", "target_end_timestamp"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    if len(frame) and frame["target_end_timestamp"].max() >= _PROTECTED_START:
        frame = frame.loc[frame["target_end_timestamp"] < _PROTECTED_START].copy()
    evaluation = frame.loc[
        frame["fill_timestamp"].ge(start) & frame["target_end_timestamp"].lt(boundary)
    ].copy().sort_values("fill_timestamp", kind="stable")
    if evaluation.empty:
        raise ValueError("issue431 adaptation window has no purge-safe evaluation rows")

    multiplier = float(contract_multiplier)
    round_trip_per_mmbtu = float(round_trip_usd) / multiplier
    recalibration_cadence = (
        None if recalibration_cadence_sessions is None else int(recalibration_cadence_sessions)
    )
    if recalibration_cadence is not None and recalibration_cadence < 1:
        raise ValueError("issue431 recalibration cadence must be positive")

    model: Ridge | None = None
    training: pd.DataFrame | None = None
    training_prediction: np.ndarray | None = None
    dead_band = 0.0
    economic_scale = 1.0
    threshold = 0.0
    uncertainty = 0.0
    training_residual_mae = 0.0
    calibration_factor = 1.0
    latest_training_end: pd.Timestamp | None = None
    since_refit = cadence
    since_recalibration = recalibration_cadence or 0
    refit_count = 0
    drift_refit_count = 0
    recalibration_count = 0
    history: list[dict[str, object]] = []
    records: list[dict[str, object]] = []

    for _, row in evaluation.iterrows():
        current_fill = pd.Timestamp(row["fill_timestamp"])
        candidate_training = _training_frame(
            frame,
            current_fill,
            refit_mode=mode,
            rolling_train_sessions=rolling_train_sessions,
        )
        if len(candidate_training) < int(minimum_training_rows):
            raise ValueError(
                f"issue431 has {len(candidate_training)} training rows; requires {minimum_training_rows}"
            )
        drifted = False
        if trigger == "feature_distribution" and model is not None and training is not None:
            drifted = _feature_drift(row, training, feature_columns)
        elif trigger in {"residual_distribution", "performance_degradation"} and model is not None:
            drifted = _history_drift(history, current_fill, trigger)
        regular_refit = model is None or (mode != "fixed" and since_refit >= cadence)
        should_refit = regular_refit or drifted

        if should_refit:
            training = candidate_training
            dead_band = _dead_band(training, config)
            y_train = _label_series(
                training,
                config,
                round_trip_per_mmbtu=round_trip_per_mmbtu,
                dead_band_per_mmbtu=dead_band,
            ).to_numpy(dtype=float)
            x_train = training[list(feature_columns)].astype(float)
            model = Ridge(alpha=float(config.get("model.ridge_alpha", 10.0)))
            weights = _sample_weights(training, decay_half_life_sessions)
            model.fit(x_train, y_train, sample_weight=weights)
            training_prediction = np.asarray(model.predict(x_train), dtype=float)
            economic_scale = _economic_scale(training, config)
            latest_training_end = pd.Timestamp(training["target_end_timestamp"].max())
            if latest_training_end >= current_fill:
                raise ValueError("issue431 adaptation training overlaps forecast fill")
            training_residual = y_train - training_prediction
            uncertainty = float(np.std(training_residual, ddof=1)) if len(training_residual) > 1 else 0.0
            training_residual_mae = float(np.mean(np.abs(training_residual)))
            if recalibration_cadence is not None:
                calibration_factor = _calibration_factor(y_train, training_prediction)
                recalibration_count += 1
                since_recalibration = 0
            else:
                calibration_factor = 1.0
            train_economic = training_prediction * economic_scale * calibration_factor
            threshold_quantile = float(config["decision.entry_threshold_quantile"])
            threshold = float(np.quantile(np.abs(train_economic), threshold_quantile))
            refit_count += 1
            if drifted and not regular_refit:
                drift_refit_count += 1
            since_refit = 0
        elif recalibration_cadence is not None and since_recalibration >= recalibration_cadence:
            assert model is not None
            training = candidate_training
            y_train = _label_series(
                training,
                config,
                round_trip_per_mmbtu=round_trip_per_mmbtu,
                dead_band_per_mmbtu=_dead_band(training, config),
            ).to_numpy(dtype=float)
            training_prediction = np.asarray(
                model.predict(training[list(feature_columns)].astype(float)), dtype=float
            )
            calibration_factor = _calibration_factor(y_train, training_prediction)
            train_economic = training_prediction * economic_scale * calibration_factor
            threshold = float(
                np.quantile(np.abs(train_economic), float(config["decision.entry_threshold_quantile"]))
            )
            recalibration_count += 1
            since_recalibration = 0

        assert model is not None and training is not None and latest_training_end is not None
        if recalibration_cadence is not None and since_recalibration == 0:
            latest_training_end = pd.Timestamp(training["target_end_timestamp"].max())
        raw_prediction = float(
            np.asarray(model.predict(pd.DataFrame([row[list(feature_columns)].to_dict()])), dtype=float)[0]
        )
        economic_prediction = raw_prediction * economic_scale * calibration_factor
        role = str(config["target.target_role"])
        if role == "volatility" or abs(economic_prediction) < threshold:
            economic_prediction = 0.0
        actual_target = float(
            _label_series(
                pd.DataFrame([row]),
                config,
                round_trip_per_mmbtu=round_trip_per_mmbtu,
                dead_band_per_mmbtu=dead_band,
            ).iloc[0]
        )
        payload = {
            "mode": mode,
            "cadence": cadence,
            "rolling": rolling_train_sessions,
            "decay": decay_half_life_sessions,
            "recalibration": recalibration_cadence,
            "drift": trigger,
            "fill": current_fill.isoformat(),
        }
        records.append(
            {
                "forecast_id": _stable_id(payload),
                "model_id": _stable_id({"config": dict(config), **payload}),
                "signal_timestamp": pd.Timestamp(row["signal_timestamp"]),
                "fill_trade_date": pd.Timestamp(row["fill_trade_date"]),
                "fill_timestamp": current_fill,
                "fill_contract_id": str(row["fill_contract_id"]),
                "target_end_timestamp": pd.Timestamp(row["target_end_timestamp"]),
                "latest_training_target_end": latest_training_end,
                "training_rows": len(training),
                "prediction": raw_prediction,
                "predicted_path_move_per_mmbtu": economic_prediction,
                "predicted_gross_pnl_usd": economic_prediction * multiplier,
                "uncertainty_per_mmbtu": uncertainty,
                "uncertainty_usd": uncertainty * multiplier,
                "actual_path_move_per_mmbtu": float(row["issue425_realized_cumulative"]),
                "actual_gross_pnl_usd": float(row["issue425_realized_cumulative"]) * multiplier,
                "horizon_sessions": int(config["target.horizon_sessions"]),
                "issue425_actual_target": actual_target,
            }
        )

        history.append(
            {
                "target_end_timestamp": pd.Timestamp(row["target_end_timestamp"]),
                "actual_target": actual_target,
                "prediction": raw_prediction,
                "training_residual_mae": training_residual_mae,
            }
        )
        since_refit += 1
        if recalibration_cadence is not None:
            since_recalibration += 1

    output = pd.DataFrame(records).sort_values("fill_timestamp", kind="stable").reset_index(drop=True)
    if output.empty:
        raise ValueError("issue431 adaptation produced no forecasts")
    if (
        pd.to_datetime(output["latest_training_target_end"], utc=True)
        >= pd.to_datetime(output["fill_timestamp"], utc=True)
    ).any():
        raise ValueError("issue431 adaptation emitted overlapping training evidence")
    diagnostics: dict[str, object] = {
        "refit_mode": mode,
        "retrain_every_sessions": cadence,
        "rolling_train_sessions": rolling_train_sessions,
        "decay_half_life_sessions": decay_half_life_sessions,
        "recalibration_cadence_sessions": recalibration_cadence,
        "drift_trigger": trigger,
        "evaluation_rows": len(output),
        "refit_count": refit_count,
        "drift_refit_count": drift_refit_count,
        "recalibration_count": recalibration_count,
        "minimum_training_rows_observed": int(output["training_rows"].min()),
        "maximum_training_rows_observed": int(output["training_rows"].max()),
        "protected_confirmation_accessed": False,
    }
    return output, diagnostics


def replay_expanded_execution_policy(
    path: pd.DataFrame,
    expanded_decisions: pd.DataFrame,
    risk: object,
    costs: object,
    *,
    contract_multiplier: float,
    max_abs_contracts: float,
) -> tuple[pd.DataFrame, dict[str, object]]:
    from commodity.stacking_policy import _replay_fractional_policy
    from commodity.v2_sizing_risk import _exposure_diagnostics

    cap = float(max_abs_contracts)
    if cap <= 0.0:
        raise ValueError("issue431 research contract cap must be positive")
    positions = pd.to_numeric(
        expanded_decisions["signal_requested_position"], errors="raise"
    ).astype(float)
    if not np.isfinite(positions.to_numpy(dtype=float)).all():
        raise ValueError("issue431 expanded positions must be finite")
    if positions.abs().gt(cap + 1e-12).any():
        raise ValueError("issue431 expanded position exceeds research contract cap")
    levels = frozenset({0.0, *positions.tolist()})
    ledger, base_summary = _replay_fractional_policy(
        path,
        expanded_decisions,
        risk,
        costs,
        contract_multiplier=float(contract_multiplier),
        enforce_risk=True,
        enforce_phase5_boundary=True,
        allowed_position_levels=levels,
    )
    diagnostics = _exposure_diagnostics(
        path,
        ledger,
        costs=costs,
        contract_multiplier=float(contract_multiplier),
    )
    summary = dict(base_summary)
    summary.update(diagnostics)
    summary["research_contract_cap"] = cap
    summary["research_only_not_execution_authority"] = True
    summary["live_trading_allowed"] = False
    return ledger, summary


def adaptation_variant_feasibility(
    variant: Mapping[str, object], *, minimum_training_rows: int
) -> tuple[bool, str | None]:
    minimum = int(minimum_training_rows)
    if minimum < 1:
        raise ValueError("issue431 minimum training rows must be positive")
    if str(variant.get("refit_mode")) != "rolling":
        return True, None
    raw_window = variant.get("rolling_train_sessions")
    if raw_window is None:
        return False, "rolling_window_missing"
    window = int(raw_window)
    if window < minimum:
        return False, f"rolling_window_below_minimum_training_rows:{window}<{minimum}"
    return True, None
