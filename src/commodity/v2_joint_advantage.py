from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

_PROTECTED_START = pd.Timestamp("2023-01-01", tz="UTC")
_ALLOWED_SIDES = {"both", "long_only", "short_only"}
_ALLOWED_LIFECYCLES = {
    "inherited_horizon",
    "one_signal_per_target_window",
    "loss_cooldown_1_session",
    "loss_cooldown_3_sessions",
}


class JointAdvantageError(ValueError):
    pass


@dataclass(frozen=True)
class JointWave1Config:
    config_id: str
    side_scope: str
    gate_id: str
    position_fraction: float
    lifecycle: str
    cost_profile: str


@dataclass(frozen=True)
class JointWave2Config:
    config_id: str
    parent_policy_id: str
    short_mode: str
    long_mode: str


def build_wave1_configs(prereg: Mapping[str, Any]) -> list[JointWave1Config]:
    if prereg.get("status") != "frozen_before_issue459_scoring":
        raise JointAdvantageError("issue459 preregistration is not frozen")
    wave = prereg["wave1_joint_scarcity_repair"]
    configs: list[JointWave1Config] = []
    for side in wave["side_scopes"]:
        for gate in wave["gate_families"]:
            for fraction in wave["position_fractions"]:
                for lifecycle in wave["lifecycle_variants"]:
                    for cost in wave["cost_profiles"]:
                        config_id = (
                            f"{side}__{gate}__f{float(fraction):.2f}__"
                            f"{lifecycle}__{cost}"
                        )
                        configs.append(
                            JointWave1Config(
                                config_id=config_id,
                                side_scope=str(side),
                                gate_id=str(gate),
                                position_fraction=float(fraction),
                                lifecycle=str(lifecycle),
                                cost_profile=str(cost),
                            )
                        )
    expected = int(prereg["search_budget"]["wave1_declared_cartesian_upper_bound"])
    if len(configs) != expected or len({row.config_id for row in configs}) != expected:
        raise JointAdvantageError("issue459 frozen wave1 grid identity changed")
    return configs


def build_wave2_configs(prereg: Mapping[str, Any]) -> list[JointWave2Config]:
    if prereg.get("status") != "frozen_before_issue459_wave2_scoring":
        raise JointAdvantageError("issue459 wave2 preregistration is not frozen")
    parents = [str(value) for value in prereg["parent_wave1"]["eligible_parent_policy_ids"]]
    space = prereg["candidate_space"]
    configs: list[JointWave2Config] = []
    for parent in parents:
        for short_mode in space["short_modes"]:
            for long_mode in space["long_modes"]:
                if short_mode == "none" and long_mode == "none":
                    continue
                if parent.startswith("short_only__") and long_mode != "none":
                    continue
                config_id = f"{parent}__short_{short_mode}__long_{long_mode}"
                configs.append(
                    JointWave2Config(
                        config_id=config_id,
                        parent_policy_id=parent,
                        short_mode=str(short_mode),
                        long_mode=str(long_mode),
                    )
                )
    expected = int(space["expected_policy_count"])
    if len(configs) != expected or len({row.config_id for row in configs}) != expected:
        raise JointAdvantageError("issue459 frozen wave2 grid identity changed")
    return configs


def apply_wave2_specialists(
    frame: pd.DataFrame,
    config: JointWave2Config,
) -> pd.DataFrame:
    required = {"signal_requested_position", "timesfm_point_return", "kronos_close_return"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise JointAdvantageError(f"issue459 wave2 frame missing columns: {missing}")
    if config.short_mode not in {"none", "half", "veto"}:
        raise JointAdvantageError(f"unsupported issue459 wave2 short mode: {config.short_mode}")
    if config.long_mode not in {"none", "half", "veto"}:
        raise JointAdvantageError(f"unsupported issue459 wave2 long mode: {config.long_mode}")

    out = frame.copy()
    timestamp_columns = ("fill_timestamp", "target_end_timestamp", "signal_timestamp")
    missing_timestamps = sorted(set(timestamp_columns) - set(out.columns))
    if missing_timestamps:
        raise JointAdvantageError(
            f"issue459 wave2 frame missing provenance timestamps: {missing_timestamps}"
        )
    for timestamp_column in timestamp_columns:
        timestamps = pd.to_datetime(out[timestamp_column], utc=True, errors="raise")
        if (timestamps >= _PROTECTED_START).any():
            raise JointAdvantageError("issue459 wave2 protected 2023+ evidence is forbidden")
        out[timestamp_column] = timestamps
    if (out["signal_timestamp"] >= out["fill_timestamp"]).any():
        raise JointAdvantageError("issue459 wave2 signal timestamp must be before fill")
    if (out["target_end_timestamp"] <= out["fill_timestamp"]).any():
        raise JointAdvantageError("issue459 wave2 target end must be strictly after fill")
    positions = pd.to_numeric(out["signal_requested_position"], errors="raise").astype(float)
    allowed = {-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0}
    if not positions.isin(allowed).all():
        raise JointAdvantageError("issue459 wave2 requested position is outside frozen levels")
    timesfm = pd.to_numeric(out["timesfm_point_return"], errors="raise").astype(float)
    kronos = pd.to_numeric(out["kronos_close_return"], errors="raise").astype(float)
    if timesfm.isna().any() or kronos.isna().any():
        raise JointAdvantageError("issue459 wave2 specialist value is missing")

    short_disagreement = positions.lt(0.0) & timesfm.ge(0.0)
    long_disagreement = positions.gt(0.0) & kronos.le(0.0)
    revised = positions.copy()
    if config.short_mode == "half":
        revised.loc[short_disagreement] *= 0.5
    elif config.short_mode == "veto":
        revised.loc[short_disagreement] = 0.0
    if config.long_mode == "half":
        revised.loc[long_disagreement] *= 0.5
    elif config.long_mode == "veto":
        revised.loc[long_disagreement] = 0.0

    if ((positions.gt(0.0) & revised.lt(0.0)) | (positions.lt(0.0) & revised.gt(0.0))).any():
        raise JointAdvantageError("issue459 wave2 specialist rule flipped direction")
    out["signal_requested_position"] = revised
    out["wave2_short_modified"] = short_disagreement & revised.ne(positions)
    out["wave2_long_modified"] = long_disagreement & revised.ne(positions)
    out["wave2_config_id"] = config.config_id
    return out


def _validate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "signal_timestamp",
        "fill_timestamp",
        "target_end_timestamp",
        "signal_requested_position",
        "net_trade_utility_usd",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise JointAdvantageError(f"issue459 candidate frame missing columns: {missing}")
    out = frame.copy().sort_values("fill_timestamp", kind="stable").reset_index(drop=True)
    signal = pd.to_datetime(out["signal_timestamp"], utc=True, errors="raise")
    fill = pd.to_datetime(out["fill_timestamp"], utc=True, errors="raise")
    target_end = pd.to_datetime(out["target_end_timestamp"], utc=True, errors="raise")
    if (
        (signal >= _PROTECTED_START).any()
        or (fill >= _PROTECTED_START).any()
        or (target_end >= _PROTECTED_START).any()
    ):
        raise JointAdvantageError("issue459 protected 2023+ evidence is forbidden")
    if (signal >= fill).any():
        raise JointAdvantageError("issue459 signal timestamp must be before fill")
    if (target_end <= fill).any():
        raise JointAdvantageError("issue459 target end must be strictly after fill")
    positions = pd.to_numeric(out["signal_requested_position"], errors="raise").astype(float)
    if not positions.isin([-1.0, 0.0, 1.0]).all():
        raise JointAdvantageError("issue459 base requested positions must be -1, 0 or +1")
    out["signal_timestamp"] = signal
    out["fill_timestamp"] = fill
    out["target_end_timestamp"] = target_end
    out["signal_requested_position"] = positions
    out["net_trade_utility_usd"] = pd.to_numeric(
        out["net_trade_utility_usd"], errors="raise"
    ).astype(float)
    return out


def _side_allowed(position: float, side_scope: str) -> bool:
    if side_scope == "both":
        return position != 0.0
    if side_scope == "long_only":
        return position > 0.0
    if side_scope == "short_only":
        return position < 0.0
    raise JointAdvantageError(f"unsupported issue459 side scope: {side_scope}")


def apply_joint_candidate(
    frame: pd.DataFrame,
    config: JointWave1Config,
) -> pd.DataFrame:
    if config.side_scope not in _ALLOWED_SIDES:
        raise JointAdvantageError(f"unsupported issue459 side scope: {config.side_scope}")
    if config.lifecycle not in _ALLOWED_LIFECYCLES:
        raise JointAdvantageError(f"unsupported issue459 lifecycle: {config.lifecycle}")
    if not (0.0 < config.position_fraction <= 1.0):
        raise JointAdvantageError("issue459 position fraction must be in (0, 1]")

    out = _validate_frame(frame)
    source_position = out["signal_requested_position"].copy()
    accepted: list[dict[str, object]] = []
    requested: list[float] = []
    abstained: list[bool] = []
    active_target_end: pd.Timestamp | None = None
    cooldown_remaining = 0
    observed_losses: set[int] = set()
    cooldown_sessions = 1 if config.lifecycle == "loss_cooldown_1_session" else 3

    for index, row in out.iterrows():
        fill = pd.Timestamp(row["fill_timestamp"])
        if config.lifecycle.startswith("loss_cooldown_"):
            for item in accepted:
                item_index = int(item["index"])
                if item_index in observed_losses:
                    continue
                if pd.Timestamp(item["target_end_timestamp"]) < fill:
                    observed_losses.add(item_index)
                    if float(item["net_trade_utility_usd"]) < 0.0:
                        cooldown_remaining = max(cooldown_remaining, cooldown_sessions)

        base = float(source_position.iloc[index])
        allowed = _side_allowed(base, config.side_scope)
        if allowed and config.lifecycle == "one_signal_per_target_window":
            allowed = active_target_end is None or fill >= active_target_end
        if allowed and config.lifecycle.startswith("loss_cooldown_") and cooldown_remaining > 0:
            allowed = False
            cooldown_remaining -= 1

        position = base * config.position_fraction if allowed else 0.0
        requested.append(position)
        abstained.append(bool(base != 0.0 and position == 0.0))
        if position != 0.0:
            active_target_end = pd.Timestamp(row["target_end_timestamp"])
            accepted.append(
                {
                    "index": index,
                    "target_end_timestamp": row["target_end_timestamp"],
                    "net_trade_utility_usd": row["net_trade_utility_usd"],
                }
            )

    out["signal_requested_position"] = requested
    out["joint_abstained"] = abstained
    out["joint_config_id"] = config.config_id
    return out


_GATE_TO_ISSUE428_CONFIG_ID = {
    "baseline": "baseline",
    "model_agreement": "model-agreement",
    "strength_q50": "strength-q50",
    "strength_q65": "strength-q65",
    "strength_q80": "strength-q80",
    "favored_count_3": "favored-signals-ge3",
    "favored_count_4": "favored-signals-ge4",
    "vol_of_vol_veto_q75": "vol-of-vol-veto-q75",
    "vol_of_vol_veto_q90": "vol-of-vol-veto-q90",
    "meta_interactions_p55": "meta-interactions-p55",
    "meta_interactions_p60": "meta-interactions-p60",
}


def issue428_config_id_for_gate(gate_id: str) -> str:
    try:
        return _GATE_TO_ISSUE428_CONFIG_ID[str(gate_id)]
    except KeyError as exc:
        raise JointAdvantageError(f"unsupported issue459 gate: {gate_id}") from exc


def evaluate_wave1_policies(
    trials: pd.DataFrame,
    prereg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    required = {
        "policy_id",
        "outer_id",
        "cost_profile",
        "mean_monthly_net_return_delta",
        "selected_trades",
        "nonempty_months",
        "kill_trigger_regression",
        "largest_incremental_month_fraction",
        "max_drawdown_fraction",
    }
    missing = sorted(required - set(trials.columns))
    if missing:
        raise JointAdvantageError(f"issue459 trial summary missing columns: {missing}")
    outers = [str(value) for value in prereg["wave1_joint_scarcity_repair"]["outer_blocks"]]
    costs = [str(value) for value in prereg["wave1_joint_scarcity_repair"]["cost_profiles"]]
    controls = prereg["effective_sample_controls"]
    gate = prereg["promotion_gate"]
    expected_pairs = {(outer, cost) for outer in outers for cost in costs}
    rows: list[dict[str, Any]] = []
    for policy_id, group in trials.groupby("policy_id", sort=True):
        observed_pairs = {
            (str(row.outer_id), str(row.cost_profile))
            for row in group.itertuples(index=False)
        }
        if observed_pairs != expected_pairs or len(group) != len(expected_pairs):
            continue
        base = group.loc[group["cost_profile"].astype(str).eq("base")].copy()
        higher = group.loc[~group["cost_profile"].astype(str).eq("base")].copy()
        base_delta = pd.to_numeric(base["mean_monthly_net_return_delta"], errors="raise")
        selected = pd.to_numeric(base["selected_trades"], errors="raise")
        months = pd.to_numeric(base["nonempty_months"], errors="raise")
        concentration = pd.to_numeric(
            base["largest_incremental_month_fraction"], errors="raise"
        )
        effective_pass = bool(
            selected.ge(int(controls["minimum_risk_executed_trades_per_outer"])).all()
            and months.ge(int(controls["minimum_nonempty_months_per_outer"])).all()
        )
        kill_regression = bool(group["kill_trigger_regression"].astype(bool).any())
        higher_cost_nonnegative = bool(
            pd.to_numeric(higher["mean_monthly_net_return_delta"], errors="raise").ge(0.0).all()
        )
        concentration_pass = bool(concentration.le(0.5).all())
        mean_delta = float(base_delta.mean())
        nonnegative_fraction = float(base_delta.ge(0.0).mean())
        passes = bool(
            mean_delta > float(gate["mean_outer_monthly_net_return_delta_gt"])
            and nonnegative_fraction >= float(gate["nonnegative_outer_fraction_gte"])
            and effective_pass
            and not kill_regression
            and higher_cost_nonnegative
            and concentration_pass
        )
        rows.append(
            {
                "policy_id": str(policy_id),
                "mean_outer_monthly_net_return_delta": mean_delta,
                "nonnegative_outer_fraction": nonnegative_fraction,
                "effective_sample_pass": effective_pass,
                "kill_trigger_regression": kill_regression,
                "higher_cost_nonnegative": higher_cost_nonnegative,
                "concentration_pass": concentration_pass,
                "max_drawdown_fraction": float(
                    pd.to_numeric(base["max_drawdown_fraction"], errors="raise").max()
                ),
                "passes_promotion_gate": passes,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            not bool(row["passes_promotion_gate"]),
            -float(row["mean_outer_monthly_net_return_delta"]),
            float(row["max_drawdown_fraction"]),
            str(row["policy_id"]),
        ),
    )


def executed_sample_summary(
    policy: pd.DataFrame,
    ledger: pd.DataFrame,
) -> dict[str, Any]:
    required_policy = {"fill_trade_date", "baseline_position", "signal_requested_position"}
    required_ledger = {"trade_date", "target_position"}
    if required_policy - set(policy.columns) or required_ledger - set(ledger.columns):
        raise JointAdvantageError("issue459 executed-sample inputs are incomplete")
    decision_dates = pd.to_datetime(policy["fill_trade_date"], utc=True, errors="raise")
    if decision_dates.duplicated().any():
        raise JointAdvantageError("issue459 policy has duplicate decision dates")
    ledger_dates = pd.to_datetime(ledger["trade_date"], utc=True, errors="raise")
    if ledger_dates.duplicated().any():
        raise JointAdvantageError("issue459 replay ledger has duplicate trade dates")
    executed_by_date = pd.Series(
        pd.to_numeric(ledger["target_position"], errors="raise").to_numpy(dtype=float),
        index=ledger_dates,
    )
    requested_position = pd.to_numeric(
        policy["signal_requested_position"], errors="raise"
    ).astype(float)
    requested = requested_position.ne(0.0)
    executed_position = decision_dates.map(executed_by_date)
    if executed_position.isna().any():
        raise JointAdvantageError("issue459 policy decision is missing from replay ledger")
    sign_mismatch = (
        requested
        & executed_position.ne(0.0)
        & requested_position.mul(executed_position).lt(0.0)
    )
    if sign_mismatch.any():
        raise JointAdvantageError("issue459 replay execution direction disagrees with request")
    executed = requested & executed_position.ne(0.0)
    months = decision_dates.loc[executed].dt.tz_convert(None).dt.to_period("M")
    month_counts = months.value_counts().sort_index()
    return {
        "trade_opportunities": int(pd.to_numeric(policy["baseline_position"], errors="raise").ne(0.0).sum()),
        "requested_selected_trades": int(requested.sum()),
        "selected_trades": int(executed.sum()),
        "nonempty_months": len(month_counts),
        "monthly_trade_counts": {str(key): int(value) for key, value in month_counts.items()},
    }


def largest_incremental_month_fraction(
    candidate_ledger: pd.DataFrame,
    baseline_ledger: pd.DataFrame,
) -> float:
    required = {"trade_date", "net_pnl_usd"}
    if required - set(candidate_ledger.columns) or required - set(baseline_ledger.columns):
        raise JointAdvantageError("issue459 concentration ledgers are incomplete")
    candidate = candidate_ledger[["trade_date", "net_pnl_usd"]].copy()
    baseline = baseline_ledger[["trade_date", "net_pnl_usd"]].copy()
    candidate["trade_date"] = pd.to_datetime(candidate["trade_date"], utc=True, errors="raise")
    baseline["trade_date"] = pd.to_datetime(baseline["trade_date"], utc=True, errors="raise")
    if candidate["trade_date"].duplicated().any() or baseline["trade_date"].duplicated().any():
        raise JointAdvantageError("issue459 concentration ledger contains duplicate trade dates")
    joined = candidate.merge(
        baseline, on="trade_date", how="outer", suffixes=("_candidate", "_baseline"), validate="one_to_one"
    ).fillna(0.0)
    joined["incremental"] = (
        pd.to_numeric(joined["net_pnl_usd_candidate"], errors="raise")
        - pd.to_numeric(joined["net_pnl_usd_baseline"], errors="raise")
    )
    joined["month"] = joined["trade_date"].dt.tz_convert(None).dt.to_period("M")
    monthly = joined.groupby("month", sort=True)["incremental"].sum()
    positive = monthly.loc[monthly > 0.0]
    if positive.empty:
        return 1.0
    return float(positive.max() / positive.sum())
