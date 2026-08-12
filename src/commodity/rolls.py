from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from commodity.market_data import DataContractViolation, validate_contract_history


def _require_policy(policy: dict[str, Any]) -> tuple[int, int]:
    if policy.get("method") != "dual_liquidity_crossover":
        raise ValueError("Only dual_liquidity_crossover is implemented")
    required = ("confirmation_sessions", "forced_roll_days_before_expiry")
    missing = [field for field in required if field not in policy]
    if missing:
        raise ValueError(f"Roll policy missing explicit fields: {missing}")
    confirmation = int(policy["confirmation_sessions"])
    forced_days = int(policy["forced_roll_days_before_expiry"])
    if confirmation < 1 or forced_days < 0:
        raise ValueError("Roll policy values are outside valid bounds")
    return confirmation, forced_days


def build_derived_contract_path(
    frame: pd.DataFrame,
    schema: dict[str, Any],
    policy: dict[str, Any],
) -> pd.DataFrame:
    """Select one contract per session without embedding a canonical roll rule."""
    confirmation, forced_days = _require_policy(policy)
    normalized = validate_contract_history(frame, schema)
    for column in ("volume", "open_interest"):
        if column not in normalized.columns:
            raise DataContractViolation(f"Roll policy requires {column}")
    dates = list(normalized["trade_date"].drop_duplicates().sort_values())
    by_date = {date: group.set_index("contract_id") for date, group in normalized.groupby("trade_date")}
    current: str | None = None
    streak = 0
    rows: list[dict[str, object]] = []

    for index, date in enumerate(dates):
        day = normalized[normalized["trade_date"] == date].sort_values(["expiration", "contract_id"])
        active = day[day["expiration"] >= date]
        if active.empty:
            continue
        ids = list(active["contract_id"])
        reason = "hold"
        if current not in ids:
            current = ids[0]
            streak = 0
            reason = "initial_or_expired"

        current_pos = ids.index(current)
        if current_pos + 1 < len(ids):
            next_id = ids[current_pos + 1]
            current_row = active[active["contract_id"] == current].iloc[0]
            dte = int((current_row["expiration"] - date).total_seconds() // 86400)
            prior_signal = False
            if index > 0:
                previous = by_date[dates[index - 1]]
                if current in previous.index and next_id in previous.index:
                    front = previous.loc[current]
                    nxt = previous.loc[next_id]
                    values = [front["volume"], front["open_interest"], nxt["volume"], nxt["open_interest"]]
                    if all(pd.notna(value) for value in values):
                        prior_signal = bool(nxt["volume"] > front["volume"] and nxt["open_interest"] > front["open_interest"])
            streak = streak + 1 if prior_signal else 0
            if dte <= forced_days:
                current, streak, reason = next_id, 0, "forced_expiry_lead"
            elif streak >= confirmation:
                current, streak, reason = next_id, 0, "prior_session_dual_liquidity"

        selected = active[active["contract_id"] == current].iloc[0]
        row = selected.to_dict()
        row["roll_reason"] = reason
        rows.append(row)

    return pd.DataFrame(rows).reset_index(drop=True)


def within_contract_log_returns(
    path: pd.DataFrame,
    price_col: str = "settle",
) -> pd.Series:
    """Compute returns only when consecutive selected rows use the same contract."""
    required = {"trade_date", "contract_id", price_col}
    missing = sorted(required - set(path.columns))
    if missing:
        raise DataContractViolation(f"Derived contract path missing columns: {missing}")
    ordered = path.sort_values("trade_date").reset_index(drop=True)
    prices = ordered[price_col].astype(float)
    same_contract = ordered["contract_id"].eq(ordered["contract_id"].shift(1))
    returns = np.log(prices / prices.shift(1)).where(same_contract)
    returns.index = pd.DatetimeIndex(pd.to_datetime(ordered["trade_date"], utc=True))
    return returns.rename(f"{price_col}_log_return")
