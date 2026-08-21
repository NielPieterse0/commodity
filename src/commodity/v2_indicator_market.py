from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from commodity.roll_safe_market import (
    RollSafeMarketError,
    same_contract_selected_returns,
)
from commodity.v2_indicator_contract import (
    IndicatorContractError,
    PinnedSourcePolicy,
    _date_identity_series,
    _eligible_before,
    _finite,
    _require_accepted_source,
    _require_columns,
    _require_fresh_current_state,
    _source_settings,
    _validated_activation_binding,
)

FROZEN_MARKET_CONTEXT = {
    "dataset_id": "us-ng-pit-0c0a39b36692",
    "data_vintage_id": "b6aaf445500f2841",
    "dataset_sha256": "0c0a39b3669215b4bdc45a0fdedf90697f0c2c92690cb33700bd0bc47c80a45f",
    "availability_rule_id": "evaluation-pit-after-daily-bar-close-v1",
    "availability_rule_sha256": "1ec62a3bb3c222d158fdd69ab031b3c0a519ba2ac9881a054fae34a26d2aeccc",
    "prediction_timestamp_semantics": "after_current_daily_bar_close",
}
FROZEN_PREFIT_CURVE_CONTEXT = {
    "snapshot_id": "20240813-20260812-v1-m1-m12",
    "canonical_sha256": "83faf07a8de1fe3fea4cd6548dd25d9c02828e1ef4faa13a234ac8f2ad03d655",
}


def _load_frozen_curve_dataset(
    dataset_path: Path,
    source_policy: PinnedSourcePolicy,
    activation_binding: Mapping[str, Any],
) -> pd.DataFrame:
    policy = _source_settings(source_policy, "market_canonical")
    availability = policy.get("availability_policy")
    if (
        policy.get("provider") != "massive_futures"
        or policy.get("product_code") != "NG"
        or policy.get("exchange") != "NYMEX"
        or policy.get("calendar") != "CME_NYMEX"
        or not isinstance(availability, Mapping)
        or availability.get("method") != "trade_date_2359_utc"
        or availability.get("status") != "reconstructed_conservative"
    ):
        raise IndicatorContractError("pinned market source policy changed")

    bound = _validated_activation_binding(activation_binding)
    control = bound.get("frozen_v1_control")
    context = control.get("context_identity") if isinstance(control, Mapping) else None
    if not isinstance(context, Mapping) or any(
        context.get(key) != value for key, value in FROZEN_MARKET_CONTEXT.items()
    ):
        raise IndicatorContractError("#83 activation binding market identity changed")
    raw = dataset_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_MARKET_CONTEXT["dataset_sha256"]:
        raise IndicatorContractError("curve dataset artifact differs from frozen #81 dataset")
    return pd.read_csv(io.BytesIO(raw))


def _load_prefit_curve_predecessor(
    canonical_path: Path,
    current_date: Any,
    source_policy: PinnedSourcePolicy,
) -> tuple[pd.Timestamp, dict[str, float]]:
    policy = _source_settings(source_policy, "market_canonical")
    if policy.get("provider") != "massive_futures":
        raise IndicatorContractError("pinned market source policy changed")
    raw = canonical_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_PREFIT_CURVE_CONTEXT["canonical_sha256"]:
        raise IndicatorContractError("pre-fit curve context differs from the pinned market artifact")
    rows = pd.read_csv(io.BytesIO(raw))
    _require_columns(rows, ("trade_date", "contract_id", "expiration", "settle"), label="pre-fit curve context")
    rows = rows.copy()
    rows["trade_date"] = pd.to_datetime(rows["trade_date"], utc=True, errors="coerce")
    rows["expiration"] = pd.to_datetime(rows["expiration"], utc=True, errors="coerce")
    if rows[["trade_date", "expiration"]].isna().any().any():
        raise IndicatorContractError("pre-fit curve context timestamps must be known")
    if rows.duplicated(["trade_date", "contract_id"]).any():
        raise IndicatorContractError("pre-fit curve context must be unique by trade_date and contract_id")
    current = pd.Timestamp(current_date, tz="UTC") if pd.Timestamp(current_date).tzinfo is None else pd.Timestamp(current_date).tz_convert("UTC")
    prior_dates = rows.loc[rows["trade_date"] < current, "trade_date"]
    if prior_dates.empty:
        raise IndicatorContractError("pre-fit curve context has no prior market session")
    prior_date = prior_dates.max()
    active = rows.loc[
        (rows["trade_date"] == prior_date) & (rows["expiration"] >= prior_date)
    ].sort_values(["expiration", "contract_id"])
    if len(active) < 4:
        raise IndicatorContractError("pre-fit curve context requires four active contracts")
    active = active.iloc[:4]
    settles = pd.to_numeric(active["settle"], errors="coerce")
    if settles.isna().any() or not np.isfinite(settles.to_numpy(dtype="float64")).all():
        raise IndicatorContractError("pre-fit curve settles must be finite")
    dte = (active["expiration"] - prior_date).dt.total_seconds() / 86400.0
    span = float(dte.iloc[3] - dte.iloc[0])
    if span <= 0.0:
        raise IndicatorContractError("pre-fit curve M1-M4 expiry span must be positive")
    values = settles.to_numpy(dtype="float64")
    return prior_date, {
        "curve_spread_m1_m2": float(values[0] - values[1]),
        "curve_spread_m2_m3": float(values[1] - values[2]),
        "curve_slope_m1_m4": float((values[3] - values[0]) / span),
    }


def build_curve_increments(
    dataset_path: Path | pd.DataFrame,
    *,
    current_trade_date: Any,
    prediction_time: Any,
    session_sequence: Sequence[Any],
    source_policy: PinnedSourcePolicy | None = None,
    activation_binding: Mapping[str, Any] | None = None,
    pre_fit_market_path: Path | None = None,
) -> dict[str, float]:
    """Build curve increments only from the exact frozen #81 dataset artifact.

    The legacy DataFrame call shape is retained solely to fail closed with a stable
    governance error instead of silently accepting caller-supplied market rows.
    """
    if isinstance(dataset_path, pd.DataFrame):
        raise IndicatorContractError(
            "legacy DataFrame curve input is not release-authoritative; pass the exact "
            "frozen dataset Path with source_policy and activation_binding"
        )
    if source_policy is None or activation_binding is None:
        raise IndicatorContractError(
            "curve artifact loading requires source_policy and activation_binding"
        )
    rows = _load_frozen_curve_dataset(
        Path(dataset_path), source_policy, activation_binding
    )
    required = (
        "prediction_time",
        "curve_spread_m1_m2",
        "curve_spread_m2_m3",
        "curve_slope_m1_m4",
    )
    _require_columns(rows, required, label="curve dataset")
    rows = rows.copy()
    rows["available_at"] = rows["prediction_time"]
    rows["trade_date"] = _date_identity_series(
        rows, "prediction_time", label="curve dataset"
    ).dt.date
    eligible, _ = _eligible_before(rows, prediction_time, label="curve dataset")
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
    prefit_prior: dict[str, float] | None = None
    if position == 0:
        frozen_dates = pd.to_datetime(rows["trade_date"], errors="coerce").dt.date
        if frozen_dates.isna().any() or current_date != frozen_dates.min():
            raise IndicatorContractError(
                "pre-fit curve context is permitted only for the first frozen dataset row"
            )
        if pre_fit_market_path is None:
            raise IndicatorContractError("curve increment requires a prior market session")
        prior_timestamp, prefit_prior = _load_prefit_curve_predecessor(
            Path(pre_fit_market_path), current_date, source_policy
        )
        prior_date = prior_timestamp.date()
    else:
        prior_date = sessions[position - 1]

    eligible = eligible.copy()
    eligible["trade_date"] = pd.to_datetime(
        eligible["trade_date"], errors="coerce"
    ).dt.date
    if eligible["trade_date"].isna().any():
        raise IndicatorContractError("curve trade_date must be known")

    selected: dict[str, Mapping[str, Any]] = {}
    current_match = eligible.loc[eligible["trade_date"] == current_date]
    if len(current_match) != 1:
        raise IndicatorContractError(
            "curve current session must have exactly one eligible row"
        )
    selected["current"] = current_match.iloc[0]
    if prefit_prior is not None:
        selected["prior"] = prefit_prior
    else:
        prior_match = eligible.loc[eligible["trade_date"] == prior_date]
        if len(prior_match) != 1:
            raise IndicatorContractError(
                "curve prior session must have exactly one eligible row"
            )
        selected["prior"] = prior_match.iloc[0]

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


def build_roll_safe_volatility_features(
    canonical_rows: pd.DataFrame,
    selected_path: pd.DataFrame,
    *,
    current_trade_date: Any,
) -> dict[str, float]:
    """Derive #83 volatility controls from selected contracts' own prior-session returns."""
    try:
        returns = same_contract_selected_returns(
            canonical_rows,
            selected_path,
            price_col="settle",
        )
    except RollSafeMarketError as exc:
        raise IndicatorContractError("roll-safe volatility input is invalid") from exc

    current = pd.to_datetime(current_trade_date, utc=True, errors="coerce")
    if pd.isna(current):
        raise IndicatorContractError("current_trade_date must be known")
    eligible = returns.loc[returns.index <= current]
    current_matches = eligible.index == current
    if current_matches.sum() != 1:
        raise IndicatorContractError(
            "current trade date must identify exactly one selected-contract return"
        )
    if len(eligible) < 20:
        raise IndicatorContractError("volatility increment requires 20 selected sessions")
    window = eligible.iloc[-20:]
    if window.isna().any() or not np.isfinite(window.to_numpy(dtype="float64")).all():
        raise IndicatorContractError(
            "volatility increment requires 20 finite same-contract returns"
        )
    vol_5 = float(window.iloc[-5:].std(ddof=1))
    vol_20 = float(window.std(ddof=1))
    if not np.isfinite(vol_5) or not np.isfinite(vol_20):
        raise IndicatorContractError("volatility increment is non-finite")
    if vol_20 == 0.0:
        raise IndicatorContractError("vol_20 denominator is zero")
    ratio = vol_5 / vol_20
    if not np.isfinite(ratio):
        raise IndicatorContractError("vol_ratio_5_20 is non-finite")
    return {
        "vol_5": vol_5,
        "vol_20": vol_20,
        "vol_ratio_5_20": float(ratio),
    }


def build_volatility_increment(
    canonical_rows: pd.DataFrame | Mapping[str, Any],
    selected_path: pd.DataFrame | None = None,
    *,
    current_trade_date: Any = None,
) -> dict[str, float]:
    if selected_path is None:
        raise IndicatorContractError(
            "legacy inherited vol_5/vol_20 input is superseded; canonical rows and "
            "selected path are required for roll-safe volatility"
        )
    features = build_roll_safe_volatility_features(
        canonical_rows,
        selected_path,
        current_trade_date=current_trade_date,
    )
    return {"vol_ratio_5_20": features["vol_ratio_5_20"]}


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
    eligible["observed_for"] = _date_identity_series(
        eligible, "observed_for", label="positioning input"
    )

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
