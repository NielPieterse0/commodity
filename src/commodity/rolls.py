from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from commodity.market_data import DataContractViolation, validate_contract_history
from commodity.roll_policy import parse_volume_crossover_policy


def _require_policy(policy: dict[str, Any]) -> tuple[int, int]:
    method = policy.get("method")
    if method == "volume_crossover_dte_v1":
        parsed = parse_volume_crossover_policy(policy)
        return parsed.confirmation_sessions, parsed.forced_roll_days_before_expiry
    raise ValueError(f"Unsupported roll policy: {method}")


def _calendar_day_dte(expiration: pd.Timestamp, trade_date: pd.Timestamp) -> int:
    """Return roll-trigger DTE using normalized UTC calendar dates, not elapsed hours."""
    return int((expiration.normalize() - trade_date.normalize()).days)


def _prior_volume_evidence(
    previous: pd.DataFrame | None,
    current_id: str,
    next_id: str,
    *,
    decision_cutoff: pd.Timestamp,
) -> tuple[float | None, float | None]:
    if previous is None:
        return None, None
    if "available_at" not in previous.columns:
        raise DataContractViolation("Roll volume evidence requires explicit available_at")
    eligible = previous.loc[pd.to_datetime(previous["available_at"], utc=True) <= decision_cutoff]
    indexed = eligible.set_index("contract_id")
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
        "old_contract_dte": _calendar_day_dte(old_expiration, trade_date),
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
    if "available_at" not in normalized.columns:
        raise DataContractViolation("Roll policy requires explicit available_at")
    if normalized["available_at"].isna().any():
        raise DataContractViolation("Roll policy available_at may not be null")
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
        decision_cutoff = pd.to_datetime(day["available_at"], utc=True).min()
        reason = "hold"

        if current is None:
            front = active.iloc[0]
            front_id = str(front["contract_id"])
            front_expiration = pd.Timestamp(front["expiration"])
            later = active[active["expiration"] > front_expiration]
            front_dte = _calendar_day_dte(front_expiration, date)
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
            prior_current, prior_next = _prior_volume_evidence(
                previous, current, next_id, decision_cutoff=decision_cutoff
            )
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
                prior_current, prior_next = _prior_volume_evidence(
                previous, current, next_id, decision_cutoff=decision_cutoff
            )
                if streak_next != next_id:
                    streak = 0
                    streak_next = next_id
                prior_signal = (
                    prior_current is not None
                    and prior_next is not None
                    and prior_next > prior_current
                )
                streak = streak + 1 if prior_signal else 0
                dte = _calendar_day_dte(current_expiration, date)
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
