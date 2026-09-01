from __future__ import annotations

import argparse
import hashlib
import json
import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commodity.config import assumptions_config, data_config
from commodity.front_curve_feasibility import (
    ALPHA,
    CONFIRMATION_END,
    CONFIRMATION_START,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    ECONOMIC_MEPI_USD_PER_MMBTU,
    MIN_CONFIRMATION_ROWS,
    SCIENTIFIC_MEPI,
    TARGET_ID,
    TARGET_POWER,
    audit_development_feasibility,
    build_front_curve_target,
    fixed_confirmatory_design,
    target_contract,
)
from commodity.research_methodology import (
    register_inference_entry,
    verify_preregistration,
)

EXPERIMENT_ID = "exp-ng-front-curve-m1m2-change-v1"
EXPERIMENT_DIR = ROOT / "research" / "experiments" / EXPERIMENT_ID
EXPLORATORY_PATH = ROOT / "research" / "exploratory" / "front-curve-feasibility-271.json"
PROGRAMME_PATH = ROOT / "config" / "programme_evidence_map.json"
LEDGER_PATH = ROOT / "config" / "programme_inference_ledger.json"
SCAN_PATH = ROOT / "research" / "evidence-scans" / "programme-evidence-map-2026-08-29.json"
LITERATURE_PATH = ROOT / "research" / "literature" / "front-curve-271-conformance-v1.json"
RETRIEVED_AT = "2026-08-13T15:33:33.834014+00:00"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_dbn_decoder() -> None:
    try:
        import databento
        return
    except ImportError as exc:
        message = str(exc)
        if "Application Control policy has blocked this file" not in message or "_parquet" not in message:
            raise
    import pyarrow  # noqa: F401

    sys.modules["pyarrow.parquet"] = types.ModuleType("pyarrow.parquet")
    import databento  # noqa: F401


def _year_file(folder: Path, year: int, schema: str) -> Path:
    matches = sorted(
        path
        for path in folder.glob(f"*.{schema}.dbn.zst")
        if f"-{year}" in path.name
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {schema} DBN for {year}, found {len(matches)}")
    return matches[0]


def _decode_development(raw_root: Path, cache_csv: Path | None) -> pd.DataFrame:
    if cache_csv is not None and cache_csv.exists():
        frame = pd.read_csv(cache_csv)
        for column in ("trade_date", "expiration", "available_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        years = set(frame["trade_date"].dt.year.unique())
        if DEVELOPMENT_END.year in years and frame["trade_date"].min() >= DEVELOPMENT_START:
            return frame
        print("ignoring stale development cache that does not cover the frozen development window", flush=True)
    _prepare_dbn_decoder()
    from commodity.databento_futures_provider import (
        _decode_databento_canonical_statistics,
        _map_offline_statistics_symbols,
        decode_databento_dbn_file,
        normalize_databento_contract_history,
    )
    from commodity.market_data import validate_contract_history

    definition_dirs = list((raw_root / "definition").glob("*"))
    statistics_dirs = list((raw_root / "statistics").glob("*"))
    if len(definition_dirs) != 1 or len(statistics_dirs) != 1:
        raise RuntimeError("Databento full-history job directories are missing or ambiguous")

    identity_definitions: list[pd.DataFrame] = []
    outright_definitions: list[pd.DataFrame] = []
    statistics_frames: list[pd.DataFrame] = []
    for year in range(2010, 2023):
        definition = _year_file(definition_dirs[0], year, "definition")
        defs, _ = decode_databento_dbn_file(definition, expected_schema="definition")
        identity_definitions.append(
            defs[["instrument_id", "raw_symbol", "ts_event", "ts_recv"]].copy()
        )
        outright_definitions.append(
            defs.loc[
                defs["asset"].astype(str).eq("NG")
                & defs["instrument_class"].astype(str).eq("F"),
                ["instrument_id", "raw_symbol", "ts_event", "ts_recv", "asset", "instrument_class", "expiration", "exchange"],
            ].copy()
        )
        if 2015 <= year <= 2021:
            statistics = _year_file(statistics_dirs[0], year, "statistics")
            stats, _ = _decode_databento_canonical_statistics(statistics, dataset="GLBX.MDP3")
            statistics_frames.append(stats)
            print(f"decoded source year {year}: {len(stats)} canonical statistic records", flush=True)

    identity = pd.concat(identity_definitions, ignore_index=True)
    definitions = pd.concat(outright_definitions, ignore_index=True)
    statistics = pd.concat(statistics_frames, ignore_index=True)
    statistics = _map_offline_statistics_symbols(identity, statistics)
    combined, _ = normalize_databento_contract_history(
        definitions, statistics, RETRIEVED_AT, "NG"
    )
    combined = combined.loc[
        (combined["trade_date"] >= DEVELOPMENT_START)
        & (combined["trade_date"] <= DEVELOPMENT_END)
    ].copy()
    combined = combined.sort_values(["trade_date", "expiration", "contract_id"])
    combined = combined.drop_duplicates(["trade_date", "contract_id"], keep="last").reset_index(drop=True)
    combined = validate_contract_history(combined, data_config()["canonical_contract_schema"])
    if cache_csv is not None:
        cache_csv.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(cache_csv, index=False)
    print(f"continuous development canonical rows: {len(combined)}", flush=True)
    return combined


def _assert_source_authority() -> dict:
    config = data_config()
    source = config["sources"]["databento_henry_hub_probe"]
    checks = {
        "integrity_complete": source.get("integrity_status") == "complete",
        "canonical_market_source": source.get("canonical_market_source") is True,
        "backtest_evidence_allowed": source.get("backtest_evidence_allowed") is True,
        "licensing_rights_verified": source.get("licensing_rights_verified") is True,
        "dataset": source.get("dataset") == "GLBX.MDP3",
    }
    if not all(checks.values()):
        raise RuntimeError(f"Databento source authority is not research-ready: {checks}")
    return {"source_id": "databento_henry_hub_probe", "checks": checks}


def _build_prereg(feasibility: dict, design: dict, programme: dict) -> dict:
    rho = float(feasibility["dependence"]["preregistered_rho"])
    return {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "programme_id": programme["programme_id"],
        "research_line_id": "line-next-defensible-edge",
        "slice_id": "issue-271-front-curve-feasibility",
        "evidence_scan_ref": {
            "path": SCAN_PATH.relative_to(ROOT).as_posix(),
            "sha256": _sha256(SCAN_PATH),
            "scan_id": programme["current_scan_id"],
        },
        "literature_snapshot_ref": {
            "path": LITERATURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": _sha256(LITERATURE_PATH),
        },
        "orientation": {
            "big_picture_ref": "docs/big-picture.md",
            "where_this_fits": "Tests the first bounded curve/spread mechanism selected after repeated failure of generic one-session return model search.",
            "origin_refs": [programme["current_scan_id"], "issue-271", "issue-242-programme-synthesis"],
            "programme_question": "Can one roll-safe Henry Hub front-curve state produce a reproducible forecast edge large enough to matter relative to an unchanged-spread baseline?",
        },
        "parent_question": "Can frozen market-only information predict the next observed-session change in the roll-safe Henry Hub active-front/next calendar spread?",
        "uncertainty_reduced": "Whether front-curve change is a sufficiently powered complementary forecast target to retain in the Commodity research programme.",
        "outside_scope": [
            "live or simulated trading",
            "execution-policy changes",
            "alternative spread targets or horizons",
            "feature search",
            "hyperparameter tuning",
            "protected-window model selection or refitting",
        ],
        "mechanism": "Near-curve shape, recent same-pair spread movement, expiry distance, relative nearby-contract volume and seasonality may contain short-lived information about next-session front-spread adjustment while outright-return forecasting remains weak.",
        "hypotheses": {
            "h0": "Neither fixed challenger improves protected-window RMSE over the unchanged-spread baseline by the declared scientific and absolute MEPI under the frozen inference and robustness gates.",
            "h1": "At least one fixed challenger improves protected-window RMSE over the unchanged-spread baseline by both declared MEPIs and clears the frozen inference and robustness gates.",
        },
        "expectations": {
            "expected": _json(LITERATURE_PATH)["expected_observations"],
            "disconfirming": _json(LITERATURE_PATH)["disconfirming_observations"],
        },
        "post_result_triangulation": {"required": True, "independent_search_required": True},
        "mepi": {
            "scientific_mepi": {
                "formula": "absolute",
                "inputs": {"minimum_effect": SCIENTIFIC_MEPI},
                "value": SCIENTIFIC_MEPI,
                "units": "standardized_paired_loss_effect",
            },
            "economic_mepi": {
                "formula": "absolute",
                "inputs": {"minimum_effect": ECONOMIC_MEPI_USD_PER_MMBTU},
                "value": ECONOMIC_MEPI_USD_PER_MMBTU,
                "units": "absolute_RMSE_improvement_USD_per_MMBtu",
                "interpretation": "forecast relevance threshold only; not a trading-profit claim",
            },
        },
        "forecast": {
            "target": TARGET_ID,
            "horizon": "1_observed_session",
            "prediction_timestamp_semantics": target_contract()["prediction_time"],
            "target_timestamp_semantics": "next observed session for the identical active-front/next contract pair",
            "information_cutoff_semantics": target_contract()["information_cutoff"],
            "target_contract": target_contract(),
        },
        "datasets": [
            {
                "id": "databento-ng-full-history-v1-front-curve",
                "vintage": "GLBX-20260813-4LWDSMFX5T+GLBX-20260813-TVQMDDWSDJ",
                "split_id": "front-curve-development-through-2021-confirmation-2022-20260812-v1",
                "role": "development_and_protected_confirmation",
            }
        ],
        "dependence": {"method": "ar1", "raw_n": MIN_CONFIRMATION_ROWS, "parameters": {"rho": rho}},
        "power": {
            "method": "normal_effect_size",
            "alpha": ALPHA,
            "target_power": TARGET_POWER,
            "minimum_effect": SCIENTIFIC_MEPI,
        },
        "features": {
            "definition_id": design["features"]["definition_id"],
            "preprocessing_id": design["features"]["preprocessing_id"],
            "information_families": ["front_curve_state", "roll_state", "nearby_volume", "calendar_seasonality"],
            "columns": design["features"]["columns"],
            "missing_rule": design["features"]["missing_rule"],
        },
        "model": {
            "family": "fixed_baseline_ridge_histgb_ladder",
            "configuration_id": "front-curve-three-model-v1",
            "training_rules": design["training"] + "; exact configurations are embedded in this preregistration",
            "configurations": design["models"],
        },
        "evaluation": {
            "claim_scope": "forecasting",
            "market_implied_relevant": True,
            "primary_metric": "rmse",
            "secondary_metrics": ["mae", "direction_accuracy", "prediction_target_correlation"],
            "inference_procedure": design["evaluation"]["inference"],
            "programme_inference_procedure": "benjamini_hochberg",
            "statistical_family": "post-hardening-front-curve-v1",
            "candidate_family": ["ridge-fixed", "histgb-fixed"],
            "benchmarks": [
                {"id": "zero-change", "type": "market_implied", "interpretation": "current spread is the next-session forecast"}
            ],
            "promotion_rule": design["evaluation"]["promotion"],
            "kill_rule": design["evaluation"]["kill"],
        },
        "inference_ledger_entry_id": "inf-ng-front-curve-m1m2-change-v1",
        "sealed_window": {"sealed_window_id": None, "use": "none"},
        "coherence_triggers": [
            {"id": "implausibly_large_rmse_improvement", "direction": "unexpectedly_good", "metric": "absolute_rmse_improvement", "operator": "gte", "threshold": 0.05},
            {"id": "single_year_dominance", "direction": "both", "metric": "largest_year_share_of_total_rmse_improvement", "operator": "gte", "threshold": 0.50},
            {"id": "confirmation_row_shortfall", "direction": "unexpectedly_bad", "metric": "scored_confirmation_rows", "operator": "lt", "threshold": MIN_CONFIRMATION_ROWS},
        ],
        "outcome_logic": {
            "success": design["evaluation"]["promotion"],
            "failure": design["evaluation"]["kill"],
            "inconclusive": "fail closed if source identity, PIT checks, minimum rows, reproduction, leakage audit, or preregistration binding cannot be verified",
        },
        "permitted_human_dispositions": ["advance", "replicate", "refine", "branch", "hold", "stop"],
        "reproduction": {"mode": "logical", "tolerance": {"absolute": 1e-12, "relative": 1e-12}},
        "lineage": {"supersedes_prereg_sha256": None, "exploratory_ancestry": ["front-curve-feasibility-271"]},
    }


def _update_programme(programme: dict, feasibility: dict) -> dict:
    updated = json.loads(json.dumps(programme))
    line = next(item for item in updated["research_lines"] if item["research_line_id"] == "line-next-defensible-edge")
    status = str(feasibility["feasibility"])
    result = "front_curve_feasibility_go_preregistration_prepared" if status == "go" else "front_curve_feasibility_hold_before_preregistration"
    history = [item for item in line.get("experiment_history", []) if item.get("issue") != 271]
    history.append({"issue": 271, "result": result})
    line["experiment_history"] = history
    evidence_ref = EXPLORATORY_PATH.relative_to(ROOT).as_posix()
    evidence_refs = list(line.get("evidence_refs", []))
    if evidence_ref not in evidence_refs:
        evidence_refs.append(evidence_ref)
    line["evidence_refs"] = evidence_refs
    if status == "go":
        line["tested_role_target_horizon"] = "Selected for first post-hardening confirmation: roll-safe active-front/next Henry Hub spread change over one observed session, market-only front-curve information family."
        line["remaining_untested_roles"] = [item for item in line.get("remaining_untested_roles", []) if item != "curve/spread change"]
    else:
        line["tested_role_target_horizon"] = "Front-curve M1-M2 spread-change feasibility was tested development-only and held before preregistration; no protected confirmation was opened."
    updated["feasibility_map"] = [item for item in updated["feasibility_map"] if item.get("target") != TARGET_ID]
    updated["feasibility_map"].append(
        {
            "target": TARGET_ID,
            "horizon": "1_observed_session",
            "information_family": "front_curve_state",
            "scientific_mepi": SCIENTIFIC_MEPI,
            "economic_mepi": ECONOMIC_MEPI_USD_PER_MMBTU,
            "raw_information": feasibility["rows"]["scoreable_targets"],
            "effective_information_method": {"method": "ar1", "rho": feasibility["dependence"]["preregistered_rho"]},
            "detectable_effect": feasibility["power"]["detectable_effect"],
            "expected_snr": None,
            "costs": {"incremental_data_usd": 0.0, "source": "existing approved Databento full-history batch"},
            "market_implied_benchmark_required": True,
            "hold_reason": ", ".join(feasibility.get("hold_reasons", [])),
            "feasibility": status,
        }
    )
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--cache-csv", type=Path)
    args = parser.parse_args()

    source_authority = _assert_source_authority()
    canonical = _decode_development(args.raw_root, args.cache_csv)
    schema = data_config()["canonical_contract_schema"]
    roll_policy = assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]
    panel = build_front_curve_target(canonical, schema, roll_policy)
    feasibility = audit_development_feasibility(panel)
    design = fixed_confirmatory_design(feasibility) if feasibility["feasibility"] == "go" else None

    exploratory = {
        "schema_version": 1,
        "run_id": "front-curve-feasibility-271",
        "parent_question": "Is one roll-safe Henry Hub M1-M2 spread-change target feasible enough to consume confirmatory evidence?",
        "purpose": "Development-only nuisance, target-integrity, concentration, dependence and power audit before any protected outcome evaluation.",
        "inputs": {
            "source_authority": source_authority,
            "source_jobs": ["GLBX-20260813-4LWDSMFX5T", "GLBX-20260813-TVQMDDWSDJ"],
            "development_cutoff": DEVELOPMENT_END.date().isoformat(),
            "protected_window": {"start": CONFIRMATION_START.date().isoformat(), "end": CONFIRMATION_END.date().isoformat(), "inspected": False},
            "target_contract": target_contract(),
        },
        "change": "Issue #271 evaluates exactly one active-front/next spread-change target; no model was fit, tuned, selected, or scored on protected outcomes.",
        "result": {"feasibility": feasibility, "confirmatory_design": design},
        "promotion_decision": "promote" if design is not None else "continue",
        "promoted_to": EXPERIMENT_ID if design is not None else None,
    }
    _write_json(EXPLORATORY_PATH, exploratory)
    programme = _update_programme(_json(PROGRAMME_PATH), feasibility)

    _write_json(PROGRAMME_PATH, programme)
    if design is None:
        print(json.dumps({"status": "hold", "feasibility": feasibility}, indent=2, sort_keys=True))
        return 2

    prereg = _build_prereg(feasibility, design, programme)
    verification = verify_preregistration(prereg)
    ledger = register_inference_entry(_json(LEDGER_PATH), prereg)
    _write_json(LEDGER_PATH, ledger)
    _write_json(EXPERIMENT_DIR / "prereg.json", prereg)
    _write_json(EXPERIMENT_DIR / "feasibility.json", {"schema_version": 1, "issue": 271, "exploratory_ref": EXPLORATORY_PATH.relative_to(ROOT).as_posix(), "feasibility": feasibility, "design": design, "prereg_verification": verification})
    print(json.dumps({"status": "go", "experiment_id": EXPERIMENT_ID, "verification": verification, "feasibility": feasibility}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
