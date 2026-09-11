from __future__ import annotations

import hashlib
import inspect
import json
import math
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.fundamentals_phase3 import (
    PHYSICAL_FEATURES,
    Phase3FundamentalsError,
    augment_market_features_with_physical,
    decide_phase3_survival,
    load_bhlr_physical_vintages,
)
from commodity.market_only_phase2 import (
    _build_segmented_decision_origins,
    _canonicalize_one_origin_per_fill,
    _frame_sha256,
    _load_inherited_risk_and_costs,
    _score_candidate_window,
    build_phase2_inputs,
    reconstruct_market_history,
    summarize_ledger,
)
from commodity.phase2_runtime import Phase2CheckpointStore, Phase2Telemetry, json_sha256


class Phase3RuntimeError(Phase3FundamentalsError):
    """Raised when the frozen Phase-3 execution contract cannot be satisfied."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3RuntimeError(f"invalid {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Phase3RuntimeError(f"{label} must be a JSON object")
    return payload


def _callable_sha256(items: list[object]) -> str:
    payload = {
        f"{getattr(item, '__module__', '')}.{getattr(item, '__qualname__', repr(item))}": inspect.getsource(item)
        for item in items
    }
    return json_sha256(payload)


def _candidate(phase2_cfg: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    matches = [item for item in phase2_cfg["candidates"] if item.get("id") == candidate_id]
    if len(matches) != 1:
        raise Phase3RuntimeError(f"frozen Phase-2 candidate is unavailable: {candidate_id}")
    return dict(matches[0])


def _assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-8):
        raise Phase3RuntimeError(f"{label} drifted: expected {expected}, observed {actual}")


def validate_phase3_authority(
    phase3_cfg: dict[str, Any], phase2_cfg: dict[str, Any], phase2_result: dict[str, Any]
) -> dict[str, Any]:
    boundary = phase3_cfg.get("evidence_boundary", {})
    if boundary.get("protected_confirmation_accessed") is not False:
        raise Phase3RuntimeError("protected confirmation must remain unopened in Phase 3")
    if str(boundary.get("last_allowed_trade_date")) != "2022-12-31":
        raise Phase3RuntimeError("Phase-3 development boundary must remain 2022-12-31")
    baseline = phase3_cfg["baseline"]
    frozen = phase2_result.get("baseline_freeze", {})
    if frozen.get("candidate_id") != baseline["candidate_id"]:
        raise Phase3RuntimeError("Phase-2 baseline candidate identity drifted")
    if frozen.get("freeze_sha256") != baseline["freeze_sha256"]:
        raise Phase3RuntimeError("Phase-2 baseline freeze identity drifted")
    phase2_features = phase2_result["evaluation"]["final_baseline"]["feature_columns"]
    configured = phase2_cfg["feature_sets"]["core"]
    if list(phase2_features) != list(configured):
        raise Phase3RuntimeError("Phase-2 baseline feature contract drifted")
    if set(PHYSICAL_FEATURES) != set(phase3_cfg["challenger"]["physical_features"]):
        raise Phase3RuntimeError("Phase-3 physical feature set drifted")
    return {
        "candidate_id": baseline["candidate_id"],
        "freeze_sha256": baseline["freeze_sha256"],
        "phase2_feature_columns": list(configured),
    }


def _score_blocks(
    origins: pd.DataFrame,
    session_path: pd.DataFrame,
    candidate: dict[str, Any],
    scoring_cfg: dict[str, Any],
    *,
    costs: Any,
    risk: Any,
) -> tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame]:
    scores: list[dict[str, Any]] = []
    forecast_parts: list[pd.DataFrame] = []
    ledger_parts: list[pd.DataFrame] = []
    for block in scoring_cfg["validation"]["outer_blocks"]:
        score, forecasts, ledger = _score_candidate_window(
            origins,
            session_path,
            candidate,
            scoring_cfg,
            costs,
            risk,
            start_date=str(block["start"]),
            end_date=str(block["end"]),
        )
        score["block_id"] = str(block["id"])
        scores.append(score)
        forecast_parts.append(forecasts.assign(outer_block_id=str(block["id"])))
        ledger_parts.append(ledger.assign(outer_block_id=str(block["id"])))
    return scores, pd.concat(forecast_parts, ignore_index=True), pd.concat(ledger_parts, ignore_index=True)


def _incremental_diagnostics(
    baseline: pd.DataFrame,
    challenger: pd.DataFrame,
    market_features: pd.DataFrame,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    keys = ["outer_block_id", "trade_date"]
    left = baseline[keys + ["net_pnl_usd"]].rename(columns={"net_pnl_usd": "baseline_net_pnl_usd"})
    right = challenger[keys + ["net_pnl_usd"]].rename(columns={"net_pnl_usd": "challenger_net_pnl_usd"})
    delta = left.merge(right, on=keys, how="outer", validate="one_to_one").fillna(
        {"baseline_net_pnl_usd": 0.0, "challenger_net_pnl_usd": 0.0}
    )
    delta["trade_date"] = pd.to_datetime(delta["trade_date"], utc=True)
    delta["incremental_net_pnl_usd"] = delta["challenger_net_pnl_usd"] - delta["baseline_net_pnl_usd"]
    delta["season"] = delta["trade_date"].dt.month.isin([11, 12, 1, 2, 3]).map({True: "winter_nov_mar", False: "non_winter"})
    feature_frame = market_features[["trade_date", "feature_vol_20"]].copy()
    feature_frame["trade_date"] = pd.to_datetime(feature_frame["trade_date"], utc=True)
    low = float(thresholds["low_upper"])
    mid = float(thresholds["mid_upper"])
    feature_frame["volatility_regime"] = "high"
    feature_frame.loc[feature_frame["feature_vol_20"] <= mid, "volatility_regime"] = "mid"
    feature_frame.loc[feature_frame["feature_vol_20"] <= low, "volatility_regime"] = "low"
    delta = delta.merge(feature_frame, on="trade_date", how="left", validate="many_to_one")
    return {
        "by_season_net_pnl_usd": {str(k): float(v) for k, v in delta.groupby("season")["incremental_net_pnl_usd"].sum().items()},
        "by_volatility_regime_net_pnl_usd": {str(k): float(v) for k, v in delta.groupby("volatility_regime")["incremental_net_pnl_usd"].sum().items()},
    }


def _physical_scoring_cfg(
    phase2_cfg: dict[str, Any], feature_columns: list[str]
) -> dict[str, Any]:
    cfg = json.loads(json.dumps(phase2_cfg))
    cfg["feature_sets"] = {"phase3": list(feature_columns)}
    cfg["candidates"] = []
    return cfg


def _phase3_candidate(phase3_cfg: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    challenger = phase3_cfg["challenger"]
    return {
        "id": candidate_id,
        "model": challenger["model"],
        "feature_set": "phase3",
        "parameters": dict(challenger["parameters"]),
        "simplicity_rank": 5,
    }


def _combined_summary(ledger: pd.DataFrame, capital: float) -> dict[str, Any]:
    summary = summarize_ledger(ledger, starting_capital_usd=capital)
    summary["sessions"] = len(ledger)
    summary["turnover_sides"] = int(ledger["execution_side_count"].sum())
    return summary


def run_phase3_fundamentals(
    phase3_config_path: Path,
    phase2_config_path: Path,
    phase2_result_path: Path,
    databento_root: Path,
    bhlr_root: Path,
    *,
    checkpoint_dir: Path | None = None,
    heartbeat_seconds: float = 30.0,
) -> dict[str, Any]:
    phase3_cfg = _load_json(phase3_config_path, "Phase-3 config")
    phase2_cfg = _load_json(phase2_config_path, "Phase-2 config")
    phase2_result = _load_json(phase2_result_path, "Phase-2 baseline result")
    authority = validate_phase3_authority(phase3_cfg, phase2_cfg, phase2_result)
    implementation_sha256 = _callable_sha256([
        run_phase3_fundamentals,
        validate_phase3_authority,
        load_bhlr_physical_vintages,
        augment_market_features_with_physical,
        _score_candidate_window,
        decide_phase3_survival,
    ])
    telemetry_path = None if checkpoint_dir is None else Path(checkpoint_dir) / "telemetry.jsonl"
    telemetry = Phase2Telemetry(telemetry_path, heartbeat_seconds=heartbeat_seconds, echo=True)
    store = None if checkpoint_dir is None else Phase2CheckpointStore(Path(checkpoint_dir), telemetry)
    lock = nullcontext() if store is None else store.run_lock()
    with lock:
        telemetry.event("phase3_run_started", authority=phase3_cfg["authority"], protected_confirmation_accessed=False)
        canonical, market, execution_bars, market_provenance = reconstruct_market_history(
            Path(databento_root), phase2_cfg, checkpoint_store=store, telemetry=telemetry
        )
        session_path, market_features = build_phase2_inputs(
            canonical, market, execution_bars, phase2_cfg, telemetry=telemetry
        )
        frozen = phase2_result["baseline_freeze"]
        if _frame_sha256(session_path) != frozen["session_path_sha256"]:
            raise Phase3RuntimeError("reconstructed Phase-2 session path identity drifted")
        if _frame_sha256(market_features) != frozen["features_sha256"]:
            raise Phase3RuntimeError("reconstructed Phase-2 feature identity drifted")
        physical, physical_provenance = load_bhlr_physical_vintages(Path(bhlr_root), phase3_cfg)
        augmented, pit_diagnostics = augment_market_features_with_physical(
            market_features,
            physical,
            cutoff=phase3_cfg["evidence_boundary"]["last_allowed_trade_date"],
        )
        if pit_diagnostics["coverage_fraction"] < 1.0:
            raise Phase3RuntimeError("Phase-3 physical block is incomplete over market origins")
        risk, cost_profiles = _load_inherited_risk_and_costs(phase2_cfg)
        costs = cost_profiles["base"]
        core = list(phase2_cfg["feature_sets"]["core"])
        baseline_origins, baseline_available = _build_segmented_decision_origins(
            session_path, market_features, horizon_sessions=int(phase2_cfg["execution_contract"]["horizon_sessions"])
        )
        baseline_origins, baseline_canonicalization = _canonicalize_one_origin_per_fill(baseline_origins)
        challenger_origins, challenger_available = _build_segmented_decision_origins(
            session_path, augmented, horizon_sessions=int(phase2_cfg["execution_contract"]["horizon_sessions"])
        )
        challenger_origins, challenger_canonicalization = _canonicalize_one_origin_per_fill(challenger_origins)
        if not set(core).issubset(baseline_available) or not {*core, *PHYSICAL_FEATURES}.issubset(challenger_available):
            raise Phase3RuntimeError("Phase-3 origins are missing frozen feature columns")
        baseline_candidate = _candidate(phase2_cfg, authority["candidate_id"])
        baseline_scores, _, baseline_ledger = _score_blocks(
            baseline_origins,
            session_path,
            baseline_candidate,
            phase2_cfg,
            costs=costs,
            risk=risk,
        )
        expected_blocks = phase3_cfg["baseline"]["expected_outer_net_pnl_usd"]
        for score in baseline_scores:
            block_id = str(score["block_id"])
            _assert_close(score["net_pnl_usd"], expected_blocks[block_id], f"baseline {block_id} P&L")
        baseline_aggregate = float(sum(float(row["net_pnl_usd"]) for row in baseline_scores))
        _assert_close(
            baseline_aggregate,
            phase3_cfg["baseline"]["expected_aggregate_net_pnl_usd"],
            "baseline aggregate P&L",
        )

        full_features = [*core, *PHYSICAL_FEATURES]
        challenger_cfg = _physical_scoring_cfg(phase2_cfg, full_features)
        challenger_candidate = _phase3_candidate(
            phase3_cfg, str(phase3_cfg["challenger"]["candidate_id"])
        )
        challenger_scores, challenger_forecasts, challenger_ledger = _score_blocks(
            challenger_origins,
            session_path,
            challenger_candidate,
            challenger_cfg,
            costs=costs,
            risk=risk,
        )
        baseline_summary = _combined_summary(baseline_ledger, risk.capital_usd)
        challenger_summary = _combined_summary(challenger_ledger, risk.capital_usd)
        block_deltas = [
            float(challenger["net_pnl_usd"]) - float(baseline["net_pnl_usd"])
            for baseline, challenger in zip(baseline_scores, challenger_scores, strict=True)
        ]
        survival = decide_phase3_survival(
            baseline_pnl=baseline_summary["net_pnl_usd"],
            baseline_drawdown=baseline_summary["max_drawdown_fraction"],
            challenger_pnl=challenger_summary["net_pnl_usd"],
            challenger_drawdown=challenger_summary["max_drawdown_fraction"],
            block_deltas=block_deltas,
        )
        remove_one: list[dict[str, Any]] = []
        for removed in PHYSICAL_FEATURES:
            diagnostic_features = [*core, *[item for item in PHYSICAL_FEATURES if item != removed]]
            diagnostic_cfg = _physical_scoring_cfg(phase2_cfg, diagnostic_features)
            diagnostic_candidate = _phase3_candidate(phase3_cfg, f"diagnostic-remove-{removed}")
            scores, _, ledger = _score_blocks(
                challenger_origins,
                session_path,
                diagnostic_candidate,
                diagnostic_cfg,
                costs=costs,
                risk=risk,
            )
            remove_one.append({
                "removed_feature": removed,
                "selection_role": "diagnostic_only",
                "aggregate": _combined_summary(ledger, risk.capital_usd),
                "outer_blocks": scores,
            })
        incremental = _incremental_diagnostics(
            baseline_ledger,
            challenger_ledger,
            market_features,
            phase3_cfg["baseline"]["volatility_regime_thresholds"],
        )
        block_comparison = []
        for baseline, challenger in zip(baseline_scores, challenger_scores, strict=True):
            block_comparison.append({
                "block_id": str(baseline["block_id"]),
                "baseline_net_pnl_usd": float(baseline["net_pnl_usd"]),
                "challenger_net_pnl_usd": float(challenger["net_pnl_usd"]),
                "incremental_net_pnl_usd": float(challenger["net_pnl_usd"] - baseline["net_pnl_usd"]),
                "latest_training_target_end": challenger["latest_training_target_end"],
            })
        result = {
            "schema_version": 1,
            "programme_id": phase3_cfg["programme_id"],
            "phase": 3,
            "authority": phase3_cfg["authority"],
            "protected_confirmation_accessed": False,
            "claim_boundary": phase3_cfg["claim_boundary"],
            "implementation_sha256": implementation_sha256,
            "phase2_baseline_identity": authority,
            "market_input_identity": {
                "session_path_sha256": _frame_sha256(session_path),
                "features_sha256": _frame_sha256(market_features),
                "source_provenance_sha256": market_provenance["provenance_sha256"],
            },
            "physical_source_provenance": physical_provenance,
            "pit_diagnostics": pit_diagnostics,
            "origin_canonicalization": {
                "baseline": baseline_canonicalization,
                "challenger": challenger_canonicalization,
            },
            "baseline_replay": {
                "aggregate": baseline_summary,
                "outer_blocks": baseline_scores,
                "identity_check": "passed",
            },
            "challenger": {
                "candidate": challenger_candidate,
                "feature_columns": full_features,
                "aggregate": challenger_summary,
                "outer_blocks": challenger_scores,
                "forecast_count": len(challenger_forecasts),
            },
            "incremental": {
                "aggregate_net_pnl_usd": float(
                    challenger_summary["net_pnl_usd"] - baseline_summary["net_pnl_usd"]
                ),
                "outer_blocks": block_comparison,
                **incremental,
            },
            "remove_one_sensitivity": remove_one,
            "disposition": survival,
        }
        result["result_sha256"] = json_sha256(result)
        if store is not None:
            store.save_json(
                "phase3/result",
                result,
                {
                    "phase3_config_sha256": hashlib.sha256(Path(phase3_config_path).read_bytes()).hexdigest(),
                    "phase2_freeze_sha256": authority["freeze_sha256"],
                    "implementation_sha256": implementation_sha256,
                },
            )
        telemetry.event(
            "phase3_run_completed",
            retained=survival["retained"],
            route=survival["route"],
            result_sha256=result["result_sha256"],
            protected_confirmation_accessed=False,
        )
        return result
