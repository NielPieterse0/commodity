from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd


class RollSafeMarketError(ValueError):
    """Raised when a derived roll-safe market representation is invalid."""


_REQUIRED_RAW = (
    "trade_date",
    "contract_id",
    "expiration",
    "available_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
_REQUIRED_SELECTED = (
    "trade_date",
    "contract_id",
    "expiration",
    "available_at",
    "roll_reason",
)
_TIMESTAMP_COLUMNS = ("trade_date", "expiration", "available_at")


def _utc(value: Any, label: str) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(timestamp):
        raise RollSafeMarketError(f"{label} must be a valid timestamp")
    return pd.Timestamp(timestamp)


def _normalize(frame: pd.DataFrame, required: tuple[str, ...], label: str) -> pd.DataFrame:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise RollSafeMarketError(f"{label} is missing columns: {missing}")
    out = frame.copy()
    for column in _TIMESTAMP_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], utc=True, errors="coerce")
            if out[column].isna().any():
                raise RollSafeMarketError(f"{label} contains invalid {column}")
    if (out["contract_id"].astype(str).str.strip() == "").any():
        raise RollSafeMarketError(f"{label} contains empty contract_id")
    return out


def _source_row_sha256(row: pd.Series) -> str:
    payload: dict[str, Any] = {}
    for column in _REQUIRED_RAW:
        value = row[column]
        if column in _TIMESTAMP_COLUMNS:
            payload[column] = pd.Timestamp(value).isoformat()
        elif column == "contract_id":
            payload[column] = str(value)
        else:
            payload[column] = float(value)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_same_contract_model_context(
    canonical_rows: pd.DataFrame,
    selected_path: pd.DataFrame,
    prediction_time: Any,
    *,
    max_context: int = 512,
) -> pd.DataFrame:
    """Derive PIT-safe history for only the contract selected at the cutoff."""
    if max_context < 1 or max_context > 512:
        raise RollSafeMarketError("max_context must be between 1 and 512")
    raw = _normalize(canonical_rows, _REQUIRED_RAW, "canonical rows")
    selected = _normalize(selected_path, _REQUIRED_SELECTED, "selected path")
    if raw.duplicated(["trade_date", "contract_id"]).any():
        raise RollSafeMarketError("canonical rows must be unique by trade_date and contract_id")
    if selected["trade_date"].duplicated().any():
        raise RollSafeMarketError("selected path must have one row per trade_date")

    cutoff = _utc(prediction_time, "prediction_time")
    eligible_selection = selected.loc[
        (selected["available_at"] <= cutoff) & (selected["trade_date"] <= cutoff)
    ].sort_values("trade_date")
    if eligible_selection.empty:
        raise RollSafeMarketError("no selected contract is available at the cutoff")
    current = eligible_selection.iloc[-1]
    contract_id = str(current["contract_id"])
    selection_date = pd.Timestamp(current["trade_date"])

    context = raw.loc[
        (raw["contract_id"].astype(str) == contract_id)
        & (raw["available_at"] <= cutoff)
        & (raw["trade_date"] <= selection_date)
    ].sort_values("trade_date").tail(max_context).copy()
    if context.empty:
        raise RollSafeMarketError("selected contract has no PIT-safe raw history")

    numeric_columns = ["open", "high", "low", "close", "volume"]
    numeric = context[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype="float64")).all():
        raise RollSafeMarketError("same-contract context contains non-finite OHLCV")
    if (numeric[["open", "high", "low", "close"]] <= 0).any().any():
        raise RollSafeMarketError("same-contract context prices must be positive")
    if (numeric["volume"] < 0).any():
        raise RollSafeMarketError("same-contract context volume must be non-negative")
    if (
        (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1)).any()
        or (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1)).any()
    ):
        raise RollSafeMarketError("same-contract context OHLC ordering is invalid")
    context.loc[:, numeric_columns] = numeric.astype("float64")
    context["selection_trade_date"] = selection_date
    context["selection_roll_reason"] = str(current["roll_reason"])
    context["source_row_sha256"] = context.apply(_source_row_sha256, axis=1)
    context["transformation"] = "same_contract_history_v1"
    return context.reset_index(drop=True)


def same_contract_selected_returns(
    canonical_rows: pd.DataFrame,
    selected_path: pd.DataFrame,
    *,
    price_col: str = "settle",
) -> pd.Series:
    """Return each selected contract against its own latest prior-session price."""
    if price_col not in canonical_rows.columns:
        raise RollSafeMarketError(f"canonical rows are missing price column: {price_col}")
    required_raw = tuple(
        dict.fromkeys(("trade_date", "contract_id", "available_at", price_col))
    )
    raw = _normalize(canonical_rows, required_raw, "canonical rows")
    selected = _normalize(selected_path, _REQUIRED_SELECTED, "selected path")
    if raw.duplicated(["trade_date", "contract_id"]).any():
        raise RollSafeMarketError("canonical rows must be unique by trade_date and contract_id")
    if selected["trade_date"].duplicated().any():
        raise RollSafeMarketError("selected path must have one row per trade_date")

    indexed: dict[str, pd.DataFrame] = {
        str(contract_id): group.sort_values("trade_date")
        for contract_id, group in raw.groupby(raw["contract_id"].astype(str))
    }
    values: list[float] = []
    dates: list[pd.Timestamp] = []
    for _, chosen in selected.sort_values("trade_date").iterrows():
        trade_date = pd.Timestamp(chosen["trade_date"])
        contract_id = str(chosen["contract_id"])
        current_available = pd.Timestamp(chosen["available_at"])
        history = indexed.get(contract_id)
        if history is None:
            raise RollSafeMarketError(f"selected contract has no canonical rows: {contract_id}")
        current_match = history[history["trade_date"] == trade_date]
        if len(current_match) != 1:
            raise RollSafeMarketError(
                f"selected contract row is missing or ambiguous: {contract_id} {trade_date.isoformat()}"
            )
        current = current_match.iloc[0]
        if pd.Timestamp(current["available_at"]) > current_available:
            raise RollSafeMarketError("selected path predates availability of its canonical source row")
        prior = history.loc[
            (history["trade_date"] < trade_date)
            & (history["available_at"] <= current_available)
        ]
        if prior.empty:
            value = float("nan")
        else:
            current_price = float(current[price_col])
            prior_price = float(prior.iloc[-1][price_col])
            if not math.isfinite(current_price) or not math.isfinite(prior_price):
                raise RollSafeMarketError("same-contract return prices must be finite")
            if current_price <= 0 or prior_price <= 0:
                raise RollSafeMarketError("same-contract return prices must be positive")
            value = float(np.log(current_price / prior_price))
        dates.append(trade_date)
        values.append(value)
    return pd.Series(values, index=pd.DatetimeIndex(dates), name=f"{price_col}_feature_log_return")
