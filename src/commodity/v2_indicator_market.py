from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from commodity.v2_indicator_contract import (
    IndicatorContractError,
    PinnedSourcePolicy,
    _eligible_before,
    _finite,
    _require_accepted_source,
    _require_columns,
    _require_fresh_current_state,
)


def build_curve_increments(
    rows: pd.DataFrame,
    *,
    current_trade_date: Any,
    prediction_time: Any,
    session_sequence: Sequence[Any],
) -> dict[str, float]:
    required = (
        "trade_date",
        "available_at",
        "curve_spread_m1_m2",
        "curve_spread_m2_m3",
        "curve_slope_m1_m4",
    )
    _require_columns(rows, required, label="curve input")
    eligible, _ = _eligible_before(rows, prediction_time, label="curve input")
    current_date = pd.Timestamp(current_trade_date).date()
    sessions = [pd.Timestamp(value).date() for value in session_sequence]
    if len(sessions) != len(set(sessions)):
        raise IndicatorContractError("market session sequence must be unique")
    try:
        position = sessions.index(current_date)
    except ValueError as exc:
        raise IndicatorContractError(
            "current trade_date is not in the frozen session sequence"
        ) from exc
    if position == 0:
        raise IndicatorContractError("curve increment requires a prior market session")
    prior_date = sessions[position - 1]

    eligible = eligible.copy()
    eligible["trade_date"] = pd.to_datetime(
        eligible["trade_date"], errors="coerce"
    ).dt.date
    if eligible["trade_date"].isna().any():
        raise IndicatorContractError("curve trade_date must be known")

    selected: dict[str, pd.Series] = {}
    for label, trade_date in (("current", current_date), ("prior", prior_date)):
        match = eligible.loc[eligible["trade_date"] == trade_date]
        if len(match) != 1:
            raise IndicatorContractError(
                f"curve {label} session must have exactly one eligible row"
            )
        selected[label] = match.iloc[0]

    current = selected["current"]
    prior = selected["prior"]
    spread12 = _finite(
        current["curve_spread_m1_m2"], label="current M1-M2 spread"
    )
    spread23 = _finite(
        current["curve_spread_m2_m3"], label="current M2-M3 spread"
    )
    prior_spread12 = _finite(
        prior["curve_spread_m1_m2"], label="prior M1-M2 spread"
    )
    slope14 = _finite(
        current["curve_slope_m1_m4"], label="current M1-M4 slope"
    )
    prior_slope14 = _finite(
        prior["curve_slope_m1_m4"], label="prior M1-M4 slope"
    )
    return {
        "curve_curvature_123": spread12 - spread23,
        "curve_spread_m1_m2_change_1": spread12 - prior_spread12,
        "curve_slope_m1_m4_change_1": slope14 - prior_slope14,
    }


def build_volatility_increment(inherited_row: Mapping[str, Any]) -> dict[str, float]:
    vol_5 = _finite(inherited_row.get("vol_5"), label="vol_5")
    vol_20 = _finite(inherited_row.get("vol_20"), label="vol_20")
    if vol_20 == 0.0:
        raise IndicatorContractError("vol_20 denominator is zero")
    ratio = vol_5 / vol_20
    if not np.isfinite(ratio):
        raise IndicatorContractError("vol_ratio_5_20 is non-finite")
    return {"vol_ratio_5_20": float(ratio)}


def build_positioning_increments(
    reports: pd.DataFrame,
    prediction_time: Any,
    source_policy: PinnedSourcePolicy,
) -> dict[str, float]:
    required = (
        "observed_for",
        "available_at",
        "managed_money_long_pct_oi",
        "managed_money_short_pct_oi",
        "revision_status",
        "source_id",
    )
    _require_columns(reports, required, label="positioning input")
    eligible, cutoff = _eligible_before(
        reports, prediction_time, label="positioning input"
    )
    _require_accepted_source(
        eligible, source_policy, "cftc_cot", label="positioning input"
    )
    if eligible.empty:
        raise IndicatorContractError(
            "no positioning report is eligible at the cutoff"
        )
    eligible["observed_for"] = pd.to_datetime(
        eligible["observed_for"], utc=True, errors="coerce"
    )
    if eligible["observed_for"].isna().any():
        raise IndicatorContractError("positioning observed_for must be known")

    states: list[pd.Series] = []
    for _, group in eligible.groupby("observed_for", sort=False):
        latest_at = group["available_at"].max()
        latest = group.loc[group["available_at"] == latest_at]
        if len(latest) != 1:
            raise IndicatorContractError("positioning report identity is ambiguous")
        states.append(latest.iloc[0])
    state = pd.DataFrame(states)
    if state["available_at"].duplicated(keep=False).any():
        raise IndicatorContractError(
            "duplicate/tied positioning available_at identities"
        )
    state = state.sort_values("available_at")
    if len(state) < 2:
        raise IndicatorContractError(
            "positioning change requires a public predecessor"
        )
    current, prior = state.iloc[-1], state.iloc[-2]
    _require_fresh_current_state(
        current["available_at"],
        cutoff,
        source_policy,
        "cftc_cot",
        label="positioning current report",
    )
    statuses = {str(current["revision_status"]), str(prior["revision_status"])}
    if statuses != {"point_in_time"}:
        raise IndicatorContractError(
            "positioning predecessor is not point-in-time eligible"
        )
    if current["observed_for"] == prior["observed_for"]:
        raise IndicatorContractError(
            "positioning predecessor must be a distinct report"
        )
    current_net = _finite(
        current["managed_money_long_pct_oi"], label="current managed money long"
    ) - _finite(
        current["managed_money_short_pct_oi"], label="current managed money short"
    )
    prior_net = _finite(
        prior["managed_money_long_pct_oi"], label="prior managed money long"
    ) - _finite(
        prior["managed_money_short_pct_oi"], label="prior managed money short"
    )
    return {
        "managed_money_net_pct_oi": current_net,
        "managed_money_net_pct_oi_change_1report": current_net - prior_net,
    }


def build_power_increments(
    forecasts: pd.DataFrame,
    prediction_time: Any,
    source_policy: PinnedSourcePolicy,
) -> dict[str, float]:
    required = (
        "issued_at",
        "available_at",
        "forecast_valid_at",
        "power_next_day_load_mean_mw",
        "power_next_day_load_max_mw",
        "power_next_day_load_min_mw",
        "revision_status",
        "source_id",
    )
    _require_columns(forecasts, required, label="power input")
    eligible, cutoff = _eligible_before(
        forecasts, prediction_time, label="power input"
    )
    _require_accepted_source(
        eligible, source_policy, "nyiso_load_forecast", label="power input"
    )
    if eligible.empty:
        raise IndicatorContractError("no power forecast is eligible at the cutoff")
    eligible["issued_at"] = pd.to_datetime(
        eligible["issued_at"], utc=True, errors="coerce"
    )
    eligible["forecast_valid_at"] = pd.to_datetime(
        eligible["forecast_valid_at"], utc=True, errors="coerce"
    )
    if eligible[["issued_at", "forecast_valid_at"]].isna().any().any():
        raise IndicatorContractError("power timestamps must be known")
    eligible = eligible.loc[eligible["issued_at"] <= cutoff].copy()
    if eligible["issued_at"].duplicated(keep=False).any():
        raise IndicatorContractError(
            "duplicate/tied eligible power issued_at identities"
        )
    eligible = eligible.sort_values("issued_at")
    if len(eligible) < 2:
        raise IndicatorContractError("power change requires a prior issued forecast")
    current, prior = eligible.iloc[-1], eligible.iloc[-2]
    _require_fresh_current_state(
        current["available_at"],
        cutoff,
        source_policy,
        "nyiso_load_forecast",
        label="power current forecast",
    )
    statuses = {str(current["revision_status"]), str(prior["revision_status"])}
    if statuses != {"issued_run_immutable"}:
        raise IndicatorContractError(
            "power inputs must be immutable archived P-7 vintages"
        )
    nyiso_tz = ZoneInfo("America/New_York")
    current_date = current["forecast_valid_at"].tz_convert(nyiso_tz).date()
    prior_date = prior["forecast_valid_at"].tz_convert(nyiso_tz).date()
    if current_date != prior_date + pd.Timedelta(days=1):
        raise IndicatorContractError(
            "power issued-level change requires consecutive NYISO calendar days"
        )
    current_mean = _finite(
        current["power_next_day_load_mean_mw"], label="current power mean"
    )
    prior_mean = _finite(
        prior["power_next_day_load_mean_mw"], label="prior power mean"
    )
    current_max = _finite(
        current["power_next_day_load_max_mw"], label="current power max"
    )
    current_min = _finite(
        current["power_next_day_load_min_mw"], label="current power min"
    )
    return {
        "power_next_day_load_range_mw": current_max - current_min,
        "power_next_day_load_mean_change_1run_mw": current_mean - prior_mean,
    }
