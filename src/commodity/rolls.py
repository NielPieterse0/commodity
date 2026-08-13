from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from commodity.market_data import DataContractViolation, validate_contract_history
from commodity.roll_policy import parse_volume_crossover_policy


def _require_dual_policy(policy: dict[str, Any]) -> tuple[int, int]:
    required = ("confirmation_sessions", "forced_roll_days_before_expiry")
    missing = [field for field in required if field not in policy]
    if missing:
        raise ValueError(f"Roll policy missing explicit fields: {missing}")
    confirmation = int(policy["confirmation_sessions"])
    forced_days = int(policy["forced_roll_days_before_expiry"])
    if confirmation < 1 or forced_days < 0:
        raise ValueError("Roll policy values are outside valid bounds")
    return confirmation, forced_days


def _require_policy(policy: dict[str, Any]) -> tuple[int, int]:
    method = policy.get("method")
    if method == "dual_liquidity_crossover":
        return _require_dual_policy(policy)
    if method == "volume_crossover_dte_v1":
        parsed = parse_volume_crossover_policy(policy)
        return parsed.confirmation_sessions, parsed.forced_roll_days_before_expiry
    raise ValueError(f"Unsupported roll policy: {method}")


def _build_dual_liquidity_path(
    frame: pd.DataFrame,
    schema: dict[str, Any],
    policy: dict[str, Any],
) -> pd.DataFrame:
    confirmation, forced_days = _require_policy(policy)
    normalized = validate_contract_history(frame, schema)
    for column in ("volume", "open_interest"):
        if column not in normalized.columns:
            raise DataContractViolation(f"Roll policy requires {column}")
    dates = list(normalized["trade_date"].drop_duplicates().sort_values())
    by_date = {
        date: group.set_index("contract_id")
        for date, group in normalized.groupby("trade_date")
    }
    current: str | None = None
    streak = 0
    rows: list[dict[str, object]] = []

    for index, date in enumerate(dates):
        day = normalized[normalized["trade_date"] == date].sort_values(
            ["expiration", "contract_id"]
        )
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
                    values = [
                        front["volume"], front["open_interest"],
                        nxt["volume"], nxt["open_interest"],
                    ]
                    if all(pd.notna(value) for value in values):
                        prior_signal = bool(
                            nxt["volume"] > front["volume"]
                            and nxt["open_interest"] > front["open_interest"]
                        )
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


def _prior_volume_evidence(
    previous: pd.DataFrame | None,
    current_id: str,
    next_id: str,
) -> tuple[float | None, float | None]:
    if previous is None:
        return None, None
    indexed = previous.set_index("contract_id")
    if current_id not in indexed.index or next_id not in indexed.index:
        return None, None
    current_volume = indexed.loc[current_id].get("volume")
    next_volume = indexed.loc[next_id].get("volume")
    current_value = None if pd.isna(current_volume) else float(current_volume)
    next_value = None if pd.isna(next_volume) else float(next_volume)
    return current_value, next_value


def _ledger_row(
    *,
    trade_date: pd.Timestamp,
    old_contract: str,
    new_contract: str,
    trigger: str,
    old_expiration: pd.Timestamp,
    prior_date: pd.Timestamp | None,
    prior_current_volume: float | None,
    prior_next_volume: float | None,
    confirmation_count: int,
    confirmation_required: int,
) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "old_contract": old_contract,
        "new_contract": new_contract,
        "trigger": trigger,
        "old_contract_dte": int((old_expiration.normalize() - trade_date.normalize()).days),
        "prior_evidence_trade_date": prior_date,
        "prior_current_volume": prior_current_volume,
        "prior_next_volume": prior_next_volume,
        "confirmation_count": confirmation_count,
        "confirmation_required": confirmation_required,
    }


def _build_volume_crossover_path(
    frame: pd.DataFrame,
    schema: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    confirmation, forced_days = _require_policy(policy)
    normalized = validate_contract_history(frame, schema)
    if "volume" not in normalized.columns:
        raise DataContractViolation("Roll policy requires volume")
    dates = list(normalized["trade_date"].drop_duplicates().sort_values())
    by_date = {
        date: group.sort_values(["expiration", "contract_id"])
        for date, group in normalized.groupby("trade_date")
    }
    current: str | None = None
    current_expiration: pd.Timestamp | None = None
    streak = 0
    streak_next: str | None = None
    rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []

    for index, date in enumerate(dates):
        day = by_date[date]
        active = day[day["expiration"] >= date].copy()
        if active.empty:
            continue
        previous_date = dates[index - 1] if index > 0 else None
        previous = by_date[previous_date] if previous_date is not None else None
        reason = "hold"

        if current is None:
            front = active.iloc[0]
            front_id = str(front["contract_id"])
            front_expiration = pd.Timestamp(front["expiration"])
            later = active[active["expiration"] > front_expiration]
            front_dte = int((front_expiration.normalize() - date.normalize()).days)
            if front_dte <= forced_days and not later.empty:
                selected = later.iloc[0]
                selected_id = str(selected["contract_id"])
                ledger_rows.append(_ledger_row(
                    trade_date=date,
                    old_contract=front_id,
                    new_contract=selected_id,
                    trigger="forced_dte",
                    old_expiration=front_expiration,
                    prior_date=None,
                    prior_current_volume=None,
                    prior_next_volume=None,
                    confirmation_count=0,
                    confirmation_required=confirmation,
                ))
                reason = "forced_dte"
            else:
                selected = front
                reason = "initial"
            current = str(selected["contract_id"])
            current_expiration = pd.Timestamp(selected["expiration"])
        elif current not in set(active["contract_id"]):
            assert current_expiration is not None
            later = active[active["expiration"] > current_expiration]
            if later.empty:
                raise DataContractViolation(
                    f"Current contract {current} is unavailable and no later eligible contract exists"
                )
            next_row = later.iloc[0]
            next_id = str(next_row["contract_id"])
            prior_current, prior_next = _prior_volume_evidence(previous, current, next_id)
            ledger_rows.append(_ledger_row(
                trade_date=date,
                old_contract=current,
                new_contract=next_id,
                trigger="contract_unavailable",
                old_expiration=current_expiration,
                prior_date=previous_date,
                prior_current_volume=prior_current,
                prior_next_volume=prior_next,
                confirmation_count=0,
                confirmation_required=confirmation,
            ))
            selected = next_row
            current = next_id
            current_expiration = pd.Timestamp(selected["expiration"])
            streak = 0
            streak_next = None
            reason = "contract_unavailable"
        else:
            current_row = active[active["contract_id"] == current].iloc[0]
            current_expiration = pd.Timestamp(current_row["expiration"])
            later = active[active["expiration"] > current_expiration]
            selected = current_row
            if later.empty:
                streak = 0
                streak_next = None
            else:
                next_row = later.iloc[0]
                next_id = str(next_row["contract_id"])
                prior_current, prior_next = _prior_volume_evidence(previous, current, next_id)
                if streak_next != next_id:
                    streak = 0
                    streak_next = next_id
                prior_signal = (
                    prior_current is not None
                    and prior_next is not None
                    and prior_next > prior_current
                )
                streak = streak + 1 if prior_signal else 0
                dte = int((current_expiration.normalize() - date.normalize()).days)
                trigger: str | None = None
                if dte <= forced_days:
                    trigger = "forced_dte"
                elif streak >= confirmation:
                    trigger = "prior_session_volume_crossover"
                if trigger is not None:
                    ledger_rows.append(_ledger_row(
                        trade_date=date,
                        old_contract=current,
                        new_contract=next_id,
                        trigger=trigger,
                        old_expiration=current_expiration,
                        prior_date=previous_date,
                        prior_current_volume=prior_current,
                        prior_next_volume=prior_next,
                        confirmation_count=streak,
                        confirmation_required=confirmation,
                    ))
                    selected = next_row
                    current = next_id
                    current_expiration = pd.Timestamp(selected["expiration"])
                    streak = 0
                    streak_next = None
                    reason = trigger

        row = selected.to_dict()
        row["roll_reason"] = reason
        rows.append(row)

    path = pd.DataFrame(rows).reset_index(drop=True)
    ledger_columns = [
        "trade_date", "old_contract", "new_contract", "trigger",
        "old_contract_dte", "prior_evidence_trade_date",
        "prior_current_volume", "prior_next_volume",
        "confirmation_count", "confirmation_required",
    ]
    ledger = pd.DataFrame(ledger_rows, columns=ledger_columns)
    return path, ledger


def build_derived_contract_path(
    frame: pd.DataFrame,
    schema: dict[str, Any],
    policy: dict[str, Any],
) -> pd.DataFrame:
    """Select one contract per observed session using an explicit roll policy."""
    method = policy.get("method")
    if method == "dual_liquidity_crossover":
        return _build_dual_liquidity_path(frame, schema, policy)
    if method == "volume_crossover_dte_v1":
        path, _ = _build_volume_crossover_path(frame, schema, policy)
        return path
    raise ValueError(f"Unsupported roll policy: {method}")


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


def build_derived_continuous_series(
    frame: pd.DataFrame,
    schema: dict[str, Any],
    policy: dict[str, Any],
    price_col: str = "settle",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a derived selected-contract series and its auditable roll ledger."""
    if policy.get("method") != "volume_crossover_dte_v1":
        raise ValueError("Continuous-series ledger requires volume_crossover_dte_v1")
    path, ledger = _build_volume_crossover_path(frame, schema, policy)
    returns = within_contract_log_returns(path, price_col=price_col)
    path[returns.name] = returns.to_numpy()
    return path, ledger
