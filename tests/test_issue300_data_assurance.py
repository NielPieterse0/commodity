from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from commodity.cftc import cftc_research_availability
from commodity.config import assumptions_config, data_config
from commodity.data_assurance import (
    DataAssuranceError,
    assert_research_ready,
    verify_reconstructed_frame,
)
from commodity.massive_futures_provider import normalize_massive_contract_history
from commodity.research_dataset import build_pit_dataset
from commodity.rolls import build_derived_continuous_series


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=30, freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": 3.0, "high": 3.2, "low": 2.8, "close": 3.1, "volume": 100.0},
        index=index,
    )


def test_research_pit_derives_literal_conservative_market_availability() -> None:
    dataset, manifest = build_pit_dataset(_market(), required_families=("market", "calendar_seasonality"))
    assert dataset.index[0].hour == 23 and dataset.index[0].minute == 59
    assert manifest["prediction_timestamp_semantics"] == "explicit_or_conservatively_derived_market_available_at_cutoff"
    assert_research_ready(manifest["data_assurance"])


def test_data_assurance_is_tamper_evident() -> None:
    _, manifest = build_pit_dataset(_market(), required_families=("market", "calendar_seasonality"))
    broken = json.loads(json.dumps(manifest["data_assurance"]))
    broken["layers"][0]["sha256"] = "0" * 64
    with pytest.raises(DataAssuranceError, match="identity"):
        assert_research_ready(broken)


def test_massive_component_hash_is_column_order_invariant() -> None:
    contract = {
        "ticker": "NGF26", "last_trade_date": "2026-01-28", "trading_venue": "NYMEX", "product_code": "NG"
    }
    aggregates = pd.DataFrame({
        "session_end_date": ["2026-01-02"], "settlement_price": [3.1], "volume": [123]
    })
    _, left = normalize_massive_contract_history(contract, aggregates, "2026-01-03T00:00:00Z")
    _, right = normalize_massive_contract_history(contract, aggregates[["volume", "settlement_price", "session_end_date"]], "2026-01-03T00:00:00Z")
    assert left["source_sha256"] == right["source_sha256"]


def test_cftc_retained_2024_policy_is_replayable_and_versioned() -> None:
    result = cftc_research_availability("2024-01-02")
    assert result["available_at"] > pd.Timestamp("2024-01-02T00:00:00Z")
    assert result["availability_policy_version"] == "ordinary-conservative-v1"


def test_cftc_2025_12_30_uses_final_accelerated_release_date() -> None:
    result = cftc_research_availability("2025-12-30")
    assert result["available_at"] == pd.Timestamp("2026-01-06T04:59:00Z")
    assert result["availability_policy_version"] == "shutdown-special-v1"


def _roll_frame() -> pd.DataFrame:
    rows = []
    for day, front, nxt in (
        ("2026-01-05", 100, 80),
        ("2026-01-06", 90, 110),
        ("2026-01-07", 80, 120),
        ("2026-01-08", 70, 130),
    ):
        cutoff = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=23)
        rows.extend([
            {"trade_date": day, "contract_id": "NGF26", "expiration": "2026-01-20", "settle": 3.0, "volume": front, "available_at": cutoff},
            {"trade_date": day, "contract_id": "NGG26", "expiration": "2026-02-20", "settle": 3.2, "volume": nxt, "available_at": cutoff},
        ])
    return pd.DataFrame(rows)


def test_roll_rejects_delayed_prior_session_volume_evidence() -> None:
    frame = _roll_frame()
    delayed = pd.Timestamp("2026-01-09T01:00:00Z")
    frame.loc[frame["trade_date"].eq("2026-01-07"), "available_at"] = delayed
    policy = assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]
    path, ledger = build_derived_continuous_series(frame, data_config()["canonical_contract_schema"], policy)
    assert list(path["contract_id"]) == ["NGF26"] * 4
    assert ledger.empty


def test_phase_d_v1_is_preserved_as_known_defective_evidence() -> None:
    methodology = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "research_methodology.json").read_text(
            encoding="utf-8"
        )
    )
    status = methodology["legacy_evidence"]
    assert status["phase_d_v1_status"] == "preserved_known_predictor_defect"
    assert status["completed_v1_v2_rewritten"] is False
    assert status["reuse_as_current_clean_evidence"] is False


@pytest.mark.parametrize("mutation", ["row", "column", "timestamp", "value"])
def test_reconstruction_comparison_rejects_material_drift(mutation: str) -> None:
    expected = _market().iloc[:3].copy()
    reconstructed = expected.copy()
    if mutation == "row":
        reconstructed = reconstructed.iloc[:-1]
    elif mutation == "column":
        reconstructed = reconstructed.drop(columns=["volume"])
    elif mutation == "timestamp":
        reconstructed.index = reconstructed.index + pd.Timedelta(minutes=1)
    else:
        reconstructed.iloc[0, reconstructed.columns.get_loc("close")] += 0.01

    with pytest.raises(DataAssuranceError, match="reconstruction"):
        verify_reconstructed_frame(expected, reconstructed, layer="fixture")


def test_reconstruction_comparison_accepts_exact_rebuild() -> None:
    expected = _market().iloc[:3].copy()
    result = verify_reconstructed_frame(expected, expected.copy(), layer="fixture")
    assert result["status"] == "verified"
    assert len(result["sha256"]) == 64
