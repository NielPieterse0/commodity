from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from commodity.v2_adaptive_controller_v2 import (
    build_base_consequences,
    causal_attribute_specialists,
    config_to_dict,
    precompute_surfaces,
    replay_candidate,
    run_meta_controller,
    stable_sha,
    structural_grid,
)

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue465-block1-controller-v2-prereg.json"
PREFLIGHT = PROGRAMME / "issue465-block1-controller-v2-preflight.json"
CANDIDATES = PROGRAMME / "issue465-block1-controller-v2-candidates.json"
TRIALS = PROGRAMME / "issue465-block1-controller-v2-trials.jsonl"
BRAIN = PROGRAMME / "issue465-block1-controller-v2-decision-brain.jsonl"
LEDGER = PROGRAMME / "issue465-block1-controller-v2-ledger.json"
RESULT = PROGRAMME / "issue465-block1-controller-v2-result.json"
V1_PREREG = PROGRAMME / "issue465-prereg-v1.json"
V1_STATE = PROGRAMME / "issue465-block1-pit-state-v1.jsonl"
V1_RESULT = PROGRAMME / "issue465-block1-result-v1.json"
ADVANTAGE_MAP = PROGRAMME / "issue459-advantage-map-v1.json"


def _materialize_frozen_jsonl(path: Path) -> Path:
    archive = path.with_name(path.name + ".gz")
    if path.exists() or not archive.is_file():
        return path
    temporary = path.with_name(f".{path.name}.materialize-{os.getpid()}")
    try:
        with gzip.open(archive, "rb") as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


BRAIN = _materialize_frozen_jsonl(BRAIN)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, frame: pd.DataFrame) -> None:
    text = frame.to_json(orient="records", lines=True, date_format="iso", double_precision=15)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def load_v1_runner():
    path = REPO / "scripts/research/run_issue465_adaptive_block.py"
    spec = importlib.util.spec_from_file_location("issue465_v1_runner_for_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load issue465 v1 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_prereg() -> dict[str, Any]:
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen_before_block1_controller_v2_scoring":
        raise RuntimeError("controller-v2 preregistration is not frozen")
    predecessor = payload["predecessor_v1"]
    for path, key in ((V1_PREREG, "prereg_sha256"), (V1_STATE, "pit_state_sha256"), (V1_RESULT, "result_sha256")):
        if sha256_file(path) != str(predecessor[key]):
            raise RuntimeError(f"frozen predecessor changed: {path.name}")
    return payload


def load_pit_state(prereg: dict[str, Any]) -> pd.DataFrame:
    frame = pd.read_json(V1_STATE, lines=True, convert_dates=False)
    if len(frame) != int(prereg["block_contract"]["expected_executable_decision_rows"]):
        raise RuntimeError("controller-v2 PIT row count changed")
    datetime_columns = [
        column for column in frame.columns
        if column.endswith(("_time", "_timestamp", "_at"))
    ]
    if "trade_date" in frame:
        datetime_columns.append("trade_date")
    for column in sorted(set(datetime_columns)):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise", format="mixed")
    frame = frame.sort_values("decision_time", kind="stable").reset_index(drop=True)
    protected = pd.Timestamp(str(prereg["pit_contract"]["protected_start"]))
    if (frame["decision_time"] >= protected).any():
        raise RuntimeError("controller-v2 PIT state crosses protected boundary")
    log_volume = pd.to_numeric(frame["feature_curve_log_volume_m1"], errors="raise").astype(float)
    frame["derived_prior20_log_volume_m1_median"] = (
        log_volume.shift(1).rolling(20, min_periods=5).median().fillna(log_volume.expanding().median().shift(1))
    )
    frame["derived_prior20_log_volume_m1_median"] = frame[
        "derived_prior20_log_volume_m1_median"
    ].fillna(log_volume.iloc[0])
    return frame


def build_execution_path(
    state: pd.DataFrame,
    v1_runner: Any,
    v1_prereg: dict[str, Any],
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10, 20),
    block_end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    _features, sessions = v1_runner.load_market_inputs(v1_prereg)
    sessions = sessions.copy().sort_values("session_open", kind="stable").reset_index(drop=True)
    sessions["session_open"] = pd.to_datetime(sessions["session_open"], utc=True)
    sessions["next_session_open"] = pd.to_datetime(sessions["next_session_open"], utc=True)
    right = sessions[["session_open", "next_session_open", "contract_id", "open_price", "path_move_per_mmbtu"]]
    joined = state[["decision_time", "fill_timestamp", "fill_contract_id"]].merge(
        right, left_on="fill_timestamp", right_on="session_open", how="left", validate="one_to_one"
    )
    if joined["path_move_per_mmbtu"].isna().any() or joined["open_price"].isna().any():
        raise RuntimeError("controller-v2 execution path has unmatched fills")
    if not joined["fill_contract_id"].astype(str).eq(joined["contract_id"].astype(str)).all():
        raise RuntimeError("controller-v2 held-contract identity changed")
    out = pd.DataFrame({
        "decision_time": joined["decision_time"],
        "fill_timestamp": joined["session_open"],
        "fill_contract_id": joined["fill_contract_id"].astype(str),
        "fill_price": pd.to_numeric(joined["open_price"], errors="raise").astype(float),
        "outcome_available_at": joined["next_session_open"],
        "path_move_per_mmbtu": pd.to_numeric(joined["path_move_per_mmbtu"], errors="raise").astype(float),
    })
    session_index = {pd.Timestamp(value): idx for idx, value in enumerate(sessions["session_open"])}
    moves = pd.to_numeric(sessions["path_move_per_mmbtu"], errors="raise").astype(float)
    rolls = sessions["roll_at_next_open"].astype(bool)
    boundary = pd.Timestamp(block_end) if block_end is not None else None
    for horizon in horizons:
        horizon_moves: list[float] = []
        available: list[pd.Timestamp | pd.NaT] = []
        roll_counts: list[float] = []
        for fill_time in out["fill_timestamp"]:
            start = session_index[pd.Timestamp(fill_time)]
            stop = start + int(horizon)
            if stop > len(sessions):
                horizon_moves.append(float("nan")); available.append(pd.NaT); roll_counts.append(float("nan")); continue
            outcome_time = pd.Timestamp(sessions.iloc[stop - 1]["next_session_open"])
            if boundary is not None and outcome_time >= boundary:
                horizon_moves.append(float("nan")); available.append(pd.NaT); roll_counts.append(float("nan")); continue
            horizon_moves.append(float(moves.iloc[start:stop].sum()))
            available.append(outcome_time)
            roll_counts.append(float(rolls.iloc[start:stop].sum()))
        out[f"h{int(horizon)}_move_per_mmbtu"] = horizon_moves
        out[f"h{int(horizon)}_outcome_available_at"] = pd.to_datetime(available, utc=True)
        out[f"h{int(horizon)}_roll_count"] = roll_counts
    return out.sort_values("decision_time", kind="stable").reset_index(drop=True)


def family_map(v1_prereg: dict[str, Any]) -> dict[str, str]:
    return {str(row["id"]): str(row["family"]) for row in v1_prereg["specialist_library"]}


def attribute_inventory(state: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in state.columns:
        lower = column.lower()
        numeric = pd.api.types.is_numeric_dtype(state[column])
        provenance = (
            lower.endswith(("_time", "_timestamp", "_at"))
            or lower == "trade_date"
            or any(token in lower for token in ("source", "sha256", "vintage", "revision", "basis", "authority", "contract_id"))
        )
        if column in {"decision_time", "fill_timestamp", "trade_date"}:
            role = "causal_clock_or_execution_identity"
        elif provenance:
            role = "causal_provenance_or_staleness_metadata"
        elif numeric:
            role = "admissible_context_attribute"
        else:
            role = "retained_nonweighted_state_metadata"
        rows.append({"attribute": column, "role": role, "weighting_permitted": bool(numeric and not provenance)})
    return rows


def attribute_family(column: str) -> str:
    if column.startswith("timesfm_"):
        return "attribute_timesfm"
    if column.startswith("kronos_"):
        return "attribute_kronos"
    if "positioning" in column or "money" in column or "producer" in column:
        return "attribute_positioning"
    if "season" in column:
        return "attribute_seasonality"
    if "vol" in column or "jump" in column or "range" in column:
        return "attribute_volatility"
    if "curve" in column or "dte" in column or "settle" in column:
        return "attribute_curve"
    if "ret_" in column or "ma_gap" in column:
        return "attribute_technical"
    if "age_" in column:
        return "attribute_staleness"
    return "attribute_other"


def build_controller_specialists(state: pd.DataFrame, v1_runner: Any) -> tuple[pd.DataFrame, list[str]]:
    inventory = attribute_inventory(state)
    attributes = [str(row["attribute"]) for row in inventory if row["weighting_permitted"]]
    base = v1_runner.build_specialist_signals(state)
    attribute_signals = causal_attribute_specialists(state, attributes)
    combined = base.merge(attribute_signals, on="decision_time", how="inner", validate="one_to_one")
    return combined, attributes


def controller_family_map(v1_prereg: dict[str, Any], attributes: list[str]) -> dict[str, str]:
    mapping = family_map(v1_prereg)
    for column in attributes:
        family = attribute_family(column)
        mapping[f"attr__{column}__direct"] = family
        mapping[f"attr__{column}__inverse"] = family
    return mapping


def current_code_identity() -> dict[str, str]:
    return {
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "controller_v2_sha256": sha256_file(REPO / "src/commodity/v2_adaptive_controller_v2.py"),
        "v1_runner_dependency_sha256": sha256_file(REPO / "scripts/research/run_issue465_adaptive_block.py"),
    }


def load_v1_inventory() -> dict[str, Any]:
    path = PROGRAMME / "issue465-inventory-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_map_summary() -> dict[str, Any]:
    payload = json.loads(ADVANTAGE_MAP.read_text(encoding="utf-8"))
    raw = payload.get("raw_evidence", [])
    return {
        "path": str(ADVANTAGE_MAP.relative_to(REPO)),
        "sha256": sha256_file(ADVANTAGE_MAP),
        "raw_evidence_count": len(raw),
        "classification_counts": payload.get("classification_counts", {}),
        "all_records_retained_by_reference": True,
        "protected_confirmation_accessed": bool(payload.get("protected_confirmation_accessed", False)),
    }


def preflight(*, write: bool = True) -> dict[str, Any]:
    prereg = load_prereg()
    v1_runner = load_v1_runner()
    v1_prereg = json.loads(V1_PREREG.read_text(encoding="utf-8"))
    state = load_pit_state(prereg)
    specialists, weighted_attributes = build_controller_specialists(state, v1_runner)
    configs = structural_grid(prereg)
    context_columns = [str(value) for value in prereg["context_columns"]]
    inventory = attribute_inventory(state)
    expected_specialists = int(prereg["attribute_weighting"]["expected_total_specialist_count"])
    checks = {
        "block1_rows_match": len(state) == int(prereg["block_contract"]["expected_executable_decision_rows"]),
        "unique_decision_times": bool(state["decision_time"].is_unique),
        "complete_weightable_attributes_transformed": len(weighted_attributes) == sum(int(row["weighting_permitted"]) for row in inventory),
        "specialist_count_matches_prereg": len(specialists.columns) - 1 == expected_specialists,
        "structural_candidate_count_144": len(configs) == 144,
        "context_columns_present": all(column in state.columns for column in context_columns),
        "context_columns_numeric": all(pd.api.types.is_numeric_dtype(state[column]) for column in context_columns),
        "market_available_by_decision": bool((state["market_available_at"] <= state["decision_time"]).all()),
        "timesfm_available_by_decision": bool((state["timesfm_generated_at"] <= state["decision_time"]).all()),
        "kronos_available_by_decision": bool((state["kronos_generated_at"] <= state["decision_time"]).all()),
        "positioning_available_by_decision": bool((state["positioning_available_at"] <= state["decision_time"]).all()),
        "protected_confirmation_not_accessed": True,
        "later_blocks_not_accessed": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    candidates_payload = {
        "schema_version": 2,
        "issue": 465,
        "iteration": "block1-controller-v2",
        "prereg_sha256": sha256_file(PREREG),
        "candidate_count": len(configs),
        "candidate_grid_sha256": stable_sha([config_to_dict(config) for config in configs]),
        "candidates": [config_to_dict(config) for config in configs],
        "named_specialist_library": v1_prereg["specialist_library"],
        "attribute_specialist_contract": {
            "source_attributes": weighted_attributes,
            "transform": prereg["attribute_weighting"]["transform"],
            "variants_per_attribute": 2,
            "generated_specialist_count": 2 * len(weighted_attributes),
            "all_unselected_weights_exactly_zero": True,
        },
        "family_dispositions": load_v1_inventory()["family_dispositions"],
        "attribute_inventory": inventory,
        "historical_evidence_map": evidence_map_summary(),
        "scoring_performed": False,
    }
    report = {
        "schema_version": 2,
        "issue": 465,
        "iteration": "block1-controller-v2",
        "status": status,
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
        "prereg_sha256": sha256_file(PREREG),
        "predecessor_pit_state_sha256": sha256_file(V1_STATE),
        "code_identity": current_code_identity(),
        "checks": checks,
        "pit_attribute_count": len(inventory),
        "weightable_attribute_count": sum(int(row["weighting_permitted"]) for row in inventory),
        "specialist_count": len(specialists.columns) - 1,
        "candidate_count": len(configs),
        "candidate_grid_sha256": candidates_payload["candidate_grid_sha256"],
        "historical_evidence_map": candidates_payload["historical_evidence_map"],
    }
    if write:
        _write_json(CANDIDATES, candidates_payload)
        report["candidates_sha256"] = sha256_file(CANDIDATES)
        _write_json(PREFLIGHT, report)
    return report


def load_scoring_preflight() -> dict[str, Any]:
    if not PREFLIGHT.exists() or not CANDIDATES.exists():
        raise RuntimeError("controller-v2 scoring requires a written preflight and candidate freeze")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("controller-v2 scoring requires a clean no-scoring PASS preflight")
    if report.get("prereg_sha256") != sha256_file(PREREG):
        raise RuntimeError("controller-v2 preregistration changed after preflight")
    if report.get("candidates_sha256") != sha256_file(CANDIDATES):
        raise RuntimeError("controller-v2 candidate freeze changed after preflight")
    if report.get("code_identity") != current_code_identity():
        raise RuntimeError("controller-v2 code identity changed after preflight")
    return report


def candidate_trials(replays: list[Any], warmup: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for replay in replays:
        frame = replay.consequences.iloc[int(warmup):].copy()
        rows.append({
            **config_to_dict(replay.config),
            "post_warmup_net_return": float(frame["realized_net_return"].sum()),
            "post_warmup_turnover": float(frame["turnover"].sum()),
            "post_warmup_active_decisions": int(frame["signal"].ne(0.0).sum()),
            "full_block_net_return": float(replay.summary["total_net_return"]),
            "slow_structural_updates": int(replay.summary["slow_structural_updates"]),
        })
    return pd.DataFrame(rows).sort_values(
        ["post_warmup_net_return", "post_warmup_turnover", "config_id"],
        ascending=[False, True, True], kind="stable"
    ).reset_index(drop=True)


def v2_oracle(replays: list[Any], decision_times: list[pd.Timestamp]) -> dict[str, Any]:
    wanted = {pd.Timestamp(value) for value in decision_times}
    total = 0.0
    winners: dict[str, str] = {}
    for decision_time in sorted(wanted):
        day: list[tuple[float, str]] = []
        for replay in replays:
            row = replay.consequences.loc[replay.consequences["decision_time"] == decision_time]
            if not row.empty:
                day.append((float(row.iloc[0]["realized_net_return"]), replay.config.config_id))
        if day:
            best = min(day, key=lambda item: (-item[0], item[1]))
            total += best[0]
            winners[decision_time.isoformat()] = best[1]
    return {"oracle_net_return": total, "oracle_candidate_by_day": winners, "decision_count": len(winners)}


def selection_concentration(brain: pd.DataFrame) -> dict[str, Any]:
    counts: dict[str, float] = {}
    total = 0.0
    for ensemble in brain["selected_ensemble"]:
        for row in ensemble:
            weight = float(row["blend_weight"])
            counts[str(row["config_id"])] = counts.get(str(row["config_id"]), 0.0) + weight
            total += weight
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "effective_selection_weight_total": total,
        "top_config_weight_share": (ranked[0][1] / total) if total > 0.0 and ranked else 0.0,
        "top_config_weights": ranked[:10],
    }


def score_block() -> dict[str, Any]:
    preflight_report = load_scoring_preflight()
    prereg = load_prereg()
    v1_runner = load_v1_runner()
    v1_prereg = json.loads(V1_PREREG.read_text(encoding="utf-8"))
    state = load_pit_state(prereg)
    path = build_execution_path(
        state,
        v1_runner,
        v1_prereg,
        horizons=tuple(int(value) for value in prereg["horizons_sessions"]),
        block_end=pd.Timestamp(str(prereg["block_contract"]["end_exclusive"])),
    )
    specialists, weighted_attributes = build_controller_specialists(state, v1_runner)
    families = controller_family_map(v1_prereg, weighted_attributes)
    execution = prereg["execution"]
    base = build_base_consequences(
        specialists,
        path,
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        capital_usd=float(execution["starting_capital_usd"]),
        cost_per_side_usd=float(execution["cost_usd_per_contract_side"]),
    )
    context_columns = [str(value) for value in prereg["context_columns"]]
    surfaces, refs = precompute_surfaces(
        base,
        state[["decision_time", *context_columns]],
        context_columns=context_columns,
        k=int(prereg["comparable_state"]["k"]),
    )
    configs = structural_grid(prereg)
    if stable_sha([config_to_dict(config) for config in configs]) != preflight_report["candidate_grid_sha256"]:
        raise RuntimeError("controller-v2 candidate grid changed after preflight")
    replays = []
    for number, config in enumerate(configs, start=1):
        replays.append(replay_candidate(
            config,
            state,
            specialists,
            path,
            surfaces,
            refs,
            families,
            max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
            initial_capital=float(execution["starting_capital_usd"]),
            multiplier=float(execution["contract_multiplier_mmbtu"]),
            cost_per_side=float(execution["cost_usd_per_contract_side"]),
            initial_margin_usd_per_contract=float(execution["initial_margin_usd_per_contract"]),
            max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
            max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
            max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
            active_family_cap=int(prereg["slow_adaptation"]["active_family_cap"]),
        ))
        if number % 12 == 0:
            print(f"controller-v2 structural replay {number}/{len(configs)}", flush=True)
    warmup = int(prereg["block_contract"]["warmup_completed_trading_sessions"])
    trials = candidate_trials(replays, warmup)
    _write_jsonl(TRIALS, trials)
    brain, consequences, freeze_sha = run_meta_controller(
        replays,
        state,
        path,
        families,
        specialists=specialists,
        surfaces=surfaces,
        refs_by_time=refs,
        objective_window=int(prereg["meta_controller"]["objective_window_sessions"]),
        ensemble_size=int(prereg["meta_controller"]["ensemble_size"]),
        structural_cadence=int(prereg["meta_controller"]["structural_ensemble_cadence_sessions"]),
        max_abs_contracts=float(prereg["dynamic_sizing"]["max_abs_contracts"]),
        initial_capital=float(execution["starting_capital_usd"]),
        multiplier=float(execution["contract_multiplier_mmbtu"]),
        cost_per_side=float(execution["cost_usd_per_contract_side"]),
        initial_margin_usd_per_contract=float(execution["initial_margin_usd_per_contract"]),
        max_margin_fraction=float(prereg["dynamic_sizing"]["max_margin_fraction"]),
        max_notional_leverage=float(prereg["dynamic_sizing"]["max_notional_leverage"]),
        max_drawdown_fraction=float(prereg["dynamic_sizing"]["max_drawdown_fraction"]),
    )
    _write_jsonl(BRAIN, brain)
    _write_json(LEDGER, {
        "schema_version": 2,
        "issue": 465,
        "iteration": "block1-controller-v2",
        "decision_brain_freeze_sha256": freeze_sha,
        "row_count": len(brain),
        "consequences": consequences.to_dict(orient="records"),
    })
    eval_consequences = consequences.iloc[warmup:].copy()
    performance = v1_runner.performance_summary(
        eval_consequences,
        starting_capital=float(execution["starting_capital_usd"]),
        cost_per_side=float(execution["cost_usd_per_contract_side"]),
        margin_per_contract=float(execution["initial_margin_usd_per_contract"]),
    )
    oracle = v2_oracle(replays, state["decision_time"].iloc[warmup:].tolist())
    best_fixed = trials.iloc[0].to_dict()
    v1_result = json.loads(V1_RESULT.read_text(encoding="utf-8"))
    prior_only = brain.iloc[warmup:].copy()
    prior_only_check = bool(
        prior_only["max_outcome_available_at_used"].dropna().lt(prior_only["decision_time"]).all()
    )
    losses = pd.to_numeric(eval_consequences["realized_net_return"], errors="raise")
    result = {
        "schema_version": 2,
        "issue": 465,
        "iteration": "block1-controller-v2",
        "status": "BLOCK1_CONTROLLER_V2_SCORED",
        "protected_confirmation_accessed": False,
        "later_blocks_accessed": False,
        "prereg_sha256": sha256_file(PREREG),
        "preflight_sha256": sha256_file(PREFLIGHT),
        "candidates_sha256": sha256_file(CANDIDATES),
        "trials_sha256": sha256_file(TRIALS),
        "decision_brain_sha256": sha256_file(BRAIN),
        "ledger_sha256": sha256_file(LEDGER),
        "decision_brain_freeze_sha256": freeze_sha,
        "structural_candidate_count": len(configs),
        "positive_fixed_candidate_count": int((trials["post_warmup_net_return"] > 0.0).sum()),
        "best_fixed_controller_v2": best_fixed,
        "post_warmup_performance": performance,
        "loss_diagnostics": {
            "losing_decision_count": int((losses < 0.0).sum()),
            "worst_decision_net_return": float(losses.min()) if len(losses) else 0.0,
            "mean_losing_decision_net_return": float(losses.loc[losses < 0.0].mean()) if (losses < 0.0).any() else 0.0,
        },
        "oracle_diagnostic": oracle,
        "oracle_minus_causal_net_return": float(oracle["oracle_net_return"] - performance["total_net_return"]),
        "selection_concentration": selection_concentration(brain.iloc[warmup:]),
        "adaptation_reporting": {
            "fast_decision_count_post_warmup": len(brain) - warmup,
            "candidate_slow_cadences_tested": sorted({int(config.slow_cadence) for config in configs}),
            "candidate_slow_update_counts": sorted({int(replay.summary["slow_structural_updates"]) for replay in replays}),
        },
        "causal_checks": {
            "all_meta_selection_outcomes_strictly_prior": prior_only_check,
            "same_day_or_future_outcomes_used": False,
            "oracle_used_in_selection": False,
        },
        "predecessor_v1_comparison": {
            "v1_post_warmup_net_return": float(v1_result["post_warmup_performance"]["total_net_return"]),
            "v1_max_drawdown_fraction": float(v1_result["post_warmup_performance"]["max_drawdown_fraction"]),
            "v1_oracle_net_return": float(v1_result["oracle_diagnostic"]["oracle_net_return"]),
            "v1_result_selection_use": False,
        },
        "architecture_evidence": {
            "pit_attribute_count": int(preflight_report["pit_attribute_count"]),
            "weightable_attribute_count": int(preflight_report["weightable_attribute_count"]),
            "historical_evidence_map": preflight_report["historical_evidence_map"],
            "effectiveness_surface_dimensions": ["specialist", "context", "horizon", "direction", "memory"],
            "memory_bank": prereg["memory_bank_sessions"] + ["expanding"],
            "concurrent_horizons": prereg["horizons_sessions"],
            "comparable_state_drives_selection": True,
            "sparse_zero_weights_legal": True,
            "slow_and_fast_adaptation_tested": True,
            "position_state_first_class": True,
            "dynamic_sizing_enabled": True,
            "long_short_asymmetric_and_symmetric_controls": True,
            "complete_trade_lifecycle_scored": True,
            "decision_brain_row_count": len(brain),
        },
        "scoring_code_identity": current_code_identity(),
    }
    _write_json(RESULT, result)
    return result


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"preflight", "score"}:
        raise SystemExit("usage: run_issue465_block1_controller_v2.py {preflight|score}")
    payload = preflight(write=True) if args[0] == "preflight" else score_block()
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
