from __future__ import annotations

import pandas as pd
import pytest

from commodity.research_construction import (
    build_curve_snapshot_eligibility,
    build_exact_monthly_panel,
    build_release_day_labels,
    build_weather_state_cells,
    standardized_detectable_effect,
    validate_replication_package_manifest,
)


def test_curve_snapshot_eligibility_counts_exact_active_maturities_without_prices():
    frame = pd.DataFrame({
        "trade_date": ["2026-01-02"] * 3 + ["2026-01-05"] * 2,
        "contract_id": ["A", "B", "C", "A", "B"],
        "expiration": ["2026-02-01", "2026-03-01", "2026-04-01", "2026-02-01", "2026-03-01"],
    })
    result = build_curve_snapshot_eligibility(frame, required_maturities=3)
    assert result["available_maturities"].tolist() == [3, 2]
    assert result["eligible"].tolist() == [True, False]
    assert "settlement" not in result.columns


def test_exact_monthly_panel_intersects_series_without_forward_fill():
    left = pd.DataFrame({"period": ["202601", "202602", "202603"], "value": [1.0, 2.0, 3.0]})
    right = pd.DataFrame({"period": ["202602", "202603", "202604"], "value": [20.0, 30.0, 40.0]})
    result = build_exact_monthly_panel({"gas": left, "oil": right})
    assert result["period"].astype(str).tolist() == ["2026-02", "2026-03"]
    assert result[["gas", "oil"]].values.tolist() == [[2.0, 20.0], [3.0, 30.0]]


def test_weather_state_cells_are_source_only_and_deterministic():
    frame = pd.DataFrame({
        "observed_for": ["2026-01-15", "2026-07-15", "2026-04-15"],
        "weather_tmean_departure_c": [-3.0, 2.0, 0.0],
        "weather_hdd_departure": [3.0, 0.0, 0.0],
        "weather_cdd_departure": [0.0, 2.0, 0.0],
    })
    result = build_weather_state_cells(frame)
    assert result["season"].tolist() == ["winter", "shoulder", "summer"]
    assert result["departure_sign"].tolist() == ["negative", "zero", "positive"]


def test_release_day_labels_preserve_holiday_shift_without_market_values():
    market = pd.DataFrame({"trade_date": ["2026-01-08", "2026-01-09", "2026-01-12"]})
    releases = pd.DataFrame({
        "release_date": [pd.Timestamp("2026-01-08").date(), pd.Timestamp("2026-01-09").date()],
        "release_weekday": ["Thursday", "Friday"],
        "holiday_shifted": [False, True],
    })
    result = build_release_day_labels(market, releases)
    assert result["is_release_day"].tolist() == [True, True, False]
    assert result["holiday_shifted_release"].tolist() == [False, True, False]


def test_standardized_detectable_effect_matches_planning_screen():
    assert standardized_detectable_effect(100.0) == pytest.approx(0.2802, abs=0.001)
    with pytest.raises(ValueError, match="effective_n"):
        standardized_detectable_effect(0.0)


def test_replication_package_manifest_requires_hash_bound_data_and_code():
    manifest = {
        "package_id": "paper-replication-v1",
        "source_url": "https://example.invalid/package",
        "artifacts": [
            {"role": "data", "path": "data/input.csv", "sha256": "a" * 64},
            {"role": "code", "path": "code/run.do", "sha256": "b" * 64},
        ],
    }
    validated = validate_replication_package_manifest(manifest)
    assert validated["package_id"] == "paper-replication-v1"
    assert validated["artifact_roles"] == ["code", "data"]


def test_replication_package_manifest_rejects_unbound_artifact():
    manifest = {
        "package_id": "paper-replication-v1",
        "source_url": "https://example.invalid/package",
        "artifacts": [{"role": "data", "path": "data/input.csv", "sha256": "not-a-hash"}],
    }
    with pytest.raises(ValueError, match="SHA-256"):
        validate_replication_package_manifest(manifest)
