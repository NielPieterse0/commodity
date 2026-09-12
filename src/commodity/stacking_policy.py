from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy


class Phase5PolicyError(ValueError):
    """Raised when the frozen Phase-5 policy contract is violated."""


_SHORT_MODES = {"none", "half", "veto"}
_LONG_MODES = {"none", "half", "veto"}
_PATH_MODES = {"none", "half"}
_UNCERTAINTY_MODES = {"none", "half_high"}
_ALLOWED_POSITION_LEVELS = {-1.0, -0.5, 0.0, 0.5, 1.0}
_PROTECTED_START = pd.Timestamp("2023-01-01T00:00:00Z")


@dataclass(frozen=True)
class PolicyConfig:
    config_id: str
    short_mode: str
    long_mode: str
    path_mode: str
    uncertainty_mode: str

    def __post_init__(self) -> None:
        if self.short_mode not in _SHORT_MODES:
            raise Phase5PolicyError(f"unsupported short modifier: {self.short_mode}")
        if self.long_mode not in _LONG_MODES:
            raise Phase5PolicyError(f"unsupported long modifier: {self.long_mode}")
        if self.path_mode not in _PATH_MODES:
            raise Phase5PolicyError(f"unsupported path modifier: {self.path_mode}")
        if self.uncertainty_mode not in _UNCERTAINTY_MODES:
            raise Phase5PolicyError(f"unsupported uncertainty modifier: {self.uncertainty_mode}")
        if not self.config_id:
            raise Phase5PolicyError("policy config ID must be non-empty")

    @property
    def complexity(self) -> int:
        return sum(
            value != "none"
            for value in (
                self.short_mode,
                self.long_mode,
                self.path_mode,
                self.uncertainty_mode,
            )
        )


@dataclass(frozen=True)
class PolicyDecision:
    position: float
    modifiers: tuple[str, ...]


def build_policy_grid() -> list[PolicyConfig]:
    configs: list[PolicyConfig] = []
    for short_mode, long_mode, path_mode, uncertainty_mode in itertools.product(
        ("none", "half", "veto"),
        ("none", "half", "veto"),
        ("none", "half"),
        ("none", "half_high"),
    ):
        config_id = (
            f"s-{short_mode}__l-{long_mode}__p-{path_mode}__u-{uncertainty_mode}"
        )
        configs.append(
            PolicyConfig(
                config_id=config_id,
                short_mode=short_mode,
                long_mode=long_mode,
                path_mode=path_mode,
                uncertainty_mode=uncertainty_mode,
            )
        )
    if len(configs) != 36 or len({item.config_id for item in configs}) != 36:
        raise Phase5PolicyError("frozen Phase-5 grid must contain exactly 36 unique configs")
    return configs


def validate_phase5_evidence_boundary(
    frame: pd.DataFrame,
    *,
    date_column: str = "trade_date",
) -> None:
    if date_column not in frame.columns:
        raise Phase5PolicyError(f"Phase-5 evidence missing date column: {date_column}")
    values = pd.to_datetime(frame[date_column], utc=True, errors="coerce")
    if values.isna().any():
        raise Phase5PolicyError("Phase-5 evidence contains invalid timestamps")
    if (values >= _PROTECTED_START).any():
        raise Phase5PolicyError("protected 2023+ confirmation evidence is forbidden in Phase 5")


def _finite_float(value: object, label: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise Phase5PolicyError(f"{label} must be finite")
    return parsed


def fit_timesfm_uncertainty_state(
    history: pd.DataFrame,
    *,
    boundary_timestamp: pd.Timestamp,
    minimum_rows: int = 50,
) -> dict[str, Any]:
    required = {"fill_timestamp", "timesfm_interval_width", "baseline_abs_error"}
    missing = sorted(required - set(history.columns))
    if missing:
        raise Phase5PolicyError(f"uncertainty calibration missing columns: {missing}")
    boundary = pd.Timestamp(boundary_timestamp)
    if boundary.tzinfo is None:
        raise Phase5PolicyError("uncertainty boundary must be timezone-aware")
    if minimum_rows < 1:
        raise Phase5PolicyError("minimum uncertainty calibration rows must be positive")

    frame = history.copy()
    frame["fill_timestamp"] = pd.to_datetime(frame["fill_timestamp"], utc=True, errors="coerce")
    frame["timesfm_interval_width"] = pd.to_numeric(
        frame["timesfm_interval_width"], errors="coerce"
    )
    frame["baseline_abs_error"] = pd.to_numeric(frame["baseline_abs_error"], errors="coerce")
    frame = frame.loc[frame["fill_timestamp"].notna() & frame["fill_timestamp"].lt(boundary)].copy()
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["timesfm_interval_width", "baseline_abs_error"]
    )
    if (frame["timesfm_interval_width"] < 0).any() or (frame["baseline_abs_error"] < 0).any():
        raise Phase5PolicyError("uncertainty calibration values must be non-negative")

    rows = len(frame)
    state: dict[str, Any] = {
        "calibration_rows": rows,
        "minimum_rows": int(minimum_rows),
        "active": False,
        "association": None,
        "high_threshold": None,
    }
    if rows < minimum_rows:
        return state
    width_rank = frame["timesfm_interval_width"].rank(method="average")
    error_rank = frame["baseline_abs_error"].rank(method="average")
    association = float(width_rank.corr(error_rank))
    if not math.isfinite(association):
        association = 0.0
    state["association"] = association
    state["high_threshold"] = float(frame["timesfm_interval_width"].quantile(0.75))
    state["active"] = association > 0.0
    return state


def _half_position(position: float) -> float:
    if position == 0.0:
        return 0.0
    return math.copysign(min(abs(position), 0.5), position)


def apply_specialist_modifiers(
    *,
    baseline_position: float,
    timesfm_point_return: float,
    kronos_close_return: float,
    kronos_terminal_return: float | None,
    timesfm_interval_width: float,
    config: PolicyConfig,
    uncertainty_state: dict[str, Any] | None,
) -> PolicyDecision:
    position = _finite_float(baseline_position, "baseline position")
    if position not in {-1.0, 0.0, 1.0}:
        raise Phase5PolicyError("baseline position must be -1, 0 or +1")
    if position == 0.0:
        return PolicyDecision(position=0.0, modifiers=())

    timesfm = _finite_float(timesfm_point_return, "TimesFM point return")
    kronos = _finite_float(kronos_close_return, "Kronos close return")
    width = _finite_float(timesfm_interval_width, "TimesFM interval width")
    if width < 0:
        raise Phase5PolicyError("TimesFM interval width must be non-negative")
    modifiers: list[str] = []

    if position < 0 and timesfm >= 0 and config.short_mode != "none":
        if config.short_mode == "veto":
            position = 0.0
            modifiers.append("timesfm_short_veto")
        else:
            position = _half_position(position)
            modifiers.append("timesfm_short_half")

    if position > 0 and kronos <= 0 and config.long_mode != "none":
        if config.long_mode == "veto":
            position = 0.0
            modifiers.append("kronos_long_veto")
        else:
            position = _half_position(position)
            modifiers.append("kronos_long_half")

    if (
        position != 0.0
        and config.path_mode == "half"
        and kronos_terminal_return is not None
    ):
        terminal = _finite_float(kronos_terminal_return, "Kronos terminal return")
        if terminal != 0.0 and math.copysign(1.0, terminal) != math.copysign(1.0, baseline_position):
            position = _half_position(position)
            modifiers.append("kronos_path_half")

    if position != 0.0 and config.uncertainty_mode == "half_high" and uncertainty_state:
        active = bool(uncertainty_state.get("active", False))
        threshold = uncertainty_state.get("high_threshold")
        if active and threshold is not None and width >= float(threshold):
            position = _half_position(position)
            modifiers.append("timesfm_uncertainty_half")

    if position not in _ALLOWED_POSITION_LEVELS:
        raise Phase5PolicyError(f"policy produced non-frozen position level: {position}")
    return PolicyDecision(position=position, modifiers=tuple(modifiers))


def replay_fractional_policy(
    path: pd.DataFrame,
    decisions: pd.DataFrame,
    risk: PaperRiskPolicy,
    costs: ExecutionCostAssumptions,
    *,
    contract_multiplier: float,
    enforce_risk: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_path = {
        "trade_date",
        "contract_id",
        "session_open",
        "path_move_per_mmbtu",
        "next_selected_contract_id",
    }
    missing = sorted(required_path - set(path.columns))
    if missing:
        raise Phase5PolicyError(f"session path missing replay columns: {missing}")
    required_decisions = {"trade_date", "signal_requested_position"}
    missing = sorted(required_decisions - set(decisions.columns))
    if missing:
        raise Phase5PolicyError(f"policy decisions missing columns: {missing}")
    validate_phase5_evidence_boundary(path)
    validate_phase5_evidence_boundary(decisions)
    multiplier = _finite_float(contract_multiplier, "contract multiplier")
    if multiplier <= 0:
        raise Phase5PolicyError("contract multiplier must be positive")

    work_path = path.copy().reset_index(drop=True)
    work_path["trade_date"] = pd.to_datetime(work_path["trade_date"], utc=True, errors="coerce")
    work_decisions = decisions.copy()
    work_decisions["trade_date"] = pd.to_datetime(
        work_decisions["trade_date"], utc=True, errors="coerce"
    )
    if work_decisions["trade_date"].duplicated().any():
        raise Phase5PolicyError("policy decisions must be unique by trade date")
    decision_map = work_decisions.set_index("trade_date")

    equity = float(risk.capital_usd)
    peak_equity = equity
    previous_position = 0.0
    previous_contract: str | None = None
    active_signal_position = 0.0
    active_signal_reason = "no_signal_yet"
    active_forecast_id: str | None = None
    active_target_end: pd.Timestamp | None = None
    killed = False
    kill_reason: str | None = None
    rows: list[dict[str, Any]] = []

    for index, session in work_path.iterrows():
        trade_date = pd.Timestamp(session["trade_date"])
        session_open = pd.Timestamp(session["session_open"])
        current_contract = str(session["contract_id"])
        if trade_date in decision_map.index:
            decision = decision_map.loc[trade_date]
            active_signal_position = _finite_float(
                decision["signal_requested_position"], "signal requested position"
            )
            if active_signal_position not in _ALLOWED_POSITION_LEVELS:
                raise Phase5PolicyError("signal requested position is outside the frozen levels")
            active_signal_reason = str(decision.get("signal_reason", "forecast_signal"))
            value = decision.get("forecast_id")
            active_forecast_id = None if pd.isna(value) else str(value)
            target_end_value = decision.get("target_end_timestamp")
            active_target_end = (
                None
                if target_end_value is None or pd.isna(target_end_value)
                else pd.Timestamp(target_end_value)
            )
        elif active_target_end is not None and session_open >= active_target_end:
            active_signal_position = 0.0
            active_signal_reason = "forecast_horizon_expired"
            active_forecast_id = None
            active_target_end = None

        signal_position = active_signal_position
        signal_abstained = signal_position == 0.0
        risk_shutdown = bool(enforce_risk and killed)
        target_position = 0.0 if risk_shutdown else signal_position
        no_trade_reason = active_signal_reason if signal_abstained else None
        if risk_shutdown:
            no_trade_reason = "risk_killed_until_explicit_operator_restart"
        if index == len(work_path) - 1:
            target_position = 0.0
            no_trade_reason = "end_of_sample_liquidation"
        if (
            target_position != 0.0
            and costs.initial_margin_usd_per_contract * abs(target_position) > equity
        ):
            target_position = 0.0
            no_trade_reason = "insufficient_margin_assumption"

        contract_changed = (
            previous_position != 0.0
            and previous_contract is not None
            and previous_contract != current_contract
        )
        order_delta = target_position - previous_position
        if contract_changed:
            execution_sides = abs(previous_position) + abs(target_position)
            roll_sides = execution_sides
        else:
            execution_sides = abs(order_delta)
            roll_sides = 0.0
        transaction_cost = execution_sides * float(costs.per_side_usd)
        equity_before = equity
        equity -= transaction_cost

        path_move = session["path_move_per_mmbtu"]
        gross_pnl = 0.0 if pd.isna(path_move) else target_position * float(path_move) * multiplier
        equity += gross_pnl
        net_pnl = gross_pnl - transaction_cost
        peak_equity = max(peak_equity, equity)
        daily_loss_usd = max(0.0, equity_before - equity)
        drawdown = 0.0 if peak_equity <= 0 else max(0.0, (peak_equity - equity) / peak_equity)
        trigger_reasons: list[str] = []
        if enforce_risk and daily_loss_usd >= risk.capital_usd * risk.daily_loss_fraction:
            trigger_reasons.append("daily_loss_limit")
        if enforce_risk and drawdown >= risk.peak_drawdown_kill_fraction:
            trigger_reasons.append("peak_drawdown_kill")
        if trigger_reasons and not killed:
            killed = True
            kill_reason = "+".join(trigger_reasons)

        rows.append(
            {
                "trade_date": trade_date,
                "session_open": session["session_open"],
                "contract_id": current_contract,
                "forecast_id": active_forecast_id,
                "signal_requested_position": float(signal_position),
                "signal_abstained": bool(signal_abstained),
                "risk_shutdown": bool(risk_shutdown),
                "prior_target_position": float(previous_position),
                "target_position": float(target_position),
                "order_delta": float(order_delta),
                "execution_side_count": float(execution_sides),
                "roll_side_count": float(roll_sides),
                "transaction_cost_usd": float(transaction_cost),
                "gross_pnl_usd": float(gross_pnl),
                "net_pnl_usd": float(net_pnl),
                "equity_usd": float(equity),
                "peak_equity_usd": float(peak_equity),
                "daily_loss_usd": float(daily_loss_usd),
                "drawdown_fraction": float(drawdown),
                "risk_state": "killed" if killed else "active",
                "kill_reason": kill_reason,
                "no_trade_reason": no_trade_reason,
                "signal_reason": active_signal_reason,
                "roll_at_open": bool(contract_changed),
                "next_selected_contract_id": session["next_selected_contract_id"],
            }
        )
        previous_position = target_position
        previous_contract = current_contract if target_position != 0.0 else None

    ledger = pd.DataFrame(rows)
    summary = {
        "starting_capital_usd": float(risk.capital_usd),
        "ending_equity_usd": float(equity),
        "net_pnl_usd": float(equity - risk.capital_usd),
        "total_transaction_cost_usd": float(ledger["transaction_cost_usd"].sum()),
        "execution_side_count": float(ledger["execution_side_count"].sum()),
        "max_drawdown_fraction": float(ledger["drawdown_fraction"].max()) if len(ledger) else 0.0,
        "max_abs_contracts": float(ledger["target_position"].abs().max()) if len(ledger) else 0.0,
        "signal_abstention_sessions": int(ledger["signal_abstained"].sum()),
        "risk_shutdown_sessions": int(ledger["risk_shutdown"].sum()),
        "kill_triggered": bool(killed),
        "kill_reason": kill_reason,
        "risk_enforced": bool(enforce_risk),
        "live_trading_allowed": False,
    }
    return ledger, summary


def select_policy_from_prior_oos(
    scores: pd.DataFrame,
    *,
    outer_start_year: int,
) -> dict[str, Any]:
    required = {
        "config_id",
        "year",
        "net_pnl_usd",
        "transaction_cost_usd",
        "complexity",
    }
    missing = sorted(required - set(scores.columns))
    if missing:
        raise Phase5PolicyError(f"policy score frame missing columns: {missing}")

    prior = scores.loc[pd.to_numeric(scores["year"], errors="coerce") < int(outer_start_year)].copy()
    if prior.empty:
        raise Phase5PolicyError("no prior OOS policy scores exist before the outer boundary")
    prior["year"] = prior["year"].astype(int)
    expected_years = sorted(prior["year"].unique().tolist())
    rows: list[dict[str, Any]] = []
    for config_id, group in prior.groupby("config_id", sort=True):
        years = sorted(group["year"].unique().tolist())
        if years != expected_years or group["year"].duplicated().any():
            continue
        net = pd.to_numeric(group["net_pnl_usd"], errors="coerce")
        costs = pd.to_numeric(group["transaction_cost_usd"], errors="coerce")
        complexity_values = pd.to_numeric(group["complexity"], errors="coerce")
        if net.isna().any() or costs.isna().any() or complexity_values.isna().any():
            continue
        complexity_unique = sorted(set(complexity_values.astype(int).tolist()))
        if len(complexity_unique) != 1:
            raise Phase5PolicyError("configuration complexity changed across OOS years")
        rows.append(
            {
                "config_id": str(config_id),
                "years": years,
                "median_yearly_net_pnl_usd": float(net.median()),
                "worst_yearly_net_pnl_usd": float(net.min()),
                "total_net_pnl_usd": float(net.sum()),
                "transaction_cost_usd": float(costs.sum()),
                "complexity": int(complexity_unique[0]),
            }
        )
    if not rows:
        raise Phase5PolicyError("no configuration has complete prior-OOS policy evidence")
    ranking = pd.DataFrame(rows).sort_values(
        [
            "median_yearly_net_pnl_usd",
            "worst_yearly_net_pnl_usd",
            "total_net_pnl_usd",
            "transaction_cost_usd",
            "complexity",
            "config_id",
        ],
        ascending=[False, False, False, True, True, True],
        kind="stable",
    )
    selected = ranking.iloc[0].to_dict()
    selected["years"] = [int(value) for value in selected["years"]]
    selected["ranking"] = ranking.to_dict("records")
    return selected


def _build_policy_decisions(
    forecasts: pd.DataFrame,
    timesfm: pd.DataFrame,
    kronos: pd.DataFrame,
    kronos_path: pd.DataFrame,
    *,
    config: PolicyConfig,
    costs: ExecutionCostAssumptions,
    uncertainty_state: dict[str, Any] | None,
    enforce_phase5_boundary: bool,
    require_realized_path: bool,
) -> pd.DataFrame:
    required_forecast = {
        "trade_date",
        "signal_timestamp",
        "fill_trade_date",
        "fill_timestamp",
        "target_end_timestamp",
        "forecast_id",
        "predicted_gross_pnl_usd",
        "predicted_path_move_per_mmbtu",
    }
    if require_realized_path:
        required_forecast.add("actual_path_move_per_mmbtu")
    missing = sorted(required_forecast - set(forecasts.columns))
    if missing:
        raise Phase5PolicyError(f"baseline forecasts missing columns: {missing}")
    required_timesfm = {
        "trade_date",
        "prediction_time",
        "timesfm_point_return",
        "timesfm_interval_width",
    }
    required_kronos = {"trade_date", "prediction_time", "kronos_close_return"}
    if required_timesfm - set(timesfm.columns):
        raise Phase5PolicyError("TimesFM feature contract is incomplete")
    if required_kronos - set(kronos.columns):
        raise Phase5PolicyError("Kronos feature contract is incomplete")

    base = forecasts.copy()
    base["trade_date"] = pd.to_datetime(base["trade_date"], utc=True, errors="coerce", format="mixed")
    if enforce_phase5_boundary:
        validate_phase5_evidence_boundary(base)
    for frame in (timesfm, kronos):
        if frame["trade_date"].duplicated().any():
            raise Phase5PolicyError("specialist features must be unique by origin trade date")

    t = timesfm[
        ["trade_date", "prediction_time", "timesfm_point_return", "timesfm_interval_width"]
    ].copy()
    k = kronos[["trade_date", "prediction_time", "kronos_close_return"]].copy()
    t["trade_date"] = pd.to_datetime(t["trade_date"], utc=True, errors="coerce", format="mixed")
    k["trade_date"] = pd.to_datetime(k["trade_date"], utc=True, errors="coerce", format="mixed")
    t = t.rename(columns={"prediction_time": "timesfm_prediction_time"})
    k = k.rename(columns={"prediction_time": "kronos_prediction_time"})
    merged = base.merge(t, on="trade_date", how="left", validate="many_to_one")
    merged = merged.merge(k, on="trade_date", how="left", validate="many_to_one")
    if merged[["timesfm_point_return", "timesfm_interval_width", "kronos_close_return"]].isna().any().any():
        raise Phase5PolicyError("full specialist feature coverage is incomplete at baseline origins")

    path_columns = ["trade_date", "pred_terminal_return"]
    if not kronos_path.empty:
        missing_path = sorted(set(path_columns) - set(kronos_path.columns))
        if missing_path:
            raise Phase5PolicyError(f"Kronos path feature contract missing columns: {missing_path}")
        p = kronos_path[path_columns].copy()
        p["trade_date"] = pd.to_datetime(p["trade_date"], utc=True, errors="coerce", format="mixed")
        if p["trade_date"].duplicated().any():
            raise Phase5PolicyError("Kronos path features must be unique by origin trade date")
        merged = merged.merge(p, on="trade_date", how="left", validate="many_to_one")
    else:
        merged["pred_terminal_return"] = np.nan

    signal_time = pd.to_datetime(merged["signal_timestamp"], utc=True, errors="coerce", format="mixed")
    timesfm_time = pd.to_datetime(merged["timesfm_prediction_time"], utc=True, errors="coerce", format="mixed")
    kronos_time = pd.to_datetime(merged["kronos_prediction_time"], utc=True, errors="coerce", format="mixed")
    if signal_time.isna().any() or timesfm_time.isna().any() or kronos_time.isna().any():
        raise Phase5PolicyError("policy join contains invalid prediction timestamps")
    if (timesfm_time.dt.floor("us") != signal_time.dt.floor("us")).any():
        raise Phase5PolicyError("TimesFM feature does not match the baseline information cutoff")
    if (kronos_time.dt.floor("us") != signal_time.dt.floor("us")).any():
        raise Phase5PolicyError("Kronos feature does not match the baseline information cutoff")

    decisions: list[dict[str, Any]] = []
    for row in merged.itertuples(index=False):
        predicted_gross = _finite_float(row.predicted_gross_pnl_usd, "baseline predicted gross P&L")
        if abs(predicted_gross) <= float(costs.round_trip_usd):
            baseline_position = 0.0
            baseline_reason = "predicted_gross_pnl_not_above_round_trip_cost"
        else:
            baseline_position = 1.0 if predicted_gross > 0 else -1.0
            baseline_reason = "forecast_signal"
        terminal_value = None if pd.isna(row.pred_terminal_return) else float(row.pred_terminal_return)
        modified = apply_specialist_modifiers(
            baseline_position=baseline_position,
            timesfm_point_return=float(row.timesfm_point_return),
            kronos_close_return=float(row.kronos_close_return),
            kronos_terminal_return=terminal_value,
            timesfm_interval_width=float(row.timesfm_interval_width),
            config=config,
            uncertainty_state=uncertainty_state,
        )
        if baseline_position == 0.0:
            reason = baseline_reason
        elif modified.position == 0.0:
            reason = "specialist_veto"
        elif modified.modifiers:
            reason = "specialist_sizing_modifier"
        else:
            reason = "forecast_signal"
        decisions.append(
            {
                "trade_date": pd.Timestamp(row.fill_trade_date),
                "origin_trade_date": pd.Timestamp(row.trade_date),
                "signal_timestamp": pd.Timestamp(row.signal_timestamp),
                "fill_timestamp": pd.Timestamp(row.fill_timestamp),
                "target_end_timestamp": pd.Timestamp(row.target_end_timestamp),
                "forecast_id": str(row.forecast_id),
                "baseline_position": float(baseline_position),
                "signal_requested_position": float(modified.position),
                "signal_reason": reason,
                "modifiers": "+".join(modified.modifiers),
                "timesfm_interval_width": float(row.timesfm_interval_width),
                "baseline_abs_error": (
                    abs(
                        float(row.actual_path_move_per_mmbtu)
                        - float(row.predicted_path_move_per_mmbtu)
                    )
                    if require_realized_path
                    else float("nan")
                ),
                "kronos_path_available": terminal_value is not None,
            }
        )
    result = pd.DataFrame(decisions)
    if result["trade_date"].duplicated().any():
        raise Phase5PolicyError("policy decisions are not unique by executable fill date")
    return result.sort_values("trade_date").reset_index(drop=True)


def build_policy_decisions(
    forecasts: pd.DataFrame,
    timesfm: pd.DataFrame,
    kronos: pd.DataFrame,
    kronos_path: pd.DataFrame,
    *,
    config: PolicyConfig,
    costs: ExecutionCostAssumptions,
    uncertainty_state: dict[str, Any] | None,
) -> pd.DataFrame:
    """Build Phase-5 historical decisions with realized-path diagnostics."""
    return _build_policy_decisions(
        forecasts,
        timesfm,
        kronos,
        kronos_path,
        config=config,
        costs=costs,
        uncertainty_state=uncertainty_state,
        enforce_phase5_boundary=True,
        require_realized_path=True,
    )


def build_prospective_policy_decisions(
    forecasts: pd.DataFrame,
    timesfm: pd.DataFrame,
    kronos: pd.DataFrame,
    kronos_path: pd.DataFrame,
    *,
    config: PolicyConfig,
    costs: ExecutionCostAssumptions,
    uncertainty_state: dict[str, Any] | None,
) -> pd.DataFrame:
    """Build outcome-blind decisions for post-freeze prospective operation.

    The policy logic is identical to Phase 5, but the decision-time path neither
    consumes realized path movement nor applies the historical protected-period
    boundary. Prospective callers remain responsible for the Phase-7 freeze and
    input-availability contract.
    """
    return _build_policy_decisions(
        forecasts,
        timesfm,
        kronos,
        kronos_path,
        config=config,
        costs=costs,
        uncertainty_state=uncertainty_state,
        enforce_phase5_boundary=False,
        require_realized_path=False,
    )
