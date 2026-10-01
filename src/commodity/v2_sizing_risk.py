from __future__ import annotations

import math
from collections.abc import Mapping

import pandas as pd


def _finite_float(value: object, label: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"issue430 {label} must be finite")
    return parsed


def _require_finite_series(values: pd.Series, label: str) -> None:
    if not values.map(math.isfinite).all():
        raise ValueError(f"issue430 {label} must be finite")


def apply_sizing_policy(
    policy: pd.DataFrame,
    config: Mapping[str, object],
) -> pd.DataFrame:
    out = _validate_policy(policy)
    positions = pd.to_numeric(out["signal_requested_position"], errors="raise").astype(float)
    _require_finite_series(positions, "requested positions")
    scale = _scale_column(out, config)
    _require_finite_series(scale, "sizing scales")
    if scale.lt(0.0).any():
        raise ValueError("issue430 sizing scales must be nonnegative")
    revised = positions * scale
    _require_finite_series(revised, "revised positions")
    cap_value = config.get("max_abs_contracts")
    cap = float("inf") if cap_value is None else _finite_float(cap_value, "contract cap")
    if cap <= 0.0:
        raise ValueError("issue430 contract cap must be positive")
    out["signal_requested_position"] = revised.clip(lower=-cap, upper=cap)
    return out


def _scale_column(out: pd.DataFrame, config: Mapping[str, object]) -> pd.Series:
    positions = pd.to_numeric(out["signal_requested_position"], errors="raise").astype(float)
    scale = pd.Series(
        _finite_float(config.get("base_scale", 1.0), "base scale"),
        index=out.index,
        dtype=float,
    )
    long_scale = _finite_float(config.get("long_scale", 1.0), "long scale")
    short_scale = _finite_float(config.get("short_scale", 1.0), "short scale")
    scale.loc[positions.gt(0.0)] *= long_scale
    scale.loc[positions.lt(0.0)] *= short_scale

    if "confidence_threshold" in config:
        favored = pd.to_numeric(out["favored_fraction"], errors="raise").astype(float)
        _require_finite_series(favored, "favored fractions")
        threshold = _finite_float(config["confidence_threshold"], "confidence threshold")
        low = _finite_float(config.get("low_confidence_scale", 1.0), "low confidence scale")
        high = _finite_float(config.get("high_confidence_scale", 1.0), "high confidence scale")
        scale *= pd.Series(high, index=out.index).where(favored.ge(threshold), low)
    if "jump_high_scale" in config:
        scale.loc[out["jump_high"].astype(bool)] *= _finite_float(
            config["jump_high_scale"], "jump-high scale"
        )
    if "vol_of_vol_high_scale" in config:
        scale.loc[out["vol_of_vol_high"].astype(bool)] *= _finite_float(
            config["vol_of_vol_high_scale"], "vol-of-vol-high scale"
        )
    if "favorable_regimes" in config:
        favorable = {str(value) for value in config["favorable_regimes"]}
        is_favorable = out["joint_regime"].astype(str).isin(favorable)
        scale.loc[is_favorable] *= _finite_float(
            config.get("favorable_regime_scale", 1.0), "favorable regime scale"
        )
        scale.loc[~is_favorable] *= _finite_float(
            config.get("other_regime_scale", 1.0), "other regime scale"
        )
    return scale


_PROTECTED_START = pd.Timestamp("2023-01-01", tz="UTC")


def _validate_policy(policy: pd.DataFrame) -> pd.DataFrame:
    required = {
        "signal_timestamp", "fill_timestamp", "target_end_timestamp",
        "fill_trade_date", "signal_requested_position",
    }
    missing = sorted(required - set(policy.columns))
    if missing:
        raise ValueError(f"issue430 policy missing columns: {missing}")
    out = policy.copy()
    for column in ("signal_timestamp", "fill_timestamp", "target_end_timestamp", "fill_trade_date"):
        out[column] = pd.to_datetime(out[column], utc=True, errors="raise")
        if (out[column] >= _PROTECTED_START).any():
            raise ValueError("issue430 protected 2023+ evidence is forbidden")
    if (out["signal_timestamp"] >= out["fill_timestamp"]).any():
        raise ValueError("issue430 signal timestamp must precede fill")
    if (out["fill_timestamp"] >= out["target_end_timestamp"]).any():
        raise ValueError("issue430 target end must follow fill")
    return out


def _validate_fill_alignment(path: pd.DataFrame, policy: pd.DataFrame) -> None:
    required = {"trade_date", "session_open"}
    missing = sorted(required - set(path.columns))
    if missing:
        raise ValueError(f"issue430 session path missing timing columns: {missing}")
    sessions = path[["trade_date", "session_open"]].copy()
    sessions["trade_date"] = pd.to_datetime(sessions["trade_date"], utc=True, errors="raise")
    sessions["session_open"] = pd.to_datetime(sessions["session_open"], utc=True, errors="raise")
    if sessions["trade_date"].duplicated().any():
        raise ValueError("issue430 session path trade dates must be unique")
    fills = policy[["fill_trade_date", "fill_timestamp"]].copy()
    fills = fills.merge(
        sessions,
        left_on="fill_trade_date",
        right_on="trade_date",
        how="left",
        validate="many_to_one",
    )
    if fills["session_open"].isna().any():
        raise ValueError("issue430 fill trade date is missing from the session path")
    if (fills["fill_timestamp"] > fills["session_open"]).any():
        raise ValueError("issue430 fill timestamp occurs after the replay execution point")


def replay_research_policy(
    path: pd.DataFrame,
    decisions: pd.DataFrame,
    risk: object,
    costs: object,
    *,
    contract_multiplier: float,
    max_abs_contracts: float,
) -> tuple[pd.DataFrame, dict[str, object]]:
    from commodity.stacking_policy import _replay_fractional_policy

    cap = _finite_float(max_abs_contracts, "research contract cap")
    multiplier = _finite_float(contract_multiplier, "contract multiplier")
    if cap <= 0.0:
        raise ValueError("issue430 research contract cap must be positive")
    if multiplier <= 0.0:
        raise ValueError("issue430 contract multiplier must be positive")
    validated = _validate_policy(decisions)
    _validate_fill_alignment(path, validated)
    validated["trade_date"] = validated["fill_trade_date"]
    positions = pd.to_numeric(validated["signal_requested_position"], errors="raise").astype(float)
    _require_finite_series(positions, "requested research positions")
    if positions.abs().gt(cap + 1e-12).any():
        raise ValueError("issue430 requested research size exceeds declared contract cap")
    levels = frozenset({0.0, *positions.tolist()})
    ledger, base_summary = _replay_fractional_policy(
        path, validated, risk, costs,
        contract_multiplier=multiplier, enforce_risk=True,
        enforce_phase5_boundary=True, allowed_position_levels=levels,
    )
    diagnostics = _exposure_diagnostics(
        path, ledger, costs=costs, contract_multiplier=multiplier
    )
    summary = dict(base_summary)
    summary.update(diagnostics)
    summary["operational_paper_max_contracts"] = int(risk.max_contracts)
    summary["research_contract_cap"] = cap
    summary["research_max_abs_contracts"] = (
        float(ledger["target_position"].abs().max()) if len(ledger) else 0.0
    )
    summary["research_only_not_execution_authority"] = True
    return ledger, summary


def _exposure_diagnostics(
    path: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    costs: object,
    contract_multiplier: float,
) -> dict[str, float]:
    required = {"trade_date", "open_price"}
    missing = sorted(required - set(path.columns))
    if missing:
        raise ValueError(f"issue430 session path missing exposure columns: {missing}")
    prices = path[["trade_date", "open_price"]].copy()
    prices["trade_date"] = pd.to_datetime(prices["trade_date"], utc=True, errors="raise")
    if prices["trade_date"].duplicated().any():
        raise ValueError("issue430 session prices are not unique by trade date")
    work = ledger.merge(prices, on="trade_date", how="left", validate="one_to_one")
    if work["open_price"].isna().any():
        raise ValueError("issue430 replay is missing session open prices")
    equity = pd.to_numeric(work["equity_usd"], errors="raise").astype(float)
    net_pnl = pd.to_numeric(work["net_pnl_usd"], errors="raise").astype(float)
    _require_finite_series(equity, "replay equity")
    _require_finite_series(net_pnl, "replay net pnl")
    equity_before = equity - net_pnl
    _require_finite_series(equity_before, "pre-session equity")
    if equity_before.le(0.0).any():
        raise ValueError("issue430 replay reached nonpositive pre-session equity")
    contracts = pd.to_numeric(work["target_position"], errors="raise").astype(float).abs()
    open_prices = pd.to_numeric(work["open_price"], errors="raise").astype(float).abs()
    _require_finite_series(contracts, "target positions")
    _require_finite_series(open_prices, "session open prices")
    margin_per_contract = _finite_float(
        costs.initial_margin_usd_per_contract, "initial margin per contract"
    )
    multiplier = _finite_float(contract_multiplier, "contract multiplier")
    margin = contracts * margin_per_contract
    notional = contracts * open_prices * multiplier
    _require_finite_series(margin, "margin requirements")
    _require_finite_series(notional, "notional exposure")
    margin_utilization = margin / equity_before
    notional_leverage = notional / equity_before
    _require_finite_series(margin_utilization, "margin utilization")
    _require_finite_series(notional_leverage, "notional leverage")
    return {
        "max_margin_utilization_fraction": float(margin_utilization.max()) if len(work) else 0.0,
        "mean_margin_utilization_fraction": float(margin_utilization.mean()) if len(work) else 0.0,
        "max_notional_leverage": float(notional_leverage.max()) if len(work) else 0.0,
        "mean_notional_leverage": float(notional_leverage.mean()) if len(work) else 0.0,
    }


def replay_risk_controlled_policy(
    path: pd.DataFrame,
    decisions: pd.DataFrame,
    risk: object,
    costs: object,
    *,
    contract_multiplier: float,
    max_abs_contracts: float,
    risk_config: Mapping[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    dynamic_keys = {
        "drawdown_threshold_fraction", "stop_loss_uncertainty_multiple",
        "take_profit_uncertainty_multiple", "max_hold_sessions",
    }
    if not any(key in risk_config for key in dynamic_keys):
        return replay_research_policy(
            path, decisions, risk, costs,
            contract_multiplier=contract_multiplier,
            max_abs_contracts=max_abs_contracts,
        )
    return _replay_dynamic_risk(
        path, decisions, risk, costs,
        contract_multiplier=contract_multiplier,
        max_abs_contracts=max_abs_contracts,
        risk_config=risk_config,
    )


def _replay_dynamic_risk(
    path: pd.DataFrame,
    decisions: pd.DataFrame,
    risk: object,
    costs: object,
    *,
    contract_multiplier: float,
    max_abs_contracts: float,
    risk_config: Mapping[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    work = path.copy().reset_index(drop=True)
    work["trade_date"] = pd.to_datetime(work["trade_date"], utc=True, errors="raise")
    work["session_open"] = pd.to_datetime(work["session_open"], utc=True, errors="raise")
    policy = _validate_policy(decisions)
    _validate_fill_alignment(work, policy)
    policy["trade_date"] = policy["fill_trade_date"]
    if policy["trade_date"].duplicated().any():
        raise ValueError("issue430 policy decisions must be unique by trade date")
    cap = _finite_float(max_abs_contracts, "research contract cap")
    multiplier = _finite_float(contract_multiplier, "contract multiplier")
    if cap <= 0.0 or multiplier <= 0.0:
        raise ValueError("issue430 replay cap and contract multiplier must be positive")
    requested = pd.to_numeric(policy["signal_requested_position"], errors="raise").astype(float)
    _require_finite_series(requested, "requested research positions")
    if requested.abs().gt(cap + 1e-12).any():
        raise ValueError("issue430 requested research size exceeds declared contract cap")
    decision_map = policy.set_index("trade_date")

    equity = _finite_float(risk.capital_usd, "starting capital")
    starting_capital = equity
    peak_equity = equity
    previous_position = 0.0
    previous_contract: str | None = None
    active_position = 0.0
    active_target_end: pd.Timestamp | None = None
    active_uncertainty_usd = 0.0
    active_age = 0
    cumulative_unit_pnl = 0.0
    path_exit_reason: str | None = None
    killed = False
    kill_reason: str | None = None
    rows: list[dict[str, object]] = []

    drawdown_threshold_raw = risk_config.get("drawdown_threshold_fraction")
    drawdown_threshold = (
        None if drawdown_threshold_raw is None
        else _finite_float(drawdown_threshold_raw, "drawdown threshold")
    )
    drawdown_scale = _finite_float(risk_config.get("drawdown_scale", 1.0), "drawdown scale")
    stop_raw = risk_config.get("stop_loss_uncertainty_multiple")
    stop_multiple = None if stop_raw is None else _finite_float(stop_raw, "stop-loss multiple")
    take_raw = risk_config.get("take_profit_uncertainty_multiple")
    take_multiple = None if take_raw is None else _finite_float(take_raw, "take-profit multiple")
    max_hold = risk_config.get("max_hold_sessions")
    margin_per_contract = _finite_float(
        costs.initial_margin_usd_per_contract, "initial margin per contract"
    )
    per_side_cost = _finite_float(costs.per_side_usd, "per-side transaction cost")
    daily_loss_fraction = _finite_float(risk.daily_loss_fraction, "daily loss fraction")
    peak_drawdown_kill = _finite_float(
        risk.peak_drawdown_kill_fraction, "peak drawdown kill fraction"
    )
    if drawdown_threshold is not None and not 0.0 <= drawdown_threshold < 1.0:
        raise ValueError("issue430 drawdown threshold must be in [0,1)")
    if not 0.0 <= drawdown_scale <= 1.0:
        raise ValueError("issue430 drawdown scale must be in [0,1]")
    if stop_multiple is not None and stop_multiple < 0.0:
        raise ValueError("issue430 stop-loss multiple must be nonnegative")
    if take_multiple is not None and take_multiple < 0.0:
        raise ValueError("issue430 take-profit multiple must be nonnegative")
    if margin_per_contract < 0.0 or per_side_cost < 0.0:
        raise ValueError("issue430 margin and execution costs must be nonnegative")
    if not 0.0 <= daily_loss_fraction < 1.0 or not 0.0 <= peak_drawdown_kill < 1.0:
        raise ValueError("issue430 inherited risk fractions must be in [0,1)")
    if max_hold is not None and int(max_hold) < 1:
        raise ValueError("issue430 max hold must be positive")

    for index, session in work.iterrows():
        trade_date = pd.Timestamp(session["trade_date"])
        session_open = pd.Timestamp(session["session_open"])
        current_contract = str(session["contract_id"])
        if trade_date in decision_map.index:
            decision = decision_map.loc[trade_date]
            active_position = _finite_float(
                decision["signal_requested_position"], "active requested position"
            )
            target_end = decision.get("target_end_timestamp")
            active_target_end = None if pd.isna(target_end) else pd.Timestamp(target_end)
            uncertainty = decision.get("uncertainty_usd", 0.0)
            active_uncertainty_usd = (
                0.0 if pd.isna(uncertainty)
                else abs(_finite_float(uncertainty, "active uncertainty"))
            )
            active_age = 0
            cumulative_unit_pnl = 0.0
            path_exit_reason = None
        elif active_target_end is not None and session_open >= active_target_end:
            active_position = 0.0
            active_target_end = None
            active_age = 0
            cumulative_unit_pnl = 0.0
            path_exit_reason = "forecast_horizon_expired"

        pre_drawdown = (
            0.0 if peak_equity <= 0.0 else max(0.0, (peak_equity - equity) / peak_equity)
        )
        target_position = active_position
        soft_drawdown_scaled = False
        if drawdown_threshold is not None and pre_drawdown >= float(drawdown_threshold):
            target_position *= drawdown_scale
            soft_drawdown_scaled = True
        if path_exit_reason not in (None, "forecast_horizon_expired"):
            target_position = 0.0
        if max_hold is not None and active_position != 0.0 and active_age >= int(max_hold):
            target_position = 0.0
            path_exit_reason = "time_stop"
        risk_shutdown = bool(killed)
        if risk_shutdown:
            target_position = 0.0
        no_trade_reason = path_exit_reason if target_position == 0.0 else None
        if risk_shutdown:
            no_trade_reason = "risk_killed_until_explicit_operator_restart"
        if index == len(work) - 1:
            target_position = 0.0
            no_trade_reason = "end_of_sample_liquidation"
        contract_changed = (
            previous_position != 0.0
            and previous_contract is not None
            and previous_contract != current_contract
        )
        order_delta = target_position - previous_position
        execution_sides = (
            abs(previous_position) + abs(target_position)
            if contract_changed else abs(order_delta)
        )
        transaction_cost = _finite_float(
            execution_sides * per_side_cost, "transaction cost"
        )
        margin_required = _finite_float(
            margin_per_contract * abs(target_position), "margin requirement"
        )
        post_cost_equity = _finite_float(equity - transaction_cost, "post-cost equity")
        if (
            target_position != 0.0
            and (post_cost_equity <= 0.0 or margin_required > post_cost_equity)
        ):
            target_position = 0.0
            no_trade_reason = "insufficient_margin_assumption"
            order_delta = target_position - previous_position
            execution_sides = abs(previous_position) if contract_changed else abs(order_delta)
            transaction_cost = _finite_float(
                execution_sides * per_side_cost, "transaction cost"
            )

        equity_before = equity
        equity = _finite_float(equity - transaction_cost, "post-cost equity")
        path_move = session["path_move_per_mmbtu"]
        move = 0.0 if pd.isna(path_move) else _finite_float(path_move, "session path move")
        gross_pnl = _finite_float(target_position * move * multiplier, "gross pnl")
        equity = _finite_float(equity + gross_pnl, "updated equity")
        net_pnl = _finite_float(gross_pnl - transaction_cost, "net pnl")
        peak_equity = max(peak_equity, equity)
        daily_loss_usd = max(0.0, equity_before - equity)
        drawdown = (
            0.0 if peak_equity <= 0.0
            else max(0.0, (peak_equity - equity) / peak_equity)
        )
        triggers: list[str] = []
        if daily_loss_usd >= starting_capital * daily_loss_fraction:
            triggers.append("daily_loss_limit")
        if drawdown >= peak_drawdown_kill:
            triggers.append("peak_drawdown_kill")
        if triggers and not killed:
            killed = True
            kill_reason = "+".join(triggers)

        if target_position != 0.0 and not pd.isna(path_move):
            unit_pnl = _finite_float(
                (1.0 if target_position > 0.0 else -1.0) * move * multiplier,
                "unit path pnl",
            )
            cumulative_unit_pnl = _finite_float(
                cumulative_unit_pnl + unit_pnl, "cumulative unit path pnl"
            )
        path_trigger_after_session: str | None = None
        if active_uncertainty_usd > 0.0 and target_position != 0.0:
            stop_threshold = (
                None if stop_multiple is None
                else _finite_float(
                    stop_multiple * active_uncertainty_usd, "stop-loss threshold"
                )
            )
            take_threshold = (
                None if take_multiple is None
                else _finite_float(
                    take_multiple * active_uncertainty_usd, "take-profit threshold"
                )
            )
            if stop_threshold is not None and cumulative_unit_pnl <= -stop_threshold:
                path_trigger_after_session = "stop_loss"
            elif take_threshold is not None and cumulative_unit_pnl >= take_threshold:
                path_trigger_after_session = "take_profit"
        if path_trigger_after_session is not None:
            path_exit_reason = path_trigger_after_session
        if target_position != 0.0:
            active_age += 1

        rows.append(
            {
                "trade_date": trade_date,
                "session_open": session["session_open"],
                "contract_id": current_contract,
                "signal_requested_position": float(active_position),
                "prior_target_position": float(previous_position),
                "target_position": float(target_position),
                "order_delta": float(order_delta),
                "execution_side_count": float(execution_sides),
                "roll_side_count": float(execution_sides if contract_changed else 0.0),
                "transaction_cost_usd": float(transaction_cost),
                "gross_pnl_usd": float(gross_pnl),
                "net_pnl_usd": float(net_pnl),
                "equity_usd": float(equity),
                "peak_equity_usd": float(peak_equity),
                "daily_loss_usd": float(daily_loss_usd),
                "drawdown_fraction": float(drawdown),
                "pre_session_drawdown_fraction": float(pre_drawdown),
                "soft_drawdown_scaled": bool(soft_drawdown_scaled),
                "path_risk_exit_reason": path_exit_reason,
                "path_risk_trigger_after_session": path_trigger_after_session,
                "risk_state": "killed" if killed else "active",
                "kill_reason": kill_reason,
                "no_trade_reason": no_trade_reason,
                "roll_at_open": bool(contract_changed),
                "next_selected_contract_id": session["next_selected_contract_id"],
            }
        )
        previous_position = target_position
        previous_contract = current_contract if target_position != 0.0 else None

    ledger = pd.DataFrame(rows)
    diagnostics = _exposure_diagnostics(
        work, ledger, costs=costs, contract_multiplier=multiplier
    )
    summary: dict[str, object] = {
        "starting_capital_usd": starting_capital,
        "ending_equity_usd": float(equity),
        "net_pnl_usd": float(equity - starting_capital),
        "total_transaction_cost_usd": float(ledger["transaction_cost_usd"].sum()),
        "execution_side_count": float(ledger["execution_side_count"].sum()),
        "max_drawdown_fraction": float(ledger["drawdown_fraction"].max()),
        "max_abs_contracts": float(ledger["target_position"].abs().max()),
        "risk_shutdown_sessions": int(ledger["risk_state"].eq("killed").sum()),
        "kill_triggered": bool(killed),
        "kill_reason": kill_reason,
        "operational_paper_max_contracts": int(risk.max_contracts),
        "research_contract_cap": cap,
        "research_max_abs_contracts": float(ledger["target_position"].abs().max()),
        "soft_drawdown_scaled_sessions": int(ledger["soft_drawdown_scaled"].sum()),
        "stop_trigger_count": int(ledger["path_risk_trigger_after_session"].eq("stop_loss").sum()),
        "take_profit_trigger_count": int(ledger["path_risk_trigger_after_session"].eq("take_profit").sum()),
        "research_only_not_execution_authority": True,
    }
    summary.update(diagnostics)
    return ledger, summary


def apply_additional_loss_cooldown(policy: pd.DataFrame, cooldown_sessions: int) -> pd.DataFrame:
    if cooldown_sessions < 0:
        raise ValueError("issue430 cooldown sessions must be nonnegative")
    out = _validate_policy(policy).sort_values("fill_timestamp").reset_index(drop=True)
    if cooldown_sessions == 0:
        return out
    if "net_trade_utility_usd" not in out.columns:
        raise ValueError("issue430 cooldown requires net_trade_utility_usd")
    source = pd.to_numeric(out["signal_requested_position"], errors="raise").astype(float)
    accepted: list[dict[str, object]] = []
    observed_losses: set[int] = set()
    remaining = 0
    revised: list[float] = []
    for index, row in out.iterrows():
        fill = pd.Timestamp(row["fill_timestamp"])
        for item in accepted:
            item_index = int(item["index"])
            if item_index in observed_losses:
                continue
            if pd.Timestamp(item["target_end_timestamp"]) < fill:
                observed_losses.add(item_index)
                if float(item["net_trade_utility_usd"]) < 0.0:
                    remaining = max(remaining, cooldown_sessions)
        base = float(source.iloc[index])
        position = base
        if base != 0.0 and remaining > 0:
            position = 0.0
            remaining -= 1
        revised.append(position)
        if position != 0.0:
            accepted.append({
                "index": index,
                "target_end_timestamp": row["target_end_timestamp"],
                "net_trade_utility_usd": row["net_trade_utility_usd"],
            })
    out["signal_requested_position"] = revised
    out["issue430_additional_loss_cooldown_sessions"] = int(cooldown_sessions)
    return out
