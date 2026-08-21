from __future__ import annotations

import math

import pandas as pd
import pytest

from commodity.kronos import KronosMiniAdapter
from commodity.roll_safe_market import build_same_contract_model_context
from commodity.v2_kronos import build_pit_context, governed_return_prediction


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


def test_current_v2_context_still_accepts_mixed_contract_levels() -> None:
    """Document the residual #154/#133 integration gap without changing runtime semantics."""
    raw = _canonical_rows()
    selected = _selected_path(raw)

    context = build_pit_context(selected, "2026-01-07T23:30:00Z")

    assert list(context["contract_id"].unique()) == ["NGF26", "NGG26"]
    assert context["close"].tolist() == pytest.approx([3.0, 3.1, 10.2])


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
