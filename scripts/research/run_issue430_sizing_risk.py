from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts/research"))

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue430-prereg-v1.json"
PREFLIGHT = PROGRAMME / "issue430-preflight-v1.json"
LEDGER = PROGRAMME / "issue430-trials-v1.jsonl"
RESULT = PROGRAMME / "issue430-result-v1.json"
EXPECTED_PREREG_SHA256 = "d1009575138536bd7a960ba0ac3cd993d8b33b1095cd3736bdd47bfade6ab016"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prereg() -> dict[str, Any]:
    if sha256_file(PREREG) != EXPECTED_PREREG_SHA256:
        raise RuntimeError("issue430 frozen preregistration identity changed")
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen_before_issue430_scoring":
        raise RuntimeError("issue430 preregistration is not frozen")
    if payload.get("evidence_class") != "development":
        raise RuntimeError("issue430 must use development evidence")
    boundary = payload.get("evidence_boundary", {})
    if boundary.get("latest_allowed_trade_date") != "2022-12-31":
        raise RuntimeError("issue430 development cutoff changed")
    if boundary.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue430 protected evidence flag changed")
    stage1 = payload["stage1_sizing"]["policy_configs"]
    stage2 = payload["stage2_risk"]["risk_variants"]
    accounting = payload["trial_accounting"]
    if len(stage1) != int(accounting["declared_stage1_policy_count"]):
        raise RuntimeError("issue430 stage1 budget changed")
    if len(stage2) != int(accounting["declared_stage2_risk_variant_count"]):
        raise RuntimeError("issue430 stage2 budget changed")
    return payload

import pandas as pd
import run_issue429_execution_structure as issue429

from commodity import v2_joint_advantage as joint
from commodity import v2_optimization as v2
from commodity import v2_sizing_risk as sizing
from commodity.market_only_phase2 import _load_inherited_risk_and_costs

PHASE2 = REPO / "config/phase2_market_only.json"
ISSUE429_PREREG = PROGRAMME / "issue429-prereg-v1.json"
ISSUE429_PREFLIGHT = PROGRAMME / "issue429-preflight-v1.json"
ISSUE429_LEDGER = PROGRAMME / "issue429-trials-v1.jsonl"
ISSUE429_RESULT = PROGRAMME / "issue429-result-v1.json"


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _parent_file_failures(prereg: dict[str, Any]) -> list[str]:
    parent = prereg["parent"]
    bindings = (
        (ISSUE429_PREREG, "issue429_prereg_sha256"),
        (ISSUE429_PREFLIGHT, "issue429_preflight_sha256"),
        (ISSUE429_LEDGER, "issue429_trial_ledger_sha256"),
        (ISSUE429_RESULT, "issue429_result_file_sha256"),
    )
    failures: list[str] = []
    for path, key in bindings:
        observed = sha256_file(path)
        if observed != str(parent[key]):
            failures.append(f"parent_identity_changed:{path.name}:{observed}")
    return failures


def preflight(*, write: bool = True) -> dict[str, object]:
    prereg = load_prereg()
    failures = _parent_file_failures(prereg)
    parent_report = issue429.preflight(write=False)
    if parent_report.get("status") != "PASS":
        failures.append("issue429_parent_preflight_not_pass")
    if parent_report.get("protected_confirmation_accessed") is not False:
        failures.append("issue429_parent_protected_boundary_changed")

    issue428_prereg, features, sessions, _families, _support = issue429.issue428._load_inputs()
    _ = issue428_prereg
    parent_result = json.loads(ISSUE429_RESULT.read_text(encoding="utf-8"))
    parent_reproduction = parent_result.get("parent_reproduction", {})
    parent_reproduction_pass = bool(parent_reproduction) and all(
        bool(value.get("reproduced")) for value in parent_reproduction.values()
    )
    if not parent_reproduction_pass:
        failures.append("issue429_parent_reproduction_not_pass")
    stage1_trials = (
        len(prereg["stage1_sizing"]["policy_configs"])
        * len(prereg["outer_blocks"])
        * len(prereg["cost_profiles"])
    )
    declared_stage1 = int(prereg["trial_accounting"]["declared_stage1_outer_cost_trials"])
    if stage1_trials != declared_stage1:
        failures.append(f"stage1_trial_budget_changed:{stage1_trials}!={declared_stage1}")

    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, costs = _load_inherited_risk_and_costs(cfg)
    fixed = prereg["fixed_operational_safety"]
    research = prereg["research_boundary"]
    if int(risk.max_contracts) != int(fixed["paper_max_standard_contracts"]):
        failures.append("paper_contract_cap_changed")
    if abs(float(risk.daily_loss_fraction) - float(fixed["daily_loss_fraction"])) > 1e-12:
        failures.append("paper_daily_loss_changed")
    if abs(float(risk.peak_drawdown_kill_fraction) - float(fixed["peak_drawdown_kill_fraction"])) > 1e-12:
        failures.append("paper_drawdown_kill_changed")
    if abs(float(costs["base"].initial_margin_usd_per_contract) - float(research["initial_margin_usd_per_contract"])) > 1e-12:
        failures.append("margin_assumption_changed")
    report: dict[str, object] = {
        "schema_version": 1,
        "issue": 430,
        "status": "PASS" if not failures else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "feature_rows": len(features),
        "session_rows": len(sessions),
        "declared_stage1_outer_cost_trials": declared_stage1,
        "declared_total_trial_upper_bound": int(
            prereg["trial_accounting"]["declared_total_trial_upper_bound"]
        ),
        "parent_policy_id": str(prereg["parent"]["policy_id"]),
        "parent_reproduction_pass": parent_reproduction_pass,
        "operational_paper_max_contracts": int(risk.max_contracts),
        "research_max_abs_contracts": float(research["research_max_abs_contracts"]),
        "failures": failures,
        "prereg_sha256": sha256_file(PREREG),
        "issue429_result_sha256": sha256_file(ISSUE429_RESULT),
        "issue429_ledger_sha256": sha256_file(ISSUE429_LEDGER),
        "sizing_code_sha256": sha256_file(REPO / "src/commodity/v2_sizing_risk.py"),
        "runner_sha256": sha256_file(Path(__file__)),
    }
    report["preflight_sha256"] = stable_sha(report)
    if write:
        PREFLIGHT.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8", newline="\n",
        )
    return report


def evaluate_stage1(trials: pd.DataFrame, prereg: dict[str, Any]) -> list[dict[str, object]]:
    gate = prereg["promotion_gate"]
    rows: list[dict[str, object]] = []
    for policy_id, group in trials.groupby("policy_id", sort=True):
        base = group.loc[group["cost_profile"].astype(str).eq("base")].copy()
        if len(base) != len(prereg["outer_blocks"]):
            raise RuntimeError(f"issue430 incomplete base-cost outer coverage: {policy_id}")
        deltas = pd.to_numeric(base["mean_monthly_net_return_delta"], errors="raise")
        mean_delta = float(deltas.mean())
        nonnegative_fraction = float(deltas.ge(0.0).mean())
        higher = group.loc[~group["cost_profile"].astype(str).eq("base")]
        higher_nonnegative = bool(
            pd.to_numeric(higher["mean_monthly_net_return_delta"], errors="raise").ge(0.0).all()
        )
        hard_safe = not bool(group["hard_safety_regression"].astype(bool).any())
        concentration = float(
            pd.to_numeric(base["largest_incremental_positive_month_fraction"], errors="raise").max()
        )
        margin = float(
            pd.to_numeric(group["max_margin_utilization_fraction"], errors="raise").max()
        )
        passes = bool(
            mean_delta > float(gate["mean_outer_monthly_net_return_improvement_gt"])
            and nonnegative_fraction >= float(gate["nonnegative_outer_fraction_gte"])
            and hard_safe
            and higher_nonnegative
            and concentration <= float(gate["largest_incremental_positive_month_fraction_lte"])
            and margin < float(gate["max_margin_utilization_fraction_lt"])
        )
        rows.append({
            "policy_id": str(policy_id),
            "mean_outer_monthly_net_return_delta": mean_delta,
            "nonnegative_outer_fraction": nonnegative_fraction,
            "higher_cost_nonnegative": higher_nonnegative,
            "hard_safety_clear": hard_safe,
            "largest_incremental_positive_month_fraction": concentration,
            "max_margin_utilization_fraction": margin,
            "passes_return_gate": passes,
            "outer_base_deltas": {
                str(row.outer_id): float(row.mean_monthly_net_return_delta)
                for row in base.itertuples(index=False)
            },
        })
    return sorted(
        rows,
        key=lambda row: (
            not bool(row["passes_return_gate"]),
            -float(row["mean_outer_monthly_net_return_delta"]),
            str(row["policy_id"]),
        ),
    )


def select_stage2_parents(
    evaluation: list[dict[str, object]],
    prereg: dict[str, Any],
) -> list[str]:
    count = int(prereg["stage2_risk"]["mechanical_parent_count"])
    eligible = [row for row in evaluation if bool(row["hard_safety_clear"])]
    eligible.sort(
        key=lambda row: (
            -float(row["mean_outer_monthly_net_return_delta"]),
            str(row["policy_id"]),
        )
    )
    if len(eligible) < count:
        raise RuntimeError("issue430 has fewer safety-clear stage1 parents than declared")
    return [str(row["policy_id"]) for row in eligible[:count]]


def materialize_stage1_config(
    spec: dict[str, Any],
    *,
    favorable_regimes: tuple[str, ...],
    max_abs_contracts: float,
) -> dict[str, object]:
    config = {
        str(key): value
        for key, value in spec.items()
        if key not in {"id", "control", "use_prior_favorable_regimes"}
    }
    if bool(spec.get("use_prior_favorable_regimes")):
        config["favorable_regimes"] = list(favorable_regimes)
    config["max_abs_contracts"] = float(max_abs_contracts)
    return config


def largest_losing_month_fraction(ledger: pd.DataFrame) -> float:
    required = {"trade_date", "net_pnl_usd"}
    missing = sorted(required - set(ledger.columns))
    if missing:
        raise RuntimeError(f"issue430 loss-concentration ledger missing columns: {missing}")
    dates = pd.to_datetime(ledger["trade_date"], utc=True, errors="raise")
    pnl = pd.to_numeric(ledger["net_pnl_usd"], errors="raise").astype(float)
    months = dates.dt.tz_convert(None).dt.to_period("M")
    monthly = pnl.groupby(months).sum()
    losses = monthly.loc[monthly < 0.0].abs()
    if losses.empty:
        return 0.0
    return float(losses.max() / losses.sum())


def _score_ledger(ledger: pd.DataFrame, starting_capital_usd: float) -> dict[str, Any]:
    return v2.score_monthly_path(
        v2._phase2_ledger_for_monthly_score(ledger),
        starting_capital_usd=float(starting_capital_usd),
        latest_allowed_timestamp="2022-12-31",
    )


def score_stage1_candidate(
    *,
    path: pd.DataFrame,
    parent_policy: pd.DataFrame,
    spec: dict[str, Any],
    favorable_regimes: tuple[str, ...],
    risk: object,
    costs: object,
    contract_multiplier: float,
    max_abs_contracts: float,
    outer_id: str,
    cost_profile: str,
    parent_bundle: tuple[dict[str, Any], pd.DataFrame, dict[str, object]] | None = None,
) -> dict[str, object]:
    if parent_bundle is None:
        parent_ledger, parent_summary = sizing.replay_research_policy(
            path, parent_policy, risk, costs,
            contract_multiplier=contract_multiplier,
            max_abs_contracts=max_abs_contracts,
        )
        parent_score = _score_ledger(parent_ledger, float(risk.capital_usd))
    else:
        parent_score, parent_ledger, parent_summary = parent_bundle
    config = materialize_stage1_config(
        spec,
        favorable_regimes=favorable_regimes,
        max_abs_contracts=max_abs_contracts,
    )
    candidate_policy = sizing.apply_sizing_policy(parent_policy, config)
    ledger, replay_summary = sizing.replay_research_policy(
        path, candidate_policy, risk, costs,
        contract_multiplier=contract_multiplier,
        max_abs_contracts=max_abs_contracts,
    )
    score = _score_ledger(ledger, float(risk.capital_usd))
    hard_safety_regression = bool(
        bool(replay_summary.get("kill_triggered"))
        and not bool(parent_summary.get("kill_triggered"))
    ) or int(replay_summary.get("risk_shutdown_sessions", 0)) > int(
        parent_summary.get("risk_shutdown_sessions", 0)
    )
    return {
        "issue": 430,
        "stage": "stage1_sizing",
        "status": "complete",
        "policy_id": str(spec["id"]),
        "outer_id": str(outer_id),
        "cost_profile": str(cost_profile),
        "mean_monthly_net_return": float(score["mean_monthly_net_return"]),
        "parent_mean_monthly_net_return": float(parent_score["mean_monthly_net_return"]),
        "mean_monthly_net_return_delta": float(score["mean_monthly_net_return"])
        - float(parent_score["mean_monthly_net_return"]),
        "hard_safety_regression": hard_safety_regression,
        "largest_incremental_positive_month_fraction": joint.largest_incremental_month_fraction(
            ledger, parent_ledger
        ),
        "largest_losing_month_fraction": largest_losing_month_fraction(ledger),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"]),
        "worst_monthly_net_return": float(score["worst_monthly_net_return"]),
        "monthly_net_return_std": float(score["monthly_net_return_std"]),
        "transaction_cost_usd": float(score["transaction_cost_usd"]),
        "largest_positive_month_profit_fraction": float(
            score["largest_positive_month_profit_fraction"]
        ),
        "long_net_pnl_usd": float(score["long_net_pnl_usd"]),
        "short_net_pnl_usd": float(score["short_net_pnl_usd"]),
        "research_max_abs_contracts": float(replay_summary["research_max_abs_contracts"]),
        "operational_paper_max_contracts": int(
            replay_summary["operational_paper_max_contracts"]
        ),
        "max_margin_utilization_fraction": float(
            replay_summary["max_margin_utilization_fraction"]
        ),
        "max_notional_leverage": float(replay_summary["max_notional_leverage"]),
        "mean_notional_leverage": float(replay_summary["mean_notional_leverage"]),
        "score": dict(score),
        "replay_summary": dict(replay_summary),
    }


def _load_stage1_context() -> dict[str, object]:
    prereg429 = issue429.load_prereg()
    issue428_prereg, features, sessions, _families, _support = issue429.issue428._load_inputs()
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    features = issue429.issue428._features_with_volatility_tail(features)
    selected_reps = issue429.issue428._selected_representations()
    selected_models = issue429.issue428._selected_model_configs()
    matched_controls = issue429.issue459.v2.load_issue426_outer_matched_controls(
        issue429.issue428.ISSUE425
    )
    parent_wave2, wave2 = issue429._parent_wave2_config(prereg429)
    wave1_configs = issue429.joint.build_wave1_configs(issue429.issue459.load_prereg())
    parent_wave1 = issue429.issue459._wave1_config_for_policy(
        wave1_configs, parent_wave2.parent_policy_id, "base"
    )
    timesfm = issue429.issue459._load_specialist_frame(
        REPO / str(wave2["specialist_inputs"]["timesfm"]["path"]),
        "timesfm_point_return",
    )
    kronos = issue429.issue459._load_specialist_frame(
        REPO / str(wave2["specialist_inputs"]["kronos"]["path"]),
        "kronos_close_return",
    )
    return {
        "prereg429": prereg429,
        "issue428_prereg": issue428_prereg,
        "features": features,
        "sessions": sessions,
        "cfg": cfg,
        "risk": risk,
        "cost_profiles": cost_profiles,
        "selected_reps": selected_reps,
        "selected_models": selected_models,
        "matched_controls": matched_controls,
        "parent_wave1": parent_wave1,
        "parent_wave2": parent_wave2,
        "timesfm": timesfm,
        "kronos": kronos,
    }


def _build_stage1_outer_context(
    outer_id: str,
    context: dict[str, object],
) -> tuple[dict[str, str], pd.DataFrame, tuple[str, ...], pd.DataFrame]:
    cost_profiles = context["cost_profiles"]
    block, parent_policy, _contribution, _lifecycle = issue429._build_outer_policy_sets(
        outer_id=outer_id,
        prereg=context["prereg429"],
        issue428_prereg=context["issue428_prereg"],
        features=context["features"],
        sessions=context["sessions"],
        cfg=context["cfg"],
        selected_reps=context["selected_reps"],
        selected_models=context["selected_models"],
        matched_controls=context["matched_controls"],
        parent_wave1=context["parent_wave1"],
        parent_wave2=context["parent_wave2"],
        timesfm=context["timesfm"],
        kronos=context["kronos"],
        round_trip_usd=float(cost_profiles["base"].round_trip_usd),
    )
    signal_columns = issue429.issue428._signal_columns_for_outer(
        outer_id, context["selected_reps"]
    )
    opportunities = issue429.issue428._build_outer_opportunities(
        target_outer_id=outer_id,
        features=context["features"],
        sessions=context["sessions"],
        cfg=context["cfg"],
        selected_config=context["selected_models"][outer_id],
        matched_config=context["matched_controls"][outer_id]["config"],
        signal_columns=signal_columns,
        round_trip_usd=float(cost_profiles["base"].round_trip_usd),
    )
    start = pd.Timestamp(str(block["start"]), tz="UTC")
    end = pd.Timestamp(str(block["end"]), tz="UTC")
    history = issue429.dec.completed_history_before(opportunities, start)
    fill_dates = pd.to_datetime(opportunities["fill_trade_date"], utc=True, errors="raise")
    outer = opportunities.loc[(fill_dates >= start) & (fill_dates <= end)].copy()
    state, _history, _outer = issue429.issue428._annotated_context(
        history,
        outer,
        signal_columns,
        context["issue428_prereg"],
        outcome_available_before=start,
    )
    path, _start, _boundary = issue429.issue428._path_window(
        context["sessions"],
        start_date=str(block["start"]),
        end_date=str(block["end"]),
    )
    return dict(block), parent_policy, tuple(state.favorable_regimes), path


def _parent_bundle(
    path: pd.DataFrame,
    parent_policy: pd.DataFrame,
    risk: object,
    costs: object,
    *,
    contract_multiplier: float,
    max_abs_contracts: float,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, object]]:
    ledger, summary = sizing.replay_research_policy(
        path, parent_policy, risk, costs,
        contract_multiplier=contract_multiplier,
        max_abs_contracts=max_abs_contracts,
    )
    score = _score_ledger(ledger, float(risk.capital_usd))
    return score, ledger, summary


def score_stage1_subset(policy_ids: list[str]) -> dict[str, object]:
    prereg = load_prereg()
    requested = [str(value) for value in policy_ids]
    specs = {
        str(spec["id"]): dict(spec)
        for spec in prereg["stage1_sizing"]["policy_configs"]
    }
    unknown = sorted(set(requested) - set(specs))
    if unknown or len(requested) != len(set(requested)):
        raise RuntimeError(f"issue430 invalid stage1 subset: {unknown}")
    context = _load_stage1_context()
    risk = context["risk"]
    cost_profiles = context["cost_profiles"]
    multiplier = float(context["cfg"]["execution_contract"]["contract_multiplier_mmbtu"])
    cap = float(prereg["stage1_sizing"]["max_abs_contracts"])
    trials: list[dict[str, object]] = []
    for outer_id in map(str, prereg["outer_blocks"]):
        _block, parent_policy, favorable_regimes, path = _build_stage1_outer_context(
            outer_id, context
        )
        parent_by_cost = {
            str(cost_name): _parent_bundle(
                path,
                parent_policy,
                risk,
                cost_profiles[str(cost_name)],
                contract_multiplier=multiplier,
                max_abs_contracts=cap,
            )
            for cost_name in prereg["cost_profiles"]
        }
        for policy_id in requested:
            for cost_name in map(str, prereg["cost_profiles"]):
                trials.append(
                    score_stage1_candidate(
                        path=path,
                        parent_policy=parent_policy,
                        spec=specs[policy_id],
                        favorable_regimes=favorable_regimes,
                        risk=risk,
                        costs=cost_profiles[cost_name],
                        contract_multiplier=multiplier,
                        max_abs_contracts=cap,
                        outer_id=outer_id,
                        cost_profile=cost_name,
                        parent_bundle=parent_by_cost[cost_name],
                    )
                )
    return {
        "issue": 430,
        "stage": "stage1_sizing",
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "policy_ids": requested,
        "trials": trials,
    }


def _require_preflight() -> dict[str, Any]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue430 scoring requires a completed no-scoring preflight")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("issue430 preflight is not a passing no-scoring report")
    if report.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue430 preflight protected-evidence flag changed")
    expected_preflight_sha = stable_sha(
        {key: value for key, value in report.items() if key != "preflight_sha256"}
    )
    if report.get("preflight_sha256") != expected_preflight_sha:
        raise RuntimeError("issue430 preflight self-hash is stale")
    parent_failures = _parent_file_failures(load_prereg())
    if parent_failures:
        raise RuntimeError(f"issue430 parent bindings changed: {parent_failures}")
    if RESULT.exists():
        raise RuntimeError(
            "issue430 scoring is frozen after the completed result; use a new research identity"
        )
    expected = {
        "prereg_sha256": sha256_file(PREREG),
        "issue429_result_sha256": sha256_file(ISSUE429_RESULT),
        "issue429_ledger_sha256": sha256_file(ISSUE429_LEDGER),
        "sizing_code_sha256": sha256_file(REPO / "src/commodity/v2_sizing_risk.py"),
        "runner_sha256": sha256_file(Path(__file__)),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"issue430 preflight is stale: {key}")
    return report


def score_stage1(*, write: bool = True) -> dict[str, object]:
    preflight_report = _require_preflight()
    prereg = load_prereg()
    policy_ids = [str(spec["id"]) for spec in prereg["stage1_sizing"]["policy_configs"]]
    scored = score_stage1_subset(policy_ids)
    trials = list(scored["trials"])
    expected = int(prereg["trial_accounting"]["declared_stage1_outer_cost_trials"])
    if len(trials) != expected:
        raise RuntimeError(f"issue430 stage1 trial accounting changed:{len(trials)}!={expected}")
    evaluation = evaluate_stage1(pd.DataFrame(trials), prereg)
    selected = select_stage2_parents(evaluation, prereg)
    result: dict[str, object] = {
        "issue": 430,
        "stage": "stage1_sizing",
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "trial_count": len(trials),
        "evaluated_policy_count": len(evaluation),
        "evaluation": evaluation,
        "selected_stage2_parent_policy_ids": selected,
        "preflight_sha256": preflight_report["preflight_sha256"],
        "prereg_sha256": sha256_file(PREREG),
        "runner_sha256": sha256_file(Path(__file__)),
        "sizing_code_sha256": sha256_file(REPO / "src/commodity/v2_sizing_risk.py"),
    }
    if write:
        LEDGER.write_text(
            "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in trials),
            encoding="utf-8", newline="\n",
        )
    return result


def score_stage2_candidate(
    *,
    path: pd.DataFrame,
    sized_parent_policy: pd.DataFrame,
    parent_policy_id: str,
    risk_spec: dict[str, Any],
    risk: object,
    costs: object,
    contract_multiplier: float,
    max_abs_contracts: float,
    outer_id: str,
    cost_profile: str,
    parent_bundle: tuple[dict[str, Any], pd.DataFrame, dict[str, object]] | None = None,
) -> dict[str, object]:
    if parent_bundle is None:
        parent_bundle = _parent_bundle(
            path, sized_parent_policy, risk, costs,
            contract_multiplier=contract_multiplier,
            max_abs_contracts=max_abs_contracts,
        )
    parent_score, parent_ledger, parent_summary = parent_bundle
    candidate_policy = sized_parent_policy
    risk_config = {
        str(key): value for key, value in risk_spec.items() if key not in {"id", "kind"}
    }
    cooldown = int(risk_config.pop("additional_loss_cooldown_sessions", 0))
    if cooldown:
        candidate_policy = sizing.apply_additional_loss_cooldown(
            candidate_policy, cooldown
        )
    if str(risk_spec.get("kind", "")) == "control" or not risk_config:
        ledger, replay_summary = sizing.replay_research_policy(
            path, candidate_policy, risk, costs,
            contract_multiplier=contract_multiplier,
            max_abs_contracts=max_abs_contracts,
        )
    else:
        ledger, replay_summary = sizing.replay_risk_controlled_policy(
            path, candidate_policy, risk, costs,
            contract_multiplier=contract_multiplier,
            max_abs_contracts=max_abs_contracts,
            risk_config=risk_config,
        )
    score = _score_ledger(ledger, float(risk.capital_usd))
    hard_safety_regression = bool(
        bool(replay_summary.get("kill_triggered"))
        and not bool(parent_summary.get("kill_triggered"))
    ) or int(replay_summary.get("risk_shutdown_sessions", 0)) > int(
        parent_summary.get("risk_shutdown_sessions", 0)
    )
    return {
        "issue": 430,
        "stage": "stage2_risk",
        "status": "complete",
        "parent_policy_id": str(parent_policy_id),
        "risk_variant_id": str(risk_spec["id"]),
        "policy_id": f"{parent_policy_id}__{risk_spec['id']}",
        "outer_id": str(outer_id),
        "cost_profile": str(cost_profile),
        "mean_monthly_net_return": float(score["mean_monthly_net_return"]),
        "sized_parent_mean_monthly_net_return": float(
            parent_score["mean_monthly_net_return"]
        ),
        "mean_monthly_net_return_delta_vs_sized_parent": float(
            score["mean_monthly_net_return"]
        ) - float(parent_score["mean_monthly_net_return"]),
        "hard_safety_regression": hard_safety_regression,
        "largest_incremental_positive_month_fraction": joint.largest_incremental_month_fraction(
            ledger, parent_ledger
        ),
        "largest_losing_month_fraction": largest_losing_month_fraction(ledger),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"]),
        "worst_monthly_net_return": float(score["worst_monthly_net_return"]),
        "monthly_net_return_std": float(score["monthly_net_return_std"]),
        "transaction_cost_usd": float(score["transaction_cost_usd"]),
        "largest_positive_month_profit_fraction": float(
            score["largest_positive_month_profit_fraction"]
        ),
        "long_net_pnl_usd": float(score["long_net_pnl_usd"]),
        "short_net_pnl_usd": float(score["short_net_pnl_usd"]),
        "research_max_abs_contracts": float(replay_summary["research_max_abs_contracts"]),
        "operational_paper_max_contracts": int(
            replay_summary["operational_paper_max_contracts"]
        ),
        "max_margin_utilization_fraction": float(
            replay_summary["max_margin_utilization_fraction"]
        ),
        "max_notional_leverage": float(replay_summary["max_notional_leverage"]),
        "mean_notional_leverage": float(replay_summary["mean_notional_leverage"]),
        "soft_drawdown_scaled_sessions": int(
            replay_summary.get("soft_drawdown_scaled_sessions", 0)
        ),
        "stop_trigger_count": int(replay_summary.get("stop_trigger_count", 0)),
        "take_profit_trigger_count": int(
            replay_summary.get("take_profit_trigger_count", 0)
        ),
        "score": dict(score),
        "replay_summary": dict(replay_summary),
    }


def evaluate_stage2(trials: pd.DataFrame, prereg: dict[str, Any]) -> list[dict[str, object]]:
    gate = prereg["promotion_gate"]
    expected_pairs = {
        (str(outer), str(cost))
        for outer in prereg["outer_blocks"]
        for cost in prereg["cost_profiles"]
    }
    rows: list[dict[str, object]] = []
    for (parent_id, risk_id), group in trials.groupby(
        ["parent_policy_id", "risk_variant_id"], sort=True
    ):
        observed = {
            (str(row.outer_id), str(row.cost_profile))
            for row in group.itertuples(index=False)
        }
        if observed != expected_pairs or len(group) != len(expected_pairs):
            raise RuntimeError(
                f"issue430 incomplete stage2 coverage:{parent_id}:{risk_id}"
            )
        base = group.loc[group["cost_profile"].astype(str).eq("base")].copy()
        higher = group.loc[~group["cost_profile"].astype(str).eq("base")].copy()
        deltas = pd.to_numeric(
            base["mean_monthly_net_return_delta_vs_sized_parent"], errors="raise"
        )
        mean_delta = float(deltas.mean())
        nonnegative_fraction = float(deltas.ge(0.0).mean())
        higher_nonnegative = bool(
            pd.to_numeric(
                higher["mean_monthly_net_return_delta_vs_sized_parent"], errors="raise"
            ).ge(0.0).all()
        )
        hard_safe = not bool(group["hard_safety_regression"].astype(bool).any())
        concentration = float(
            pd.to_numeric(
                base["largest_incremental_positive_month_fraction"], errors="raise"
            ).max()
        )
        margin = float(
            pd.to_numeric(group["max_margin_utilization_fraction"], errors="raise").max()
        )
        passes = bool(
            mean_delta > float(gate["mean_outer_monthly_net_return_improvement_gt"])
            and nonnegative_fraction >= float(gate["nonnegative_outer_fraction_gte"])
            and higher_nonnegative
            and hard_safe
            and concentration <= float(gate["largest_incremental_positive_month_fraction_lte"])
            and margin < float(gate["max_margin_utilization_fraction_lt"])
        )
        rows.append({
            "parent_policy_id": str(parent_id),
            "risk_variant_id": str(risk_id),
            "mean_outer_monthly_net_return_delta": mean_delta,
            "nonnegative_outer_fraction": nonnegative_fraction,
            "higher_cost_nonnegative": higher_nonnegative,
            "hard_safety_clear": hard_safe,
            "largest_incremental_positive_month_fraction": concentration,
            "max_margin_utilization_fraction": margin,
            "passes_risk_gate": passes,
            "outer_base_deltas": {
                str(row.outer_id): float(row.mean_monthly_net_return_delta_vs_sized_parent)
                for row in base.itertuples(index=False)
            },
        })
    return sorted(
        rows,
        key=lambda row: (
            not bool(row["passes_risk_gate"]),
            -float(row["mean_outer_monthly_net_return_delta"]),
            str(row["parent_policy_id"]),
            str(row["risk_variant_id"]),
        ),
    )


def score_stage2_subset(
    parent_policy_ids: list[str],
    risk_variant_ids: list[str],
) -> dict[str, object]:
    prereg = load_prereg()
    sizing_specs = {
        str(spec["id"]): dict(spec)
        for spec in prereg["stage1_sizing"]["policy_configs"]
    }
    risk_specs = {
        str(spec["id"]): dict(spec)
        for spec in prereg["stage2_risk"]["risk_variants"]
    }
    parents = [str(value) for value in parent_policy_ids]
    risks = [str(value) for value in risk_variant_ids]
    if set(parents) - set(sizing_specs) or len(parents) != len(set(parents)):
        raise RuntimeError("issue430 invalid stage2 parent subset")
    if set(risks) - set(risk_specs) or len(risks) != len(set(risks)):
        raise RuntimeError("issue430 invalid stage2 risk subset")
    context = _load_stage1_context()
    risk = context["risk"]
    cost_profiles = context["cost_profiles"]
    multiplier = float(context["cfg"]["execution_contract"]["contract_multiplier_mmbtu"])
    cap = float(prereg["stage1_sizing"]["max_abs_contracts"])
    trials: list[dict[str, object]] = []
    for outer_id in map(str, prereg["outer_blocks"]):
        _block, promoted_parent, favorable_regimes, path = _build_stage1_outer_context(
            outer_id, context
        )
        for parent_id in parents:
            config = materialize_stage1_config(
                sizing_specs[parent_id],
                favorable_regimes=favorable_regimes,
                max_abs_contracts=cap,
            )
            sized_parent = sizing.apply_sizing_policy(promoted_parent, config)
            parent_by_cost = {
                str(cost_name): _parent_bundle(
                    path,
                    sized_parent,
                    risk,
                    cost_profiles[str(cost_name)],
                    contract_multiplier=multiplier,
                    max_abs_contracts=cap,
                )
                for cost_name in prereg["cost_profiles"]
            }
            for risk_id in risks:
                for cost_name in map(str, prereg["cost_profiles"]):
                    trials.append(
                        score_stage2_candidate(
                            path=path,
                            sized_parent_policy=sized_parent,
                            parent_policy_id=parent_id,
                            risk_spec=risk_specs[risk_id],
                            risk=risk,
                            costs=cost_profiles[cost_name],
                            contract_multiplier=multiplier,
                            max_abs_contracts=cap,
                            outer_id=outer_id,
                            cost_profile=cost_name,
                            parent_bundle=parent_by_cost[cost_name],
                        )
                    )
    return {
        "issue": 430,
        "stage": "stage2_risk",
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "parent_policy_ids": parents,
        "risk_variant_ids": risks,
        "trials": trials,
    }


def allocation_efficiency_summary(trials: pd.DataFrame) -> list[dict[str, object]]:
    required = {
        "policy_id", "outer_id", "cost_profile",
        "mean_monthly_net_return", "mean_notional_leverage",
    }
    missing = sorted(required - set(trials.columns))
    if missing:
        raise RuntimeError(f"issue430 allocation summary missing columns: {missing}")
    base = trials.loc[trials["cost_profile"].astype(str).eq("base")].copy()
    fixed = base.loc[base["policy_id"].astype(str).str.startswith("fixed_")].copy()
    if fixed.empty:
        raise RuntimeError("issue430 allocation summary has no fixed-exposure controls")
    rows: list[dict[str, object]] = []
    for policy_id, group in base.groupby("policy_id", sort=True):
        policy_id = str(policy_id)
        if policy_id.startswith("fixed_"):
            rows.append({
                "policy_id": policy_id,
                "classification": "exposure_amplification_control",
                "distinct_allocation_value": False,
                "mean_monthly_return_delta_vs_nearest_fixed": 0.0,
                "nonnegative_outer_fraction_vs_nearest_fixed": 1.0,
                "nearest_fixed_policy_ids": {
                    str(row.outer_id): policy_id for row in group.itertuples(index=False)
                },
            })
            continue
        nearest: dict[str, str] = {}
        deltas: list[float] = []
        for candidate in group.itertuples(index=False):
            outer_fixed = fixed.loc[
                fixed["outer_id"].astype(str).eq(str(candidate.outer_id))
            ].copy()
            if outer_fixed.empty:
                raise RuntimeError(
                    f"issue430 missing fixed control for outer:{candidate.outer_id}"
                )
            target_leverage = float(candidate.mean_notional_leverage)
            outer_fixed["distance"] = (
                pd.to_numeric(
                    outer_fixed["mean_notional_leverage"], errors="raise"
                ) - target_leverage
            ).abs()
            chosen = outer_fixed.sort_values(
                ["distance", "policy_id"], kind="stable"
            ).iloc[0]
            nearest[str(candidate.outer_id)] = str(chosen["policy_id"])
            deltas.append(
                float(candidate.mean_monthly_net_return)
                - float(chosen["mean_monthly_net_return"])
            )
        mean_delta = float(pd.Series(deltas, dtype=float).mean())
        nonnegative = float(pd.Series(deltas, dtype=float).ge(0.0).mean())
        rows.append({
            "policy_id": policy_id,
            "classification": "dynamic_allocation_candidate",
            "distinct_allocation_value": bool(mean_delta > 0.0 and nonnegative >= 1.0),
            "mean_monthly_return_delta_vs_nearest_fixed": mean_delta,
            "nonnegative_outer_fraction_vs_nearest_fixed": nonnegative,
            "nearest_fixed_policy_ids": nearest,
        })
    return sorted(
        rows,
        key=lambda row: (
            not bool(row["distinct_allocation_value"]),
            -float(row["mean_monthly_return_delta_vs_nearest_fixed"]),
            str(row["policy_id"]),
        ),
    )


def promotable_stage2_variants(
    stage1_evaluation: list[dict[str, object]],
    stage2_evaluation: list[dict[str, object]],
) -> list[dict[str, object]]:
    passing_stage1_ids = {
        str(row["policy_id"])
        for row in stage1_evaluation
        if bool(row["passes_return_gate"])
    }
    return [
        row
        for row in stage2_evaluation
        if bool(row["passes_risk_gate"])
        and str(row["parent_policy_id"]) in passing_stage1_ids
    ]


def score_issue430() -> dict[str, object]:
    preflight_report = _require_preflight()
    prereg = load_prereg()
    stage1 = score_stage1(write=True)
    stage1_trials = [
        json.loads(line)
        for line in LEDGER.read_text(encoding="utf-8").splitlines()
        if line
    ]
    selected_parents = [
        str(value) for value in stage1["selected_stage2_parent_policy_ids"]
    ]
    risk_ids = [
        str(spec["id"]) for spec in prereg["stage2_risk"]["risk_variants"]
    ]
    stage2 = score_stage2_subset(selected_parents, risk_ids)
    stage2_trials = list(stage2["trials"])
    expected_stage2 = int(
        prereg["trial_accounting"]["declared_stage2_outer_cost_trial_upper_bound"]
    )
    if len(stage2_trials) != expected_stage2:
        raise RuntimeError(
            f"issue430 stage2 trial accounting changed:{len(stage2_trials)}!={expected_stage2}"
        )
    stage2_evaluation = evaluate_stage2(pd.DataFrame(stage2_trials), prereg)
    stage1_evaluation = list(stage1["evaluation"])
    allocation = allocation_efficiency_summary(pd.DataFrame(stage1_trials))
    passing_stage1 = [row for row in stage1_evaluation if row["passes_return_gate"]]
    passing_stage2 = promotable_stage2_variants(stage1_evaluation, stage2_evaluation)
    if passing_stage2:
        disposition = "FREEZE_ISSUE430_SIZING_RISK_DEVELOPMENT_CANDIDATE"
    elif passing_stage1:
        disposition = "FREEZE_ISSUE430_SIZING_DEVELOPMENT_CANDIDATE_NO_RISK_INCREMENT"
    else:
        disposition = "NO_ISSUE430_ROBUST_SIZING_OR_RISK_IMPROVEMENT"
    combined_trials = [*stage1_trials, *stage2_trials]
    expected_total = int(prereg["trial_accounting"]["declared_total_trial_upper_bound"])
    if len(combined_trials) != expected_total:
        raise RuntimeError(
            f"issue430 total trial accounting changed:{len(combined_trials)}!={expected_total}"
        )
    LEDGER.write_text(
        "".join(
            json.dumps(row, sort_keys=True, default=str) + "\n"
            for row in combined_trials
        ),
        encoding="utf-8",
        newline="\n",
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 430,
        "evidence_class": "development",
        "claim_boundary": prereg["claim_boundary"],
        "protected_confirmation_accessed": False,
        "parent_policy_id": prereg["parent"]["policy_id"],
        "stage1_trial_count": len(stage1_trials),
        "stage2_trial_count": len(stage2_trials),
        "trial_count": len(combined_trials),
        "stage1_evaluation": stage1_evaluation,
        "stage1_passing_policy_count": len(passing_stage1),
        "stage1_passing_policies": passing_stage1,
        "selected_stage2_parent_policy_ids": selected_parents,
        "allocation_efficiency": allocation,
        "stage2_evaluation": stage2_evaluation,
        "stage2_passing_variant_count": len(passing_stage2),
        "stage2_passing_variants": passing_stage2,
        "options_implied_lane": dict(prereg["options_implied_lane"]),
        "fixed_exposure_interpretation": (
            "fixed-scale return changes are exposure amplification, not new directional edge"
        ),
        "disposition": disposition,
        "preflight_sha256": preflight_report["preflight_sha256"],
        "prereg_sha256": sha256_file(PREREG),
        "runner_sha256": sha256_file(Path(__file__)),
        "sizing_code_sha256": sha256_file(REPO / "src/commodity/v2_sizing_risk.py"),
        "trial_ledger_file_sha256": sha256_file(LEDGER),
    }
    result["result_sha256"] = stable_sha(
        {key: value for key, value in result.items() if key != "result_sha256"}
    )
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> int:
    if "--preflight" in sys.argv:
        payload = preflight(write=True)
    else:
        payload = score_issue430()
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
