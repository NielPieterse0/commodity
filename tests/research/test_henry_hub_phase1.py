from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from commodity.henry_hub_phase1 import (
    ColumnSubsetRidgeModel,
    FeatureBaselineModel,
    build_announcement_forecast_panel,
    build_curve_forecast_panel,
    build_front_forecast_panel,
    build_storage_forecast_panel,
    classify_skill_evidence,
    split_reserved_confirmation,
)


def _contracts() -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=45, freq="B", tz="UTC")
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        specs = [
            ("A", "2026-06-20", 3.0 + 0.03 * i, 100.0),
            ("B", "2026-07-20", 3.2 + 0.02 * i, 90.0),
            ("C", "2026-08-20", 3.4 + 0.01 * i, 80.0),
            ("D", "2026-09-20", 3.5 + 0.01 * i, 70.0),
            ("E", "2026-10-20", 3.6 + 0.01 * i, 60.0),
            ("F", "2026-11-20", 3.7 + 0.01 * i, 50.0),
        ]
        for contract_id, expiration, settle, volume in specs:
            rows.append({
                "trade_date": date,
                "contract_id": contract_id,
                "expiration": pd.Timestamp(expiration, tz="UTC"),
                "settle": settle,
                "volume": volume,
                "available_at": date + pd.Timedelta(hours=23, minutes=59),
            })
    return pd.DataFrame(rows)


def test_front_panel_uses_conservative_cutoff_and_future_same_contract_interval() -> None:
    contracts = _contracts()
    contracts["available_at"] = contracts["available_at"] + pd.Timedelta(days=3)
    panel = build_front_forecast_panel(contracts)
    assert panel.index.is_monotonic_increasing
    assert panel.index.is_unique
    assert list(panel.columns) == [
        "target_start_trade_date",
        "target_end_trade_date",
        "target_end_available_at",
        "trailing_20_abs_return",
        "days_to_maturity",
        "winter",
        "days_to_maturity_x_winter",
        "target_next_return",
        "target_next_abs_return",
    ]
    prices = np.array([3.0 + 0.03 * i for i in range(23)])
    expected_trailing = np.abs(np.log(prices[1:21] / prices[:20])).mean()
    expected_target = np.log(prices[22] / prices[21])
    assert panel.index[0] == pd.Timestamp("2026-02-02T23:59:00Z")
    assert panel.iloc[0]["target_start_trade_date"] == pd.Timestamp("2026-02-03T00:00:00Z")
    assert panel.iloc[0]["target_end_trade_date"] == pd.Timestamp("2026-02-04T00:00:00Z")
    assert panel.iloc[0]["trailing_20_abs_return"] == pytest.approx(expected_trailing)
    assert panel.iloc[0]["target_next_return"] == pytest.approx(expected_target)


def test_front_panel_contract_selection_does_not_use_same_day_volume() -> None:
    contracts = _contracts()
    contracts.loc[contracts["contract_id"].eq("A"), "volume"] = 0.0
    panel = build_front_forecast_panel(contracts)
    prices = np.array([3.0 + 0.03 * i for i in range(23)])
    expected_target = np.log(prices[22] / prices[21])
    assert panel.iloc[0]["target_next_return"] == pytest.approx(expected_target)
    assert panel.index.is_monotonic_increasing


def test_curve_panel_uses_six_expiry_ranks_without_same_day_volume() -> None:
    contracts = _contracts()
    contracts["volume"] = 0.0
    panel = build_curve_forecast_panel(contracts)
    assert {
        "target_start_trade_date",
        "target_end_trade_date",
        "target_end_available_at",
        "m1_m6_log_slope",
        "winter",
        "m1_m6_log_slope_x_winter",
        "target_next_return",
    } == set(panel)
    assert len(panel) == 43
    assert np.isfinite(panel["m1_m6_log_slope"]).all()
    assert panel.index[0] == pd.Timestamp("2026-01-05T23:59:00Z")


def test_feature_baseline_uses_only_the_frozen_prediction_feature() -> None:
    index = pd.date_range("2026-01-01", periods=2, tz="UTC")
    x = pd.DataFrame({"trailing_20_abs_return": [0.1, 0.2]}, index=index)
    y = pd.Series([9.0, 99.0], index=index)
    model = FeatureBaselineModel("trailing_20_abs_return").fit(x.iloc[:1], y.iloc[:1])
    prediction = model.predict(x.iloc[[1]])
    assert prediction.iloc[0] == pytest.approx(0.2)


def test_column_subset_ridge_ignores_challenger_only_feature() -> None:
    index = pd.date_range("2026-01-01", periods=6, tz="UTC")
    x = pd.DataFrame(
        {"weekday": [0, 1, 0, 1, 0, 1], "release": [0, 0, 1, 1, 0, 1]},
        index=index,
        dtype=float,
    )
    y = pd.Series([0.0, 0.1, 1.0, 1.1, 0.0, 1.1], index=index)
    model = ColumnSubsetRidgeModel(("weekday",), alpha=10.0).fit(x, y)
    paired = pd.DataFrame({"weekday": [1.0, 1.0], "release": [0.0, 1.0]}, index=index[:2])
    prediction = model.predict(paired)
    assert prediction.iloc[0] == pytest.approx(prediction.iloc[1])


def test_reserved_confirmation_is_fully_prepared_then_excluded_from_research() -> None:
    index = pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "feature": np.arange(10, dtype=float),
            "target": np.arange(10, dtype=float) / 10.0,
            "target_end_available_at": index + pd.Timedelta(days=2),
        },
        index=index,
    )
    research, reserved, metadata = split_reserved_confirmation(
        frame,
        planning_fraction=0.2,
        label_available_at_column="target_end_available_at",
    )
    assert len(reserved) == 2
    assert len(research) == 6
    assert reserved.index[0] == pd.Timestamp("2026-01-09T00:00:00Z")
    assert research.index.max() == pd.Timestamp("2026-01-06T00:00:00Z")
    assert metadata["prepared_rows"] == 10
    assert metadata["reserved_rows"] == 2
    assert metadata["purged_boundary_rows"] == 2
    assert metadata["preparation_verification_scope"] == "full_prepared_frame"
    assert metadata["preparation_verification_status"] == "passed"
    assert metadata["pre_freeze_outcome_use"] is False
    assert len(metadata["content_sha256"]) == 64


def test_reserved_confirmation_rejects_unusable_prepared_rows_before_sealing() -> None:
    index = pd.date_range("2026-01-01", periods=5, freq="D", tz="UTC")
    frame = pd.DataFrame({"feature": [1.0, 2.0, np.nan, 4.0, 5.0]}, index=index)
    with pytest.raises(ValueError, match="missing values"):
        split_reserved_confirmation(frame)


def test_skill_classification_is_fixed_before_empirical_results() -> None:
    survive = classify_skill_evidence(
        rmse_improvement=0.02,
        relative_rmse_improvement=0.03,
        ci_lower=0.001,
        ci_upper=0.04,
        positive_periods=2,
        negative_periods=1,
        min_relative_improvement=0.01,
    )
    kill = classify_skill_evidence(
        rmse_improvement=-0.02,
        relative_rmse_improvement=-0.03,
        ci_lower=-0.04,
        ci_upper=-0.001,
        positive_periods=0,
        negative_periods=3,
        min_relative_improvement=0.01,
    )
    inconclusive = classify_skill_evidence(
        rmse_improvement=0.02,
        relative_rmse_improvement=0.03,
        ci_lower=-0.01,
        ci_upper=0.04,
        positive_periods=2,
        negative_periods=1,
        min_relative_improvement=0.01,
    )
    assert survive == "SURVIVE"
    assert kill == "KILL"
    assert inconclusive == "INCONCLUSIVE"


def _release_events(dates: list[pd.Timestamp], storage: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "observed_for": [date - pd.Timedelta(days=6) for date in dates],
            "available_at": [date + pd.Timedelta(hours=14, minutes=30) for date in dates],
            "storage_lower48_bcf": storage,
            "storage_weekly_change_bcf": [10.0, -20.0, 15.0, -5.0, 30.0, -10.0],
            "revision_status": ["point_in_time"] * len(dates),
            "source_event_type": ["release"] * len(dates),
        }
    )


def test_storage_forecast_panel_freezes_state_transform_on_development_rows() -> None:
    contracts = _contracts()
    dates = sorted(contracts["trade_date"].unique())
    release_dates = [dates[i] for i in (22, 26, 30, 34, 38, 42)]
    events = _release_events(release_dates, [3000.0, 2800.0, 2600.0, 5000.0, 1000.0, 6000.0])

    panel, state = build_storage_forecast_panel(
        contracts,
        events,
        development_rows=3,
    )
    assert len(panel) == 6
    assert panel.index.is_unique
    assert state["development_rows"] == 3
    assert state["low_inventory_threshold_bcf"] == pytest.approx(2700.0)
    assert panel.iloc[0]["storage_level_z"] == pytest.approx(1.2247448714)
    assert panel.iloc[2]["low_inventory"] == 1.0
    assert panel.iloc[3]["low_inventory"] == 0.0

    changed = events.copy()
    changed.loc[3:, "storage_lower48_bcf"] = [9000.0, 8000.0, 7000.0]
    _, changed_state = build_storage_forecast_panel(
        contracts,
        changed,
        development_rows=3,
    )
    assert changed_state == state


def test_storage_forecast_excludes_release_without_same_contract_target() -> None:
    contracts = _contracts()
    dates = sorted(contracts["trade_date"].unique())
    release_dates = [dates[i] for i in (22, 26, 30, 34, 38, 42)]
    events = _release_events(release_dates, [3000.0, 2800.0, 2600.0, 2500.0, 2400.0, 2300.0])
    extra = events.iloc[[0]].copy()
    extra["available_at"] = pd.Timestamp("2026-02-07T14:30:00Z")
    events = pd.concat([events, extra], ignore_index=True)

    panel, state = build_storage_forecast_panel(contracts, events, development_rows=3)
    assert len(panel) == 6
    assert state["release_rows"] == 7
    assert state["valid_same_contract_market_rows"] == 6
    assert state["excluded_no_same_contract_target"] == 1


def test_announcement_forecast_panel_labels_releases_inside_future_target_interval() -> None:
    contracts = _contracts()
    dates = sorted(contracts["trade_date"].unique())
    release_dates = [dates[i] for i in (25, 30, 35, 40)]
    events = pd.DataFrame(
        {
            "available_at": [date + pd.Timedelta(hours=14, minutes=30) for date in release_dates],
            "source_event_type": ["release"] * len(release_dates),
        }
    )
    panel = build_announcement_forecast_panel(contracts, events)
    release_target_dates = set(pd.to_datetime(release_dates).date)
    labelled = set(
        pd.to_datetime(
            panel.loc[panel["target_end_release"].eq(1.0), "target_end_trade_date"]
        ).dt.date
    )
    assert labelled == release_target_dates
    assert (panel.index < panel["target_start_trade_date"]).all()
    assert panel["target_end_release"].isin([0.0, 1.0]).all()
