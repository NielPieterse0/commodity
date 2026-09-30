from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts/research"))

import run_issue448_coverage as issue448

from commodity import v2_model_optimization as opt
from commodity import v2_optimization as v2
from commodity.market_only_phase2 import (
    _inner_fold_specs,
    _load_inherited_risk_and_costs,
)

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue427-prereg-v1.json"
PREFLIGHT = PROGRAMME / "issue427-preflight-v1.json"
RESULT = PROGRAMME / "issue427-core-result-v1.json"
FINAL_RESULT = PROGRAMME / "issue427-result-v1.json"
LEDGER = PROGRAMME / "issue427-trials-v1.jsonl"
SPECIALIST_LEDGER = PROGRAMME / "issue427-specialist-trials-v1.jsonl"
ISSUE425 = PROGRAMME / "issue425-result-v1.json"
ISSUE425_SEARCH_PLAN = PROGRAMME / "issue425-search-plan-v1.json"
ISSUE448 = PROGRAMME / "issue448-result-v1.json"
ISSUE448_HANDOFF = PROGRAMME / "issue448-downstream-handoff-v1.json"
PHASE2 = REPO / "config/phase2_market_only.json"
PHASE4_AUDIT = REPO / ".work/changes/358-foundation-specialists/phase4-specialist-audit.json"
PHASE5_RESULT = REPO / ".work/changes/359-stacking-policy/phase5-stacking-policy-result.json"
TIMESFM_FEATURES = REPO / ".work/changes/358-foundation-specialists/timesfm-features.csv"
KRONOS_FEATURES = REPO / ".work/changes/358-foundation-specialists/kronos-features.csv"
CHRONOS_SUMMARY = REPO / ".work/changes/358-foundation-specialists/chronos-2-path-summary.json"
MOIRAI_SUMMARY = REPO / ".work/changes/358-foundation-specialists/moirai-2-small-path-summary.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _require_hash(path: Path, expected: str, label: str) -> None:
    observed = sha256_file(path)
    if observed != expected:
        raise RuntimeError(f"issue427 {label} identity changed: {observed}")


def load_prereg() -> dict[str, object]:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "frozen_before_issue427_scoring":
        raise RuntimeError("issue427 preregistration is not frozen")
    boundary = prereg.get("evidence_boundary", {})
    if boundary.get("latest_allowed_trade_date") != "2022-12-31":
        raise RuntimeError("issue427 development cutoff changed")
    if boundary.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue427 protected evidence flag is not false")
    return prereg


def verify_authorities(prereg: Mapping[str, object]) -> None:
    authority = prereg["authority"]
    upstream = prereg["upstream_evidence"]
    assert isinstance(authority, Mapping) and isinstance(upstream, Mapping)
    _require_hash(REPO / "config/v2_variable_registry.json", str(authority["registry_sha256"]), "registry")
    _require_hash(PHASE2, str(authority["phase2_sha256"]), "phase2")
    _require_hash(ISSUE425, str(upstream["issue425_result_sha256"]), "issue425")
    issue425_result = json.loads(ISSUE425.read_text(encoding="utf-8"))
    _require_hash(
        ISSUE425_SEARCH_PLAN,
        str(issue425_result["search_plan_sha256"]),
        "issue425 search plan",
    )
    _require_hash(ISSUE448, str(upstream["issue448_result_sha256"]), "issue448")
    _require_hash(
        ISSUE448_HANDOFF, str(upstream["issue448_handoff_sha256"]), "issue448 handoff"
    )
    _require_hash(
        REPO / ".work/changes/358-foundation-specialists/phase4-specialist-audit.json",
        str(upstream["phase4_specialist_audit_sha256"]),
        "phase4 specialist audit",
    )
    _require_hash(
        REPO / ".work/changes/359-stacking-policy/phase5-stacking-policy-result.json",
        str(upstream["phase5_policy_result_sha256"]),
        "phase5 stacking result",
    )


def _kill_triggered(result: Mapping[str, object]) -> bool:
    blocks = result.get("block_scores", [])
    return any(
        isinstance(row, Mapping)
        and isinstance(row.get("policy_summary"), Mapping)
        and bool(row["policy_summary"].get("kill_triggered"))
        for row in blocks
    )


def _trial(stage: str, payload: Mapping[str, object]) -> dict[str, object]:
    core = {
        "issue": 427,
        "evidence_class": "development",
        "stage": stage,
        **dict(payload),
    }
    return {"trial_id": stable_sha(core), **core}


def _outer_blocks(cfg: Mapping[str, object]) -> dict[str, dict[str, str]]:
    validation = cfg.get("validation", {})
    if not isinstance(validation, Mapping):
        raise TypeError("issue427 phase2 validation is invalid")
    blocks = validation.get("outer_blocks", [])
    return {str(row["id"]): dict(row) for row in blocks if isinstance(row, Mapping)}


def _prior_inner_blocks(
    inner_blocks: Sequence[Mapping[str, str]], outer: Mapping[str, str]
) -> list[dict[str, str]]:
    outer_start = pd.Timestamp(str(outer["start"]), tz="UTC")
    return [
        dict(block)
        for block in inner_blocks
        if pd.Timestamp(str(block["end"]), tz="UTC") < outer_start
    ]


def preflight() -> dict[str, object]:
    prereg = load_prereg()
    verify_authorities(prereg)
    features, families, source_evidence, _selection_support = issue448.load_preflight_cache()
    market, sessions = issue448.load_market()
    cutoff = pd.Timestamp("2022-12-31", tz="UTC")
    failures: list[str] = []
    if len(features) != len(market):
        failures.append(f"feature_row_count_changed:{len(features)}!={len(market)}")
    if pd.to_datetime(features["trade_date"], utc=True).max() > cutoff:
        failures.append("feature_matrix_crosses_protected_cutoff")
    retained = prereg["frozen_handoff"]["retained_feature_families"]
    missing_families = sorted(set(map(str, retained)) - set(families))
    if missing_families:
        failures.append(f"missing_retained_families:{missing_families}")
    outer_controls = v2.load_issue426_outer_matched_controls(ISSUE425)
    for outer_id in prereg["validation"]["outer_blocks"]:
        if str(outer_id) not in outer_controls:
            failures.append(f"missing_issue425_outer_control:{outer_id}")
            continue
        opt.build_issue427_model_candidates(
            dict(outer_controls[str(outer_id)]["config"]), prereg
        )
    report: dict[str, object] = {
        "schema_version": 1,
        "issue": 427,
        "status": "PASS" if not failures else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "feature_rows": len(features),
        "session_rows": len(sessions),
        "family_count": len(families),
        "failures": failures,
        "prereg_sha256": sha256_file(PREREG),
        "issue425_search_plan_sha256": sha256_file(ISSUE425_SEARCH_PLAN),
        "issue448_preflight_sha256": sha256_file(issue448.PREFLIGHT),
        "issue448_feature_cache_sha256": sha256_file(issue448.CACHE / "preflight-features.parquet"),
        "source_evidence_sha256": stable_sha(source_evidence),
        "runner_sha256": sha256_file(Path(__file__)),
        "model_code_sha256": sha256_file(REPO / "src/commodity/v2_model_optimization.py"),
        "v2_code_sha256": sha256_file(REPO / "src/commodity/v2_optimization.py"),
    }
    report["preflight_sha256"] = stable_sha(report)
    PREFLIGHT.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report


def _load_scoring_inputs() -> tuple[
    dict[str, object], pd.DataFrame, pd.DataFrame, dict[str, tuple[str, ...]], dict[str, object]
]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue427 scoring requires completed preflight")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("issue427 preflight is not a passing no-scoring report")
    prereg = load_prereg()
    verify_authorities(prereg)
    expected = {
        "prereg_sha256": sha256_file(PREREG),
        "issue425_search_plan_sha256": sha256_file(ISSUE425_SEARCH_PLAN),
        "issue448_preflight_sha256": sha256_file(issue448.PREFLIGHT),
        "issue448_feature_cache_sha256": sha256_file(issue448.CACHE / "preflight-features.parquet"),
        "runner_sha256": sha256_file(Path(__file__)),
        "model_code_sha256": sha256_file(REPO / "src/commodity/v2_model_optimization.py"),
        "v2_code_sha256": sha256_file(REPO / "src/commodity/v2_optimization.py"),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"issue427 preflight is stale: {key}")
    features, families, _source_evidence, _selection_support = issue448.load_preflight_cache()
    _market, sessions = issue448.load_market()
    return prereg, features, sessions, families, report


def _score_core_models(
    *,
    prereg: Mapping[str, object],
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, object],
    risk: object,
    costs: object,
    minimum_training_rows: int,
    trials: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    inner_blocks = _inner_fold_specs(cfg)
    outers = _outer_blocks(cfg)
    outer_controls = v2.load_issue426_outer_matched_controls(ISSUE425)
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    round_trip = float(costs.round_trip_usd) / multiplier
    results: dict[str, object] = {}
    selected_configs: dict[str, dict[str, object]] = {}

    for outer_id in map(str, prereg["validation"]["outer_blocks"]):
        outer = outers[outer_id]
        prior = _prior_inner_blocks(inner_blocks, outer)
        base_config = dict(outer_controls[outer_id]["config"])
        origins, columns = opt.prepare_issue427_market_origins(
            sessions, features, base_config, round_trip_per_mmbtu=round_trip
        )
        candidates = opt.build_issue427_model_candidates(base_config, prereg)
        selection_rows: list[dict[str, object]] = []
        for candidate in candidates:
            try:
                scored = opt.score_issue427_config(
                    origins, columns, sessions, candidate, prior, cfg, risk, costs,
                    minimum_training_rows=minimum_training_rows,
                )
                selection_rows.append(scored)
                trials.append(
                    _trial(
                        "core_model_inner_selection",
                        {
                            "outer_block_id": outer_id,
                            "selection_block_ids": [str(block["id"]) for block in prior],
                            "candidate_id": scored["candidate_id"],
                            "config": dict(candidate),
                            "monthly_score": scored["monthly_score"],
                            "kill_triggered": _kill_triggered(scored),
                        },
                    )
                )
            except (
                opt.Issue427OptimizationError,
                v2.V2OptimizationError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                trials.append(
                    _trial(
                        "core_model_inner_selection_failed",
                        {
                            "outer_block_id": outer_id,
                            "config": dict(candidate),
                            "reason": str(exc),
                        },
                    )
                )
        if not selection_rows:
            raise RuntimeError(f"issue427 no scorable model candidates for {outer_id}")
        selected = dict(opt.select_issue427_model(selection_rows))
        selected_config = dict(selected["config"])

        selected_configs[outer_id] = selected_config
        selected_outer = opt.score_issue427_config(
            origins,
            columns,
            sessions,
            selected_config,
            [outer],
            cfg,
            risk,
            costs,
            minimum_training_rows=minimum_training_rows,
        )
        baseline_outer = opt.score_issue427_config(
            origins,
            columns,
            sessions,
            base_config,
            [outer],
            cfg,
            risk,
            costs,
            minimum_training_rows=minimum_training_rows,
        )
        selected_score = selected_outer["monthly_score"]
        baseline_score = baseline_outer["monthly_score"]
        assert isinstance(selected_score, Mapping) and isinstance(baseline_score, Mapping)
        delta = float(selected_score["mean_monthly_net_return"]) - float(
            baseline_score["mean_monthly_net_return"]
        )
        kill_regression = _kill_triggered(selected_outer) and not _kill_triggered(
            baseline_outer
        )
        results[outer_id] = {
            "outer_block": outer,
            "selected_config": selected_config,
            "inner_selected_candidate_id": selected["candidate_id"],
            "inner_selected_monthly_score": selected["monthly_score"],
            "selected_outer": selected_outer,
            "matched_issue425_outer": baseline_outer,
            "mean_monthly_net_return_delta": delta,
            "kill_trigger_regression": kill_regression,
        }
        trials.append(
            _trial(
                "core_model_outer_evaluation",
                {
                    "outer_block_id": outer_id,
                    "selected_config": selected_config,
                    "mean_monthly_net_return_delta": delta,
                    "selected_monthly_score": selected_score,
                    "baseline_monthly_score": baseline_score,
                    "kill_trigger_regression": kill_regression,
                },
            )
        )

    gate_cfg = prereg["promotion_gates"]["development_advantage"]
    deltas = [
        float(results[outer_id]["mean_monthly_net_return_delta"])
        for outer_id in map(str, prereg["validation"]["outer_blocks"])
    ]
    gate = opt.evaluate_issue427_advantage(
        deltas,
        required_nonnegative_fraction=float(gate_cfg["nonnegative_outer_fraction_gte"]),
    )
    kill_regression = any(
        bool(results[outer_id]["kill_trigger_regression"])
        for outer_id in map(str, prereg["validation"]["outer_blocks"])
    )
    gate["kill_trigger_regression"] = kill_regression
    gate["passes"] = bool(gate["passes"] and not kill_regression)
    return {
        "outer_results": results,
        "advantage_gate": gate,
    }, selected_configs


def _selected_issue448_representations(
    prereg: Mapping[str, object],
) -> dict[str, dict[str, str]]:
    issue448_result = json.loads(ISSUE448.read_text(encoding="utf-8"))
    retained = set(map(str, prereg["frozen_handoff"]["retained_feature_families"]))
    selected: dict[str, dict[str, str]] = {}
    family_results = issue448_result.get("family_results", {})
    if not isinstance(family_results, Mapping):
        raise TypeError("issue427 issue448 family results are invalid")
    for family in sorted(retained):
        item = family_results.get(family)
        if not isinstance(item, Mapping):
            raise TypeError(f"issue427 missing retained issue448 family: {family}")
        for outer_row in item.get("nested_outer", []):
            if not isinstance(outer_row, Mapping):
                continue
            outer = outer_row.get("outer_block", {})
            if not isinstance(outer, Mapping):
                continue
            outer_id = str(outer.get("id", ""))
            representation = str(outer_row.get("selected_representation", ""))
            if outer_id and representation:
                selected.setdefault(outer_id, {})[family] = representation
    return selected


def _feature_set_family_map() -> dict[str, str]:
    return {
        "market_plus_positioning": "market_structure.positioning",
        "market_plus_oscillator_mean_reversion": "ta.oscillator_mean_reversion",
        "market_plus_range_breakout": "ta.range_breakout",
        "market_plus_trend_strength": "ta.trend_strength",
        "market_plus_volume_confirmation": "ta.volume_confirmation",
    }


def _score_stable_features(
    *,
    prereg: Mapping[str, object],
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, object],
    risk: object,
    costs: object,
    minimum_training_rows: int,
    selected_configs: Mapping[str, Mapping[str, object]],
    trials: list[dict[str, object]],
) -> dict[str, object]:
    outers = _outer_blocks(cfg)
    selected_reps = _selected_issue448_representations(prereg)
    feature_cfg = prereg["feature_search"]
    eligible_outers = list(map(str, feature_cfg["eligible_outer_blocks"]))
    family_map = _feature_set_family_map()
    stable_families = list(map(str, prereg["frozen_handoff"]["retained_feature_families"]))
    result_sets: dict[str, object] = {}

    for set_name in map(str, feature_cfg["candidate_sets"]):
        if set_name == "market_control":
            result_sets[set_name] = {
                "disposition": "MATCHED_BASELINE",
                "outer_results": {},
                "advantage_gate": {
                    "passes": False,
                    "mean_outer_monthly_net_return_delta": 0.0,
                    "nonnegative_outer_fraction": 1.0,
                    "outer_deltas": [0.0 for _ in eligible_outers],
                    "kill_trigger_regression": False,
                },
            }
            continue
        if set_name == "market_plus_all_stable_retained":
            required_families = stable_families
        else:
            family = family_map.get(set_name)
            if family is None:
                raise RuntimeError(f"issue427 unknown feature set: {set_name}")
            required_families = [family]

        outer_results: dict[str, object] = {}
        deltas: list[float] = []
        kill_regression = False
        for outer_id in eligible_outers:
            reps = selected_reps.get(outer_id, {})
            missing = [family for family in required_families if family not in reps]
            if missing:
                outer_results[outer_id] = {
                    "status": "HOLD_MISSING_INHERITED_REPRESENTATION",
                    "missing_families": missing,
                }
                trials.append(
                    _trial(
                        "stable_feature_outer_hold",
                        {
                            "feature_set": set_name,
                            "outer_block_id": outer_id,
                            "missing_families": missing,
                        },
                    )
                )
                continue
            columns = [reps[family] for family in required_families]
            config = dict(selected_configs[outer_id])
            try:
                scored = opt.evaluate_issue427_feature_set(
                    session_path=sessions,
                    features=features,
                    config=config,
                    candidate_columns=columns,
                    blocks=[outers[outer_id]],
                    phase2_cfg=cfg,
                    risk=risk,
                    costs=costs,
                    minimum_training_rows=minimum_training_rows,
                )
                delta = float(scored["ablation"]["mean_monthly_net_return_delta"])
                current_kill_regression = _kill_triggered(scored) and not _kill_triggered(
                    scored["matched_control"]
                )
                deltas.append(delta)
                kill_regression = kill_regression or current_kill_regression
                outer_results[outer_id] = {
                    "status": "complete",
                    "candidate_columns": columns,
                    "result": scored,
                    "kill_trigger_regression": current_kill_regression,
                }
                trials.append(
                    _trial(
                        "stable_feature_outer_evaluation",
                        {
                            "feature_set": set_name,
                            "outer_block_id": outer_id,
                            "candidate_columns": columns,
                            "mean_monthly_net_return_delta": delta,
                            "monthly_score": scored["monthly_score"],
                            "matched_control_score": scored["matched_control"]["monthly_score"],
                            "kill_trigger_regression": current_kill_regression,
                        },
                    )
                )
            except (
                opt.Issue427OptimizationError,
                v2.V2OptimizationError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                outer_results[outer_id] = {
                    "status": "failed",
                    "candidate_columns": columns,
                    "reason": str(exc),
                }
                trials.append(
                    _trial(
                        "stable_feature_outer_failed",
                        {
                            "feature_set": set_name,
                            "outer_block_id": outer_id,
                            "candidate_columns": columns,
                            "reason": str(exc),
                        },
                    )
                )

        gate_cfg = prereg["promotion_gates"]["development_advantage"]
        gate = opt.evaluate_issue427_advantage(
            deltas,
            required_nonnegative_fraction=float(gate_cfg["nonnegative_outer_fraction_gte"]),
        )
        complete_support = len(deltas) == len(eligible_outers)
        gate["complete_outer_support"] = complete_support
        gate["kill_trigger_regression"] = kill_regression
        gate["passes"] = bool(
            gate["passes"] and complete_support and not kill_regression
        )
        result_sets[set_name] = {
            "disposition": (
                "DEVELOPMENT_ADVANTAGE"
                if gate["passes"]
                else "HOLD_NO_ROBUST_DEVELOPMENT_ADVANTAGE"
            ),
            "required_families": required_families,
            "outer_results": outer_results,
            "advantage_gate": gate,
        }

    return {
        "candidate_sets": result_sets,
        "development_advantages": sorted(
            name
            for name, item in result_sets.items()
            if isinstance(item, Mapping)
            and item.get("disposition") == "DEVELOPMENT_ADVANTAGE"
        ),
    }


def _volatility_feature_set_map() -> dict[str, list[str]]:
    return {
        "ewma": ["feature_issue427_ewma_vol"],
        "har": ["feature_issue427_har_rv"],
        "garch_family": ["feature_issue427_garch_vol"],
        "jump_intensity": ["feature_issue427_jump_intensity"],
        "tail_loss_state": ["feature_issue427_tail_loss_state"],
        "vol_of_vol": ["feature_issue427_vol_of_vol"],
        "all_volatility_tail": [
            "feature_issue427_ewma_vol",
            "feature_issue427_har_rv",
            "feature_issue427_garch_vol",
            "feature_issue427_jump_intensity",
            "feature_issue427_tail_loss_state",
            "feature_issue427_vol_of_vol",
        ],
    }


def _score_volatility_tail(
    *,
    prereg: Mapping[str, object],
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, object],
    risk: object,
    costs: object,
    minimum_training_rows: int,
    selected_configs: Mapping[str, Mapping[str, object]],
    trials: list[dict[str, object]],
) -> dict[str, object]:
    states = opt.build_issue427_volatility_tail_features(features)
    enriched = features.merge(
        states,
        on=["trade_date", "available_at"],
        how="left",
        validate="one_to_one",
    )
    outers = _outer_blocks(cfg)
    outer_ids = list(map(str, prereg["validation"]["outer_blocks"]))
    candidate_sets = _volatility_feature_set_map()
    budget = int(prereg["budgets"]["volatility_tail_configs_max"])
    if len(candidate_sets) * len(outer_ids) > budget:
        raise RuntimeError("issue427 volatility/tail budget exceeded")
    result_sets: dict[str, object] = {}

    for set_name, columns in candidate_sets.items():
        outer_results: dict[str, object] = {}
        deltas: list[float] = []
        kill_regression = False
        for outer_id in outer_ids:
            config = dict(selected_configs[outer_id])
            try:
                scored = opt.evaluate_issue427_feature_set(
                    session_path=sessions,
                    features=enriched,
                    config=config,
                    candidate_columns=columns,
                    blocks=[outers[outer_id]],
                    phase2_cfg=cfg,
                    risk=risk,
                    costs=costs,
                    minimum_training_rows=minimum_training_rows,
                )
                delta = float(scored["ablation"]["mean_monthly_net_return_delta"])
                regression = _kill_triggered(scored) and not _kill_triggered(
                    scored["matched_control"]
                )
                deltas.append(delta)
                kill_regression = kill_regression or regression
                outer_results[outer_id] = {
                    "status": "complete",
                    "candidate_columns": columns,
                    "result": scored,
                    "kill_trigger_regression": regression,
                }
                trials.append(
                    _trial(
                        "volatility_tail_outer_evaluation",
                        {
                            "feature_set": set_name,
                            "outer_block_id": outer_id,
                            "candidate_columns": columns,
                            "mean_monthly_net_return_delta": delta,
                            "kill_trigger_regression": regression,
                        },
                    )
                )
            except (
                opt.Issue427OptimizationError,
                v2.V2OptimizationError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                outer_results[outer_id] = {
                    "status": "failed",
                    "candidate_columns": columns,
                    "reason": str(exc),
                }
                trials.append(
                    _trial(
                        "volatility_tail_outer_failed",
                        {
                            "feature_set": set_name,
                            "outer_block_id": outer_id,
                            "reason": str(exc),
                        },
                    )
                )

        gate_cfg = prereg["promotion_gates"]["development_advantage"]
        gate = opt.evaluate_issue427_advantage(
            deltas,
            required_nonnegative_fraction=float(gate_cfg["nonnegative_outer_fraction_gte"]),
        )
        gate["complete_outer_support"] = len(deltas) == len(outer_ids)
        gate["kill_trigger_regression"] = kill_regression
        gate["passes"] = bool(
            gate["passes"] and gate["complete_outer_support"] and not kill_regression
        )
        result_sets[set_name] = {
            "disposition": (
                "DEVELOPMENT_ADVANTAGE"
                if gate["passes"]
                else "HOLD_NO_ROBUST_DEVELOPMENT_ADVANTAGE"
            ),
            "outer_results": outer_results,
            "advantage_gate": gate,
        }

    return {
        "candidate_sets": result_sets,
        "development_advantages": sorted(
            name
            for name, item in result_sets.items()
            if isinstance(item, Mapping)
            and item.get("disposition") == "DEVELOPMENT_ADVANTAGE"
        ),
        "role_dispositions": {
            "direction": "SCORED_MATCHED_FEATURE_ABLATION",
            "trade_admission": "HANDOFF_428_NO_FROZEN_POLICY_SEMANTICS_IN_427",
            "confidence": "HANDOFF_428_NO_FROZEN_POLICY_SEMANTICS_IN_427",
            "risk_control": "HANDOFF_430_NO_FROZEN_RISK_MAPPING_IN_427",
        },
    }


def score_core() -> dict[str, object]:
    prereg, features, sessions, families, preflight_report = _load_scoring_inputs()
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    issue425_plan = json.loads(ISSUE425_SEARCH_PLAN.read_text(encoding="utf-8"))
    minimum_training_rows = int(issue425_plan["validation"]["minimum_training_rows"])
    trials: list[dict[str, object]] = []

    model_stage, selected_configs = _score_core_models(
        prereg=prereg,
        features=features,
        sessions=sessions,
        cfg=cfg,
        risk=risk,
        costs=costs,
        minimum_training_rows=minimum_training_rows,
        trials=trials,
    )
    feature_stage = _score_stable_features(
        prereg=prereg,
        features=features,
        sessions=sessions,
        cfg=cfg,
        risk=risk,
        costs=costs,
        minimum_training_rows=minimum_training_rows,
        selected_configs=selected_configs,
        trials=trials,
    )
    advantages: list[dict[str, object]] = []
    if model_stage["advantage_gate"]["passes"]:
        advantages.append(
            {
                "type": "core_model",
                "id": "nested_core_model_optimization",
                "gate": model_stage["advantage_gate"],
            }
        )
    for name in feature_stage["development_advantages"]:
        item = feature_stage["candidate_sets"][name]
        advantages.append(
            {
                "type": "stable_feature_set",
                "id": name,
                "gate": item["advantage_gate"],
            }
        )

    LEDGER.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in trials),
        encoding="utf-8",
        newline="\n",
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 427,
        "status": "core_scoring_complete",
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "prereg_sha256": sha256_file(PREREG),
        "preflight_sha256": preflight_report["preflight_sha256"],
        "model_stage": model_stage,
        "feature_stage": feature_stage,
        "advantage_found": bool(advantages),
        "development_advantages": advantages,
        "trial_count": len(trials),
        "trial_ledger_sha256": sha256_file(LEDGER),
        "retained_family_count": len(prereg["frozen_handoff"]["retained_feature_families"]),
        "source_family_count": len(families),
        "runner_sha256": sha256_file(Path(__file__)),
        "model_code_sha256": sha256_file(REPO / "src/commodity/v2_model_optimization.py"),
        "v2_code_sha256": sha256_file(REPO / "src/commodity/v2_optimization.py"),
    }
    result["result_sha256"] = stable_sha(result)
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _selected_configs_from_core(core: Mapping[str, object]) -> dict[str, dict[str, object]]:
    model_stage = core.get("model_stage")
    if not isinstance(model_stage, Mapping):
        raise TypeError("issue427 core result lacks model stage")
    outer_results = model_stage.get("outer_results")
    if not isinstance(outer_results, Mapping):
        raise TypeError("issue427 core result lacks outer model results")
    selected: dict[str, dict[str, object]] = {}
    for outer_id, raw in outer_results.items():
        if not isinstance(raw, Mapping) or not isinstance(raw.get("selected_config"), Mapping):
            raise TypeError(f"issue427 core result lacks selected config: {outer_id}")
        selected[str(outer_id)] = dict(raw["selected_config"])
    return selected


def _open_interest_evidence(prereg: Mapping[str, object]) -> dict[str, object]:
    issue448 = json.loads(ISSUE448.read_text(encoding="utf-8"))
    family_results = issue448.get("family_results")
    if not isinstance(family_results, Mapping):
        raise TypeError("issue427 issue448 family results are invalid")
    item = family_results.get("market_structure.open_interest")
    if not isinstance(item, Mapping):
        raise TypeError("issue427 issue448 OI result is missing")
    rows: list[dict[str, object]] = []
    for raw in item.get("nested_outer", []):
        if not isinstance(raw, Mapping):
            continue
        outer = raw.get("outer_block")
        result = raw.get("outer_result")
        if not isinstance(outer, Mapping) or not isinstance(result, Mapping):
            continue
        ablation = result.get("ablation")
        if not isinstance(ablation, Mapping):
            continue
        rows.append(
            {
                "outer_block_id": str(outer.get("id")),
                "representation": str(raw.get("selected_representation")),
                "mean_monthly_net_return_delta": float(
                    ablation["mean_monthly_net_return_delta"]
                ),
            }
        )
    eligible = list(map(str, prereg["open_interest_lane"]["eligible_outer_blocks"]))
    by_id = {str(row["outer_block_id"]): row for row in rows}
    if sorted(by_id) != sorted(eligible):
        raise RuntimeError("issue427 inherited OI outer support changed")
    deltas = [float(by_id[outer_id]["mean_monthly_net_return_delta"]) for outer_id in eligible]
    gate_cfg = prereg["promotion_gates"]["development_advantage"]
    gate = opt.evaluate_issue427_advantage(
        deltas,
        required_nonnegative_fraction=float(gate_cfg["nonnegative_outer_fraction_gte"]),
    )
    gate["complete_outer_support"] = True
    gate["kill_trigger_regression"] = False
    return {
        "source_issue": 448,
        "source_result_sha256": sha256_file(ISSUE448),
        "outer_results": [by_id[outer_id] for outer_id in eligible],
        "advantage_gate": gate,
        "disposition": (
            "DEVELOPMENT_ADVANTAGE" if gate["passes"] else "CONDITIONAL_ONLY_HANDOFF_428"
        ),
        "role_dispositions": {
            "representation_feature": "INHERITED_MATCHED_EVIDENCE",
            "trade_admission": "HANDOFF_428_NO_FROZEN_POLICY_SEMANTICS_IN_427",
            "confidence": "HANDOFF_428_NO_FROZEN_POLICY_SEMANTICS_IN_427",
            "veto": "HANDOFF_428_NO_FROZEN_POLICY_SEMANTICS_IN_427",
        },
    }


def _foundation_context_evidence() -> dict[str, object]:
    phase4 = json.loads(PHASE4_AUDIT.read_text(encoding="utf-8"))
    phase5 = json.loads(PHASE5_RESULT.read_text(encoding="utf-8"))
    four_way = phase4["four_way_whole_system_evaluation"]
    timesfm_eval = phase4["timesfm_whole_system_evaluation"]
    aggregates = four_way["aggregates"]
    baseline_pnl = float(aggregates["histgb-core-v1"]["net_pnl_usd"])
    phase5_ablations = phase5["diagnostics"]["remove_one_specialist_ablations"]
    context: dict[str, object] = {
        "phase4_audit_sha256": sha256_file(PHASE4_AUDIT),
        "phase5_result_sha256": sha256_file(PHASE5_RESULT),
        "aggregate_net_pnl_usd": {
            name: float(row["net_pnl_usd"]) for name, row in aggregates.items()
        },
        "aggregate_incremental_vs_core_usd": {
            name: float(row["net_pnl_usd"]) - baseline_pnl
            for name, row in aggregates.items()
            if name != "histgb-core-v1"
        },
        "timesfm_probabilistic_calibration": timesfm_eval["probabilistic_calibration"],
        "phase5_remove_one_specialist_ablations": phase5_ablations,
        "phase5_outer_selections": phase5["outer_selections"],
        "protected_confirmation_accessed": False,
    }
    if CHRONOS_SUMMARY.exists():
        chronos = json.loads(CHRONOS_SUMMARY.read_text(encoding="utf-8"))
        context["chronos_comparator"] = {
            "sha256": sha256_file(CHRONOS_SUMMARY),
            "evidence_role": chronos["evidence_role"],
            "terminal_direction_accuracy": chronos["metrics"]["path"][
                "terminal_direction_accuracy"
            ],
            "disposition": "COMPARATOR_ONLY_EXISTING_DIAGNOSTIC_NOT_PROMOTION_EVIDENCE",
        }
    if MOIRAI_SUMMARY.exists():
        moirai = json.loads(MOIRAI_SUMMARY.read_text(encoding="utf-8"))
        context["moirai_research_only"] = {
            "sha256": sha256_file(MOIRAI_SUMMARY),
            "promotion_eligibility": moirai["promotion_eligibility"],
            "terminal_direction_accuracy": moirai["metrics"]["path"][
                "terminal_direction_accuracy"
            ],
            "disposition": "RESEARCH_ONLY_NONDEPLOYABLE",
        }
    return context


def _foundation_feature_frame(
    features: pd.DataFrame, sessions: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    phase4 = json.loads(PHASE4_AUDIT.read_text(encoding="utf-8"))
    if sha256_file(TIMESFM_FEATURES) != str(phase4["timesfm_generation"]["output_sha256"]):
        raise RuntimeError("issue427 TimesFM feature identity changed")
    if sha256_file(KRONOS_FEATURES) != str(phase4["kronos_generation"]["output_sha256"]):
        raise RuntimeError("issue427 Kronos feature identity changed")
    timesfm_columns = [
        "timesfm_point_return",
        "timesfm_q10_return",
        "timesfm_q90_return",
        "timesfm_interval_width",
    ]
    kronos_columns = ["kronos_close_return", "kronos_range_pct"]
    timesfm = pd.read_csv(TIMESFM_FEATURES)
    kronos = pd.read_csv(KRONOS_FEATURES)
    enriched = opt.merge_issue427_specialist_features(
        features, sessions, timesfm, timesfm_columns
    )
    kronos_enriched = opt.merge_issue427_specialist_features(
        features, sessions, kronos, kronos_columns
    )
    enriched = enriched.merge(
        kronos_enriched[["trade_date", "available_at", *kronos_columns]],
        on=["trade_date", "available_at"],
        how="left",
        validate="one_to_one",
    )
    if enriched[kronos_columns].isna().any().any():
        raise RuntimeError("issue427 Kronos feature coverage changed")
    return enriched, {
        "timesfm": timesfm_columns,
        "kronos": kronos_columns,
        "timesfm_kronos": [*timesfm_columns, *kronos_columns],
    }


def _score_foundation_features(
    *,
    prereg: Mapping[str, object],
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, object],
    risk: object,
    costs: object,
    minimum_training_rows: int,
    selected_configs: Mapping[str, Mapping[str, object]],
    trials: list[dict[str, object]],
) -> dict[str, object]:
    enriched, candidate_sets = _foundation_feature_frame(features, sessions)
    outer_ids = list(map(str, prereg["validation"]["outer_blocks"]))
    outers = _outer_blocks(cfg)
    budget = int(prereg["budgets"]["foundation_policy_configs_max"])
    if len(candidate_sets) * len(outer_ids) > budget:
        raise RuntimeError("issue427 foundation specialist budget exceeded")
    result_sets: dict[str, object] = {}

    for set_name, columns in candidate_sets.items():
        outer_results: dict[str, object] = {}
        deltas: list[float] = []
        kill_regression = False
        for outer_id in outer_ids:
            config = dict(selected_configs[outer_id])
            try:
                scored = opt.evaluate_issue427_feature_set(
                    session_path=sessions,
                    features=enriched,
                    config=config,
                    candidate_columns=columns,
                    blocks=[outers[outer_id]],
                    phase2_cfg=cfg,
                    risk=risk,
                    costs=costs,
                    minimum_training_rows=minimum_training_rows,
                )
                delta = float(scored["ablation"]["mean_monthly_net_return_delta"])
                regression = _kill_triggered(scored) and not _kill_triggered(
                    scored["matched_control"]
                )
                deltas.append(delta)
                kill_regression = kill_regression or regression
                outer_results[outer_id] = {
                    "status": "complete",
                    "candidate_columns": columns,
                    "result": scored,
                    "kill_trigger_regression": regression,
                }
                trials.append(
                    _trial(
                        "foundation_feature_outer_evaluation",
                        {
                            "feature_set": set_name,
                            "outer_block_id": outer_id,
                            "candidate_columns": columns,
                            "mean_monthly_net_return_delta": delta,
                            "kill_trigger_regression": regression,
                        },
                    )
                )
            except (
                opt.Issue427OptimizationError,
                v2.V2OptimizationError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                outer_results[outer_id] = {
                    "status": "failed",
                    "candidate_columns": columns,
                    "reason": str(exc),
                }
                trials.append(
                    _trial(
                        "foundation_feature_outer_failed",
                        {
                            "feature_set": set_name,
                            "outer_block_id": outer_id,
                            "reason": str(exc),
                        },
                    )
                )

        gate_cfg = prereg["promotion_gates"]["development_advantage"]
        gate = opt.evaluate_issue427_advantage(
            deltas,
            required_nonnegative_fraction=float(gate_cfg["nonnegative_outer_fraction_gte"]),
        )
        gate["complete_outer_support"] = len(deltas) == len(outer_ids)
        gate["kill_trigger_regression"] = kill_regression
        gate["passes"] = bool(
            gate["passes"] and gate["complete_outer_support"] and not kill_regression
        )
        result_sets[set_name] = {
            "disposition": (
                "DEVELOPMENT_ADVANTAGE"
                if gate["passes"]
                else "HOLD_NO_ROBUST_DEVELOPMENT_ADVANTAGE"
            ),
            "outer_results": outer_results,
            "advantage_gate": gate,
        }

    return {
        "candidate_sets": result_sets,
        "development_advantages": sorted(
            name
            for name, item in result_sets.items()
            if isinstance(item, Mapping)
            and item.get("disposition") == "DEVELOPMENT_ADVANTAGE"
        ),
        "context_and_role_evidence": _foundation_context_evidence(),
        "role_dispositions": {
            "representation_feature": "FRESH_ISSUE427_MATCHED_SCORING",
            "direct_forecast": "UPSTREAM_DEVELOPMENT_EVIDENCE_ONLY_NO_NEW_427_PROMOTION",
            "probabilistic_summary": "TIMESFM_CALIBRATION_REUSED",
            "path_summary_feature": "UPSTREAM_KRONOS_CHRONOS_DIAGNOSTIC_ONLY",
            "confidence_filter_veto": "PHASE5_ABLATIONS_REUSED_NO_INCREMENTAL_PROMOTION",
        },
    }


def score_specialists() -> dict[str, object]:
    prereg, features, sessions, _families, preflight_report = _load_scoring_inputs()
    if not RESULT.exists():
        raise RuntimeError("issue427 specialist scoring requires completed core result")
    core = json.loads(RESULT.read_text(encoding="utf-8"))
    expected_core = {
        "prereg_sha256": sha256_file(PREREG),
        "preflight_sha256": preflight_report["preflight_sha256"],
        "runner_sha256": sha256_file(Path(__file__)),
        "model_code_sha256": sha256_file(REPO / "src/commodity/v2_model_optimization.py"),
        "v2_code_sha256": sha256_file(REPO / "src/commodity/v2_optimization.py"),
    }
    for key, value in expected_core.items():
        if core.get(key) != value:
            raise RuntimeError(f"issue427 core result is stale: {key}")

    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    issue425_plan = json.loads(ISSUE425_SEARCH_PLAN.read_text(encoding="utf-8"))
    minimum_training_rows = int(issue425_plan["validation"]["minimum_training_rows"])
    selected_configs = _selected_configs_from_core(core)
    trials: list[dict[str, object]] = []

    volatility_tail = _score_volatility_tail(
        prereg=prereg,
        features=features,
        sessions=sessions,
        cfg=cfg,
        risk=risk,
        costs=costs,
        minimum_training_rows=minimum_training_rows,
        selected_configs=selected_configs,
        trials=trials,
    )
    foundation = _score_foundation_features(
        prereg=prereg,
        features=features,
        sessions=sessions,
        cfg=cfg,
        risk=risk,
        costs=costs,
        minimum_training_rows=minimum_training_rows,
        selected_configs=selected_configs,
        trials=trials,
    )
    open_interest = _open_interest_evidence(prereg)

    specialist_advantages: list[dict[str, object]] = []
    for name in volatility_tail["development_advantages"]:
        specialist_advantages.append(
            {
                "type": "volatility_tail_feature",
                "id": name,
                "gate": volatility_tail["candidate_sets"][name]["advantage_gate"],
            }
        )
    for name in foundation["development_advantages"]:
        specialist_advantages.append(
            {
                "type": "foundation_representation_feature",
                "id": name,
                "gate": foundation["candidate_sets"][name]["advantage_gate"],
            }
        )
    if open_interest["advantage_gate"]["passes"]:
        specialist_advantages.append(
            {
                "type": "open_interest_inherited",
                "id": "open_interest",
                "gate": open_interest["advantage_gate"],
            }
        )

    SPECIALIST_LEDGER.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in trials),
        encoding="utf-8",
        newline="\n",
    )
    issue448_result = json.loads(ISSUE448.read_text(encoding="utf-8"))
    phase5 = json.loads(PHASE5_RESULT.read_text(encoding="utf-8"))
    advantages = [*core.get("development_advantages", []), *specialist_advantages]
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 427,
        "status": "development_model_family_optimization_complete",
        "evidence_class": "development",
        "protected_confirmation_accessed": False,
        "prereg_sha256": sha256_file(PREREG),
        "preflight_sha256": preflight_report["preflight_sha256"],
        "core_result_file_sha256": sha256_file(RESULT),
        "core_result_sha256": core["result_sha256"],
        "core_trial_count": int(core["trial_count"]),
        "specialist_trial_count": len(trials),
        "new_issue427_trial_count": int(core["trial_count"]) + len(trials),
        "upstream_reused_trial_counts": {
            "issue448": int(issue448_result.get("trial_count", 0)),
            "phase5_policy_attempts": int(phase5["search"]["attempt_count"]),
        },
        "core": core,
        "open_interest_lane": open_interest,
        "volatility_tail_lane": volatility_tail,
        "foundation_lane": foundation,
        "advantage_found": bool(advantages),
        "development_advantages": advantages,
        "specialist_trial_ledger_sha256": sha256_file(SPECIALIST_LEDGER),
        "runner_sha256": sha256_file(Path(__file__)),
        "model_code_sha256": sha256_file(REPO / "src/commodity/v2_model_optimization.py"),
        "v2_code_sha256": sha256_file(REPO / "src/commodity/v2_optimization.py"),
    }
    result["result_sha256"] = stable_sha(result)
    FINAL_RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--preflight"
    if mode == "--preflight":
        report = preflight()
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        if report["status"] != "PASS":
            raise SystemExit(2)
        return
    if mode == "--score-core":
        result = score_core()
        summary = {
            "status": result["status"],
            "trial_count": result["trial_count"],
            "advantage_found": result["advantage_found"],
            "development_advantages": result["development_advantages"],
            "result_sha256": result["result_sha256"],
        }
    elif mode == "--score-specialists":
        result = score_specialists()
        summary = {
            "status": result["status"],
            "new_issue427_trial_count": result["new_issue427_trial_count"],
            "specialist_trial_count": result["specialist_trial_count"],
            "advantage_found": result["advantage_found"],
            "development_advantages": result["development_advantages"],
            "result_sha256": result["result_sha256"],
        }
    else:
        raise SystemExit(
            "usage: run_issue427_model_optimization.py "
            "[--preflight|--score-core|--score-specialists]"
        )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
