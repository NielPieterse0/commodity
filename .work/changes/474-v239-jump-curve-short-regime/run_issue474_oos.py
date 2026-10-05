from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
MAIN_REPO = REPO.parents[2] if REPO.parent.name == "worktrees" else REPO
PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
EXPERIMENT = PROGRAMME / "lines/001-v2-optimization-execution/experiments/474-jump-curve-short-regime"
V3_PREREG = PROGRAMME / "issue465-block1-controller-v3-prereg.json"
V1_PREREG = PROGRAMME / "issue465-prereg-v1.json"
MARKET_INPUTS = MAIN_REPO / ".work/worktrees/356-market-only-nested-walk-forward/.work/checkpoints/356-market-only-nested-walk-forward/inputs"
BLOCK1_SESSIONS = PROGRAMME / "issue465-block1-controller-v3-execution-sessions.csv"
GID = "e3e221b3c9d945813e92cef9dbef8fd0"
GEN = MAIN_REPO / ".work/temp/470-closeout-cache/generations" / GID
CAPITAL = 100000.0
MULTIPLIER = 10000.0
BASE_COST = 15.0

BLOCKS = {
    "block1": ("2010-07-06T00:00:00Z", "2011-01-06T00:00:00Z"),
    "block2": ("2011-01-06T00:00:00Z", "2011-07-06T00:00:00Z"),
    "block3": ("2011-07-06T00:00:00Z", "2012-01-06T00:00:00Z"),
    "block4": ("2012-01-06T00:00:00Z", "2012-07-06T00:00:00Z"),
}
SCENARIOS = {
    "base": {"extra_slippage": 0.0, "miss_increase": False},
    "moderate": {"extra_slippage": 15.0, "miss_increase": True},
    "severe": {"extra_slippage": 30.0, "miss_increase": True},
}
CANDIDATES = {
    "A": "high_jump_and_contango",
    "B": "aligned_jump_curve",
}
EXPOSURES = (1.0, 1.5)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()

def source_contract() -> dict[str, Any]:
    prereg = json.loads(V1_PREREG.read_text(encoding="utf-8"))
    return dict(prereg["source_identity_contract"])


def verify_source_identity() -> dict[str, str]:
    contract = source_contract()
    paths = {
        "features": MARKET_INPUTS / "features.parquet",
        "session_path": MARKET_INPUTS / "session-path.parquet",
    }
    expected = {
        "features": str(contract["frozen_market_feature_sha256"]),
        "session_path": str(contract["frozen_session_path_sha256"]),
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    for name in actual:
        if actual[name] != expected[name]:
            raise RuntimeError(f"source identity changed for {name}: {actual[name]}")
    return actual


def load_market_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    verify_source_identity()
    features = pd.read_parquet(MARKET_INPUTS / "features.parquet")
    sessions = pd.read_parquet(MARKET_INPUTS / "session-path.parquet")
    features["trade_date"] = pd.to_datetime(features["trade_date"], utc=True)
    features["available_at"] = pd.to_datetime(features["available_at"], utc=True)
    for column in ("trade_date", "session_open", "available_at", "next_session_open"):
        sessions[column] = pd.to_datetime(sessions[column], utc=True)
    return features, sessions.sort_values("session_open", kind="stable").reset_index(drop=True)

def build_state_for_block(
    features: pd.DataFrame, sessions: pd.DataFrame, start_text: str, end_text: str,
) -> pd.DataFrame:
    start = pd.Timestamp(start_text)
    end = pd.Timestamp(end_text)
    block_features = features.loc[
        (features["trade_date"] >= start) & (features["trade_date"] < end)
    ].copy()
    selected = sessions[["trade_date", "available_at"]].rename(
        columns={"available_at": "selected_available_at"}
    )
    merged = block_features.merge(selected, on="trade_date", how="left", validate="one_to_one")
    merged["decision_time"] = merged[["available_at", "selected_available_at"]].max(axis=1)
    opens = sessions["session_open"].to_numpy(dtype="datetime64[ns]")
    records: list[dict[str, Any]] = []
    for row in merged.sort_values("trade_date", kind="stable").itertuples(index=False):
        signal = pd.Timestamp(row.decision_time)
        fill_index = int(np.searchsorted(opens, signal.to_datetime64(), side="right"))
        if fill_index >= len(sessions):
            continue
        fill = sessions.iloc[fill_index]
        if pd.Timestamp(fill["next_session_open"]) >= end:
            continue
        records.append({
            "trade_date": pd.Timestamp(row.trade_date),
            "decision_time": signal,
            "fill_timestamp": pd.Timestamp(fill["session_open"]),
            "fill_contract_id": str(fill["contract_id"]),
        })
    state = pd.DataFrame(records)
    state = state.sort_values(
        ["fill_timestamp", "decision_time", "trade_date"], kind="stable"
    ).drop_duplicates("fill_timestamp", keep="last")
    state = state.sort_values("decision_time", kind="stable").reset_index(drop=True)
    state = state.merge(features, on="trade_date", how="left", validate="one_to_one")
    return enrich_derived_state(state)

def enrich_derived_state(state: pd.DataFrame) -> pd.DataFrame:
    out = state.copy()
    vol20 = pd.to_numeric(out["feature_vol_20"], errors="raise").astype(float)
    ret1 = pd.to_numeric(out["feature_ret_1"], errors="raise").astype(float)
    out["derived_jump_intensity"] = ret1.abs() / vol20.clip(lower=1e-12)
    out["derived_prior60_jump_q67"] = (
        out["derived_jump_intensity"].shift(1).rolling(60, min_periods=20).quantile(0.67)
    )
    log_volume = pd.to_numeric(out["feature_curve_log_volume_m1"], errors="raise").astype(float)
    out["derived_prior20_log_volume_m1_median"] = (
        log_volume.shift(1).rolling(20, min_periods=5).median()
        .fillna(log_volume.expanding().median().shift(1))
        .fillna(log_volume.iloc[0])
    )
    settle = np.exp(pd.to_numeric(out["feature_curve_log_settle_m1"], errors="raise").astype(float))
    out["derived_settle_m1"] = settle
    return out


def build_execution_path(state: pd.DataFrame, sessions: pd.DataFrame, end_text: str) -> pd.DataFrame:
    boundary = pd.Timestamp(end_text)
    index_by_open = {pd.Timestamp(value): index for index, value in enumerate(sessions["session_open"])}
    fill_times = pd.to_datetime(state["fill_timestamp"], utc=True).tolist()
    rows: list[dict[str, Any]] = []
    for index, state_row in state.reset_index(drop=True).iterrows():
        fill_time = pd.Timestamp(state_row["fill_timestamp"])
        start = index_by_open[fill_time]
        session = sessions.iloc[start]
        if str(session["contract_id"]) != str(state_row["fill_contract_id"]):
            raise RuntimeError("held-contract identity mismatch")
        interval_end = fill_times[index + 1] if index + 1 < len(fill_times) else boundary
        interval = sessions.loc[
            (sessions["session_open"] >= fill_time)
            & (sessions["session_open"] < interval_end)
            & (sessions["next_session_open"] < boundary)
        ].copy()
        if interval.empty:
            raise RuntimeError(f"execution interval is empty at {fill_time}")
        rows.append({
            "decision_time": pd.Timestamp(state_row["decision_time"]),
            "fill_timestamp": fill_time,
            "fill_contract_id": str(state_row["fill_contract_id"]),
            "fill_price": float(session["open_price"]),
            "holding_move_per_mmbtu": float(
                pd.to_numeric(interval["path_move_per_mmbtu"], errors="raise").sum()
            ),
            "holding_roll_count": int(interval["roll_at_next_open"].astype(bool).sum()),
        })
    return pd.DataFrame(rows)


def candidate_masks(state: pd.DataFrame) -> dict[str, pd.Series]:
    q67 = pd.to_numeric(state["derived_prior60_jump_q67"], errors="coerce")
    jump = pd.to_numeric(state["derived_jump_intensity"], errors="raise")
    curve = pd.to_numeric(state["feature_curve_slope_m1_m4"], errors="raise")
    high_jump = q67.notna() & (jump > q67)
    low_jump = q67.notna() & ~high_jump
    contango = curve > 0.0
    backwardation = curve <= 0.0
    return {
        "high_jump_contango": high_jump & contango,
        "low_jump_contango": low_jump & contango,
        "high_jump_backwardation": high_jump & backwardation,
        "low_jump_backwardation": low_jump & backwardation,
        "A": high_jump & contango,
        "B": (high_jump & contango) | (low_jump & backwardation),
    }


def execution_turnover(current: float, target: float, current_contract: str | None, target_contract: str) -> float:
    if current != 0.0 and target != 0.0 and current * target > 0.0 and current_contract != target_contract:
        return abs(current) + abs(target)
    if current * target < 0.0:
        return abs(current) + abs(target)
    return abs(target - current)

def evaluate_mask(
    state: pd.DataFrame,
    path: pd.DataFrame,
    active_mask: pd.Series,
    exposure: float,
    scenario_id: str,
    *,
    start_index: int = 0,
) -> pd.DataFrame:
    scenario = SCENARIOS[scenario_id]
    cost_per_side = BASE_COST + float(scenario["extra_slippage"])
    current = 0.0
    current_contract: str | None = None
    records: list[dict[str, Any]] = []
    for i in range(start_index, len(state)):
        requested = -float(exposure) if bool(active_mask.iloc[i]) else 0.0
        low_liquidity = float(state.loc[i, "feature_curve_log_volume_m1"]) < float(
            state.loc[i, "derived_prior20_log_volume_m1_median"]
        )
        missed = False
        executed = requested
        if bool(scenario["miss_increase"]) and low_liquidity:
            if current == 0.0 and requested != 0.0:
                executed, missed = 0.0, True
            elif current * requested < 0.0:
                executed, missed = 0.0, True
            elif current * requested > 0.0 and abs(requested) > abs(current):
                executed, missed = current, True
        target_contract = str(path.loc[i, "fill_contract_id"])
        transition = execution_turnover(current, executed, current_contract, target_contract)
        roll = 2.0 * abs(executed) * float(path.loc[i, "holding_roll_count"])
        gross = executed * float(path.loc[i, "holding_move_per_mmbtu"]) * MULTIPLIER / CAPITAL
        net = gross - (transition + roll) * cost_per_side / CAPITAL
        records.append({
            "decision_time": pd.Timestamp(state.loc[i, "decision_time"]),
            "requested_target": requested,
            "executed_target": executed,
            "missed_fill": missed,
            "transition_turnover": transition,
            "roll_turnover": roll,
            "gross_return": gross,
            "net_return": net,
        })
        current = executed
        current_contract = target_contract if executed != 0.0 else None
    return pd.DataFrame(records)

def max_drawdown(net_returns: pd.Series) -> float:
    values = pd.to_numeric(net_returns, errors="raise").to_numpy(dtype=float)
    equity = 1.0 + np.cumsum(values)
    equity = np.concatenate(([1.0], equity))
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / np.maximum(peak, 1e-12)
    return float(np.max(drawdown))


def signal_episode_count(mask: pd.Series) -> int:
    values = mask.astype(bool).to_numpy()
    if len(values) == 0:
        return 0
    return int(values[0]) + int(np.sum(values[1:] & ~values[:-1]))


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"net_return": 0.0, "gross_return": 0.0, "max_drawdown": 0.0,
                "active_rows": 0, "missed_fills": 0, "turnover": 0.0, "monthly": {}}
    monthly = frame.assign(
        month=frame["decision_time"].dt.tz_convert("UTC").dt.strftime("%Y-%m")
    ).groupby("month")["net_return"].sum()
    return {
        "net_return": float(frame["net_return"].sum()),
        "gross_return": float(frame["gross_return"].sum()),
        "max_drawdown": max_drawdown(frame["net_return"]),
        "active_rows": int(frame["executed_target"].ne(0.0).sum()),
        "missed_fills": int(frame["missed_fill"].sum()),
        "turnover": float((frame["transition_turnover"] + frame["roll_turnover"]).sum()),
        "monthly": {str(k): float(v) for k, v in monthly.items()},
    }


def evaluate_candidate_bundle(state: pd.DataFrame, path: pd.DataFrame, candidate: str) -> dict[str, Any]:
    masks = candidate_masks(state)
    active = masks[candidate]
    result: dict[str, Any] = {"signal_rows": int(active.sum()), "signal_episodes": signal_episode_count(active)}
    for exposure in EXPOSURES:
        key = f"{exposure:.1f}"
        result[key] = {
            scenario: summarize(evaluate_mask(state, path, active, exposure, scenario))
            for scenario in SCENARIOS
        }
    return result

def evaluate_leg_bundle(state: pd.DataFrame, path: pd.DataFrame) -> dict[str, Any]:
    masks = candidate_masks(state)
    result: dict[str, Any] = {}
    for leg in (
        "high_jump_contango", "low_jump_contango",
        "high_jump_backwardation", "low_jump_backwardation",
    ):
        mask = masks[leg]
        result[leg] = {
            "signal_rows": int(mask.sum()),
            "signal_episodes": signal_episode_count(mask),
            "1.5": {
                scenario: summarize(evaluate_mask(state, path, mask, 1.5, scenario))
                for scenario in SCENARIOS
            },
        }
    return result


def evaluate_always_short(state: pd.DataFrame, path: pd.DataFrame) -> dict[str, Any]:
    mask = pd.Series(True, index=state.index)
    return {
        f"{exposure:.1f}": {
            scenario: summarize(evaluate_mask(state, path, mask, exposure, scenario))
            for scenario in SCENARIOS
        }
        for exposure in EXPOSURES
    }


def evaluate_block(features: pd.DataFrame, sessions: pd.DataFrame, block_id: str) -> dict[str, Any]:
    start, end = BLOCKS[block_id]
    state = build_state_for_block(features, sessions, start, end)
    path = build_execution_path(state, sessions, end)
    return {
        "block_id": block_id,
        "start_inclusive": start,
        "end_exclusive": end,
        "decision_rows": len(state),
        "candidates": {
            candidate: evaluate_candidate_bundle(state, path, candidate)
            for candidate in CANDIDATES
        },
        "state_legs": evaluate_leg_bundle(state, path),
        "always_short": evaluate_always_short(state, path),
    }

def block1_reference_state() -> pd.DataFrame:
    brain = pd.read_json(GEN / "issue465-block1-controller-v3-decision-brain.jsonl", lines=True)
    state = pd.json_normalize(brain["pit_state"])
    state["decision_time"] = pd.to_datetime(brain["decision_time"], utc=True)
    state["fill_timestamp"] = pd.to_datetime(state["fill_timestamp"], utc=True)
    return state.reset_index(drop=True)


def assert_block1_reconstruction(state: pd.DataFrame) -> dict[str, Any]:
    reference = block1_reference_state()
    if len(state) != len(reference):
        raise AssertionError(f"Block1 state row mismatch: {len(state)} != {len(reference)}")
    for column in ("decision_time", "fill_timestamp"):
        left = pd.to_datetime(state[column], utc=True)
        right = pd.to_datetime(reference[column], utc=True)
        if not left.equals(right):
            raise AssertionError(f"Block1 {column} mismatch")
    if not state["fill_contract_id"].astype(str).equals(reference["fill_contract_id"].astype(str)):
        raise AssertionError("Block1 fill contract mismatch")
    numeric = (
        "derived_jump_intensity", "derived_prior60_jump_q67",
        "derived_prior20_log_volume_m1_median", "feature_curve_slope_m1_m4",
    )
    max_diffs: dict[str, float] = {}
    for column in numeric:
        left = pd.to_numeric(state[column], errors="coerce").to_numpy(dtype=float)
        right = pd.to_numeric(reference[column], errors="coerce").to_numpy(dtype=float)
        if not np.allclose(left, right, atol=1e-12, rtol=0.0, equal_nan=True):
            raise AssertionError(f"Block1 {column} reconstruction mismatch")
        finite = np.isfinite(left) & np.isfinite(right)
        max_diffs[column] = float(np.max(np.abs(left[finite] - right[finite]))) if finite.any() else 0.0
    return {"status": "PASS", "row_count": len(state), "max_abs_diffs": max_diffs}

def verify_block1_economics(state: pd.DataFrame, path: pd.DataFrame) -> dict[str, Any]:
    expected_full = {
        "A": {"base": 0.12645, "moderate": 0.05010, "severe": 0.04425},
        "B": {"base": 0.20700, "moderate": 0.11730, "severe": 0.11010},
    }
    expected_post = {
        "A": {"base": 0.07425, "moderate": 0.03000, "severe": 0.02460},
        "B": {"base": 0.15480, "moderate": 0.09720, "severe": 0.09045},
    }
    masks = candidate_masks(state)
    evidence: dict[str, Any] = {}
    for candidate in CANDIDATES:
        evidence[candidate] = {"full": {}, "post_warmup_reset_flat": {}}
        for scenario in SCENARIOS:
            full = summarize(evaluate_mask(state, path, masks[candidate], 1.5, scenario))
            post = summarize(evaluate_mask(state, path, masks[candidate], 1.5, scenario, start_index=30))
            for label, observed, expected in (
                ("full", full["net_return"], expected_full[candidate][scenario]),
                ("post_warmup_reset_flat", post["net_return"], expected_post[candidate][scenario]),
            ):
                if not np.isclose(float(observed), float(expected), atol=1e-12, rtol=0.0):
                    raise AssertionError(
                        f"Block1 {candidate} {scenario} {label} mismatch: {observed} != {expected}"
                    )
            evidence[candidate]["full"][scenario] = full
            evidence[candidate]["post_warmup_reset_flat"][scenario] = post
    return {"status": "PASS", "metrics": evidence}

def future_invariance_proof(state: pd.DataFrame, path: pd.DataFrame) -> dict[str, Any]:
    cutoffs = [30, 60, 90]
    proofs: list[dict[str, Any]] = []
    base_masks = candidate_masks(state)
    for cutoff in cutoffs:
        mutated_state = state.copy(deep=True)
        future = mutated_state.index > cutoff
        mutated_state.loc[future, "feature_ret_1"] = (
            pd.to_numeric(mutated_state.loc[future, "feature_ret_1"], errors="raise") * -1000.0 + 7.0
        )
        mutated_state.loc[future, "feature_curve_slope_m1_m4"] = (
            -pd.to_numeric(mutated_state.loc[future, "feature_curve_slope_m1_m4"], errors="raise") - 0.01
        )
        mutated_state.loc[future, "feature_curve_log_volume_m1"] = (
            pd.to_numeric(mutated_state.loc[future, "feature_curve_log_volume_m1"], errors="raise") + 5.0
        )
        mutated_state = enrich_derived_state(mutated_state)
        mutated_path = path.copy(deep=True)
        mutated_path.loc[mutated_path.index > cutoff, "holding_move_per_mmbtu"] = 9999.0
        mutated_path.loc[mutated_path.index > cutoff, "holding_roll_count"] = 99
        mutated_path.loc[mutated_path.index > cutoff, "fill_contract_id"] = "FUTURE-MUTATION"
        mutated_masks = candidate_masks(mutated_state)
        for candidate in CANDIDATES:
            if not base_masks[candidate].iloc[: cutoff + 1].reset_index(drop=True).equals(
                mutated_masks[candidate].iloc[: cutoff + 1].reset_index(drop=True)
            ):
                raise AssertionError(f"future mutation changed {candidate} detector prefix at {cutoff}")
            for scenario in SCENARIOS:
                base_run = evaluate_mask(state, path, base_masks[candidate], 1.5, scenario)
                mutated_run = evaluate_mask(
                    mutated_state, mutated_path, mutated_masks[candidate], 1.5, scenario
                )
                columns = [
                    "requested_target", "executed_target", "missed_fill",
                    "transition_turnover", "roll_turnover",
                ]
                left = base_run.loc[:cutoff, columns].reset_index(drop=True)
                right = mutated_run.loc[:cutoff, columns].reset_index(drop=True)
                if not left.equals(right):
                    raise AssertionError(
                        f"future mutation changed {candidate}/{scenario} lifecycle prefix at {cutoff}"
                    )
        proofs.append({"cutoff_index": cutoff, "prefix_rows": cutoff + 1, "status": "PASS"})
    return {"status": "PASS", "proofs": proofs}

def aggregate_path(blocks: dict[str, dict[str, Any]], owner: str, exposure: str, scenario: str) -> dict[str, Any]:
    rows = []
    for block_id, block in blocks.items():
        if owner == "always_short":
            metric = block["always_short"][exposure][scenario]
        else:
            metric = block["candidates"][owner][exposure][scenario]
        rows.append((block_id, metric))
    returns = [float(metric["net_return"]) for _, metric in rows]
    positive = [value for value in returns if value > 0.0]
    total_positive = sum(positive)
    concentration = (
        max(positive) / total_positive if total_positive > 0.0 and positive else None
    )
    max_dd = max(float(metric["max_drawdown"]) for _, metric in rows)
    total = float(sum(returns))
    return {
        "net_return": total,
        "block_returns": {block_id: float(metric["net_return"]) for block_id, metric in rows},
        "positive_blocks": int(sum(value > 0.0 for value in returns)),
        "max_block_drawdown": max_dd,
        "positive_block_concentration": concentration,
        "return_to_max_block_drawdown": (
            total / max_dd if max_dd > 1e-12 else (float("inf") if total > 0.0 else 0.0)
        ),
    }


def oos_disposition(blocks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {"candidates": {}, "always_short": {}}
    for candidate in CANDIDATES:
        aggregate["candidates"][candidate] = {
            exposure: {
                scenario: aggregate_path(blocks, candidate, exposure, scenario)
                for scenario in SCENARIOS
            }
            for exposure in ("1.0", "1.5")
        }
    aggregate["always_short"] = {
        exposure: {
            scenario: aggregate_path(blocks, "always_short", exposure, scenario)
            for scenario in SCENARIOS
        }
        for exposure in ("1.0", "1.5")
    }
    notable: dict[str, Any] = {}
    always_severe = aggregate["always_short"]["1.5"]["severe"]
    for candidate in CANDIDATES:
        canonical = aggregate["candidates"][candidate]["1.5"]
        scale = aggregate["candidates"][candidate]["1.0"]
        total_episodes = sum(
            int(block["candidates"][candidate]["signal_episodes"]) for block in blocks.values()
        )
        blocks_with_signal = sum(
            int(block["candidates"][candidate]["signal_rows"]) > 0 for block in blocks.values()
        )
        severe = canonical["severe"]
        severe_ratio = float(severe["return_to_max_block_drawdown"])
        always_ratio = float(always_severe["return_to_max_block_drawdown"])
        gates = {
            "all_1p5_scenarios_positive": all(
                float(canonical[scenario]["net_return"]) > 0.0 for scenario in SCENARIOS
            ),
            "severe_positive_in_at_least_two_blocks": int(severe["positive_blocks"]) >= 2,
            "one_contract_severe_positive": float(scale["severe"]["net_return"]) > 0.0,
            "signals_span_at_least_two_blocks": blocks_with_signal >= 2,
            "multiple_signal_episodes": total_episodes >= 2,
            "severe_net_at_least_three_percent": float(severe["net_return"]) >= 0.03,
            "severe_max_drawdown_below_ten_percent": float(severe["max_block_drawdown"]) <= 0.10,
            "stress_drawdown_not_worse_than_always_short": (
                float(severe["max_block_drawdown"]) <= float(always_severe["max_block_drawdown"]) + 1e-12
            ),
            "stress_return_to_drawdown_beats_always_short": severe_ratio > always_ratio,
            "positive_block_concentration_below_80pct": (
                severe["positive_block_concentration"] is not None
                and float(severe["positive_block_concentration"]) <= 0.80
            ),
        }
        notable[candidate] = {
            "gates": gates,
            "pass": all(gates.values()),
            "total_signal_episodes": total_episodes,
            "blocks_with_signal": blocks_with_signal,
        }

    second_leg_blocks = {}
    for block_id, block in blocks.items():
        leg = block["state_legs"]["low_jump_backwardation"]
        second_leg_blocks[block_id] = {
            "signal_rows": int(leg["signal_rows"]),
            "signal_episodes": int(leg["signal_episodes"]),
            "severe_net_return": float(leg["1.5"]["severe"]["net_return"]),
        }
    second_leg_positive_blocks = sum(
        row["signal_rows"] > 0 and row["severe_net_return"] > 0.0
        for row in second_leg_blocks.values()
    )
    a_stress = aggregate["candidates"]["A"]["1.5"]
    b_stress = aggregate["candidates"]["B"]["1.5"]
    b_increment = {
        scenario: float(b_stress[scenario]["net_return"] - a_stress[scenario]["net_return"])
        for scenario in SCENARIOS
    }
    b_incremental_gate = {
        "second_leg_positive_in_more_than_one_block": second_leg_positive_blocks >= 2,
        "moderate_increment_at_least_two_percent": b_increment["moderate"] >= 0.02,
        "severe_increment_at_least_two_percent": b_increment["severe"] >= 0.02,
        "severe_drawdown_not_materially_worse_than_A": (
            float(b_stress["severe"]["max_block_drawdown"])
            <= float(a_stress["severe"]["max_block_drawdown"]) + 0.01
        ),
    }
    b_eligible = bool(notable["B"]["pass"] and all(b_incremental_gate.values()))
    a_eligible = bool(notable["A"]["pass"])
    if b_eligible:
        selected = "B"
        disposition = "FREEZE_CANDIDATE_B"
    elif a_eligible:
        selected = "A"
        disposition = "FREEZE_CANDIDATE_A"
    else:
        selected = None
        disposition = "REJECT_OR_MATERIALLY_WEAKEN_SHORT_REGIME_THESIS"
    return {
        "aggregate": aggregate,
        "notable_edge_gates": notable,
        "candidate_b_second_leg_by_block": second_leg_blocks,
        "candidate_b_increment_vs_a": b_increment,
        "candidate_b_incremental_gate": b_incremental_gate,
        "selected_candidate": selected,
        "disposition": disposition,
        "retuning_authorized": False,
    }


def freeze_contract() -> dict[str, Any]:
    path = EXPERIMENT / "design-freeze.json"
    if not path.is_file():
        raise RuntimeError("design freeze is missing; untouched scoring is prohibited")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "FROZEN_BEFORE_BLOCKS_2_4":
        raise RuntimeError("design freeze status does not authorize untouched scoring")
    runner_sha = sha256_file(Path(__file__))
    if payload.get("runner_sha256") != runner_sha:
        raise RuntimeError("runner identity differs from frozen design")
    if payload.get("source_generation") != GID:
        raise RuntimeError("source generation differs from frozen design")
    return payload

def verify_block1() -> dict[str, Any]:
    features, sessions = load_market_sources()
    start, end = BLOCKS["block1"]
    state = build_state_for_block(features, sessions, start, end)
    reconstruction = assert_block1_reconstruction(state)
    path = build_execution_path(state, sessions, end)
    economics = verify_block1_economics(state, path)
    invariance = future_invariance_proof(state, path)
    return {
        "schema_version": 1,
        "status": "PASS",
        "source_generation": GID,
        "source_sha256": verify_source_identity(),
        "runner_sha256": sha256_file(Path(__file__)),
        "reconstruction": reconstruction,
        "economics": economics,
        "future_invariance": invariance,
        "later_block_outcomes_scored": False,
        "protected_confirmation_accessed": False,
    }


def run_untouched() -> dict[str, Any]:
    freeze = freeze_contract()
    features, sessions = load_market_sources()
    blocks: dict[str, dict[str, Any]] = {}
    for block_id in ("block2", "block3", "block4"):
        blocks[block_id] = evaluate_block(features, sessions, block_id)
    disposition = oos_disposition(blocks)
    return {
        "schema_version": 1,
        "status": "SCORED_FROZEN_UNTOUCHED_BLOCKS_2_4",
        "source_generation": GID,
        "source_sha256": verify_source_identity(),
        "runner_sha256": sha256_file(Path(__file__)),
        "design_freeze_sha256": sha256_file(EXPERIMENT / "design-freeze.json"),
        "freeze_id": freeze["freeze_id"],
        "blocks": blocks,
        "disposition": disposition,
        "ordinary_tuning_performed": False,
        "protected_confirmation_accessed": False,
    }

def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, default=str) + "\n"
    path.write_bytes(rendered.encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify-block1", "run-untouched"))
    args = parser.parse_args()
    if args.command == "verify-block1":
        payload = verify_block1()
        output = Path(__file__).with_name("evidence") / "block1-reproduction.json"
    else:
        payload = run_untouched()
        output = EXPERIMENT / "results.json"
    write_json(output, payload)
    print(json.dumps({
        "status": payload["status"],
        "output": str(output),
        "output_sha256": sha256_file(output),
        "disposition": payload.get("disposition"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
