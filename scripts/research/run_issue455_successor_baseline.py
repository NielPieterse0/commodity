from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import commodity.v2_optimization as v2
from commodity.market_only_phase2 import (
    _inner_fold_specs,
    _load_inherited_risk_and_costs,
)

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
RAW = REPO / "data/raw/issue455"
MARKET = RAW / "market-checkpoint"
WEATHER = RAW / "weather/gfs_rda_025"
PLAN = PROGRAMME / "issue455-successor-baseline-plan-v1.json"
RESULT = PROGRAMME / "issue455-successor-weather-baseline-v1.json"
LEDGER = PROGRAMME / "issue455-successor-weather-trials-v1.jsonl"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_authority() -> dict[str, Any]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if plan.get("status") != "preregistered_before_successor_weather_scoring_and_power_weather_interaction":
        raise RuntimeError("issue455 successor baseline plan is not preregistered")
    freeze = plan["successor_weather_freeze"]
    if freeze.get("complete") is not True or int(freeze.get("snapshot_count", -1)) != 2908:
        raise RuntimeError("issue455 successor weather freeze is incomplete")
    manifest = PROGRAMME / "issue455-gfs-manifest-index-v1.json"
    if sha256_file(manifest) != str(freeze["manifest_artifact_sha256"]):
        raise RuntimeError("issue455 successor weather manifest artifact changed after freeze")
    if sha256_file(MARKET / "session-path.parquet") != plan["fixed_authorities"]["market_session_path_sha256"]:
        raise RuntimeError("issue455 market session identity changed")
    if sha256_file(MARKET / "features.parquet") != plan["fixed_authorities"]["market_features_sha256"]:
        raise RuntimeError("issue455 market feature identity changed")
    if plan.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue455 successor authority crossed protected evidence")
    return plan


def score_successor_weather(plan: Mapping[str, Any]) -> dict[str, object]:
    registry_path = REPO / "config/v2_variable_registry.json"
    search_plan_path = PROGRAMME / "issue426-search-plan-v1.json"
    optimization_plan_path = PROGRAMME / "issue426-optimization-plan-v3.json"
    phase2_config_path = REPO / "config/phase2_market_only.json"
    issue425_result_path = PROGRAMME / "issue425-result-v1.json"
    registry = v2.load_v2_registry(registry_path)
    search_plan = v2.load_issue426_search_plan(search_plan_path)
    v2.validate_issue426_search_plan(registry, search_plan)
    optimization_plan = v2.load_issue426_optimization_plan(optimization_plan_path)
    v2.validate_issue426_optimization_plan(registry, optimization_plan)
    weather_contract_path = PROGRAMME / "issue426-weather-feature-contract-v1.json"
    weather_contract = v2.load_issue426_weather_feature_contract(weather_contract_path)
    cfg = json.loads(phase2_config_path.read_text(encoding="utf-8"))
    session_path = pd.read_parquet(MARKET / "session-path.parquet")
    market_features = pd.read_parquet(MARKET / "features.parquet")
    cutoff = pd.Timestamp(str(search_plan["latest_allowed_trade_date"]), tz="UTC")
    if pd.to_datetime(session_path["trade_date"], utc=True).max().normalize() > cutoff:
        raise RuntimeError("issue455 session path crosses protected evidence")
    if pd.to_datetime(market_features["trade_date"], utc=True).max().normalize() > cutoff:
        raise RuntimeError("issue455 market features cross protected evidence")
    weather = v2.build_issue426_weather_family_frame(
        WEATHER,
        availability_delay_minutes=int(weather_contract["availability_delay_minutes"]),
        degree_day_base_c=float(weather_contract["degree_day_base_c"]),
    )
    weather_search = next(
        item for item in search_plan["families"] if item.get("family") == "weather"
    )
    value_columns = [c for c in weather.columns if c not in {"observed_for", "available_at"}]
    merged = v2.merge_issue426_pit_family(
        market_features,
        weather,
        family="weather",
        value_columns=value_columns,
        max_staleness=pd.Timedelta(str(weather_search["max_staleness"])),
        latest_allowed_trade_date=str(search_plan["latest_allowed_trade_date"]),
    )
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    minimum_training_rows = int(cfg["execution_contract"]["minimum_training_rows"])
    round_trip_per_mmbtu = float(costs.round_trip_usd) / float(
        cfg["execution_contract"]["contract_multiplier_mmbtu"]
    )
    inner_blocks = _inner_fold_specs(cfg)
    outer_blocks = list(cfg["validation"]["outer_blocks"])
    outer_controls = v2.load_issue426_outer_matched_controls(issue425_result_path)
    ledger = v2.TrialLedger(LEDGER)
    trial_cache = ledger._records()
    dataset_id = v2._sha256_payload(
        {
            "issue": 455,
            "family": "weather",
            "successor_weather_dataset_id": plan["successor_weather_freeze"]["dataset_id"],
            "successor_plan_sha256": sha256_file(PLAN),
            "session_path_sha256": plan["fixed_authorities"]["market_session_path_sha256"],
            "market_features_sha256": plan["fixed_authorities"]["market_features_sha256"],
            "search_plan_sha256": sha256_file(search_plan_path),
            "optimization_plan_sha256": sha256_file(optimization_plan_path),
            "weather_contract_sha256": sha256_file(weather_contract_path),
        }
    )
    code_id = sha256_file(Path(v2.__file__))
    feature_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    origin_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}

    def evaluator(
        stage: str,
        outer_block_id: str,
        blocks: Sequence[Mapping[str, str]],
        config: Mapping[str, object],
    ) -> dict[str, object]:
        return v2._issue426_evaluate_trial(
            stage=stage,
            outer_block_id=outer_block_id,
            blocks=blocks,
            config=config,
            session_path=session_path,
            features=merged,
            phase2_cfg=cfg,
            risk=risk,
            costs=costs,
            minimum_training_rows=minimum_training_rows,
            ledger=ledger,
            trial_cache=trial_cache,
            dataset_id=dataset_id,
            code_id=code_id,
            feature_cache=feature_cache,
            origin_cache=origin_cache,
            trial_issue=455,
        )

    nested_outer: list[dict[str, object]] = []
    skipped_outer: list[dict[str, object]] = []
    declared_representations = [str(v) for v in weather_search.get("representations", [])]
    for outer in outer_blocks:
        outer_id = str(outer["id"])
        if outer_id not in outer_controls:
            raise RuntimeError(f"issue455 missing outer control: {outer_id}")
        eligible_inner = v2._issue426_valid_inner_blocks(
            merged,
            family="weather",
            inner_blocks=inner_blocks,
            outer_start=str(outer["start"]),
            minimum_training_rows=minimum_training_rows,
        )
        if not eligible_inner:
            skipped_outer.append({
                "outer_block": dict(outer),
                "disposition": "HOLD_INSUFFICIENT_PRIOR_WEATHER_TRAINING",
            })
            continue
        support = v2._issue426_representation_selection_support(
            session_path,
            merged,
            family="weather",
            representations=declared_representations,
            base_config=outer_controls[outer_id]["config"],
            inner_blocks=eligible_inner,
            minimum_training_rows=minimum_training_rows,
            round_trip_per_mmbtu=round_trip_per_mmbtu,
            feature_cache=feature_cache,
            origin_cache=origin_cache,
        )
        common = v2._issue426_common_selection_blocks(eligible_inner, support["block_ids"])
        common_blocks = common["common_blocks"]
        available_representations = common["available_representations"]
        if not common_blocks or not available_representations:
            skipped_outer.append({
                "outer_block": dict(outer),
                "disposition": "HOLD_NO_COMMON_REPRESENTATION_SELECTION_EVIDENCE",
                "representation_support": support,
                "held_representations": common["held_representations"],
            })
            continue
        search = v2._search_issue426_outer(
            search_plan,
            optimization_plan,
            family="weather",
            outer_block=outer,
            base_config=outer_controls[outer_id]["config"],
            inner_blocks=common_blocks,
            evaluator=evaluator,
            representations_override=available_representations,
        )
        selected_config = dict(search["selected_config"])
        outer_result = evaluator("outer_evaluation", outer_id, [outer], selected_config)
        if outer_result.get("status", "complete") != "complete":
            skipped_outer.append({
                "outer_block": dict(outer),
                "disposition": "HOLD_SELECTED_OUTER_FAILED",
                "reason": outer_result.get("reason"),
            })
            continue
        nested_outer.append({
            "outer_block": dict(outer),
            "representation_support": support,
            "available_representations": available_representations,
            "held_representations": common["held_representations"],
            "common_selection_block_ids": [str(block["id"]) for block in common_blocks],
            "search": search,
            "selected_outer_result": outer_result,
            "issue425_outer_control": outer_controls[outer_id],
        })

    if nested_outer:
        candidate = v2._combine_issue425_score_summaries(
            [item["selected_outer_result"]["monthly_score"] for item in nested_outer]
        )
        control = v2._combine_issue425_score_summaries(
            [item["selected_outer_result"]["matched_control"]["monthly_score"] for item in nested_outer]
        )
        delta = float(candidate["mean_monthly_net_return"]) - float(
            control["mean_monthly_net_return"]
        )
        disposition = (
            "RETAIN_MATCHED_MARGINAL_VALUE_AND_REGISTERED_INTERACTIONS"
            if delta > 0.0
            else "HOLD_STANDALONE_NO_MATCHED_MARGINAL_VALUE_REGISTERED_INTERACTIONS_STILL_REQUIRED"
        )
    else:
        candidate = None
        control = None
        delta = None
        disposition = "HOLD_NO_SCORABLE_OUTER_BLOCK"
    records = ledger._records()
    return {
        "schema_version": 1,
        "issue": 455,
        "programme_issue": 393,
        "status": "successor_weather_baseline_complete",
        "evidence_class": "development",
        "dataset_frozen": True,
        "complete": True,
        "pit_safe": True,
        "protected_confirmation_accessed": False,
        "true_forward_accessed": False,
        "prospective_paper_accessed": False,
        "saxo_sim_accessed": False,
        "saxo_live_accessed": False,
        "successor_plan_sha256": sha256_file(PLAN),
        "successor_weather_dataset_id": plan["successor_weather_freeze"]["dataset_id"],
        "scoring_dataset_id": dataset_id,
        "execution_code_id": code_id,
        "weather_rows": len(weather),
        "nested_outer": nested_outer,
        "skipped_outer": skipped_outer,
        "nested_selection_score": candidate,
        "matched_control_score": control,
        "mean_monthly_net_return_delta": delta,
        "development_disposition": disposition,
        "trial_count": len(records),
        "trial_ledger_path": str(LEDGER.relative_to(REPO)).replace("\\", "/"),
        "trial_ledger_sha256": sha256_file(LEDGER) if LEDGER.is_file() else v2._sha256_payload([]),
        "claim_boundary": (
            "development-only successor weather baseline; no protected confirmation, "
            "forward, paper, SIM, or LIVE evidence accessed"
        ),
    }


def main() -> int:
    plan = load_authority()
    result = score_successor_weather(plan)
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "result": str(RESULT),
        "trial_count": result["trial_count"],
        "disposition": result["development_disposition"],
        "candidate": result["nested_selection_score"],
        "matched_control": result["matched_control_score"],
        "delta": result["mean_monthly_net_return_delta"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
