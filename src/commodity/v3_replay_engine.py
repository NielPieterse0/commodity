from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

NAT_INT64 = int(pd.NaT.value)

LIFECYCLE_REASON_LABELS = (
    "no_positive_remaining_edge",
    "entry_abstain",
    "entry_wait",
    "starter_positive_edge",
    "exit_wait_before_reverse",
    "exit_reverse_edge_insufficient",
    "reverse_stronger_future_edge",
    "exit_remaining_edge_nonpositive",
    "exit_max_hold_without_edge_improvement",
    "reduce_hard_risk_cap",
    "hold_wait_for_entry_quality",
    "hold_add_requires_future_marginal_edge",
    "add_future_marginal_edge_and_capacity",
    "reduce_edge_deterioration",
    "hold_reduction_requires_edge_or_hard_risk_deterioration",
    "hold_or_full_positive_remaining_edge",
)


@dataclass(frozen=True)
class ReplayKernelLimits:
    max_abs_contracts: float
    initial_capital: float
    multiplier: float
    base_cost_per_side: float
    initial_margin_usd_per_contract: float
    max_margin_fraction: float
    max_notional_leverage: float
    max_drawdown_fraction: float


@dataclass(frozen=True)
class ReplayKernelInputs:
    decision_time_ns: np.ndarray
    market_observation_time_ns: np.ndarray
    settle: np.ndarray
    volatility: np.ndarray
    prior_volatility: np.ndarray
    log_volume: np.ndarray
    prior_log_volume: np.ndarray
    fill_time_ns: np.ndarray
    fill_price: np.ndarray
    fill_contract_code: np.ndarray
    outcome_available_ns: np.ndarray
    holding_move_per_mmbtu: np.ndarray
    holding_session_count: np.ndarray
    holding_roll_count: np.ndarray
    terminal_basis_price: np.ndarray
    terminal_contract_code: np.ndarray
    selected_direction: np.ndarray
    timing: np.ndarray
    edge: np.ndarray
    uncertainty: np.ndarray
    support: np.ndarray
    max_vol_ratio: np.ndarray
    size_scale: np.ndarray
    max_hold_sessions: np.ndarray
    add_edge_ratio: np.ndarray
    reduce_edge_ratio: np.ndarray
    reverse_edge_ratio: np.ndarray
    exit_edge_floor: np.ndarray
    contract_labels: tuple[str, ...]


@dataclass(frozen=True)
class ReplayKernelResult:
    decision_target: np.ndarray
    executed_target: np.ndarray
    remaining_edge: np.ndarray
    uncertainty: np.ndarray
    missed_fill: np.ndarray
    lifecycle_reason: np.ndarray
    signal: np.ndarray
    turnover: np.ndarray
    gross_return: np.ndarray
    execution_cost_return: np.ndarray
    realized_net_return: np.ndarray
    notional_leverage: np.ndarray
    margin_fraction: np.ndarray
    position_exposure_before: np.ndarray
    position_entry_price_before: np.ndarray
    position_basis_price_before: np.ndarray
    position_entry_time_ns_before: np.ndarray
    position_entry_contract_code_before: np.ndarray
    position_contract_code_before: np.ndarray
    position_age_before: np.ndarray
    position_edge_at_entry_before: np.ndarray
    position_unrealized_pnl_before: np.ndarray
    position_current_mtm_before: np.ndarray
    position_economic_pnl_before: np.ndarray
    position_mfe_before: np.ndarray
    position_mae_before: np.ndarray
    position_instance_before: np.ndarray
    position_mark_valid_before: np.ndarray
    position_equity_before: np.ndarray
    position_peak_equity_before: np.ndarray
    position_marked_equity_before: np.ndarray
    position_peak_marked_equity_before: np.ndarray
    position_drawdown_before: np.ndarray
    position_risk_drawdown_before: np.ndarray
    sizing_selected: np.ndarray
    sizing_estimated_edge: np.ndarray
    sizing_confidence: np.ndarray
    sizing_support: np.ndarray
    sizing_regime_quality: np.ndarray
    sizing_volatility_factor: np.ndarray
    sizing_volatility_ratio: np.ndarray
    sizing_liquidity_factor: np.ndarray
    sizing_drawdown_factor: np.ndarray
    sizing_side_size_scale: np.ndarray
    sizing_hard_exposure_cap: np.ndarray
    sizing_risk_capacity: np.ndarray
    execution_hard_cap: np.ndarray
    transition_turnover: np.ndarray
    roll_turnover: np.ndarray


def _float_column(frame: pd.DataFrame, name: str, default: Any) -> np.ndarray:
    if name in frame:
        values = pd.to_numeric(frame[name], errors="raise").to_numpy(dtype=np.float64)
    else:
        if np.isscalar(default):
            values = np.full(len(frame), float(default), dtype=np.float64)
        else:
            values = np.asarray(default, dtype=np.float64)
    return np.asarray(values, dtype=np.float64)


def _time_column(frame: pd.DataFrame, name: str, *, required: bool) -> np.ndarray:
    if name not in frame:
        if required:
            raise KeyError(name)
        return np.full(len(frame), NAT_INT64, dtype=np.int64)
    values = pd.to_datetime(frame[name], utc=True, errors="raise" if required else "coerce")
    return values.astype("int64").to_numpy(dtype=np.int64, copy=True)


def _contract_codes(path: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    labels: list[str] = []
    indices: dict[str, int] = {}
    def encode(values: pd.Series) -> np.ndarray:
        out = np.full(len(values), -1, dtype=np.int32)
        for index, raw in enumerate(values):
            if pd.isna(raw):
                continue
            label = str(raw)
            code = indices.get(label)
            if code is None:
                code = len(labels)
                labels.append(label)
                indices[label] = code
            out[index] = code
        return out

    fill = encode(path["fill_contract_id"])
    terminal = encode(path["holding_terminal_contract_id"])
    return fill, terminal, tuple(labels)


def _policy_arrays(config: Any, directions: np.ndarray) -> tuple[np.ndarray, ...]:
    count = len(directions)
    max_vol_ratio = np.zeros(count, dtype=np.float64)
    size_scale = np.zeros(count, dtype=np.float64)
    max_hold_sessions = np.zeros(count, dtype=np.int32)
    add_edge_ratio = np.zeros(count, dtype=np.float64)
    reduce_edge_ratio = np.zeros(count, dtype=np.float64)
    reverse_edge_ratio = np.zeros(count, dtype=np.float64)
    exit_edge_floor = np.zeros(count, dtype=np.float64)
    for index, direction in enumerate(directions):
        policy = config.long_policy if int(direction) >= 0 else config.short_policy
        max_vol_ratio[index] = float(policy.max_vol_ratio)
        size_scale[index] = float(policy.size_scale)
        max_hold_sessions[index] = int(policy.max_hold_sessions)
        add_edge_ratio[index] = float(policy.add_edge_ratio)
        reduce_edge_ratio[index] = float(policy.reduce_edge_ratio)
        reverse_edge_ratio[index] = float(policy.reverse_edge_ratio)
        exit_edge_floor[index] = float(policy.exit_edge_floor)
    return (
        max_vol_ratio,
        size_scale,
        max_hold_sessions,
        add_edge_ratio,
        reduce_edge_ratio,
        reverse_edge_ratio,
        exit_edge_floor,
    )


def prepare_replay_kernel_inputs(
    config: Any,
    state: pd.DataFrame,
    path: pd.DataFrame,
    decision_plan: Any,
) -> ReplayKernelInputs:
    state = state.reset_index(drop=True)
    path = path.reset_index(drop=True)
    if len(state) != len(path) or len(state) != len(decision_plan.decision_times):
        raise ValueError("replay kernel inputs require aligned decision rows")
    decision_time_ns = _time_column(state, "decision_time", required=True)
    path_time_ns = _time_column(path, "decision_time", required=True)
    if not np.array_equal(decision_time_ns, path_time_ns):
        raise ValueError("replay kernel state/path decision_time mismatch")
    settle = _float_column(state, "derived_settle_m1", 1.0)
    volatility = _float_column(state, "feature_vol_20", 0.0)
    prior_volatility = _float_column(
        state, "derived_prior60_vol20_median", volatility
    )
    log_volume = _float_column(state, "feature_curve_log_volume_m1", 0.0)
    prior_log_volume = _float_column(
        state, "derived_prior20_log_volume_m1_median", log_volume
    )
    fill_contract_code, terminal_contract_code, contract_labels = _contract_codes(path)
    directions = np.asarray(decision_plan.selected_direction, dtype=np.int8)
    policy_arrays = _policy_arrays(config, directions)
    return ReplayKernelInputs(
        decision_time_ns=decision_time_ns,
        market_observation_time_ns=_time_column(
            state, "market_observation_time", required=False
        ),
        settle=settle,
        volatility=volatility,
        prior_volatility=prior_volatility,
        log_volume=log_volume,
        prior_log_volume=prior_log_volume,
        fill_time_ns=_time_column(path, "fill_timestamp", required=True),
        fill_price=_float_column(path, "fill_price", 0.0),
        fill_contract_code=fill_contract_code,
        outcome_available_ns=_time_column(
            path, "holding_outcome_available_at", required=True
        ),
        holding_move_per_mmbtu=_float_column(path, "holding_move_per_mmbtu", 0.0),
        holding_session_count=np.asarray(
            pd.to_numeric(path["holding_session_count"], errors="raise"), dtype=np.int32
        ),
        holding_roll_count=np.asarray(
            pd.to_numeric(path["holding_roll_count"], errors="raise"), dtype=np.int32
        ),
        terminal_basis_price=_float_column(path, "holding_terminal_basis_price", np.nan),
        terminal_contract_code=terminal_contract_code,
        selected_direction=directions,
        timing=np.asarray(decision_plan.timing, dtype=np.int8),
        edge=np.asarray(decision_plan.edge, dtype=np.float64),
        uncertainty=np.asarray(decision_plan.uncertainty, dtype=np.float64),
        support=np.asarray(decision_plan.support, dtype=np.float64),
        max_vol_ratio=policy_arrays[0],
        size_scale=policy_arrays[1],
        max_hold_sessions=policy_arrays[2],
        add_edge_ratio=policy_arrays[3],
        reduce_edge_ratio=policy_arrays[4],
        reverse_edge_ratio=policy_arrays[5],
        exit_edge_floor=policy_arrays[6],
        contract_labels=contract_labels,
    )


def _risk_drawdown(peak_marked: float, marked: float) -> float:
    if peak_marked <= 0.0:
        return 1.0
    return max(0.0, (peak_marked - marked) / peak_marked)


def _drawdown(peak_equity: float, equity: float) -> float:
    if peak_equity <= 0.0:
        return 1.0
    return max(0.0, (peak_equity - equity) / peak_equity)


def _hard_cap(
    *,
    marked_equity: float,
    peak_marked_equity: float,
    price: float,
    limits: ReplayKernelLimits,
) -> float:
    if _risk_drawdown(peak_marked_equity, marked_equity) >= limits.max_drawdown_fraction:
        return 0.0
    equity = max(float(marked_equity), 1e-12)
    margin_cap = (
        equity * limits.max_margin_fraction
        / max(limits.initial_margin_usd_per_contract, 1e-12)
    )
    notional = max(abs(float(price)) * limits.multiplier, 1e-12)
    leverage_cap = equity * limits.max_notional_leverage / notional
    return max(0.0, min(limits.max_abs_contracts, margin_cap, leverage_cap))


def _execution_adjusted_target(
    current: float,
    target: float,
    log_volume: float,
    prior_log_volume: float,
    miss_increase_when_below_prior_volume: bool,
) -> tuple[float, bool]:
    if not miss_increase_when_below_prior_volume or log_volume >= prior_log_volume:
        return float(target), False
    if current == 0.0 and target != 0.0:
        return 0.0, True
    if current * target < 0.0:
        return 0.0, True
    if current * target > 0.0 and abs(target) > abs(current):
        return float(current), True
    return float(target), False


def _lifecycle_target(
    *,
    current: float,
    selected: bool,
    timing: int,
    edge: float,
    desired_target: float,
    direction: int,
    edge_at_entry: float,
    age: int,
    risk_capacity: float,
    hard_exposure_cap: float,
    max_hold_sessions: int,
    add_edge_ratio: float,
    reduce_edge_ratio: float,
    reverse_edge_ratio: float,
    exit_edge_floor: float,
) -> tuple[float, int]:
    if not selected:
        return 0.0, 0
    if current == 0.0:
        if timing != 2:
            return 0.0, 2 if timing == 1 else 1
        return float(desired_target), 3
    same_side = (current > 0.0 and direction > 0) or (current < 0.0 and direction < 0)
    if not same_side:
        if timing != 2:
            return 0.0, 4
        required = max(0.0, abs(float(edge_at_entry)) * reverse_edge_ratio)
        if edge < required:
            return 0.0, 5
        return float(desired_target), 6
    if edge <= exit_edge_floor:
        return 0.0, 7
    if age >= max_hold_sessions and edge <= max(float(edge_at_entry), 0.0):
        return 0.0, 8
    if hard_exposure_cap < abs(current) - 1e-12:
        capped = np.sign(current) * min(
            abs(float(desired_target)), max(0.0, hard_exposure_cap)
        )
        return float(capped), 9
    if timing == 1:
        return float(current), 10
    target = float(desired_target)
    if abs(target) > abs(current):
        required = max(0.0, float(edge_at_entry) * add_edge_ratio)
        if edge < required or risk_capacity <= 0.0:
            return float(current), 11
        return target, 12
    if abs(target) < abs(current):
        if hard_exposure_cap < abs(current) - 1e-12:
            capped = np.sign(current) * min(abs(target), max(0.0, hard_exposure_cap))
            return float(capped), 9
        deterioration_level = max(0.0, float(edge_at_entry) * reduce_edge_ratio)
        if edge < deterioration_level:
            return target, 13
        return float(current), 14
    return target, 15


def _empty_result(count: int) -> ReplayKernelResult:
    zeros = lambda: np.zeros(count, dtype=np.float64)
    nans = lambda: np.full(count, np.nan, dtype=np.float64)
    ints = lambda: np.zeros(count, dtype=np.int64)
    return ReplayKernelResult(
        decision_target=zeros(), executed_target=zeros(), remaining_edge=zeros(),
        uncertainty=zeros(), missed_fill=np.zeros(count, dtype=np.bool_),
        lifecycle_reason=np.zeros(count, dtype=np.int8), signal=zeros(), turnover=zeros(),
        gross_return=zeros(), execution_cost_return=zeros(), realized_net_return=zeros(),
        notional_leverage=zeros(), margin_fraction=zeros(), position_exposure_before=zeros(),
        position_entry_price_before=nans(), position_basis_price_before=nans(),
        position_entry_time_ns_before=np.full(count, NAT_INT64, dtype=np.int64),
        position_entry_contract_code_before=np.full(count, -1, dtype=np.int32),
        position_contract_code_before=np.full(count, -1, dtype=np.int32),
        position_age_before=ints(), position_edge_at_entry_before=zeros(),
        position_unrealized_pnl_before=zeros(), position_current_mtm_before=zeros(),
        position_economic_pnl_before=zeros(), position_mfe_before=zeros(),
        position_mae_before=zeros(), position_instance_before=ints(),
        position_mark_valid_before=np.ones(count, dtype=np.bool_),
        position_equity_before=zeros(), position_peak_equity_before=zeros(),
        position_marked_equity_before=zeros(), position_peak_marked_equity_before=zeros(),
        position_drawdown_before=zeros(), position_risk_drawdown_before=zeros(),
        sizing_selected=np.zeros(count, dtype=np.bool_), sizing_estimated_edge=nans(),
        sizing_confidence=nans(), sizing_support=nans(), sizing_regime_quality=nans(),
        sizing_volatility_factor=nans(), sizing_volatility_ratio=nans(),
        sizing_liquidity_factor=nans(), sizing_drawdown_factor=nans(),
        sizing_side_size_scale=nans(), sizing_hard_exposure_cap=nans(),
        sizing_risk_capacity=zeros(), execution_hard_cap=zeros(),
        transition_turnover=zeros(), roll_turnover=zeros(),
    )


def run_replay_kernel_serial(
    inputs: ReplayKernelInputs,
    limits: ReplayKernelLimits,
    *,
    extra_slippage_usd_per_contract_side: float = 0.0,
    miss_increase_when_below_prior_volume: bool = False,
) -> ReplayKernelResult:
    count = len(inputs.decision_time_ns)
    result = _empty_result(count)
    exposure = 0.0
    entry_price = np.nan
    current_basis = np.nan
    entry_time_ns = NAT_INT64
    entry_session_index = -1
    entry_contract_code = -1
    current_contract_code = -1
    edge_at_entry = 0.0
    equity = limits.initial_capital
    peak_equity = limits.initial_capital
    marked_equity = limits.initial_capital
    peak_marked_equity = limits.initial_capital
    economic_path_pnl = 0.0
    mfe = 0.0
    mae = 0.0
    instance_id = 0

    pending_return = np.zeros(count, dtype=np.float64)
    pending_instance = np.zeros(count, dtype=np.int64)
    pending_heap: list[tuple[int, int]] = []

    for index in range(count):
        decision_ns = int(inputs.decision_time_ns[index])
        if index > 0:
            pending_index = index - 1
            heapq.heappush(
                pending_heap,
                (int(inputs.outcome_available_ns[pending_index]), pending_index),
            )
        matured_pending: list[int] = []
        while pending_heap and pending_heap[0][0] < decision_ns:
            _, pending_index = heapq.heappop(pending_heap)
            matured_pending.append(pending_index)
        matured_pending.sort()
        for pending_index in matured_pending:
            realized = float(pending_return[pending_index])
            pnl_usd = realized * limits.initial_capital
            equity += pnl_usd
            peak_equity = max(peak_equity, equity)
            marked_equity += pnl_usd
            peak_marked_equity = max(peak_marked_equity, marked_equity)
            if int(pending_instance[pending_index]) == instance_id and exposure != 0.0:
                economic_path_pnl += realized
                terminal_basis = float(inputs.terminal_basis_price[pending_index])
                terminal_contract = int(inputs.terminal_contract_code[pending_index])
                if not np.isnan(terminal_basis) and terminal_contract >= 0:
                    current_basis = terminal_basis
                    current_contract_code = terminal_contract

        mark_valid = True
        market_observation_ns = int(inputs.market_observation_time_ns[index])
        if (
            exposure != 0.0
            and entry_time_ns != NAT_INT64
            and market_observation_ns != NAT_INT64
            and market_observation_ns < entry_time_ns
        ):
            mark_valid = False
        mtm = 0.0
        if mark_valid and exposure != 0.0 and not np.isnan(current_basis):
            mtm = (
                exposure
                * (float(inputs.settle[index]) - current_basis)
                * limits.multiplier
                / limits.initial_capital
            )
        trade_path_mark = economic_path_pnl + mtm
        marked_equity = equity + mtm * limits.initial_capital
        peak_marked_equity = max(peak_marked_equity, marked_equity)
        if exposure != 0.0 and mark_valid:
            mfe = max(mfe, trade_path_mark)
            mae = min(mae, trade_path_mark)
        age = 0 if entry_session_index < 0 else max(0, index - entry_session_index)
        drawdown = _drawdown(peak_equity, equity)
        risk_drawdown = _risk_drawdown(peak_marked_equity, marked_equity)
        result.position_exposure_before[index] = exposure
        result.position_entry_price_before[index] = entry_price
        result.position_basis_price_before[index] = current_basis
        result.position_entry_time_ns_before[index] = entry_time_ns
        result.position_entry_contract_code_before[index] = entry_contract_code
        result.position_contract_code_before[index] = current_contract_code
        result.position_age_before[index] = age
        result.position_edge_at_entry_before[index] = edge_at_entry
        result.position_unrealized_pnl_before[index] = trade_path_mark
        result.position_current_mtm_before[index] = mtm
        result.position_economic_pnl_before[index] = economic_path_pnl
        result.position_mfe_before[index] = mfe
        result.position_mae_before[index] = mae
        result.position_instance_before[index] = instance_id
        result.position_mark_valid_before[index] = mark_valid
        result.position_equity_before[index] = equity
        result.position_peak_equity_before[index] = peak_equity
        result.position_marked_equity_before[index] = marked_equity
        result.position_peak_marked_equity_before[index] = peak_marked_equity
        result.position_drawdown_before[index] = drawdown
        result.position_risk_drawdown_before[index] = risk_drawdown

        direction = int(inputs.selected_direction[index])
        selected = direction != 0
        edge = float(inputs.edge[index])
        uncertainty = float(inputs.uncertainty[index])
        desired_target = 0.0
        hard_cap = limits.max_abs_contracts
        risk_capacity = max(0.0, 1.0 - drawdown)
        if selected:
            positive_edge = max(0.0, edge)
            positive_uncertainty = max(0.0, uncertainty)
            confidence = positive_edge / (
                positive_edge + positive_uncertainty + 1e-12
            )
            support = min(1.0, max(0.0, float(inputs.support[index])))
            current_vol = max(float(inputs.volatility[index]), 1e-12)
            reference_vol = max(float(inputs.prior_volatility[index]), 1e-12)
            vol_ratio = current_vol / reference_vol
            volatility_factor = min(1.0, max(0.35, reference_vol / current_vol))
            liquidity_factor = (
                1.0
                if float(inputs.log_volume[index]) >= float(inputs.prior_log_volume[index])
                else 0.75
            )
            drawdown_factor = max(0.20, 1.0 - 2.0 * risk_drawdown)
            regime_quality = (
                volatility_factor
                if vol_ratio <= float(inputs.max_vol_ratio[index])
                else 0.0
            )
            hard_cap = _hard_cap(
                marked_equity=marked_equity,
                peak_marked_equity=peak_marked_equity,
                price=float(inputs.settle[index]),
                limits=limits,
            )
            raw = (
                hard_cap * confidence * support * regime_quality * liquidity_factor
                * drawdown_factor * float(inputs.size_scale[index])
            )
            sized = min(hard_cap, max(0.0, round(raw * 4.0) / 4.0))
            if positive_edge <= 0.0 or hard_cap <= 0.0:
                sized = 0.0
            desired_target = (1.0 if direction > 0 else -1.0) * sized
            risk_capacity = max(0.0, 1.0 - risk_drawdown)
            result.sizing_selected[index] = True
            result.sizing_estimated_edge[index] = positive_edge
            result.sizing_confidence[index] = confidence
            result.sizing_support[index] = support
            result.sizing_regime_quality[index] = regime_quality
            result.sizing_volatility_factor[index] = volatility_factor
            result.sizing_volatility_ratio[index] = vol_ratio
            result.sizing_liquidity_factor[index] = liquidity_factor
            result.sizing_drawdown_factor[index] = drawdown_factor
            result.sizing_side_size_scale[index] = float(inputs.size_scale[index])
            result.sizing_hard_exposure_cap[index] = hard_cap
        result.sizing_risk_capacity[index] = risk_capacity

        target, lifecycle_reason = _lifecycle_target(
            current=exposure,
            selected=selected,
            timing=int(inputs.timing[index]),
            edge=edge,
            desired_target=desired_target,
            direction=direction,
            edge_at_entry=edge_at_entry,
            age=age,
            risk_capacity=risk_capacity,
            hard_exposure_cap=hard_cap,
            max_hold_sessions=int(inputs.max_hold_sessions[index]),
            add_edge_ratio=float(inputs.add_edge_ratio[index]),
            reduce_edge_ratio=float(inputs.reduce_edge_ratio[index]),
            reverse_edge_ratio=float(inputs.reverse_edge_ratio[index]),
            exit_edge_floor=float(inputs.exit_edge_floor[index]),
        )
        decision_target, missed_fill = _execution_adjusted_target(
            exposure,
            target,
            float(inputs.log_volume[index]),
            float(inputs.prior_log_volume[index]),
            miss_increase_when_below_prior_volume,
        )
        execution_hard_cap = _hard_cap(
            marked_equity=marked_equity,
            peak_marked_equity=peak_marked_equity,
            price=float(inputs.fill_price[index]),
            limits=limits,
        )
        if decision_target > 0.0:
            executed_target = min(abs(decision_target), execution_hard_cap)
        elif decision_target < 0.0:
            executed_target = -min(abs(decision_target), execution_hard_cap)
        else:
            executed_target = 0.0

        target_contract = int(inputs.fill_contract_code[index])
        if (
            exposure != 0.0
            and current_contract_code >= 0
            and target_contract >= 0
            and current_contract_code != target_contract
        ):
            transition_turnover = abs(exposure) + abs(executed_target)
        else:
            transition_turnover = abs(executed_target - exposure)
        roll_turnover = (
            2.0 * abs(executed_target) * float(inputs.holding_roll_count[index])
        )
        turnover = transition_turnover + roll_turnover
        gross_pnl = (
            executed_target * float(inputs.holding_move_per_mmbtu[index])
            * limits.multiplier
        )
        execution_cost = turnover * (
            limits.base_cost_per_side + extra_slippage_usd_per_contract_side
        )
        realized_return = (gross_pnl - execution_cost) / limits.initial_capital
        risk_equity = max(marked_equity, 1e-12)
        leverage = (
            abs(executed_target) * float(inputs.fill_price[index])
            * limits.multiplier / risk_equity
        )
        margin_fraction = (
            abs(executed_target) * limits.initial_margin_usd_per_contract / risk_equity
        )
        result.decision_target[index] = decision_target
        result.executed_target[index] = executed_target
        result.remaining_edge[index] = edge
        result.uncertainty[index] = uncertainty
        result.missed_fill[index] = missed_fill
        result.lifecycle_reason[index] = lifecycle_reason
        result.signal[index] = executed_target
        result.transition_turnover[index] = transition_turnover
        result.roll_turnover[index] = roll_turnover
        result.turnover[index] = turnover
        result.execution_hard_cap[index] = execution_hard_cap
        result.gross_return[index] = gross_pnl / limits.initial_capital
        result.execution_cost_return[index] = execution_cost / limits.initial_capital
        result.realized_net_return[index] = realized_return
        result.notional_leverage[index] = leverage
        result.margin_fraction[index] = margin_fraction

        current = exposure
        rolled = (
            current != 0.0
            and target_contract >= 0
            and current_contract_code >= 0
            and target_contract != current_contract_code
        )
        if executed_target == 0.0:
            entry_price = np.nan
            current_basis = np.nan
            entry_time_ns = NAT_INT64
            entry_session_index = -1
            entry_contract_code = -1
            current_contract_code = -1
            edge_at_entry = 0.0
            economic_path_pnl = 0.0
            mfe = 0.0
            mae = 0.0
        elif current == 0.0 or current * executed_target < 0.0:
            instance_id += 1
            entry_price = float(inputs.fill_price[index])
            current_basis = float(inputs.fill_price[index])
            entry_time_ns = int(inputs.fill_time_ns[index])
            entry_session_index = index
            entry_contract_code = target_contract
            current_contract_code = target_contract
            edge_at_entry = edge
            economic_path_pnl = 0.0
            mfe = 0.0
            mae = 0.0
        else:
            if rolled:
                current_basis = float(inputs.fill_price[index])
                current_contract_code = target_contract
            elif abs(executed_target) > abs(current) and not np.isnan(current_basis):
                added = abs(executed_target) - abs(current)
                current_basis = (
                    abs(current) * current_basis
                    + added * float(inputs.fill_price[index])
                ) / abs(executed_target)
            elif target_contract >= 0:
                current_contract_code = target_contract
        exposure = executed_target
        pending_return[index] = realized_return
        pending_instance[index] = instance_id

    return result
