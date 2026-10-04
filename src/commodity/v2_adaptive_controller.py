from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import pandas as pd

PROTECTED_START = pd.Timestamp("2023-01-01", tz="UTC")
FORBIDDEN_STATE_TOKENS = (
    "future",
    "target",
    "label",
    "outcome",
    "consequence",
    "oracle",
)


class AdaptiveContractError(ValueError):
    """Raised when the issue #465 chronological contract is violated."""


@dataclass(frozen=True)
class BlockSpec:
    block_id: str
    start: pd.Timestamp
    end_exclusive: pd.Timestamp
    warmup_sessions: int = 30


@dataclass(frozen=True)
class AdaptiveBlockResult:
    ledger: pd.DataFrame
    consequences: pd.DataFrame
    freeze_sha256: str


def _utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def first_block_spec(feature_dates: pd.Series) -> BlockSpec:
    dates = pd.to_datetime(feature_dates, utc=True, errors="coerce").dropna()
    if dates.empty:
        raise AdaptiveContractError("cannot anchor block without eligible feature dates")
    start = _utc(dates.min()).normalize()
    end = start + pd.DateOffset(months=6)
    if end >= PROTECTED_START:
        raise AdaptiveContractError("first block crosses protected confirmation boundary")
    return BlockSpec("block-001", start, end, 30)


def assert_causal_state_columns(columns: Iterable[str]) -> None:
    invalid = [
        str(column)
        for column in columns
        if any(token in str(column).lower() for token in FORBIDDEN_STATE_TOKENS)
    ]
    if invalid:
        raise AdaptiveContractError(f"causal state contains consequence/target columns: {invalid}")


def latest_known_state(
    observations: pd.DataFrame,
    decision_times: pd.Series,
) -> pd.DataFrame:
    required = {"observation_time", "available_at", "source_id"}
    missing = required.difference(observations.columns)
    if missing:
        raise AdaptiveContractError(f"missing PIT provenance columns: {sorted(missing)}")
    assert_causal_state_columns(observations.columns)
    right = observations.copy()
    right["available_at"] = pd.to_datetime(right["available_at"], utc=True)
    right["observation_time"] = pd.to_datetime(right["observation_time"], utc=True)
    right = right.sort_values("available_at")
    left = pd.DataFrame({"decision_time": pd.to_datetime(decision_times, utc=True)}).sort_values(
        "decision_time"
    )
    return pd.merge_asof(
        left,
        right,
        left_on="decision_time",
        right_on="available_at",
        direction="backward",
        allow_exact_matches=True,
    )


def matured_consequences(
    consequences: pd.DataFrame,
    decision_time: pd.Timestamp,
    *,
    window: int,
) -> pd.DataFrame:
    frame = consequences.copy()
    frame["outcome_available_at"] = pd.to_datetime(frame["outcome_available_at"], utc=True)
    matured = frame.loc[frame["outcome_available_at"] < _utc(decision_time)]
    return matured.sort_values("outcome_available_at").tail(int(window)).reset_index(drop=True)


def memory_snapshot(
    consequences: pd.DataFrame,
    decision_time: pd.Timestamp,
    *,
    windows: tuple[int, ...] = (5, 10, 20, 40, 60, 126, 252),
) -> dict[str, dict[str, float | int]]:
    frame = consequences.copy()
    frame["outcome_available_at"] = pd.to_datetime(frame["outcome_available_at"], utc=True)
    prior = frame.loc[frame["outcome_available_at"] < _utc(decision_time)].sort_values(
        "outcome_available_at"
    )
    result: dict[str, dict[str, float | int]] = {}
    for window in windows:
        sample = prior.tail(int(window))
        result[f"w{window}"] = {
            "count": len(sample),
            "net_return_sum": float(sample["net_return"].sum()),
        }
    result["expanding"] = {
        "count": len(prior),
        "net_return_sum": float(prior["net_return"].sum()),
    }
    return result


def rebalance_target_signal(signal: pd.Series, *, cadence_sessions: int) -> pd.Series:
    cadence = int(cadence_sessions)
    if cadence < 1:
        raise AdaptiveContractError("rebalance cadence must be positive")
    values = pd.to_numeric(signal, errors="raise").astype(float).reset_index(drop=True)
    out = values.copy()
    held = 0.0
    for index, value in enumerate(values):
        if index % cadence == 0:
            held = float(value)
        out.iloc[index] = held
    return out


def sparse_policy_signal(
    specialists: pd.DataFrame,
    *,
    weights: dict[str, float],
    cadence_sessions: int,
    side: str,
    exposure: float,
) -> pd.Series:
    if not weights or any(column not in specialists.columns for column in weights):
        raise AdaptiveContractError("sparse policy references an unavailable specialist")
    vote = sum(pd.to_numeric(specialists[column], errors="raise") * weight for column, weight in weights.items())
    raw = pd.Series(0.0, index=specialists.index, dtype=float)
    raw.loc[vote > 0] = float(exposure)
    raw.loc[vote < 0] = -float(exposure)
    if side == "long_only":
        raw = raw.clip(lower=0.0)
    elif side == "short_only":
        raw = raw.clip(upper=0.0)
    elif side != "symmetric":
        raise AdaptiveContractError(f"unknown side mode: {side}")
    return rebalance_target_signal(
        raw.reset_index(drop=True), cadence_sessions=cadence_sessions
    )


def comparable_state_refs(
    context_state: pd.DataFrame,
    decision_time: pd.Timestamp,
    *,
    k: int = 10,
    feature_columns: Iterable[str] | None = None,
) -> list[pd.Timestamp]:
    frame = context_state.copy()
    if "decision_time" not in frame:
        raise AdaptiveContractError("comparable-state context requires decision_time")
    frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
    current_time = _utc(decision_time)
    current = frame.loc[frame["decision_time"] == current_time]
    prior = frame.loc[frame["decision_time"] < current_time]
    if current.empty or prior.empty or k < 1:
        return []
    columns = list(feature_columns or [
        column for column in frame.columns
        if column != "decision_time" and pd.api.types.is_numeric_dtype(frame[column])
    ])
    if not columns:
        return []
    current_values = current.iloc[-1][columns].astype(float)
    usable = prior[columns].notna().all(axis=1) & current_values.notna().all()
    prior = prior.loc[usable].copy()
    if prior.empty:
        return []
    scale = prior[columns].std(ddof=0).replace(0.0, 1.0).fillna(1.0)
    distance = (((prior[columns].astype(float) - current_values) / scale) ** 2).sum(axis=1)
    ranked = prior.assign(_distance=distance).sort_values(
        ["_distance", "decision_time"], kind="stable"
    )
    return [pd.Timestamp(value) for value in ranked.head(int(k))["decision_time"]]


def next_position_state(
    current_state: str,
    desired_signal: float,
    *,
    current_position: float | None = None,
    marginal_edge: float,
    risk_capacity: float,
) -> str:
    desired = float(desired_signal)
    if current_position is None:
        if desired == 0.0:
            return "FLAT" if current_state == "FLAT" else "EXIT"
        if current_state in {"FLAT", "EXIT", "REVERSE"}:
            return "STARTER"
        if current_state == "STARTER":
            return "FULL"
        if current_state == "FULL":
            return "ADD" if marginal_edge > 0.0 and risk_capacity > 0.0 else "FULL"
        if current_state == "ADD":
            return "ADD" if marginal_edge > 0.0 and risk_capacity > 0.0 else "FULL"
        if current_state == "REDUCE":
            return "FULL"
        raise AdaptiveContractError(f"unknown position state: {current_state}")
    position = float(current_position)
    if desired == 0.0:
        return "FLAT" if position == 0.0 and current_state == "FLAT" else "EXIT"
    if position != 0.0 and desired * position < 0.0:
        return "REVERSE"
    if position != 0.0 and abs(desired) < abs(position):
        return "REDUCE"
    if position == 0.0 or current_state in {"FLAT", "EXIT", "REVERSE"}:
        return "STARTER"
    if abs(desired) > abs(position):
        return "ADD" if marginal_edge > 0.0 and risk_capacity > 0.0 else "FULL"
    if current_state == "STARTER":
        return "FULL"
    if current_state in {"FULL", "ADD", "REDUCE"}:
        return "FULL"
    raise AdaptiveContractError(f"unknown position state: {current_state}")


def _policy_complexity(policy_id: str) -> int:
    return 0 if policy_id == "flat" else 1


def _freeze_frame(frame: pd.DataFrame) -> str:
    payload = frame.to_json(orient="records", date_format="iso", double_precision=15)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate_consequence_store(
    state: pd.DataFrame,
    path: pd.DataFrame,
    policy_ids: list[str],
    *,
    multiplier: float,
    capital_usd: float,
    cost_per_side_usd: float,
) -> pd.DataFrame:
    joined = state[["decision_time", *policy_ids]].merge(
        path[["decision_time", "outcome_available_at", "path_move_per_mmbtu"]],
        on="decision_time",
        how="inner",
        validate="one_to_one",
    )
    rows: list[dict[str, object]] = []
    previous = {policy_id: 0.0 for policy_id in policy_ids}
    decision_times = joined["decision_time"].tolist()
    outcome_times = joined["outcome_available_at"].tolist()
    path_moves = pd.to_numeric(joined["path_move_per_mmbtu"], errors="raise").astype(float)
    signals = joined[policy_ids].apply(pd.to_numeric, errors="raise").astype(float).to_numpy()
    for row_index, decision_time in enumerate(decision_times):
        for policy_index, policy_id in enumerate(policy_ids):
            signal = float(signals[row_index, policy_index])
            turnover = abs(signal - previous[policy_id])
            pnl = signal * float(path_moves.iloc[row_index]) * multiplier
            pnl -= turnover * cost_per_side_usd
            rows.append(
                {
                    "decision_time": decision_time,
                    "outcome_available_at": outcome_times[row_index],
                    "policy_id": policy_id,
                    "signal": signal,
                    "turnover": turnover,
                    "net_return": pnl / capital_usd,
                }
            )
            previous[policy_id] = signal
    return pd.DataFrame(rows)


def candidate_consequence_store(
    state: pd.DataFrame,
    path: pd.DataFrame,
    policy_ids: list[str],
    *,
    multiplier: float = 10000.0,
    capital_usd: float = 100000.0,
    cost_per_side_usd: float = 15.0,
) -> pd.DataFrame:
    return _candidate_consequence_store(
        state,
        path,
        policy_ids,
        multiplier=multiplier,
        capital_usd=capital_usd,
        cost_per_side_usd=cost_per_side_usd,
    )


def oracle_diagnostic(
    candidate_consequences: pd.DataFrame,
    decision_times: Iterable[pd.Timestamp],
) -> dict[str, object]:
    wanted = {_utc(value) for value in decision_times}
    frame = candidate_consequences.copy()
    frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
    if "turnover" not in frame:
        frame["turnover"] = 0.0
    frame = frame.loc[frame["decision_time"].isin(wanted)].copy()
    winners: dict[str, str] = {}
    total = 0.0
    for decision_time, group in frame.groupby("decision_time", sort=True):
        ranked = group.sort_values(
            ["net_return", "turnover", "policy_id"],
            ascending=[False, True, True],
            kind="stable",
        )
        best = ranked.iloc[0]
        total += float(best["net_return"])
        winners[pd.Timestamp(decision_time).isoformat()] = str(best["policy_id"])
    return {
        "oracle_net_return": total,
        "oracle_policy_by_day": winners,
        "decision_count": len(winners),
    }


def run_adaptive_block(
    state: pd.DataFrame,
    path: pd.DataFrame,
    *,
    objective_window: int = 30,
    multiplier: float = 10000.0,
    capital_usd: float = 100000.0,
    cost_per_side_usd: float = 15.0,
    policy_metadata: Mapping[str, Mapping[str, object]] | None = None,
    context_state: pd.DataFrame | None = None,
    similar_state_k: int = 10,
) -> AdaptiveBlockResult:
    if "decision_time" not in state or "decision_time" not in path:
        raise AdaptiveContractError("state and path require decision_time")
    state = state.copy().sort_values("decision_time").reset_index(drop=True)
    path = path.copy().sort_values("decision_time").reset_index(drop=True)
    state["decision_time"] = pd.to_datetime(state["decision_time"], utc=True)
    path["decision_time"] = pd.to_datetime(path["decision_time"], utc=True)
    path["outcome_available_at"] = pd.to_datetime(path["outcome_available_at"], utc=True)
    if (state["decision_time"] >= PROTECTED_START).any():
        raise AdaptiveContractError("protected 2023+ state is sealed")
    policy_ids = [column for column in state.columns if column != "decision_time"]
    if not policy_ids:
        raise AdaptiveContractError("at least one preregistered policy signal is required")
    assert_causal_state_columns(policy_ids)
    candidates = _candidate_consequence_store(
        state,
        path,
        policy_ids,
        multiplier=multiplier,
        capital_usd=capital_usd,
        cost_per_side_usd=cost_per_side_usd,
    )
    candidate_by_policy = {
        str(policy_id): group.reset_index(drop=True)
        for policy_id, group in candidates.groupby("policy_id", sort=False)
    }
    metadata = {str(key): dict(value) for key, value in (policy_metadata or {}).items()}
    unknown_metadata = sorted(set(metadata) - set(policy_ids))
    if unknown_metadata:
        raise AdaptiveContractError(f"metadata references unknown policies: {unknown_metadata}")
    context = None
    if context_state is not None:
        context = context_state.copy().sort_values("decision_time").reset_index(drop=True)
        context["decision_time"] = pd.to_datetime(context["decision_time"], utc=True)
        if (context["decision_time"] >= PROTECTED_START).any():
            raise AdaptiveContractError("protected 2023+ context state is sealed")
    path_by_time = path.set_index("decision_time")
    ledger_rows: list[dict[str, object]] = []
    actual_rows: list[dict[str, object]] = []
    actual_previous = 0.0
    position_state = "FLAT"
    for index, row in state.iterrows():
        decision_time = _utc(row["decision_time"])
        selected_policy = "warmup"
        selected_signal = 0.0
        selected_weights: dict[str, float] = {}
        selected_memory: dict[str, dict[str, float | int]] = {}
        selected_meta: dict[str, object] = {}
        similar_refs = (
            comparable_state_refs(context, decision_time, k=similar_state_k)
            if context is not None
            else []
        )
        similar_state_net_return_mean = 0.0
        max_used = pd.NaT
        marginal_edge = 0.0
        if index >= int(objective_window):
            eligible: list[tuple[float, float, int, str, pd.DataFrame]] = []
            for policy_id in policy_ids:
                history = matured_consequences(
                    candidate_by_policy[policy_id],
                    decision_time,
                    window=objective_window,
                )
                if len(history) < int(objective_window):
                    continue
                score = float(history["net_return"].sum())
                turnover = float(history["turnover"].sum())
                complexity = int(metadata.get(policy_id, {}).get("complexity", _policy_complexity(policy_id)))
                eligible.append((score, -turnover, -complexity, policy_id, history))
            if eligible:
                eligible.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
                best = eligible[0]
                selected_policy = best[3]
                selected_signal = float(row[selected_policy])
                selected_meta = metadata.get(selected_policy, {})
                selected_weights = dict(
                    selected_meta.get("weights", {selected_policy: 1.0})
                )
                selected_memory = memory_snapshot(
                    candidate_by_policy[selected_policy],
                    decision_time,
                )
                max_used = best[4]["outcome_available_at"].max()
                if similar_refs:
                    selected_candidates = candidate_by_policy[selected_policy]
                    comparable = selected_candidates.loc[
                        selected_candidates["decision_time"].isin(similar_refs)
                        & (selected_candidates["outcome_available_at"] < decision_time)
                    ]
                    if not comparable.empty:
                        similar_state_net_return_mean = float(
                            comparable["net_return"].mean()
                        )
                runner_up = eligible[1][0] if len(eligible) > 1 else 0.0
                marginal_edge = float(best[0] - runner_up)
            else:
                selected_policy = "flat" if "flat" in policy_ids else policy_ids[0]
                selected_signal = float(row[selected_policy])
                selected_meta = metadata.get(selected_policy, {})
                selected_weights = dict(
                    selected_meta.get("weights", {selected_policy: 1.0})
                )
        current_for_transition = "FLAT" if actual_previous == 0.0 else position_state
        position_state = next_position_state(
            current_for_transition,
            float(selected_signal),
            current_position=actual_previous,
            marginal_edge=marginal_edge,
            risk_capacity=1.0,
        )
        ledger_rows.append(
            {
                "decision_time": decision_time,
                "selected_policy_id": selected_policy,
                "selected_signal": selected_signal,
                "selected_weights": selected_weights,
                "selected_memory": selected_memory,
                "selected_horizon_sessions": selected_meta.get("horizon_sessions"),
                "selected_side": selected_meta.get("side"),
                "selected_exposure": selected_meta.get("exposure"),
                "similar_state_refs": similar_refs,
                "similar_state_net_return_mean": similar_state_net_return_mean,
                "position_state": position_state,
                "marginal_edge": marginal_edge,
                "max_outcome_available_at_used": max_used,
                "objective_window_sessions": int(objective_window),
            }
        )
        if decision_time in path_by_time.index:
            outcome = path_by_time.loc[decision_time]
            turnover = abs(selected_signal - actual_previous)
            pnl = selected_signal * float(outcome["path_move_per_mmbtu"]) * multiplier
            pnl -= turnover * cost_per_side_usd
            actual_rows.append(
                {
                    "decision_time": decision_time,
                    "outcome_available_at": outcome["outcome_available_at"],
                    "selected_policy_id": selected_policy,
                    "signal": selected_signal,
                    "turnover": turnover,
                    "realized_net_return": pnl / capital_usd,
                }
            )
        actual_previous = selected_signal
    ledger = pd.DataFrame(ledger_rows)
    consequences = pd.DataFrame(actual_rows)
    return AdaptiveBlockResult(ledger, consequences, _freeze_frame(ledger))
