from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from commodity.contracts import ForecastModel
from commodity.evaluation import (
    evaluate_predictions,
    paired_block_bootstrap_rmse,
    walk_forward_predict_with_label_availability,
)
from commodity.models.baselines import RidgeReturnModel, ZeroReturnModel
from commodity.research_construction import (
    build_m1_m6_log_curve_slope,
    same_contract_log_returns,
)

DTE_BUCKET_ORDER = ("0-30", "31-60", "61-90", "91-180", "181-365", "366+")
FORECAST_AVAILABILITY_OFFSET = pd.Timedelta(hours=23, minutes=59)


def split_reserved_confirmation(
    frame: pd.DataFrame,
    *,
    planning_fraction: float = 0.2,
    label_available_at_column: str | None = None,
    minimum_research_rows: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Prepare/verify 100% of a panel, then reserve the latest rows from research use."""
    if frame.empty:
        raise ValueError("Reserved-confirmation split requires a non-empty prepared frame")
    if not 0.0 < planning_fraction < 1.0:
        raise ValueError("Reserved-confirmation planning fraction must be between zero and one")
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("Reserved-confirmation split requires chronological unique timestamps")
    if frame.isna().any().any():
        raise ValueError("Prepared confirmation frame contains missing values")
    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty and not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("Prepared confirmation frame contains non-finite numeric values")

    reserve_rows = max(1, math.ceil(len(frame) * planning_fraction))
    if reserve_rows >= len(frame):
        raise ValueError("Reserved-confirmation split leaves no research rows")
    reserved = frame.iloc[-reserve_rows:].copy()
    research = frame.iloc[:-reserve_rows].copy()
    boundary = reserved.index[0]
    purged_boundary_rows = 0
    if label_available_at_column is not None:
        if label_available_at_column not in research.columns:
            raise ValueError(
                f"Reserved-confirmation split is missing {label_available_at_column}"
            )
        label_available = pd.to_datetime(
            research[label_available_at_column], utc=True, errors="coerce"
        )
        if label_available.isna().any():
            raise ValueError("Reserved-confirmation label availability contains invalid timestamps")
        keep = label_available < boundary
        purged_boundary_rows = int((~keep).sum())
        research = research.loc[keep].copy()
    if len(research) < minimum_research_rows:
        raise ValueError("Reserved-confirmation split leaves too few research rows")

    canonical = reserved.sort_index().reindex(sorted(reserved.columns), axis=1)
    content = canonical.to_json(
        orient="split",
        date_format="iso",
        date_unit="ns",
        double_precision=15,
    ).encode("utf-8")
    metadata = {
        "planning_fraction": planning_fraction,
        "prepared_rows": len(frame),
        "research_rows": len(research),
        "reserved_rows": len(reserved),
        "reserved_fraction": len(reserved) / len(frame),
        "reserved_start": boundary,
        "reserved_end": reserved.index[-1],
        "purged_boundary_rows": purged_boundary_rows,
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "preparation_verification_scope": "full_prepared_frame",
        "preparation_verification_status": "passed",
        "pre_freeze_outcome_use": False,
    }
    return research, reserved, metadata


class FeatureBaselineModel:
    def __init__(self, feature_column: str) -> None:
        self.feature_column = feature_column

    def fit(self, x: pd.DataFrame, y: pd.Series) -> FeatureBaselineModel:
        if x.empty or not x.index.equals(y.index):
            raise ValueError("Feature baseline requires aligned non-empty training data")
        if self.feature_column not in x.columns:
            raise ValueError(f"Feature baseline is missing {self.feature_column}")
        return self

    def predict(self, x: pd.DataFrame) -> pd.Series:
        if self.feature_column not in x.columns:
            raise ValueError(f"Feature baseline is missing {self.feature_column}")
        values = pd.to_numeric(x[self.feature_column], errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError("Feature baseline requires finite prediction values")
        return pd.Series(values.to_numpy(dtype=float), index=x.index, name="prediction")


class ColumnSubsetRidgeModel:
    """Fixed ridge benchmark that deliberately ignores non-benchmark columns."""

    def __init__(self, columns: tuple[str, ...], *, alpha: float = 10.0) -> None:
        if not columns:
            raise ValueError("Column-subset ridge requires at least one feature")
        self.columns = columns
        self.model = RidgeReturnModel(alpha=alpha)

    def _select(self, x: pd.DataFrame) -> pd.DataFrame:
        missing = sorted(set(self.columns) - set(x.columns))
        if missing:
            raise ValueError(f"Column-subset ridge is missing features: {missing}")
        return x.loc[:, list(self.columns)]

    def fit(self, x: pd.DataFrame, y: pd.Series) -> ColumnSubsetRidgeModel:
        self.model.fit(self._select(x), y)
        return self

    def predict(self, x: pd.DataFrame) -> pd.Series:
        return self.model.predict(self._select(x))


def _prepare_contracts(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "contract_id", "expiration", "settle", "volume", "available_at"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Phase-1 market contracts are missing columns: {missing}")
    out = frame.loc[:, sorted(required)].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="coerce")
    out["expiration"] = pd.to_datetime(out["expiration"], utc=True, errors="coerce")
    out["available_at"] = pd.to_datetime(out["available_at"], utc=True, errors="coerce")
    for column in ("settle", "volume"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    required_values = ["trade_date", "expiration", "available_at", "settle"]
    if out[required_values].isna().any().any():
        raise ValueError("Phase-1 market contracts contain missing required values")
    if (out["settle"] <= 0.0).any():
        raise ValueError("Phase-1 market contracts require positive settlements")
    observed_volume = out["volume"].dropna()
    if (observed_volume < 0.0).any():
        raise ValueError("Phase-1 market contracts require non-negative observed volume")
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise ValueError("Phase-1 market contracts contain duplicate trade_date/contract_id")
    if (out["trade_date"] > out["expiration"]).any():
        raise ValueError("Phase-1 market contracts contain rows after expiration")
    return out.sort_values(["trade_date", "expiration", "contract_id"], kind="stable").reset_index(drop=True)


def _front_daily_targets(frame: pd.DataFrame) -> pd.DataFrame:
    out = _prepare_contracts(frame)
    out["maturity_rank"] = out.groupby("trade_date", sort=False).cumcount() + 1
    front = out.loc[out["maturity_rank"] == 1].copy()
    front = front.sort_values("trade_date", kind="stable").reset_index(drop=True)
    front["days_to_maturity"] = (
        (front["expiration"] - front["trade_date"]).dt.total_seconds() / 86400.0
    )
    if (front["days_to_maturity"] <= 0.0).any():
        raise ValueError("Front contract requires positive days to maturity")

    sessions = pd.Series(out["trade_date"].drop_duplicates().sort_values().to_numpy())
    session_map = pd.DataFrame({"trade_date": sessions})
    session_map["target_start_trade_date"] = session_map["trade_date"].shift(-1)
    session_map["target_end_trade_date"] = session_map["trade_date"].shift(-2)
    front = front.merge(session_map, on="trade_date", how="left", validate="one_to_one")

    prices = out[["trade_date", "contract_id", "settle"]].copy()
    start_prices = prices.rename(
        columns={"trade_date": "target_start_trade_date", "settle": "target_start_settle"}
    )
    end_prices = prices.rename(
        columns={"trade_date": "target_end_trade_date", "settle": "target_end_settle"}
    )
    front = front.merge(
        start_prices,
        on=["target_start_trade_date", "contract_id"],
        how="left",
        validate="many_to_one",
    ).merge(
        end_prices,
        on=["target_end_trade_date", "contract_id"],
        how="left",
        validate="many_to_one",
    )
    front["prediction_available_at"] = front["trade_date"] + FORECAST_AVAILABILITY_OFFSET
    front["target_end_available_at"] = (
        front["target_end_trade_date"] + FORECAST_AVAILABILITY_OFFSET
    )
    front["winter"] = front["trade_date"].dt.month.isin([11, 12, 1, 2, 3]).astype(float)
    front["days_to_maturity_x_winter"] = front["days_to_maturity"] * front["winter"]
    front["target_next_return"] = np.log(
        front["target_end_settle"] / front["target_start_settle"]
    )
    front["target_next_abs_return"] = front["target_next_return"].abs()
    return front


def build_front_forecast_panel(frame: pd.DataFrame) -> pd.DataFrame:
    contracts = _prepare_contracts(frame)
    returns = same_contract_log_returns(contracts, price_column="settle")
    returns["trailing_20_abs_return"] = (
        returns.groupby("contract_id", sort=False)["log_return"]
        .transform(lambda values: values.abs().rolling(20, min_periods=20).mean())
    )
    front = _front_daily_targets(contracts)
    front = front.merge(
        returns[["trade_date", "contract_id", "trailing_20_abs_return"]],
        on=["trade_date", "contract_id"],
        how="left",
        validate="one_to_one",
    )
    front = front.dropna(
        subset=[
            "target_start_trade_date",
            "target_end_trade_date",
            "target_next_return",
            "trailing_20_abs_return",
        ]
    ).copy()
    front = front.set_index("prediction_available_at").sort_index()
    return front[[
        "target_start_trade_date",
        "target_end_trade_date",
        "target_end_available_at",
        "trailing_20_abs_return",
        "days_to_maturity",
        "winter",
        "days_to_maturity_x_winter",
        "target_next_return",
        "target_next_abs_return",
    ]]


def build_curve_forecast_panel(frame: pd.DataFrame) -> pd.DataFrame:
    contracts = _prepare_contracts(frame)
    slopes = build_m1_m6_log_curve_slope(contracts, price_column="settle")
    front = _front_daily_targets(contracts)
    joined = slopes.merge(
        front[[
            "trade_date",
            "prediction_available_at",
            "target_start_trade_date",
            "target_end_trade_date",
            "target_end_available_at",
            "target_next_return",
        ]],
        on="trade_date",
        how="inner",
        validate="one_to_one",
    ).dropna(subset=["target_next_return"])
    joined["winter"] = joined["season"].eq("winter_withdrawal").astype(float)
    joined["m1_m6_log_slope_x_winter"] = joined["m1_m6_log_slope"] * joined["winter"]
    joined = joined.set_index("prediction_available_at").sort_index()
    return joined[[
        "target_start_trade_date",
        "target_end_trade_date",
        "target_end_available_at",
        "m1_m6_log_slope",
        "winter",
        "m1_m6_log_slope_x_winter",
        "target_next_return",
    ]]


def _front_with_trailing_volatility(frame: pd.DataFrame) -> pd.DataFrame:
    contracts = _prepare_contracts(frame)
    returns = same_contract_log_returns(contracts, price_column="settle")
    returns["trailing_20_abs_return"] = (
        returns.groupby("contract_id", sort=False)["log_return"]
        .transform(lambda values: values.abs().rolling(20, min_periods=20).mean())
    )
    front = _front_daily_targets(contracts)
    front = front.merge(
        returns[["trade_date", "contract_id", "trailing_20_abs_return"]],
        on=["trade_date", "contract_id"],
        how="left",
        validate="one_to_one",
    )
    return front.dropna(
        subset=[
            "target_next_return",
            "target_start_trade_date",
            "target_end_trade_date",
            "trailing_20_abs_return",
        ]
    ).copy()


def build_storage_forecast_panel(
    frame: pd.DataFrame,
    events: pd.DataFrame,
    *,
    development_rows: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {
        "available_at",
        "storage_lower48_bcf",
        "storage_weekly_change_bcf",
        "revision_status",
        "source_event_type",
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"Storage forecast events are missing columns: {missing}")
    releases = events.loc[events["source_event_type"].astype(str).eq("release")].copy()
    if releases.empty:
        raise ValueError("Storage forecast requires release events")
    if not releases["revision_status"].astype(str).eq("point_in_time").all():
        raise ValueError("Storage forecast requires point-in-time release states")
    releases["release_available_at"] = pd.to_datetime(
        releases["available_at"], utc=True, errors="coerce"
    )
    releases["storage_lower48_bcf"] = pd.to_numeric(
        releases["storage_lower48_bcf"], errors="coerce"
    )
    releases["storage_weekly_change_bcf"] = pd.to_numeric(
        releases["storage_weekly_change_bcf"], errors="coerce"
    )
    if releases[["release_available_at", "storage_lower48_bcf"]].isna().any().any():
        raise ValueError("Storage forecast releases contain invalid required values")
    releases["release_date"] = releases["release_available_at"].dt.tz_convert(
        "America/New_York"
    ).dt.date
    releases = releases.drop(columns=["available_at"])
    if releases["release_date"].duplicated().any():
        raise ValueError("Storage forecast releases contain duplicate release dates")

    front = _front_with_trailing_volatility(frame)
    front["release_date"] = front["trade_date"].dt.date
    joined = releases.merge(front, on="release_date", how="inner", validate="one_to_one")
    valid_market_rows = len(joined)
    excluded_no_same_contract_target = len(releases) - valid_market_rows
    if joined.empty:
        raise ValueError("Storage forecast has no valid same-contract release-day targets")
    if (joined["prediction_available_at"] < joined["release_available_at"]).any():
        raise ValueError("Storage state is not available before the market prediction time")
    joined = joined.dropna(subset=["storage_weekly_change_bcf"]).sort_values(
        "prediction_available_at", kind="stable"
    ).reset_index(drop=True)
    if development_rows < 3 or len(joined) < development_rows + 3:
        raise ValueError("Storage forecast requires development rows plus at least three OOS rows")

    development = joined.iloc[:development_rows]
    level_mean = float(development["storage_lower48_bcf"].mean())
    level_std = float(development["storage_lower48_bcf"].std(ddof=0))
    change_mean = float(development["storage_weekly_change_bcf"].mean())
    change_std = float(development["storage_weekly_change_bcf"].std(ddof=0))
    if level_std <= 0.0 or change_std <= 0.0:
        raise ValueError("Storage forecast development state must have non-zero variation")
    low_threshold = float(development["storage_lower48_bcf"].quantile(0.25))
    joined["storage_level_z"] = (joined["storage_lower48_bcf"] - level_mean) / level_std
    joined["storage_change_z"] = (
        joined["storage_weekly_change_bcf"] - change_mean
    ) / change_std
    joined["low_inventory"] = joined["storage_lower48_bcf"].le(low_threshold).astype(float)
    joined["winter"] = joined["trade_date"].dt.month.isin([11, 12, 1, 2, 3]).astype(float)
    joined["storage_level_z_x_winter"] = joined["storage_level_z"] * joined["winter"]
    joined["low_inventory_x_winter"] = joined["low_inventory"] * joined["winter"]
    state = {
        "release_rows": len(releases),
        "valid_same_contract_market_rows": valid_market_rows,
        "excluded_no_same_contract_target": excluded_no_same_contract_target,
        "development_rows": development_rows,
        "storage_level_mean_bcf": level_mean,
        "storage_level_std_bcf": level_std,
        "storage_change_mean_bcf": change_mean,
        "storage_change_std_bcf": change_std,
        "low_inventory_threshold_bcf": low_threshold,
        "low_inventory_quantile": 0.25,
        "state_fit_scope": "development_point_in_time_storage_only",
    }
    joined = joined.set_index("prediction_available_at").sort_index()
    return joined[[
        "trade_date",
        "target_start_trade_date",
        "target_end_trade_date",
        "target_end_available_at",
        "release_available_at",
        "trailing_20_abs_return",
        "storage_level_z",
        "storage_change_z",
        "low_inventory",
        "winter",
        "storage_level_z_x_winter",
        "low_inventory_x_winter",
        "target_next_return",
        "target_next_abs_return",
    ]], state


def build_announcement_forecast_panel(
    frame: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    required = {"available_at", "source_event_type"}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"Announcement events are missing columns: {missing}")
    releases = events.loc[events["source_event_type"].astype(str).eq("release")].copy()
    if releases.empty:
        raise ValueError("Announcement forecast requires release events")
    releases["release_available_at"] = pd.to_datetime(
        releases["available_at"], utc=True, errors="coerce"
    )
    if releases["release_available_at"].isna().any():
        raise ValueError("Announcement releases contain invalid availability timestamps")
    local = releases["release_available_at"].dt.tz_convert("America/New_York")
    releases["release_date"] = local.dt.date
    releases["holiday_shifted_release"] = local.dt.day_name().ne("Thursday")
    if releases["release_date"].duplicated().any():
        raise ValueError("Announcement releases contain duplicate release dates")
    release_flags = releases.set_index("release_date")["holiday_shifted_release"].to_dict()
    coverage_start = min(release_flags)
    coverage_end = max(release_flags)

    front = _front_with_trailing_volatility(frame)
    target_dates = front["target_end_trade_date"].dt.date
    front = front.loc[target_dates.between(coverage_start, coverage_end)].copy()
    target_dates = front["target_end_trade_date"].dt.date
    front["target_end_release"] = target_dates.isin(release_flags).astype(float)
    front["holiday_shifted_release"] = target_dates.map(release_flags).eq(True).astype(float)
    front["winter"] = front["target_end_trade_date"].dt.month.isin([11, 12, 1, 2, 3]).astype(float)
    front["target_end_release_x_winter"] = front["target_end_release"] * front["winter"]
    if front.empty:
        raise ValueError("Announcement forecast has no market rows inside release-calendar coverage")
    front = front.set_index("prediction_available_at").sort_index()
    return front[[
        "target_start_trade_date",
        "target_end_trade_date",
        "target_end_available_at",
        "trailing_20_abs_return",
        "target_end_release",
        "holiday_shifted_release",
        "winter",
        "target_end_release_x_winter",
        "target_next_abs_return",
    ]]


def classify_skill_evidence(
    *,
    rmse_improvement: float,
    relative_rmse_improvement: float,
    ci_lower: float,
    ci_upper: float,
    positive_periods: int,
    negative_periods: int,
    min_relative_improvement: float,
) -> str:
    if (
        rmse_improvement > 0.0
        and relative_rmse_improvement >= min_relative_improvement
        and ci_lower > 0.0
        and positive_periods >= 2
    ):
        return "SURVIVE"
    if (
        relative_rmse_improvement <= 0.0 and ci_upper <= 0.0
    ) or negative_periods >= 2:
        return "KILL"
    return "INCONCLUSIVE"


def _rmse(frame: pd.DataFrame) -> float:
    error = frame["prediction"].to_numpy(dtype=float) - frame["actual"].to_numpy(dtype=float)
    return float(np.sqrt(np.mean(error**2)))


def _period_rmse_improvements(
    challenger: pd.DataFrame,
    baseline: pd.DataFrame,
) -> dict[str, float]:
    if not challenger.index.equals(baseline.index):
        raise ValueError("Period scoring requires paired forecasts")
    positions = np.array_split(np.arange(len(challenger)), 3)
    if any(len(position) == 0 for position in positions):
        raise ValueError("Period scoring requires at least three OOS rows")
    return {
        f"period_{i + 1}": _rmse(baseline.iloc[position]) - _rmse(challenger.iloc[position])
        for i, position in enumerate(positions)
    }


def chronological_skill_test(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    label_available_at: pd.Series,
    baseline_factory: Callable[[], ForecastModel],
    initial_train: int,
    retrain_every: int = 5,
    block_size: int = 20,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 327,
    min_relative_improvement: float = 0.01,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if x.empty or not x.index.equals(y.index) or not x.index.equals(label_available_at.index):
        raise ValueError("Chronological skill test requires aligned non-empty inputs")
    if not x.index.is_monotonic_increasing or x.index.has_duplicates:
        raise ValueError("Chronological skill test requires chronological unique timestamps")
    challenger = walk_forward_predict_with_label_availability(
        lambda: RidgeReturnModel(alpha=10.0),
        x,
        y,
        label_available_at,
        initial_train=initial_train,
        retrain_every=retrain_every,
    )
    baseline = walk_forward_predict_with_label_availability(
        baseline_factory,
        x,
        y,
        label_available_at,
        initial_train=initial_train,
        retrain_every=retrain_every,
    )
    uncertainty = paired_block_bootstrap_rmse(
        challenger,
        baseline,
        block_size=block_size,
        resamples=resamples,
        confidence=confidence,
        seed=seed,
    )
    period_improvements = _period_rmse_improvements(challenger, baseline)
    challenger_metrics = evaluate_predictions(challenger)
    baseline_metrics = evaluate_predictions(baseline)
    baseline_rmse = float(baseline_metrics["rmse"])
    rmse_improvement = baseline_rmse - float(challenger_metrics["rmse"])
    relative_improvement = rmse_improvement / baseline_rmse if baseline_rmse > 0.0 else 0.0
    positive_periods = sum(value > 0.0 for value in period_improvements.values())
    negative_periods = sum(value < 0.0 for value in period_improvements.values())
    disposition = classify_skill_evidence(
        rmse_improvement=rmse_improvement,
        relative_rmse_improvement=relative_improvement,
        ci_lower=float(uncertainty["ci_lower"]),
        ci_upper=float(uncertainty["ci_upper"]),
        positive_periods=positive_periods,
        negative_periods=negative_periods,
        min_relative_improvement=min_relative_improvement,
    )
    evidence: dict[str, Any] = {
        "target_rows": len(x),
        "initial_train": initial_train,
        "oos_rows": len(challenger),
        "retrain_every": retrain_every,
        "block_size": block_size,
        "bootstrap_resamples": resamples,
        "challenger": challenger_metrics,
        "baseline": baseline_metrics,
        "rmse_improvement": rmse_improvement,
        "relative_rmse_improvement": relative_improvement,
        "uncertainty": uncertainty,
        "period_rmse_improvements": period_improvements,
        "positive_periods": positive_periods,
        "negative_periods": negative_periods,
        "min_relative_improvement": min_relative_improvement,
        "disposition": disposition,
        "leakage_audit": "passed_feature_and_label_availability",
        "resolved_training_labels_only": True,
    }
    return challenger, baseline, evidence


def rep001_forecast_test(
    panel: pd.DataFrame,
    *,
    initial_train: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = panel[[
        "trailing_20_abs_return",
        "days_to_maturity",
        "winter",
        "days_to_maturity_x_winter",
    ]]
    y = panel["target_next_abs_return"]
    return chronological_skill_test(
        x,
        y,
        label_available_at=panel["target_end_available_at"],
        baseline_factory=lambda: FeatureBaselineModel("trailing_20_abs_return"),
        initial_train=initial_train,
        block_size=20,
    )


def rep002_forecast_test(
    panel: pd.DataFrame,
    *,
    initial_train: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = panel[["m1_m6_log_slope", "winter", "m1_m6_log_slope_x_winter"]]
    y = panel["target_next_return"]
    return chronological_skill_test(
        x,
        y,
        label_available_at=panel["target_end_available_at"],
        baseline_factory=ZeroReturnModel,
        initial_train=initial_train,
        block_size=20,
    )


def rep004_forecast_test(
    panel: pd.DataFrame,
    *,
    initial_train: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = panel[[
        "storage_level_z",
        "storage_change_z",
        "low_inventory",
        "winter",
        "storage_level_z_x_winter",
    ]]
    y = panel["target_next_return"]
    return chronological_skill_test(
        x,
        y,
        label_available_at=panel["target_end_available_at"],
        baseline_factory=ZeroReturnModel,
        initial_train=initial_train,
        block_size=4,
    )


def rep005_forecast_test(
    panel: pd.DataFrame,
    *,
    initial_train: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = panel[[
        "trailing_20_abs_return",
        "storage_level_z",
        "low_inventory",
        "winter",
        "low_inventory_x_winter",
    ]]
    y = panel["target_next_abs_return"]
    return chronological_skill_test(
        x,
        y,
        label_available_at=panel["target_end_available_at"],
        baseline_factory=lambda: FeatureBaselineModel("trailing_20_abs_return"),
        initial_train=initial_train,
        block_size=4,
    )


def rep009_forecast_test(
    panel: pd.DataFrame,
    *,
    initial_train: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = panel[[
        "trailing_20_abs_return",
        "target_end_release",
        "winter",
        "target_end_release_x_winter",
    ]]
    y = panel["target_next_abs_return"]
    return chronological_skill_test(
        x,
        y,
        label_available_at=panel["target_end_available_at"],
        baseline_factory=lambda: FeatureBaselineModel("trailing_20_abs_return"),
        initial_train=initial_train,
        block_size=20,
    )


def rep018_forecast_test(
    panel: pd.DataFrame,
    *,
    initial_train: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    benchmark_columns = (
        "target_end_monday",
        "target_end_tuesday",
        "target_end_wednesday",
        "target_end_friday",
        "winter",
    )
    x = panel[["target_end_release", *benchmark_columns]]
    y = panel["target_next_return"]
    return chronological_skill_test(
        x,
        y,
        label_available_at=panel["target_end_available_at"],
        baseline_factory=lambda: ColumnSubsetRidgeModel(benchmark_columns, alpha=10.0),
        initial_train=initial_train,
        block_size=20,
    )
