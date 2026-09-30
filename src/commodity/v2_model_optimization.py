from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from commodity import v2_optimization as v2
from commodity.market_only_phase2 import (
    _build_segmented_decision_origins,
    _canonicalize_one_origin_per_fill,
)


class Issue427OptimizationError(RuntimeError):
    pass


def _stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def build_issue427_model_candidates(
    base_config: Mapping[str, object], prereg: Mapping[str, object]
) -> list[dict[str, object]]:
    search = prereg.get("model_search")
    if not isinstance(search, Mapping):
        raise Issue427OptimizationError("issue-427 model search is missing")
    rows: list[dict[str, object]] = []

    mean_cfg = dict(base_config)
    mean_cfg["model.model_id"] = "expanding_mean"
    mean_cfg["model.training_window"] = "expanding"
    rows.append(mean_cfg)

    ridge = search.get("ridge")
    if not isinstance(ridge, Mapping):
        raise Issue427OptimizationError("issue-427 ridge search is missing")
    for alpha in ridge.get("alpha", []):
        for window in ridge.get("training_windows", []):
            cfg = dict(base_config)
            cfg.update(
                {
                    "model.model_id": "ridge",
                    "model.training_window": str(window),
                    "model.ridge_alpha": float(alpha),
                }
            )
            rows.append(cfg)

    for profile in search.get("hist_gb_profiles", []):
        if not isinstance(profile, Mapping):
            raise Issue427OptimizationError("issue-427 HistGB profile is invalid")
        for window in search.get("hist_gb_training_windows", []):
            cfg = dict(base_config)
            cfg.update(
                {
                    "model.model_id": "hist_gb",
                    "model.training_window": str(window),
                    "model.hist_gb_learning_rate": float(profile["learning_rate"]),
                    "model.hist_gb_max_iter": int(profile["max_iter"]),
                    "model.hist_gb_max_leaf_nodes": int(profile["max_leaf_nodes"]),
                }
            )
            rows.append(cfg)

    expected = int(search.get("candidate_count", -1))
    identities = {_stable_sha(row) for row in rows}
    if len(rows) != expected or len(identities) != expected:
        raise Issue427OptimizationError(
            f"issue-427 model candidate count changed: expected={expected} observed={len(rows)} unique={len(identities)}"
        )
    return rows


def prepare_issue427_market_origins(
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    config: Mapping[str, object],
    *,
    round_trip_per_mmbtu: float,
) -> tuple[pd.DataFrame, list[str]]:
    prepared, feature_columns = v2.prepare_issue425_features(
        features, v2._issue425_transform_config(config)
    )
    origins, rebuilt_columns = _build_segmented_decision_origins(
        session_path,
        prepared,
        horizon_sessions=int(config["target.horizon_sessions"]),
    )
    if origins.empty or set(rebuilt_columns) != set(feature_columns):
        raise Issue427OptimizationError("issue-427 market origin reconstruction changed")
    origins, _ = _canonicalize_one_origin_per_fill(origins)
    attached = v2._attach_issue425_targets(
        origins,
        session_path,
        horizon_sessions=int(config["target.horizon_sessions"]),
        role=str(config["target.target_role"]),
        aggregation=str(config["target.aggregation"]),
        round_trip_per_mmbtu=float(round_trip_per_mmbtu),
    )
    return attached, list(rebuilt_columns)


def score_issue427_config(
    origins: pd.DataFrame,
    feature_columns: Sequence[str],
    session_path: pd.DataFrame,
    config: Mapping[str, object],
    blocks: Sequence[Mapping[str, str]],
    phase2_cfg: Mapping[str, Any],
    risk: object,
    costs: object,
    *,
    minimum_training_rows: int,
) -> dict[str, object]:
    rows = [
        v2._score_issue425_block(
            origins,
            feature_columns,
            session_path,
            config,
            phase2_cfg,
            risk,
            costs,
            block_id=str(block["id"]),
            start_date=str(block["start"]),
            end_date=str(block["end"]),
            minimum_training_rows=minimum_training_rows,
        )
        for block in blocks
    ]
    aggregate = v2._aggregate_issue425_blocks(rows)
    aggregate["status"] = "complete"
    aggregate["candidate_id"] = _stable_sha(dict(config))[:20]
    return aggregate


def select_issue427_model(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    return v2.select_issue425_candidate(rows)


def prepare_issue427_feature_set(
    features: pd.DataFrame,
    config: Mapping[str, object],
    candidate_columns: Sequence[str],
) -> tuple[pd.DataFrame, list[str], list[str]]:
    candidates = [str(column) for column in candidate_columns]
    if not candidates or len(candidates) != len(set(candidates)):
        raise Issue427OptimizationError("issue-427 feature set candidates are invalid")
    required = {"trade_date", "available_at", *candidates}
    missing = sorted(required - set(features.columns))
    if missing:
        raise Issue427OptimizationError(f"issue-427 feature set lacks columns: {missing}")

    frame = features.copy().sort_values("trade_date", kind="stable")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    if len(frame) and frame["trade_date"].max() > pd.Timestamp("2022-12-31", tz="UTC"):
        raise Issue427OptimizationError("issue-427 feature set crosses protected cutoff")
    v2._issue425_return_transform(frame, str(config["transforms.return_transform"]))
    control_base = v2._issue425_family_columns(frame, str(config["data.feature_family_subset"]))
    numeric_columns = [*control_base, *candidates]
    numeric = frame[numeric_columns].apply(pd.to_numeric, errors="raise").astype(float)
    lookback = int(config["data.lookback_sessions"])
    lag = int(config["transforms.lag_sessions"])
    stat_window = int(config["transforms.rolling_stat_window_sessions"])
    norm_window = int(config["transforms.normalization_window_sessions"])
    winsor = float(config["transforms.winsor_quantile"])
    if min(lookback, lag, stat_window, norm_window) < 1 or not 0.0 <= winsor < 0.5:
        raise Issue427OptimizationError("issue-427 feature transform settings are invalid")
    if winsor > 0.0:
        shifted = numeric.shift(1)
        history = shifted.rolling(window=lookback, min_periods=min(20, lookback))
        numeric = numeric.clip(
            lower=history.quantile(winsor),
            upper=history.quantile(1.0 - winsor),
            axis=1,
        )
    lagged = numeric.shift(lag)
    history = numeric.shift(1).rolling(window=stat_window, min_periods=stat_window)
    derived = pd.concat(
        [lagged, history.mean().add_suffix(f"__mean{stat_window}"), history.std(ddof=0).add_suffix(f"__std{stat_window}")],
        axis=1,
    )
    scaled = v2._issue425_rolling_scale(
        derived, str(config["transforms.scaling"]), norm_window
    )
    candidate_transformed = [
        name
        for column in candidates
        for name in (column, f"{column}__mean{stat_window}", f"{column}__std{stat_window}")
    ]
    control_columns = [column for column in scaled.columns if column not in candidate_transformed]
    if not control_columns or set(control_columns) & set(candidate_transformed):
        raise Issue427OptimizationError("issue-427 matched control identity is invalid")
    output_columns = [*control_columns, *candidate_transformed]
    output = pd.concat([frame[["trade_date", "available_at"]], scaled], axis=1)
    output = output.replace([np.inf, -np.inf], np.nan).dropna(subset=output_columns).copy()
    if output.empty or not np.isfinite(output[output_columns].to_numpy(dtype=float)).all():
        raise Issue427OptimizationError("issue-427 feature transform produced invalid rows")
    return output, candidate_transformed, control_columns


def evaluate_issue427_feature_set(
    *,
    session_path: pd.DataFrame,
    features: pd.DataFrame,
    config: Mapping[str, object],
    candidate_columns: Sequence[str],
    blocks: Sequence[Mapping[str, str]],
    phase2_cfg: Mapping[str, Any],
    risk: object,
    costs: object,
    minimum_training_rows: int,
) -> dict[str, object]:
    prepared, candidate_transformed, control_columns = prepare_issue427_feature_set(
        features, config, candidate_columns
    )
    origins, rebuilt = _build_segmented_decision_origins(
        session_path,
        prepared,
        horizon_sessions=int(config["target.horizon_sessions"]),
    )
    if origins.empty or set(rebuilt) != set(candidate_transformed) | set(control_columns):
        raise Issue427OptimizationError("issue-427 feature origin identity changed")
    origins, _ = _canonicalize_one_origin_per_fill(origins)
    multiplier = float(phase2_cfg["execution_contract"]["contract_multiplier_mmbtu"])
    origins = v2._attach_issue425_targets(
        origins,
        session_path,
        horizon_sessions=int(config["target.horizon_sessions"]),
        role=str(config["target.target_role"]),
        aggregation=str(config["target.aggregation"]),
        round_trip_per_mmbtu=float(costs.round_trip_usd) / multiplier,
    )
    candidate = score_issue427_config(
        origins,
        [*control_columns, *candidate_transformed],
        session_path,
        config,
        blocks,
        phase2_cfg,
        risk,
        costs,
        minimum_training_rows=minimum_training_rows,
    )
    control = score_issue427_config(
        origins,
        control_columns,
        session_path,
        config,
        blocks,
        phase2_cfg,
        risk,
        costs,
        minimum_training_rows=minimum_training_rows,
    )
    candidate_score = candidate["monthly_score"]
    control_score = control["monthly_score"]
    assert isinstance(candidate_score, Mapping) and isinstance(control_score, Mapping)
    candidate["matched_control"] = control
    candidate["matched_origin_count"] = len(origins)
    candidate["candidate_feature_columns"] = list(candidate_columns)
    candidate["ablation"] = {
        "mean_monthly_net_return_delta": float(candidate_score["mean_monthly_net_return"])
        - float(control_score["mean_monthly_net_return"]),
        "total_net_pnl_usd_delta": float(candidate_score["total_net_pnl_usd"])
        - float(control_score["total_net_pnl_usd"]),
        "max_drawdown_fraction_delta": float(candidate_score["max_drawdown_fraction"])
        - float(control_score["max_drawdown_fraction"]),
        "transaction_cost_usd_delta": float(candidate_score["transaction_cost_usd"])
        - float(control_score["transaction_cost_usd"]),
    }
    return candidate


def evaluate_issue427_advantage(
    outer_deltas: Sequence[float], *, required_nonnegative_fraction: float
) -> dict[str, object]:
    values = [float(value) for value in outer_deltas]
    if not values:
        return {
            "passes": False,
            "mean_outer_monthly_net_return_delta": None,
            "nonnegative_outer_fraction": 0.0,
        }
    mean_delta = float(np.mean(values))
    nonnegative_fraction = float(np.mean(np.asarray(values) >= 0.0))
    return {
        "passes": bool(mean_delta > 0.0 and nonnegative_fraction >= required_nonnegative_fraction),
        "mean_outer_monthly_net_return_delta": mean_delta,
        "nonnegative_outer_fraction": nonnegative_fraction,
        "outer_deltas": values,
    }


def build_issue427_volatility_tail_features(features: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "available_at", "feature_ret_1"}
    missing = sorted(required - set(features.columns))
    if missing:
        raise Issue427OptimizationError(
            f"issue-427 volatility/tail frame lacks columns: {missing}"
        )
    out = features[["trade_date", "available_at"]].copy()
    returns = pd.to_numeric(features["feature_ret_1"], errors="raise").astype(float)
    past = returns.shift(1)
    squared = past.pow(2)
    ewma_variance = squared.ewm(alpha=0.06, adjust=False).mean()
    out["feature_issue427_ewma_vol"] = np.sqrt(ewma_variance.clip(lower=0.0))

    past_abs = past.abs()
    har_week = past_abs.rolling(5, min_periods=5).mean()
    har_month = past_abs.rolling(22, min_periods=22).mean()
    out["feature_issue427_har_rv"] = (past_abs + har_week + har_month) / 3.0

    alpha, beta = 0.05, 0.94
    unconditional = squared.expanding(min_periods=20).mean()
    garch = np.full(len(out), np.nan, dtype=float)
    previous_variance = np.nan
    for index in range(len(out)):
        prior_return = past.iloc[index]
        prior_scale = unconditional.iloc[index]
        if not np.isfinite(prior_return) or not np.isfinite(prior_scale):
            continue
        if not np.isfinite(previous_variance):
            previous_variance = float(prior_scale)
        omega = (1.0 - alpha - beta) * float(prior_scale)
        variance = omega + alpha * float(prior_return) * float(prior_return)
        variance += beta * previous_variance
        garch[index] = max(variance, 0.0)
        previous_variance = variance
    out["feature_issue427_garch_vol"] = np.sqrt(garch)
    rolling_std = past.rolling(20, min_periods=20).std(ddof=0)
    jumps = (past_abs > (2.0 * rolling_std)).astype(float)
    out["feature_issue427_jump_intensity"] = jumps.rolling(20, min_periods=20).mean()
    tail_quantile = past.rolling(60, min_periods=60).quantile(0.10)
    out["feature_issue427_tail_loss_state"] = -tail_quantile.clip(upper=0.0)
    out["feature_issue427_vol_of_vol"] = out["feature_issue427_ewma_vol"].rolling(
        20, min_periods=20
    ).std(ddof=0)
    return out

def merge_issue427_specialist_features(
    features: pd.DataFrame,
    session_path: pd.DataFrame,
    specialist: pd.DataFrame,
    feature_columns: Sequence[str],
) -> pd.DataFrame:
    required = {"trade_date", "available_at"}
    if not required.issubset(features.columns):
        raise Issue427OptimizationError("issue-427 base features lack PIT timestamps")
    specialist_required = {"trade_date", "contract_id", "prediction_time", *feature_columns}
    missing = sorted(specialist_required - set(specialist.columns))
    if missing:
        raise Issue427OptimizationError(
            f"issue-427 specialist frame lacks columns: {missing}"
        )
    selected = session_path[["trade_date", "contract_id"]].copy()
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], utc=True, errors="raise")
    selected = selected.drop_duplicates()
    if selected["trade_date"].duplicated().any():
        raise Issue427OptimizationError("issue-427 selected contract path is ambiguous")
    base = features.copy()
    base["trade_date"] = pd.to_datetime(base["trade_date"], utc=True, errors="raise")
    base["available_at"] = pd.to_datetime(base["available_at"], utc=True, errors="raise")
    merged = base.merge(selected, on="trade_date", how="left", validate="one_to_one")
    if merged["contract_id"].isna().any():
        raise Issue427OptimizationError("issue-427 selected contract coverage is incomplete")

    extra = specialist.copy()
    extra["trade_date"] = pd.to_datetime(extra["trade_date"], utc=True, errors="raise")
    extra["prediction_time"] = pd.to_datetime(
        extra["prediction_time"], utc=True, errors="raise", format="mixed"
    )
    if extra.duplicated(["trade_date", "contract_id"]).any():
        raise Issue427OptimizationError("issue-427 specialist PIT grain is duplicated")
    merged = merged.merge(
        extra[["trade_date", "contract_id", "prediction_time", *feature_columns]],
        on=["trade_date", "contract_id"],
        how="left",
        validate="one_to_one",
    )
    if merged[list(feature_columns)].isna().any().any() or merged["prediction_time"].isna().any():
        raise Issue427OptimizationError("issue-427 specialist coverage is incomplete")
    expected_time = merged["available_at"].dt.floor("us")
    observed_time = merged["prediction_time"].dt.floor("us")
    if not expected_time.equals(observed_time):
        raise Issue427OptimizationError(
            "issue-427 specialist prediction time does not match information cutoff"
        )
    return merged.drop(columns=["contract_id", "prediction_time"])
