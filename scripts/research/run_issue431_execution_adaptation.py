from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts/research"))

import run_issue429_execution_structure as issue429
import run_issue430_sizing_risk as issue430

from commodity import v2_execution_adaptation as execution
from commodity import v2_sizing_risk as sizing

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue431-prereg-v1.json"
PREFLIGHT = PROGRAMME / "issue431-preflight-v1.json"
TRIALS = PROGRAMME / "issue431-trials-v1.jsonl"
RESULT = PROGRAMME / "issue431-result-v1.json"
EXPECTED_PREREG_SHA256 = "befe4de0dff67aad999d2d71c5b480671a16027d25e1d096c0e1a913ed701dfc"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_prereg() -> dict[str, Any]:
    if sha256_file(PREREG) != EXPECTED_PREREG_SHA256:
        raise RuntimeError("issue431 frozen preregistration identity changed")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("evidence_class") != "development_only":
        raise RuntimeError("issue431 evidence class changed")
    if prereg.get("protected_confirmation_start") != "2023-01-01":
        raise RuntimeError("issue431 protected boundary changed")
    if prereg.get("paper_sim_live_access") is not False:
        raise RuntimeError("issue431 protected runtime access flag changed")
    if len(prereg["adaptation_stage"]["variants"]) != 25:
        raise RuntimeError("issue431 adaptation budget changed")
    if int(prereg["trial_budget"]["maximum_total_outer_trials"]) != 190:
        raise RuntimeError("issue431 total trial budget changed")
    return prereg


def _authority_paths() -> dict[str, Path]:
    programme = PROGRAMME
    return {
        "config/v2_variable_registry.json": REPO / "config/v2_variable_registry.json",
        "config/simulation.json": REPO / "config/simulation.json",
        "config/trading-policy.json": REPO / "config/trading-policy.json",
        "config/research_dataset.json": REPO / "config/research_dataset.json",
        "config/phase2_market_only.json": REPO / "config/phase2_market_only.json",
        "issue430-prereg-v1.json": programme / "issue430-prereg-v1.json",
        "issue430-preflight-v1.json": programme / "issue430-preflight-v1.json",
        "issue430-trials-v1.jsonl": programme / "issue430-trials-v1.jsonl",
        "issue430-result-v1.json": programme / "issue430-result-v1.json",
        "issue429-result-v1.json": programme / "issue429-result-v1.json",
        "issue448-downstream-handoff-v1.json": programme / "issue448-downstream-handoff-v1.json",
    }


def _verify_authority(prereg: Mapping[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for key, path in _authority_paths().items():
        digest = sha256_file(path)
        observed[key] = digest
        if digest != str(prereg["authority_sha256"][key]):
            raise RuntimeError(f"issue431 authority identity changed: {key}")
    return observed


def _execution_configs(prereg: Mapping[str, Any]) -> list[dict[str, object]]:
    stage = prereg["execution_stage"]
    profiles = {str(row["id"]): dict(row) for row in stage["cost_profiles"]}
    configs: list[dict[str, object]] = []
    for delay, roll_gap, miss, profile_id in itertools.product(
        stage["delay_sessions"],
        stage["roll_gap_sessions"],
        stage["miss_every_nth_order"],
        profiles,
    ):
        profile = profiles[str(profile_id)]
        config = {
            "delay_sessions": int(delay),
            "roll_gap_sessions": int(roll_gap),
            "miss_every_nth_order": int(miss),
            "cost_profile": str(profile_id),
            "half_spread_ticks_per_side": float(profile["half_spread_ticks_per_side"]),
            "slippage_ticks_per_side": float(profile["slippage_ticks_per_side"]),
        }
        config["id"] = (
            f"d{delay}__roll{roll_gap}__miss{miss}__cost_{profile_id}"
        )
        configs.append(config)
    if len(configs) != int(stage["scored_config_count"]):
        raise RuntimeError("issue431 execution config count changed")
    return configs


def _holding_diagnostics(ledger: pd.DataFrame) -> dict[str, float]:
    positions = pd.to_numeric(ledger["target_position"], errors="raise").astype(float)
    nonzero = positions.ne(0.0)
    runs: list[int] = []
    current = 0
    for active in nonzero.tolist():
        if active:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return {
        "mean_holding_sessions": float(sum(runs) / len(runs)) if runs else 0.0,
        "max_holding_sessions": float(max(runs)) if runs else 0.0,
        "nonzero_position_sessions": float(nonzero.sum()),
    }


def _promoted_sizing_config(
    prereg430: Mapping[str, Any],
    favorable_regimes: tuple[str, ...],
) -> dict[str, object]:
    specs = prereg430["stage1_sizing"]["policy_configs"]
    spec = next(row for row in specs if row["id"] == "regime_favored1_50_other0_75")
    return issue430.materialize_stage1_config(
        dict(spec), favorable_regimes=favorable_regimes, max_abs_contracts=1.5
    )


def _replay_policy(
    *,
    path: pd.DataFrame,
    decisions: pd.DataFrame,
    risk: object,
    base_costs: object,
    execution_config: Mapping[str, object],
    multiplier: float,
    max_abs_contracts: float,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, object], dict[str, int]]:
    expanded, transform = execution.expand_execution_decisions(
        path,
        decisions,
        delay_sessions=int(execution_config["delay_sessions"]),
        roll_gap_sessions=int(execution_config["roll_gap_sessions"]),
        miss_every_nth_order=int(execution_config["miss_every_nth_order"]),
    )
    costs = execution.build_cost_assumptions(
        base_costs,
        half_spread_ticks_per_side=float(execution_config["half_spread_ticks_per_side"]),
        slippage_ticks_per_side=float(execution_config["slippage_ticks_per_side"]),
    )
    ledger, replay = execution.replay_expanded_execution_policy(
        path, expanded, risk, costs,
        contract_multiplier=multiplier, max_abs_contracts=max_abs_contracts,
    )
    score = issue430._score_ledger(ledger, float(risk.capital_usd))
    score.update(_holding_diagnostics(ledger))
    return score, ledger, replay, transform


def preflight() -> dict[str, object]:
    prereg = load_prereg()
    authority = _verify_authority(prereg)
    context = issue430._load_stage1_context()
    paths: dict[str, dict[str, object]] = {}
    for outer in prereg["development_outers"]:
        outer_id = str(outer["id"])
        _block, _parent, _regimes, path = issue430._build_stage1_outer_context(
            outer_id, context
        )
        required = {"trade_date", "session_open", "contract_id", "open_price", "roll_reason"}
        missing = sorted(required - set(path.columns))
        if missing:
            raise RuntimeError(f"issue431 executable path is missing columns: {missing}")
        settlement_supported = bool({"settlement_price", "close_price"} & set(path.columns))
        if settlement_supported:
            raise RuntimeError("issue431 preregistered settlement source hold is no longer true")
        paths[outer_id] = {
            "rows": len(path),
            "minimum_trade_date": str(pd.Timestamp(path["trade_date"].min())),
            "maximum_trade_date": str(pd.Timestamp(path["trade_date"].max())),
            "settlement_or_close_supported": False,
            "roll_transitions": int(path["contract_id"].astype(str).ne(path["contract_id"].shift()).sum() - 1),
        }
    configs = _execution_configs(prereg)
    variants = [dict(row) for row in prereg["adaptation_stage"]["variants"]]
    adaptation_count = len(variants)
    minimum_training_rows = int(context["cfg"]["execution_contract"]["minimum_training_rows"])
    infeasible_adaptation = []
    for variant in variants:
        feasible, reason = execution.adaptation_variant_feasibility(
            variant, minimum_training_rows=minimum_training_rows
        )
        if not feasible:
            infeasible_adaptation.append(
                {"variant_id": str(variant["id"]), "reason": str(reason)}
            )
    report: dict[str, object] = {
        "issue": 431,
        "status": "PASS_NO_SCORING",
        "evidence_class": "development_only",
        "prereg_sha256": sha256_file(PREREG),
        "runner_sha256": sha256_file(Path(__file__)),
        "authority_sha256": authority,
        "execution_config_count": len(configs),
        "execution_outer_trial_count": len(configs) * len(prereg["development_outers"]),
        "adaptation_variant_count": adaptation_count,
        "adaptation_outer_trial_count": adaptation_count * len(prereg["development_outers"]),
        "adaptation_minimum_training_rows": minimum_training_rows,
        "infeasible_adaptation_variants": infeasible_adaptation,
        "maximum_conditional_outer_trials": int(
            prereg["conditional_cross_execution_stage"]["maximum_outer_trial_count"]
        ),
        "maximum_total_outer_trials": int(prereg["trial_budget"]["maximum_total_outer_trials"]),
        "event_time_trials": 0,
        "event_time_status": prereg["event_time_lane"]["status"],
        "protected_confirmation_accessed": False,
        "paper_sim_live_accessed": False,
        "paths": paths,
    }
    _write_json(PREFLIGHT, report)
    return report


def _require_preflight() -> dict[str, Any]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue431 scoring requires a passing no-scoring preflight")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS_NO_SCORING":
        raise RuntimeError("issue431 preflight is not passing")
    if report.get("prereg_sha256") != EXPECTED_PREREG_SHA256:
        raise RuntimeError("issue431 preflight is bound to a different preregistration")
    if report.get("runner_sha256") != sha256_file(Path(__file__)):
        raise RuntimeError("issue431 preflight is stale for the current runner")
    current_authority = _verify_authority(load_prereg())
    if report.get("authority_sha256") != current_authority:
        raise RuntimeError("issue431 preflight authority binding is stale")
    if report.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue431 preflight protected boundary changed")
    if report.get("paper_sim_live_accessed") is not False:
        raise RuntimeError("issue431 preflight runtime boundary changed")
    return report


def _execution_trial_row(
    *,
    outer_id: str,
    config: Mapping[str, object],
    fixed: tuple[dict[str, Any], pd.DataFrame, dict[str, object], dict[str, int]],
    sized: tuple[dict[str, Any], pd.DataFrame, dict[str, object], dict[str, int]],
) -> dict[str, object]:
    fixed_score, _fixed_ledger, fixed_replay, fixed_transform = fixed
    sized_score, _sized_ledger, sized_replay, sized_transform = sized
    return {
        "issue": 431,
        "stage": "execution",
        "status": "complete",
        "evidence_class": "development",
        "outer_id": outer_id,
        "config_id": str(config["id"]),
        "config": dict(config),
        "fixed_parent_mean_monthly_net_return": float(fixed_score["mean_monthly_net_return"]),
        "sized_mean_monthly_net_return": float(sized_score["mean_monthly_net_return"]),
        "sizing_delta_mean_monthly_net_return": float(sized_score["mean_monthly_net_return"]) - float(fixed_score["mean_monthly_net_return"]),
        "fixed_score": fixed_score,
        "sized_score": sized_score,
        "fixed_replay": fixed_replay,
        "sized_replay": sized_replay,
        "fixed_transform": fixed_transform,
        "sized_transform": sized_transform,
        "protected_confirmation_accessed": False,
    }


def score_execution_stage(
    prereg: Mapping[str, Any], context: Mapping[str, object]
) -> list[dict[str, object]]:
    prereg430 = issue430.load_prereg()
    configs = _execution_configs(prereg)
    risk = context["risk"]
    base_costs = context["cost_profiles"]["base"]
    multiplier = float(context["cfg"]["execution_contract"]["contract_multiplier_mmbtu"])
    rows: list[dict[str, object]] = []
    for outer in prereg["development_outers"]:
        outer_id = str(outer["id"])
        _block, parent, favorable_regimes, path = issue430._build_stage1_outer_context(
            outer_id, dict(context)
        )
        sizing_config = _promoted_sizing_config(prereg430, favorable_regimes)
        sized = sizing.apply_sizing_policy(parent, sizing_config)
        for config in configs:
            fixed_result = _replay_policy(
                path=path, decisions=parent, risk=risk, base_costs=base_costs,
                execution_config=config, multiplier=multiplier, max_abs_contracts=1.0,
            )
            sized_result = _replay_policy(
                path=path, decisions=sized, risk=risk, base_costs=base_costs,
                execution_config=config, multiplier=multiplier, max_abs_contracts=1.5,
            )
            rows.append(
                _execution_trial_row(
                    outer_id=outer_id, config=config,
                    fixed=fixed_result, sized=sized_result,
                )
            )
    expected = int(prereg["trial_budget"]["execution_outer_trials"])
    if len(rows) != expected:
        raise RuntimeError(f"issue431 execution trial count changed: {len(rows)} != {expected}")
    return rows


def _adaptive_opportunities(
    *,
    outer_id: str,
    variant: Mapping[str, object],
    context: Mapping[str, object],
    round_trip_usd: float,
) -> tuple[pd.DataFrame, dict[str, int]]:
    issue428 = issue429.issue428
    signal_columns = issue428._signal_columns_for_outer(
        outer_id, context["selected_reps"]
    )
    selected_config = context["selected_models"][outer_id]
    matched_config = context["matched_controls"][outer_id]["config"]
    multiplier = float(context["cfg"]["execution_contract"]["contract_multiplier_mmbtu"])
    minimum_training_rows = int(context["cfg"]["execution_contract"]["minimum_training_rows"])
    origins, control_columns = issue428._prepare_outer_origins(
        context["features"], context["sessions"], selected_config, signal_columns,
        round_trip_per_mmbtu=round_trip_usd / multiplier,
    )
    block = issue428._outer_blocks(context["cfg"])[outer_id]
    outer_start_year = int(str(block["start"])[:4])
    windows = [(f"{year}-01-01", f"{year}-12-31") for year in range(2017, outer_start_year)]
    windows.append((str(block["start"]), str(block["end"])))
    frames: list[pd.DataFrame] = []
    diagnostics = {"selected_refits": 0, "matched_refits": 0}
    for start, end in windows:
        kwargs = {
            "start_timestamp": pd.Timestamp(start, tz="UTC"),
            "boundary_timestamp": pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1),
            "contract_multiplier": multiplier,
            "round_trip_usd": round_trip_usd,
            "minimum_training_rows": minimum_training_rows,
            "refit_mode": str(variant["refit_mode"]),
            "retrain_every_sessions": int(variant["retrain_every_sessions"]),
            "rolling_train_sessions": variant["rolling_train_sessions"],
            "decay_half_life_sessions": variant["decay_half_life_sessions"],
            "recalibration_cadence_sessions": variant["recalibration_cadence_sessions"],
            "drift_trigger": str(variant["drift_trigger"]),
        }
        selected, selected_diag = execution.adaptive_forecast_window(
            origins, control_columns, selected_config, **kwargs
        )
        matched, matched_diag = execution.adaptive_forecast_window(
            origins, control_columns, matched_config, **kwargs
        )
        diagnostics["selected_refits"] += int(selected_diag["refit_count"])
        diagnostics["matched_refits"] += int(matched_diag["refit_count"])
        frames.append(
            issue428._opportunity_frame(
                origins, selected, matched, signal_columns,
                round_trip_usd=round_trip_usd, multiplier=multiplier,
            )
        )
    combined = pd.concat(frames, ignore_index=True).sort_values("fill_timestamp", kind="stable")
    if combined["fill_timestamp"].duplicated().any():
        raise RuntimeError("issue431 adaptive opportunity windows overlap")
    return combined.reset_index(drop=True), diagnostics


def _adapted_policy(
    *,
    outer_id: str,
    variant: Mapping[str, object],
    context: Mapping[str, object],
    round_trip_usd: float,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...], dict[str, int]]:
    opportunities, refit_diag = _adaptive_opportunities(
        outer_id=outer_id, variant=variant, context=context, round_trip_usd=round_trip_usd
    )
    block = issue429.issue428._outer_blocks(context["cfg"])[outer_id]
    start = pd.Timestamp(str(block["start"]), tz="UTC")
    end = pd.Timestamp(str(block["end"]), tz="UTC")
    history = issue429.dec.completed_history_before(opportunities, start)
    dates = pd.to_datetime(opportunities["fill_trade_date"], utc=True, errors="raise")
    outer = opportunities.loc[(dates >= start) & (dates <= end)].copy()
    signal_columns = issue429.issue428._signal_columns_for_outer(
        outer_id, context["selected_reps"]
    )
    issue428 = issue429.issue428
    if history.empty or outer.empty:
        raise RuntimeError(f"issue431 adaptive context is empty: {outer_id}")
    state, _annotated_history, annotated_outer = issue428._annotated_context(
        history,
        outer,
        signal_columns,
        context["issue428_prereg"],
        outcome_available_before=start,
    )
    configs = issue428._config_map(context["issue428_prereg"])
    strength_gate = issue428._score_policy(
        annotated_outer,
        configs["strength-q50"],
        state,
        {},
        signal_columns,
    )
    wave1 = issue429.joint.apply_joint_candidate(strength_gate, context["parent_wave1"])
    joined = issue429.issue459._join_wave2_specialists(
        wave1, context["timesfm"], context["kronos"]
    )
    promoted = issue429.joint.apply_wave2_specialists(joined, context["parent_wave2"])
    path, _start, _boundary = issue428._path_window(
        context["sessions"], start_date=str(block["start"]), end_date=str(block["end"])
    )
    return promoted, path, tuple(state.favorable_regimes), refit_diag


def _adaptation_complexity(variant: Mapping[str, object]) -> int:
    mode = str(variant["refit_mode"])
    rank = {"fixed": 0, "expanding": 1, "rolling": 2}[mode]
    if variant.get("decay_half_life_sessions") is not None:
        rank += 1
    if variant.get("recalibration_cadence_sessions") is not None:
        rank += 1
    if str(variant.get("drift_trigger", "off")) != "off":
        rank += 1
    return rank


def _execution_config_by_id(
    prereg: Mapping[str, Any], config_id: str
) -> dict[str, object]:
    matches = [row for row in _execution_configs(prereg) if row["id"] == config_id]
    if len(matches) != 1:
        raise RuntimeError(f"issue431 execution config unavailable: {config_id}")
    return matches[0]


def _common_execution_config(prereg: Mapping[str, Any]) -> dict[str, object]:
    reference = prereg["execution_stage"]["common_reference"]
    wanted = (
        f"d{reference['delay_sessions']}__roll{reference['roll_gap_sessions']}"
        f"__miss{reference['miss_every_nth_order']}__cost_{reference['cost_profile']}"
    )
    return _execution_config_by_id(prereg, wanted)


def _score_adaptation_policy(
    *,
    prereg: Mapping[str, Any],
    context: Mapping[str, object],
    outer_id: str,
    variant: Mapping[str, object],
) -> dict[str, object]:
    base_costs = context["cost_profiles"]["base"]
    round_trip_usd = float(base_costs.round_trip_usd)
    policy, path, favorable_regimes, refit_diag = _adapted_policy(
        outer_id=outer_id,
        variant=variant,
        context=context,
        round_trip_usd=round_trip_usd,
    )
    sizing_config = _promoted_sizing_config(issue430.load_prereg(), favorable_regimes)
    sized = sizing.apply_sizing_policy(policy, sizing_config)
    execution_config = _common_execution_config(prereg)
    multiplier = float(context["cfg"]["execution_contract"]["contract_multiplier_mmbtu"])
    score, _ledger, replay, transform = _replay_policy(
        path=path,
        decisions=sized,
        risk=context["risk"],
        base_costs=base_costs,
        execution_config=execution_config,
        multiplier=multiplier,
        max_abs_contracts=1.5,
    )
    return {
        "issue": 431,
        "stage": "adaptation",
        "status": "complete",
        "evidence_class": "development",
        "outer_id": outer_id,
        "variant_id": str(variant["id"]),
        "variant": dict(variant),
        "declared_complexity": _adaptation_complexity(variant),
        "score": score,
        "replay": replay,
        "execution_transform": transform,
        "adaptation_diagnostics": refit_diag,
        "mean_monthly_net_return": float(score["mean_monthly_net_return"]),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"]),
        "kill_triggered": bool(replay.get("kill_triggered", False)),
        "total_refits": int(refit_diag["selected_refits"]) + int(refit_diag["matched_refits"]),
        "protected_confirmation_accessed": False,
    }


def score_adaptation_stage(
    prereg: Mapping[str, Any], context: Mapping[str, object]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    variants = [dict(row) for row in prereg["adaptation_stage"]["variants"]]
    minimum_training_rows = int(context["cfg"]["execution_contract"]["minimum_training_rows"])
    for outer in prereg["development_outers"]:
        outer_id = str(outer["id"])
        for variant in variants:
            feasible, reason = execution.adaptation_variant_feasibility(
                variant, minimum_training_rows=minimum_training_rows
            )
            if not feasible:
                rows.append(
                    {
                        "issue": 431,
                        "stage": "adaptation",
                        "status": "infeasible",
                        "evidence_class": "development",
                        "outer_id": outer_id,
                        "variant_id": str(variant["id"]),
                        "variant": dict(variant),
                        "declared_complexity": _adaptation_complexity(variant),
                        "failure_reason": str(reason),
                        "total_refits": 0,
                        "protected_confirmation_accessed": False,
                    }
                )
                continue
            rows.append(
                _score_adaptation_policy(
                    prereg=prereg,
                    context=context,
                    outer_id=outer_id,
                    variant=variant,
                )
            )
    expected = int(prereg["trial_budget"]["adaptation_outer_trials"])
    if len(rows) != expected:
        raise RuntimeError(
            f"issue431 adaptation trial count changed: {len(rows)} != {expected}"
        )
    reference_id = str(prereg["adaptation_stage"]["reference_variant_id"])
    reference = {
        str(row["outer_id"]): row
        for row in rows
        if str(row["variant_id"]) == reference_id and row["status"] == "complete"
    }
    if len(reference) != len(prereg["development_outers"]):
        raise RuntimeError("issue431 fixed adaptation reference is incomplete")
    for row in rows:
        if row["status"] != "complete":
            row["mean_monthly_net_return_delta_vs_fixed"] = None
            row["max_drawdown_regression_vs_fixed"] = None
            row["kill_trigger_regression_vs_fixed"] = None
            continue
        ref = reference[str(row["outer_id"])]
        row["mean_monthly_net_return_delta_vs_fixed"] = (
            float(row["mean_monthly_net_return"])
            - float(ref["mean_monthly_net_return"])
        )
        row["max_drawdown_regression_vs_fixed"] = (
            float(row["max_drawdown_fraction"])
            - float(ref["max_drawdown_fraction"])
        )
        row["kill_trigger_regression_vs_fixed"] = bool(row["kill_triggered"]) and not bool(
            ref["kill_triggered"]
        )
    return rows


def evaluate_adaptation(
    rows: list[dict[str, object]], prereg: Mapping[str, Any]
) -> list[dict[str, object]]:
    frame = pd.DataFrame(rows)
    gates = prereg["adaptation_stage"]["promotion_gates"]
    evaluations: list[dict[str, object]] = []
    for variant_id, group in frame.groupby("variant_id", sort=True):
        complete = group.loc[group["status"].astype(str).eq("complete")].copy()
        failure_reasons = sorted(
            {str(value) for value in group["failure_reason"].dropna().tolist()}
        )
        if len(complete) != len(group):
            evaluations.append(
                {
                    "variant_id": str(variant_id),
                    "status": "infeasible",
                    "failure_reasons": failure_reasons,
                    "mean_outer_monthly_net_return_delta": None,
                    "nonnegative_outer_fraction": 0.0,
                    "maximum_drawdown_regression_fraction": None,
                    "kill_trigger_regression": None,
                    "total_refits": int(group["total_refits"].sum()),
                    "declared_complexity": int(group["declared_complexity"].iloc[0]),
                    "outer_deltas": {str(row.outer_id): None for row in group.itertuples(index=False)},
                    "passes_promotion_gate": False,
                }
            )
            continue
        deltas = pd.to_numeric(
            complete["mean_monthly_net_return_delta_vs_fixed"], errors="raise"
        )
        drawdown = pd.to_numeric(
            complete["max_drawdown_regression_vs_fixed"], errors="raise"
        )
        mean_delta = float(deltas.mean())
        nonnegative = float(deltas.ge(0.0).mean())
        max_drawdown_regression = float(drawdown.max())
        kill_regression = bool(
            complete["kill_trigger_regression_vs_fixed"].astype(bool).any()
        )
        passes = bool(
            mean_delta >= float(gates["minimum_mean_outer_monthly_net_return_delta"])
            and nonnegative >= float(gates["minimum_nonnegative_outer_fraction"])
            and max_drawdown_regression <= float(gates["maximum_drawdown_regression_fraction"])
            and not kill_regression
        )
        evaluations.append(
            {
                "variant_id": str(variant_id),
                "status": "complete",
                "failure_reasons": [],
                "mean_outer_monthly_net_return_delta": mean_delta,
                "nonnegative_outer_fraction": nonnegative,
                "maximum_drawdown_regression_fraction": max_drawdown_regression,
                "kill_trigger_regression": kill_regression,
                "total_refits": int(complete["total_refits"].sum()),
                "declared_complexity": int(complete["declared_complexity"].iloc[0]),
                "outer_deltas": {
                    str(row.outer_id): float(row.mean_monthly_net_return_delta_vs_fixed)
                    for row in complete.itertuples(index=False)
                },
                "passes_promotion_gate": passes,
            }
        )
    return sorted(
        evaluations,
        key=lambda row: (
            not bool(row["passes_promotion_gate"]),
            float("inf")
            if row["mean_outer_monthly_net_return_delta"] is None
            else -float(row["mean_outer_monthly_net_return_delta"]),
            int(row["total_refits"]),
            int(row["declared_complexity"]),
            str(row["variant_id"]),
        ),
    )


def evaluate_execution(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    frame = pd.DataFrame(rows)
    evaluations: list[dict[str, object]] = []
    for config_id, group in frame.groupby("config_id", sort=True):
        deltas = pd.to_numeric(group["sizing_delta_mean_monthly_net_return"], errors="raise")
        evaluations.append(
            {
                "config_id": str(config_id),
                "mean_outer_sizing_delta": float(deltas.mean()),
                "minimum_outer_sizing_delta": float(deltas.min()),
                "nonnegative_outer_fraction": float(deltas.ge(0.0).mean()),
                "outer_deltas": {
                    str(row.outer_id): float(row.sizing_delta_mean_monthly_net_return)
                    for row in group.itertuples(index=False)
                },
            }
        )
    return sorted(
        evaluations,
        key=lambda row: (
            -float(row["mean_outer_sizing_delta"]),
            str(row["config_id"]),
        ),
    )


def _cross_execution_configs(prereg: Mapping[str, Any]) -> list[dict[str, object]]:
    stage = prereg["conditional_cross_execution_stage"]
    profiles = {
        str(row["id"]): dict(row)
        for row in prereg["execution_stage"]["cost_profiles"]
    }
    rows: list[dict[str, object]] = []
    for delay, roll_gap, miss, profile_id in itertools.product(
        stage["delay_sessions"], stage["roll_gap_sessions"],
        stage["miss_every_nth_order"], stage["cost_profiles"],
    ):
        profile = profiles[str(profile_id)]
        row = {
            "delay_sessions": int(delay),
            "roll_gap_sessions": int(roll_gap),
            "miss_every_nth_order": int(miss),
            "cost_profile": str(profile_id),
            "half_spread_ticks_per_side": float(profile["half_spread_ticks_per_side"]),
            "slippage_ticks_per_side": float(profile["slippage_ticks_per_side"]),
        }
        row["id"] = f"d{delay}__roll{roll_gap}__miss{miss}__cost_{profile_id}"
        rows.append(row)
    if len(rows) != int(stage["config_count"]):
        raise RuntimeError("issue431 cross-execution config count changed")
    return rows


def _sized_adapted_policy(
    *,
    outer_id: str,
    variant: Mapping[str, object],
    context: Mapping[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    base_costs = context["cost_profiles"]["base"]
    policy, path, favorable_regimes, refit_diag = _adapted_policy(
        outer_id=outer_id,
        variant=variant,
        context=context,
        round_trip_usd=float(base_costs.round_trip_usd),
    )
    sizing_config = _promoted_sizing_config(issue430.load_prereg(), favorable_regimes)
    return sizing.apply_sizing_policy(policy, sizing_config), path, refit_diag


def score_cross_execution_stage(
    *,
    prereg: Mapping[str, Any],
    context: Mapping[str, object],
    selected_variant_id: str,
) -> list[dict[str, object]]:
    variants = {
        str(row["id"]): dict(row)
        for row in prereg["adaptation_stage"]["variants"]
    }
    if selected_variant_id not in variants:
        raise RuntimeError("issue431 selected adaptation variant is unavailable")
    fixed_id = str(prereg["adaptation_stage"]["reference_variant_id"])
    configs = _cross_execution_configs(prereg)
    base_costs = context["cost_profiles"]["base"]
    multiplier = float(context["cfg"]["execution_contract"]["contract_multiplier_mmbtu"])
    rows: list[dict[str, object]] = []
    for outer in prereg["development_outers"]:
        outer_id = str(outer["id"])
        selected, selected_path, selected_diag = _sized_adapted_policy(
            outer_id=outer_id, variant=variants[selected_variant_id], context=context
        )
        fixed, fixed_path, fixed_diag = _sized_adapted_policy(
            outer_id=outer_id, variant=variants[fixed_id], context=context
        )
        if len(selected_path) != len(fixed_path):
            raise RuntimeError("issue431 cross-execution path identity changed")
        for config in configs:
            fixed_result = _replay_policy(
                path=fixed_path,
                decisions=fixed,
                risk=context["risk"],
                base_costs=base_costs,
                execution_config=config,
                multiplier=multiplier,
                max_abs_contracts=1.5,
            )
            selected_result = _replay_policy(
                path=selected_path,
                decisions=selected,
                risk=context["risk"],
                base_costs=base_costs,
                execution_config=config,
                multiplier=multiplier,
                max_abs_contracts=1.5,
            )
            fixed_score, _fixed_ledger, fixed_replay, _fixed_transform = fixed_result
            selected_score, _selected_ledger, selected_replay, selected_transform = selected_result
            rows.append(
                {
                    "issue": 431,
                    "stage": "conditional_cross_execution",
                    "status": "complete",
                    "evidence_class": "development",
                    "outer_id": outer_id,
                    "variant_id": selected_variant_id,
                    "config_id": str(config["id"]),
                    "config": dict(config),
                    "fixed_mean_monthly_net_return": float(
                        fixed_score["mean_monthly_net_return"]
                    ),
                    "selected_mean_monthly_net_return": float(
                        selected_score["mean_monthly_net_return"]
                    ),
                    "mean_monthly_net_return_delta_vs_fixed": float(
                        selected_score["mean_monthly_net_return"]
                    )
                    - float(fixed_score["mean_monthly_net_return"]),
                    "fixed_score": fixed_score,
                    "selected_score": selected_score,
                    "fixed_replay": fixed_replay,
                    "selected_replay": selected_replay,
                    "selected_transform": selected_transform,
                    "selected_refits": int(selected_diag["selected_refits"])
                    + int(selected_diag["matched_refits"]),
                    "fixed_refits": int(fixed_diag["selected_refits"])
                    + int(fixed_diag["matched_refits"]),
                    "protected_confirmation_accessed": False,
                }
            )
    maximum = int(
        prereg["trial_budget"]["maximum_conditional_cross_execution_outer_trials"]
    )
    if len(rows) != maximum:
        raise RuntimeError(f"issue431 cross trial count changed: {len(rows)} != {maximum}")
    return rows


def evaluate_cross_execution(
    rows: list[dict[str, object]], prereg: Mapping[str, Any]
) -> list[dict[str, object]]:
    frame = pd.DataFrame(rows)
    evaluations: list[dict[str, object]] = []
    require_nonnegative = bool(
        prereg["conditional_cross_execution_stage"]["required_mean_outer_delta_nonnegative"]
    )
    for config_id, group in frame.groupby("config_id", sort=True):
        deltas = pd.to_numeric(
            group["mean_monthly_net_return_delta_vs_fixed"], errors="raise"
        )
        mean_delta = float(deltas.mean())
        nonnegative_fraction = float(deltas.ge(0.0).mean())
        evaluations.append(
            {
                "config_id": str(config_id),
                "mean_outer_monthly_net_return_delta": mean_delta,
                "nonnegative_outer_fraction": nonnegative_fraction,
                "passes_cross_execution_gate": bool(
                    (not require_nonnegative) or mean_delta >= 0.0
                ),
                "outer_deltas": {
                    str(row.outer_id): float(row.mean_monthly_net_return_delta_vs_fixed)
                    for row in group.itertuples(index=False)
                },
            }
        )
    return sorted(
        evaluations,
        key=lambda row: (
            not bool(row["passes_cross_execution_gate"]),
            -float(row["mean_outer_monthly_net_return_delta"]),
            str(row["config_id"]),
        ),
    )


def _verify_issue430_reproduction(
    execution_rows: list[dict[str, object]], prereg: Mapping[str, Any]
) -> dict[str, object]:
    reference_id = "d0__roll0__miss0__cost_inherited_base"
    observed = {
        str(row["outer_id"]): float(row["sizing_delta_mean_monthly_net_return"])
        for row in execution_rows
        if str(row["config_id"]) == reference_id
    }
    parent_result = json.loads(
        (PROGRAMME / "issue430-result-v1.json").read_text(encoding="utf-8")
    )
    passing = [
        row
        for row in parent_result["stage1_passing_policies"]
        if row["policy_id"] == prereg["scientific_parent"]["sizing_policy_id"]
    ]
    if len(passing) != 1:
        raise RuntimeError("issue431 promoted #430 parent is unavailable")
    expected = {str(k): float(v) for k, v in passing[0]["outer_base_deltas"].items()}
    differences = {
        outer_id: observed[outer_id] - expected[outer_id]
        for outer_id in expected
    }
    reproduced = set(observed) == set(expected) and all(
        abs(value) <= 1e-12 for value in differences.values()
    )
    if not reproduced:
        raise RuntimeError(f"issue431 failed #430 parent reproduction: {differences}")
    return {"reproduced": True, "observed": observed, "expected": expected}


def _write_trials(rows: list[dict[str, object]]) -> None:
    TRIALS.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def score_issue431() -> dict[str, object]:
    preflight_report = _require_preflight()
    prereg = load_prereg()
    context = issue430._load_stage1_context()
    execution_rows = score_execution_stage(prereg, context)
    reproduction = _verify_issue430_reproduction(execution_rows, prereg)
    execution_evaluation = evaluate_execution(execution_rows)
    adaptation_rows = score_adaptation_stage(prereg, context)
    adaptation_evaluation = evaluate_adaptation(adaptation_rows, prereg)
    passing_adaptation = [
        row for row in adaptation_evaluation if bool(row["passes_promotion_gate"])
    ]
    selected_adaptation = passing_adaptation[0] if passing_adaptation else None
    cross_rows: list[dict[str, object]] = []
    cross_evaluation: list[dict[str, object]] = []
    if selected_adaptation is not None:
        cross_rows = score_cross_execution_stage(
            prereg=prereg,
            context=context,
            selected_variant_id=str(selected_adaptation["variant_id"]),
        )
        cross_evaluation = evaluate_cross_execution(cross_rows, prereg)
    all_rows = [*execution_rows, *adaptation_rows, *cross_rows]
    maximum = int(prereg["trial_budget"]["maximum_total_outer_trials"])
    if len(all_rows) > maximum:
        raise RuntimeError(f"issue431 exceeded frozen trial budget: {len(all_rows)} > {maximum}")
    expected_without_cross = (
        int(prereg["trial_budget"]["execution_outer_trials"])
        + int(prereg["trial_budget"]["adaptation_outer_trials"])
    )
    expected = expected_without_cross + (
        int(prereg["trial_budget"]["maximum_conditional_cross_execution_outer_trials"])
        if selected_adaptation is not None
        else 0
    )
    if len(all_rows) != expected:
        raise RuntimeError(f"issue431 trial accounting changed: {len(all_rows)} != {expected}")
    _write_trials(all_rows)
    sizing_survival = [
        row
        for row in execution_evaluation
        if float(row["nonnegative_outer_fraction"]) >= 1.0
    ]
    cross_robust = bool(cross_evaluation) and all(
        bool(row["passes_cross_execution_gate"]) for row in cross_evaluation
    )
    if selected_adaptation is None:
        disposition = "FREEZE_EXECUTION_SURVIVAL_NO_ADAPTATION_PROMOTION"
    elif cross_robust:
        disposition = "FREEZE_ADAPTATION_EXECUTION_ROBUST_DEVELOPMENT_CANDIDATE"
    else:
        disposition = "HOLD_ADAPTATION_CROSS_EXECUTION_NOT_ROBUST"
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 431,
        "evidence_class": "development_only",
        "disposition": disposition,
        "protected_confirmation_accessed": False,
        "paper_sim_live_accessed": False,
        "event_time_trials": 0,
        "event_time_status": prereg["event_time_lane"]["status"],
        "trial_count": len(all_rows),
        "execution_trial_count": len(execution_rows),
        "adaptation_trial_count": len(adaptation_rows),
        "conditional_cross_execution_trial_count": len(cross_rows),
        "issue430_parent_reproduction": reproduction,
        "execution_evaluation": execution_evaluation,
        "execution_full_outer_survival_config_count": len(sizing_survival),
        "execution_config_count": len(execution_evaluation),
        "adaptation_evaluation": adaptation_evaluation,
        "adaptation_passing_variant_count": len(passing_adaptation),
        "selected_adaptation": selected_adaptation,
        "cross_execution_evaluation": cross_evaluation,
        "cross_execution_robust": cross_robust,
        "prereg_sha256": sha256_file(PREREG),
        "preflight_sha256": stable_sha(preflight_report),
        "runner_sha256": sha256_file(Path(__file__)),
        "execution_code_sha256": sha256_file(REPO / "src/commodity/v2_execution_adaptation.py"),
        "trial_ledger_file_sha256": sha256_file(TRIALS),
    }
    result["result_sha256"] = stable_sha(result)
    _write_json(RESULT, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    payload = preflight() if args.preflight else score_issue431()
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
