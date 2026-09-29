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
from commodity.miso import load_miso_window

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
RAW = REPO / "data/raw/issue455"
MARKET = RAW / "market-checkpoint"
WEATHER = RAW / "weather/gfs_rda_025"
MISO = RAW / "miso-reacquired"
PLAN = PROGRAMME / "issue455-successor-baseline-plan-v1.json"
SEARCH_PLAN = PROGRAMME / "issue426-search-plan-v1.json"
WEATHER_CONTRACT = PROGRAMME / "issue426-weather-feature-contract-v1.json"
WEATHER_RESULT = PROGRAMME / "issue455-successor-weather-baseline-v1.json"
POWER_RESULT = PROGRAMME / "issue452-result-v1.json"
MISO_SOURCE_AUDIT = PROGRAMME / "issue452-miso-capture-audit-v1.json"
MISO_VALIDATION = PROGRAMME / "issue455-miso-reacquisition-validation-v1.json"
LEDGER = PROGRAMME / "issue455-power-weather-trials-v1.jsonl"
RESULT = PROGRAMME / "issue455-power-weather-result-v1.json"

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def canonical_sha(payload: object) -> str:
    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def verify_current_miso_identity(miso_validation: Mapping[str, Any]) -> str:
    source_audit = load_json(MISO_SOURCE_AUDIT)
    expected_rows = source_audit.get("monthly_manifests")
    if not isinstance(expected_rows, list) or len(expected_rows) != 144:
        raise RuntimeError("#452 MISO source audit does not contain 144 monthly identities")
    observed: list[dict[str, str]] = []
    for row in expected_rows:
        if not isinstance(row, Mapping):
            raise TypeError("#452 MISO monthly identity is invalid")
        snapshot_id = str(row["snapshot_id"])
        month_dir = MISO / "miso_rf_al" / snapshot_id
        current = {
            "snapshot_id": snapshot_id,
            "archive_zip_sha256": sha256_file(month_dir / "archive.zip"),
            "power_features_sha256": sha256_file(month_dir / "power_features.csv"),
            "excluded_members_sha256": sha256_file(month_dir / "excluded_members.json"),
        }
        for key in ("archive_zip_sha256", "power_features_sha256", "excluded_members_sha256"):
            if current[key] != str(row[key]):
                raise RuntimeError(f"reacquired MISO {key} changed: {snapshot_id}")
        observed.append(current)
    identity = canonical_sha(observed)
    if identity != str(miso_validation.get("verified_month_hash_records_sha256", "")):
        raise RuntimeError("current MISO snapshot identity differs from tracked #455 validation")
    return identity


def validate_authority() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    plan = load_json(PLAN)
    weather_result = load_json(WEATHER_RESULT)
    miso_validation = load_json(MISO_VALIDATION)
    if weather_result.get("dataset_frozen") is not True:
        raise RuntimeError("successor weather result is not frozen")
    if weather_result.get("complete") is not True or weather_result.get("pit_safe") is not True:
        raise RuntimeError("successor weather result is not complete/PIT-safe")
    if weather_result.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("successor weather result crossed protected evidence")
    if weather_result.get("successor_plan_sha256") != sha256_file(PLAN):
        raise RuntimeError("successor weather result does not bind the current preregistration")
    fixed = plan.get("fixed_authorities")
    if not isinstance(fixed, Mapping):
        raise TypeError("issue455 preregistration fixed authority block is invalid")
    expected_paths = {
        "issue426_search_plan_sha256": SEARCH_PLAN,
        "issue426_weather_contract_sha256": WEATHER_CONTRACT,
        "issue452_power_result_sha256": POWER_RESULT,
        "issue452_miso_capture_audit_sha256": MISO_SOURCE_AUDIT,
    }
    for key, path in expected_paths.items():
        if sha256_file(path) != str(fixed.get(key, "")):
            raise RuntimeError(f"preregistered authority identity changed: {key}")
    if miso_validation.get("all_archive_and_feature_hashes_match_issue452") is not True:
        raise RuntimeError("reacquired MISO capture differs from #452 authority")
    audit = miso_validation.get("audit")
    if not isinstance(audit, Mapping) or audit.get("research_pit_ready") is not True:
        raise RuntimeError("reacquired MISO capture is not PIT-ready")
    if int(audit.get("usable_day_count", -1)) != 4374:
        raise RuntimeError("reacquired MISO usable-day count changed")
    if int(audit.get("excluded_member_count", -1)) != 9:
        raise RuntimeError("reacquired MISO exclusion count changed")
    if miso_validation.get("tracked_issue452_capture_audit_sha256") != sha256_file(MISO_SOURCE_AUDIT):
        raise RuntimeError("tracked #455 MISO validation no longer binds #452 source authority")
    current_miso_identity = verify_current_miso_identity(miso_validation)
    if plan.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue455 preregistration crossed protected evidence")
    return plan, weather_result, miso_validation, current_miso_identity


def build_merged_features(
    plan: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    search_plan = v2.load_issue426_search_plan(SEARCH_PLAN)
    weather_contract = v2.load_issue426_weather_feature_contract(WEATHER_CONTRACT)
    market = pd.read_parquet(MARKET / "features.parquet")
    session = pd.read_parquet(MARKET / "session-path.parquet")
    if sha256_file(MARKET / "features.parquet") != plan["fixed_authorities"]["market_features_sha256"]:
        raise RuntimeError("market feature identity changed")
    if sha256_file(MARKET / "session-path.parquet") != plan["fixed_authorities"]["market_session_path_sha256"]:
        raise RuntimeError("market session identity changed")
    weather = v2.build_issue426_weather_family_frame(
        WEATHER,
        availability_delay_minutes=int(weather_contract["availability_delay_minutes"]),
        degree_day_base_c=float(weather_contract["degree_day_base_c"]),
    )
    weather_cfg = next(item for item in search_plan["families"] if item["family"] == "weather")
    weather_values = [c for c in weather.columns if c not in {"observed_for", "available_at"}]
    merged = v2.merge_issue426_pit_family(
        market,
        weather,
        family="weather",
        value_columns=weather_values,
        max_staleness=pd.Timedelta(str(weather_cfg["max_staleness"])),
        latest_allowed_trade_date=str(search_plan["latest_allowed_trade_date"]),
    )
    miso_raw = load_miso_window(MISO, "2011-01-01", "2022-12-31")
    power = v2.build_issue452_miso_power_family_frame(miso_raw)
    power_values = ["issued_load_level", "issued_load_anomaly", "source_row_count"]
    power_cfg = next(item for item in search_plan["families"] if item["family"] == "power")
    merged = v2.merge_issue426_pit_family(
        merged,
        power,
        family="power",
        value_columns=power_values,
        max_staleness=pd.Timedelta(str(power_cfg["max_staleness"])),
        latest_allowed_trade_date=str(search_plan["latest_allowed_trade_date"]),
    )
    return session, merged, search_plan


def rebuild_power_selection_support(
    *,
    session: pd.DataFrame,
    merged: pd.DataFrame,
    cfg: Mapping[str, Any],
    inner_blocks: Sequence[Mapping[str, str]],
    power_result: Mapping[str, Any],
) -> list[dict[str, object]]:
    controls = v2.load_issue426_outer_matched_controls(PROGRAMME / "issue425-result-v1.json")
    minimum_training_rows = int(cfg["execution_contract"]["minimum_training_rows"])
    _, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    round_trip = float(costs.round_trip_usd) / float(
        cfg["execution_contract"]["contract_multiplier_mmbtu"]
    )
    feature_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    origin_cache: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    rebuilt: list[dict[str, object]] = []
    source_rows = power_result["power_scoring"]["nested_outer"]
    for source in source_rows:
        outer = source["outer_block"]
        outer_id = str(outer["id"])
        eligible = v2._issue426_valid_inner_blocks(
            merged,
            family="power",
            inner_blocks=inner_blocks,
            outer_start=str(outer["start"]),
            minimum_training_rows=minimum_training_rows,
        )
        support = v2._issue426_representation_selection_support(
            session,
            merged,
            family="power",
            representations=["issued_load_level", "issued_load_anomaly"],
            base_config=controls[outer_id]["config"],
            inner_blocks=eligible,
            minimum_training_rows=minimum_training_rows,
            round_trip_per_mmbtu=round_trip,
            feature_cache=feature_cache,
            origin_cache=origin_cache,
        )
        common = v2._issue426_common_selection_blocks(eligible, support["block_ids"])
        selected = dict(source["search"]["selected_config"])
        if str(selected["issue426.representation"]) not in common["available_representations"]:
            raise RuntimeError(f"closed #452 power selection lost support: {outer_id}")
        rebuilt.append(
            {
                "outer_block": dict(outer),
                "common_selection_block_ids": [
                    str(block["id"]) for block in common["common_blocks"]
                ],
                "search": {
                    "selected_candidate_id": source["search"]["selected_candidate_id"],
                    "selected_config": selected,
                },
            }
        )
    return rebuilt


def score_interaction(
    plan: Mapping[str, Any],
    weather_result: Mapping[str, Any],
    miso_validation: Mapping[str, Any],
    current_miso_identity: str,
) -> dict[str, object]:
    session, merged, _ = build_merged_features(plan)
    cfg = load_json(REPO / "config/phase2_market_only.json")
    power_result = load_json(POWER_RESULT)
    inner_blocks = _inner_fold_specs(cfg)
    outer_blocks = list(cfg["validation"]["outer_blocks"])
    power_nested = rebuild_power_selection_support(
        session=session,
        merged=merged,
        cfg=cfg,
        inner_blocks=inner_blocks,
        power_result=power_result,
    )
    weather_nested = weather_result["nested_outer"]
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    costs = cost_profiles["base"]
    minimum_training_rows = int(cfg["execution_contract"]["minimum_training_rows"])
    ledger = v2.TrialLedger(LEDGER)
    trial_cache = ledger._records()
    dataset_id = v2._sha256_payload(
        {
            "issue": 455,
            "interaction": "power×successor_weather",
            "successor_weather_result_sha256": sha256_file(WEATHER_RESULT),
            "successor_weather_scoring_dataset_id": weather_result["scoring_dataset_id"],
            "issue452_power_result_sha256": sha256_file(POWER_RESULT),
            "miso_reacquisition_validation_sha256": sha256_file(MISO_VALIDATION),
            "current_miso_snapshot_identity_sha256": current_miso_identity,
            "market_features_sha256": plan["fixed_authorities"]["market_features_sha256"],
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
        return v2._issue455_evaluate_power_weather_trial(
            stage=stage,
            outer_block_id=outer_block_id,
            blocks=blocks,
            config=config,
            session_path=session,
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
        )

    interaction = v2.run_issue455_power_weather_outer_orchestration(
        outer_blocks=outer_blocks,
        inner_blocks=inner_blocks,
        power_nested_outer=power_nested,
        weather_nested_outer=weather_nested,
        successor_weather_validation=weather_result,
        evaluator=evaluator,
    )
    records = ledger._records()
    current_identity_trial_count = sum(
        1
        for record in records.values()
        if record.get("dataset_id") == dataset_id and record.get("code_id") == code_id
    )
    return {
        "schema_version": 1,
        "issue": 455,
        "programme_issue": 393,
        "status": "power_successor_weather_interaction_complete",
        "evidence_class": "development",
        "interaction": interaction,
        "dataset_id": dataset_id,
        "execution_code_id": code_id,
        "successor_plan_sha256": sha256_file(PLAN),
        "successor_weather_result_sha256": sha256_file(WEATHER_RESULT),
        "issue452_power_result_sha256": sha256_file(POWER_RESULT),
        "miso_reacquisition_validation_sha256": sha256_file(MISO_VALIDATION),
        "current_miso_snapshot_identity_sha256": current_miso_identity,
        "miso_archive_and_feature_hashes_match_issue452": bool(
            miso_validation["all_archive_and_feature_hashes_match_issue452"]
        ),
        "trial_count": len(records),
        "current_identity_trial_count": current_identity_trial_count,
        "trial_ledger_path": str(LEDGER.relative_to(REPO)).replace("\\", "/"),
        "trial_ledger_sha256": sha256_file(LEDGER) if LEDGER.is_file() else v2._sha256_payload([]),
        "protected_confirmation_accessed": False,
        "true_forward_accessed": False,
        "prospective_paper_accessed": False,
        "saxo_sim_accessed": False,
        "saxo_live_accessed": False,
        "claim_boundary": (
            "development-only incremental MISO power×successor-weather evidence; "
            "no protected confirmation, forward, paper, SIM, or LIVE evidence accessed"
        ),
    }


def main() -> int:
    plan, weather_result, miso_validation, current_miso_identity = validate_authority()
    result = score_interaction(plan, weather_result, miso_validation, current_miso_identity)
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    interaction = result["interaction"]
    print(
        json.dumps(
            {
                "result": str(RESULT),
                "trial_count": result["trial_count"],
                "disposition": interaction["disposition"],
                "candidate": interaction["nested_selection_score"],
                "matched_successor_weather": interaction["matched_control_score"],
                "delta": interaction["mean_monthly_net_return_delta"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
