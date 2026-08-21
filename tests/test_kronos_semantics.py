from __future__ import annotations

import math

import pandas as pd
import pytest

from commodity.kronos import KronosMiniAdapter
from commodity.roll_safe_market import build_same_contract_model_context
from commodity.v2_kronos import (
    CORRECTED_IMPLEMENTATION_SOURCE_PATHS,
    KronosContractError,
    build_execution_pit_context,
    build_pit_context,
    execution_adapter_frame,
    governed_kronos_forecast,
    governed_return_prediction,
)


def _canonical_rows() -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=4, tz="UTC")
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        for contract_id, expiration, base in (
            ("NGF26", "2026-01-28", 3.0),
            ("NGG26", "2026-02-25", 10.0),
        ):
            close = base + 0.1 * i
            rows.append(
                {
                    "trade_date": date,
                    "contract_id": contract_id,
                    "expiration": pd.Timestamp(expiration, tz="UTC"),
                    "available_at": date + pd.Timedelta(hours=23),
                    "open": close - 0.02,
                    "high": close + 0.05,
                    "low": close - 0.05,
                    "close": close,
                    "volume": 1000.0 + i,
                }
            )
    return pd.DataFrame(rows)


def _selected_path(rows: pd.DataFrame) -> pd.DataFrame:
    chosen: list[dict[str, object]] = []
    for i, date in enumerate(sorted(rows["trade_date"].unique())):
        contract_id = "NGF26" if i < 2 else "NGG26"
        row = rows[
            (rows["trade_date"] == date) & (rows["contract_id"] == contract_id)
        ].iloc[0]
        item = row.to_dict()
        item["roll_reason"] = (
            "initial"
            if i == 0
            else "prior_session_volume_crossover"
            if i == 2
            else "hold"
        )
        chosen.append(item)
    return pd.DataFrame(chosen)


def test_historical_v2_context_still_accepts_mixed_contract_levels() -> None:
    """Preserve consumed #82 runtime semantics under its original frozen identity."""
    raw = _canonical_rows()
    selected = _selected_path(raw)

    context = build_pit_context(selected, "2026-01-07T23:30:00Z")

    assert list(context["contract_id"].unique()) == ["NGF26", "NGG26"]
    assert context["close"].tolist() == pytest.approx([3.0, 3.1, 10.2])


def test_execution_context_uses_same_contract_history_and_preserves_lineage() -> None:
    raw = _canonical_rows()
    selected = _selected_path(raw)

    context = build_execution_pit_context(
        raw,
        selected,
        "2026-01-07T23:30:00Z",
    )

    assert list(context["contract_id"].unique()) == ["NGG26"]
    assert context["close"].tolist() == pytest.approx([10.0, 10.1, 10.2])
    assert set(context["selection_roll_reason"]) == {"prior_session_volume_crossover"}
    assert set(context["transformation"]) == {"same_contract_history_v1"}
    assert context["source_row_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()


def test_execution_adapter_boundary_rejects_mixed_contract_context() -> None:
    raw = _canonical_rows()
    selected = _selected_path(raw)
    context = build_execution_pit_context(raw, selected, "2026-01-07T23:30:00Z")
    mixed = context.copy()
    mixed.loc[mixed.index[0], "contract_id"] = "NGF26"

    with pytest.raises(KronosContractError, match="single contract"):
        execution_adapter_frame(mixed)


def test_execution_context_requires_explicit_timezone_identity() -> None:
    raw = _canonical_rows()
    selected = _selected_path(raw)
    raw["trade_date"] = raw["trade_date"].dt.tz_localize(None)

    with pytest.raises(KronosContractError, match="timezone-aware"):
        build_execution_pit_context(raw, selected, "2026-01-07T23:30:00Z")


def test_corrected_source_paths_include_roll_safe_dependency() -> None:
    assert "src/commodity/roll_safe_market.py" in CORRECTED_IMPLEMENTATION_SOURCE_PATHS


def test_governed_executor_uses_same_contract_history_end_to_end() -> None:
    raw = _canonical_rows()
    selected = _selected_path(raw)
    calls: list[tuple[pd.DataFrame, pd.DatetimeIndex]] = []

    class _Adapter:
        def forecast(self, ohlcv: pd.DataFrame, future_index: pd.DatetimeIndex) -> pd.DataFrame:
            calls.append((ohlcv.copy(), future_index.copy()))
            return pd.DataFrame({"close": [10.3]}, index=future_index)

    forecast, context = governed_kronos_forecast(
        adapter=_Adapter(),
        canonical_market=raw,
        selected_market=selected,
        prediction_time="2026-01-07T23:30:00Z",
        target_timestamp="2026-01-08T23:30:00Z",
    )

    assert len(calls) == 1
    assert calls[0][0]["close"].tolist() == pytest.approx([10.0, 10.1, 10.2])
    assert list(context["contract_id"].unique()) == ["NGG26"]
    assert calls[0][1].equals(pd.DatetimeIndex(["2026-01-08T23:30:00Z"]))
    assert forecast.iloc[0]["close"] == pytest.approx(10.3)


def test_governed_executor_rejects_nonfuture_target_before_adapter_call() -> None:
    raw = _canonical_rows()
    selected = _selected_path(raw)
    called = False

    class _Adapter:
        def forecast(self, ohlcv: pd.DataFrame, future_index: pd.DatetimeIndex) -> pd.DataFrame:
            nonlocal called
            called = True
            return pd.DataFrame()

    with pytest.raises(KronosContractError, match="after prediction_time"):
        governed_kronos_forecast(
            adapter=_Adapter(),
            canonical_market=raw,
            selected_market=selected,
            prediction_time="2026-01-07T23:30:00Z",
            target_timestamp="2026-01-07T23:30:00Z",
        )
    assert called is False


def test_roll_safe_builder_removes_contract_level_discontinuity() -> None:
    raw = _canonical_rows()
    selected = _selected_path(raw)

    context = build_same_contract_model_context(
        raw,
        selected,
        "2026-01-07T23:30:00Z",
    )

    assert list(context["contract_id"].unique()) == ["NGG26"]
    assert context["close"].tolist() == pytest.approx([10.0, 10.1, 10.2])


def test_adapter_boundary_to_evaluator_units_round_trip_is_explicit() -> None:
    calls: list[dict[str, object]] = []

    class _Predictor:
        def predict(self, **kwargs):
            calls.append(kwargs)
            y_timestamp = pd.DatetimeIndex(kwargs["y_timestamp"])
            return pd.DataFrame(
                {
                    "open": [100.5],
                    "high": [102.0],
                    "low": [99.5],
                    "close": [101.0],
                    "volume": [1100.0],
                    "amount": [110550.0],
                },
                index=y_timestamp,
            )

    adapter = KronosMiniAdapter.__new__(KronosMiniAdapter)
    adapter.predictor = _Predictor()
    adapter.inference = {
        "T": 1.0,
        "top_p": 0.9,
        "sample_count": 1,
        "verbose": False,
    }
    history_index = pd.DatetimeIndex(
        ["2026-01-05T23:59:00Z", "2026-01-06T23:59:00Z"]
    )
    history = pd.DataFrame(
        {
            "open": [99.0, 99.5],
            "high": [100.0, 101.0],
            "low": [98.5, 99.0],
            "close": [99.5, 100.0],
            "volume": [900.0, 1000.0],
        },
        index=history_index,
    )
    future_index = pd.DatetimeIndex(["2026-01-07T23:59:00Z"])

    forecast = adapter.forecast(history, future_index)
    prediction = governed_return_prediction(
        predicted_close_next=forecast.iloc[0]["close"],
        observed_close_at_cutoff=history.iloc[-1]["close"],
        current_contract_id="NGG26",
        target_contract_id="NGG26",
    )

    assert calls[0]["pred_len"] == 1
    assert list(calls[0]["df"].columns) == ["open", "high", "low", "close", "volume"]
    assert pd.DatetimeIndex(calls[0]["y_timestamp"]).equals(future_index)
    assert calls[0]["T"] == 1.0
    assert calls[0]["top_p"] == 0.9
    assert calls[0]["sample_count"] == 1
    assert prediction == pytest.approx(math.log(101.0 / 100.0))


def test_cross_contract_target_mapping_still_fails_closed() -> None:
    with pytest.raises(ValueError, match="cross-contract"):
        governed_return_prediction(
            predicted_close_next=10.3,
            observed_close_at_cutoff=10.2,
            current_contract_id="NGG26",
            target_contract_id="NGH26",
        )
