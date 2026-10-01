from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts/research"))

import run_issue428_decision_optimization as issue428

from commodity import v2_decision_optimization as dec
from commodity import v2_joint_advantage as joint
from commodity import v2_optimization as v2
from commodity.market_only_phase2 import _load_inherited_risk_and_costs
from commodity.stacking_policy import replay_bounded_fractional_policy

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue459-prereg-v1.json"
ADVANTAGE_MAP = PROGRAMME / "issue459-advantage-map-v1.json"
PREFLIGHT = PROGRAMME / "issue459-preflight-v1.json"
RESULT = PROGRAMME / "issue459-wave1-result-v1.json"
LEDGER = PROGRAMME / "issue459-wave1-trials-v1.jsonl"
WAVE2_PREREG = PROGRAMME / "issue459-wave2-prereg-v2.json"
WAVE2_PREFLIGHT = PROGRAMME / "issue459-wave2-preflight-v2.json"
WAVE2_RESULT = PROGRAMME / "issue459-wave2-result-v2.json"
WAVE2_LEDGER = PROGRAMME / "issue459-wave2-trials-v2.jsonl"
PHASE2 = REPO / "config/phase2_market_only.json"
ISSUE428_RESULT = PROGRAMME / "issue428-result-v1.json"
ISSUE459_POSITION_LEVELS = (-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def load_prereg() -> dict[str, Any]:
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen_before_issue459_scoring":
        raise RuntimeError("issue459 preregistration is not frozen")
    boundary = payload.get("evidence_boundary", {})
    if boundary.get("latest_allowed_trade_date") != "2022-12-31":
        raise RuntimeError("issue459 development cutoff changed")
    if boundary.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue459 protected evidence flag is not false")
    return payload


def load_advantage_map() -> dict[str, Any]:
    payload = json.loads(ADVANTAGE_MAP.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("issue") != 459:
        raise RuntimeError("issue459 advantage map identity is invalid")
    if payload.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue459 advantage map opened protected evidence")
    return payload


def load_wave2_prereg() -> dict[str, Any]:
    payload = json.loads(WAVE2_PREREG.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen_before_issue459_wave2_scoring":
        raise RuntimeError("issue459 wave2 preregistration is not frozen")
    boundary = payload.get("evidence_boundary", {})
    if boundary.get("latest_allowed_trade_date") != "2022-12-31":
        raise RuntimeError("issue459 wave2 development cutoff changed")
    if boundary.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue459 wave2 protected evidence flag is not false")
    return payload


def _load_specialist_frame(path: Path, value_column: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"trade_date", "prediction_time", value_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"issue459 specialist input missing columns: {missing}")
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"], utc=True, errors="raise", format="mixed"
    )
    frame["prediction_time"] = pd.to_datetime(
        frame["prediction_time"], utc=True, errors="raise", format="mixed"
    )
    frame[value_column] = pd.to_numeric(frame[value_column], errors="raise").astype(float)
    if frame["trade_date"].duplicated().any():
        raise RuntimeError("issue459 specialist input has duplicate origin trade dates")
    if frame[value_column].isna().any():
        raise RuntimeError("issue459 specialist input has missing values")
    cutoff = pd.Timestamp("2022-12-31", tz="UTC")
    if (frame["trade_date"] > cutoff).any():
        raise RuntimeError("issue459 specialist input crosses protected cutoff")
    return frame[["trade_date", "prediction_time", value_column]].copy()


def preflight(*, write: bool = True) -> dict[str, object]:
    prereg = load_prereg()
    advantage_map = load_advantage_map()
    issue428_prereg, features, sessions, _families, _support = issue428._load_inputs()
    failures: list[str] = []
    configs = joint.build_wave1_configs(prereg)
    declared_fractions = {float(value) for value in prereg["wave1_joint_scarcity_repair"]["position_fractions"]}
    replay_fractions = {abs(value) for value in ISSUE459_POSITION_LEVELS if value != 0.0}
    if declared_fractions != replay_fractions:
        failures.append("position_fraction_replay_contract_changed")
    gate_ids = {cfg.config_id for cfg in dec.build_issue428_candidate_grid(issue428_prereg)}
    for gate in prereg["wave1_joint_scarcity_repair"]["gate_families"]:
        mapped = joint.issue428_config_id_for_gate(str(gate))
        if mapped not in gate_ids:
            failures.append(f"missing_issue428_gate:{gate}:{mapped}")
    if len(advantage_map.get("priority_clues", [])) != int(
        prereg["historical_map"]["required_priority_clues"]
    ):
        failures.append("priority_clue_count_changed")
    if len(features) != 3088:
        failures.append(f"feature_row_count_changed:{len(features)}")
    if len(sessions) != 3897:
        failures.append(f"session_row_count_changed:{len(sessions)}")
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, _costs = _load_inherited_risk_and_costs(cfg)
    fixed = prereg["fixed_safety"]
    if not np.isclose(float(risk.peak_drawdown_kill_fraction), float(fixed["peak_drawdown_kill_fraction"])):
        failures.append("peak_drawdown_safety_changed")
    if not np.isclose(float(risk.daily_loss_fraction), float(fixed["daily_loss_fraction"])):
        failures.append("daily_loss_safety_changed")
    report: dict[str, object] = {
        "schema_version": 1,
        "issue": 459,
        "status": "PASS" if not failures else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "feature_rows": len(features),
        "session_rows": len(sessions),
        "wave1_candidate_count": len(configs),
        "priority_clue_count": len(advantage_map["priority_clues"]),
        "failures": failures,
        "prereg_sha256": sha256_file(PREREG),
        "advantage_map_sha256": sha256_file(ADVANTAGE_MAP),
        "issue428_result_sha256": sha256_file(ISSUE428_RESULT),
        "runner_sha256": sha256_file(Path(__file__)),
        "joint_code_sha256": sha256_file(REPO / "src/commodity/v2_joint_advantage.py"),
    }
    report["preflight_sha256"] = stable_sha(report)
    if write:
        PREFLIGHT.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return report


def preflight_wave2(*, write: bool = True) -> dict[str, object]:
    prereg = load_prereg()
    wave2 = load_wave2_prereg()
    failures: list[str] = []
    configs = joint.build_wave2_configs(wave2)
    parent_result = json.loads(RESULT.read_text(encoding="utf-8"))
    parent_preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    parent = wave2["parent_wave1"]
    if parent_result.get("result_sha256") != parent["result_sha256"]:
        failures.append("wave1_result_identity_changed")
    if parent_result.get("preflight_sha256") != parent["preflight_sha256"]:
        failures.append("wave1_result_preflight_binding_changed")
    if parent_preflight.get("preflight_sha256") != parent["preflight_sha256"]:
        failures.append("wave1_preflight_identity_changed")
    if sha256_file(LEDGER) != parent["trial_ledger_sha256"]:
        failures.append("wave1_trial_ledger_identity_changed")

    ledger_rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line]
    completed = pd.DataFrame([row for row in ledger_rows if row.get("status") == "complete"])
    evaluation = joint.evaluate_wave1_policies(completed, prereg)
    rule = parent["eligibility_rule"]
    fractions = {float(value) for value in rule["compatible_position_fractions"]}
    eligible = {
        str(row["policy_id"])
        for row in evaluation
        if float(row["mean_outer_monthly_net_return_delta"]) > float(rule["mean_outer_monthly_net_return_delta_gt"])
        and bool(row["effective_sample_pass"]) is bool(rule["effective_sample_pass_required"])
        and bool(row["kill_trigger_regression"]) is False
        and any(f"__f{fraction:.2f}__" in str(row["policy_id"]) for fraction in fractions)
    }
    frozen_parents = {str(value) for value in parent["eligible_parent_policy_ids"]}
    if eligible != frozen_parents:
        failures.append("wave2_parent_eligibility_set_changed")

    specialist_frames: dict[str, pd.DataFrame] = {}
    for name, column in (("timesfm", "timesfm_point_return"), ("kronos", "kronos_close_return")):
        spec = wave2["specialist_inputs"][name]
        path = REPO / str(spec["path"])
        if sha256_file(path) != spec["sha256"]:
            failures.append(f"{name}_feature_identity_changed")
        specialist_frames[name] = _load_specialist_frame(path, column)
        if len(specialist_frames[name]) != 3088:
            failures.append(f"{name}_row_count_changed:{len(specialist_frames[name])}")

    expected_trials = int(wave2["candidate_space"]["expected_outer_cost_trial_count"])
    computed_trials = len(configs) * len(wave2["evaluation"]["outer_blocks"]) * len(wave2["evaluation"]["cost_profiles"])
    if computed_trials != expected_trials:
        failures.append("wave2_outer_cost_trial_budget_changed")
    report: dict[str, object] = {
        "schema_version": 1,
        "issue": 459,
        "wave": 2,
        "status": "PASS" if not failures else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "wave2_candidate_count": len(configs),
        "expected_outer_cost_trial_count": expected_trials,
        "eligible_parent_count": len(frozen_parents),
        "timesfm_rows": len(specialist_frames["timesfm"]),
        "kronos_rows": len(specialist_frames["kronos"]),
        "failures": failures,
        "wave2_prereg_sha256": sha256_file(WAVE2_PREREG),
        "wave1_result_identity": parent_result.get("result_sha256"),
        "wave1_preflight_identity": parent_preflight.get("preflight_sha256"),
        "wave1_trial_ledger_sha256": sha256_file(LEDGER),
        "timesfm_sha256": sha256_file(REPO / str(wave2["specialist_inputs"]["timesfm"]["path"])),
        "kronos_sha256": sha256_file(REPO / str(wave2["specialist_inputs"]["kronos"]["path"])),
        "runner_sha256": sha256_file(Path(__file__)),
        "joint_code_sha256": sha256_file(REPO / "src/commodity/v2_joint_advantage.py"),
    }
    report["preflight_sha256"] = stable_sha(report)
    if write:
        WAVE2_PREFLIGHT.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return report


def _require_preflight() -> dict[str, Any]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue459 scoring requires a completed preflight")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("issue459 preflight is not a passing no-scoring report")
    expected = {
        "prereg_sha256": sha256_file(PREREG),
        "advantage_map_sha256": sha256_file(ADVANTAGE_MAP),
        "issue428_result_sha256": sha256_file(ISSUE428_RESULT),
        "runner_sha256": sha256_file(Path(__file__)),
        "joint_code_sha256": sha256_file(REPO / "src/commodity/v2_joint_advantage.py"),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"issue459 preflight is stale: {key}")
    return report


def _require_wave2_preflight() -> dict[str, Any]:
    if not WAVE2_PREFLIGHT.exists():
        raise RuntimeError("issue459 wave2 scoring requires a completed preflight")
    report = json.loads(WAVE2_PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("issue459 wave2 preflight is not a passing no-scoring report")
    wave2 = load_wave2_prereg()
    expected = {
        "wave2_prereg_sha256": sha256_file(WAVE2_PREREG),
        "wave1_trial_ledger_sha256": sha256_file(LEDGER),
        "timesfm_sha256": sha256_file(REPO / str(wave2["specialist_inputs"]["timesfm"]["path"])),
        "kronos_sha256": sha256_file(REPO / str(wave2["specialist_inputs"]["kronos"]["path"])),
        "runner_sha256": sha256_file(Path(__file__)),
        "joint_code_sha256": sha256_file(REPO / "src/commodity/v2_joint_advantage.py"),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"issue459 wave2 preflight is stale: {key}")
    return report


def _join_wave2_specialists(
    policy: pd.DataFrame,
    timesfm: pd.DataFrame,
    kronos: pd.DataFrame,
) -> pd.DataFrame:
    required = {"trade_date", "signal_timestamp"}
    missing = sorted(required - set(policy.columns))
    if missing:
        raise RuntimeError(f"issue459 wave2 policy missing join columns: {missing}")
    out = policy.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], utc=True, errors="raise")
    out["signal_timestamp"] = pd.to_datetime(out["signal_timestamp"], utc=True, errors="raise")
    if out["trade_date"].duplicated().any():
        raise RuntimeError("issue459 wave2 policy origin trade dates are not one-to-one")
    timesfm_join = timesfm.rename(columns={"prediction_time": "timesfm_prediction_time"})
    kronos_join = kronos.rename(columns={"prediction_time": "kronos_prediction_time"})
    out = out.merge(timesfm_join, on="trade_date", how="left", validate="one_to_one")
    out = out.merge(kronos_join, on="trade_date", how="left", validate="one_to_one")
    required_values = [
        "timesfm_prediction_time",
        "timesfm_point_return",
        "kronos_prediction_time",
        "kronos_close_return",
    ]
    if out[required_values].isna().any().any():
        raise RuntimeError("issue459 wave2 specialist join is incomplete")
    for column in ("timesfm_prediction_time", "kronos_prediction_time"):
        if (pd.to_datetime(out[column], utc=True, errors="raise") > out["signal_timestamp"]).any():
            raise RuntimeError("issue459 wave2 specialist prediction is after signal timestamp")
    return out


def _policy_id(config: joint.JointWave1Config) -> str:
    suffix = f"__{config.cost_profile}"
    if not config.config_id.endswith(suffix):
        raise RuntimeError("issue459 config/cost identity is inconsistent")
    return config.config_id[: -len(suffix)]


def _score_policy(
    sessions: pd.DataFrame,
    policy: pd.DataFrame,
    *,
    start: str,
    end: str,
    risk: object,
    costs: object,
    multiplier: float,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any], dict[str, Any]]:
    path, _start, _boundary = issue428._path_window(sessions, start_date=start, end_date=end)
    ledger, summary = replay_bounded_fractional_policy(
        path,
        issue428._policy_decisions(policy),
        risk,
        costs,
        contract_multiplier=multiplier,
        enforce_risk=True,
        allowed_position_levels=ISSUE459_POSITION_LEVELS,
    )
    score = v2.score_monthly_path(
        v2._phase2_ledger_for_monthly_score(ledger),
        starting_capital_usd=float(risk.capital_usd),
        latest_allowed_timestamp="2022-12-31",
    )
    effective = joint.executed_sample_summary(policy, ledger)
    return score, ledger, summary, effective


def _prepare_outer_context(
    *,
    outer_id: str,
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, Any],
    issue428_prereg: Mapping[str, Any],
    selected_reps: Mapping[str, Mapping[str, str]],
    selected_models: Mapping[str, Mapping[str, object]],
    matched_controls: Mapping[str, Mapping[str, object]],
    round_trip_usd: float,
) -> tuple[dict[str, str], list[str], object, pd.DataFrame, dict[str, object]]:
    blocks = issue428._outer_blocks(cfg)
    block = blocks[outer_id]
    signal_columns = issue428._signal_columns_for_outer(outer_id, selected_reps)
    opportunities = issue428._build_outer_opportunities(
        target_outer_id=outer_id,
        features=features,
        sessions=sessions,
        cfg=cfg,
        selected_config=selected_models[outer_id],
        matched_config=matched_controls[outer_id]["config"],
        signal_columns=signal_columns,
        round_trip_usd=round_trip_usd,
    )
    start = pd.Timestamp(str(block["start"]), tz="UTC")
    end = pd.Timestamp(str(block["end"]), tz="UTC")
    history = dec.completed_history_before(opportunities, start)
    fill_dates = pd.to_datetime(opportunities["fill_trade_date"], utc=True, errors="raise")
    outer = opportunities.loc[(fill_dates >= start) & (fill_dates <= end)].copy()
    if history.empty or outer.empty:
        raise RuntimeError(f"issue459 outer context is empty: {outer_id}")
    state, annotated_history, annotated_outer = issue428._annotated_context(
        history,
        outer,
        signal_columns,
        issue428_prereg,
        outcome_available_before=start,
    )
    meta_states, meta_diagnostics = issue428._fit_meta_states(
        annotated_history,
        signal_columns,
        issue428_prereg,
        outcome_available_before=start,
    )
    return block, signal_columns, state, annotated_outer, {
        "meta_states": meta_states,
        "meta_diagnostics": meta_diagnostics,
        "history_rows": len(history),
        "max_history_target_end": str(
            pd.to_datetime(history["target_end_timestamp"], utc=True, errors="raise").max()
        ),
    }


def _gate_policy_cache(
    annotated_outer: pd.DataFrame,
    *,
    state: object,
    meta_states: Mapping[str, object],
    signal_columns: list[str],
    issue428_prereg: Mapping[str, Any],
    gate_ids: list[str],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frozen = {
        config.config_id: config
        for config in dec.build_issue428_candidate_grid(issue428_prereg)
    }
    policies: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    for gate_id in gate_ids:
        config_id = joint.issue428_config_id_for_gate(gate_id)
        try:
            policies[gate_id] = issue428._score_policy(
                annotated_outer,
                frozen[config_id],
                state,
                meta_states,
                signal_columns,
            )
        except dec.Issue428DecisionError as exc:
            failures[gate_id] = str(exc)
    return policies, failures


def _baseline_joint_config(
    configs: list[joint.JointWave1Config],
    cost_profile: str,
) -> joint.JointWave1Config:
    matches = [
        config
        for config in configs
        if config.side_scope == "both"
        and config.gate_id == "baseline"
        and config.position_fraction == 1.0
        and config.lifecycle == "inherited_horizon"
        and config.cost_profile == cost_profile
    ]
    if len(matches) != 1:
        raise RuntimeError(f"issue459 baseline config identity changed: {cost_profile}")
    return matches[0]


def _wave1_config_for_policy(
    configs: list[joint.JointWave1Config],
    policy_id: str,
    cost_profile: str,
) -> joint.JointWave1Config:
    matches = [
        config
        for config in configs
        if _policy_id(config) == policy_id and config.cost_profile == cost_profile
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"issue459 wave2 parent config identity changed: {policy_id}:{cost_profile}"
        )
    return matches[0]


def _trial_row(
    *,
    config: joint.JointWave1Config,
    outer_id: str,
    score: Mapping[str, object],
    replay_summary: Mapping[str, object],
    effective: Mapping[str, object],
    baseline_score: Mapping[str, object],
    baseline_summary: Mapping[str, object],
    concentration: float,
) -> dict[str, object]:
    return {
        "issue": 459,
        "wave": 1,
        "evidence_class": "development",
        "status": "complete",
        "config_id": config.config_id,
        "policy_id": _policy_id(config),
        "outer_id": outer_id,
        "cost_profile": config.cost_profile,
        "side_scope": config.side_scope,
        "gate_id": config.gate_id,
        "position_fraction": config.position_fraction,
        "lifecycle": config.lifecycle,
        "mean_monthly_net_return_delta": float(score["mean_monthly_net_return"]) - float(baseline_score["mean_monthly_net_return"]),
        "total_net_pnl_usd_delta": float(score["total_net_pnl_usd"]) - float(baseline_score["total_net_pnl_usd"]),
        "selected_trades": int(effective["selected_trades"]),
        "nonempty_months": int(effective["nonempty_months"]),
        "requested_selected_trades": int(effective["requested_selected_trades"]),
        "kill_trigger_regression": int(replay_summary.get("risk_shutdown_sessions", 0)) > int(baseline_summary.get("risk_shutdown_sessions", 0)),
        "largest_incremental_month_fraction": float(concentration),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"]),
        "transaction_cost_usd": float(score["transaction_cost_usd"]),
        "long_net_pnl_usd": float(score["long_net_pnl_usd"]),
        "short_net_pnl_usd": float(score["short_net_pnl_usd"]),
        "score": dict(score),
        "replay_summary": dict(replay_summary),
        "effective_sample": dict(effective),
    }


def _wave2_trial_row(
    *,
    config: joint.JointWave2Config,
    cost_profile: str,
    outer_id: str,
    score: Mapping[str, object],
    replay_summary: Mapping[str, object],
    effective: Mapping[str, object],
    parent_score: Mapping[str, object],
    baseline_score: Mapping[str, object],
    baseline_summary: Mapping[str, object],
    concentration: float,
    short_modified_count: int,
    long_modified_count: int,
) -> dict[str, object]:
    candidate_return = float(score["mean_monthly_net_return"])
    parent_return = float(parent_score["mean_monthly_net_return"])
    baseline_return = float(baseline_score["mean_monthly_net_return"])
    return {
        "issue": 459,
        "wave": 2,
        "evidence_class": "development",
        "status": "complete",
        "config_id": f"{config.config_id}__{cost_profile}",
        "policy_id": config.config_id,
        "parent_policy_id": config.parent_policy_id,
        "outer_id": outer_id,
        "cost_profile": cost_profile,
        "short_mode": config.short_mode,
        "long_mode": config.long_mode,
        "mean_monthly_net_return_delta": candidate_return - baseline_return,
        "parent_mean_monthly_net_return_delta": parent_return - baseline_return,
        "specialist_incremental_mean_monthly_delta": candidate_return - parent_return,
        "total_net_pnl_usd_delta": float(score["total_net_pnl_usd"])
        - float(baseline_score["total_net_pnl_usd"]),
        "selected_trades": int(effective["selected_trades"]),
        "nonempty_months": int(effective["nonempty_months"]),
        "requested_selected_trades": int(effective["requested_selected_trades"]),
        "kill_trigger_regression": int(replay_summary.get("risk_shutdown_sessions", 0))
        > int(baseline_summary.get("risk_shutdown_sessions", 0)),
        "largest_incremental_month_fraction": float(concentration),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"]),
        "transaction_cost_usd": float(score["transaction_cost_usd"]),
        "long_net_pnl_usd": float(score["long_net_pnl_usd"]),
        "short_net_pnl_usd": float(score["short_net_pnl_usd"]),
        "short_modified_count": int(short_modified_count),
        "long_modified_count": int(long_modified_count),
        "score": dict(score),
        "replay_summary": dict(replay_summary),
        "effective_sample": dict(effective),
    }


def _evaluate_wave2(
    trials: pd.DataFrame,
    prereg: Mapping[str, Any],
    wave2: Mapping[str, Any],
) -> list[dict[str, Any]]:
    base_evaluation = joint.evaluate_wave1_policies(trials, prereg)
    base_rows = trials.loc[trials["cost_profile"].astype(str).eq("base")].copy()
    incremental = {
        str(policy_id): float(
            pd.to_numeric(group["specialist_incremental_mean_monthly_delta"], errors="raise").mean()
        )
        for policy_id, group in base_rows.groupby("policy_id", sort=True)
    }
    outer_incremental = {
        str(policy_id): {
            str(row.outer_id): float(row.specialist_incremental_mean_monthly_delta)
            for row in group.itertuples(index=False)
        }
        for policy_id, group in base_rows.groupby("policy_id", sort=True)
    }
    hurdle = float(wave2["evaluation"]["specialist_incremental_mean_monthly_delta_gt"])
    rows: list[dict[str, Any]] = []
    for row in base_evaluation:
        policy_id = str(row["policy_id"])
        specialist_delta = incremental[policy_id]
        item = dict(row)
        item["specialist_incremental_mean_monthly_delta"] = specialist_delta
        item["specialist_outer_incremental_delta"] = outer_incremental[policy_id]
        item["specialist_incremental_positive"] = specialist_delta > hurdle
        item["passes_wave2_gate"] = bool(
            row["passes_promotion_gate"] and item["specialist_incremental_positive"]
        )
        rows.append(item)
    return sorted(
        rows,
        key=lambda row: (
            not bool(row["passes_wave2_gate"]),
            -float(row["mean_outer_monthly_net_return_delta"]),
            -float(row["specialist_incremental_mean_monthly_delta"]),
            str(row["policy_id"]),
        ),
    )


def score_wave1() -> dict[str, object]:
    preflight_report = _require_preflight()
    prereg = load_prereg()
    issue428_prereg, features, sessions, _families, _support = issue428._load_inputs()
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    features = issue428._features_with_volatility_tail(features)
    selected_reps = issue428._selected_representations()
    selected_models = issue428._selected_model_configs()
    matched_controls = v2.load_issue426_outer_matched_controls(issue428.ISSUE425)
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    configs = joint.build_wave1_configs(prereg)
    gate_ids = [str(value) for value in prereg["wave1_joint_scarcity_repair"]["gate_families"]]
    trials: list[dict[str, object]] = []
    outer_diagnostics: dict[str, object] = {}

    for outer_id in map(str, prereg["wave1_joint_scarcity_repair"]["outer_blocks"]):
        block, signal_columns, state, annotated_outer, context = _prepare_outer_context(
            outer_id=outer_id,
            features=features,
            sessions=sessions,
            cfg=cfg,
            issue428_prereg=issue428_prereg,
            selected_reps=selected_reps,
            selected_models=selected_models,
            matched_controls=matched_controls,
            round_trip_usd=float(cost_profiles["base"].round_trip_usd),
        )
        gate_policies, gate_failures = _gate_policy_cache(
            annotated_outer,
            state=state,
            meta_states=context["meta_states"],
            signal_columns=signal_columns,
            issue428_prereg=issue428_prereg,
            gate_ids=gate_ids,
        )
        baselines: dict[str, tuple[dict[str, Any], pd.DataFrame, dict[str, Any], dict[str, Any]]] = {}
        for cost_name in prereg["wave1_joint_scarcity_repair"]["cost_profiles"]:
            cost_name = str(cost_name)
            base_config = _baseline_joint_config(configs, cost_name)
            base_policy = joint.apply_joint_candidate(gate_policies["baseline"], base_config)
            baselines[cost_name] = _score_policy(
                sessions,
                base_policy,
                start=str(block["start"]),
                end=str(block["end"]),
                risk=risk,
                costs=cost_profiles[cost_name],
                multiplier=multiplier,
            )

        outer_diagnostics[outer_id] = {
            "block": dict(block),
            "signal_columns": signal_columns,
            "history_rows": context["history_rows"],
            "max_history_target_end": context["max_history_target_end"],
            "meta_diagnostics": context["meta_diagnostics"],
            "gate_failures": gate_failures,
            "baseline_scores": {
                cost_name: baselines[cost_name][0]
                for cost_name in baselines
            },
            "baseline_replay_summaries": {
                cost_name: baselines[cost_name][2]
                for cost_name in baselines
            },
        }

        for config in configs:
            gate_policy = gate_policies.get(config.gate_id)
            if gate_policy is None:
                trials.append(
                    {
                        "issue": 459,
                        "wave": 1,
                        "evidence_class": "development",
                        "status": "ineligible",
                        "config_id": config.config_id,
                        "policy_id": _policy_id(config),
                        "outer_id": outer_id,
                        "cost_profile": config.cost_profile,
                        "reason": gate_failures.get(config.gate_id, "gate_unavailable"),
                    }
                )
                continue
            policy = joint.apply_joint_candidate(gate_policy, config)
            score, candidate_ledger, replay_summary, effective = _score_policy(
                sessions,
                policy,
                start=str(block["start"]),
                end=str(block["end"]),
                risk=risk,
                costs=cost_profiles[config.cost_profile],
                multiplier=multiplier,
            )
            baseline_score, baseline_ledger, baseline_summary, _baseline_effective = baselines[
                config.cost_profile
            ]
            concentration = joint.largest_incremental_month_fraction(
                candidate_ledger, baseline_ledger
            )
            trials.append(
                _trial_row(
                    config=config,
                    outer_id=outer_id,
                    score=score,
                    replay_summary=replay_summary,
                    effective=effective,
                    baseline_score=baseline_score,
                    baseline_summary=baseline_summary,
                    concentration=concentration,
                )
            )

    complete_rows = [row for row in trials if row.get("status") == "complete"]
    evaluation = joint.evaluate_wave1_policies(pd.DataFrame(complete_rows), prereg)
    passing = [row for row in evaluation if row["passes_promotion_gate"]]
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 459,
        "wave": 1,
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "claim_boundary": prereg["claim_boundary"],
        "declared_configuration_budget": int(
            prereg["search_budget"]["wave1_declared_cartesian_upper_bound"]
        ),
        "outer_blocks": list(prereg["wave1_joint_scarcity_repair"]["outer_blocks"]),
        "trial_count": len(trials),
        "complete_trial_count": len(complete_rows),
        "ineligible_trial_count": len(trials) - len(complete_rows),
        "evaluated_policy_count": len(evaluation),
        "passing_policy_count": len(passing),
        "top_policies": evaluation[:50],
        "passing_policies": passing,
        "outer_diagnostics": outer_diagnostics,
        "disposition": (
            "FREEZE_WAVE1_DEVELOPMENT_CANDIDATE"
            if passing
            else "CONTINUE_TO_WAVE2_SIDE_SPECIALIST_RECOMBINATION"
        ),
        "preflight_sha256": preflight_report["preflight_sha256"],
        "prereg_sha256": sha256_file(PREREG),
        "advantage_map_sha256": sha256_file(ADVANTAGE_MAP),
        "runner_sha256": sha256_file(Path(__file__)),
        "joint_code_sha256": sha256_file(REPO / "src/commodity/v2_joint_advantage.py"),
    }
    LEDGER.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in trials),
        encoding="utf-8",
        newline="\n",
    )
    result["trial_ledger_file_sha256"] = sha256_file(LEDGER)
    result["result_sha256"] = stable_sha(
        {key: value for key, value in result.items() if key != "result_sha256"}
    )
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def score_wave2() -> dict[str, object]:
    preflight_report = _require_wave2_preflight()
    prereg = load_prereg()
    wave2 = load_wave2_prereg()
    issue428_prereg, features, sessions, _families, _support = issue428._load_inputs()
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    features = issue428._features_with_volatility_tail(features)
    selected_reps = issue428._selected_representations()
    selected_models = issue428._selected_model_configs()
    matched_controls = v2.load_issue426_outer_matched_controls(issue428.ISSUE425)
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    wave1_configs = joint.build_wave1_configs(prereg)
    wave2_configs = joint.build_wave2_configs(wave2)
    parent_ids = [str(value) for value in wave2["parent_wave1"]["eligible_parent_policy_ids"]]
    timesfm = _load_specialist_frame(
        REPO / str(wave2["specialist_inputs"]["timesfm"]["path"]),
        "timesfm_point_return",
    )
    kronos = _load_specialist_frame(
        REPO / str(wave2["specialist_inputs"]["kronos"]["path"]),
        "kronos_close_return",
    )
    parent_base_configs = {
        parent_id: _wave1_config_for_policy(wave1_configs, parent_id, "base")
        for parent_id in parent_ids
    }
    gate_ids = sorted({"baseline", *(config.gate_id for config in parent_base_configs.values())})
    trials: list[dict[str, object]] = []
    outer_diagnostics: dict[str, object] = {}

    for outer_id in map(str, wave2["evaluation"]["outer_blocks"]):
        block, signal_columns, state, annotated_outer, context = _prepare_outer_context(
            outer_id=outer_id,
            features=features,
            sessions=sessions,
            cfg=cfg,
            issue428_prereg=issue428_prereg,
            selected_reps=selected_reps,
            selected_models=selected_models,
            matched_controls=matched_controls,
            round_trip_usd=float(cost_profiles["base"].round_trip_usd),
        )
        gate_policies, gate_failures = _gate_policy_cache(
            annotated_outer,
            state=state,
            meta_states=context["meta_states"],
            signal_columns=signal_columns,
            issue428_prereg=issue428_prereg,
            gate_ids=gate_ids,
        )
        if gate_failures:
            raise RuntimeError(f"issue459 wave2 frozen parent gate unavailable: {gate_failures}")

        baselines: dict[str, tuple[dict[str, Any], pd.DataFrame, dict[str, Any], dict[str, Any]]] = {}
        for cost_name in map(str, wave2["evaluation"]["cost_profiles"]):
            base_config = _baseline_joint_config(wave1_configs, cost_name)
            base_policy = joint.apply_joint_candidate(gate_policies["baseline"], base_config)
            baselines[cost_name] = _score_policy(
                sessions,
                base_policy,
                start=str(block["start"]),
                end=str(block["end"]),
                risk=risk,
                costs=cost_profiles[cost_name],
                multiplier=multiplier,
            )

        parent_policies: dict[str, pd.DataFrame] = {}
        parent_scores: dict[
            tuple[str, str], tuple[dict[str, Any], pd.DataFrame, dict[str, Any], dict[str, Any]]
        ] = {}
        for parent_id, parent_config in parent_base_configs.items():
            parent_policy = joint.apply_joint_candidate(
                gate_policies[parent_config.gate_id], parent_config
            )
            parent_policies[parent_id] = _join_wave2_specialists(
                parent_policy, timesfm, kronos
            )
            for cost_name in map(str, wave2["evaluation"]["cost_profiles"]):
                parent_scores[(parent_id, cost_name)] = _score_policy(
                    sessions,
                    parent_policies[parent_id],
                    start=str(block["start"]),
                    end=str(block["end"]),
                    risk=risk,
                    costs=cost_profiles[cost_name],
                    multiplier=multiplier,
                )

        for config in wave2_configs:
            candidate = joint.apply_wave2_specialists(
                parent_policies[config.parent_policy_id], config
            )
            short_modified = int(candidate["wave2_short_modified"].astype(bool).sum())
            long_modified = int(candidate["wave2_long_modified"].astype(bool).sum())
            for cost_name in map(str, wave2["evaluation"]["cost_profiles"]):
                score, candidate_ledger, replay_summary, effective = _score_policy(
                    sessions,
                    candidate,
                    start=str(block["start"]),
                    end=str(block["end"]),
                    risk=risk,
                    costs=cost_profiles[cost_name],
                    multiplier=multiplier,
                )
                parent_score = parent_scores[(config.parent_policy_id, cost_name)][0]
                baseline_score, baseline_ledger, baseline_summary, _ = baselines[cost_name]
                concentration = joint.largest_incremental_month_fraction(
                    candidate_ledger, baseline_ledger
                )
                trials.append(
                    _wave2_trial_row(
                        config=config,
                        cost_profile=cost_name,
                        outer_id=outer_id,
                        score=score,
                        replay_summary=replay_summary,
                        effective=effective,
                        parent_score=parent_score,
                        baseline_score=baseline_score,
                        baseline_summary=baseline_summary,
                        concentration=concentration,
                        short_modified_count=short_modified,
                        long_modified_count=long_modified,
                    )
                )

        outer_diagnostics[outer_id] = {
            "block": dict(block),
            "history_rows": context["history_rows"],
            "max_history_target_end": context["max_history_target_end"],
            "gate_ids": gate_ids,
            "parent_policy_count": len(parent_policies),
            "baseline_scores": {name: value[0] for name, value in baselines.items()},
        }

    expected_trials = int(wave2["candidate_space"]["expected_outer_cost_trial_count"])
    if len(trials) != expected_trials:
        raise RuntimeError(
            f"issue459 wave2 trial accounting changed: expected {expected_trials}, got {len(trials)}"
        )
    trial_frame = pd.DataFrame(trials)
    evaluation = _evaluate_wave2(trial_frame, prereg, wave2)
    passing = [row for row in evaluation if row["passes_wave2_gate"]]
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 459,
        "wave": 2,
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "claim_boundary": wave2["claim_boundary"],
        "declared_policy_count": len(wave2_configs),
        "trial_count": len(trials),
        "evaluated_policy_count": len(evaluation),
        "passing_policy_count": len(passing),
        "top_policies": evaluation,
        "passing_policies": passing,
        "outer_diagnostics": outer_diagnostics,
        "disposition": (
            "FREEZE_WAVE2_DEVELOPMENT_CANDIDATE"
            if passing
            else "CONTINUE_TO_WAVE3_MECHANISM_CLOCK_RECOMBINATION"
        ),
        "preflight_sha256": preflight_report["preflight_sha256"],
        "wave2_prereg_sha256": sha256_file(WAVE2_PREREG),
        "wave1_result_identity": wave2["parent_wave1"]["result_sha256"],
        "runner_sha256": sha256_file(Path(__file__)),
        "joint_code_sha256": sha256_file(REPO / "src/commodity/v2_joint_advantage.py"),
    }
    WAVE2_LEDGER.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in trials),
        encoding="utf-8",
        newline="\n",
    )
    result["trial_ledger_file_sha256"] = sha256_file(WAVE2_LEDGER)
    result["result_sha256"] = stable_sha(
        {key: value for key, value in result.items() if key != "result_sha256"}
    )
    WAVE2_RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--preflight"
    if mode == "--preflight":
        report = preflight(write=True)
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] != "PASS":
            raise SystemExit(1)
        return
    if mode == "--score-wave1":
        result = score_wave1()
        print(
            json.dumps(
                {
                    "disposition": result["disposition"],
                    "trial_count": result["trial_count"],
                    "evaluated_policy_count": result["evaluated_policy_count"],
                    "passing_policy_count": result["passing_policy_count"],
                    "result_sha256": result["result_sha256"],
                    "top_policies": result["top_policies"][:5],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if mode == "--preflight-wave2":
        report = preflight_wave2(write=True)
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] != "PASS":
            raise SystemExit(1)
        return
    if mode == "--score-wave2":
        result = score_wave2()
        print(
            json.dumps(
                {
                    "disposition": result["disposition"],
                    "trial_count": result["trial_count"],
                    "evaluated_policy_count": result["evaluated_policy_count"],
                    "passing_policy_count": result["passing_policy_count"],
                    "result_sha256": result["result_sha256"],
                    "top_policies": result["top_policies"][:5],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    raise SystemExit(f"unsupported issue459 mode: {mode}")


if __name__ == "__main__":
    main()
