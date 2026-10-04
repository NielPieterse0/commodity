from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from commodity.v2_adaptive_controller import AdaptiveContractError
from commodity.v2_adaptive_controller_v2 import MEMORY_BANK

FOUNDATION_CONTEXT_HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 20)
FOUNDATION_CONTEXT_COLUMNS: tuple[str, ...] = (
    "expert_timesfm_slope",
    "expert_timesfm_acceleration",
    "expert_kronos_slope",
    "expert_kronos_acceleration",
    *(f"expert_timesfm_interval_width_h{h}" for h in FOUNDATION_CONTEXT_HORIZONS),
    *(f"expert_model_disagreement_h{h}" for h in FOUNDATION_CONTEXT_HORIZONS),
    "expert_model_disagreement_mean_abs",
    "expert_model_sign_disagreement_rate",
)


def path_shape_features(returns: Sequence[float]) -> dict[str, float]:
    values = np.asarray(list(returns), dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise AdaptiveContractError("expert path must be finite and non-empty")
    x = np.arange(1, len(values) + 1, dtype=float)
    slope = float(np.polyfit(x, values, 1)[0]) if len(values) >= 2 else 0.0
    acceleration = float(2.0 * np.polyfit(x, values, 2)[0]) if len(values) >= 3 else 0.0
    return {
        "terminal_return": float(values[-1]),
        "slope_per_session": slope,
        "acceleration_per_session2": acceleration,
        "dispersion": float(np.std(values, ddof=0)),
    }


def _horizon_value(values: Sequence[float], horizon: int) -> float | None:
    items = list(values)
    value = items[horizon - 1] if len(items) >= int(horizon) else None
    return None if value is None or pd.isna(value) else float(value)


def _horizon_item(values: Sequence[Any], horizon: int) -> Any:
    items = list(values)
    return items[horizon - 1] if len(items) >= int(horizon) else None


def build_foundation_actual_paths(
    expert_paths: pd.DataFrame,
    canonical_history: pd.DataFrame,
    ohlcv_history: pd.DataFrame,
    state: pd.DataFrame,
) -> pd.DataFrame:
    experts = expert_paths.copy()
    canonical = canonical_history.copy()
    ohlcv = ohlcv_history.copy()
    decisions = state.copy()
    experts["decision_time"] = pd.to_datetime(experts["decision_time"], utc=True)
    experts["trade_date"] = pd.to_datetime(experts["trade_date"], utc=True)
    canonical["trade_date"] = pd.to_datetime(canonical["trade_date"], utc=True)
    canonical["available_at"] = pd.to_datetime(canonical["available_at"], utc=True)
    ohlcv["trade_date"] = pd.to_datetime(ohlcv["trade_date"], utc=True)
    decisions["trade_date"] = pd.to_datetime(decisions["trade_date"], utc=True)
    decisions["decision_time"] = pd.to_datetime(decisions["decision_time"], utc=True)
    if canonical.duplicated(["trade_date", "contract_id"]).any() or ohlcv.duplicated(["trade_date", "contract_id"]).any():
        raise AdaptiveContractError("foundation actual history must be unique by trade_date and contract_id")
    canonical_by_key = canonical.set_index(["trade_date", "contract_id"])
    ohlcv_by_key = ohlcv.set_index(["trade_date", "contract_id"])
    known_at = decisions.groupby("trade_date", sort=False)["decision_time"].min().to_dict()
    rows: list[dict[str, Any]] = []
    for row in experts.itertuples(index=False):
        origin = (pd.Timestamp(row.trade_date), str(row.contract_id))
        current_settle = float(canonical_by_key.loc[origin, "settle"]) if origin in canonical_by_key.index else None
        current_close = float(ohlcv_by_key.loc[origin, "close"]) if origin in ohlcv_by_key.index else None
        tf_returns: list[float | None] = []
        tf_available: list[str | None] = []
        kr_returns: list[float | None] = []
        kr_available: list[str | None] = []
        for raw_future in row.forecast_sessions:
            future = pd.Timestamp(raw_future)
            key = (future, str(row.contract_id))
            if current_settle is not None and key in canonical_by_key.index:
                tf_returns.append(float(canonical_by_key.loc[key, "settle"]) / current_settle - 1.0)
                tf_available.append(pd.Timestamp(canonical_by_key.loc[key, "available_at"]).isoformat())
            else:
                tf_returns.append(None); tf_available.append(None)
            if current_close is not None and key in ohlcv_by_key.index and future in known_at:
                kr_returns.append(float(ohlcv_by_key.loc[key, "close"]) / current_close - 1.0)
                kr_available.append(pd.Timestamp(known_at[future]).isoformat())
            else:
                kr_returns.append(None); kr_available.append(None)
        rows.append({
            "decision_time": pd.Timestamp(row.decision_time),
            "timesfm_actual_returns": tf_returns,
            "timesfm_actual_available_at": tf_available,
            "kronos_actual_returns": kr_returns,
            "kronos_actual_available_at": kr_available,
        })
    return pd.DataFrame(rows)


def foundation_horizon_signals(
    expert_paths: pd.DataFrame,
    horizons: Sequence[int] = FOUNDATION_CONTEXT_HORIZONS,
) -> dict[pd.Timestamp, dict[int, dict[str, float]]]:
    rows: dict[pd.Timestamp, dict[int, dict[str, float]]] = {}
    for row in expert_paths.itertuples(index=False):
        stamp = pd.Timestamp(row.decision_time)
        by_horizon: dict[int, dict[str, float]] = {}
        for horizon in horizons:
            timesfm = _horizon_value(row.timesfm_point_returns, int(horizon))
            kronos = _horizon_value(row.kronos_close_returns, int(horizon))
            by_horizon[int(horizon)] = {
                "timesfm_direction": 0.0 if timesfm is None else float(np.sign(timesfm)),
                "kronos_direction": 0.0 if kronos is None else float(np.sign(kronos)),
            }
        rows[stamp] = by_horizon
    return rows


def foundation_context_frame(
    expert_paths: pd.DataFrame,
    horizons: Sequence[int] = FOUNDATION_CONTEXT_HORIZONS,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in expert_paths.itertuples(index=False):
        timesfm_features = dict(row.timesfm_path_features)
        kronos_features = dict(row.kronos_path_features)
        record: dict[str, Any] = {
            "decision_time": pd.Timestamp(row.decision_time),
            "expert_timesfm_slope": float(timesfm_features["slope_per_session"]),
            "expert_timesfm_acceleration": float(timesfm_features["acceleration_per_session2"]),
            "expert_kronos_slope": float(kronos_features["slope_per_session"]),
            "expert_kronos_acceleration": float(kronos_features["acceleration_per_session2"]),
            "expert_model_disagreement_mean_abs": float(row.model_disagreement_mean_abs),
            "expert_model_sign_disagreement_rate": float(row.model_sign_disagreement_rate),
        }
        for horizon in horizons:
            q10 = _horizon_value(row.timesfm_q10_returns, int(horizon))
            q90 = _horizon_value(row.timesfm_q90_returns, int(horizon))
            disagreement = _horizon_value(row.model_disagreement_returns, int(horizon))
            record[f"expert_timesfm_interval_width_h{int(horizon)}"] = (
                None if q10 is None or q90 is None else float(q90 - q10)
            )
            record[f"expert_model_disagreement_h{int(horizon)}"] = disagreement
        records.append(record)
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
    return frame


def _quantitative_forecast(
    specialist: str,
    horizon: int,
    expert_row: pd.Series | None,
) -> tuple[float | None, float | None, float | None]:
    if expert_row is None:
        return None, None, None
    if specialist == "timesfm_direction":
        point = _horizon_value(expert_row["timesfm_point_returns"], horizon)
        low = _horizon_value(expert_row["timesfm_q10_returns"], horizon)
        high = _horizon_value(expert_row["timesfm_q90_returns"], horizon)
        if point is None:
            return None, None, None
        return point, low, high
    if specialist == "kronos_direction":
        point = _horizon_value(expert_row["kronos_close_returns"], horizon)
        if point is None:
            return None, None, None
        return point, None, None
    return None, None, None


def build_rich_expert_consequences(
    base_consequences: pd.DataFrame,
    path: pd.DataFrame,
    *,
    expert_paths: pd.DataFrame | None = None,
    foundation_actuals: pd.DataFrame | None = None,
    multiplier: float = 10000.0,
    capital_usd: float = 100000.0,
    cost_per_side_usd: float = 15.0,
) -> pd.DataFrame:
    frame = base_consequences.copy()
    if frame.empty:
        return frame
    path_by_time = path.copy().set_index(pd.to_datetime(path["decision_time"], utc=True))
    expert_by_time = None
    if expert_paths is not None and not expert_paths.empty:
        experts = expert_paths.copy()
        experts["decision_time"] = pd.to_datetime(experts["decision_time"], utc=True)
        expert_by_time = experts.set_index("decision_time")
    actual_by_time = None
    if foundation_actuals is not None and not foundation_actuals.empty:
        actuals = foundation_actuals.copy()
        actuals["decision_time"] = pd.to_datetime(actuals["decision_time"], utc=True)
        actual_by_time = actuals.set_index("decision_time")
    records: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        stamp = pd.Timestamp(row.decision_time)
        horizon = int(row.horizon)
        if stamp not in path_by_time.index:
            raise AdaptiveContractError("rich consequence path missing decision timestamp")
        outcome = path_by_time.loc[stamp]
        move_col = f"h{horizon}_move_per_mmbtu"
        price = float(outcome.get("fill_price", outcome.get("decision_price", 1.0)))
        actual_return = float(outcome[move_col]) / max(abs(price), 1e-12)
        expert_row = None
        if expert_by_time is not None and stamp in expert_by_time.index:
            expert_row = expert_by_time.loc[stamp]
        specialist = str(row.specialist)
        predicted, lower, upper = _quantitative_forecast(specialist, horizon, expert_row)
        signal = float(row.signal)
        turnover = float(getattr(row, "turnover", 0.0))
        net_return = float(row.net_return)
        if specialist in {"timesfm_direction", "kronos_direction"} and predicted is not None:
            raw_signal = float(np.sign(predicted))
            signal = max(raw_signal, 0.0) if str(row.direction) == "long" else min(raw_signal, 0.0)
            roll_column = f"h{horizon}_roll_count"
            roll_count = float(outcome[roll_column]) if roll_column in outcome.index else 0.0
            turnover = 2.0 * abs(signal) * (1.0 + roll_count)
            pnl = signal * float(outcome[move_col]) * float(multiplier)
            pnl -= turnover * float(cost_per_side_usd)
            net_return = pnl / float(capital_usd)
        direction_hit = None if signal == 0.0 else float(np.sign(signal) == np.sign(actual_return))
        direction_error = None if signal == 0.0 else float(abs(np.sign(signal) - np.sign(actual_return)))
        forecast_actual = None
        forecast_available = None
        actual_row = actual_by_time.loc[stamp] if actual_by_time is not None and stamp in actual_by_time.index else None
        specialist = str(row.specialist)
        if predicted is not None and actual_row is not None:
            if specialist == "timesfm_direction" or "attr__timesfm_point_return__" in specialist:
                forecast_actual = _horizon_value(actual_row["timesfm_actual_returns"], horizon)
                forecast_available = _horizon_item(actual_row["timesfm_actual_available_at"], horizon)
            elif specialist == "kronos_direction" or "attr__kronos_close_return__" in specialist:
                forecast_actual = _horizon_value(actual_row["kronos_actual_returns"], horizon)
                forecast_available = _horizon_item(actual_row["kronos_actual_available_at"], horizon)
        forecast_error = None if predicted is None or forecast_actual is None else float(predicted - forecast_actual)
        interval_covered = None
        interval_width = None
        if lower is not None and upper is not None and forecast_actual is not None:
            interval_covered = float(float(lower) <= forecast_actual <= float(upper))
            interval_width = float(upper - lower)
        payload = dict(row._asdict())
        payload.update({
            "signal": signal,
            "turnover": turnover,
            "net_return": net_return,
            "horizon_specific_foundation_signal": specialist in {"timesfm_direction", "kronos_direction"},
            "actual_return": actual_return,
            "prediction_score": float(np.sign(signal)) if signal != 0.0 else 0.0,
            "direction_hit": direction_hit,
            "direction_error": direction_error,
            "quantitative_predicted_return": predicted,
            "forecast_actual_return": forecast_actual,
            "forecast_outcome_available_at": forecast_available,
            "forecast_error_return": forecast_error,
            "abs_forecast_error_return": None if forecast_error is None else abs(forecast_error),
            "squared_forecast_error_return": None if forecast_error is None else forecast_error * forecast_error,
            "interval_covered": interval_covered,
            "interval_width": interval_width,
        })
        records.append(payload)
    return pd.DataFrame(records)

def _metric_mean(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.mean())


def _metric_rmse(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(np.sqrt(np.mean(np.square(values))))


def rich_effectiveness_surface_for_day(
    consequences: pd.DataFrame,
    decision_time: pd.Timestamp,
    comparable_refs: list[pd.Timestamp],
    *,
    memories: tuple[int | str, ...] = MEMORY_BANK,
) -> pd.DataFrame:
    stamp = pd.Timestamp(decision_time)
    prior = consequences.loc[pd.to_datetime(consequences["outcome_available_at"], utc=True) < stamp].copy()
    refs = {pd.Timestamp(value) for value in comparable_refs}
    rows: list[dict[str, Any]] = []
    for (specialist, horizon, direction), group in prior.groupby(["specialist", "horizon", "direction"], sort=False):
        group = group.sort_values("outcome_available_at", kind="stable")
        objective = group.tail(30)
        comparable = group.loc[group["decision_time"].isin(refs)] if refs else group.iloc[0:0]
        for memory in memories:
            sample = group if memory == "expanding" else group.tail(int(memory))
            diagnostic_sample = sample
            if "forecast_outcome_available_at" in sample:
                diagnostic_available = pd.to_datetime(
                    sample["forecast_outcome_available_at"], utc=True, errors="coerce"
                )
                diagnostic_sample = sample.loc[diagnostic_available.notna() & (diagnostic_available < stamp)]
            net = pd.to_numeric(sample["net_return"], errors="raise").astype(float)
            obj_net = pd.to_numeric(objective["net_return"], errors="raise").astype(float)
            cmp_net = pd.to_numeric(comparable["net_return"], errors="raise").astype(float)
            rows.append({
                "specialist": str(specialist), "horizon": int(horizon), "direction": str(direction),
                "memory": memory, "count": len(net),
                "mean_net_return": float(net.mean()) if len(net) else 0.0,
                "std_net_return": float(net.std(ddof=0)) if len(net) else 0.0,
                "objective_30_count": len(obj_net),
                "objective_30_net_return_sum": float(obj_net.sum()) if len(obj_net) else 0.0,
                "objective_30_mean_net_return": float(obj_net.mean()) if len(obj_net) else 0.0,
                "objective_30_std_net_return": float(obj_net.std(ddof=0)) if len(obj_net) else 0.0,
                "comparable_count": len(cmp_net),
                "comparable_mean_net_return": float(cmp_net.mean()) if len(cmp_net) else 0.0,
                "comparable_std_net_return": float(cmp_net.std(ddof=0)) if len(cmp_net) else 0.0,
                "direction_hit_rate": _metric_mean(sample, "direction_hit"),
                "direction_error_mean": _metric_mean(sample, "direction_error"),
                "forecast_diagnostic_count": len(diagnostic_sample),
                "forecast_mae_return": _metric_mean(diagnostic_sample, "abs_forecast_error_return"),
                "forecast_rmse_return": _metric_rmse(diagnostic_sample, "forecast_error_return"),
                "forecast_bias_return": _metric_mean(diagnostic_sample, "forecast_error_return"),
                "interval_coverage": _metric_mean(diagnostic_sample, "interval_covered"),
                "interval_sharpness": _metric_mean(diagnostic_sample, "interval_width"),
                "comparable_hit_rate": _metric_mean(comparable, "direction_hit"),
                "max_outcome_available_at_used": (
                    pd.Timestamp(sample["outcome_available_at"].max()) if len(sample) else None
                ),
                "max_forecast_outcome_available_at_used": (
                    pd.to_datetime(
                        diagnostic_sample["forecast_outcome_available_at"], utc=True, errors="coerce"
                    ).max()
                    if len(diagnostic_sample) and "forecast_outcome_available_at" in diagnostic_sample
                    else None
                ),
            })
    return pd.DataFrame(rows)


def precompute_rich_surfaces(
    consequences: pd.DataFrame,
    context_state: pd.DataFrame,
    refs_by_time: dict[pd.Timestamp, list[pd.Timestamp]],
) -> dict[pd.Timestamp, pd.DataFrame]:
    return {
        pd.Timestamp(stamp): rich_effectiveness_surface_for_day(
            consequences, pd.Timestamp(stamp), refs_by_time[pd.Timestamp(stamp)]
        )
        for stamp in pd.to_datetime(context_state["decision_time"], utc=True)
    }

def causal_standardized_attributes(state: pd.DataFrame, attributes: list[str]) -> pd.DataFrame:
    frame = state[["decision_time", *attributes]].copy()
    out = pd.DataFrame({"decision_time": pd.to_datetime(frame["decision_time"], utc=True)})
    for column in attributes:
        values = pd.to_numeric(frame[column], errors="raise").astype(float)
        center = values.shift(1).expanding(min_periods=1).mean().fillna(0.0)
        scale = values.shift(1).expanding(min_periods=2).std(ddof=0).replace(0.0, np.nan)
        scale = scale.fillna(1.0)
        out[column] = ((values - center) / scale).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out


def _minimum_norm_weights(vector: np.ndarray, target: float, mask: np.ndarray | None = None) -> np.ndarray:
    x = vector if mask is None else vector * mask
    denom = float(np.dot(x, x))
    if abs(float(target)) <= 1e-15 or denom <= 1e-15:
        return np.zeros_like(vector, dtype=float)
    return float(target) * x / denom


def _oracle_exposure_solution(
    outcome: pd.Series,
    horizon: int,
    *,
    multiplier: float,
    capital_usd: float,
    round_trip_cost_usd: float,
    max_abs_contracts: float,
    exposure_step_contracts: float,
) -> tuple[float, float, pd.Timestamp | pd.NaT, bool]:
    move = outcome.get(f"h{int(horizon)}_move_per_mmbtu")
    available = outcome.get(f"h{int(horizon)}_outcome_available_at")
    observed = move is not None and available is not None and not pd.isna(move) and not pd.isna(available)
    if not observed:
        return 0.0, 0.0, pd.NaT, False
    roll_count = float(outcome.get(f"h{int(horizon)}_roll_count", 0.0) or 0.0)
    steps = round(float(max_abs_contracts) / float(exposure_step_contracts))
    exposures = [float(index * exposure_step_contracts) for index in range(-steps, steps + 1)]
    candidates = []
    for exposure in exposures:
        pnl = exposure * float(move) * float(multiplier)
        pnl -= abs(exposure) * (1.0 + roll_count) * float(round_trip_cost_usd)
        net = float(pnl / float(capital_usd))
        candidates.append((net, -abs(exposure), exposure))
    best_net, _size_tiebreak, best_exposure = max(candidates)
    return float(best_exposure), float(best_net), pd.Timestamp(available), True


def hindsight_attribute_weight_oracle(
    state: pd.DataFrame,
    attributes: list[str],
    path: pd.DataFrame,
    *,
    sparse_k: int = 8,
    sparse_ks: Sequence[int] = (1, 2, 4, 8, 16),
    horizons: Sequence[int] = FOUNDATION_CONTEXT_HORIZONS,
    max_abs_contracts: float = 1.5,
    exposure_step_contracts: float = 0.25,
    multiplier: float = 10000.0,
    capital_usd: float = 100000.0,
    round_trip_cost_usd: float = 30.0,
) -> pd.DataFrame:
    if len(attributes) == 0:
        raise AdaptiveContractError("attribute oracle requires at least one attribute")
    if exposure_step_contracts <= 0.0 or max_abs_contracts <= 0.0:
        raise AdaptiveContractError("attribute oracle exposure lattice must be positive")
    normalized = causal_standardized_attributes(state, attributes).set_index("decision_time")
    path_frame = path.copy()
    path_frame["decision_time"] = pd.to_datetime(path_frame["decision_time"], utc=True)
    path_by_time = path_frame.set_index("decision_time")
    sparse_ladder = tuple(sorted({min(len(attributes), max(1, int(k))) for k in sparse_ks}))
    if int(sparse_k) not in sparse_ladder:
        sparse_ladder = tuple(sorted({*sparse_ladder, min(len(attributes), int(sparse_k))}))
    rows: list[dict[str, Any]] = []
    for stamp in pd.to_datetime(state["decision_time"], utc=True):
        if stamp not in path_by_time.index:
            continue
        outcome = path_by_time.loc[stamp]
        vector = normalized.loc[stamp, attributes].to_numpy(dtype=float)
        order = np.argsort(-np.abs(vector), kind="stable")
        horizon_solutions: dict[str, dict[str, Any]] = {}
        for horizon in horizons:
            exposure, net_return, available, observed = _oracle_exposure_solution(
                outcome, int(horizon), multiplier=multiplier, capital_usd=capital_usd,
                round_trip_cost_usd=round_trip_cost_usd,
                max_abs_contracts=max_abs_contracts,
                exposure_step_contracts=exposure_step_contracts,
            )
            dense = _minimum_norm_weights(vector, exposure)
            dense_map = {name: float(value) for name, value in zip(attributes, dense, strict=True)}
            sparse_solutions: dict[str, dict[str, Any]] = {}
            for k in sparse_ladder:
                mask = np.zeros(len(attributes), dtype=float)
                mask[order[: int(k)]] = 1.0
                sparse = _minimum_norm_weights(vector, exposure, mask)
                sparse_map = {
                    name: float(value) for name, value in zip(attributes, sparse, strict=True)
                    if abs(value) > 1e-15
                }
                reconstructed = float(np.dot(sparse, vector))
                sparse_solutions[str(k)] = {
                    "weights": sparse_map,
                    "selected_attributes": list(sparse_map),
                    "reconstructed_exposure": reconstructed,
                    "reconstruction_error": float(abs(reconstructed - exposure)),
                }
            dense_reconstructed = float(np.dot(dense, vector))
            horizon_solutions[str(int(horizon))] = {
                "outcome_available_at": available,
                "oracle_outcome_observed": bool(observed),
                "optimal_exposure": exposure,
                "optimal_side": int(np.sign(exposure)),
                "optimal_direction": "long" if exposure > 0 else "short" if exposure < 0 else "flat",
                "optimal_net_return": net_return,
                "dense_weights": dense_map,
                "dense_reconstructed_exposure": dense_reconstructed,
                "dense_reconstruction_error": float(abs(dense_reconstructed - exposure)),
                "sparse_solutions": sparse_solutions,
            }
        primary_key = "1" if "1" in horizon_solutions else str(int(next(iter(horizons))))
        primary = horizon_solutions[primary_key]
        primary_sparse = primary["sparse_solutions"][str(min(len(attributes), int(sparse_k)))]
        sparse_map = dict(primary_sparse["weights"])
        top_attribute = (
            min(sparse_map, key=lambda name: (-abs(sparse_map[name]), name)) if sparse_map else None
        )
        rows.append({
            "decision_time": pd.Timestamp(stamp),
            "outcome_available_at": primary["outcome_available_at"],
            "oracle_outcome_observed": bool(primary["oracle_outcome_observed"]),
            "oracle_direction": str(primary["optimal_direction"]),
            "oracle_side": int(primary["optimal_side"]),
            "oracle_exposure": float(primary["optimal_exposure"]),
            "oracle_net_return": float(primary["optimal_net_return"]),
            "dense_weights": dict(primary["dense_weights"]),
            "sparse_weights": sparse_map,
            "sparse_k": int(sparse_k),
            "sparse_ks": list(sparse_ladder),
            "top_attribute": top_attribute,
            "horizon_solutions": horizon_solutions,
            "normalized_attribute_vector": {
                name: float(value) for name, value in zip(attributes, vector, strict=True)
            },
            "diagnostic_interpretation": "minimum_norm_exposure_reconstruction_not_identified_feature_importance",
            "feature_importance_inference": False,
            "selection_use": False,
            "development_only_nontradable": True,
        })
    return pd.DataFrame(rows)


def _dict_vector(weights: dict[str, float], attributes: list[str]) -> np.ndarray:
    return np.asarray([float(weights.get(name, 0.0)) for name in attributes], dtype=float)


def causal_primitive_oracle_winner_predictor(
    state: pd.DataFrame,
    winner_by_day: dict[str, dict[str, Any]],
    attributes: list[str],
    *,
    k: int = 10,
) -> pd.DataFrame:
    if not attributes:
        raise AdaptiveContractError("primitive oracle predictor requires state attributes")
    if int(k) <= 0:
        raise AdaptiveContractError("primitive oracle predictor neighbor count must be positive")
    normalized = causal_standardized_attributes(state, attributes).set_index("decision_time")
    label_rows: list[dict[str, Any]] = []
    for raw_decision_time, payload in winner_by_day.items():
        decision_time = pd.Timestamp(raw_decision_time)
        if decision_time not in normalized.index:
            continue
        raw_available = payload.get("outcome_available_at")
        available = (
            None if raw_available is None or pd.isna(raw_available)
            else pd.Timestamp(raw_available)
        )
        label_rows.append({
            "decision_time": decision_time,
            "outcome_available_at": available,
            "policy_id": str(payload["policy_id"]),
            "specialist": str(payload["specialist"]),
            "horizon": int(payload["horizon"]),
            "direction": str(payload["direction"]),
        })
    labels = pd.DataFrame(label_rows)
    if not labels.empty:
        for policy_id, group in labels.groupby("policy_id", sort=False):
            identities = group[["specialist", "horizon", "direction"]].drop_duplicates()
            if len(identities) != 1:
                raise AdaptiveContractError(
                    f"primitive oracle policy identity changed for {policy_id}"
                )
        labels = labels.sort_values("decision_time", kind="stable").reset_index(drop=True)
        labels_by_time = labels.set_index("decision_time")
        policy_meta = (
            labels.drop_duplicates("policy_id")
            .set_index("policy_id")[["specialist", "horizon", "direction"]]
        )
    else:
        labels_by_time = pd.DataFrame()
        policy_meta = pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for stamp in pd.to_datetime(state["decision_time"], utc=True):
        current = normalized.loc[stamp, attributes].to_numpy(dtype=float)
        actual = None
        if not labels.empty and stamp in labels_by_time.index:
            actual = labels_by_time.loc[stamp]
        if labels.empty:
            eligible = labels
        else:
            available = pd.to_datetime(labels["outcome_available_at"], utc=True, errors="coerce")
            eligible = labels.loc[available.notna() & (available < stamp)].copy()
        predicted_policy: str | None = None
        predicted_specialist: str | None = None
        predicted_horizon: int | None = None
        predicted_direction: str | None = None
        max_available: pd.Timestamp | None = None
        class_probabilities: dict[str, float] = {}
        neighbor_count = 0
        if not eligible.empty:
            candidates: list[tuple[float, pd.Series]] = []
            for _, label in eligible.iterrows():
                prior_stamp = pd.Timestamp(label["decision_time"])
                prior = normalized.loc[prior_stamp, attributes].to_numpy(dtype=float)
                candidates.append((float(np.linalg.norm(current - prior)), label))
            candidates.sort(key=lambda item: (item[0], pd.Timestamp(item[1]["decision_time"])))
            chosen = candidates[: min(int(k), len(candidates))]
            neighbor_count = len(chosen)
            distances = np.asarray([item[0] for item in chosen], dtype=float)
            alphas = 1.0 / np.maximum(distances, 1e-9)
            alphas /= alphas.sum()
            votes: dict[str, float] = {}
            used_available: list[pd.Timestamp] = []
            for alpha, (_distance, label) in zip(alphas, chosen, strict=True):
                policy_id = str(label["policy_id"])
                votes[policy_id] = votes.get(policy_id, 0.0) + float(alpha)
                used_available.append(pd.Timestamp(label["outcome_available_at"]))
            class_probabilities = dict(sorted(votes.items()))
            predicted_policy = min(votes, key=lambda value: (-votes[value], value))
            meta = policy_meta.loc[predicted_policy]
            predicted_specialist = str(meta["specialist"])
            predicted_horizon = int(meta["horizon"])
            predicted_direction = str(meta["direction"])
            max_available = max(used_available)
        actual_policy = None if actual is None else str(actual["policy_id"])
        rows.append({
            "decision_time": pd.Timestamp(stamp),
            "target_type": "primitive_policy_id",
            "training_label_count": len(eligible),
            "neighbor_count": int(neighbor_count),
            "max_label_available_at": max_available,
            "predicted_policy_id": predicted_policy,
            "predicted_specialist": predicted_specialist,
            "predicted_horizon": predicted_horizon,
            "predicted_direction": predicted_direction,
            "class_probabilities": class_probabilities,
            "actual_policy_id": actual_policy,
            "actual_specialist": None if actual is None else str(actual["specialist"]),
            "actual_horizon": None if actual is None else int(actual["horizon"]),
            "actual_direction": None if actual is None else str(actual["direction"]),
            "oracle_policy_hit": (
                None if actual_policy is None or predicted_policy is None
                else bool(predicted_policy == actual_policy)
            ),
            "selection_use": False,
            "development_only_nontradable": True,
        })
    return pd.DataFrame(rows)


def causal_oracle_weight_predictor(
    state: pd.DataFrame,
    oracle: pd.DataFrame,
    attributes: list[str],
    *,
    k: int = 10,
    sparse_k: int = 8,
    horizons: Sequence[int] = FOUNDATION_CONTEXT_HORIZONS,
    max_abs_contracts: float = 1.5,
    exposure_step_contracts: float = 0.25,
) -> pd.DataFrame:
    normalized = causal_standardized_attributes(state, attributes).set_index("decision_time")
    labels = oracle.copy()
    labels["decision_time"] = pd.to_datetime(labels["decision_time"], utc=True)
    labels_by_time = labels.set_index("decision_time")
    rows: list[dict[str, Any]] = []
    for stamp in pd.to_datetime(state["decision_time"], utc=True):
        current = normalized.loc[stamp, attributes].to_numpy(dtype=float)
        actual = labels_by_time.loc[stamp] if stamp in labels_by_time.index else None
        horizon_predictions: dict[str, dict[str, Any]] = {}
        for horizon in horizons:
            hkey = str(int(horizon))
            eligible_rows: list[pd.Series] = []
            for label in labels.itertuples(index=False):
                solution = dict(label.horizon_solutions).get(hkey, {})
                available = solution.get("outcome_available_at")
                if available is not None and not pd.isna(available) and pd.Timestamp(available) < stamp:
                    eligible_rows.append(pd.Series(label._asdict()))
            if not eligible_rows:
                horizon_predictions[hkey] = {
                    "training_label_count": 0, "max_label_available_at": None,
                    "predicted_weights": {}, "predicted_exposure": 0.0,
                    "weight_implied_exposure": 0.0, "weight_exposure_consistency_error_abs": 0.0,
                    "predicted_direction": "flat", "predicted_side": 0,
                    "predicted_top_attribute": None, "oracle_exposure_error_abs": None,
                    "oracle_side_hit": None, "oracle_top_attribute_hit": None,
                    "weight_cosine_similarity": None,
                }
                continue
            candidates = []
            for label in eligible_rows:
                prior = normalized.loc[pd.Timestamp(label["decision_time"]), attributes].to_numpy(dtype=float)
                candidates.append((float(np.linalg.norm(current - prior)), label))
            candidates.sort(key=lambda item: (item[0], pd.Timestamp(item[1]["decision_time"])))
            chosen = candidates[: min(int(k), len(candidates))]
            distances = np.asarray([item[0] for item in chosen], dtype=float)
            alphas = 1.0 / np.maximum(distances, 1e-9)
            alphas /= alphas.sum()
            predicted = np.zeros(len(attributes), dtype=float)
            predicted_exposure_raw = 0.0
            used_available: list[pd.Timestamp] = []
            for alpha, (_distance, label) in zip(alphas, chosen, strict=True):
                solution = dict(label["horizon_solutions"])[hkey]
                sparse = dict(solution["sparse_solutions"])
                chosen_sparse = sparse.get(str(int(sparse_k)), next(iter(sparse.values())))
                predicted += float(alpha) * _dict_vector(dict(chosen_sparse["weights"]), attributes)
                predicted_exposure_raw += float(alpha) * float(solution["optimal_exposure"])
                used_available.append(pd.Timestamp(solution["outcome_available_at"]))
            order = np.argsort(-np.abs(predicted), kind="stable")
            keep = np.zeros(len(attributes), dtype=bool)
            keep[order[: min(int(sparse_k), len(attributes))]] = True
            predicted[~keep] = 0.0
            predicted_exposure = float(np.clip(
                round(predicted_exposure_raw / exposure_step_contracts) * exposure_step_contracts,
                -max_abs_contracts, max_abs_contracts,
            ))
            weight_implied_exposure = float(np.dot(predicted, current))
            side = int(np.sign(predicted_exposure))
            weight_map = {
                name: float(value) for name, value in zip(attributes, predicted, strict=True)
                if abs(value) > 1e-15
            }
            top = min(weight_map, key=lambda name: (-abs(weight_map[name]), name)) if weight_map else None
            actual_solution = dict(actual["horizon_solutions"]).get(hkey, {}) if actual is not None else {}
            actual_observed = bool(
                actual_solution.get("oracle_outcome_observed", False)
                and actual_solution.get("outcome_available_at") is not None
                and not pd.isna(actual_solution.get("outcome_available_at"))
            )
            actual_exposure = actual_solution.get("optimal_exposure") if actual_observed else None
            actual_side = int(actual_solution.get("optimal_side", 0)) if actual_observed else None
            actual_sparse = dict(actual_solution.get("sparse_solutions", {})) if actual_observed else {}
            actual_sparse_choice = actual_sparse.get(
                str(int(sparse_k)), next(iter(actual_sparse.values()), {"weights": {}})
            )
            actual_weights = _dict_vector(dict(actual_sparse_choice.get("weights", {})), attributes)
            actual_weight_map = dict(actual_sparse_choice.get("weights", {}))
            actual_top = (
                min(actual_weight_map, key=lambda name: (-abs(actual_weight_map[name]), name))
                if actual_weight_map else None
            )
            denom = float(np.linalg.norm(predicted) * np.linalg.norm(actual_weights))
            cosine = (
                None if not actual_observed or denom <= 1e-15
                else float(np.dot(predicted, actual_weights) / denom)
            )
            horizon_predictions[hkey] = {
                "training_label_count": len(eligible_rows),
                "max_label_available_at": max(used_available),
                "predicted_weights": weight_map,
                "predicted_exposure": predicted_exposure,
                "weight_implied_exposure": weight_implied_exposure,
                "weight_exposure_consistency_error_abs": abs(weight_implied_exposure - predicted_exposure),
                "predicted_direction": "long" if side > 0 else "short" if side < 0 else "flat",
                "predicted_side": side,
                "predicted_top_attribute": top,
                "oracle_outcome_observed": bool(actual_observed),
                "oracle_exposure_error_abs": (
                    None if actual_exposure is None else abs(predicted_exposure - float(actual_exposure))
                ),
                "oracle_side_hit": (
                    bool(side == actual_side) if actual_observed else None
                ),
                "oracle_top_attribute_hit": (
                    bool(top == actual_top) if actual_observed else None
                ),
                "weight_cosine_similarity": cosine,
                "diagnostic_interpretation": "exposure_reconstruction_representation_not_feature_importance",
                "feature_importance_inference": False,
            }
        primary = horizon_predictions.get("1", next(iter(horizon_predictions.values())))
        rows.append({
            "decision_time": pd.Timestamp(stamp),
            "training_label_count": int(primary["training_label_count"]),
            "max_label_available_at": primary["max_label_available_at"],
            "predicted_weights": dict(primary["predicted_weights"]),
            "predicted_exposure": float(primary["predicted_exposure"]),
            "weight_implied_exposure": float(primary["weight_implied_exposure"]),
            "weight_exposure_consistency_error_abs": float(primary["weight_exposure_consistency_error_abs"]),
            "predicted_direction": str(primary["predicted_direction"]),
            "predicted_side": int(primary["predicted_side"]),
            "predicted_top_attribute": primary["predicted_top_attribute"],
            "oracle_exposure_error_abs": primary["oracle_exposure_error_abs"],
            "oracle_side_hit": primary["oracle_side_hit"],
            "oracle_top_attribute_hit": primary["oracle_top_attribute_hit"],
            "weight_cosine_similarity": primary["weight_cosine_similarity"],
            "horizon_predictions": horizon_predictions,
            "diagnostic_interpretation": "exposure_reconstruction_representation_not_feature_importance",
            "feature_importance_inference": False,
            "selection_use": False,
        })
    return pd.DataFrame(rows)


def oracle_predictor_causal_check(frame: pd.DataFrame) -> bool:
    if frame.empty:
        return True
    for row in frame.itertuples(index=False):
        decision = pd.Timestamp(row.decision_time)
        used = getattr(row, "max_label_available_at", None)
        if used is not None and not pd.isna(used) and pd.Timestamp(used) >= decision:
            return False
        for payload in getattr(row, "horizon_predictions", {}).values():
            nested = payload.get("max_label_available_at")
            if nested is not None and not pd.isna(nested) and pd.Timestamp(nested) >= decision:
                return False
    return True
