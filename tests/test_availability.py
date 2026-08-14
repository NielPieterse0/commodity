import pandas as pd
import pytest

from commodity.availability import (
    annotate_eia930_generation_availability,
    annotate_eia930_region_availability,
    annotate_weather_research_availability,
    annotate_wngsr_availability,
    asof_join_point_in_time,
    validate_availability,
)
from commodity.config import data_config

POWER_CFG = {
    "availability_policy": {
        "timezone": "America/New_York",
        "demand": {"period_end_reporting_lag_minutes": 60},
        "demand_forecast": {"local_hour": 11, "local_minute": 10, "day_offset": 0},
        "generation": {"local_hour": 11, "local_minute": 10, "day_offset": 1},
    }
}

WEATHER_CFG = {
    "availability_policy": {
        "historical_exact_status": "unverified",
        "research_global_model_delay_minutes": 360,
        "server_consistency_margin_minutes": 10,
    }
}

WNGSR_CFG = {
    "availability_policy": {
        "timezone": "America/New_York",
        "regular_release_weekday": "Thursday",
        "regular_release_hour": 10,
        "regular_release_minute": 30,
        "exception_registry_coverage_start": "2025-01-01",
        "exception_registry_coverage_end": "2026-11-25",
        "release_date_overrides": {
            "2025-11-13": "2025-11-14T10:30:00-05:00",
            "2026-11-26": "2026-11-25T12:00:00-05:00",
        },
    }
}


def test_eia930_demand_uses_hour_ending_timestamp_plus_reporting_lag() -> None:
    frame = pd.DataFrame({"period": ["2026-01-02T18"], "type": ["D"], "value": [1.0]})
    out = annotate_eia930_region_availability(frame, POWER_CFG)
    assert out.iloc[0]["observed_for"] == pd.Timestamp("2026-01-02T18:00:00Z")
    assert out.iloc[0]["available_at"] == pd.Timestamp("2026-01-02T19:00:00Z")
    assert out.iloc[0]["availability_status"] == "reconstructed_conservative"
    assert out.iloc[0]["revision_status"] == "current_snapshot_revised_history"


def test_eia930_demand_forecast_cutoff_is_dst_aware() -> None:
    frame = pd.DataFrame({"period": ["2026-07-01T16"], "type": ["DF"], "value": [1.0]})
    out = annotate_eia930_region_availability(frame, POWER_CFG)
    assert out.iloc[0]["available_at"] == pd.Timestamp("2026-07-01T15:10:00Z")


def test_eia930_generation_uses_next_day_morning_cutoff() -> None:
    frame = pd.DataFrame({"period": ["2026-07-01T16"], "value": [1.0]})
    out = annotate_eia930_generation_availability(frame, POWER_CFG)
    assert out.iloc[0]["available_at"] == pd.Timestamp("2026-07-02T15:10:00Z")
    assert out.iloc[0]["revision_status"] == "current_snapshot_revised_history"


def test_wngsr_regular_release_uses_following_thursday() -> None:
    frame = pd.DataFrame({"period": ["2025-10-31"], "value": [3900.0]})
    out = annotate_wngsr_availability(frame, WNGSR_CFG)
    assert out.iloc[0]["available_at"] == pd.Timestamp("2025-11-06T15:30:00Z")
    assert out.iloc[0]["availability_status"] == "reconstructed_conservative"


def test_wngsr_official_exception_overrides_regular_release() -> None:
    frame = pd.DataFrame({"period": ["2025-11-07"], "value": [3950.0]})
    out = annotate_wngsr_availability(frame, WNGSR_CFG)
    assert out.iloc[0]["available_at"] == pd.Timestamp("2025-11-14T15:30:00Z")


def test_wngsr_before_exception_registry_coverage_fails_closed() -> None:
    frame = pd.DataFrame({"period": ["2024-10-25"], "value": [3800.0]})
    out = annotate_wngsr_availability(frame, WNGSR_CFG)
    assert pd.isna(out.iloc[0]["available_at"])
    assert out.iloc[0]["availability_status"] == "unresolved"


def test_wngsr_after_exception_registry_coverage_fails_closed() -> None:
    frame = pd.DataFrame({"period": ["2026-11-27"], "value": [3800.0]})
    out = annotate_wngsr_availability(frame, WNGSR_CFG)
    assert pd.isna(out.iloc[0]["available_at"])
    assert out.iloc[0]["availability_status"] == "unresolved"


def test_wngsr_known_end_boundary_override_is_still_accepted() -> None:
    frame = pd.DataFrame({"period": ["2026-11-20"], "value": [3800.0]})
    out = annotate_wngsr_availability(frame, WNGSR_CFG)
    assert out.iloc[0]["available_at"] == pd.Timestamp("2026-11-25T17:00:00Z")


def test_weather_research_availability_keeps_issue_time_separate() -> None:
    frame = pd.DataFrame(
        {
            "issued_at": [pd.Timestamp("2024-08-13T00:00:00Z")],
            "forecast_valid_at": [pd.Timestamp("2024-08-13T12:00:00Z")],
            "temperature_2m": [25.0],
        }
    )
    out = annotate_weather_research_availability(frame, WEATHER_CFG)
    assert out.iloc[0]["issued_at"] == pd.Timestamp("2024-08-13T00:00:00Z")
    assert out.iloc[0]["available_at"] == pd.Timestamp("2024-08-13T06:10:00Z")
    assert out.iloc[0]["availability_status"] == "reconstructed_conservative"
    assert out.iloc[0]["revision_status"] == "issued_run_immutable"


def test_research_pit_accepts_conservative_immutable_weather() -> None:
    frame = pd.DataFrame(
        {
            "available_at": [pd.Timestamp("2026-01-01T12:00:00Z")],
            "availability_status": ["reconstructed_conservative"],
            "revision_status": ["issued_run_immutable"],
        }
    )
    out = validate_availability(frame, "research_pit")
    assert len(out) == 1
    assert out.iloc[0]["evidence_mode"] == "research_pit"
    assert not bool(out.iloc[0]["canonical_evidence"])


def test_research_pit_rejects_current_snapshot_revision_history() -> None:
    frame = pd.DataFrame(
        {
            "available_at": [pd.Timestamp("2026-01-01T12:00:00Z")],
            "availability_status": ["reconstructed_conservative"],
            "revision_status": ["current_snapshot_revised_history"],
        }
    )
    with pytest.raises(ValueError, match="research_pit"):
        validate_availability(frame, "research_pit")
    screening = validate_availability(frame, "screening")
    assert len(screening) == 1
    assert bool(screening.iloc[0]["revision_leakage_risk"])


def test_canonical_requires_verified_point_in_time_rows() -> None:
    frame = pd.DataFrame(
        {
            "available_at": [pd.Timestamp("2026-01-01T12:00:00Z")],
            "availability_status": ["verified"],
            "revision_status": ["point_in_time"],
        }
    )
    canonical = validate_availability(frame, "canonical")
    assert len(canonical) == 1
    assert bool(canonical.iloc[0]["canonical_evidence"])
    with pytest.raises(ValueError, match="Unknown availability mode"):
        validate_availability(frame, "anything")


def test_asof_join_never_uses_future_information() -> None:
    cutoffs = pd.DataFrame(
        {
            "prediction_time": pd.to_datetime(
                ["2026-01-01T15:00:00Z", "2026-01-01T17:00:00Z"], utc=True
            )
        }
    )
    exogenous = pd.DataFrame(
        {
            "available_at": [pd.Timestamp("2026-01-01T16:00:00Z")],
            "availability_status": ["reconstructed_conservative"],
            "revision_status": ["issued_run_immutable"],
            "weather_signal": [7.0],
        }
    )
    joined = asof_join_point_in_time(
        cutoffs, exogenous, ["weather_signal"], mode="research_pit"
    )
    assert pd.isna(joined.iloc[0]["weather_signal"])
    assert joined.iloc[1]["weather_signal"] == 7.0
    assert joined.iloc[1]["evidence_mode"] == "research_pit"


def test_asof_join_rejects_ambiguous_duplicate_availability_times() -> None:
    cutoffs = pd.DataFrame(
        {"prediction_time": pd.to_datetime(["2026-01-01T17:00:00Z"], utc=True)}
    )
    exogenous = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2026-01-01T16:00:00Z", "2026-01-01T16:00:00Z"], utc=True
            ),
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["issued_run_immutable"] * 2,
            "weather_signal": [7.0, 9.0],
        }
    )
    with pytest.raises(ValueError, match="unique available_at"):
        asof_join_point_in_time(
            cutoffs, exogenous, ["weather_signal"], mode="research_pit"
        )


def test_screening_join_retains_revision_risk_labels() -> None:
    cutoffs = pd.DataFrame(
        {"prediction_time": pd.to_datetime(["2026-01-01T17:00:00Z"], utc=True)}
    )
    exogenous = pd.DataFrame(
        {
            "available_at": [pd.Timestamp("2026-01-01T16:00:00Z")],
            "availability_status": ["reconstructed_conservative"],
            "revision_status": ["current_snapshot_revised_history"],
            "power_signal": [5.0],
        }
    )
    joined = asof_join_point_in_time(
        cutoffs, exogenous, ["power_signal"], mode="screening"
    )
    assert joined.iloc[0]["power_signal"] == 5.0
    assert joined.iloc[0]["revision_status"] == "current_snapshot_revised_history"
    assert bool(joined.iloc[0]["revision_leakage_risk"])
    assert not bool(joined.iloc[0]["canonical_evidence"])


def test_authoritative_config_owns_availability_rules_without_unlocking_massive() -> None:
    cfg = data_config()
    storage = cfg["sources"]["eia_storage"]["availability_policy"]
    power = cfg["sources"]["eia_power"]["availability_policy"]
    weather = cfg["sources"]["weather"]["availability_policy"]
    assert storage["timezone"] == "America/New_York"
    assert storage["exception_registry_coverage_end"] == "2026-11-25"
    assert "2025-11-13" in storage["release_date_overrides"]
    assert power["demand"]["period_end_reporting_lag_minutes"] == 60
    assert weather["research_global_model_delay_minutes"] == 360
    canonical = cfg["sources"]["market_canonical"]
    assert canonical["non_display_backtesting_rights_verified"] is False
    assert canonical["backtest_evidence_allowed"] is False


def test_asof_join_keeps_independent_series_grouped() -> None:
    cutoffs = pd.DataFrame(
        {
            "prediction_time": pd.to_datetime(
                ["2026-01-01T17:00:00Z", "2026-01-01T17:00:00Z"], utc=True
            ),
            "series": ["D", "DF"],
        }
    )
    exogenous = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2026-01-01T16:00:00Z", "2026-01-01T16:30:00Z"], utc=True
            ),
            "series": ["D", "DF"],
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["issued_run_immutable"] * 2,
            "power_signal": [7.0, 9.0],
        }
    )
    joined = asof_join_point_in_time(
        cutoffs, exogenous, ["power_signal"], mode="research_pit", by="series"
    )
    assert list(joined["power_signal"]) == [7.0, 9.0]


def test_asof_join_requires_group_key_for_multi_series_source() -> None:
    cutoffs = pd.DataFrame(
        {"prediction_time": pd.to_datetime(["2026-01-01T17:00:00Z"], utc=True)}
    )
    exogenous = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2026-01-01T16:00:00Z", "2026-01-01T16:30:00Z"], utc=True
            ),
            "type": ["D", "DF"],
            "availability_status": ["reconstructed_conservative"] * 2,
            "revision_status": ["issued_run_immutable"] * 2,
            "power_signal": [7.0, 9.0],
        }
    )
    with pytest.raises(ValueError, match="group"):
        asof_join_point_in_time(
            cutoffs, exogenous, ["power_signal"], mode="research_pit"
        )


def test_validate_availability_requires_causal_issue_order() -> None:
    issued = pd.Timestamp("2026-01-01T12:00:00Z")
    frame = pd.DataFrame(
        {
            "issued_at": [issued],
            "available_at": [issued - pd.Timedelta(minutes=1)],
            "availability_status": ["verified"],
            "revision_status": ["issued_run_immutable"],
        }
    )
    with pytest.raises(ValueError, match="issued_at"):
        validate_availability(frame, "research_pit")
