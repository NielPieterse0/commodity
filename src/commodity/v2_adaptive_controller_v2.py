from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from commodity.v2_adaptive_controller import (
    PROTECTED_START,
    AdaptiveContractError,
    comparable_state_refs,
)

MEMORY_BANK: tuple[int | str, ...] = (5, 10, 20, 40, 60, 126, 252, "expanding")
HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 20)
DIRECTIONS: tuple[str, ...] = ("long", "short")


@dataclass(frozen=True)
class ControllerConfig:
    config_id: str
    memory_profile: tuple[int | str, ...]
    comparable_weight: float
    top_k: int
    slow_cadence: int
    asymmetric: bool
    uncertainty_penalty: float = 0.5


@dataclass
class PositionState:
    exposure: float = 0.0
    entry_price: float | None = None
    entry_time: pd.Timestamp | None = None
    entry_contract_id: str | None = None
    current_contract_id: str | None = None
    edge_at_entry: float = 0.0
    equity_usd: float = 100000.0
    peak_equity_usd: float = 100000.0
    path_pnl_fraction: float = 0.0
    mfe_fraction: float = 0.0
    mae_fraction: float = 0.0
    instance_id: int = 0
    last_action: str = "FLAT"

    @property
    def direction(self) -> str:
        if self.exposure > 0:
            return "long"
        if self.exposure < 0:
            return "short"
        return "flat"

    @property
    def drawdown_fraction(self) -> float:
        if self.peak_equity_usd <= 0:
            return 1.0
        return max(0.0, (self.peak_equity_usd - self.equity_usd) / self.peak_equity_usd)


@dataclass
class CandidateReplay:
    config: ControllerConfig
    decisions: pd.DataFrame
    consequences: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)


def structural_grid(prereg: dict[str, Any]) -> list[ControllerConfig]:
    search = prereg["structural_search"]
    profiles = search["memory_profiles"]
    rows: list[ControllerConfig] = []
    for name, memories in profiles.items():
        for comparable_weight in prereg["comparable_state"]["weights"]:
            for top_k in search["top_k_specialists"]:
                for cadence in search["slow_cadence_sessions"]:
                    for asymmetric in search["asymmetric"]:
                        cid = (
                            f"mem={name}|cmp={float(comparable_weight):g}|k={int(top_k)}|"
                            f"slow={int(cadence)}|asym={int(bool(asymmetric))}"
                        )
                        rows.append(ControllerConfig(
                            config_id=cid,
                            memory_profile=tuple(memories),
                            comparable_weight=float(comparable_weight),
                            top_k=int(top_k),
                            slow_cadence=int(cadence),
                            asymmetric=bool(asymmetric),
                            uncertainty_penalty=float(search["uncertainty_penalty"]),
                        ))
    expected = int(search["expected_candidate_count"])
    if len(rows) != expected or len({row.config_id for row in rows}) != expected:
        raise AdaptiveContractError("controller-v2 structural search identity changed")
    return rows


def causal_attribute_specialists(
    state: pd.DataFrame,
    attribute_columns: list[str],
    *,
    lookback: int = 20,
    min_periods: int = 5,
) -> pd.DataFrame:
    if "decision_time" not in state:
        raise AdaptiveContractError("attribute specialists require decision_time")
    columns: dict[str, Any] = {
        "decision_time": pd.to_datetime(state["decision_time"], utc=True).to_numpy()
    }
    for column in attribute_columns:
        if column not in state:
            raise AdaptiveContractError(f"missing admissible attribute: {column}")
        values = pd.to_numeric(state[column], errors="raise").astype(float)
        prior_center = values.shift(1).rolling(int(lookback), min_periods=int(min_periods)).median()
        direct = pd.Series(0.0, index=state.index, dtype=float)
        valid = values.notna() & prior_center.notna()
        direct.loc[valid] = np.sign(values.loc[valid] - prior_center.loc[valid])
        columns[f"attr__{column}__direct"] = direct.to_numpy()
        columns[f"attr__{column}__inverse"] = (-direct).to_numpy()
    return pd.DataFrame(columns)


def _base_policy_id(specialist: str, horizon: int, direction: str) -> str:
    return f"{specialist}|h={int(horizon)}|dir={direction}"


def build_base_consequences(
    specialists: pd.DataFrame,
    path: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = HORIZONS,
    multiplier: float = 10000.0,
    capital_usd: float = 100000.0,
    cost_per_side_usd: float = 15.0,
) -> pd.DataFrame:
    if "decision_time" not in specialists or "decision_time" not in path:
        raise AdaptiveContractError("base consequence inputs require decision_time")
    specialist_names = [c for c in specialists.columns if c != "decision_time"]
    path_by_time = path.set_index(pd.to_datetime(path["decision_time"], utc=True))
    rows: list[dict[str, Any]] = []
    for specialist in specialist_names:
        raw = pd.to_numeric(specialists[specialist], errors="raise").astype(float)
        for horizon in horizons:
            move_column = f"h{int(horizon)}_move_per_mmbtu"
            available_column = f"h{int(horizon)}_outcome_available_at"
            roll_column = f"h{int(horizon)}_roll_count"
            if move_column not in path.columns or available_column not in path.columns:
                if int(horizon) != 1:
                    raise AdaptiveContractError(f"missing true forward-horizon path for h={horizon}")
                move_column = "path_move_per_mmbtu"
                available_column = "outcome_available_at"
                roll_column = ""
            for direction in DIRECTIONS:
                signal = raw.clip(lower=0.0) if direction == "long" else raw.clip(upper=0.0)
                policy_id = _base_policy_id(specialist, horizon, direction)
                for decision_time, exposure in zip(specialists["decision_time"], signal, strict=True):
                    stamp = pd.Timestamp(decision_time)
                    if stamp not in path_by_time.index:
                        continue
                    outcome = path_by_time.loc[stamp]
                    if pd.isna(outcome[move_column]) or pd.isna(outcome[available_column]):
                        continue
                    roll_count = float(outcome[roll_column]) if roll_column else 0.0
                    round_trip_turnover = 2.0 * abs(float(exposure)) * (1.0 + roll_count)
                    pnl = float(exposure) * float(outcome[move_column]) * multiplier
                    pnl -= round_trip_turnover * cost_per_side_usd
                    rows.append({
                        "decision_time": stamp,
                        "outcome_available_at": pd.Timestamp(outcome[available_column]),
                        "policy_id": policy_id,
                        "specialist": specialist,
                        "horizon": int(horizon),
                        "direction": direction,
                        "signal": float(exposure),
                        "turnover": round_trip_turnover,
                        "net_return": pnl / capital_usd,
                    })
    frame = pd.DataFrame(rows)
    frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
    frame["outcome_available_at"] = pd.to_datetime(frame["outcome_available_at"], utc=True)
    return frame.sort_values(["decision_time", "policy_id"], kind="stable").reset_index(drop=True)


def _history_stats(values: pd.Series) -> tuple[int, float, float]:
    numeric = pd.to_numeric(values, errors="raise").astype(float)
    count = len(numeric)
    if count == 0:
        return 0, 0.0, 0.0
    return count, float(numeric.mean()), float(numeric.std(ddof=0))


def effectiveness_surface_for_day(
    base_consequences: pd.DataFrame,
    decision_time: pd.Timestamp,
    comparable_refs: list[pd.Timestamp],
    *,
    memories: tuple[int | str, ...] = MEMORY_BANK,
) -> pd.DataFrame:
    stamp = pd.Timestamp(decision_time)
    prior = base_consequences.loc[
        pd.to_datetime(base_consequences["outcome_available_at"], utc=True) < stamp
    ].copy()
    refs = {pd.Timestamp(value) for value in comparable_refs}
    rows: list[dict[str, Any]] = []
    keys = ["specialist", "horizon", "direction"]
    for (specialist, horizon, direction), group in prior.groupby(keys, sort=False):
        group = group.sort_values("outcome_available_at", kind="stable")
        comparable = group.loc[group["decision_time"].isin(refs)] if refs else group.iloc[0:0]
        cmp_count, cmp_mean, cmp_std = _history_stats(comparable["net_return"])
        objective = group.tail(30)
        obj_count, obj_mean, obj_std = _history_stats(objective["net_return"])
        obj_sum = float(objective["net_return"].sum()) if obj_count else 0.0
        for memory in memories:
            sample = group if memory == "expanding" else group.tail(int(memory))
            count, mean, std = _history_stats(sample["net_return"])
            rows.append({
                "specialist": str(specialist),
                "horizon": int(horizon),
                "direction": str(direction),
                "memory": memory,
                "count": count,
                "mean_net_return": mean,
                "std_net_return": std,
                "objective_30_count": obj_count,
                "objective_30_net_return_sum": obj_sum,
                "objective_30_mean_net_return": obj_mean,
                "objective_30_std_net_return": obj_std,
                "comparable_count": cmp_count,
                "comparable_mean_net_return": cmp_mean,
                "comparable_std_net_return": cmp_std,
            })
    return pd.DataFrame(rows)


def precompute_surfaces(
    base_consequences: pd.DataFrame,
    context_state: pd.DataFrame,
    *,
    context_columns: list[str],
    k: int,
) -> tuple[dict[pd.Timestamp, pd.DataFrame], dict[pd.Timestamp, list[pd.Timestamp]]]:
    context = context_state.copy()
    context["decision_time"] = pd.to_datetime(context["decision_time"], utc=True)
    surfaces: dict[pd.Timestamp, pd.DataFrame] = {}
    refs_by_time: dict[pd.Timestamp, list[pd.Timestamp]] = {}
    for decision_time in context["decision_time"]:
        stamp = pd.Timestamp(decision_time)
        refs = comparable_state_refs(
            context[["decision_time", *context_columns]],
            stamp,
            k=int(k),
            feature_columns=context_columns,
        )
        refs_by_time[stamp] = refs
        surfaces[stamp] = effectiveness_surface_for_day(base_consequences, stamp, refs)
    return surfaces, refs_by_time


def score_surface(surface: pd.DataFrame, config: ControllerConfig) -> pd.DataFrame:
    empty_columns = [
        "specialist", "horizon", "direction", "score", "state_value",
        "uncertainty", "effective_count", "objective_30_count",
    ]
    if surface.empty:
        return pd.DataFrame(columns=empty_columns)
    sample = surface.loc[surface["memory"].isin(config.memory_profile)].copy()
    if sample.empty:
        return pd.DataFrame(columns=empty_columns)
    sample["component"] = (
        (1.0 - config.comparable_weight) * sample["mean_net_return"]
        + config.comparable_weight * sample["comparable_mean_net_return"]
    )
    sample["component_uncertainty"] = sample["std_net_return"] / np.sqrt(sample["count"].clip(lower=1))
    scored = sample.groupby(["specialist", "horizon", "direction"], as_index=False).agg(
        score=("objective_30_net_return_sum", "max"),
        state_value=("component", "mean"),
        memory_uncertainty=("component_uncertainty", "mean"),
        objective_uncertainty=("objective_30_std_net_return", lambda value: float(value.max()) / np.sqrt(30.0)),
        effective_count=("count", "max"),
        objective_30_count=("objective_30_count", "max"),
    )
    scored.loc[scored["objective_30_count"] < 30, "score"] = 0.0
    scored["uncertainty"] = scored[["memory_uncertainty", "objective_uncertainty"]].max(axis=1)
    return scored.drop(columns=["memory_uncertainty", "objective_uncertainty"])


def choose_active_families(
    scored: pd.DataFrame,
    family_by_specialist: dict[str, str],
    *,
    cap: int,
) -> tuple[str, ...]:
    if scored.empty:
        return ()
    frame = scored.copy()
    frame["family"] = frame["specialist"].map(family_by_specialist)
    family = frame.groupby("family", as_index=False)["score"].max()
    family = family.loc[family["score"] > 0.0]
    family = family.sort_values(
        ["score", "family"], ascending=[False, True], kind="stable"
    )
    return tuple(family.head(int(cap))["family"].astype(str))


def normalized_weights(frame: pd.DataFrame, *, top_k: int) -> dict[str, float]:
    ranked = frame.loc[frame["rank_score"] > 0.0].sort_values(
        ["rank_score", "specialist"], ascending=[False, True], kind="stable"
    ).head(int(top_k))
    if ranked.empty:
        return {}
    total = float(ranked["rank_score"].sum())
    if total <= 0.0:
        return {}
    return {str(row.specialist): float(row.rank_score) / total for row in ranked.itertuples(index=False)}


def opportunity_table(
    scored: pd.DataFrame,
    current_signals: pd.Series,
    family_by_specialist: dict[str, str],
    active_families: tuple[str, ...],
    config: ControllerConfig,
) -> pd.DataFrame:
    if scored.empty or not active_families:
        return pd.DataFrame()
    frame = scored.copy()
    frame["family"] = frame["specialist"].map(family_by_specialist)
    frame = frame.loc[frame["family"].isin(active_families)].copy()
    if not config.asymmetric:
        symmetric = frame.groupby(["specialist", "horizon"], as_index=False)["score"].mean()
        symmetric = symmetric.rename(columns={"score": "rank_score"})
        frame = frame.merge(symmetric, on=["specialist", "horizon"], how="left")
    else:
        frame["rank_score"] = frame["score"]
    rows: list[dict[str, Any]] = []
    for (horizon, direction), group in frame.groupby(["horizon", "direction"], sort=True):
        weights = normalized_weights(group, top_k=config.top_k)
        if not weights:
            continue
        indexed = group.set_index("specialist")
        value = sum(weights[name] * float(indexed.loc[name, "state_value"]) for name in weights)
        uncertainty = sum(weights[name] * float(indexed.loc[name, "uncertainty"]) for name in weights)
        sign = 1.0 if direction == "long" else -1.0
        support = sum(weight for name, weight in weights.items() if float(current_signals.get(name, 0.0)) * sign > 0.0)
        edge = value - config.uncertainty_penalty * uncertainty
        rows.append({
            "horizon": int(horizon),
            "direction": str(direction),
            "value": float(value),
            "uncertainty": float(uncertainty),
            "edge": float(edge),
            "support": float(support),
            "weights": weights,
        })
    return pd.DataFrame(rows)


def group_weights(
    weights: dict[str, float],
    family_by_specialist: dict[str, str],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for specialist, weight in weights.items():
        family = family_by_specialist[specialist]
        out[family] = out.get(family, 0.0) + float(weight)
    return dict(sorted(out.items()))


def transition_action(current: float, target: float) -> str:
    if current == 0.0 and target == 0.0:
        return "FLAT"
    if current == 0.0 and target != 0.0:
        return "STARTER"
    if current != 0.0 and target == 0.0:
        return "EXIT"
    if current * target < 0.0:
        return "REVERSE"
    if abs(target) > abs(current):
        return "ADD"
    if abs(target) < abs(current):
        return "REDUCE"
    return "FULL"


def mark_position(
    position: PositionState,
    *,
    mark_price: float,
    decision_time: pd.Timestamp,
    multiplier: float,
    initial_capital: float,
) -> dict[str, Any]:
    del mark_price, multiplier, initial_capital
    path_pnl = float(position.path_pnl_fraction) if position.exposure != 0.0 else 0.0
    age_sessions = 0
    if position.entry_time is not None:
        age_sessions = max(0, int((pd.Timestamp(decision_time).normalize() - position.entry_time.normalize()).days))
    return {
        "direction": position.direction,
        "exposure": float(position.exposure),
        "entry_price": position.entry_price,
        "entry_time": position.entry_time,
        "entry_contract_id": position.entry_contract_id,
        "current_contract_id": position.current_contract_id,
        "time_in_position_sessions": age_sessions,
        "unrealized_pnl_fraction": path_pnl,
        "economic_path_pnl_fraction": path_pnl,
        "mfe_to_date_fraction": float(position.mfe_fraction),
        "mae_to_date_fraction": float(position.mae_fraction),
        "position_instance_id": int(position.instance_id),
        "equity_usd": float(position.equity_usd),
        "drawdown_fraction": float(position.drawdown_fraction),
    }


def hard_exposure_limit(
    state_row: pd.Series,
    position: PositionState,
    *,
    max_abs_contracts: float,
    initial_margin_usd_per_contract: float = 5000.0,
    contract_multiplier: float = 10000.0,
    max_margin_fraction: float = 0.15,
    max_notional_leverage: float = 1.0,
    max_drawdown_fraction: float = 0.25,
) -> float:
    if position.drawdown_fraction >= float(max_drawdown_fraction):
        return 0.0
    equity = max(float(position.equity_usd), 1e-12)
    margin_cap = equity * float(max_margin_fraction) / max(float(initial_margin_usd_per_contract), 1e-12)
    price = max(abs(float(state_row.get("derived_settle_m1", 1.0))), 1e-12)
    notional_per_contract = price * float(contract_multiplier)
    leverage_cap = equity * float(max_notional_leverage) / max(notional_per_contract, 1e-12)
    return max(0.0, min(float(max_abs_contracts), margin_cap, leverage_cap))


def dynamic_target_exposure(
    opportunity: pd.Series,
    state_row: pd.Series,
    position: PositionState,
    *,
    max_abs_contracts: float,
    initial_margin_usd_per_contract: float = 5000.0,
    contract_multiplier: float = 10000.0,
    max_margin_fraction: float = 0.15,
    max_notional_leverage: float = 1.0,
    max_drawdown_fraction: float = 0.25,
) -> tuple[float, dict[str, float]]:
    edge = max(0.0, float(opportunity["edge"]))
    uncertainty = max(0.0, float(opportunity["uncertainty"]))
    confidence = edge / (edge + uncertainty + 1e-12)
    support = min(1.0, max(0.0, float(opportunity["support"])))
    current_vol = max(float(state_row.get("feature_vol_20", 0.0)), 1e-12)
    reference_vol = max(float(state_row.get("derived_prior60_vol20_median", current_vol)), 1e-12)
    vol_factor = min(1.0, max(0.4, reference_vol / current_vol))
    log_volume = float(state_row.get("feature_curve_log_volume_m1", 0.0))
    prior_volume = float(state_row.get("derived_prior20_log_volume_m1_median", log_volume))
    liquidity_factor = 1.0 if log_volume >= prior_volume else 0.75
    drawdown_factor = max(0.25, 1.0 - 2.0 * position.drawdown_fraction)
    hard_cap = hard_exposure_limit(
        state_row,
        position,
        max_abs_contracts=max_abs_contracts,
        initial_margin_usd_per_contract=initial_margin_usd_per_contract,
        contract_multiplier=contract_multiplier,
        max_margin_fraction=max_margin_fraction,
        max_notional_leverage=max_notional_leverage,
        max_drawdown_fraction=max_drawdown_fraction,
    )
    raw = hard_cap * confidence * support * vol_factor * liquidity_factor * drawdown_factor
    sized = min(hard_cap, max(0.0, round(raw * 4.0) / 4.0))
    if edge <= 0.0 or support < 0.5 or hard_cap <= 0.0:
        sized = 0.0
    sign = 1.0 if str(opportunity["direction"]) == "long" else -1.0
    return sign * sized, {
        "confidence": confidence,
        "support": support,
        "volatility_factor": vol_factor,
        "liquidity_factor": liquidity_factor,
        "drawdown_factor": drawdown_factor,
        "hard_exposure_cap": hard_cap,
        "risk_capacity": max(0.0, 1.0 - position.drawdown_fraction),
    }


def execution_turnover(
    current: float,
    target: float,
    *,
    current_contract_id: str | None,
    target_contract_id: str | None,
) -> float:
    if current != 0.0 and current_contract_id and target_contract_id and current_contract_id != target_contract_id:
        return abs(float(current)) + abs(float(target))
    return abs(float(target) - float(current))


def apply_realized_return(
    position: PositionState,
    realized_return: float,
    initial_capital: float,
    *,
    position_instance_id: int | None = None,
) -> None:
    position.equity_usd += float(realized_return) * float(initial_capital)
    position.peak_equity_usd = max(position.peak_equity_usd, position.equity_usd)
    if position_instance_id == position.instance_id and position.exposure != 0.0:
        position.path_pnl_fraction += float(realized_return)
        position.mfe_fraction = max(position.mfe_fraction, position.path_pnl_fraction)
        position.mae_fraction = min(position.mae_fraction, position.path_pnl_fraction)


def apply_fill(
    position: PositionState,
    *,
    target: float,
    fill_price: float,
    fill_time: pd.Timestamp,
    remaining_edge: float,
    contract_id: str | None = None,
) -> None:
    current = float(position.exposure)
    target = float(target)
    action = transition_action(current, target)
    if target == 0.0:
        position.entry_price = None
        position.entry_time = None
        position.entry_contract_id = None
        position.current_contract_id = None
        position.edge_at_entry = 0.0
        position.path_pnl_fraction = 0.0
        position.mfe_fraction = 0.0
        position.mae_fraction = 0.0
    elif current == 0.0 or current * target < 0.0:
        position.instance_id += 1
        position.entry_price = float(fill_price)
        position.entry_time = pd.Timestamp(fill_time)
        position.entry_contract_id = contract_id
        position.current_contract_id = contract_id
        position.edge_at_entry = float(remaining_edge)
        position.path_pnl_fraction = 0.0
        position.mfe_fraction = 0.0
        position.mae_fraction = 0.0
    else:
        position.current_contract_id = contract_id or position.current_contract_id
        if abs(target) > abs(current) and position.entry_price is not None:
            added = abs(target) - abs(current)
            position.entry_price = (
                abs(current) * float(position.entry_price) + added * float(fill_price)
            ) / abs(target)
    position.exposure = target
    position.last_action = action


def replay_candidate(
    config: ControllerConfig,
    state: pd.DataFrame,
    specialists: pd.DataFrame,
    path: pd.DataFrame,
    surfaces: dict[pd.Timestamp, pd.DataFrame],
    refs_by_time: dict[pd.Timestamp, list[pd.Timestamp]],
    family_by_specialist: dict[str, str],
    *,
    max_abs_contracts: float = 1.5,
    initial_capital: float = 100000.0,
    multiplier: float = 10000.0,
    cost_per_side: float = 15.0,
    initial_margin_usd_per_contract: float = 5000.0,
    max_margin_fraction: float = 0.15,
    max_notional_leverage: float = 1.0,
    max_drawdown_fraction: float = 0.25,
    active_family_cap: int = 6,
) -> CandidateReplay:
    state = state.copy().reset_index(drop=True)
    specialists = specialists.copy().reset_index(drop=True)
    path = path.copy().reset_index(drop=True)
    for frame in (state, specialists, path):
        frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
        if (frame["decision_time"] >= PROTECTED_START).any():
            raise AdaptiveContractError("controller-v2 crossed protected boundary")
    specialist_by_time = specialists.set_index("decision_time")
    path_by_time = path.set_index("decision_time")
    position = PositionState(equity_usd=initial_capital, peak_equity_usd=initial_capital)
    pending: list[tuple[pd.Timestamp, float, int]] = []
    decisions: list[dict[str, Any]] = []
    consequences: list[dict[str, Any]] = []
    active_families: tuple[str, ...] = ()
    for index, state_row in state.iterrows():
        decision_time = pd.Timestamp(state_row["decision_time"])
        matured = [item for item in pending if item[0] < decision_time]
        for _available_at, realized_return, instance_id in matured:
            apply_realized_return(
                position,
                realized_return,
                initial_capital,
                position_instance_id=instance_id,
            )
        pending = [item for item in pending if item[0] >= decision_time]
        mark = mark_position(
            position,
            mark_price=float(state_row["derived_settle_m1"]),
            decision_time=decision_time,
            multiplier=multiplier,
            initial_capital=initial_capital,
        )
        surface = surfaces[decision_time]
        scored = score_surface(surface, config)
        structural_update = index % config.slow_cadence == 0
        if structural_update:
            active_families = choose_active_families(
                scored, family_by_specialist, cap=active_family_cap
            )
        current_signals = specialist_by_time.loc[decision_time]
        opportunities = opportunity_table(
            scored, current_signals, family_by_specialist, active_families, config
        )
        selected: pd.Series | None = None
        if not opportunities.empty:
            viable = opportunities.loc[
                (opportunities["edge"] > 0.0) & (opportunities["support"] >= 0.5)
            ]
            if not viable.empty:
                selected = viable.sort_values(
                    ["edge", "uncertainty", "horizon", "direction"],
                    ascending=[False, True, True, True], kind="stable"
                ).iloc[0]
        target = 0.0
        sizing: dict[str, float] = {
            "confidence": 0.0, "support": 0.0, "volatility_factor": 1.0,
            "liquidity_factor": 1.0, "drawdown_factor": 1.0,
            "risk_capacity": max(0.0, 1.0 - position.drawdown_fraction),
        }
        selected_weights: dict[str, float] = {}
        selected_edge = 0.0
        selected_uncertainty = 0.0
        selected_horizon: int | None = None
        selected_direction = "flat"
        if selected is not None:
            target, sizing = dynamic_target_exposure(
                selected,
                state_row,
                position,
                max_abs_contracts=max_abs_contracts,
                initial_margin_usd_per_contract=initial_margin_usd_per_contract,
                contract_multiplier=multiplier,
                max_margin_fraction=max_margin_fraction,
                max_notional_leverage=max_notional_leverage,
                max_drawdown_fraction=max_drawdown_fraction,
            )
            selected_weights = dict(selected["weights"])
            selected_edge = float(selected["edge"])
            selected_uncertainty = float(selected["uncertainty"])
            selected_horizon = int(selected["horizon"])
            selected_direction = str(selected["direction"])
        risk_capacity = float(sizing["risk_capacity"])
        if (
            position.exposure != 0.0
            and target * position.exposure > 0.0
            and abs(target) > abs(position.exposure)
            and (selected_edge <= 0.0 or risk_capacity <= 0.0)
        ):
            target = position.exposure
        action = transition_action(position.exposure, target)
        edge_change = selected_edge - float(position.edge_at_entry)
        outcome = path_by_time.loc[decision_time]
        target_contract_id = str(outcome["fill_contract_id"])
        turnover = execution_turnover(
            position.exposure,
            target,
            current_contract_id=position.current_contract_id,
            target_contract_id=target_contract_id,
        )
        pnl = float(target) * float(outcome["path_move_per_mmbtu"]) * multiplier
        pnl -= turnover * cost_per_side
        realized_return = pnl / initial_capital
        reason = "positive_executable_edge" if target != 0.0 else "no_positive_executable_edge"
        decisions.append({
            "decision_time": decision_time,
            "config_id": config.config_id,
            "structural_update": structural_update,
            "active_families": active_families,
            "comparable_state_refs": refs_by_time[decision_time],
            "selected_horizon": selected_horizon,
            "selected_direction": selected_direction,
            "selected_weights": selected_weights,
            "selected_group_weights": group_weights(selected_weights, family_by_specialist),
            "opportunity_table": opportunities.to_dict(orient="records"),
            "remaining_edge": selected_edge,
            "edge_change_since_entry": edge_change,
            "uncertainty": selected_uncertainty,
            "sizing_inputs": sizing,
            "position_before": mark,
            "action": action,
            "target_exposure": float(target),
            "reason_code": reason,
            "planned_fill_time": pd.Timestamp(outcome["fill_timestamp"]),
            "planned_contract_id": str(outcome["fill_contract_id"]),
            "execution_fill_price_attached_post_decision": float(outcome["fill_price"]),
        })
        consequences.append({
            "decision_time": decision_time,
            "outcome_available_at": pd.Timestamp(outcome["outcome_available_at"]),
            "config_id": config.config_id,
            "signal": float(target),
            "turnover": float(turnover),
            "realized_net_return": float(realized_return),
        })
        apply_fill(
            position,
            target=float(target),
            fill_price=float(outcome["fill_price"]),
            fill_time=pd.Timestamp(outcome["fill_timestamp"]),
            remaining_edge=selected_edge,
            contract_id=target_contract_id,
        )
        pending.append((
            pd.Timestamp(outcome["outcome_available_at"]),
            float(realized_return),
            int(position.instance_id),
        ))
    decision_frame = pd.DataFrame(decisions)
    consequence_frame = pd.DataFrame(consequences)
    total_return = float(consequence_frame["realized_net_return"].sum()) if not consequence_frame.empty else 0.0
    return CandidateReplay(
        config=config,
        decisions=decision_frame,
        consequences=consequence_frame,
        summary={
            "total_net_return": total_return,
            "turnover": float(consequence_frame["turnover"].sum()) if not consequence_frame.empty else 0.0,
            "active_decisions": int(consequence_frame["signal"].ne(0.0).sum()) if not consequence_frame.empty else 0,
            "slow_structural_updates": int(decision_frame["structural_update"].sum()) if not decision_frame.empty else 0,
        },
    )


def _matured_candidate_score(
    consequences: pd.DataFrame,
    decision_time: pd.Timestamp,
    *,
    window: int,
) -> tuple[float, pd.Timestamp | None] | None:
    frame = consequences.loc[
        pd.to_datetime(consequences["outcome_available_at"], utc=True) < pd.Timestamp(decision_time)
    ].sort_values("outcome_available_at", kind="stable").tail(int(window))
    if len(frame) < int(window):
        return None
    maximum = pd.Timestamp(frame["outcome_available_at"].max())
    return float(frame["realized_net_return"].sum()), maximum


def _weighted_dict(items: list[tuple[float, dict[str, float]]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for alpha, values in items:
        for key, value in values.items():
            out[key] = out.get(key, 0.0) + float(alpha) * float(value)
    return {key: value for key, value in sorted(out.items()) if abs(value) > 1e-15}


def serializable_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): serializable_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable_value(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def serializable_state_snapshot(row: pd.Series) -> dict[str, Any]:
    return {str(key): serializable_value(value) for key, value in row.items()}


def serializable_frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [serializable_state_snapshot(pd.Series(row)) for row in frame.to_dict(orient="records")]


def run_meta_controller(
    replays: list[CandidateReplay],
    state: pd.DataFrame,
    path: pd.DataFrame,
    family_by_specialist: dict[str, str],
    *,
    specialists: pd.DataFrame,
    surfaces: dict[pd.Timestamp, pd.DataFrame],
    refs_by_time: dict[pd.Timestamp, list[pd.Timestamp]],
    objective_window: int = 30,
    ensemble_size: int = 5,
    structural_cadence: int = 10,
    max_abs_contracts: float = 1.5,
    initial_capital: float = 100000.0,
    multiplier: float = 10000.0,
    cost_per_side: float = 15.0,
    initial_margin_usd_per_contract: float = 5000.0,
    max_margin_fraction: float = 0.15,
    max_notional_leverage: float = 1.0,
    max_drawdown_fraction: float = 0.25,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    if not replays:
        raise AdaptiveContractError("meta-controller requires structural candidates")
    decision_maps = {
        replay.config.config_id: replay.decisions.set_index("decision_time") for replay in replays
    }
    consequence_maps = {replay.config.config_id: replay.consequences for replay in replays}
    path_by_time = path.set_index("decision_time")
    specialist_frame = specialists.copy()
    specialist_frame["decision_time"] = pd.to_datetime(specialist_frame["decision_time"], utc=True)
    if not specialist_frame["decision_time"].is_unique:
        raise AdaptiveContractError("meta-controller specialist archive requires unique decision_time")
    specialist_by_time = specialist_frame.set_index("decision_time")
    position = PositionState(equity_usd=initial_capital, peak_equity_usd=initial_capital)
    pending: list[tuple[pd.Timestamp, float, int]] = []
    brain: list[dict[str, Any]] = []
    consequences: list[dict[str, Any]] = []
    active_config_ids: tuple[str, ...] = ()
    last_structural_update_time: pd.Timestamp | None = None
    state = state.copy().reset_index(drop=True)
    state["decision_time"] = pd.to_datetime(state["decision_time"], utc=True)
    for index, state_row in state.iterrows():
        decision_time = pd.Timestamp(state_row["decision_time"])
        matured_actual = [item for item in pending if item[0] < decision_time]
        for _available_at, realized_return, instance_id in matured_actual:
            apply_realized_return(
                position,
                realized_return,
                initial_capital,
                position_instance_id=instance_id,
            )
        pending = [item for item in pending if item[0] >= decision_time]
        mark = mark_position(
            position,
            mark_price=float(state_row["derived_settle_m1"]),
            decision_time=decision_time,
            multiplier=multiplier,
            initial_capital=initial_capital,
        )
        if decision_time not in specialist_by_time.index:
            raise AdaptiveContractError("meta-controller specialist archive missing decision_time")
        if decision_time not in surfaces or decision_time not in refs_by_time:
            raise AdaptiveContractError("meta-controller archive inputs missing decision_time")
        eligible: list[tuple[float, str, pd.Timestamp]] = []
        candidate_objective_scores: list[dict[str, Any]] = []
        if index >= int(objective_window):
            for replay in replays:
                scored = _matured_candidate_score(
                    consequence_maps[replay.config.config_id], decision_time,
                    window=objective_window,
                )
                if scored is None:
                    continue
                score_value, used_at = scored
                positive = bool(score_value > 0.0)
                candidate_objective_scores.append({
                    "config_id": replay.config.config_id,
                    "trailing_30_net_return": float(score_value),
                    "max_outcome_available_at_used": used_at.isoformat(),
                    "positive_history": positive,
                })
                if positive:
                    eligible.append((score_value, replay.config.config_id, used_at))
        candidate_objective_scores.sort(key=lambda item: (-item["trailing_30_net_return"], item["config_id"]))
        eligible.sort(key=lambda item: (-item[0], item[1]))
        structural_update = bool(
            index >= int(objective_window)
            and (index - int(objective_window)) % int(structural_cadence) == 0
        )
        if structural_update:
            active_config_ids = tuple(item[1] for item in eligible[: int(ensemble_size)])
            last_structural_update_time = decision_time
        active_set = set(active_config_ids)
        selected = [item for item in eligible if item[1] in active_set]
        ensemble: list[dict[str, Any]] = []
        target = 0.0
        selected_weights: dict[str, float] = {}
        selected_groups: dict[str, float] = {}
        remaining_edge = 0.0
        uncertainty = 0.0
        max_used: pd.Timestamp | None = None
        if selected:
            score_total = sum(item[0] for item in selected)
            weight_items: list[tuple[float, dict[str, float]]] = []
            group_items: list[tuple[float, dict[str, float]]] = []
            for score, config_id, used_at in selected:
                alpha = score / score_total
                row = decision_maps[config_id].loc[decision_time]
                target += alpha * float(row["target_exposure"])
                remaining_edge += alpha * float(row["remaining_edge"])
                uncertainty += alpha * float(row["uncertainty"])
                weight_items.append((alpha, dict(row["selected_weights"])))
                group_items.append((alpha, dict(row["selected_group_weights"])))
                max_used = used_at if max_used is None else max(max_used, used_at)
                ensemble.append({
                    "config_id": config_id,
                    "trailing_30_net_return": float(score),
                    "blend_weight": float(alpha),
                    "candidate_target": float(row["target_exposure"]),
                    "candidate_horizon": serializable_value(row["selected_horizon"]),
                    "candidate_direction": str(row["selected_direction"]),
                    "candidate_sparse_weights": serializable_value(dict(row["selected_weights"])),
                    "candidate_group_weights": serializable_value(dict(row["selected_group_weights"])),
                    "candidate_opportunity_table": serializable_value(row["opportunity_table"]),
                    "candidate_active_families": serializable_value(row.get("active_families", ())),
                    "candidate_structural_update": bool(row.get("structural_update", False)),
                    "candidate_sizing_inputs": serializable_value(row.get("sizing_inputs", {})),
                    "candidate_position_before": serializable_value(row.get("position_before", {})),
                    "candidate_action": str(row.get("action", "UNKNOWN")),
                    "candidate_reason_code": str(row.get("reason_code", "unknown")),
                })
            selected_weights = _weighted_dict(weight_items)
            selected_groups = _weighted_dict(group_items)
            target = float(np.clip(round(target * 4.0) / 4.0, -max_abs_contracts, max_abs_contracts))
        hard_cap = hard_exposure_limit(
            state_row,
            position,
            max_abs_contracts=max_abs_contracts,
            initial_margin_usd_per_contract=initial_margin_usd_per_contract,
            contract_multiplier=multiplier,
            max_margin_fraction=max_margin_fraction,
            max_notional_leverage=max_notional_leverage,
            max_drawdown_fraction=max_drawdown_fraction,
        )
        target = float(np.clip(target, -hard_cap, hard_cap))
        outcome = path_by_time.loc[decision_time]
        target_contract_id = str(outcome["fill_contract_id"])
        turnover = execution_turnover(
            position.exposure,
            target,
            current_contract_id=position.current_contract_id,
            target_contract_id=target_contract_id,
        )
        action = transition_action(position.exposure, target)
        gross_pnl = float(target) * float(outcome["path_move_per_mmbtu"]) * multiplier
        execution_cost = turnover * cost_per_side
        realized_return = (gross_pnl - execution_cost) / initial_capital
        reason_code = "positive_prior30_ensemble" if selected else "flat_no_positive_prior30_candidate"
        current_signals = serializable_state_snapshot(specialist_by_time.loc[decision_time])
        comparable_refs = [pd.Timestamp(value).isoformat() for value in refs_by_time[decision_time]]
        brain.append({
            "decision_time": decision_time,
            "pit_state": serializable_state_snapshot(state_row),
            "specialist_signals": current_signals,
            "specialist_signal_count": len(current_signals),
            "comparable_state_refs": comparable_refs,
            "effectiveness_surface": serializable_frame_records(surfaces[decision_time]),
            "objective_window_sessions": int(objective_window),
            "candidate_objective_scores": candidate_objective_scores,
            "eligible_candidate_count": len(eligible),
            "structural_update": structural_update,
            "active_structural_configs": active_config_ids,
            "structural_state": {
                "cadence_sessions": int(structural_cadence),
                "active_config_ids": list(active_config_ids),
                "last_structural_update_time": (
                    last_structural_update_time.isoformat() if last_structural_update_time is not None else None
                ),
            },
            "adaptation_state": {
                "slow_structural_update": structural_update,
                "fast_daily_update": True,
                "ensemble_membership_held_between_slow_updates": True,
            },
            "selected_ensemble": ensemble,
            "selected_sparse_weights": selected_weights,
            "selected_group_weights": selected_groups,
            "remaining_edge": float(remaining_edge),
            "edge_change_since_entry": float(remaining_edge - position.edge_at_entry),
            "uncertainty": float(uncertainty),
            "hard_exposure_cap": float(hard_cap),
            "risk_state": {
                "hard_exposure_cap": float(hard_cap),
                "max_abs_contracts": float(max_abs_contracts),
                "max_margin_fraction": float(max_margin_fraction),
                "max_notional_leverage": float(max_notional_leverage),
                "max_drawdown_fraction": float(max_drawdown_fraction),
                "initial_margin_usd_per_contract": float(initial_margin_usd_per_contract),
                "equity_usd": float(position.equity_usd),
                "peak_equity_usd": float(position.peak_equity_usd),
                "drawdown_fraction": float(position.drawdown_fraction),
            },
            "position_before": serializable_value(mark),
            "action": action,
            "target_exposure": float(target),
            "timing_decision": "EXECUTE_EARLIEST" if turnover > 0.0 else "HOLD_NO_ORDER",
            "max_outcome_available_at_used": max_used,
            "reason_code": reason_code,
            "execution_assumptions": {
                "planned_fill_time": pd.Timestamp(outcome["fill_timestamp"]).isoformat(),
                "planned_contract_id": str(outcome["fill_contract_id"]),
                "fill_rule": "same_frozen_earliest_executable_fill_contract_as_v1",
                "fill_price_source": "attached_after_decision",
                "cost_usd_per_contract_side": float(cost_per_side),
                "contract_multiplier_mmbtu": float(multiplier),
                "roll_turnover_charged": True,
            },
        })
        consequences.append({
            "decision_time": decision_time,
            "fill_timestamp": pd.Timestamp(outcome["fill_timestamp"]),
            "fill_contract_id": str(outcome["fill_contract_id"]),
            "fill_price": float(outcome["fill_price"]),
            "outcome_available_at": pd.Timestamp(outcome["outcome_available_at"]),
            "path_move_per_mmbtu": float(outcome["path_move_per_mmbtu"]),
            "signal": float(target),
            "turnover": float(turnover),
            "gross_return": float(gross_pnl / initial_capital),
            "execution_cost_return": float(execution_cost / initial_capital),
            "realized_net_return": float(realized_return),
        })
        apply_fill(
            position,
            target=float(target),
            fill_price=float(outcome["fill_price"]),
            fill_time=pd.Timestamp(outcome["fill_timestamp"]),
            remaining_edge=float(remaining_edge),
            contract_id=target_contract_id,
        )
        pending.append((
            pd.Timestamp(outcome["outcome_available_at"]),
            float(realized_return),
            int(position.instance_id),
        ))
    brain_frame = pd.DataFrame(brain)
    consequence_frame = pd.DataFrame(consequences)
    payload = brain_frame.to_json(orient="records", date_format="iso", double_precision=15)
    freeze_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return brain_frame, consequence_frame, freeze_sha


def config_to_dict(config: ControllerConfig) -> dict[str, Any]:
    return {
        "config_id": config.config_id,
        "memory_profile": list(config.memory_profile),
        "comparable_weight": config.comparable_weight,
        "top_k": config.top_k,
        "slow_cadence": config.slow_cadence,
        "asymmetric": config.asymmetric,
        "uncertainty_penalty": config.uncertainty_penalty,
    }


def stable_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
