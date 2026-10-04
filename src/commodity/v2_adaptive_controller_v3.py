from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from commodity.v2_adaptive_controller import PROTECTED_START, AdaptiveContractError
from commodity.v2_adaptive_controller_v2 import (
    MEMORY_BANK,
    choose_active_families,
    execution_turnover,
    group_weights,
    serializable_frame_records,
    serializable_state_snapshot,
    serializable_value,
)


@dataclass(frozen=True)
class SidePolicy:
    profile_id: str
    memories: tuple[int | str, ...]
    horizons: tuple[int, ...]
    top_k: int
    wait_support_floor: float
    enter_support_floor: float
    enter_confidence_floor: float
    max_vol_ratio: float
    size_scale: float
    max_hold_sessions: int
    add_edge_ratio: float
    reduce_edge_ratio: float
    reverse_edge_ratio: float
    exit_edge_floor: float


@dataclass(frozen=True)
class ControllerConfig:
    config_id: str
    long_policy: SidePolicy
    short_policy: SidePolicy
    comparable_weight: float
    slow_cadence: int
    uncertainty_penalty: float
    active_family_cap: int

    @property
    def asymmetric(self) -> bool:
        return self.long_policy.profile_id != self.short_policy.profile_id

    def policy_for(self, direction: str) -> SidePolicy:
        if direction == "long":
            return self.long_policy
        if direction == "short":
            return self.short_policy
        raise AdaptiveContractError(f"unknown direction: {direction}")


@dataclass
class PositionState:
    exposure: float = 0.0
    entry_price: float | None = None
    current_basis_price: float | None = None
    entry_time: pd.Timestamp | None = None
    entry_session_index: int | None = None
    entry_contract_id: str | None = None
    current_contract_id: str | None = None
    edge_at_entry: float = 0.0
    equity_usd: float = 100000.0
    peak_equity_usd: float = 100000.0
    marked_equity_usd: float = 100000.0
    peak_marked_equity_usd: float = 100000.0
    economic_path_pnl_fraction: float = 0.0
    mfe_fraction: float = 0.0
    mae_fraction: float = 0.0
    instance_id: int = 0
    last_action: str = "FLAT"

    @property
    def direction(self) -> str:
        if self.exposure > 0.0:
            return "long"
        if self.exposure < 0.0:
            return "short"
        return "flat"

    @property
    def drawdown_fraction(self) -> float:
        if self.peak_equity_usd <= 0.0:
            return 1.0
        return max(0.0, (self.peak_equity_usd - self.equity_usd) / self.peak_equity_usd)

    @property
    def risk_drawdown_fraction(self) -> float:
        if self.peak_marked_equity_usd <= 0.0:
            return 1.0
        return max(
            0.0,
            (self.peak_marked_equity_usd - self.marked_equity_usd)
            / self.peak_marked_equity_usd,
        )


@dataclass
class CandidateReplay:
    config: ControllerConfig
    decisions: pd.DataFrame
    consequences: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)


def _side_policy(profile_id: str, payload: dict[str, Any]) -> SidePolicy:
    return SidePolicy(
        profile_id=str(profile_id),
        memories=tuple(payload["memories"]),
        horizons=tuple(int(value) for value in payload["horizons"]),
        top_k=int(payload["top_k"]),
        wait_support_floor=float(payload["wait_support_floor"]),
        enter_support_floor=float(payload["enter_support_floor"]),
        enter_confidence_floor=float(payload["enter_confidence_floor"]),
        max_vol_ratio=float(payload["max_vol_ratio"]),
        size_scale=float(payload["size_scale"]),
        max_hold_sessions=int(payload["max_hold_sessions"]),
        add_edge_ratio=float(payload["add_edge_ratio"]),
        reduce_edge_ratio=float(payload["reduce_edge_ratio"]),
        reverse_edge_ratio=float(payload["reverse_edge_ratio"]),
        exit_edge_floor=float(payload["exit_edge_floor"]),
    )


def structural_grid(prereg: dict[str, Any]) -> list[ControllerConfig]:
    profiles = {
        name: _side_policy(name, payload)
        for name, payload in prereg["side_policy_profiles"].items()
    }
    search = prereg["structural_search"]
    rows: list[ControllerConfig] = []
    for long_name, long_policy in profiles.items():
        for short_name, short_policy in profiles.items():
            for comparable_weight in search["comparable_state_weights"]:
                for cadence in search["slow_cadence_sessions"]:
                    config_id = (
                        f"long={long_name}|short={short_name}|cmp={float(comparable_weight):g}|"
                        f"slow={int(cadence)}"
                    )
                    rows.append(ControllerConfig(
                        config_id=config_id,
                        long_policy=long_policy,
                        short_policy=short_policy,
                        comparable_weight=float(comparable_weight),
                        slow_cadence=int(cadence),
                        uncertainty_penalty=float(search["uncertainty_penalty"]),
                        active_family_cap=int(search["active_family_cap"]),
                    ))
    expected = int(search["expected_candidate_count"])
    if len(rows) != expected or len({row.config_id for row in rows}) != expected:
        raise AdaptiveContractError("controller-v3 structural search identity changed")
    return rows

def score_surface_for_side(
    surface: pd.DataFrame,
    config: ControllerConfig,
    direction: str,
) -> pd.DataFrame:
    policy = config.policy_for(direction)
    if surface.empty:
        return pd.DataFrame()
    sample = surface.loc[
        surface["horizon"].isin(policy.horizons)
        & surface["direction"].eq(direction)
    ].copy()
    if sample.empty:
        return pd.DataFrame()
    sample["state_component"] = (
        (1.0 - config.comparable_weight) * sample["mean_net_return"]
        + config.comparable_weight * sample["comparable_mean_net_return"]
    )
    sample["memory_uncertainty"] = (
        sample["std_net_return"] / np.sqrt(sample["count"].clip(lower=1))
    )
    neutral = pd.Series(1.0, index=sample.index, dtype=float)
    hit = pd.to_numeric(sample["direction_hit_rate"], errors="coerce") if "direction_hit_rate" in sample else None
    hit_multiplier = neutral if hit is None else (0.5 + hit).clip(lower=0.5, upper=1.5).fillna(1.0)
    mae = pd.to_numeric(sample["forecast_mae_return"], errors="coerce") if "forecast_mae_return" in sample else None
    mae_multiplier = neutral if mae is None else (1.0 / (1.0 + 10.0 * mae.clip(lower=0.0))).fillna(1.0)
    coverage = pd.to_numeric(sample["interval_coverage"], errors="coerce") if "interval_coverage" in sample else None
    calibration_multiplier = neutral if coverage is None else (1.0 - (coverage - 0.80).abs()).clip(lower=0.5, upper=1.0).fillna(1.0)
    sample["diagnostic_reliability"] = hit_multiplier * mae_multiplier * calibration_multiplier
    sample["memory_selection_score"] = (
        sample["diagnostic_reliability"] * sample["state_component"]
        - config.uncertainty_penalty * sample["memory_uncertainty"]
    )
    memory_order = {str(memory): index for index, memory in enumerate(MEMORY_BANK)}
    sample["profile_memory_preferred"] = sample["memory"].isin(policy.memories).astype(int)
    sample["memory_order"] = sample["memory"].map(
        lambda value: memory_order.get(str(value), len(memory_order))
    )
    memory_keys = ["specialist", "horizon", "direction"]
    sample["memory_count"] = sample.groupby(memory_keys)["memory"].transform("size")
    sample = sample.sort_values(
        [
            "specialist", "horizon", "direction", "memory_selection_score",
            "profile_memory_preferred", "count", "memory_order",
        ],
        ascending=[True, True, True, False, False, False, True],
        kind="stable",
    )
    scored = sample.groupby(memory_keys, as_index=False, sort=False).head(1).copy()
    scored["rank_score"] = (
        scored["objective_30_net_return_sum"] * scored["diagnostic_reliability"]
    )
    scored.loc[scored["objective_30_count"] < 30, "rank_score"] = 0.0
    scored["objective_uncertainty"] = (
        scored["objective_30_std_net_return"]
        / np.sqrt(scored["objective_30_count"].clip(lower=1))
    )
    scored["uncertainty"] = scored[["memory_uncertainty", "objective_uncertainty"]].max(axis=1)
    scored["state_value"] = scored["state_component"]
    scored["selected_memory"] = scored["memory"]
    scored["memory_weights"] = scored["selected_memory"].map(
        lambda value: {str(value): 1.0}
    )
    scored["memory_bank"] = [list(MEMORY_BANK)] * len(scored)
    scored["memory_profile"] = [list(policy.memories)] * len(scored)
    return scored.drop(columns=[
        "memory_uncertainty", "objective_uncertainty", "state_component",
        "profile_memory_preferred", "memory_order",
    ])


def _normalized_weights(frame: pd.DataFrame, top_k: int) -> dict[str, float]:
    ranked = frame.loc[frame["rank_score"] > 0.0].sort_values(
        ["rank_score", "specialist"], ascending=[False, True], kind="stable"
    ).head(int(top_k))
    if ranked.empty:
        return {}
    total = float(ranked["rank_score"].sum())
    if total <= 0.0:
        return {}
    return {
        str(row.specialist): float(row.rank_score) / total
        for row in ranked.itertuples(index=False)
    }


def opportunity_table(
    surface: pd.DataFrame,
    current_signals: pd.Series,
    family_by_specialist: dict[str, str],
    active_families: tuple[str, ...],
    config: ControllerConfig,
    *,
    horizon_signal_overrides: dict[int, dict[str, float]] | None = None,
) -> pd.DataFrame:
    if surface.empty or not active_families:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for direction in ("long", "short"):
        policy = config.policy_for(direction)
        scored = score_surface_for_side(surface, config, direction)
        if scored.empty:
            continue
        scored["family"] = scored["specialist"].map(family_by_specialist)
        scored = scored.loc[scored["family"].isin(active_families)].copy()
        for horizon, group in scored.groupby("horizon", sort=True):
            weights = _normalized_weights(group, policy.top_k)
            if not weights:
                continue
            indexed = group.set_index("specialist")
            value = sum(
                weights[name] * float(indexed.loc[name, "state_value"])
                for name in weights
            )
            uncertainty = sum(
                weights[name] * float(indexed.loc[name, "uncertainty"])
                for name in weights
            )
            sign = 1.0 if direction == "long" else -1.0
            horizon_signals = (
                horizon_signal_overrides.get(int(horizon), {})
                if horizon_signal_overrides is not None else {}
            )
            support = sum(
                weight for name, weight in weights.items()
                if float(horizon_signals.get(name, current_signals.get(name, 0.0))) * sign > 0.0
            )
            edge = value - config.uncertainty_penalty * uncertainty
            confidence = max(0.0, edge) / (max(0.0, edge) + uncertainty + 1e-12)
            rows.append({
                "horizon": int(horizon), "direction": direction,
                "value": float(value), "uncertainty": float(uncertainty),
                "edge": float(edge), "confidence": float(confidence),
                "support": float(support), "weights": weights,
                "selected_memories": {
                    name: indexed.loc[name, "selected_memory"] for name in weights
                },
                "memory_weights_by_specialist": {
                    name: dict(indexed.loc[name, "memory_weights"]) for name in weights
                },
                "memory_bank": list(MEMORY_BANK),
                "memory_profile": list(policy.memories), "profile_id": policy.profile_id,
            })
    return pd.DataFrame(rows)

def transition_action(current: float, target: float) -> str:
    if current == 0.0 and target == 0.0:
        return "FLAT"
    if current == 0.0:
        return "STARTER"
    if target == 0.0:
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
    decision_index: int,
    multiplier: float,
    initial_capital: float,
    mark_observation_time: pd.Timestamp | None = None,
    update_extrema: bool = True,
) -> dict[str, Any]:
    mtm = 0.0
    mark_valid = True
    mark_rejection_reason: str | None = None
    if (
        position.exposure != 0.0
        and position.entry_time is not None
        and mark_observation_time is not None
        and pd.Timestamp(mark_observation_time) < pd.Timestamp(position.entry_time)
    ):
        mark_valid = False
        mark_rejection_reason = "mark_observation_precedes_position_entry"
    if (
        mark_valid
        and position.exposure != 0.0
        and position.current_basis_price is not None
    ):
        mtm = (
            float(position.exposure)
            * (float(mark_price) - float(position.current_basis_price))
            * float(multiplier) / float(initial_capital)
        )
    trade_path_mark = float(position.economic_path_pnl_fraction) + float(mtm)
    position.marked_equity_usd = float(position.equity_usd) + float(mtm) * float(initial_capital)
    position.peak_marked_equity_usd = max(
        float(position.peak_marked_equity_usd), float(position.marked_equity_usd)
    )
    if update_extrema and position.exposure != 0.0 and mark_valid:
        position.mfe_fraction = max(float(position.mfe_fraction), trade_path_mark)
        position.mae_fraction = min(float(position.mae_fraction), trade_path_mark)
    age = 0 if position.entry_session_index is None else max(
        0, int(decision_index) - int(position.entry_session_index)
    )
    return {
        "direction": position.direction,
        "exposure": float(position.exposure),
        "entry_price": position.entry_price,
        "current_execution_basis_price": position.current_basis_price,
        "entry_time": position.entry_time,
        "entry_contract_id": position.entry_contract_id,
        "current_contract_id": position.current_contract_id,
        "time_in_position_sessions": age,
        "edge_at_entry": float(position.edge_at_entry),
        "unrealized_pnl_fraction": trade_path_mark,
        "current_contract_mtm_fraction": float(mtm),
        "economic_path_pnl_fraction": float(position.economic_path_pnl_fraction),
        "mfe_to_date_fraction": float(position.mfe_fraction),
        "mae_to_date_fraction": float(position.mae_fraction),
        "position_instance_id": int(position.instance_id),
        "mark_observation_time": (
            pd.Timestamp(mark_observation_time) if mark_observation_time is not None else None
        ),
        "mark_valid_for_position": bool(mark_valid),
        "mark_rejection_reason": mark_rejection_reason,
        "equity_usd": float(position.equity_usd),
        "peak_equity_usd": float(position.peak_equity_usd),
        "marked_equity_usd": float(position.marked_equity_usd),
        "peak_marked_equity_usd": float(position.peak_marked_equity_usd),
        "drawdown_fraction": float(position.drawdown_fraction),
        "risk_drawdown_fraction": float(position.risk_drawdown_fraction),
        "decision_time": pd.Timestamp(decision_time),
    }


def hard_exposure_limit(
    state_row: pd.Series,
    position: PositionState,
    *,
    max_abs_contracts: float,
    initial_margin_usd_per_contract: float,
    contract_multiplier: float,
    max_margin_fraction: float,
    max_notional_leverage: float,
    max_drawdown_fraction: float,
    execution_price: float | None = None,
) -> float:
    if position.risk_drawdown_fraction >= max_drawdown_fraction:
        return 0.0
    equity = max(float(position.marked_equity_usd), 1e-12)
    margin_cap = equity * max_margin_fraction / max(initial_margin_usd_per_contract, 1e-12)
    raw_price = (
        execution_price
        if execution_price is not None
        else state_row.get("derived_settle_m1", 1.0)
    )
    price = max(abs(float(raw_price)), 1e-12)
    leverage_cap = equity * max_notional_leverage / max(price * contract_multiplier, 1e-12)
    return max(0.0, min(float(max_abs_contracts), margin_cap, leverage_cap))


def enforce_execution_hard_cap(
    target: float,
    state_row: pd.Series,
    position: PositionState,
    *,
    fill_price: float,
    max_abs_contracts: float,
    initial_margin_usd_per_contract: float,
    contract_multiplier: float,
    max_margin_fraction: float,
    max_notional_leverage: float,
    max_drawdown_fraction: float,
) -> tuple[float, float]:
    cap = hard_exposure_limit(
        state_row,
        position,
        max_abs_contracts=max_abs_contracts,
        initial_margin_usd_per_contract=initial_margin_usd_per_contract,
        contract_multiplier=contract_multiplier,
        max_margin_fraction=max_margin_fraction,
        max_notional_leverage=max_notional_leverage,
        max_drawdown_fraction=max_drawdown_fraction,
        execution_price=float(fill_price),
    )
    signed = np.sign(float(target)) * min(abs(float(target)), float(cap))
    return float(signed), float(cap)


def dynamic_target_exposure(
    opportunity: pd.Series,
    state_row: pd.Series,
    position: PositionState,
    side_policy: SidePolicy,
    *,
    max_abs_contracts: float,
    initial_margin_usd_per_contract: float,
    contract_multiplier: float,
    max_margin_fraction: float,
    max_notional_leverage: float,
    max_drawdown_fraction: float,
) -> tuple[float, dict[str, float]]:
    edge = max(0.0, float(opportunity["edge"]))
    uncertainty = max(0.0, float(opportunity["uncertainty"]))
    confidence = edge / (edge + uncertainty + 1e-12)
    support = float(np.clip(float(opportunity["support"]), 0.0, 1.0))
    current_vol = max(float(state_row.get("feature_vol_20", 0.0)), 1e-12)
    reference_vol = max(float(state_row.get("derived_prior60_vol20_median", current_vol)), 1e-12)
    vol_ratio = current_vol / reference_vol
    volatility_factor = float(np.clip(reference_vol / current_vol, 0.35, 1.0))
    log_volume = float(state_row.get("feature_curve_log_volume_m1", 0.0))
    prior_volume = float(state_row.get("derived_prior20_log_volume_m1_median", log_volume))
    liquidity_factor = 1.0 if log_volume >= prior_volume else 0.75
    drawdown_factor = max(0.20, 1.0 - 2.0 * position.risk_drawdown_fraction)
    regime_quality = volatility_factor if vol_ratio <= side_policy.max_vol_ratio else 0.0
    hard_cap = hard_exposure_limit(
        state_row, position, max_abs_contracts=max_abs_contracts,
        initial_margin_usd_per_contract=initial_margin_usd_per_contract,
        contract_multiplier=contract_multiplier, max_margin_fraction=max_margin_fraction,
        max_notional_leverage=max_notional_leverage,
        max_drawdown_fraction=max_drawdown_fraction,
    )
    raw = (
        hard_cap * confidence * support * regime_quality * liquidity_factor
        * drawdown_factor * float(side_policy.size_scale)
    )
    sized = min(hard_cap, max(0.0, round(raw * 4.0) / 4.0))
    if edge <= 0.0 or hard_cap <= 0.0:
        sized = 0.0
    sign = 1.0 if str(opportunity["direction"]) == "long" else -1.0
    return sign * sized, {
        "estimated_edge": edge,
        "confidence": confidence,
        "support": support,
        "regime_quality": regime_quality,
        "volatility_factor": volatility_factor,
        "volatility_ratio": vol_ratio,
        "liquidity_factor": liquidity_factor,
        "drawdown_factor": drawdown_factor,
        "side_size_scale": float(side_policy.size_scale),
        "hard_exposure_cap": hard_cap,
        "risk_capacity": max(0.0, 1.0 - position.risk_drawdown_fraction),
    }


def timing_entry_decision(
    opportunity: pd.Series,
    state_row: pd.Series,
    policy: SidePolicy,
) -> str:
    edge = float(opportunity["edge"])
    support = float(opportunity["support"])
    confidence = float(opportunity["confidence"])
    current_vol = max(float(state_row.get("feature_vol_20", 0.0)), 1e-12)
    reference_vol = max(float(state_row.get("derived_prior60_vol20_median", current_vol)), 1e-12)
    vol_ratio = current_vol / reference_vol
    if edge <= 0.0 or support < policy.wait_support_floor:
        return "ABSTAIN"
    if support < policy.enter_support_floor or confidence < policy.enter_confidence_floor:
        return "WAIT"
    if vol_ratio > policy.max_vol_ratio:
        return "WAIT"
    return "ENTER_NOW"

def select_timed_opportunity(
    opportunities: pd.DataFrame,
    state_row: pd.Series,
    config: ControllerConfig,
) -> tuple[pd.Series | None, str]:
    if opportunities.empty:
        return None, "ABSTAIN"
    evaluated: list[tuple[int, float, float, int, str, pd.Series, str]] = []
    priority = {"ENTER_NOW": 2, "WAIT": 1, "ABSTAIN": 0}
    for _, row in opportunities.iterrows():
        policy = config.policy_for(str(row["direction"]))
        timing = timing_entry_decision(row, state_row, policy)
        evaluated.append((
            priority[timing], float(row["edge"]), -float(row["uncertainty"]),
            -int(row["horizon"]), str(row["direction"]), row, timing,
        ))
    best = max(evaluated, key=lambda item: item[:5])
    if best[0] == 0:
        return None, "ABSTAIN"
    return best[5], best[6]


def lifecycle_target(
    position: PositionState,
    selected: pd.Series | None,
    timing: str,
    desired_target: float,
    mark: dict[str, Any],
    config: ControllerConfig,
    *,
    risk_capacity: float,
    hard_exposure_cap: float | None = None,
) -> tuple[float, str]:
    current = float(position.exposure)
    if selected is None:
        return 0.0, "no_positive_remaining_edge"
    direction = str(selected["direction"])
    policy = config.policy_for(direction)
    edge = float(selected["edge"])
    if current == 0.0:
        if timing != "ENTER_NOW":
            return 0.0, f"entry_{timing.lower()}"
        return float(desired_target), "starter_positive_edge"
    same_side = (current > 0.0 and direction == "long") or (current < 0.0 and direction == "short")
    if not same_side:
        if timing != "ENTER_NOW":
            return 0.0, "exit_wait_before_reverse"
        required = max(0.0, abs(float(position.edge_at_entry)) * policy.reverse_edge_ratio)
        if edge < required:
            return 0.0, "exit_reverse_edge_insufficient"
        return float(desired_target), "reverse_stronger_future_edge"
    if edge <= policy.exit_edge_floor:
        return 0.0, "exit_remaining_edge_nonpositive"
    age = int(mark["time_in_position_sessions"])
    if age >= policy.max_hold_sessions and edge <= max(float(position.edge_at_entry), 0.0):
        return 0.0, "exit_max_hold_without_edge_improvement"
    effective_hard_cap = (
        float(hard_exposure_cap) if hard_exposure_cap is not None else float("inf")
    )
    if effective_hard_cap < abs(current) - 1e-12:
        capped = np.sign(current) * min(abs(float(desired_target)), max(0.0, effective_hard_cap))
        return float(capped), "reduce_hard_risk_cap"
    if timing == "WAIT":
        return current, "hold_wait_for_entry_quality"
    target = float(desired_target)
    if abs(target) > abs(current):
        required = max(0.0, float(position.edge_at_entry) * policy.add_edge_ratio)
        if edge < required or risk_capacity <= 0.0:
            return current, "hold_add_requires_future_marginal_edge"
        return target, "add_future_marginal_edge_and_capacity"
    if abs(target) < abs(current):
        effective_hard_cap = (
            float(hard_exposure_cap) if hard_exposure_cap is not None else float("inf")
        )
        if effective_hard_cap < abs(current) - 1e-12:
            capped = np.sign(current) * min(abs(target), max(0.0, effective_hard_cap))
            return float(capped), "reduce_hard_risk_cap"
        deterioration_level = max(0.0, float(position.edge_at_entry) * policy.reduce_edge_ratio)
        if edge < deterioration_level:
            return target, "reduce_edge_deterioration"
        return current, "hold_reduction_requires_edge_or_hard_risk_deterioration"
    return target, "hold_or_full_positive_remaining_edge"


def apply_realized_return(
    position: PositionState,
    realized_return: float,
    initial_capital: float,
    *,
    position_instance_id: int | None = None,
    terminal_basis_price: float | None = None,
    contract_id: str | None = None,
) -> None:
    pnl_usd = float(realized_return) * float(initial_capital)
    position.equity_usd += pnl_usd
    position.peak_equity_usd = max(position.peak_equity_usd, position.equity_usd)
    position.marked_equity_usd += pnl_usd
    position.peak_marked_equity_usd = max(
        position.peak_marked_equity_usd, position.marked_equity_usd
    )
    same_instance = position_instance_id == position.instance_id and position.exposure != 0.0
    if same_instance:
        position.economic_path_pnl_fraction += float(realized_return)
        if terminal_basis_price is not None and contract_id is not None:
            position.current_basis_price = float(terminal_basis_price)
            position.current_contract_id = str(contract_id)


def apply_fill(
    position: PositionState,
    *,
    target: float,
    fill_price: float,
    fill_time: pd.Timestamp,
    decision_index: int,
    remaining_edge: float,
    contract_id: str | None = None,
) -> None:
    current = float(position.exposure)
    target = float(target)
    action = transition_action(current, target)
    rolled = bool(
        current != 0.0 and contract_id is not None
        and position.current_contract_id is not None
        and str(contract_id) != str(position.current_contract_id)
    )
    if target == 0.0:
        position.entry_price = None
        position.current_basis_price = None
        position.entry_time = None
        position.entry_session_index = None
        position.entry_contract_id = None
        position.current_contract_id = None
        position.edge_at_entry = 0.0
        position.economic_path_pnl_fraction = 0.0
        position.mfe_fraction = 0.0
        position.mae_fraction = 0.0
    elif current == 0.0 or current * target < 0.0:
        position.instance_id += 1
        position.entry_price = float(fill_price)
        position.current_basis_price = float(fill_price)
        position.entry_time = pd.Timestamp(fill_time)
        position.entry_session_index = int(decision_index)
        position.entry_contract_id = contract_id
        position.current_contract_id = contract_id
        position.edge_at_entry = float(remaining_edge)
        position.economic_path_pnl_fraction = 0.0
        position.mfe_fraction = 0.0
        position.mae_fraction = 0.0
    else:
        if rolled:
            position.current_basis_price = float(fill_price)
            position.current_contract_id = contract_id
        elif abs(target) > abs(current) and position.current_basis_price is not None:
            added = abs(target) - abs(current)
            position.current_basis_price = (
                abs(current) * float(position.current_basis_price) + added * float(fill_price)
            ) / abs(target)
        elif contract_id is not None:
            position.current_contract_id = contract_id
    position.exposure = target
    position.last_action = action


def _execution_adjusted_target(
    current: float,
    target: float,
    state_row: pd.Series,
    *,
    miss_increase_when_below_prior_volume: bool,
) -> tuple[float, bool]:
    if not miss_increase_when_below_prior_volume:
        return float(target), False
    low_liquidity = float(state_row.get("feature_curve_log_volume_m1", 0.0)) < float(
        state_row.get("derived_prior20_log_volume_m1_median", 0.0)
    )
    if not low_liquidity:
        return float(target), False
    current = float(current)
    target = float(target)
    if current == 0.0 and target != 0.0:
        return 0.0, True
    if current * target < 0.0:
        return 0.0, True
    if current * target > 0.0 and abs(target) > abs(current):
        return current, True
    return target, False


def _active_family_candidates(
    surface: pd.DataFrame,
    config: ControllerConfig,
    family_by_specialist: dict[str, str],
) -> pd.DataFrame:
    parts = [score_surface_for_side(surface, config, direction) for direction in ("long", "short")]
    parts = [part for part in parts if not part.empty]
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def replay_candidate(
    config: ControllerConfig,
    state: pd.DataFrame,
    specialists: pd.DataFrame,
    path: pd.DataFrame,
    surfaces: dict[pd.Timestamp, pd.DataFrame],
    refs_by_time: dict[pd.Timestamp, list[pd.Timestamp]],
    family_by_specialist: dict[str, str],
    *,
    execution_scenario: dict[str, Any],
    horizon_signals_by_time: dict[pd.Timestamp, dict[int, dict[str, float]]] | None = None,
    max_abs_contracts: float = 1.5,
    initial_capital: float = 100000.0,
    multiplier: float = 10000.0,
    base_cost_per_side: float = 15.0,
    initial_margin_usd_per_contract: float = 5000.0,
    max_margin_fraction: float = 0.15,
    max_notional_leverage: float = 1.0,
    max_drawdown_fraction: float = 0.25,
) -> CandidateReplay:
    state = state.copy().reset_index(drop=True)
    specialists = specialists.copy().reset_index(drop=True)
    path = path.copy().reset_index(drop=True)
    for frame in (state, specialists, path):
        frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
        if (frame["decision_time"] >= PROTECTED_START).any():
            raise AdaptiveContractError("controller-v3 crossed protected boundary")
    if not state["decision_time"].is_unique:
        raise AdaptiveContractError("controller-v3 state requires unique decision_time")
    specialist_by_time = specialists.set_index("decision_time")
    path_by_time = path.set_index("decision_time")
    position = PositionState(
        equity_usd=initial_capital,
        peak_equity_usd=initial_capital,
        marked_equity_usd=initial_capital,
        peak_marked_equity_usd=initial_capital,
    )
    pending: list[tuple[pd.Timestamp, float, int, float, str]] = []
    decisions: list[dict[str, Any]] = []
    consequences: list[dict[str, Any]] = []
    active_families: tuple[str, ...] = ()
    extra_slippage = float(execution_scenario.get("extra_slippage_usd_per_contract_side", 0.0))
    miss_low_liquidity = bool(execution_scenario.get("miss_increase_when_below_prior_volume", False))
    scenario_id = str(execution_scenario["id"])
    for index, state_row in state.iterrows():
        decision_time = pd.Timestamp(state_row["decision_time"])
        matured = [item for item in pending if item[0] < decision_time]
        for _available_at, realized_return, instance_id, terminal_basis, contract_id in matured:
            apply_realized_return(
                position, realized_return, initial_capital,
                position_instance_id=instance_id,
                terminal_basis_price=terminal_basis,
                contract_id=contract_id,
            )
        pending = [item for item in pending if item[0] >= decision_time]
        mark = mark_position(
            position, mark_price=float(state_row["derived_settle_m1"]),
            decision_time=decision_time, decision_index=index,
            multiplier=multiplier, initial_capital=initial_capital,
            mark_observation_time=(
                pd.Timestamp(state_row["market_observation_time"])
                if "market_observation_time" in state_row.index
                and pd.notna(state_row["market_observation_time"])
                else None
            ),
        )
        surface = surfaces[decision_time]
        structural_update = index % config.slow_cadence == 0
        if structural_update:
            family_scores = _active_family_candidates(surface, config, family_by_specialist)
            active_families = choose_active_families(
                family_scores.rename(columns={"rank_score": "score"}),
                family_by_specialist,
                cap=config.active_family_cap,
            ) if not family_scores.empty else ()
        current_signals = specialist_by_time.loc[decision_time]
        opportunities = opportunity_table(
            surface, current_signals, family_by_specialist, active_families, config,
            horizon_signal_overrides=(
                horizon_signals_by_time.get(decision_time, {})
                if horizon_signals_by_time is not None else None
            ),
        )
        selected, timing = select_timed_opportunity(opportunities, state_row, config)
        desired_target = 0.0
        sizing: dict[str, float] = {"risk_capacity": max(0.0, 1.0 - position.drawdown_fraction)}
        selected_weights: dict[str, float] = {}
        selected_edge = 0.0
        selected_uncertainty = 0.0
        selected_horizon: int | None = None
        selected_direction = "flat"
        if selected is not None:
            side_policy = config.policy_for(str(selected["direction"]))
            desired_target, sizing = dynamic_target_exposure(
                selected, state_row, position, side_policy,
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
        target, lifecycle_reason = lifecycle_target(
            position, selected, timing, desired_target, mark, config,
            risk_capacity=float(sizing.get("risk_capacity", 0.0)),
            hard_exposure_cap=float(sizing.get("hard_exposure_cap", max_abs_contracts)),
        )
        outcome = path_by_time.loc[decision_time]
        target, missed_fill = _execution_adjusted_target(
            position.exposure, target, state_row,
            miss_increase_when_below_prior_volume=miss_low_liquidity,
        )
        target_before_execution_cap = float(target)
        target, execution_hard_cap = enforce_execution_hard_cap(
            target,
            state_row,
            position,
            fill_price=float(outcome["fill_price"]),
            max_abs_contracts=max_abs_contracts,
            initial_margin_usd_per_contract=initial_margin_usd_per_contract,
            contract_multiplier=multiplier,
            max_margin_fraction=max_margin_fraction,
            max_notional_leverage=max_notional_leverage,
            max_drawdown_fraction=max_drawdown_fraction,
        )
        if abs(target) < abs(target_before_execution_cap) - 1e-12:
            lifecycle_reason = "reduce_execution_price_hard_risk_cap"
        target_contract_id = str(outcome["fill_contract_id"])
        transition_turnover = execution_turnover(
            position.exposure, target,
            current_contract_id=position.current_contract_id,
            target_contract_id=target_contract_id,
        )
        roll_turnover = 2.0 * abs(float(target)) * float(outcome.get("holding_roll_count", 0.0))
        turnover = float(transition_turnover + roll_turnover)
        action = transition_action(position.exposure, target)
        gross_pnl = float(target) * float(outcome["holding_move_per_mmbtu"]) * multiplier
        execution_cost = turnover * (base_cost_per_side + extra_slippage)
        realized_return = (gross_pnl - execution_cost) / initial_capital
        risk_equity = max(float(position.marked_equity_usd), 1e-12)
        leverage = abs(float(target)) * float(outcome["fill_price"]) * multiplier / risk_equity
        margin_fraction = abs(float(target)) * initial_margin_usd_per_contract / risk_equity
        decisions.append({
            "decision_time": decision_time,
            "config_id": config.config_id,
            "execution_scenario": scenario_id,
            "structural_update": structural_update,
            "active_families": active_families,
            "comparable_state_refs": refs_by_time[decision_time],
            "selected_horizon": selected_horizon,
            "selected_direction": selected_direction,
            "selected_side_profile": (
                config.policy_for(selected_direction).profile_id
                if selected_direction in {"long", "short"} else None
            ),
            "selected_weights": selected_weights,
            "selected_group_weights": group_weights(selected_weights, family_by_specialist),
            "opportunity_table": opportunities.to_dict(orient="records"),
            "timing_decision": timing,
            "remaining_edge": selected_edge,
            "edge_change_since_entry": selected_edge - float(position.edge_at_entry),
            "uncertainty": selected_uncertainty,
            "sizing_inputs": {
                **sizing,
                "execution_price_hard_exposure_cap": float(execution_hard_cap),
            },
            "position_before": mark,
            "action": action,
            "target_exposure": float(target),
            "lifecycle_reason": lifecycle_reason,
            "missed_fill": missed_fill,
            "planned_fill_time": pd.Timestamp(outcome["fill_timestamp"]),
            "planned_contract_id": target_contract_id,
        })
        consequences.append({
            "decision_time": decision_time,
            "fill_timestamp": pd.Timestamp(outcome["fill_timestamp"]),
            "fill_contract_id": target_contract_id,
            "outcome_available_at": pd.Timestamp(outcome["holding_outcome_available_at"]),
            "holding_session_count": int(outcome["holding_session_count"]),
            "holding_roll_count": int(outcome["holding_roll_count"]),
            "transition_turnover": float(transition_turnover),
            "roll_turnover": float(roll_turnover),
            "config_id": config.config_id,
            "execution_scenario": scenario_id,
            "exposure_before": float(position.exposure),
            "signal": float(target),
            "turnover": float(turnover),
            "gross_return": float(gross_pnl / initial_capital),
            "execution_cost_return": float(execution_cost / initial_capital),
            "realized_net_return": float(realized_return),
            "missed_fill": missed_fill,
            "notional_leverage": float(leverage),
            "margin_fraction": float(margin_fraction),
            "action": action,
            "direction": "long" if target > 0.0 else ("short" if target < 0.0 else "flat"),
        })
        apply_fill(
            position, target=float(target), fill_price=float(outcome["fill_price"]),
            fill_time=pd.Timestamp(outcome["fill_timestamp"]), decision_index=index,
            remaining_edge=selected_edge, contract_id=target_contract_id,
        )
        pending.append((
            pd.Timestamp(outcome["holding_outcome_available_at"]),
            float(realized_return), int(position.instance_id),
            float(outcome["holding_terminal_basis_price"]),
            str(outcome["holding_terminal_contract_id"]),
        ))
    decision_frame = pd.DataFrame(decisions)
    consequence_frame = pd.DataFrame(consequences)
    return CandidateReplay(
        config=config,
        decisions=decision_frame,
        consequences=consequence_frame,
        summary={
            "execution_scenario": scenario_id,
            "total_net_return": float(consequence_frame["realized_net_return"].sum()),
            "turnover": float(consequence_frame["turnover"].sum()),
            "active_decisions": int(consequence_frame["signal"].ne(0.0).sum()),
            "missed_fill_count": int(consequence_frame["missed_fill"].sum()),
            "slow_structural_updates": int(decision_frame["structural_update"].sum()),
            "max_notional_leverage": float(consequence_frame["notional_leverage"].max()),
            "max_margin_fraction": float(consequence_frame["margin_fraction"].max()),
        },
    )


def _matured_candidate_score(
    consequences: pd.DataFrame,
    decision_time: pd.Timestamp,
    *,
    window: int,
) -> tuple[float, pd.Timestamp] | None:
    mask = pd.to_datetime(consequences["outcome_available_at"], utc=True) < pd.Timestamp(decision_time)
    frame = consequences.loc[mask].sort_values("outcome_available_at", kind="stable")
    if frame.empty:
        return None
    if "holding_session_count" in frame:
        session_counts = pd.to_numeric(frame["holding_session_count"], errors="raise").astype(int)
        if int(session_counts.sum()) < int(window):
            return None
        cumulative = session_counts.iloc[::-1].cumsum()
        rows_needed = int((cumulative < int(window)).sum()) + 1
        frame = frame.tail(rows_needed)
    else:
        frame = frame.tail(int(window))
        if len(frame) < int(window):
            return None
    maximum = pd.Timestamp(frame["outcome_available_at"].max())
    return float(frame["realized_net_return"].sum()), maximum


def causal_prior_check(brain: pd.DataFrame) -> bool:
    used = pd.to_datetime(brain["max_outcome_available_at_used"], utc=True, errors="coerce")
    decisions = pd.to_datetime(brain["decision_time"], utc=True, errors="raise")
    mask = used.notna()
    if not bool(mask.any()):
        return True
    return bool((used.loc[mask].to_numpy() < decisions.loc[mask].to_numpy()).all())

def _replay_map(replays: list[CandidateReplay]) -> dict[str, CandidateReplay]:
    mapping = {replay.config.config_id: replay for replay in replays}
    if len(mapping) != len(replays):
        raise AdaptiveContractError("duplicate controller-v3 replay config")
    return mapping


def _weighted_dict(items: list[tuple[float, dict[str, float]]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for alpha, values in items:
        for key, value in values.items():
            out[key] = out.get(key, 0.0) + float(alpha) * float(value)
    return {key: value for key, value in sorted(out.items()) if abs(value) > 1e-15}


def meta_lifecycle_inputs(
    members: list[dict[str, Any]],
    *,
    current_exposure: float,
    target_exposure: float,
) -> dict[str, Any]:
    if target_exposure > 0.0:
        lifecycle_direction = "long"
    elif target_exposure < 0.0:
        lifecycle_direction = "short"
    elif current_exposure > 0.0:
        lifecycle_direction = "long"
    elif current_exposure < 0.0:
        lifecycle_direction = "short"
    else:
        lifecycle_direction = "flat"

    directional_state: dict[str, dict[str, Any]] = {}
    for direction in ("long", "short"):
        aligned = [row for row in members if str(row["direction"]) == direction]
        weight = sum(float(row["alpha"]) for row in aligned)
        if weight <= 0.0:
            directional_state[direction] = {
                "weight": 0.0,
                "remaining_edge": 0.0,
                "uncertainty": 0.0,
                "timing_decision": "ABSTAIN",
                "add_edge_ratio": 1.0,
                "reduce_edge_ratio": 0.5,
                "reverse_edge_ratio": 1.0,
                "exit_edge_floor": 0.0,
                "max_hold_sessions": 20.0,
            }
            continue
        directional_state[direction] = {
            "weight": float(weight),
            "remaining_edge": float(sum(
                float(row["alpha"]) * float(row["edge"]) for row in aligned
            )),
            "uncertainty": float(sum(
                float(row["alpha"]) * float(row["uncertainty"]) for row in aligned
            )),
            "timing_decision": str(aligned[0]["timing"]),
            "add_edge_ratio": float(sum(
                float(row["alpha"]) * float(row["add_edge_ratio"]) for row in aligned
            ) / weight),
            "reduce_edge_ratio": float(sum(
                float(row["alpha"]) * float(row["reduce_edge_ratio"]) for row in aligned
            ) / weight),
            "reverse_edge_ratio": float(sum(
                float(row["alpha"]) * float(row["reverse_edge_ratio"]) for row in aligned
            ) / weight),
            "exit_edge_floor": float(sum(
                float(row["alpha"]) * float(row["exit_edge_floor"]) for row in aligned
            ) / weight),
            "max_hold_sessions": float(sum(
                float(row["alpha"]) * float(row["max_hold_sessions"]) for row in aligned
            ) / weight),
        }

    selected = directional_state.get(lifecycle_direction, {
        "weight": 0.0,
        "remaining_edge": 0.0,
        "uncertainty": 0.0,
        "timing_decision": "ABSTAIN",
        "add_edge_ratio": 1.0,
        "reduce_edge_ratio": 0.5,
        "reverse_edge_ratio": 1.0,
        "exit_edge_floor": 0.0,
        "max_hold_sessions": 20.0,
    })
    return {
        "lifecycle_direction": lifecycle_direction,
        "direction_weight": float(selected["weight"]),
        "remaining_edge": float(selected["remaining_edge"]),
        "uncertainty": float(selected["uncertainty"]),
        "timing_decision": str(selected["timing_decision"]),
        "add_edge_ratio": float(selected["add_edge_ratio"]),
        "reduce_edge_ratio": float(selected["reduce_edge_ratio"]),
        "reverse_edge_ratio": float(selected["reverse_edge_ratio"]),
        "exit_edge_floor": float(selected["exit_edge_floor"]),
        "max_hold_sessions": float(selected["max_hold_sessions"]),
        "directional_state": directional_state,
    }


def run_meta_controller(
    base_replays: list[CandidateReplay],
    stress_replays: dict[str, list[CandidateReplay]],
    state: pd.DataFrame,
    path: pd.DataFrame,
    *,
    specialists: pd.DataFrame,
    surfaces: dict[pd.Timestamp, pd.DataFrame],
    refs_by_time: dict[pd.Timestamp, list[pd.Timestamp]],
    objective_window: int = 30,
    ensemble_size: int = 5,
    structural_cadence: int = 10,
    stress_floor: float = -0.05,
    max_abs_contracts: float = 1.5,
    initial_capital: float = 100000.0,
    multiplier: float = 10000.0,
    cost_per_side: float = 15.0,
    initial_margin_usd_per_contract: float = 5000.0,
    max_margin_fraction: float = 0.15,
    max_notional_leverage: float = 1.0,
    max_drawdown_fraction: float = 0.25,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    if not base_replays:
        raise AdaptiveContractError("meta-controller requires structural candidates")
    base_map = _replay_map(base_replays)
    stress_maps = {name: _replay_map(rows) for name, rows in stress_replays.items()}
    if any(set(mapping) != set(base_map) for mapping in stress_maps.values()):
        raise AdaptiveContractError("execution stress replay identities differ from base")
    decision_maps = {
        config_id: replay.decisions.set_index("decision_time")
        for config_id, replay in base_map.items()
    }
    path_frame = path.copy()
    path_frame["decision_time"] = pd.to_datetime(path_frame["decision_time"], utc=True)
    path_by_time = path_frame.set_index("decision_time")
    specialist_frame = specialists.copy()
    specialist_frame["decision_time"] = pd.to_datetime(specialist_frame["decision_time"], utc=True)
    specialist_by_time = specialist_frame.set_index("decision_time")
    state = state.copy().reset_index(drop=True)
    state["decision_time"] = pd.to_datetime(state["decision_time"], utc=True)
    position = PositionState(
        equity_usd=initial_capital,
        peak_equity_usd=initial_capital,
        marked_equity_usd=initial_capital,
        peak_marked_equity_usd=initial_capital,
    )
    pending: list[tuple[pd.Timestamp, float, int, float, str]] = []
    brain: list[dict[str, Any]] = []
    consequences: list[dict[str, Any]] = []
    active_config_ids: tuple[str, ...] = ()
    last_structural_update_time: pd.Timestamp | None = None
    for index, state_row in state.iterrows():
        decision_time = pd.Timestamp(state_row["decision_time"])
        matured = [item for item in pending if item[0] < decision_time]
        for _available_at, realized_return, instance_id, terminal_basis, contract_id in matured:
            apply_realized_return(
                position, realized_return, initial_capital,
                position_instance_id=instance_id,
                terminal_basis_price=terminal_basis,
                contract_id=contract_id,
            )
        pending = [item for item in pending if item[0] >= decision_time]
        mark = mark_position(
            position, mark_price=float(state_row["derived_settle_m1"]),
            decision_time=decision_time, decision_index=index,
            multiplier=multiplier, initial_capital=initial_capital,
            mark_observation_time=(
                pd.Timestamp(state_row["market_observation_time"])
                if "market_observation_time" in state_row.index
                and pd.notna(state_row["market_observation_time"])
                else None
            ),
        )
        eligible: list[tuple[float, str, pd.Timestamp, float]] = []
        candidate_scores: list[dict[str, Any]] = []
        if index >= int(objective_window):
            for config_id, replay in base_map.items():
                base_score = _matured_candidate_score(
                    replay.consequences, decision_time, window=objective_window
                )
                if base_score is None:
                    continue
                base_value, used_at = base_score
                stress_values: dict[str, float] = {}
                for scenario_id, mapping in stress_maps.items():
                    stress_score = _matured_candidate_score(
                        mapping[config_id].consequences,
                        decision_time,
                        window=objective_window,
                    )
                    if stress_score is not None:
                        stress_values[scenario_id] = float(stress_score[0])
                expected_stress = set(stress_maps)
                missing_stress = sorted(expected_stress.difference(stress_values))
                stress_complete = not missing_stress
                worst_stress = (
                    min(stress_values.values())
                    if stress_complete and stress_values
                    else float("-inf")
                )
                robust = bool(
                    base_value > 0.0
                    and stress_complete
                    and worst_stress >= float(stress_floor)
                )
                candidate_scores.append({
                    "config_id": config_id,
                    "trailing_30_net_return": float(base_value),
                    "stress_trailing_30": stress_values,
                    "required_stress_scenarios": sorted(expected_stress),
                    "missing_stress_scenarios": missing_stress,
                    "stress_complete": bool(stress_complete),
                    "worst_stress_trailing_30": (
                        float(worst_stress) if np.isfinite(worst_stress) else None
                    ),
                    "max_outcome_available_at_used": used_at,
                    "eligible": robust,
                })
                if robust:
                    eligible.append((float(base_value), config_id, used_at, float(worst_stress)))
        candidate_scores.sort(key=lambda row: (-row["trailing_30_net_return"], row["config_id"]))
        eligible.sort(key=lambda item: (-item[0], item[1]))
        structural_update = bool(
            index >= int(objective_window)
            and (index - int(objective_window)) % int(structural_cadence) == 0
        )
        if structural_update:
            active_config_ids = tuple(item[1] for item in eligible[: int(ensemble_size)])
            last_structural_update_time = decision_time
        score_by_id = {row["config_id"]: row for row in candidate_scores}
        selected: list[tuple[float, str, pd.Timestamp | None, float | None, bool]] = []
        for config_id in active_config_ids:
            score_row = score_by_id.get(config_id)
            if score_row is None:
                selected.append((0.0, config_id, None, None, False))
                continue
            selected.append((
                max(0.0, float(score_row["trailing_30_net_return"]))
                if bool(score_row["eligible"]) else 0.0,
                config_id,
                pd.Timestamp(score_row["max_outcome_available_at_used"]),
                (
                    float(score_row["worst_stress_trailing_30"])
                    if score_row["worst_stress_trailing_30"] is not None else None
                ),
                bool(score_row["eligible"]),
            ))
        ensemble: list[dict[str, Any]] = []
        blended_target = 0.0
        max_used: pd.Timestamp | None = None
        weight_items: list[tuple[float, dict[str, float]]] = []
        group_items: list[tuple[float, dict[str, float]]] = []
        lifecycle_members: list[dict[str, Any]] = []
        if selected:
            score_total = sum(item[0] for item in selected)
            for score, config_id, used_at, worst_stress, stress_gate_passed in selected:
                alpha = float(score / score_total) if score_total > 0.0 else 0.0
                row = decision_maps[config_id].loc[decision_time]
                blended_target += alpha * float(row["target_exposure"])
                weight_items.append((alpha, dict(row["selected_weights"])))
                group_items.append((alpha, dict(row["selected_group_weights"])))
                if used_at is not None:
                    max_used = used_at if max_used is None else max(max_used, used_at)
                config = base_map[config_id].config
                candidate_direction = str(row["selected_direction"])
                if candidate_direction in {"long", "short"}:
                    lifecycle_policy = config.policy_for(candidate_direction)
                    lifecycle_members.append({
                        "direction": candidate_direction,
                        "alpha": alpha,
                        "edge": float(row["remaining_edge"]),
                        "uncertainty": float(row["uncertainty"]),
                        "timing": str(row["timing_decision"]),
                        "add_edge_ratio": float(lifecycle_policy.add_edge_ratio),
                        "reduce_edge_ratio": float(lifecycle_policy.reduce_edge_ratio),
                        "reverse_edge_ratio": float(lifecycle_policy.reverse_edge_ratio),
                        "exit_edge_floor": float(lifecycle_policy.exit_edge_floor),
                        "max_hold_sessions": float(lifecycle_policy.max_hold_sessions),
                    })
                ensemble.append({
                    "config_id": config_id,
                    "trailing_30_net_return": float(score),
                    "worst_stress_trailing_30": (
                        float(worst_stress) if worst_stress is not None else None
                    ),
                    "stress_gate_passed": bool(stress_gate_passed),
                    "structural_member": True,
                    "blend_weight": alpha,
                    "long_profile": config.long_policy.profile_id,
                    "short_profile": config.short_policy.profile_id,
                    "candidate_target": float(row["target_exposure"]),
                    "candidate_horizon": serializable_value(row["selected_horizon"]),
                    "candidate_direction": str(row["selected_direction"]),
                    "candidate_side_profile": serializable_value(row["selected_side_profile"]),
                    "candidate_timing": str(row["timing_decision"]),
                    "candidate_action": str(row["action"]),
                    "candidate_lifecycle_reason": str(row["lifecycle_reason"]),
                    "candidate_sparse_weights": serializable_value(dict(row["selected_weights"])),
                    "candidate_group_weights": serializable_value(dict(row["selected_group_weights"])),
                    "candidate_opportunity_table": serializable_value(row["opportunity_table"]),
                    "candidate_active_families": serializable_value(row["active_families"]),
                    "candidate_structural_update": bool(row["structural_update"]),
                    "candidate_sizing_inputs": serializable_value(row["sizing_inputs"]),
                    "candidate_position_before": serializable_value(row["position_before"]),
                })
        selected_weights = _weighted_dict(weight_items)
        selected_groups = _weighted_dict(group_items)
        blended_target = float(np.clip(
            round(blended_target * 4.0) / 4.0,
            -max_abs_contracts,
            max_abs_contracts,
        ))
        hard_cap = hard_exposure_limit(
            state_row, position, max_abs_contracts=max_abs_contracts,
            initial_margin_usd_per_contract=initial_margin_usd_per_contract,
            contract_multiplier=multiplier, max_margin_fraction=max_margin_fraction,
            max_notional_leverage=max_notional_leverage,
            max_drawdown_fraction=max_drawdown_fraction,
        )
        target = float(np.clip(blended_target, -hard_cap, hard_cap))
        current = float(position.exposure)
        lifecycle_inputs = meta_lifecycle_inputs(
            lifecycle_members,
            current_exposure=current,
            target_exposure=target,
        )
        remaining_edge = float(lifecycle_inputs["remaining_edge"])
        uncertainty = float(lifecycle_inputs["uncertainty"])
        primary_timing = str(lifecycle_inputs["timing_decision"])
        blended_add_ratio = float(lifecycle_inputs["add_edge_ratio"])
        blended_reduce_ratio = float(lifecycle_inputs["reduce_edge_ratio"])
        blended_reverse_ratio = float(lifecycle_inputs["reverse_edge_ratio"])
        blended_exit_floor = float(lifecycle_inputs["exit_edge_floor"])
        blended_max_hold = float(lifecycle_inputs["max_hold_sessions"])
        meta_lifecycle_reason = "ensemble_target_accepted"
        if current == 0.0 and target != 0.0 and primary_timing != "ENTER_NOW":
            target = 0.0
            meta_lifecycle_reason = "flat_wait_or_abstain"
        elif current != 0.0 and current * target < 0.0:
            required = abs(float(position.edge_at_entry)) * blended_reverse_ratio
            if remaining_edge < required:
                target = 0.0
                meta_lifecycle_reason = "exit_reverse_edge_insufficient"
        elif current != 0.0 and current * target > 0.0:
            if remaining_edge <= blended_exit_floor:
                target = 0.0
                meta_lifecycle_reason = "exit_remaining_edge_floor"
            elif abs(target) > abs(current):
                required = max(0.0, float(position.edge_at_entry) * blended_add_ratio)
                if remaining_edge < required:
                    target = current
                    meta_lifecycle_reason = "hold_add_requires_future_marginal_edge"
            elif abs(target) < abs(current):
                hard_risk_reduction = hard_cap < abs(current) - 1e-12
                deterioration_level = max(
                    0.0, float(position.edge_at_entry) * blended_reduce_ratio
                )
                if hard_risk_reduction:
                    meta_lifecycle_reason = "reduce_hard_risk_cap"
                elif remaining_edge < deterioration_level:
                    meta_lifecycle_reason = "reduce_edge_deterioration"
                else:
                    target = current
                    meta_lifecycle_reason = "hold_reduction_requires_edge_or_hard_risk_deterioration"
        if (
            current != 0.0
            and int(mark["time_in_position_sessions"]) >= round(blended_max_hold)
            and remaining_edge <= max(0.0, float(position.edge_at_entry))
        ):
            target = 0.0
            meta_lifecycle_reason = "exit_blended_max_hold_without_edge_improvement"
        outcome = path_by_time.loc[decision_time]
        target_before_execution_cap = float(target)
        target, execution_hard_cap = enforce_execution_hard_cap(
            target,
            state_row,
            position,
            fill_price=float(outcome["fill_price"]),
            max_abs_contracts=max_abs_contracts,
            initial_margin_usd_per_contract=initial_margin_usd_per_contract,
            contract_multiplier=multiplier,
            max_margin_fraction=max_margin_fraction,
            max_notional_leverage=max_notional_leverage,
            max_drawdown_fraction=max_drawdown_fraction,
        )
        if abs(target) < abs(target_before_execution_cap) - 1e-12:
            meta_lifecycle_reason = "reduce_execution_price_hard_risk_cap"
        target_contract_id = str(outcome["fill_contract_id"])
        transition_turnover = execution_turnover(
            position.exposure, target,
            current_contract_id=position.current_contract_id,
            target_contract_id=target_contract_id,
        )
        roll_turnover = 2.0 * abs(float(target)) * float(outcome.get("holding_roll_count", 0.0))
        turnover = float(transition_turnover + roll_turnover)
        action = transition_action(position.exposure, target)
        gross_pnl = float(target) * float(outcome["holding_move_per_mmbtu"]) * multiplier
        execution_cost = turnover * cost_per_side
        realized_return = (gross_pnl - execution_cost) / initial_capital
        risk_equity = max(float(position.marked_equity_usd), 1e-12)
        leverage = abs(float(target)) * float(outcome["fill_price"]) * multiplier / risk_equity
        margin_fraction = abs(float(target)) * initial_margin_usd_per_contract / risk_equity
        current_signals = serializable_state_snapshot(specialist_by_time.loc[decision_time])
        comparable_refs = [
            pd.Timestamp(value).isoformat() for value in refs_by_time[decision_time]
        ]
        reason_code = (
            "positive_prior30_robust_ensemble"
            if any(float(row["blend_weight"]) > 0.0 for row in ensemble)
            else "flat_no_robust_positive_prior30_candidate"
        )
        brain.append({
            "decision_time": decision_time,
            "pit_state": serializable_state_snapshot(state_row),
            "specialist_signals": current_signals,
            "specialist_signal_count": len(current_signals),
            "comparable_state_refs": comparable_refs,
            "effectiveness_surface": serializable_frame_records(surfaces[decision_time]),
            "objective_window_sessions": int(objective_window),
            "candidate_objective_scores": serializable_value(candidate_scores),
            "eligible_candidate_count": len(eligible),
            "structural_update": structural_update,
            "active_structural_configs": active_config_ids,
            "structural_state": {
                "cadence_sessions": int(structural_cadence),
                "active_config_ids": list(active_config_ids),
                "last_structural_update_time": (
                    last_structural_update_time.isoformat()
                    if last_structural_update_time is not None else None
                ),
            },
            "adaptation_state": {
                "slow_structural_update": structural_update,
                "fast_daily_weight_trade_position_update": True,
                "ensemble_membership_held_between_slow_updates": True,
            },
            "selected_ensemble": ensemble,
            "selected_sparse_weights": selected_weights,
            "selected_weights": selected_weights,
            "selected_specialists": sorted(
                key for key, value in selected_weights.items() if abs(float(value)) > 0.0
            ),
            "selected_group_weights": selected_groups,
            "opportunity_table": [
                {
                    "config_id": row["config_id"],
                    "candidate_opportunity_table": row["candidate_opportunity_table"],
                }
                for row in ensemble
            ],
            "remaining_edge": float(remaining_edge),
            "edge_change_since_entry": float(remaining_edge - position.edge_at_entry),
            "uncertainty": float(uncertainty),
            "hard_exposure_cap": float(hard_cap),
            "risk_state": {
                "hard_exposure_cap": float(hard_cap),
                "execution_price_hard_exposure_cap": float(execution_hard_cap),
                "max_abs_contracts": float(max_abs_contracts),
                "max_margin_fraction": float(max_margin_fraction),
                "max_notional_leverage": float(max_notional_leverage),
                "max_drawdown_fraction": float(max_drawdown_fraction),
                "initial_margin_usd_per_contract": float(initial_margin_usd_per_contract),
                "equity_usd": float(position.equity_usd),
                "peak_equity_usd": float(position.peak_equity_usd),
                "marked_equity_usd": float(position.marked_equity_usd),
                "peak_marked_equity_usd": float(position.peak_marked_equity_usd),
                "drawdown_fraction": float(position.drawdown_fraction),
                "risk_drawdown_fraction": float(position.risk_drawdown_fraction),
                "notional_leverage_after_action": float(leverage),
                "margin_fraction_after_action": float(margin_fraction),
            },
            "position_before": serializable_value(mark),
            "meta_lifecycle_policy": {
                "lifecycle_direction": str(lifecycle_inputs["lifecycle_direction"]),
                "selected_direction_weight": float(lifecycle_inputs["direction_weight"]),
                "directional_state": serializable_value(lifecycle_inputs["directional_state"]),
                "blended_add_edge_ratio": float(blended_add_ratio),
                "blended_reduce_edge_ratio": float(blended_reduce_ratio),
                "blended_reverse_edge_ratio": float(blended_reverse_ratio),
                "blended_exit_edge_floor": float(blended_exit_floor),
                "blended_max_hold_sessions": float(blended_max_hold),
            },
            "meta_lifecycle_reason": meta_lifecycle_reason,
            "lifecycle_reason": meta_lifecycle_reason,
            "action": action,
            "target_exposure": float(target),
            "timing_decision": primary_timing,
            "max_outcome_available_at_used": max_used,
            "reason_code": reason_code,
            "reason_codes": [reason_code, meta_lifecycle_reason],
            "execution_assumptions": {
                "planned_fill_time": pd.Timestamp(outcome["fill_timestamp"]).isoformat(),
                "planned_contract_id": target_contract_id,
                "fill_rule": "frozen_earliest_executable_fill_contract",
                "fill_price_source": "attached_only_after_decision_freeze",
                "cost_usd_per_contract_side": float(cost_per_side),
                "roll_turnover_charged": True,
            },
        })
        consequences.append({
            "decision_time": decision_time,
            "fill_timestamp": pd.Timestamp(outcome["fill_timestamp"]),
            "fill_contract_id": target_contract_id,
            "fill_price": float(outcome["fill_price"]),
            "outcome_available_at": pd.Timestamp(outcome["holding_outcome_available_at"]),
            "path_move_per_mmbtu": float(outcome["holding_move_per_mmbtu"]),
            "holding_session_count": int(outcome["holding_session_count"]),
            "holding_roll_count": int(outcome["holding_roll_count"]),
            "transition_turnover": float(transition_turnover),
            "roll_turnover": float(roll_turnover),
            "exposure_before": float(position.exposure),
            "signal": float(target),
            "turnover": float(turnover),
            "gross_return": float(gross_pnl / initial_capital),
            "execution_cost_return": float(execution_cost / initial_capital),
            "realized_net_return": float(realized_return),
            "notional_leverage": float(leverage),
            "margin_fraction": float(margin_fraction),
            "action": action,
            "direction": "long" if target > 0.0 else ("short" if target < 0.0 else "flat"),
        })
        apply_fill(
            position, target=float(target), fill_price=float(outcome["fill_price"]),
            fill_time=pd.Timestamp(outcome["fill_timestamp"]), decision_index=index,
            remaining_edge=float(remaining_edge), contract_id=target_contract_id,
        )
        pending.append((
            pd.Timestamp(outcome["holding_outcome_available_at"]),
            float(realized_return), int(position.instance_id),
            float(outcome["holding_terminal_basis_price"]),
            str(outcome["holding_terminal_contract_id"]),
        ))
    brain_frame = pd.DataFrame(brain)
    consequence_frame = pd.DataFrame(consequences)
    payload = brain_frame.to_json(orient="records", date_format="iso", double_precision=15)
    freeze_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return brain_frame, consequence_frame, freeze_sha

def side_policy_to_dict(policy: SidePolicy) -> dict[str, Any]:
    return {
        "profile_id": policy.profile_id,
        "memories": list(policy.memories),
        "horizons": list(policy.horizons),
        "top_k": policy.top_k,
        "wait_support_floor": policy.wait_support_floor,
        "enter_support_floor": policy.enter_support_floor,
        "enter_confidence_floor": policy.enter_confidence_floor,
        "max_vol_ratio": policy.max_vol_ratio,
        "size_scale": policy.size_scale,
        "max_hold_sessions": policy.max_hold_sessions,
        "add_edge_ratio": policy.add_edge_ratio,
        "reduce_edge_ratio": policy.reduce_edge_ratio,
        "reverse_edge_ratio": policy.reverse_edge_ratio,
        "exit_edge_floor": policy.exit_edge_floor,
    }


def config_to_dict(config: ControllerConfig) -> dict[str, Any]:
    return {
        "config_id": config.config_id,
        "long_policy": side_policy_to_dict(config.long_policy),
        "short_policy": side_policy_to_dict(config.short_policy),
        "asymmetric": config.asymmetric,
        "comparable_weight": config.comparable_weight,
        "slow_cadence": config.slow_cadence,
        "uncertainty_penalty": config.uncertainty_penalty,
        "active_family_cap": config.active_family_cap,
    }

def oracle_first_diagnostic(
    base_consequences: pd.DataFrame,
    decision_times: list[pd.Timestamp],
) -> dict[str, Any]:
    wanted = {pd.Timestamp(value) for value in decision_times}
    frame = base_consequences.loc[
        base_consequences["decision_time"].isin(wanted)
    ].copy()
    if "outcome_available_at" in frame:
        frame = frame.loc[
            pd.to_datetime(frame["outcome_available_at"], utc=True, errors="coerce").notna()
        ].copy()
    winners: dict[str, dict[str, Any]] = {}
    total = 0.0
    for decision_time, group in frame.groupby("decision_time", sort=True):
        best = group.sort_values(
            ["net_return", "policy_id"],
            ascending=[False, True],
            kind="stable",
        ).iloc[0]
        total += float(best["net_return"])
        raw_available = best.get("outcome_available_at")
        winners[pd.Timestamp(decision_time).isoformat()] = {
            "policy_id": str(best["policy_id"]),
            "specialist": str(best["specialist"]),
            "horizon": int(best["horizon"]),
            "direction": str(best["direction"]),
            "net_return": float(best["net_return"]),
            "outcome_available_at": (
                None if raw_available is None or pd.isna(raw_available)
                else pd.Timestamp(raw_available)
            ),
        }
    winner_ids = [row["policy_id"] for row in winners.values()]
    counts = pd.Series(winner_ids, dtype="object").value_counts() if winner_ids else pd.Series(dtype="int64")
    return {
        "stage": "oracle_first_before_structural_candidate_replay",
        "development_only_nontradable": True,
        "selection_use": False,
        "oracle_net_return": float(total),
        "decision_count": len(winners),
        "unique_winning_primitive_count": int(counts.size),
        "top_winner_share": float(counts.iloc[0] / len(winner_ids)) if winner_ids else 0.0,
        "winner_by_day": winners,
    }

def replay_targets_under_execution_stress(
    brain: pd.DataFrame,
    state: pd.DataFrame,
    path: pd.DataFrame,
    scenario: dict[str, Any],
    *,
    initial_capital: float = 100000.0,
    multiplier: float = 10000.0,
    base_cost_per_side: float = 15.0,
) -> pd.DataFrame:
    state_by_time = state.set_index(pd.to_datetime(state["decision_time"], utc=True))
    path_by_time = path.set_index(pd.to_datetime(path["decision_time"], utc=True))
    current = 0.0
    current_contract: str | None = None
    rows: list[dict[str, Any]] = []
    extra = float(scenario.get("extra_slippage_usd_per_contract_side", 0.0))
    miss_low_liquidity = bool(scenario.get("miss_increase_when_below_prior_volume", False))
    for brain_row in brain.itertuples(index=False):
        decision_time = pd.Timestamp(brain_row.decision_time)
        state_row = state_by_time.loc[decision_time]
        outcome = path_by_time.loc[decision_time]
        requested = float(brain_row.target_exposure)
        target, missed = _execution_adjusted_target(
            current, requested, state_row,
            miss_increase_when_below_prior_volume=miss_low_liquidity,
        )
        contract_id = str(outcome["fill_contract_id"])
        transition_turnover = execution_turnover(
            current, target,
            current_contract_id=current_contract,
            target_contract_id=contract_id,
        )
        roll_turnover = 2.0 * abs(float(target)) * float(outcome.get("holding_roll_count", 0.0))
        turnover = float(transition_turnover + roll_turnover)
        held_move = float(outcome.get("holding_move_per_mmbtu", outcome["path_move_per_mmbtu"]))
        gross = target * held_move * multiplier
        cost = turnover * (base_cost_per_side + extra)
        rows.append({
            "decision_time": decision_time,
            "scenario": str(scenario["id"]),
            "requested_target": requested,
            "executed_target": float(target),
            "missed_fill": bool(missed),
            "holding_session_count": int(outcome.get("holding_session_count", 1)),
            "transition_turnover": float(transition_turnover),
            "roll_turnover": float(roll_turnover),
            "turnover": float(turnover),
            "realized_net_return": float((gross - cost) / initial_capital),
        })
        current = float(target)
        current_contract = (
            str(outcome.get("holding_terminal_contract_id", contract_id))
            if current != 0.0 else None
        )
    return pd.DataFrame(rows)