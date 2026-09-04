import math

import pandas as pd
import pytest

from commodity.research_construction import (
    ar1_effective_information,
    build_observed_weather_departures,
    build_release_calendar,
    build_same_valid_time_revisions,
    build_storage_seasonal_state,
    managed_money_weekly_changes,
    rank_contracts_by_expiration,
)


def test_contract_ranking_uses_exact_expiration_identity_without_prices():
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-02", "2026-01-02", "2026-01-02"],
            "contract_id": ["NGG26", "NGF26", "NGH26"],
            "expiration": ["2026-02-25", "2026-01-28", "2026-03-27"],
        }
    )
    ranked = rank_contracts_by_expiration(frame)
    assert ranked["contract_id"].tolist() == ["NGF26", "NGG26", "NGH26"]
    assert ranked["maturity_rank"].tolist() == [1, 2, 3]
    assert "settle" not in ranked.columns


def test_contract_ranking_rejects_rows_after_expiration():
    frame = pd.DataFrame(
        {"trade_date": ["2026-02-01"], "contract_id": ["NGF26"], "expiration": ["2026-01-28"]}
    )
    with pytest.raises(ValueError, match="after expiration"):
        rank_contracts_by_expiration(frame)


def test_storage_state_uses_week_of_year_norm_without_market_outcomes():
    frame = pd.DataFrame(
        {
            "observed_for": ["2024-01-05", "2025-01-03", "2024-01-12", "2025-01-10"],
            "storage_lower48_bcf": [3000.0, 2800.0, 2900.0, 2700.0],
        }
    )
    state = build_storage_seasonal_state(frame)
    assert state["seasonal_norm_bcf"].tolist() == [2900.0, 2900.0, 2800.0, 2800.0]
    assert state["storage_anomaly_bcf"].tolist() == [100.0, -100.0, 100.0, -100.0]
    assert state["below_seasonal_norm"].tolist() == [False, True, False, True]


def test_release_calendar_preserves_holiday_shifted_weekdays():
    events = pd.DataFrame(
        {
            "available_at": ["2026-01-08T15:30:00Z", "2026-01-09T15:30:00Z", "2026-01-09T20:00:00Z"],
            "source_event_type": ["release", "release", "revision"],
        }
    )
    calendar = build_release_calendar(events, timezone="America/New_York")
    assert calendar["release_weekday"].tolist() == ["Thursday", "Friday"]
    assert calendar["holiday_shifted"].tolist() == [False, True]


def test_managed_money_primary_change_uses_report_order_and_preserves_availability():
    frame = pd.DataFrame(
        {
            "observed_for": ["2026-01-13", "2026-01-06", "2026-01-20"],
            "available_at": ["2026-01-20T23:59:00Z", "2026-01-13T23:59:00Z", "2026-01-27T23:59:00Z"],
            "managed_money_net": [120.0, 100.0, 90.0],
        }
    )
    result = managed_money_weekly_changes(frame)
    assert result["managed_money_net"].tolist() == [100.0, 120.0, 90.0]
    assert math.isnan(result.iloc[0]["managed_money_net_change"])
    assert result["managed_money_net_change"].iloc[1:].tolist() == [20.0, -30.0]


def test_observed_weather_departures_use_fixed_normals_and_predeclared_weights():
    observations = pd.DataFrame(
        {
            "observed_for": ["2026-01-15", "2026-01-15"],
            "location_id": ["A", "B"],
            "tmax_c": [12.0, 22.0],
            "tmin_c": [8.0, 18.0],
        }
    )
    normals = pd.DataFrame(
        {"location_id": ["A", "B"], "month_day": ["01-15", "01-15"], "normal_tmean_c": [12.0, 18.0]}
    )
    weights = {"A": 0.75, "B": 0.25}
    result = build_observed_weather_departures(observations, normals, weights=weights, degree_day_base_c=18.0)
    row = result.iloc[0]
    assert row["weather_hdd_departure"] == pytest.approx(1.5)
    assert row["weather_cdd_departure"] == pytest.approx(0.5)
    assert row["weather_tmean_departure_c"] == pytest.approx(-1.0)


def test_observed_weather_departures_fail_closed_when_normal_is_missing():
    observations = pd.DataFrame(
        {"observed_for": ["2024-02-29"], "location_id": ["A"], "tmax_c": [10.0], "tmin_c": [0.0]}
    )
    normals = pd.DataFrame({"location_id": ["A"], "month_day": ["02-28"], "normal_tmean_c": [5.0]})
    with pytest.raises(ValueError, match="missing fixed normal"):
        build_observed_weather_departures(observations, normals, weights={"A": 1.0})


def test_same_valid_time_revisions_only_compare_matching_valid_times():
    previous = pd.DataFrame(
        {
            "issued_at": ["2026-01-01T00:00:00Z"] * 3,
            "location_id": ["A"] * 3,
            "forecast_valid_at": ["2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"],
            "temperature_2m": [10.0, 11.0, 12.0],
        }
    )
    current = pd.DataFrame(
        {
            "issued_at": ["2026-01-02T00:00:00Z"] * 2,
            "location_id": ["A"] * 2,
            "forecast_valid_at": ["2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"],
            "temperature_2m": [13.0, 11.0],
        }
    )
    revisions = build_same_valid_time_revisions(current, previous, value_columns=["temperature_2m"])
    assert revisions["forecast_valid_at"].dt.day.tolist() == [3, 4]
    assert revisions["revision_temperature_2m"].tolist() == [2.0, -1.0]


def test_ar1_effective_information_reports_dependence_without_outcomes():
    report = ar1_effective_information(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert report["raw_n"] == 5
    assert report["ar1"] == pytest.approx(1.0)
    assert report["effective_n"] == pytest.approx(0.0)


def test_ar1_effective_information_requires_enough_finite_values():
    with pytest.raises(ValueError, match="at least three"):
        ar1_effective_information(pd.Series([1.0, float("nan"), 2.0]))


def test_monthly_physical_balance_core_uses_exact_common_months_without_fill():
    from commodity.research_construction import build_monthly_physical_balance_core

    series_map = {
        "production": "PROD",
        "consumption": "CONS",
        "imports": "IMP",
        "exports": "EXP",
        "storage_working_gas": "STOR",
    }
    rows = []
    values = {
        "PROD": [3000.0, 3100.0, 3200.0],
        "CONS": [2800.0, 2900.0, 3000.0],
        "IMP": [200.0, 210.0, 220.0],
        "EXP": [100.0, 120.0, 140.0],
        "STOR": [2500.0, 2550.0, 2520.0],
    }
    for series_id, observed in values.items():
        for period, value in zip(["202601", "202602", "202603"], observed, strict=True):
            rows.append({"series_id": series_id, "period": period, "value": value, "unit": "Million Cubic Feet"})
    result = build_monthly_physical_balance_core(pd.DataFrame(rows), series_map=series_map)
    assert result["period"].astype(str).tolist() == ["2026-02", "2026-03"]
    assert result["net_imports_mmcft"].tolist() == [90.0, 80.0]
    assert result["storage_change_mmcft"].tolist() == [50.0, -30.0]


def test_monthly_physical_balance_core_rejects_unit_substitution():
    from commodity.research_construction import build_monthly_physical_balance_core

    frame = pd.DataFrame(
        {"series_id": ["PROD"], "period": ["202601"], "value": [3.0], "unit": ["Billion Cubic Feet"]}
    )
    with pytest.raises(ValueError, match="Million Cubic Feet"):
        build_monthly_physical_balance_core(
            frame,
            series_map={"production": "PROD", "consumption": "CONS", "imports": "IMP", "exports": "EXP", "storage_working_gas": "STOR"},
        )


def test_same_contract_log_returns_never_cross_contract_identity():
    from commodity.research_construction import same_contract_log_returns

    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"],
            "contract_id": ["A", "A", "B", "B"],
            "settle": [2.0, 2.2, 3.0, 2.7],
        }
    )
    result = same_contract_log_returns(frame)
    a = result[result["contract_id"] == "A"].reset_index(drop=True)
    b = result[result["contract_id"] == "B"].reset_index(drop=True)
    assert math.isnan(a.loc[0, "log_return"])
    assert a.loc[1, "log_return"] == pytest.approx(math.log(2.2 / 2.0))
    assert b.loc[1, "log_return"] == pytest.approx(math.log(2.7 / 3.0))


def test_exact_maturity_rank_selection_requires_requested_curve_depth():
    from commodity.research_construction import select_exact_maturity_ranks

    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-02"] * 3,
            "contract_id": ["M1", "M2", "M3"],
            "expiration": ["2026-01-28", "2026-02-25", "2026-03-27"],
            "settle": [3.0, 3.1, 3.2],
        }
    )
    selected = select_exact_maturity_ranks(frame, ranks=[1, 3], preserve_columns=["settle"])
    assert selected["contract_id"].tolist() == ["M1", "M3"]
    assert selected["maturity_rank"].tolist() == [1, 3]
    with pytest.raises(ValueError, match="requested maturity ranks"):
        select_exact_maturity_ranks(frame, ranks=[1, 13], preserve_columns=["settle"])


def test_curve_eligibility_counts_active_contract_depth_only():
    from commodity.research_construction import build_curve_snapshot_eligibility

    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-02"] * 3 + ["2026-01-05"] * 2,
            "contract_id": ["A", "B", "C", "A", "B"],
            "expiration": ["2026-01-28", "2026-02-25", "2026-03-27", "2026-01-28", "2026-02-25"],
        }
    )
    result = build_curve_snapshot_eligibility(frame, required_maturities=3)
    assert result["available_maturities"].tolist() == [3, 2]
    assert result["eligible"].tolist() == [True, False]


def test_exact_monthly_panel_intersects_without_imputation():
    from commodity.research_construction import build_exact_monthly_panel

    left = pd.DataFrame({"period": ["202601", "202602"], "value": [1.0, 2.0]})
    right = pd.DataFrame({"period": ["202602", "202603"], "value": [3.0, 4.0]})
    result = build_exact_monthly_panel({"left": left, "right": right})
    assert result["period"].astype(str).tolist() == ["2026-02"]
    assert result.loc[0, "left"] == 2.0
    assert result.loc[0, "right"] == 3.0


def test_weather_state_cells_are_calendar_and_weather_only():
    from commodity.research_construction import build_weather_state_cells

    frame = pd.DataFrame(
        {
            "observed_for": ["2026-01-15", "2026-07-15", "2026-04-15"],
            "weather_tmean_departure_c": [-2.0, 3.0, 0.0],
            "weather_hdd_departure": [2.0, 0.0, 0.0],
            "weather_cdd_departure": [0.0, 3.0, 0.0],
        }
    )
    result = build_weather_state_cells(frame)
    assert result["season"].tolist() == ["winter", "shoulder", "summer"]
    assert result["departure_sign"].tolist() == ["negative", "zero", "positive"]


def test_release_day_labels_do_not_require_market_values():
    from commodity.research_construction import build_release_day_labels

    market = pd.DataFrame({"trade_date": ["2026-01-08", "2026-01-09"]})
    releases = pd.DataFrame(
        {"release_date": [pd.Timestamp("2026-01-09").date()], "release_weekday": ["Friday"], "holiday_shifted": [True]}
    )
    result = build_release_day_labels(market, releases)
    assert result["is_release_day"].tolist() == [False, True]
    assert result["holiday_shifted_release"].tolist() == [False, True]


def test_standardized_detectable_effect_matches_planning_constant():
    from commodity.research_construction import standardized_detectable_effect

    effect = standardized_detectable_effect(100.0, alpha=0.05, power=0.80)
    assert effect == pytest.approx(0.28016, rel=2e-4)


def test_replication_package_manifest_is_hash_bound_and_nonexecuting():
    from commodity.research_construction import validate_replication_package_manifest

    manifest = {
        "package_id": "paper-replication-v1",
        "source_url": "https://example.org/archive",
        "artifacts": [
            {"role": "data", "path": "data/source.csv", "sha256": "a" * 64},
            {"role": "code", "path": "code/run.m", "sha256": "b" * 64},
        ],
    }
    result = validate_replication_package_manifest(manifest)
    assert result["artifact_roles"] == ["code", "data"]
    assert result["artifacts"][0]["path"] == "code/run.m"
    with pytest.raises(ValueError, match="relative and bounded"):
        validate_replication_package_manifest(
            {**manifest, "artifacts": [{"role": "data", "path": "../escape.csv", "sha256": "a" * 64}]},
            required_roles=["data"],
        )
