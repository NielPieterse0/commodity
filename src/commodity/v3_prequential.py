from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from commodity.v2_adaptive_controller import PROTECTED_START

MEMORY_BANK: tuple[int | str, ...] = (5, 10, 20, 40, 60, 126, 252, "expanding")


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    parent_id: str | None
    signal_column: str
    complexity: int
    role: str = "challenger"


@dataclass(frozen=True)
class PrequentialConfig:
    initial_train_rows: int = 252
    retrain_every_rows: int = 5
    slow_update_every_rows: int = 20
    fast_window_rows: int = 20
    slow_window_rows: int = 60
    minimum_matured_rows: int = 20
    minimum_incremental_severe_return: float = 0.0
    contract_multiplier: float = 10000.0
    capital_usd: float = 100000.0
    base_cost_per_side_usd: float = 15.0
    severe_extra_cost_per_side_usd: float = 30.0
    severe_miss_increase_when_low_liquidity: bool = True
    memory_bank: tuple[int | str, ...] = MEMORY_BANK
    protected_start: pd.Timestamp = PROTECTED_START

    def __post_init__(self) -> None:
        integer_fields = (
            "initial_train_rows",
            "retrain_every_rows",
            "slow_update_every_rows",
            "fast_window_rows",
            "slow_window_rows",
            "minimum_matured_rows",
        )
        for name in integer_fields:
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if float(self.capital_usd) <= 0.0:
            raise ValueError("capital_usd must be positive")
        if float(self.contract_multiplier) <= 0.0:
            raise ValueError("contract_multiplier must be positive")


@dataclass(frozen=True)
class RobustnessConfig:
    minimum_positive_periods: int = 3
    minimum_recurrence_rate: float = 0.60
    max_drawdown_fraction: float = 0.25
    max_best_period_concentration: float = 0.70
    minimum_incremental_severe_return: float = 0.0
    minimum_leave_best_period_incremental_return: float = 0.0
    multiplicity_alpha: float = 0.05

    def __post_init__(self) -> None:
        if self.minimum_positive_periods <= 0:
            raise ValueError("minimum_positive_periods must be positive")
        for name in ("minimum_recurrence_rate", "max_drawdown_fraction", "max_best_period_concentration", "multiplicity_alpha"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be inside [0, 1]")


@dataclass(frozen=True)
class _EvidenceSeries:
    outcome_ns: np.ndarray
    returns: np.ndarray
    active: np.ndarray
    prefix_return: np.ndarray
    prefix_active: np.ndarray


@dataclass(frozen=True)
class PrequentialResult:
    decisions: pd.DataFrame
    learning_events: pd.DataFrame
    evidence: pd.DataFrame
    candidate_consequences: pd.DataFrame
    candidate_specs: pd.DataFrame
    edge_contribution: pd.DataFrame
    freeze_sha256: str
    protected_confirmation_accessed: bool = False


def _as_utc(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="raise")


def _validate_specs(specs: tuple[CandidateSpec, ...]) -> None:
    if not specs:
        raise ValueError("prequential candidate set cannot be empty")
    ids = [spec.candidate_id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("prequential candidate IDs must be unique")
    known: set[str] = set()
    for spec in specs:
        if spec.parent_id is not None and spec.parent_id not in known:
            raise ValueError(
                f"candidate parent must precede child: {spec.candidate_id}->{spec.parent_id}"
            )
        known.add(spec.candidate_id)


def validate_prequential_frame(
    frame: pd.DataFrame, specs: Iterable[CandidateSpec]
) -> pd.DataFrame:
    candidate_specs = tuple(specs)
    _validate_specs(candidate_specs)
    required = {"decision_time", "outcome_available_at", "path_move_per_mmbtu"}
    required.update(spec.signal_column for spec in candidate_specs)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"prequential frame missing columns: {missing}")
    out = frame.copy().reset_index(drop=True)
    out["decision_time"] = _as_utc(out["decision_time"])
    out["outcome_available_at"] = _as_utc(out["outcome_available_at"])
    protected = pd.Timestamp(PROTECTED_START)
    if (out["decision_time"] >= protected).any() or (
        out["outcome_available_at"] >= protected
    ).any():
        raise ValueError("prequential frame crossed protected confirmation boundary")
    if not out["decision_time"].is_monotonic_increasing:
        raise ValueError("prequential decision_time must be chronological")
    if not out["decision_time"].is_unique:
        raise ValueError("prequential decision_time must be unique")
    if not (out["outcome_available_at"] > out["decision_time"]).all():
        raise ValueError("prequential outcomes must mature after their decision")
    move = pd.to_numeric(out["path_move_per_mmbtu"], errors="raise").astype(float)
    if not np.isfinite(move.to_numpy()).all():
        raise ValueError("prequential path move must be finite")
    out["path_move_per_mmbtu"] = move
    for spec in candidate_specs:
        signal = pd.to_numeric(out[spec.signal_column], errors="raise").astype(float)
        if not np.isfinite(signal.to_numpy()).all() or (signal.abs() > 1.0 + 1e-12).any():
            raise ValueError(f"candidate signal is not bounded: {spec.candidate_id}")
        out[spec.signal_column] = signal
    return out


def _execution_target(
    current: float,
    requested: float,
    *,
    low_liquidity: bool,
    miss_increase: bool,
) -> float:
    if not miss_increase or not low_liquidity:
        return float(requested)
    if current == 0.0 and requested != 0.0:
        return 0.0
    if current * requested < 0.0:
        return 0.0
    if current * requested > 0.0 and abs(requested) > abs(current):
        return float(current)
    return float(requested)


def _candidate_consequences(
    frame: pd.DataFrame,
    specs: tuple[CandidateSpec, ...],
    config: PrequentialConfig,
) -> pd.DataFrame:
    low_liquidity = (
        frame["low_liquidity"].astype(bool).to_numpy()
        if "low_liquidity" in frame
        else np.zeros(len(frame), dtype=bool)
    )
    rows: list[dict[str, Any]] = []
    for scenario, extra_cost, miss_increase in (
        ("base", 0.0, False),
        ("severe", config.severe_extra_cost_per_side_usd, config.severe_miss_increase_when_low_liquidity),
    ):
        cost_per_side = float(config.base_cost_per_side_usd + extra_cost)
        for spec in specs:
            current = 0.0
            signals = frame[spec.signal_column].to_numpy(dtype=float)
            for index, requested in enumerate(signals):
                executed = _execution_target(
                    current,
                    float(requested),
                    low_liquidity=bool(low_liquidity[index]),
                    miss_increase=bool(miss_increase),
                )
                turnover = abs(executed - current)
                gross_pnl = (
                    executed
                    * float(frame.at[index, "path_move_per_mmbtu"])
                    * float(config.contract_multiplier)
                )
                net_return = (
                    gross_pnl - turnover * cost_per_side
                ) / float(config.capital_usd)
                rows.append(
                    {
                        "decision_index": index,
                        "decision_time": frame.at[index, "decision_time"],
                        "outcome_available_at": frame.at[index, "outcome_available_at"],
                        "candidate_id": spec.candidate_id,
                        "scenario": scenario,
                        "requested_signal": float(requested),
                        "executed_signal": float(executed),
                        "turnover": float(turnover),
                        "realized_net_return": float(net_return),
                    }
                )
                current = float(executed)
    return pd.DataFrame(rows)


def _window_frame(frame: pd.DataFrame, memory: int | str) -> pd.DataFrame:
    if memory == "expanding":
        return frame
    return frame.tail(int(memory))


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = 1.0 + pd.to_numeric(returns, errors="raise").astype(float).cumsum()
    peak = equity.cummax().clip(lower=1e-12)
    return float(((peak - equity) / peak).max())


def _max_drawdown_array(returns: np.ndarray) -> float:
    if len(returns) == 0:
        return 0.0
    equity = 1.0 + np.cumsum(np.asarray(returns, dtype=float))
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / np.maximum(peak, 1e-12)
    return float(np.max(drawdown))


def _build_evidence_cache(
    consequences: pd.DataFrame,
    specs: tuple[CandidateSpec, ...],
) -> dict[tuple[str, str], _EvidenceSeries]:
    cache: dict[tuple[str, str], _EvidenceSeries] = {}
    for spec in specs:
        for scenario in ("base", "severe"):
            sample = consequences.loc[
                (consequences["candidate_id"] == spec.candidate_id)
                & (consequences["scenario"] == scenario)
            ].sort_values("outcome_available_at", kind="stable")
            outcome_ns = pd.to_datetime(
                sample["outcome_available_at"], utc=True, errors="raise"
            ).astype("int64").to_numpy(copy=True)
            returns = pd.to_numeric(
                sample["realized_net_return"], errors="raise"
            ).to_numpy(dtype=float, copy=True)
            active = sample["executed_signal"].ne(0.0).to_numpy(dtype=np.int64)
            cache[(spec.candidate_id, scenario)] = _EvidenceSeries(
                outcome_ns=outcome_ns,
                returns=returns,
                active=active,
                prefix_return=np.concatenate(([0.0], np.cumsum(returns))),
                prefix_active=np.concatenate(([0], np.cumsum(active))),
            )
    return cache


def _evidence_snapshot(
    consequences: pd.DataFrame,
    specs: tuple[CandidateSpec, ...],
    decision_time: pd.Timestamp,
    memories: tuple[int | str, ...],
) -> list[dict[str, Any]]:
    mature = consequences.loc[
        pd.to_datetime(consequences["outcome_available_at"], utc=True) < decision_time
    ]
    rows: list[dict[str, Any]] = []
    for spec in specs:
        for scenario in ("base", "severe"):
            history = mature.loc[
                (mature["candidate_id"] == spec.candidate_id)
                & (mature["scenario"] == scenario)
            ].sort_values("outcome_available_at", kind="stable")
            for memory in memories:
                sample = _window_frame(history, memory)
                returns = sample["realized_net_return"].astype(float)
                rows.append(
                    {
                        "decision_time": decision_time,
                        "candidate_id": spec.candidate_id,
                        "scenario": scenario,
                        "memory": str(memory),
                        "support_rows": len(sample),
                        "active_rows": int(sample["executed_signal"].ne(0.0).sum()),
                        "net_return": float(returns.sum()),
                        "max_drawdown_fraction": _max_drawdown(returns),
                        "max_outcome_available_at_used": (
                            sample["outcome_available_at"].max() if len(sample) else pd.NaT
                        ),
                    }
                )
    return rows


def _cached_evidence_snapshot(
    cache: dict[tuple[str, str], _EvidenceSeries],
    specs: tuple[CandidateSpec, ...],
    decision_time: pd.Timestamp,
    memories: tuple[int | str, ...],
) -> list[dict[str, Any]]:
    decision_ns = int(pd.Timestamp(decision_time).value)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        for scenario in ("base", "severe"):
            series = cache[(spec.candidate_id, scenario)]
            end = int(np.searchsorted(series.outcome_ns, decision_ns, side="left"))
            for memory in memories:
                start = 0 if memory == "expanding" else max(0, end - int(memory))
                support = end - start
                net_return = float(
                    series.prefix_return[end] - series.prefix_return[start]
                )
                active_rows = int(
                    series.prefix_active[end] - series.prefix_active[start]
                )
                rows.append(
                    {
                        "decision_time": decision_time,
                        "candidate_id": spec.candidate_id,
                        "scenario": scenario,
                        "memory": str(memory),
                        "support_rows": support,
                        "active_rows": active_rows,
                        "net_return": net_return,
                        "max_drawdown_fraction": _max_drawdown_array(
                            series.returns[start:end]
                        ),
                        "max_outcome_available_at_used": (
                            pd.Timestamp(series.outcome_ns[end - 1], unit="ns", tz="UTC")
                            if support
                            else pd.NaT
                        ),
                    }
                )
    return rows


def _candidate_metric(
    evidence: pd.DataFrame,
    candidate_id: str,
    scenario: str,
    memory: int | str,
) -> tuple[float, int]:
    row = evidence.loc[
        (evidence["candidate_id"] == candidate_id)
        & (evidence["scenario"] == scenario)
        & (evidence["memory"] == str(memory))
    ]
    if len(row) != 1:
        return 0.0, 0
    return float(row.iloc[0]["net_return"]), int(row.iloc[0]["support_rows"])


def _promoted_candidates(
    evidence: pd.DataFrame,
    specs: tuple[CandidateSpec, ...],
    *,
    memory: int | str,
    config: PrequentialConfig,
) -> tuple[str, ...]:
    promoted: list[str] = []
    for spec in specs:
        if spec.parent_id is None:
            promoted.append(spec.candidate_id)
            continue
        if spec.parent_id not in promoted:
            continue
        child_return, child_support = _candidate_metric(
            evidence, spec.candidate_id, "severe", memory
        )
        parent_return, parent_support = _candidate_metric(
            evidence, spec.parent_id, "severe", memory
        )
        support = min(child_support, parent_support)
        increment = child_return - parent_return
        if support >= int(config.minimum_matured_rows) and increment > float(
            config.minimum_incremental_severe_return
        ):
            promoted.append(spec.candidate_id)
    return tuple(promoted)


def _candidate_weights(
    evidence: pd.DataFrame,
    specs: tuple[CandidateSpec, ...],
    structural_promoted: tuple[str, ...],
    config: PrequentialConfig,
) -> dict[str, float]:
    fast_promoted = set(
        _promoted_candidates(
            evidence,
            specs,
            memory=config.fast_window_rows,
            config=config,
        )
    )
    eligible = [
        spec for spec in specs
        if spec.candidate_id in structural_promoted and spec.candidate_id in fast_promoted
    ]
    if not eligible:
        eligible = [specs[0]]
    ranked: list[tuple[float, int, str]] = []
    for spec in eligible:
        value, _support = _candidate_metric(
            evidence, spec.candidate_id, "severe", config.fast_window_rows
        )
        ranked.append((float(value), int(spec.complexity), spec.candidate_id))
    champion = min(ranked, key=lambda row: (-row[0], row[1], row[2]))[2]
    return {
        spec.candidate_id: (1.0 if spec.candidate_id == champion else 0.0)
        for spec in specs
    }


def _selected_candidate(weights: dict[str, float], specs: tuple[CandidateSpec, ...]) -> str:
    for spec in specs:
        if float(weights.get(spec.candidate_id, 0.0)) > 0.0:
            return spec.candidate_id
    return specs[0].candidate_id


def _spec_frame(specs: tuple[CandidateSpec, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate_id": spec.candidate_id,
                "parent_id": spec.parent_id,
                "signal_column": spec.signal_column,
                "complexity": spec.complexity,
                "role": spec.role,
            }
            for spec in specs
        ]
    )


def _edge_contribution(
    consequences: pd.DataFrame, specs: tuple[CandidateSpec, ...]
) -> pd.DataFrame:
    severe = consequences.loc[consequences["scenario"] == "severe"]
    totals = severe.groupby("candidate_id")["realized_net_return"].sum().to_dict()
    rows: list[dict[str, Any]] = []
    for spec in specs:
        own = float(totals.get(spec.candidate_id, 0.0))
        parent = float(totals.get(spec.parent_id, 0.0)) if spec.parent_id else 0.0
        rows.append(
            {
                "candidate_id": spec.candidate_id,
                "parent_id": spec.parent_id,
                "severe_net_return": own,
                "incremental_severe_net_return": own - parent,
            }
        )
    return pd.DataFrame(rows)


def run_prequential(
    frame: pd.DataFrame,
    specs: Iterable[CandidateSpec],
    config: PrequentialConfig | None = None,
) -> PrequentialResult:
    cfg = config or PrequentialConfig()
    candidate_specs = tuple(specs)
    data = validate_prequential_frame(frame, candidate_specs)
    if len(data) <= int(cfg.initial_train_rows):
        raise ValueError("prequential frame does not extend beyond initial training history")
    consequences = _candidate_consequences(data, candidate_specs, cfg)
    evidence_cache = _build_evidence_cache(consequences, candidate_specs)
    memory_values = tuple(
        dict.fromkeys((*cfg.memory_bank, cfg.fast_window_rows, cfg.slow_window_rows))
    )
    structural_promoted: tuple[str, ...] = (candidate_specs[0].candidate_id,)
    weights = {spec.candidate_id: 0.0 for spec in candidate_specs}
    weights[candidate_specs[0].candidate_id] = 1.0
    decision_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []

    reference = consequences.loc[
        (consequences["candidate_id"] == candidate_specs[0].candidate_id)
        & (consequences["scenario"] == "base")
    ]
    for index, row in data.iterrows():
        decision_time = pd.Timestamp(row["decision_time"])
        matured_count = int(
            (pd.to_datetime(reference["outcome_available_at"], utc=True) < decision_time).sum()
        )
        training_only = index < int(cfg.initial_train_rows)
        retrain = bool(
            not training_only
            and (index - int(cfg.initial_train_rows)) % int(cfg.retrain_every_rows) == 0
        )
        slow_update = bool(
            not training_only
            and (index - int(cfg.initial_train_rows)) % int(cfg.slow_update_every_rows) == 0
        )
        if retrain:
            snapshot_rows = _cached_evidence_snapshot(
                evidence_cache, candidate_specs, decision_time, memory_values
            )
            evidence_rows.extend(snapshot_rows)
            snapshot = pd.DataFrame(snapshot_rows)
            if slow_update:
                structural_promoted = _promoted_candidates(
                    snapshot,
                    candidate_specs,
                    memory=cfg.slow_window_rows,
                    config=cfg,
                )
            weights = _candidate_weights(
                snapshot, candidate_specs, structural_promoted, cfg
            )
            used = pd.to_datetime(
                snapshot["max_outcome_available_at_used"], utc=True, errors="coerce"
            )
            maximum_used = used.max() if used.notna().any() else pd.NaT
            event_rows.append(
                {
                    "decision_index": int(index),
                    "decision_time": decision_time,
                    "slow_update": bool(slow_update),
                    "promoted_candidates": list(structural_promoted),
                    "candidate_weights": dict(weights),
                    "max_outcome_available_at_used": maximum_used,
                }
            )
        selected = _selected_candidate(weights, candidate_specs)
        selected_spec = next(
            spec for spec in candidate_specs if spec.candidate_id == selected
        )
        target = 0.0 if training_only else float(row[selected_spec.signal_column])
        decision_rows.append(
            {
                "decision_index": int(index),
                "decision_time": decision_time,
                "training_only": bool(training_only),
                "retrain": bool(retrain),
                "slow_update": bool(slow_update),
                "matured_candidate_rows": int(matured_count),
                "selected_candidate_id": selected,
                "target_exposure": float(target),
                "candidate_weights": dict(weights),
            }
        )

    decisions = pd.DataFrame(decision_rows)
    events = pd.DataFrame(event_rows)
    evidence = pd.DataFrame(evidence_rows)
    edge = _edge_contribution(consequences, candidate_specs)
    freeze_payload = {
        "config": asdict(cfg),
        "candidate_specs": [asdict(spec) for spec in candidate_specs],
        "decisions": decisions.to_dict(orient="records"),
        "learning_events": events.to_dict(orient="records"),
    }
    freeze_sha256 = hashlib.sha256(
        json.dumps(
            freeze_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return PrequentialResult(
        decisions=decisions,
        learning_events=events,
        evidence=evidence,
        candidate_consequences=consequences,
        candidate_specs=_spec_frame(candidate_specs),
        edge_contribution=edge,
        freeze_sha256=freeze_sha256,
        protected_confirmation_accessed=False,
    )


def default_candidate_specs() -> tuple[CandidateSpec, ...]:
    """Frozen bounded benchmark/challenger tree for issue #475."""
    return (
        CandidateSpec("flat", None, "signal_flat", 0, "baseline"),
        CandidateSpec("always_short", "flat", "signal_always_short", 0, "baseline"),
        CandidateSpec("trend_short", "always_short", "signal_trend_short", 1, "baseline"),
        CandidateSpec("curve_short", "always_short", "signal_curve_short", 1, "baseline"),
        CandidateSpec(
            "trend_curve_short",
            "trend_short",
            "signal_trend_curve_short",
            2,
            "baseline",
        ),
        CandidateSpec("timesfm_short", "always_short", "signal_timesfm_short", 1, "challenger"),
        CandidateSpec(
            "trend_timesfm_short",
            "trend_short",
            "signal_trend_timesfm_short",
            2,
            "challenger",
        ),
        CandidateSpec("kronos_short", "always_short", "signal_kronos_short", 1, "challenger"),
        CandidateSpec(
            "low_vol_trend_short",
            "trend_short",
            "signal_low_vol_trend_short",
            2,
            "risk_veto_challenger",
        ),
        CandidateSpec(
            "jump_veto_trend_short",
            "trend_short",
            "signal_jump_veto_trend_short",
            2,
            "risk_veto_challenger",
        ),
        CandidateSpec(
            "timesfm_long_challenger",
            "flat",
            "signal_timesfm_long_challenger",
            1,
            "long_challenger",
        ),
        CandidateSpec(
            "current_v3",
            "trend_curve_short",
            "signal_current_v3",
            4,
            "legacy_v3_reference",
        ),
        CandidateSpec(
            "negative_control_inverted_trend",
            "flat",
            "signal_negative_control_inverted_trend",
            1,
            "negative_control",
        ),
    )


def _sign(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="raise").astype(float)
    return pd.Series(np.sign(numeric.to_numpy()), index=values.index, dtype=float)


def build_default_candidate_signals(features: pd.DataFrame) -> pd.DataFrame:
    """Build the frozen simple ladder and a fixed legacy-V3 directional reference lane."""
    required = {
        "decision_time",
        "feature_ret_1",
        "feature_ret_20",
        "feature_ret_5",
        "feature_ma_gap_20",
        "feature_curve_slope_m1_m4",
        "feature_vol_20",
        "feature_vol_5",
        "timesfm_point_return",
        "kronos_close_return",
    }
    missing = sorted(required.difference(features.columns))
    if missing:
        raise ValueError(f"default candidate signals missing features: {missing}")
    out = pd.DataFrame(
        {"decision_time": pd.to_datetime(features["decision_time"], utc=True, errors="raise")}
    )
    ret1 = pd.to_numeric(features["feature_ret_1"], errors="raise").astype(float)
    ret20 = _sign(features["feature_ret_20"])
    ret5 = _sign(features["feature_ret_5"])
    ma20 = _sign(features["feature_ma_gap_20"])
    slope = _sign(features["feature_curve_slope_m1_m4"])
    timesfm = _sign(features["timesfm_point_return"])
    kronos = _sign(features["kronos_close_return"])
    vol20 = pd.to_numeric(features["feature_vol_20"], errors="raise").astype(float)
    jump = ret1.abs() / vol20.clip(lower=1e-12)
    prior_vol_median = vol20.shift(1).rolling(60, min_periods=20).median()
    prior_jump_q67 = jump.shift(1).rolling(60, min_periods=20).quantile(0.67)

    out["signal_flat"] = 0.0
    out["signal_always_short"] = -1.0
    out["signal_trend_short"] = np.where(ret20 < 0.0, -1.0, 0.0)
    # Positive M1->M4 slope is treated as contango confirmation for the short lane.
    out["signal_curve_short"] = np.where(slope > 0.0, -1.0, 0.0)
    out["signal_trend_curve_short"] = np.where(
        (out["signal_trend_short"] < 0.0) & (out["signal_curve_short"] < 0.0),
        -1.0,
        0.0,
    )
    out["signal_timesfm_short"] = np.where(timesfm < 0.0, -1.0, 0.0)
    out["signal_trend_timesfm_short"] = np.where(
        (out["signal_trend_short"] < 0.0) & (timesfm < 0.0), -1.0, 0.0
    )
    out["signal_kronos_short"] = np.where(kronos < 0.0, -1.0, 0.0)
    out["signal_low_vol_trend_short"] = np.where(
        (out["signal_trend_short"] < 0.0) & (vol20 <= prior_vol_median), -1.0, 0.0
    )
    out["signal_jump_veto_trend_short"] = np.where(
        (out["signal_trend_short"] < 0.0) & (jump <= prior_jump_q67), -1.0, 0.0
    )
    out["signal_timesfm_long_challenger"] = np.where(timesfm > 0.0, 1.0, 0.0)
    # Frozen legacy-V3 reference lane. It approximates the prior controller's directional
    # specialist consensus on the full-history inputs; it is not represented as an exact
    # replay of the Block-1-only 96-candidate meta-controller.
    carry_direction = -slope
    score = 2.0 * ret20 + ret5 + ma20 + carry_direction + timesfm + kronos
    out["signal_current_v3"] = np.where(
        score >= 3.0,
        1.0,
        np.where(score <= -3.0, -1.0, 0.0),
    )
    out["signal_negative_control_inverted_trend"] = np.where(ret20 < 0.0, 1.0, 0.0)
    signal_columns = [column for column in out if column.startswith("signal_")]
    if not out[signal_columns].isin([-1.0, 0.0, 1.0]).all().all():
        raise ValueError("default candidate signals left bounded direction set")
    return out


def select_smallest_passing_architecture(
    robustness_report: pd.DataFrame,
    specs: Iterable[CandidateSpec],
) -> str | None:
    candidate_specs = tuple(specs)
    _validate_specs(candidate_specs)
    if "candidate_id" not in robustness_report or "passes_all_gates" not in robustness_report:
        raise ValueError("robustness report lacks selection fields")
    by_id = {spec.candidate_id: spec for spec in candidate_specs}
    rows = robustness_report.loc[robustness_report["passes_all_gates"].astype(bool)].copy()
    rows = rows.loc[rows["candidate_id"].isin(by_id)]
    rows = rows.loc[
        rows["candidate_id"].map(lambda value: by_id[str(value)].role != "negative_control")
    ]
    if rows.empty:
        return None
    if "severe_net_return" not in rows:
        rows["severe_net_return"] = 0.0
    rows["complexity"] = rows["candidate_id"].map(
        lambda value: int(by_id[str(value)].complexity)
    )
    rows = rows.sort_values(
        ["complexity", "severe_net_return", "candidate_id"],
        ascending=[True, False, True],
        kind="stable",
    )
    return str(rows.iloc[0]["candidate_id"])


def build_one_session_execution_frame(
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    *,
    protected_start: pd.Timestamp = PROTECTED_START,
) -> pd.DataFrame:
    """Map each PIT feature row to the first executable session and its one-session outcome."""
    feature_required = {"trade_date", "available_at"}
    session_required = {
        "trade_date",
        "session_open",
        "available_at",
        "next_session_open",
        "path_move_per_mmbtu",
    }
    if missing := sorted(feature_required.difference(features.columns)):
        raise ValueError(f"execution features missing columns: {missing}")
    if missing := sorted(session_required.difference(sessions.columns)):
        raise ValueError(f"execution sessions missing columns: {missing}")
    safe_boundary = pd.Timestamp(protected_start)
    left = features.copy().reset_index(drop=True)
    right = sessions.copy().reset_index(drop=True)
    left["trade_date"] = pd.to_datetime(left["trade_date"], utc=True, errors="raise")
    left["available_at"] = pd.to_datetime(left["available_at"], utc=True, errors="raise")
    for column in ("trade_date", "session_open", "available_at", "next_session_open"):
        right[column] = pd.to_datetime(right[column], utc=True, errors="raise")
    if (right["next_session_open"] >= safe_boundary).any():
        raise ValueError("execution sessions expose protected confirmation outcome timing")
    if (left["available_at"] >= safe_boundary).any():
        raise ValueError("execution feature availability crossed protected confirmation")
    selected = right[["trade_date", "available_at"]].rename(
        columns={"available_at": "selected_contract_available_at"}
    )
    if selected["trade_date"].duplicated().any():
        raise ValueError("execution session path has duplicate trade_date")
    state = left.merge(selected, on="trade_date", how="left", validate="one_to_one")
    if state["selected_contract_available_at"].isna().any():
        raise ValueError("feature row lacks selected session-path state")
    state["decision_time"] = state[
        ["available_at", "selected_contract_available_at"]
    ].max(axis=1)
    path = right.sort_values("session_open", kind="stable").reset_index(drop=True)
    opens = path["session_open"].astype("int64").to_numpy()
    decisions = state["decision_time"].astype("int64").to_numpy()
    fill_indices = np.searchsorted(opens, decisions, side="right")
    executable = fill_indices < len(path)
    state = state.loc[executable].reset_index(drop=True)
    fill_indices = fill_indices[executable]
    fills = path.iloc[fill_indices].reset_index(drop=True)
    matured_safe = fills["next_session_open"].notna() & (
        fills["next_session_open"] < safe_boundary
    )
    state = state.loc[matured_safe].reset_index(drop=True)
    fills = fills.loc[matured_safe].reset_index(drop=True)
    if not state.empty and not (
        state["decision_time"].to_numpy() < fills["session_open"].to_numpy()
    ).all():
        raise ValueError("selected fill does not strictly follow decision")
    out = state.copy()
    out["fill_timestamp"] = fills["session_open"].to_numpy()
    out["outcome_available_at"] = fills["next_session_open"].to_numpy()
    out["path_move_per_mmbtu"] = pd.to_numeric(
        fills["path_move_per_mmbtu"], errors="raise"
    ).to_numpy(dtype=float)
    if "contract_id" in fills:
        out["fill_contract_id"] = fills["contract_id"].astype(str).to_numpy()
    if "open_price" in fills:
        out["fill_price"] = pd.to_numeric(fills["open_price"], errors="raise").to_numpy(dtype=float)
    if "feature_curve_log_volume_m1" in out:
        volume = pd.to_numeric(out["feature_curve_log_volume_m1"], errors="raise").astype(float)
        prior_median = volume.shift(1).rolling(20, min_periods=5).median()
        out["low_liquidity"] = (volume < prior_median).fillna(False)
    else:
        out["low_liquidity"] = False
    if not (pd.to_datetime(out["outcome_available_at"], utc=True) > out["decision_time"]).all():
        raise ValueError("execution outcome does not strictly follow decision")
    return out.sort_values("decision_time", kind="stable").reset_index(drop=True)


def _one_sided_sign_test_p_value(positive_periods: int, period_count: int) -> float:
    if period_count <= 0:
        return 1.0
    positive_periods = max(0, min(int(positive_periods), int(period_count)))
    numerator = sum(
        math.comb(int(period_count), successes)
        for successes in range(positive_periods, int(period_count) + 1)
    )
    return float(numerator / (2 ** int(period_count)))


def evaluate_robustness(
    consequences: pd.DataFrame,
    specs: Iterable[CandidateSpec],
    config: RobustnessConfig | None = None,
) -> pd.DataFrame:
    """Evaluate parent-relative recurrence, concentration, drawdown, and multiplicity gates."""
    cfg = config or RobustnessConfig()
    candidate_specs = tuple(specs)
    _validate_specs(candidate_specs)
    required = {"decision_time", "candidate_id", "scenario", "realized_net_return"}
    missing = sorted(required.difference(consequences.columns))
    if missing:
        raise ValueError(f"robustness consequences missing columns: {missing}")
    frame = consequences.copy()
    frame["decision_time"] = pd.to_datetime(
        frame["decision_time"], utc=True, errors="raise"
    )
    frame["realized_net_return"] = pd.to_numeric(
        frame["realized_net_return"], errors="raise"
    ).astype(float)
    frame["period"] = frame["decision_time"].dt.year.astype(int)
    spec_by_id = {spec.candidate_id: spec for spec in candidate_specs}
    unknown = sorted(set(frame["candidate_id"].astype(str)) - set(spec_by_id))
    if unknown:
        raise ValueError(
            f"robustness consequences contain unknown candidates: {unknown}"
        )
    tested_candidates = [
        spec
        for spec in candidate_specs
        if spec.parent_id is not None and spec.role != "negative_control"
    ]
    multiplicity_count = max(1, len(tested_candidates))
    rows: list[dict[str, Any]] = []
    grouped = (
        frame.groupby(["candidate_id", "scenario", "period"], sort=True)[
            "realized_net_return"
        ]
        .sum()
        .to_dict()
    )
    for spec in candidate_specs:
        periods = sorted(
            {
                int(period)
                for candidate_id, scenario, period in grouped
                if candidate_id == spec.candidate_id and scenario == "severe"
            }
        )
        severe_path = frame.loc[
            (frame["candidate_id"] == spec.candidate_id)
            & (frame["scenario"] == "severe")
        ].sort_values("decision_time", kind="stable")
        base_path = frame.loc[
            (frame["candidate_id"] == spec.candidate_id)
            & (frame["scenario"] == "base")
        ].sort_values("decision_time", kind="stable")
        severe_total = float(severe_path["realized_net_return"].sum())
        base_total = float(base_path["realized_net_return"].sum())
        if spec.parent_id is None:
            increments = [0.0 for _ in periods]
        else:
            increments = [
                float(grouped.get((spec.candidate_id, "severe", period), 0.0))
                - float(grouped.get((spec.parent_id, "severe", period), 0.0))
                for period in periods
            ]
        incremental_total = float(sum(increments))
        positive_periods = int(sum(value > 0.0 for value in increments))
        period_count = len(periods)
        recurrence_rate = (
            float(positive_periods / period_count) if period_count else 0.0
        )
        best_increment = max(increments, default=0.0)
        leave_best = float(incremental_total - best_increment)
        positive_sum = float(sum(max(0.0, value) for value in increments))
        concentration = (
            float(max(0.0, best_increment) / positive_sum)
            if positive_sum > 0.0
            else 1.0
        )
        raw_p = _one_sided_sign_test_p_value(positive_periods, period_count)
        adjusted_p = min(1.0, float(raw_p * multiplicity_count))
        drawdown = _max_drawdown(severe_path["realized_net_return"])
        gates = {
            "positive_severe": severe_total > 0.0,
            "positive_base": base_total > 0.0,
            "incremental_parent_edge": incremental_total
            > float(cfg.minimum_incremental_severe_return),
            "recurrence": positive_periods >= int(cfg.minimum_positive_periods)
            and recurrence_rate >= float(cfg.minimum_recurrence_rate),
            "leave_best_period": leave_best
            > float(cfg.minimum_leave_best_period_incremental_return),
            "concentration": concentration <= float(cfg.max_best_period_concentration),
            "drawdown": drawdown <= float(cfg.max_drawdown_fraction),
            "multiplicity": adjusted_p <= float(cfg.multiplicity_alpha),
            "eligible_role": spec.role != "negative_control" and spec.parent_id is not None,
        }
        rows.append(
            {
                "candidate_id": spec.candidate_id,
                "parent_id": spec.parent_id,
                "role": spec.role,
                "base_net_return": base_total,
                "severe_net_return": severe_total,
                "incremental_severe_net_return": incremental_total,
                "positive_incremental_periods": positive_periods,
                "period_count": period_count,
                "recurrence_rate": recurrence_rate,
                "best_period_incremental_return": float(best_increment),
                "leave_best_period_incremental_return": leave_best,
                "best_period_concentration": concentration,
                "max_drawdown_fraction": drawdown,
                "sign_test_p_value": raw_p,
                "multiplicity_test_count": multiplicity_count,
                "multiplicity_adjusted_p_value": adjusted_p,
                **{f"gate_{name}": bool(value) for name, value in gates.items()},
                "passes_all_gates": bool(all(gates.values())),
            }
        )
    return pd.DataFrame(rows)


def validate_authoritative_freeze(
    freeze: dict[str, Any],
    expected_identity: dict[str, str],
) -> None:
    """Fail closed unless the pre-traversal freeze exactly binds code, data, and reserve state."""
    if freeze.get("status") != "FROZEN_BEFORE_AUTHORITATIVE_TRAVERSAL":
        raise ValueError("authoritative traversal is not frozen")
    if freeze.get("protected_confirmation_accessed") is not False:
        raise ValueError("authoritative freeze does not preserve protected confirmation")
    if pd.Timestamp(str(freeze.get("protected_start"))) != PROTECTED_START:
        raise ValueError("authoritative freeze protected_start changed")
    observed = freeze.get("identity")
    if not isinstance(observed, dict):
        raise ValueError("authoritative freeze identity is missing")  # noqa: TRY004
    for key, expected in expected_identity.items():
        actual = observed.get(key)
        if actual != expected:
            raise ValueError(
                f"authoritative freeze identity mismatch for {key}: {actual!r} != {expected!r}"
            )


def future_invariance_proof(
    frame: pd.DataFrame,
    specs: Iterable[CandidateSpec],
    config: PrequentialConfig | None = None,
    *,
    cut_indices: Iterable[int] | None = None,
    mutation_scale: float = -101.0,
) -> dict[str, Any]:
    """Prove that mutating later outcomes cannot change decisions at or before each cut."""
    cfg = config or PrequentialConfig()
    candidate_specs = tuple(specs)
    data = validate_prequential_frame(frame, candidate_specs)
    baseline = run_prequential(data, candidate_specs, cfg)
    default_cuts = (
        max(int(cfg.initial_train_rows), len(data) // 3),
        max(int(cfg.initial_train_rows), 2 * len(data) // 3),
    )
    cuts = tuple(int(value) for value in (cut_indices or default_cuts))
    checks: list[dict[str, Any]] = []
    columns = [
        "decision_index",
        "decision_time",
        "training_only",
        "retrain",
        "slow_update",
        "selected_candidate_id",
        "target_exposure",
        "candidate_weights",
    ]
    for cut in cuts:
        if cut < 0 or cut >= len(data) - 1:
            raise ValueError(f"future-invariance cut is outside mutable range: {cut}")
        mutated = data.copy()
        mutated.loc[mutated.index > cut, "path_move_per_mmbtu"] *= float(
            mutation_scale
        )
        changed = run_prequential(mutated, candidate_specs, cfg)
        left = baseline.decisions.loc[:cut, columns].reset_index(drop=True)
        right = changed.decisions.loc[:cut, columns].reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(left, right, check_dtype=False)
            equal = True
        except AssertionError:
            equal = False
        checks.append(
            {
                "cut_index": int(cut),
                "cut_decision_time": pd.Timestamp(
                    baseline.decisions.loc[cut, "decision_time"]
                ),
                "mutated_row_count": int(len(data) - cut - 1),
                "prefix_equal": bool(equal),
            }
        )
    return {
        "status": "PASS" if all(row["prefix_equal"] for row in checks) else "FAIL",
        "cut_count": len(checks),
        "mutation_scale": float(mutation_scale),
        "checks": checks,
    }


def score_exposure_path(
    frame: pd.DataFrame,
    exposure: pd.Series | np.ndarray | list[float],
    config: PrequentialConfig | None = None,
) -> pd.DataFrame:
    """Score one immutable exposure path under the frozen base and severe execution scenarios."""
    cfg = config or PrequentialConfig()
    required = {"decision_time", "outcome_available_at", "path_move_per_mmbtu"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"exposure scoring frame missing columns: {missing}")
    data = frame.copy().reset_index(drop=True)
    data["decision_time"] = _as_utc(data["decision_time"])
    data["outcome_available_at"] = _as_utc(data["outcome_available_at"])
    if (data["decision_time"] >= cfg.protected_start).any() or (
        data["outcome_available_at"] >= cfg.protected_start
    ).any():
        raise ValueError("exposure scoring crossed protected confirmation boundary")
    targets = np.asarray(exposure, dtype=float)
    if len(targets) != len(data) or not np.isfinite(targets).all():
        raise ValueError("exposure path must be finite and aligned one-to-one")
    low_liquidity = (
        data["low_liquidity"].astype(bool).to_numpy()
        if "low_liquidity" in data
        else np.zeros(len(data), dtype=bool)
    )
    rows: list[dict[str, Any]] = []
    for scenario, extra_cost, miss_increase in (
        ("base", 0.0, False),
        (
            "severe",
            cfg.severe_extra_cost_per_side_usd,
            cfg.severe_miss_increase_when_low_liquidity,
        ),
    ):
        current = 0.0
        cost_per_side = float(cfg.base_cost_per_side_usd + extra_cost)
        for index, requested in enumerate(targets):
            executed = _execution_target(
                current,
                float(requested),
                low_liquidity=bool(low_liquidity[index]),
                miss_increase=bool(miss_increase),
            )
            turnover = abs(executed - current)
            gross_pnl = (
                executed
                * float(data.at[index, "path_move_per_mmbtu"])
                * float(cfg.contract_multiplier)
            )
            net_return = (
                gross_pnl - turnover * cost_per_side
            ) / float(cfg.capital_usd)
            rows.append(
                {
                    "decision_index": index,
                    "decision_time": data.at[index, "decision_time"],
                    "outcome_available_at": data.at[index, "outcome_available_at"],
                    "scenario": scenario,
                    "requested_signal": float(requested),
                    "signal": float(executed),
                    "turnover": float(turnover),
                    "realized_net_return": float(net_return),
                }
            )
            current = float(executed)
    return pd.DataFrame(rows)


def attach_foundation_experts(
    frame: pd.DataFrame,
    timesfm: pd.DataFrame,
    kronos: pd.DataFrame,
) -> pd.DataFrame:
    """Attach frozen retrospective expert features only when their effective timestamps are PIT-safe."""
    base = frame.copy()
    required_base = {"trade_date", "decision_time"}
    missing_base = sorted(required_base.difference(base.columns))
    if missing_base:
        raise ValueError(f"foundation expert merge missing base columns: {missing_base}")
    base["trade_date"] = pd.to_datetime(base["trade_date"], utc=True, errors="raise")
    base["decision_time"] = pd.to_datetime(base["decision_time"], utc=True, errors="raise")

    def prepare(
        source: pd.DataFrame,
        *,
        label: str,
        value_columns: tuple[str, ...],
        prefix: str,
    ) -> pd.DataFrame:
        required = {"trade_date", "prediction_time", "generated_at", *value_columns}
        missing = sorted(required.difference(source.columns))
        if missing:
            raise ValueError(f"{label} expert source missing columns: {missing}")
        out = source[["trade_date", "prediction_time", "generated_at", *value_columns]].copy()
        for column in ("trade_date", "prediction_time", "generated_at"):
            out[column] = pd.to_datetime(out[column], utc=True, errors="raise", format="mixed")
        if out["trade_date"].duplicated().any():
            raise ValueError(f"{label} expert source has duplicate trade_date")
        if (out["generated_at"] >= PROTECTED_START).any():
            raise ValueError(f"{label} expert source crosses protected confirmation")
        return out.rename(
            columns={
                "prediction_time": f"{prefix}_prediction_time",
                "generated_at": f"{prefix}_generated_at",
            }
        )

    timesfm_frame = prepare(
        timesfm,
        label="TimesFM",
        prefix="timesfm",
        value_columns=(
            "timesfm_point_return",
            "timesfm_q10_return",
            "timesfm_q90_return",
            "timesfm_interval_width",
        ),
    )
    kronos_frame = prepare(
        kronos,
        label="Kronos",
        prefix="kronos",
        value_columns=("kronos_close_return", "kronos_range_pct"),
    )
    merged = base.merge(timesfm_frame, on="trade_date", how="left", validate="one_to_one")
    merged = merged.merge(kronos_frame, on="trade_date", how="left", validate="one_to_one")
    required_values = [
        "timesfm_point_return",
        "timesfm_q10_return",
        "timesfm_q90_return",
        "timesfm_interval_width",
        "kronos_close_return",
        "kronos_range_pct",
    ]
    if merged[required_values].isna().any().any():
        raise ValueError("foundation expert merge is incomplete for executable rows")
    for label, prefix in (("TimesFM", "timesfm"), ("Kronos", "kronos")):
        if (merged[f"{prefix}_generated_at"] > merged["decision_time"]).any():
            raise ValueError(f"{label} generated_at crosses decision boundary")
        if (merged[f"{prefix}_prediction_time"] > merged["decision_time"]).any():
            raise ValueError(f"{label} prediction_time crosses decision boundary")
    return merged
