import numpy as np
import pandas as pd
import pytest


def _market_frame(n: int = 80) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    close = 3.0 + np.linspace(0.0, 0.8, n) + 0.05 * np.sin(np.arange(n))
    return pd.DataFrame(
        {
            "open": close - 0.02,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 1000.0 + np.arange(n),
        },
        index=index,
    )


def test_pit_dataset_identity_is_deterministic() -> None:
    from commodity.research_dataset import build_pit_dataset

    first, first_manifest = build_pit_dataset(_market_frame())
    second, second_manifest = build_pit_dataset(_market_frame())

    pd.testing.assert_frame_equal(first, second)
    assert first_manifest["dataset_sha256"] == second_manifest["dataset_sha256"]
    assert first_manifest["dataset_id"] == second_manifest["dataset_id"]
    assert first_manifest["evidence_mode"] == "research_pit"
    assert first_manifest["completeness"] == "pit_core"


def test_screening_source_is_rejected_from_pit_dataset() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    source = PitFeatureSource(
        name="revised_power",
        family="power",
        frame=pd.DataFrame(
            {
                "available_at": [pd.Timestamp("2025-02-01T12:00:00Z")],
                "availability_status": ["reconstructed_conservative"],
                "revision_status": ["current_snapshot_revised_history"],
                "power_signal": [1.0],
            }
        ),
        value_columns=("power_signal",),
        evidence_mode="screening",
    )

    with pytest.raises(ValueError):
        build_pit_dataset(_market_frame(), exogenous=[source])


def test_pit_join_respects_availability_cutoff() -> None:
    from commodity.research_dataset import PitFeatureSource, build_pit_dataset

    source = PitFeatureSource(
        name="issued_weather",
        family="weather",
        frame=pd.DataFrame(
            {
                "available_at": [pd.Timestamp("2025-03-01T12:00:00Z")],
                "availability_status": ["reconstructed_conservative"],
                "revision_status": ["issued_run_immutable"],
                "weather_signal": [7.0],
            }
        ),
        value_columns=("weather_signal",),
    )
    dataset, _ = build_pit_dataset(_market_frame(), exogenous=[source])

    assert dataset.index.min() >= pd.Timestamp("2025-03-01T12:00:00Z")
    assert dataset["weather_signal"].eq(7.0).all()


def test_full_v1_requires_all_configured_families() -> None:
    from commodity.research_dataset import build_pit_dataset

    with pytest.raises(ValueError):
        build_pit_dataset(
            _market_frame(),
            required_families=("market", "calendar_seasonality", "weather"),
            require_full_v1=True,
        )
