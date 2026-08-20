import math

import pandas as pd
import pytest

from commodity.roll_safe_market import (
    build_same_contract_model_context,
    same_contract_selected_returns,
)


def _rows() -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=4, tz="UTC")
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        for contract, expiration, base in (
            ("NGF26", "2026-01-28", 3.0),
            ("NGG26", "2026-02-25", 10.0),
        ):
            close = base + 0.1 * i
            rows.append(
                {
                    "trade_date": date,
                    "contract_id": contract,
                    "expiration": pd.Timestamp(expiration, tz="UTC"),
                    "available_at": date + pd.Timedelta(hours=23),
                    "open": close - 0.02,
                    "high": close + 0.05,
                    "low": close - 0.05,
                    "close": close,
                    "settle": close,
                    "volume": 1000.0 + i,
                }
            )
    return pd.DataFrame(rows)


def _selected(rows: pd.DataFrame) -> pd.DataFrame:
    chosen = []
    for i, date in enumerate(sorted(rows["trade_date"].unique())):
        contract = "NGF26" if i < 2 else "NGG26"
        row = rows[(rows["trade_date"] == date) & (rows["contract_id"] == contract)].iloc[0]
        selected = row.to_dict()
        selected["roll_reason"] = "prior_session_volume_crossover" if i == 2 else ("initial" if i == 0 else "hold")
        chosen.append(selected)
    return pd.DataFrame(chosen)


def test_roll_day_feature_return_uses_new_contract_own_prior_session() -> None:
    rows = _rows()
    selected = _selected(rows)

    returns = same_contract_selected_returns(rows, selected, price_col="settle")

    roll_date = pd.Timestamp("2026-01-07", tz="UTC")
    expected = math.log(10.2 / 10.1)
    assert returns.loc[roll_date] == pytest.approx(expected)
    assert returns.loc[roll_date] != pytest.approx(0.0)
    assert returns.loc[roll_date] != pytest.approx(math.log(10.2 / 3.1))


def test_same_contract_model_context_contains_only_selected_contract_history() -> None:
    rows = _rows()
    selected = _selected(rows)
    cutoff = pd.Timestamp("2026-01-07T23:30:00Z")

    context = build_same_contract_model_context(rows, selected, cutoff, max_context=512)

    assert list(context["contract_id"].unique()) == ["NGG26"]
    assert list(context["trade_date"]) == list(pd.date_range("2026-01-05", periods=3, tz="UTC"))
    assert set(context["selection_roll_reason"]) == {"prior_session_volume_crossover"}
    assert set(context["transformation"]) == {"same_contract_history_v1"}
    assert context["source_row_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert context["close"].tolist() == pytest.approx([10.0, 10.1, 10.2])


def test_roll_safe_outputs_are_append_future_invariant() -> None:
    rows = _rows()
    selected = _selected(rows)
    cutoff = pd.Timestamp("2026-01-07T23:30:00Z")
    base_context = build_same_contract_model_context(rows, selected, cutoff)
    base_returns = same_contract_selected_returns(rows, selected)

    future = rows.copy()
    extras = rows[rows["trade_date"] == pd.Timestamp("2026-01-08", tz="UTC")].copy()
    extras["trade_date"] = pd.Timestamp("2026-01-09", tz="UTC")
    extras["available_at"] = pd.Timestamp("2026-01-09T23:00:00Z")
    extras[["open", "high", "low", "close", "settle"]] += 0.5
    future = pd.concat([future, extras], ignore_index=True)
    future_selected = selected.copy()

    observed_context = build_same_contract_model_context(future, future_selected, cutoff)
    observed_returns = same_contract_selected_returns(future, future_selected)

    pd.testing.assert_frame_equal(observed_context, base_context)
    pd.testing.assert_series_equal(observed_returns, base_returns)
