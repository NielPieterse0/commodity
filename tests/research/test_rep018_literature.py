from __future__ import annotations

import math

import pandas as pd

from commodity.rep018_literature import (
    announcement_day_tests,
    build_conservative_eia_release_calendar,
    build_source_roll_returns,
)


def _contract_rows() -> pd.DataFrame:
    dates = pd.to_datetime(["2021-05-28", "2021-05-31", "2021-06-01"], utc=True)
    rows = []
    for date, july, august in zip(dates, [3.00, 3.03, 3.06], [3.20, 3.24, 3.30], strict=True):
        rows.extend(
            [
                {
                    "trade_date": date,
                    "contract_id": "NGN1@2021-06-28",
                    "expiration": pd.Timestamp("2021-06-28T18:30:00Z"),
                    "settle": july,
                },
                {
                    "trade_date": date,
                    "contract_id": "NGQ1@2021-07-28",
                    "expiration": pd.Timestamp("2021-07-28T18:30:00Z"),
                    "settle": august,
                },
            ]
        )
    return pd.DataFrame(rows)


def test_source_roll_switches_at_end_of_month_preceding_month_prior_to_delivery():
    result = build_source_roll_returns(_contract_rows())
    may31 = result.loc[result["trade_date"].eq(pd.Timestamp("2021-05-31T00:00:00Z"))].iloc[0]
    june1 = result.loc[result["trade_date"].eq(pd.Timestamp("2021-06-01T00:00:00Z"))].iloc[0]
    assert may31["contract_id"] == "NGN1@2021-06-28"
    assert june1["contract_id"] == "NGQ1@2021-07-28"


def test_source_roll_return_is_same_contract_not_roll_price_jump():
    result = build_source_roll_returns(_contract_rows())
    june1 = result.loc[result["trade_date"].eq(pd.Timestamp("2021-06-01T00:00:00Z"))].iloc[0]
    assert june1["log_return"] == pytest_approx(math.log(3.30 / 3.24))
    assert june1["log_return"] != pytest_approx(math.log(3.30 / 3.03))


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value, rel=0.0, abs=1e-12)


def test_conservative_calendar_excludes_unverified_holiday_shift_week():
    week_endings = pd.Series(pd.to_datetime(["2021-11-12", "2021-11-19", "2021-11-26"]))
    holidays = pd.DatetimeIndex(pd.to_datetime(["2021-11-25"]))
    calendar = build_conservative_eia_release_calendar(week_endings, federal_holidays=holidays)
    rows = calendar.set_index("standard_release_date")
    assert bool(rows.loc[pd.Timestamp("2021-11-18"), "eligible_release_day"])
    assert not bool(rows.loc[pd.Timestamp("2021-11-25"), "eligible_release_day"])
    assert rows.loc[pd.Timestamp("2021-11-25"), "exclusion_reason"] == "federal_holiday_week"
    assert bool(rows.loc[pd.Timestamp("2021-12-02"), "eligible_release_day"])


def test_announcement_day_test_recovers_negative_premium():
    dates = pd.bdate_range("2020-01-02", periods=260)
    release = dates.weekday == 3
    returns = pd.Series(0.001, index=dates, dtype=float)
    returns.loc[release] = -0.004
    frame = pd.DataFrame(
        {
            "trade_date": dates,
            "log_return": returns.to_numpy(),
            "is_release_day": release,
        }
    )
    evidence = announcement_day_tests(frame, hac_lags=5)
    assert evidence["release_days"] > 40
    assert evidence["announcement_mean"] < evidence["nonannouncement_mean"]
    assert evidence["raw_difference"] < 0.0
    assert evidence["raw_hac"]["ci_upper"] < 0.0
    assert evidence["weekday_controlled_hac"]["coefficient"] < 0.0


def test_eia_fixed_rank_reconstruction_switches_after_front_expiry():
    from commodity.rep018_literature import build_eia_source_roll_returns

    dates = pd.bdate_range("2018-01-24", "2018-01-31", tz="UTC")
    c1 = pd.DataFrame({"trade_date": dates, "price": [3.0, 3.1, 3.2, 3.3, 3.4, 3.5]})
    c2 = pd.DataFrame({"trade_date": dates, "price": [3.2, 3.3, 3.4, 3.5, 3.6, 3.7]})
    result = build_eia_source_roll_returns(c1, c2)
    ranks = result.set_index("trade_date")["selected_rank"]
    assert ranks.loc[pd.Timestamp("2018-01-29T00:00:00Z")] == 2
    assert ranks.loc[pd.Timestamp("2018-01-30T00:00:00Z")] == 1
    assert ranks.loc[pd.Timestamp("2018-01-31T00:00:00Z")] == 1


def test_eia_fixed_rank_returns_cross_rank_switch_as_same_delivery_contract():
    from commodity.rep018_literature import build_eia_source_roll_returns

    dates = pd.bdate_range("2018-01-26", "2018-01-31", tz="UTC")
    c1 = pd.DataFrame({"trade_date": dates, "price": [3.0, 3.1, 3.2, 3.3]})
    c2 = pd.DataFrame({"trade_date": dates, "price": [3.4, 3.5, 3.6, 3.7]})
    result = build_eia_source_roll_returns(c1, c2)
    jan30 = result.loc[result["trade_date"].eq(pd.Timestamp("2018-01-30T00:00:00Z"))].iloc[0]
    assert jan30["log_return"] == pytest_approx(math.log(3.2 / 3.5))


def test_eia_fixed_rank_reconstruction_handles_thanksgiving_expiry_exception():
    from commodity.rep018_literature import build_eia_source_roll_returns

    dates = pd.to_datetime(["2010-11-23", "2010-11-24", "2010-11-26", "2010-11-29"], utc=True)
    c1 = pd.DataFrame({"trade_date": dates, "price": [4.0, 4.1, 4.2, 4.3]})
    c2 = pd.DataFrame({"trade_date": dates, "price": [4.4, 4.5, 4.6, 4.7]})
    result = build_eia_source_roll_returns(c1, c2).set_index("trade_date")
    assert result.loc[pd.Timestamp("2010-11-23T00:00:00Z"), "selected_rank"] == 2
    assert result.loc[pd.Timestamp("2010-11-24T00:00:00Z"), "selected_rank"] == 2
    assert result.loc[pd.Timestamp("2010-11-26T00:00:00Z"), "selected_rank"] == 1


def test_advance_known_calendar_panel_excludes_ambiguous_week_and_labels_target_day():
    from commodity.rep018_literature import build_advance_known_calendar_panel

    index = pd.to_datetime(["2021-11-15T23:59:00Z", "2021-11-16T23:59:00Z"])
    front = pd.DataFrame(
        {
            "target_end_trade_date": pd.to_datetime(["2021-11-18", "2021-11-25"], utc=True),
            "target_end_available_at": pd.to_datetime(["2021-11-18T23:59Z", "2021-11-25T23:59Z"]),
            "target_next_return": [-0.01, 0.02],
        },
        index=index,
    )
    calendar = build_conservative_eia_release_calendar(
        pd.Series(pd.to_datetime(["2021-11-12", "2021-11-19"])),
        federal_holidays=pd.DatetimeIndex(pd.to_datetime(["2021-11-25"])),
    )
    result = build_advance_known_calendar_panel(front, calendar)
    assert len(result) == 1
    assert result.iloc[0]["target_end_release"] == 1.0
    assert result.iloc[0]["target_end_thursday"] == 1.0
