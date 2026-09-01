from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from commodity.market_data import DataContractViolation, validate_contract_history
from commodity.rolls import build_derived_contract_path

TARGET_ID = "ng-front-curve-m1m2-change-1session-v1"
DEVELOPMENT_START = pd.Timestamp("2015-01-01", tz="UTC")
DEVELOPMENT_END = pd.Timestamp("2021-12-31", tz="UTC")
CONFIRMATION_START = pd.Timestamp("2022-01-01", tz="UTC")
CONFIRMATION_END = pd.Timestamp("2026-08-12", tz="UTC")
MIN_CONFIRMATION_ROWS = 1100
SCIENTIFIC_MEPI = 0.15
ECONOMIC_MEPI_USD_PER_MMBTU = 0.005
ALPHA = 0.05
TARGET_POWER = 0.80
DEPENDENCE_RHO_FLOOR = 0.25
DEPENDENCE_RHO_CAP = 0.75
MIN_DEVELOPMENT_ROWS = 1500
MAX_PAIR_TRANSITION_SHARE = 0.08
MAX_MONTH_SHARE = 0.12
MAX_YEAR_SHARE = 0.15


@dataclass(frozen=True)
class FrontCurveTargetContract:
    target_id: str = TARGET_ID
    price_semantics: str = "CME final settlement"
    active_front_semantics: str = "volume_crossover_dte_v1 selected contract"
    second_leg_semantics: str = "nearest later outright contract by expiration"
    spread_formula: str = "m1_settle - m2_settle"
    response_formula: str = "next_observed_session_spread - current_spread"
    response_units: str = "USD_per_MMBtu"
    horizon: str = "1_observed_session"
    prediction_time: str = "max(current M1 settlement available_at, current M2 settlement available_at)"
    information_cutoff: str = "only information with available_at <= prediction_time"
    transition_rule: str = "score only when both M1 and M2 contract IDs are unchanged on the next observed session"
    expiry_rule: str = "reuse volume_crossover_dte_v1; never score a cross-pair transition"
    input_validity_rule: str = "curve legs require finite positive settlement and observed nonnegative volume; zero-price/missing-volume placeholders are excluded before roll selection"
    development_end: str = "2021-12-31"
    protected_confirmation_start: str = "2022-01-01"
    protected_confirmation_end: str = "2026-08-12"


def target_contract() -> dict[str, Any]:
    return asdict(FrontCurveTargetContract())


def _front_and_second_leg(
    canonical_rows: pd.DataFrame,
    schema: dict[str, Any],
    roll_policy: dict[str, Any],
) -> pd.DataFrame:
    canonical = validate_contract_history(canonical_rows, schema)
    if "settle" not in canonical.columns or "volume" not in canonical.columns:
        raise DataContractViolation("front-curve target requires settle and volume")
    settle = pd.to_numeric(canonical["settle"], errors="coerce")
    volume = pd.to_numeric(canonical["volume"], errors="coerce")
    valid = np.isfinite(settle) & settle.gt(0) & np.isfinite(volume) & volume.ge(0)
    canonical = canonical.loc[valid].copy()
    canonical["settle"] = settle.loc[valid].astype("float64")
    canonical["volume"] = volume.loc[valid].astype("float64")
    if canonical.empty:
        raise DataContractViolation("front-curve target has no valid positive-settlement rows with observed volume")
    path = build_derived_contract_path(canonical, schema, roll_policy)
    if path.empty:
        raise DataContractViolation("front-curve target has no selected active-front rows")

    by_date = {
        pd.Timestamp(date): group.sort_values(["expiration", "contract_id"])
        for date, group in canonical.groupby("trade_date")
    }
    records: list[dict[str, Any]] = []
    for _, front in path.sort_values("trade_date").iterrows():
        trade_date = pd.Timestamp(front["trade_date"])
        day = by_date[trade_date]
        front_expiration = pd.Timestamp(front["expiration"])
        later = day.loc[day["expiration"] > front_expiration]
        if later.empty:
            continue
        second = later.iloc[0]
        prediction_time = max(
            pd.Timestamp(front["available_at"]), pd.Timestamp(second["available_at"])
        )
        if pd.Timestamp(front["available_at"]) > prediction_time or pd.Timestamp(second["available_at"]) > prediction_time:
            raise DataContractViolation("front-curve pair is not available at prediction time")
        records.append(
            {
                "trade_date": trade_date,
                "prediction_time": prediction_time,
                "m1_contract_id": str(front["contract_id"]),
                "m1_expiration": pd.Timestamp(front["expiration"]),
                "m1_settle": float(front["settle"]),
                "m1_volume": float(front["volume"]),
                "m1_roll_reason": str(front["roll_reason"]),
                "m2_contract_id": str(second["contract_id"]),
                "m2_expiration": pd.Timestamp(second["expiration"]),
                "m2_settle": float(second["settle"]),
                "m2_volume": float(second["volume"]),
            }
        )
    if not records:
        raise DataContractViolation("front-curve target has no M1/M2 pairs")
    result = pd.DataFrame.from_records(records).sort_values("trade_date").reset_index(drop=True)
    result.attrs["source_session_count"] = int(canonical["trade_date"].nunique())
    result.attrs["selected_front_session_count"] = len(path)
    return result


def build_front_curve_target(
    canonical_rows: pd.DataFrame,
    schema: dict[str, Any],
    roll_policy: dict[str, Any],
) -> pd.DataFrame:
    """Build the one permitted M1-M2 spread-change target without cross-pair returns."""
    panel = _front_and_second_leg(canonical_rows, schema, roll_policy)
    panel["spread"] = panel["m1_settle"] - panel["m2_settle"]
    panel["target_trade_date"] = panel["trade_date"].shift(-1)
    same_pair = panel["m1_contract_id"].eq(panel["m1_contract_id"].shift(-1)) & panel[
        "m2_contract_id"
    ].eq(panel["m2_contract_id"].shift(-1))
    panel["same_pair_next_session"] = same_pair
    panel["target_spread_change"] = (panel["spread"].shift(-1) - panel["spread"]).where(same_pair)
    panel["excluded_pair_transition"] = ~same_pair
    panel.loc[panel.index[-1], "excluded_pair_transition"] = False
    return panel


def build_frozen_feature_frame(panel: pd.DataFrame) -> pd.DataFrame:
    """Derive the fixed market-only feature family without fitting a model."""
    required = {
        "trade_date",
        "prediction_time",
        "m1_contract_id",
        "m2_contract_id",
        "m1_expiration",
        "m1_volume",
        "m2_volume",
        "spread",
        "target_spread_change",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise DataContractViolation(f"front-curve panel missing feature inputs: {missing}")
    out = panel.copy()
    prior_same_pair = out["m1_contract_id"].eq(out["m1_contract_id"].shift(1)) & out[
        "m2_contract_id"
    ].eq(out["m2_contract_id"].shift(1))
    lag1 = out["spread"] - out["spread"].shift(1)
    out["lag1_spread_change"] = lag1.where(prior_same_pair)
    out["lag5_mean_spread_change"] = out["lag1_spread_change"].rolling(5, min_periods=5).mean()
    out["m1_calendar_dte"] = (
        out["m1_expiration"].dt.normalize() - out["trade_date"].dt.normalize()
    ).dt.days.astype(float)
    ratio = (out["m2_volume"].astype(float) + 1.0) / (out["m1_volume"].astype(float) + 1.0)
    out["log_m2_m1_volume_ratio"] = np.log(ratio)
    month_angle = 2.0 * math.pi * out["trade_date"].dt.month.astype(float) / 12.0
    out["calendar_month_sin"] = np.sin(month_angle)
    out["calendar_month_cos"] = np.cos(month_angle)
    return out


def _power_detectable_effect(raw_n: int, rho: float) -> tuple[float, float]:
    effective = raw_n * (1.0 - rho) / (1.0 + rho)
    z_alpha = NormalDist().inv_cdf(1.0 - ALPHA / 2.0)
    z_power = NormalDist().inv_cdf(TARGET_POWER)
    detectable = (z_alpha + z_power) / math.sqrt(effective)
    return effective, detectable


def audit_development_feasibility(panel: pd.DataFrame) -> dict[str, Any]:
    """Inspect development-only nuisance properties; never accepts protected rows."""
    if panel.empty:
        raise DataContractViolation("front-curve feasibility panel is empty")
    if pd.Timestamp(panel["trade_date"].max()) > DEVELOPMENT_END:
        raise DataContractViolation("protected confirmation rows reached development feasibility audit")
    scored = panel.loc[panel["target_spread_change"].notna()].copy()
    if scored.empty:
        raise DataContractViolation("front-curve feasibility has no scoreable development targets")
    target = scored["target_spread_change"].astype(float)
    if not np.isfinite(target.to_numpy()).all():
        raise DataContractViolation("front-curve development target contains non-finite values")

    observed_rho = float(target.autocorr(lag=1)) if len(target) > 2 else 0.0
    if not math.isfinite(observed_rho):
        observed_rho = 0.0
    power_rho = min(DEPENDENCE_RHO_CAP, max(DEPENDENCE_RHO_FLOOR, abs(observed_rho)))
    effective, detectable = _power_detectable_effect(MIN_CONFIRMATION_ROWS, power_rho)

    month_share = scored["trade_date"].dt.month.value_counts(normalize=True).sort_index()
    year_share = scored["trade_date"].dt.year.value_counts(normalize=True).sort_index()
    transition_share = float(panel["excluded_pair_transition"].sum() / max(len(panel) - 1, 1))
    source_sessions = int(panel.attrs.get("source_session_count", len(panel)))
    selected_front_sessions = int(panel.attrs.get("selected_front_session_count", len(panel)))
    missing_pair_sessions = max(selected_front_sessions - len(panel), 0)
    missing_pair_share = float(missing_pair_sessions / max(selected_front_sessions, 1))
    development_rmse_zero = float(np.sqrt(np.mean(np.square(target.to_numpy()))))
    development_mae_zero = float(np.mean(np.abs(target.to_numpy())))

    checks = {
        "minimum_development_rows": len(scored) >= MIN_DEVELOPMENT_ROWS,
        "pair_transition_share": transition_share <= MAX_PAIR_TRANSITION_SHARE,
        "missing_second_leg_share": missing_pair_share <= 0.01,
        "month_concentration": float(month_share.max()) <= MAX_MONTH_SHARE,
        "year_concentration": float(year_share.max()) <= MAX_YEAR_SHARE,
        "power_vs_scientific_mepi": detectable <= SCIENTIFIC_MEPI,
        "development_precedes_protected_window": pd.Timestamp(scored["target_trade_date"].max()) < CONFIRMATION_START,
    }
    return {
        "target_id": TARGET_ID,
        "development_window": {
            "start": pd.Timestamp(panel["trade_date"].min()).date().isoformat(),
            "end": pd.Timestamp(panel["trade_date"].max()).date().isoformat(),
            "protected_confirmation_start": CONFIRMATION_START.date().isoformat(),
            "protected_confirmation_end": CONFIRMATION_END.date().isoformat(),
        },
        "rows": {
            "source_sessions": source_sessions,
            "selected_front_sessions": selected_front_sessions,
            "pair_rows": len(panel),
            "missing_second_leg_sessions": int(missing_pair_sessions),
            "missing_second_leg_share": missing_pair_share,
            "scoreable_targets": len(scored),
            "pair_transition_exclusions": int(panel["excluded_pair_transition"].sum()),
            "pair_transition_share": transition_share,
        },
        "dependence": {
            "development_lag1_rho": observed_rho,
            "preregistered_rho": power_rho,
            "rule": "max(0.25, abs(development lag-1 target rho)), capped at 0.75",
        },
        "power": {
            "method": "normal_effect_size",
            "alpha": ALPHA,
            "target_power": TARGET_POWER,
            "minimum_confirmation_rows": MIN_CONFIRMATION_ROWS,
            "effective_information": effective,
            "detectable_effect": detectable,
            "scientific_mepi": SCIENTIFIC_MEPI,
        },
        "economic_scale": {
            "predeclared_absolute_rmse_improvement_mepi_usd_per_mmbtu": ECONOMIC_MEPI_USD_PER_MMBTU,
            "development_zero_change_rmse": development_rmse_zero,
            "development_zero_change_mae": development_mae_zero,
            "note": "Development loss scale is diagnostic only and did not set the predeclared absolute MEPI.",
        },
        "concentration": {
            "month_share": {str(int(key)): float(value) for key, value in month_share.items()},
            "year_share": {str(int(key)): float(value) for key, value in year_share.items()},
        },
        "checks": checks,
        "feasibility": "go" if all(checks.values()) else "hold",
        "hold_reasons": [name for name, passed in checks.items() if not passed],
    }


def fixed_confirmatory_design(feasibility: dict[str, Any]) -> dict[str, Any]:
    if feasibility.get("feasibility") != "go":
        raise DataContractViolation("confirmatory design cannot be emitted when feasibility is not go")
    rho = float(feasibility["dependence"]["preregistered_rho"])
    return {
        "target_contract": target_contract(),
        "split": {
            "development": "2015-01-01/2021-12-31",
            "protected_confirmation": "2022-01-01/2026-08-12",
            "minimum_scored_confirmation_rows": MIN_CONFIRMATION_ROWS,
            "fail_closed_if_minimum_not_met": True,
        },
        "features": {
            "definition_id": "front-curve-market-only-v1",
            "preprocessing_id": "front-curve-pit-standardize-train-only-v1",
            "columns": [
                "spread",
                "lag1_spread_change",
                "lag5_mean_spread_change",
                "m1_calendar_dte",
                "log_m2_m1_volume_ratio",
                "calendar_month_sin",
                "calendar_month_cos",
            ],
            "missing_rule": f"drop rows missing any frozen feature before fitting; confirmation must still retain >={MIN_CONFIRMATION_ROWS} scored rows",
        },
        "models": [
            {"id": "zero-change", "family": "naive", "prediction": 0.0},
            {"id": "ridge-fixed", "family": "ridge", "alpha": 1.0, "fit_intercept": True, "scaling": "StandardScaler fit on development only"},
            {"id": "histgb-fixed", "family": "hist_gradient_boosting", "learning_rate": 0.05, "max_iter": 200, "max_depth": 3, "min_samples_leaf": 20, "l2_regularization": 1.0, "random_state": 271},
        ],
        "training": "fit once on development rows only; no tuning, search, protected-window refit, or model selection",
        "evaluation": {
            "primary_metric": "rmse",
            "secondary_metrics": ["mae", "direction_accuracy", "prediction_target_correlation"],
            "primary_benchmark": "zero-change",
            "inference": "paired moving-block bootstrap, block_size=20, 2000 resamples, seed=271",
            "multiplicity": "Benjamini-Hochberg across ridge-fixed and histgb-fixed primary comparisons",
            "scientific_mepi_standardized_paired_loss_effect": SCIENTIFIC_MEPI,
            "economic_mepi_absolute_rmse_improvement_usd_per_mmbtu": ECONOMIC_MEPI_USD_PER_MMBTU,
            "promotion": "at least one fixed model must have positive 95% lower CI RMSE improvement, BH-adjusted p<=0.05, absolute RMSE improvement>=0.005 USD/MMBtu, standardized paired-loss effect>=0.15, and non-negative RMSE improvement in at least 4 of the 5 calendar-year slices 2022-2026",
            "kill": "otherwise stop this target/model slice; no post-result target, feature, roll, horizon, or hyperparameter rescue inside this experiment",
        },
        "dependence": {
            "method": "ar1",
            "raw_n": MIN_CONFIRMATION_ROWS,
            "parameters": {"rho": rho},
        },
    }
