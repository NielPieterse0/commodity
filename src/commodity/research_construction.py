from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd


class ResearchConstructionError(ValueError):
    """Raised when an outcome-blind research construction is semantically invalid."""


def _require_columns(frame: pd.DataFrame, required: Sequence[str], label: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ResearchConstructionError(f"{label} is missing columns: {missing}")


def _utc_series(values: pd.Series, label: str) -> pd.Series:
    parsed = pd.to_datetime(values, utc=True, errors="coerce")
    if parsed.isna().any():
        raise ResearchConstructionError(f"{label} contains invalid timestamps")
    return parsed


def rank_contracts_by_expiration(frame: pd.DataFrame) -> pd.DataFrame:
    """Rank active listed contracts by exact expiration without reading price fields."""
    required = ("trade_date", "contract_id", "expiration")
    _require_columns(frame, required, "contract identity")
    out = frame.loc[:, list(required)].copy()
    out["trade_date"] = _utc_series(out["trade_date"], "trade_date")
    out["expiration"] = _utc_series(out["expiration"], "expiration")
    if (out["contract_id"].astype(str).str.strip() == "").any():
        raise ResearchConstructionError("contract identity contains empty contract_id")
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise ResearchConstructionError("contract identity contains duplicate trade_date/contract_id")
    if (out["trade_date"] > out["expiration"]).any():
        raise ResearchConstructionError("contract identity contains row after expiration")
    out = out.sort_values(["trade_date", "expiration", "contract_id"], kind="stable")
    out["maturity_rank"] = out.groupby("trade_date", sort=False).cumcount() + 1
    return out.reset_index(drop=True)


def build_samuelson_eligibility(
    frame: pd.DataFrame,
    *,
    volume_column: str = "volume",
) -> pd.DataFrame:
    """Fix DTE buckets and the primary positive-volume screen without reading prices."""
    required = ("trade_date", "contract_id", "expiration", volume_column)
    _require_columns(frame, required, "Samuelson eligibility")
    out = frame.loc[:, list(required)].copy()
    out["trade_date"] = _utc_series(out["trade_date"], "Samuelson trade_date")
    out["expiration"] = _utc_series(out["expiration"], "Samuelson expiration")
    if (out["contract_id"].astype(str).str.strip() == "").any():
        raise ResearchConstructionError("Samuelson eligibility contains empty contract_id")
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise ResearchConstructionError("Samuelson eligibility contains duplicate trade_date/contract_id")
    out[volume_column] = pd.to_numeric(out[volume_column], errors="coerce")
    volume = out[volume_column].to_numpy(dtype=float)
    if not np.isfinite(volume).all() or (volume < 0.0).any():
        raise ResearchConstructionError("Samuelson liquidity volume must be finite and non-negative")
    out["days_to_maturity"] = (
        (out["expiration"] - out["trade_date"]).dt.total_seconds() / 86400.0
    )
    if (out["days_to_maturity"] <= 0.0).any():
        raise ResearchConstructionError("Samuelson eligibility requires positive days to maturity")
    out["dte_bucket"] = pd.cut(
        out["days_to_maturity"],
        bins=[0.0, 30.0, 60.0, 90.0, 180.0, 365.0, float("inf")],
        labels=["0-30", "31-60", "61-90", "91-180", "181-365", "366+"],
        right=True,
        include_lowest=False,
    )
    if out["dte_bucket"].isna().any():
        raise ResearchConstructionError("Samuelson eligibility could not assign a DTE bucket")
    out["eligible_primary"] = out[volume_column] > 0.0
    return out.sort_values(["trade_date", "expiration", "contract_id"], kind="stable").reset_index(drop=True)


def build_storage_seasonal_state(
    frame: pd.DataFrame,
    *,
    value_column: str = "storage_lower48_bcf",
) -> pd.DataFrame:
    """Construct a week-of-year storage state using storage information only."""
    _require_columns(frame, ("observed_for", value_column), "storage state")
    out = frame.loc[:, ["observed_for", value_column]].copy()
    out["observed_for"] = _utc_series(out["observed_for"], "storage observed_for")
    if out["observed_for"].duplicated().any():
        raise ResearchConstructionError("storage state contains duplicate observed_for")
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce")
    if out[value_column].isna().any() or not np.isfinite(out[value_column]).all():
        raise ResearchConstructionError("storage state contains non-finite values")
    iso_week = out["observed_for"].dt.isocalendar().week.astype(int)
    out["seasonal_norm_bcf"] = out.groupby(iso_week)[value_column].transform("mean")
    out["storage_anomaly_bcf"] = out[value_column] - out["seasonal_norm_bcf"]
    out["below_seasonal_norm"] = out["storage_anomaly_bcf"] < 0.0
    return out


def build_release_calendar(
    events: pd.DataFrame,
    *,
    timezone: str = "America/New_York",
) -> pd.DataFrame:
    """Extract release-day identities without reading market responses."""
    _require_columns(events, ("available_at", "source_event_type"), "release events")
    release_mask = events["source_event_type"].astype(str).str.contains("release", regex=False)
    out = events.loc[release_mask, ["available_at", "source_event_type"]].copy()
    out["available_at"] = _utc_series(out["available_at"], "release available_at")
    if out.empty:
        raise ResearchConstructionError("release events contain no release rows")
    if out["available_at"].duplicated().any():
        raise ResearchConstructionError("release events contain duplicate release timestamps")
    local = out["available_at"].dt.tz_convert(timezone)
    out["release_date"] = local.dt.date
    out["release_weekday"] = local.dt.day_name()
    out["holiday_shifted"] = out["release_weekday"] != "Thursday"
    return out.sort_values("available_at", kind="stable").reset_index(drop=True)


def managed_money_weekly_changes(frame: pd.DataFrame) -> pd.DataFrame:
    """Construct publication-lag-preserving Managed Money net weekly changes."""
    required = ("observed_for", "available_at", "managed_money_net")
    _require_columns(frame, required, "CFTC positioning")
    out = frame.loc[:, list(required)].copy()
    out["observed_for"] = _utc_series(out["observed_for"], "CFTC observed_for")
    out["available_at"] = _utc_series(out["available_at"], "CFTC available_at")
    if out["observed_for"].duplicated().any():
        raise ResearchConstructionError("CFTC positioning contains duplicate report dates")
    if (out["available_at"] < out["observed_for"]).any():
        raise ResearchConstructionError("CFTC positioning availability precedes report date")
    out["managed_money_net"] = pd.to_numeric(out["managed_money_net"], errors="coerce")
    if out["managed_money_net"].isna().any():
        raise ResearchConstructionError("CFTC positioning contains non-numeric managed_money_net")
    out = out.sort_values("observed_for", kind="stable").reset_index(drop=True)
    out["managed_money_net_change"] = out["managed_money_net"].diff()
    return out


def _validate_weather_weights(
    location_ids: set[str],
    weights: Mapping[str, float],
) -> dict[str, float]:
    normalized = {str(key): float(value) for key, value in weights.items()}
    missing = sorted(location_ids - set(normalized))
    if missing:
        raise ResearchConstructionError(f"weather weights are missing locations: {missing}")
    used = {key: normalized[key] for key in sorted(location_ids)}
    if any(not math.isfinite(value) or value <= 0.0 for value in used.values()):
        raise ResearchConstructionError("weather weights must be finite and positive")
    if not math.isclose(sum(used.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ResearchConstructionError("weather weights must sum to one")
    return used


def build_observed_weather_departures(
    observations: pd.DataFrame,
    normals: pd.DataFrame,
    *,
    weights: Mapping[str, float],
    degree_day_base_c: float = 18.3333333333,
) -> pd.DataFrame:
    """Build weighted departures from fixed observed-weather climate normals."""
    obs_required = ("observed_for", "location_id", "tmax_c", "tmin_c")
    normal_required = ("location_id", "month_day", "normal_tmean_c")
    _require_columns(observations, obs_required, "observed weather")
    _require_columns(normals, normal_required, "weather normals")
    if not math.isfinite(float(degree_day_base_c)):
        raise ResearchConstructionError("degree-day base must be finite")

    obs = observations.loc[:, list(obs_required)].copy()
    obs["observed_for"] = _utc_series(obs["observed_for"], "weather observed_for")
    obs["location_id"] = obs["location_id"].astype(str)
    if obs.duplicated(["observed_for", "location_id"]).any():
        raise ResearchConstructionError("observed weather contains duplicate date/location rows")
    for column in ("tmax_c", "tmin_c"):
        obs[column] = pd.to_numeric(obs[column], errors="coerce")
    if obs[["tmax_c", "tmin_c"]].isna().any().any():
        raise ResearchConstructionError("observed weather contains non-numeric temperatures")
    if (obs["tmax_c"] < obs["tmin_c"]).any():
        raise ResearchConstructionError("observed weather has tmax below tmin")

    normal = normals.loc[:, list(normal_required)].copy()
    normal["location_id"] = normal["location_id"].astype(str)
    normal["normal_tmean_c"] = pd.to_numeric(normal["normal_tmean_c"], errors="coerce")
    if normal["normal_tmean_c"].isna().any():
        raise ResearchConstructionError("weather normals contain non-numeric normal_tmean_c")
    if normal.duplicated(["location_id", "month_day"]).any():
        raise ResearchConstructionError("weather normals contain duplicate location/month_day rows")

    location_ids = set(obs["location_id"])
    used_weights = _validate_weather_weights(location_ids, weights)
    obs["month_day"] = obs["observed_for"].dt.strftime("%m-%d")
    merged = obs.merge(normal, on=["location_id", "month_day"], how="left", validate="many_to_one")
    if merged["normal_tmean_c"].isna().any():
        missing = merged.loc[merged["normal_tmean_c"].isna(), ["location_id", "month_day"]]
        raise ResearchConstructionError(
            f"observed weather is missing fixed normal for {missing.to_dict(orient='records')}"
        )

    merged["weight"] = merged["location_id"].map(used_weights)
    merged["tmean_c"] = (merged["tmax_c"] + merged["tmin_c"]) / 2.0
    base = float(degree_day_base_c)
    merged["hdd"] = (base - merged["tmean_c"]).clip(lower=0.0)
    merged["cdd"] = (merged["tmean_c"] - base).clip(lower=0.0)
    merged["normal_hdd"] = (base - merged["normal_tmean_c"]).clip(lower=0.0)
    merged["normal_cdd"] = (merged["normal_tmean_c"] - base).clip(lower=0.0)
    weighted_columns = {
        "weather_tmean_c": "tmean_c",
        "weather_normal_tmean_c": "normal_tmean_c",
        "weather_hdd": "hdd",
        "weather_hdd_normal": "normal_hdd",
        "weather_cdd": "cdd",
        "weather_cdd_normal": "normal_cdd",
    }
    for output, source in weighted_columns.items():
        merged[output] = merged[source] * merged["weight"]
    weight_sum = merged.groupby("observed_for")["weight"].sum()
    if not np.allclose(weight_sum.to_numpy(dtype=float), 1.0, rtol=0.0, atol=1e-9):
        raise ResearchConstructionError("observed weather is missing one or more weighted locations on a date")
    result = merged.groupby("observed_for", as_index=False)[list(weighted_columns)].sum()
    result["weather_tmean_departure_c"] = result["weather_tmean_c"] - result["weather_normal_tmean_c"]
    result["weather_hdd_departure"] = result["weather_hdd"] - result["weather_hdd_normal"]
    result["weather_cdd_departure"] = result["weather_cdd"] - result["weather_cdd_normal"]
    return result.sort_values("observed_for", kind="stable").reset_index(drop=True)


def build_same_valid_time_revisions(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    *,
    value_columns: Sequence[str],
    key_columns: Sequence[str] = ("location_id", "forecast_valid_at"),
) -> pd.DataFrame:
    required = tuple(dict.fromkeys(("issued_at", *key_columns, *value_columns)))
    _require_columns(current, required, "current issued forecast")
    _require_columns(previous, required, "previous issued forecast")
    if not value_columns:
        raise ResearchConstructionError("revision construction requires at least one value column")

    left = current.loc[:, list(required)].copy()
    right = previous.loc[:, list(required)].copy()
    for label, frame in (("current", left), ("previous", right)):
        frame["issued_at"] = _utc_series(frame["issued_at"], f"{label} issued_at")
        for column in key_columns:
            if column.endswith("_at"):
                frame[column] = _utc_series(frame[column], f"{label} {column}")
        if frame.duplicated(list(key_columns)).any():
            raise ResearchConstructionError(f"{label} issued forecast has duplicate valid-time keys")
        for column in value_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[list(value_columns)].isna().any().any():
            raise ResearchConstructionError(f"{label} issued forecast has non-numeric revision values")

    current_issues = left["issued_at"].drop_duplicates()
    previous_issues = right["issued_at"].drop_duplicates()
    if len(current_issues) != 1 or len(previous_issues) != 1:
        raise ResearchConstructionError("revision construction requires exactly one issue time per run")
    current_issue = pd.Timestamp(current_issues.iloc[0])
    previous_issue = pd.Timestamp(previous_issues.iloc[0])
    if current_issue <= previous_issue:
        raise ResearchConstructionError("current issued forecast must follow previous issued forecast")

    merged = left.merge(
        right,
        on=list(key_columns),
        how="inner",
        suffixes=("_current", "_previous"),
        validate="one_to_one",
    )
    if merged.empty:
        raise ResearchConstructionError("issued forecast runs have no matching valid times")
    result = merged.loc[:, list(key_columns)].copy()
    result["current_issued_at"] = current_issue
    result["previous_issued_at"] = previous_issue
    for column in value_columns:
        result[f"revision_{column}"] = merged[f"{column}_current"] - merged[f"{column}_previous"]
    return result.sort_values(list(key_columns), kind="stable").reset_index(drop=True)


def ar1_effective_information(values: pd.Series) -> dict[str, float | int]:
    """Return a conservative scalar AR(1) effective-information screen."""
    numeric = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if len(numeric) < 3:
        raise ResearchConstructionError("AR1 effective information requires at least three finite values")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ResearchConstructionError("AR1 effective information requires finite values")
    rho = float(numeric.autocorr(lag=1))
    if not math.isfinite(rho):
        raise ResearchConstructionError("AR1 effective information could not estimate lag-one dependence")
    raw_n = len(numeric)
    if rho >= 1.0:
        effective_n = 0.0
    elif rho <= -1.0:
        effective_n = float(raw_n)
    else:
        effective_n = raw_n * (1.0 - rho) / (1.0 + rho)
        effective_n = min(float(raw_n), max(0.0, float(effective_n)))
    return {"raw_n": raw_n, "ar1": rho, "effective_n": effective_n}


_BALANCE_FAMILIES = (
    "production",
    "consumption",
    "imports",
    "exports",
    "storage_working_gas",
)


def _monthly_period(values: pd.Series) -> pd.Series:
    text = values.astype(str).str.strip()
    compact = text.str.fullmatch(r"\d{6}")
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    if compact.any():
        parsed.loc[compact] = pd.to_datetime(text.loc[compact], format="%Y%m", errors="coerce")
    if (~compact).any():
        parsed.loc[~compact] = pd.to_datetime(text.loc[~compact], errors="coerce")
    if parsed.isna().any():
        raise ResearchConstructionError("monthly physical-balance input contains invalid period")
    return parsed.dt.to_period("M")


def build_monthly_physical_balance_core(
    frame: pd.DataFrame,
    *,
    series_map: Mapping[str, str],
) -> pd.DataFrame:
    """Construct a source-coherent monthly physical-balance core without imputation."""
    required = ("series_id", "period", "value", "unit")
    _require_columns(frame, required, "monthly physical balance")
    if tuple(sorted(series_map)) != tuple(sorted(_BALANCE_FAMILIES)):
        raise ResearchConstructionError(
            f"monthly physical balance requires families: {list(_BALANCE_FAMILIES)}"
        )
    inverse = {str(series_id): family for family, series_id in series_map.items()}
    if len(inverse) != len(_BALANCE_FAMILIES):
        raise ResearchConstructionError("monthly physical-balance series IDs must be unique")

    out = frame.loc[frame["series_id"].astype(str).isin(inverse), list(required)].copy()
    if not out.empty and not out["unit"].astype(str).eq("Million Cubic Feet").all():
        raise ResearchConstructionError(
            "monthly physical-balance series must use Million Cubic Feet"
        )
    observed_ids = set(out["series_id"].astype(str))
    missing_ids = sorted(set(inverse) - observed_ids)
    if missing_ids:
        raise ResearchConstructionError(
            f"monthly physical-balance input is missing selected series: {missing_ids}"
        )
    out["family"] = out["series_id"].astype(str).map(inverse)
    out["period"] = _monthly_period(out["period"])
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    if out["value"].isna().any() or not np.isfinite(out["value"]).all():
        raise ResearchConstructionError("monthly physical-balance input contains non-finite values")
    if out.duplicated(["family", "period"]).any():
        raise ResearchConstructionError("monthly physical-balance input contains duplicate family/month rows")

    wide = out.pivot(index="period", columns="family", values="value").sort_index()
    wide = wide.dropna(subset=list(_BALANCE_FAMILIES))
    if wide.empty:
        raise ResearchConstructionError("monthly physical-balance series have no exact common months")
    wide["storage_change_mmcft"] = wide["storage_working_gas"].diff()
    wide["net_imports_mmcft"] = wide["imports"] - wide["exports"]
    wide = wide.dropna(subset=["storage_change_mmcft"])
    if wide.empty:
        raise ResearchConstructionError(
            "monthly physical-balance overlap needs at least two consecutive complete months"
        )
    renamed = wide.rename(
        columns={
            "production": "production_mmcft",
            "consumption": "consumption_mmcft",
            "imports": "imports_mmcft",
            "exports": "exports_mmcft",
            "storage_working_gas": "storage_working_gas_mmcft",
        }
    )
    return renamed.reset_index()


def build_curve_snapshot_eligibility(
    frame: pd.DataFrame,
    *,
    required_maturities: int,
) -> pd.DataFrame:
    """Count exact active listed maturities by trade date without reading prices."""
    if required_maturities < 1:
        raise ResearchConstructionError("required_maturities must be positive")
    ranked = rank_contracts_by_expiration(frame)
    counts = (
        ranked.groupby("trade_date", as_index=False)["maturity_rank"]
        .max()
        .rename(columns={"maturity_rank": "available_maturities"})
        .sort_values("trade_date", kind="stable")
        .reset_index(drop=True)
    )
    counts["eligible"] = counts["available_maturities"] >= int(required_maturities)
    return counts


def select_last_eligible_curve_date_per_month(
    frame: pd.DataFrame,
    *,
    required_maturities: int = 6,
) -> pd.DataFrame:
    """Select the last identity-eligible curve date in each month without reading prices."""
    counts = build_curve_snapshot_eligibility(
        frame,
        required_maturities=required_maturities,
    )
    eligible = counts.loc[counts["eligible"]].copy()
    if eligible.empty:
        raise ResearchConstructionError("curve history contains no eligible monthly snapshot")
    eligible["_month"] = eligible["trade_date"].dt.tz_localize(None).dt.to_period("M")
    selected = (
        eligible.sort_values("trade_date", kind="stable")
        .groupby("_month", sort=True, as_index=False)
        .tail(1)
        .drop(columns=["_month"])
        .sort_values("trade_date", kind="stable")
        .reset_index(drop=True)
    )
    return selected


def build_exact_monthly_panel(
    series: Mapping[str, pd.DataFrame],
    *,
    period_column: str = "period",
    value_column: str = "value",
) -> pd.DataFrame:
    """Align named monthly series on their exact common months with no imputation."""
    if len(series) < 2:
        raise ResearchConstructionError("exact monthly panel requires at least two series")
    prepared: list[pd.DataFrame] = []
    for name, frame in series.items():
        label = str(name).strip()
        if not label:
            raise ResearchConstructionError("exact monthly panel contains empty series name")
        _require_columns(frame, (period_column, value_column), f"monthly series {label}")
        part = frame.loc[:, [period_column, value_column]].copy()
        part[period_column] = _monthly_period(part[period_column])
        if part[period_column].duplicated().any():
            raise ResearchConstructionError(f"monthly series {label} contains duplicate months")
        part[value_column] = pd.to_numeric(part[value_column], errors="coerce")
        if part[value_column].isna().any() or not np.isfinite(part[value_column]).all():
            raise ResearchConstructionError(f"monthly series {label} contains non-finite values")
        prepared.append(part.rename(columns={value_column: label}).set_index(period_column))
    panel = pd.concat(prepared, axis=1, join="inner").sort_index()
    if panel.empty:
        raise ResearchConstructionError("monthly series have no exact common months")
    if panel.isna().any().any():
        raise ResearchConstructionError("exact monthly panel unexpectedly contains missing values")
    return panel.reset_index()


def build_weather_state_cells(frame: pd.DataFrame) -> pd.DataFrame:
    """Assign fixed calendar season and departure sign from weather inputs only."""
    required = (
        "observed_for",
        "weather_tmean_departure_c",
        "weather_hdd_departure",
        "weather_cdd_departure",
    )
    _require_columns(frame, required, "weather state")
    out = frame.loc[:, list(required)].copy()
    out["observed_for"] = _utc_series(out["observed_for"], "weather state observed_for")
    if out["observed_for"].duplicated().any():
        raise ResearchConstructionError("weather state contains duplicate observed_for")
    for column in required[1:]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if out[list(required[1:])].isna().any().any():
        raise ResearchConstructionError("weather state contains non-numeric departures")
    month = out["observed_for"].dt.month
    out["season"] = np.select(
        [month.isin([12, 1, 2]), month.isin([6, 7, 8])],
        ["winter", "summer"],
        default="shoulder",
    )
    departure = out["weather_tmean_departure_c"].astype(float)
    out["departure_sign"] = np.select(
        [departure < 0.0, departure > 0.0],
        ["negative", "positive"],
        default="zero",
    )
    return out.sort_values("observed_for", kind="stable").reset_index(drop=True)


def build_release_day_labels(
    market_dates: pd.DataFrame,
    release_calendar: pd.DataFrame,
) -> pd.DataFrame:
    """Label market dates using release identities only, never market values."""
    _require_columns(market_dates, ("trade_date",), "market calendar")
    _require_columns(
        release_calendar,
        ("release_date", "release_weekday", "holiday_shifted"),
        "release calendar",
    )
    out = market_dates.loc[:, ["trade_date"]].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
    if out["trade_date"].isna().any():
        raise ResearchConstructionError("market calendar contains invalid trade_date")
    if out["trade_date"].duplicated().any():
        raise ResearchConstructionError("market calendar contains duplicate trade_date")
    releases = release_calendar.loc[:, ["release_date", "release_weekday", "holiday_shifted"]].copy()
    releases["release_date"] = pd.to_datetime(releases["release_date"], errors="coerce").dt.date
    if releases["release_date"].isna().any():
        raise ResearchConstructionError("release calendar contains invalid release_date")
    if releases["release_date"].duplicated().any():
        raise ResearchConstructionError("release calendar contains duplicate release_date")
    merged = out.merge(releases, left_on="trade_date", right_on="release_date", how="left", validate="one_to_one")
    merged["is_release_day"] = merged["release_date"].notna()
    merged["holiday_shifted_release"] = merged["holiday_shifted"].eq(True)
    return merged.drop(columns=["release_date", "release_weekday", "holiday_shifted"])


def standardized_detectable_effect(
    effective_n: float,
    *,
    alpha: float = 0.05,
    power: float = 0.80,
    two_sided: bool = True,
) -> float:
    """Approximate standardized detectable effect for an effective independent N."""
    n = float(effective_n)
    if not math.isfinite(n) or n <= 0.0:
        raise ResearchConstructionError("effective_n must be finite and positive")
    if not 0.0 < alpha < 1.0:
        raise ResearchConstructionError("alpha must lie strictly between zero and one")
    if not 0.0 < power < 1.0:
        raise ResearchConstructionError("power must lie strictly between zero and one")
    normal = NormalDist()
    alpha_tail = alpha / 2.0 if two_sided else alpha
    critical = normal.inv_cdf(1.0 - alpha_tail)
    power_quantile = normal.inv_cdf(power)
    return float((critical + power_quantile) / math.sqrt(n))


def standardized_power(
    effect_size: float,
    effective_n: float,
    *,
    alpha: float = 0.05,
    two_sided: bool = True,
) -> float:
    """Approximate normal-test power for a standardized effect and effective N."""
    effect = float(effect_size)
    n = float(effective_n)
    if not math.isfinite(effect) or effect < 0.0:
        raise ResearchConstructionError("effect_size must be finite and non-negative")
    if not math.isfinite(n) or n <= 0.0:
        raise ResearchConstructionError("effective_n must be finite and positive")
    if not 0.0 < alpha < 1.0:
        raise ResearchConstructionError("alpha must lie strictly between zero and one")
    normal = NormalDist()
    shift = effect * math.sqrt(n)
    if two_sided:
        critical = normal.inv_cdf(1.0 - alpha / 2.0)
        return float(normal.cdf(-critical - shift) + 1.0 - normal.cdf(critical - shift))
    critical = normal.inv_cdf(1.0 - alpha)
    return float(1.0 - normal.cdf(critical - shift))


def same_contract_log_returns(
    frame: pd.DataFrame,
    *,
    price_column: str = "settle",
) -> pd.DataFrame:
    """Compute log returns strictly within each listed contract identity."""
    required = ("trade_date", "contract_id", price_column)
    _require_columns(frame, required, "same-contract returns")
    out = frame.loc[:, list(required)].copy()
    out["trade_date"] = _utc_series(out["trade_date"], "same-contract trade_date")
    if (out["contract_id"].astype(str).str.strip() == "").any():
        raise ResearchConstructionError("same-contract returns contain empty contract_id")
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise ResearchConstructionError("same-contract returns contain duplicate trade_date/contract_id")
    out[price_column] = pd.to_numeric(out[price_column], errors="coerce")
    prices = out[price_column].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ResearchConstructionError("same-contract return prices must be finite and positive")
    out = out.sort_values(["contract_id", "trade_date"], kind="stable").reset_index(drop=True)
    prior = out.groupby("contract_id", sort=False)[price_column].shift(1)
    out["log_return"] = np.log(out[price_column] / prior)
    return out


def validate_replication_package_manifest(
    manifest: Mapping[str, Any],
    *,
    required_roles: Sequence[str] = ("data", "code"),
) -> dict[str, Any]:
    """Validate hash-bound replication-package metadata without executing package contents."""
    package_id = str(manifest.get("package_id", "")).strip()
    source_url = str(manifest.get("source_url", "")).strip()
    artifacts = manifest.get("artifacts")
    if not package_id or not source_url:
        raise ResearchConstructionError("replication package requires package_id and source_url")
    if not isinstance(artifacts, list) or not artifacts:
        raise ResearchConstructionError("replication package requires artifacts")
    normalized: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise ResearchConstructionError("replication package artifact must be an object")
        role = str(item.get("role", "")).strip()
        path = str(item.get("path", "")).strip().replace("\\", "/")
        digest = str(item.get("sha256", "")).strip().lower()
        if not role or not path:
            raise ResearchConstructionError("replication package artifact requires role and path")
        if path.startswith("/") or ".." in path.split("/"):
            raise ResearchConstructionError("replication package artifact path must be relative and bounded")
        if path in seen_paths:
            raise ResearchConstructionError("replication package artifact paths must be unique")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ResearchConstructionError("replication package artifact requires canonical SHA-256")
        seen_paths.add(path)
        normalized.append({"role": role, "path": path, "sha256": digest})
    roles = sorted({item["role"] for item in normalized})
    missing_roles = sorted({str(role) for role in required_roles} - set(roles))
    if missing_roles:
        raise ResearchConstructionError(f"replication package is missing required roles: {missing_roles}")
    return {
        "package_id": package_id,
        "source_url": source_url,
        "artifacts": sorted(normalized, key=lambda item: (item["role"], item["path"])),
        "artifact_roles": roles,
    }


def select_exact_maturity_ranks(
    frame: pd.DataFrame,
    *,
    ranks: Sequence[int],
    preserve_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """Select exact expiration-ranked contracts and fail closed on insufficient curve depth."""
    requested = [int(rank) for rank in ranks]
    if not requested or len(set(requested)) != len(requested) or any(rank < 1 for rank in requested):
        raise ResearchConstructionError("requested maturity ranks must be unique positive integers")
    required = ("trade_date", "contract_id", "expiration")
    _require_columns(frame, (*required, *preserve_columns), "maturity-rank selection")
    ranked = rank_contracts_by_expiration(frame)
    payload_columns = [column for column in preserve_columns if column not in required]
    payload = frame.loc[:, ["trade_date", "contract_id", *payload_columns]].copy()
    payload["trade_date"] = _utc_series(payload["trade_date"], "maturity selection trade_date")
    payload["contract_id"] = payload["contract_id"].astype(str)
    if payload.duplicated(["trade_date", "contract_id"]).any():
        raise ResearchConstructionError("maturity-rank payload contains duplicate trade_date/contract_id")
    ranked["contract_id"] = ranked["contract_id"].astype(str)
    merged = ranked.merge(payload, on=["trade_date", "contract_id"], how="left", validate="one_to_one")
    selected = merged.loc[merged["maturity_rank"].isin(requested)].copy()
    required_count = len(requested)
    complete = selected.groupby("trade_date")["maturity_rank"].agg(
        lambda values: {int(value) for value in values}
    )
    expected = set(requested)
    if len(complete) != merged["trade_date"].nunique() or any(value != expected for value in complete):
        raise ResearchConstructionError(
            f"requested maturity ranks {sorted(requested)} are not available on every trade date"
        )
    selected = selected.sort_values(["trade_date", "maturity_rank"], kind="stable")
    if selected.groupby("trade_date").size().ne(required_count).any():
        raise ResearchConstructionError("maturity-rank selection produced ambiguous curve rows")
    return selected.reset_index(drop=True)


def build_m1_m6_log_curve_slope(
    frame: pd.DataFrame,
    *,
    price_column: str = "settle",
) -> pd.DataFrame:
    """Compute the exact M1-M6 OLS log-price slope on normalized maturity rank."""
    selected = select_exact_maturity_ranks(
        frame,
        ranks=[1, 2, 3, 4, 5, 6],
        preserve_columns=[price_column],
    )
    selected[price_column] = pd.to_numeric(selected[price_column], errors="coerce")
    prices = selected[price_column].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ResearchConstructionError("M1-M6 curve prices must be finite and positive")
    selected["_rank_normalized"] = (selected["maturity_rank"].astype(float) - 1.0) / 5.0
    selected["_log_price"] = np.log(selected[price_column].astype(float))
    selected["_slope_term"] = (selected["_rank_normalized"] - 0.5) * selected["_log_price"]
    slopes = (
        selected.groupby("trade_date", as_index=False)["_slope_term"]
        .sum()
        .rename(columns={"_slope_term": "m1_m6_log_slope"})
    )
    slopes["m1_m6_log_slope"] = slopes["m1_m6_log_slope"] / 0.7
    month = slopes["trade_date"].dt.month
    slopes["season"] = np.where(
        month.isin([11, 12, 1, 2, 3]),
        "winter_withdrawal",
        "injection",
    )
    return slopes.sort_values("trade_date", kind="stable").reset_index(drop=True)
