from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
)
from pandas.tseries.offsets import CustomBusinessDay
from scipy.stats import norm

_REQUIRED_CONTRACT_COLUMNS = {"trade_date", "contract_id", "expiration", "settle"}


def _month_period(values: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(values, utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("monthly period input contains invalid timestamps")
    return timestamps.dt.tz_localize(None).dt.to_period("M")


class _CME2003To2018HolidayCalendar(AbstractHolidayCalendar):
    rules: ClassVar[list[Any]] = [
        Holiday("NewYearsDay", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday("IndependenceDay", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("ChristmasDay", month=12, day=25, observance=nearest_workday),
    ]


_CME_BDAY_2003_2018 = CustomBusinessDay(calendar=_CME2003To2018HolidayCalendar())


def _front_expiry_for_trade_month(month: pd.Period) -> pd.Timestamp:
    delivery_start = (month + 1).to_timestamp(how="start")
    expiry = delivery_start - 3 * _CME_BDAY_2003_2018
    # Historical NYMEX December NG contracts due to expire on the Friday after
    # Thanksgiving ceased trading on the preceding Wednesday instead. This
    # applies in the source period in 2004 and 2010 and is independently
    # evidenced by the exact 2010 contract identity and the 2004 FERC record.
    prior_day = expiry - pd.Timedelta(days=1)
    if expiry.month == 11 and expiry.weekday() == 4 and 22 <= prior_day.day <= 28:
        expiry = expiry - pd.Timedelta(days=2)
    return expiry


def build_eia_source_roll_returns(
    contract1: pd.DataFrame,
    contract2: pd.DataFrame,
) -> pd.DataFrame:
    """Reconstruct the paper's first investable series from EIA fixed-rank prices."""
    required = {"trade_date", "price"}
    frames: list[pd.DataFrame] = []
    for rank, frame in ((1, contract1), (2, contract2)):
        if missing := sorted(required - set(frame.columns)):
            raise ValueError(f"EIA Contract {rank} frame missing required columns: {missing}")
        part = frame.loc[:, ["trade_date", "price"]].copy()
        part["trade_date"] = pd.to_datetime(part["trade_date"], utc=True, errors="coerce")
        part["price"] = pd.to_numeric(part["price"], errors="coerce")
        if part.isna().any().any() or not part["price"].gt(0.0).all():
            raise ValueError(f"EIA Contract {rank} frame contains invalid values")
        if part["trade_date"].duplicated().any():
            raise ValueError(f"EIA Contract {rank} frame contains duplicate trade dates")
        frames.append(part.rename(columns={"price": f"contract{rank}_price"}))
    merged = frames[0].merge(frames[1], on="trade_date", how="inner", validate="one_to_one")
    if merged.empty:
        raise ValueError("EIA fixed-rank series have no common trade dates")
    trade_month = merged["trade_date"].dt.tz_localize(None).dt.to_period("M")
    expiry_map = {month: _front_expiry_for_trade_month(month) for month in trade_month.unique()}
    merged["front_expiry"] = trade_month.map(expiry_map)
    local_date = merged["trade_date"].dt.tz_localize(None).dt.normalize()
    merged["selected_rank"] = np.where(local_date.le(merged["front_expiry"]), 2, 1)
    merged["price"] = np.where(
        merged["selected_rank"].eq(2),
        merged["contract2_price"],
        merged["contract1_price"],
    )
    merged = merged.sort_values("trade_date", kind="stable").reset_index(drop=True)
    merged["log_return"] = np.log(merged["price"] / merged["price"].shift(1))
    return merged[["trade_date", "price", "selected_rank", "front_expiry", "log_return"]]


def build_source_roll_returns(contracts: pd.DataFrame) -> pd.DataFrame:
    """Build source-rule investable returns without ever crossing contract identity."""
    missing = sorted(_REQUIRED_CONTRACT_COLUMNS - set(contracts.columns))
    if missing:
        raise ValueError(f"rep-018 contracts missing required columns: {missing}")
    out = contracts.loc[:, sorted(_REQUIRED_CONTRACT_COLUMNS)].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="coerce")
    out["expiration"] = pd.to_datetime(out["expiration"], utc=True, errors="coerce")
    out["settle"] = pd.to_numeric(out["settle"], errors="coerce")
    if out[["trade_date", "expiration", "settle"]].isna().any().any():
        raise ValueError("rep-018 contracts contain invalid required values")
    if not out["settle"].gt(0.0).all():
        raise ValueError("rep-018 contracts require positive settlements")
    if out.duplicated(["trade_date", "contract_id"]).any():
        raise ValueError("rep-018 contracts contain duplicate contract-day keys")
    if (out["trade_date"] > out["expiration"]).any():
        raise ValueError("rep-018 contracts contain observations after expiration")

    out = out.sort_values(["contract_id", "trade_date"], kind="stable")
    prior = out.groupby("contract_id", sort=False)["settle"].shift(1)
    out["log_return"] = np.log(out["settle"] / prior)

    # NYMEX NG expires in the calendar month immediately before delivery. The
    # source rolls at the end of the month preceding the month prior to delivery,
    # so a return ending in month m may hold the earliest delivery month m+2.
    out["delivery_month"] = _month_period(out["expiration"]) + 1
    out["minimum_delivery_month"] = _month_period(out["trade_date"]) + 2
    eligible = out.loc[out["delivery_month"] >= out["minimum_delivery_month"]].copy()
    if eligible.empty:
        raise ValueError("rep-018 source roll has no eligible contracts")
    selected = (
        eligible.sort_values(
            ["trade_date", "delivery_month", "expiration", "contract_id"],
            kind="stable",
        )
        .drop_duplicates("trade_date", keep="first")
        .sort_values("trade_date", kind="stable")
        .reset_index(drop=True)
    )
    selected = selected.dropna(subset=["log_return"]).copy()
    if selected.empty:
        raise ValueError("rep-018 source roll has no same-contract returns")
    if selected["trade_date"].duplicated().any():
        raise ValueError("rep-018 source roll produced duplicate trade dates")
    return selected[
        [
            "trade_date",
            "contract_id",
            "expiration",
            "delivery_month",
            "settle",
            "log_return",
        ]
    ]


def build_conservative_eia_release_calendar(
    week_ending_dates: Iterable[object],
    *,
    federal_holidays: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Infer standard Thursdays and exclude holiday weeks whose shift is unverified."""
    endings = pd.Series(list(week_ending_dates), name="week_ending")
    endings = pd.to_datetime(endings, errors="coerce").dt.normalize()
    if endings.isna().any() or endings.empty:
        raise ValueError("rep-018 WNGSR week-ending dates are invalid or empty")
    if endings.duplicated().any():
        raise ValueError("rep-018 WNGSR week-ending dates contain duplicates")
    if not endings.dt.dayofweek.eq(4).all():
        raise ValueError("rep-018 WNGSR history must use Friday week-ending dates")

    holidays = pd.DatetimeIndex(pd.to_datetime(federal_holidays, errors="coerce")).normalize()
    if holidays.hasnans:
        raise ValueError("rep-018 federal holiday calendar contains invalid dates")
    holiday_set = set(holidays.to_pydatetime())

    standard = endings + pd.Timedelta(days=6)
    rows: list[dict[str, Any]] = []
    for week_ending, release_date in zip(endings, standard, strict=True):
        monday = release_date - pd.Timedelta(days=3)
        friday = release_date + pd.Timedelta(days=1)
        ambiguous = any(
            monday <= pd.Timestamp(holiday) <= friday for holiday in holiday_set
        )
        rows.append(
            {
                "week_ending": week_ending,
                "standard_release_date": release_date,
                "eligible_release_day": not ambiguous,
                "exclusion_reason": "federal_holiday_week" if ambiguous else None,
            }
        )
    result = pd.DataFrame(rows).sort_values("standard_release_date", kind="stable")
    if not result["standard_release_date"].dt.dayofweek.eq(3).all():
        raise ValueError("rep-018 inferred standard release dates must be Thursday")
    return result.reset_index(drop=True)


def label_announcement_days(
    returns: pd.DataFrame,
    release_calendar: pd.DataFrame,
) -> pd.DataFrame:
    required_returns = {"trade_date", "log_return"}
    required_calendar = {"standard_release_date", "eligible_release_day"}
    if missing := sorted(required_returns - set(returns.columns)):
        raise ValueError(f"rep-018 returns missing required columns: {missing}")
    if missing := sorted(required_calendar - set(release_calendar.columns)):
        raise ValueError(f"rep-018 calendar missing required columns: {missing}")
    out = returns.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="coerce")
    if out["trade_date"].isna().any() or out["trade_date"].duplicated().any():
        raise ValueError("rep-018 returns require unique valid trade dates")
    eligible = release_calendar.loc[release_calendar["eligible_release_day"].eq(True)].copy()
    eligible_dates = set(pd.to_datetime(eligible["standard_release_date"]).dt.date)
    out["is_release_day"] = out["trade_date"].dt.date.isin(eligible_dates)

    ambiguous = release_calendar.loc[~release_calendar["eligible_release_day"].eq(True)].copy()
    ambiguous_dates: set[object] = set()
    for release_date in pd.to_datetime(ambiguous["standard_release_date"]):
        monday = release_date - pd.Timedelta(days=3)
        friday = release_date + pd.Timedelta(days=1)
        ambiguous_dates.update(pd.date_range(monday, friday, freq="D").date)
    out["ambiguous_holiday_week"] = out["trade_date"].dt.date.isin(ambiguous_dates)
    return out.sort_values("trade_date", kind="stable").reset_index(drop=True)


def build_advance_known_calendar_panel(
    front_panel: pd.DataFrame,
    release_calendar: pd.DataFrame,
) -> pd.DataFrame:
    """Attach target-day calendar features while excluding unresolved holiday weeks."""
    required = {"target_end_trade_date", "target_end_available_at", "target_next_return"}
    if missing := sorted(required - set(front_panel.columns)):
        raise ValueError(f"rep-018 forecast panel missing required columns: {missing}")
    if front_panel.empty or front_panel.index.has_duplicates or not front_panel.index.is_monotonic_increasing:
        raise ValueError("rep-018 forecast panel requires chronological unique prediction times")
    out = front_panel.copy()
    out["target_end_trade_date"] = pd.to_datetime(out["target_end_trade_date"], utc=True)
    out["target_end_available_at"] = pd.to_datetime(out["target_end_available_at"], utc=True)
    if (out["target_end_available_at"] <= out.index).any():
        raise ValueError("rep-018 target availability must follow prediction time")
    release_standard = pd.to_datetime(release_calendar["standard_release_date"])
    coverage_start = release_standard.min().date()
    coverage_end = release_standard.max().date()
    eligible = release_calendar.loc[release_calendar["eligible_release_day"].eq(True)].copy()
    release_dates = set(pd.to_datetime(eligible["standard_release_date"]).dt.date)
    ambiguous = release_calendar.loc[~release_calendar["eligible_release_day"].eq(True)]
    ambiguous_dates: set[object] = set()
    for date in pd.to_datetime(ambiguous["standard_release_date"]):
        ambiguous_dates.update(pd.date_range(date - pd.Timedelta(days=3), date + pd.Timedelta(days=1)).date)
    target_dates = out["target_end_trade_date"].dt.date
    in_coverage = target_dates.map(lambda value: coverage_start <= value <= coverage_end)
    out = out.loc[in_coverage & ~target_dates.isin(ambiguous_dates)].copy()
    target_dates = out["target_end_trade_date"].dt.date
    out["target_end_release"] = target_dates.isin(release_dates).astype(float)
    weekday = out["target_end_trade_date"].dt.dayofweek
    names = {0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday", 4: "friday"}
    for code, name in names.items():
        out[f"target_end_{name}"] = weekday.eq(code).astype(float)
    out["winter"] = out["target_end_trade_date"].dt.month.isin([11, 12, 1, 2, 3]).astype(float)
    return out


def _newey_west_regression(y: np.ndarray, x: np.ndarray, *, lags: int) -> dict[str, Any]:
    if y.ndim != 1 or x.ndim != 2 or len(y) != len(x):
        raise ValueError("HAC regression requires aligned one-dimensional y and matrix x")
    if len(y) <= x.shape[1] + lags:
        raise ValueError("HAC regression sample is too small")
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = y - x @ beta
    bread = np.linalg.pinv(x.T @ x)
    xu = x * residual[:, None]
    meat = xu.T @ xu
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1.0)
        gamma = xu[lag:].T @ xu[:-lag]
        meat += weight * (gamma + gamma.T)
    covariance = bread @ meat @ bread
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    return {
        "coefficients": beta,
        "standard_errors": standard_errors,
        "residuals": residual,
    }


def _announcement_hac(frame: pd.DataFrame, *, hac_lags: int, weekday_controls: bool) -> dict[str, float]:
    y = pd.to_numeric(frame["log_return"], errors="coerce").to_numpy(dtype=float)
    release = frame["is_release_day"].astype(float).to_numpy()
    columns = [np.ones(len(frame)), release]
    if weekday_controls:
        weekday = pd.to_datetime(frame["trade_date"], utc=True).dt.dayofweek
        # Thursday (3) is reference; release dates are normally Thursday.
        for code in (0, 1, 2, 4):
            columns.append(weekday.eq(code).astype(float).to_numpy())
    x = np.column_stack(columns)
    fit = _newey_west_regression(y, x, lags=hac_lags)
    coefficient = float(fit["coefficients"][1])
    standard_error = float(fit["standard_errors"][1])
    z = coefficient / standard_error if standard_error > 0.0 else math.copysign(math.inf, coefficient)
    pvalue = float(2.0 * norm.sf(abs(z)))
    return {
        "coefficient": coefficient,
        "standard_error": standard_error,
        "z_statistic": z,
        "pvalue_two_sided": pvalue,
        "ci_lower": coefficient - 1.96 * standard_error,
        "ci_upper": coefficient + 1.96 * standard_error,
    }


def announcement_day_tests(frame: pd.DataFrame, *, hac_lags: int = 5) -> dict[str, Any]:
    required = {"trade_date", "log_return", "is_release_day"}
    if missing := sorted(required - set(frame.columns)):
        raise ValueError(f"rep-018 test frame missing required columns: {missing}")
    out = frame.loc[:, ["trade_date", "log_return", "is_release_day"]].copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="coerce")
    out["log_return"] = pd.to_numeric(out["log_return"], errors="coerce")
    out = out.dropna(subset=["trade_date", "log_return"])
    if out.empty or out["trade_date"].duplicated().any():
        raise ValueError("rep-018 test requires unique non-empty market dates")
    release = out["is_release_day"].astype(bool)
    if release.sum() < 10 or (~release).sum() < 10:
        raise ValueError("rep-018 test requires at least ten release and non-release days")
    announcement_mean = float(out.loc[release, "log_return"].mean())
    nonannouncement_mean = float(out.loc[~release, "log_return"].mean())
    total_return = float(out["log_return"].sum())
    announcement_return = float(out.loc[release, "log_return"].sum())
    share = announcement_return / total_return if not math.isclose(total_return, 0.0, abs_tol=1e-15) else None
    return {
        "rows": len(out),
        "release_days": int(release.sum()),
        "nonrelease_days": int((~release).sum()),
        "announcement_mean": announcement_mean,
        "nonannouncement_mean": nonannouncement_mean,
        "raw_difference": announcement_mean - nonannouncement_mean,
        "announcement_cumulative_return": announcement_return,
        "total_cumulative_return": total_return,
        "announcement_share_of_cumulative_return": share,
        "raw_hac": _announcement_hac(out, hac_lags=hac_lags, weekday_controls=False),
        "weekday_controlled_hac": _announcement_hac(
            out, hac_lags=hac_lags, weekday_controls=True
        ),
    }
