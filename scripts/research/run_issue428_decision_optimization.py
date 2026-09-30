from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts/research"))

import run_issue448_coverage as issue448

from commodity import v2_decision_optimization as dec
from commodity import v2_model_optimization as opt
from commodity import v2_optimization as v2
from commodity.market_only_phase2 import _load_inherited_risk_and_costs, _path_window
from commodity.stacking_policy import replay_fractional_policy

PROGRAMME = REPO / "research/programmes/004-v2-maximum-reproducible-one-month-return"
PREREG = PROGRAMME / "issue428-prereg-v3.json"
PREFLIGHT = PROGRAMME / "issue428-preflight-v1.json"
RESULT = PROGRAMME / "issue428-result-v1.json"
LEDGER = PROGRAMME / "issue428-trials-v1.jsonl"
ISSUE425 = PROGRAMME / "issue425-result-v1.json"
ISSUE427_PREREG = PROGRAMME / "issue427-prereg-v1.json"
ISSUE427_CORE = PROGRAMME / "issue427-core-result-v1.json"
ISSUE427_RESULT = PROGRAMME / "issue427-result-v1.json"
ISSUE427_TRIALS = PROGRAMME / "issue427-trials-v1.jsonl"
ISSUE427_SPECIALIST_TRIALS = PROGRAMME / "issue427-specialist-trials-v1.jsonl"
ISSUE448 = PROGRAMME / "issue448-result-v1.json"
ISSUE448_HANDOFF = PROGRAMME / "issue448-downstream-handoff-v1.json"
PHASE2 = REPO / "config/phase2_market_only.json"
PHASE5 = REPO / ".work/changes/359-stacking-policy/phase5-stacking-policy-result.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _require_hash(path: Path, expected: object, label: str) -> None:
    observed = sha256_file(path)
    if observed != str(expected):
        raise RuntimeError(f"issue428 {label} identity changed: {observed}")


def load_prereg() -> dict[str, Any]:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "frozen_before_issue428_scoring":
        raise RuntimeError("issue428 preregistration is not frozen")
    boundary = prereg.get("evidence_boundary", {})
    if boundary.get("latest_allowed_trade_date") != "2022-12-31":
        raise RuntimeError("issue428 development cutoff changed")
    if boundary.get("protected_confirmation_accessed") is not False:
        raise RuntimeError("issue428 protected evidence flag is not false")
    upstream = prereg.get("upstream_evidence", {})
    if not isinstance(upstream, Mapping):
        raise TypeError("issue428 upstream authority is invalid")
    authorities = (
        (ISSUE427_PREREG, "issue427_prereg_sha256", "issue427 prereg"),
        (ISSUE427_CORE, "issue427_core_result_sha256", "issue427 core result"),
        (ISSUE427_RESULT, "issue427_result_sha256", "issue427 result"),
        (ISSUE427_TRIALS, "issue427_core_trials_sha256", "issue427 trials"),
        (ISSUE427_SPECIALIST_TRIALS, "issue427_specialist_trials_sha256", "issue427 specialist trials"),
        (ISSUE448, "issue448_result_sha256", "issue448 result"),
        (ISSUE448_HANDOFF, "issue448_handoff_sha256", "issue448 handoff"),
        (PHASE2, "phase2_sha256", "phase2 config"),
        (PHASE5, "phase5_stacking_result_sha256", "phase5 result"),
    )
    for path, key, label in authorities:
        _require_hash(path, upstream[key], label)
    return prereg


def _outer_blocks(cfg: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    rows = cfg["validation"]["outer_blocks"]
    return {str(row["id"]): dict(row) for row in rows}


def _oi_block_spec(block_id: str, cfg: Mapping[str, Any]) -> dict[str, str]:
    if block_id == "outer-2020-oi":
        return {"id": block_id, "start": "2020-01-01", "end": "2020-12-31"}
    blocks = _outer_blocks(cfg)
    if block_id not in blocks:
        raise RuntimeError(f"issue428 unknown OI block: {block_id}")
    return blocks[block_id]


def _oi_parent_outer_id(block_id: str) -> str:
    return "outer-2019-2020" if block_id == "outer-2020-oi" else block_id


def _selected_model_configs() -> dict[str, dict[str, object]]:
    core = json.loads(ISSUE427_CORE.read_text(encoding="utf-8"))
    outer_results = core["model_stage"]["outer_results"]
    return {
        str(outer_id): dict(item["selected_config"])
        for outer_id, item in outer_results.items()
    }


def _selected_representations() -> dict[str, dict[str, str]]:
    issue448_result = json.loads(ISSUE448.read_text(encoding="utf-8"))
    selected: dict[str, dict[str, str]] = {}
    for family, item in issue448_result["family_results"].items():
        if not isinstance(item, Mapping):
            continue
        for row in item.get("nested_outer", []):
            if not isinstance(row, Mapping):
                continue
            outer = row.get("outer_block", {})
            representation = row.get("selected_representation")
            if isinstance(outer, Mapping) and representation:
                selected.setdefault(str(outer["id"]), {})[str(family)] = str(representation)
    return selected


def _signal_columns_for_outer(
    outer_id: str,
    selected_reps: Mapping[str, Mapping[str, str]],
) -> list[str]:
    required = (
        "market_structure.positioning",
        "ta.range_breakout",
        "ta.trend_strength",
        "ta.volume_confirmation",
    )
    reps = selected_reps.get(outer_id, {})
    missing = [family for family in required if family not in reps]
    if missing:
        raise RuntimeError(f"issue428 missing selected representations for {outer_id}: {missing}")
    return [
        *(str(reps[family]) for family in required),
        "feature_issue427_jump_intensity",
        "feature_issue427_vol_of_vol",
    ]


def _oi_representation_for_block(
    block_id: str,
    selected_reps: Mapping[str, Mapping[str, str]],
) -> str:
    representation = selected_reps.get(block_id, {}).get("market_structure.open_interest")
    if not representation:
        raise RuntimeError(f"issue428 missing inherited OI representation for {block_id}")
    return str(representation)


def _features_with_volatility_tail(features: pd.DataFrame) -> pd.DataFrame:
    specialist = opt.build_issue427_volatility_tail_features(features)
    join = specialist[
        [
            "trade_date",
            "available_at",
            "feature_issue427_jump_intensity",
            "feature_issue427_vol_of_vol",
        ]
    ].copy()
    merged = features.merge(
        join,
        on=["trade_date", "available_at"],
        how="left",
        validate="one_to_one",
    )
    return merged


def _trial(stage: str, payload: Mapping[str, object]) -> dict[str, object]:
    core = {
        "issue": 428,
        "evidence_class": "development",
        "stage": stage,
        **dict(payload),
    }
    return {"trial_id": stable_sha(core), **core}


def _load_inputs() -> tuple[
    dict[str, Any], pd.DataFrame, pd.DataFrame, dict[str, tuple[str, ...]], dict[str, Any]
]:
    prereg = load_prereg()
    features, families, source_evidence, selection_support = issue448.load_preflight_cache()
    _market, sessions = issue448.load_market()
    dec.validate_issue428_evidence_boundary(features)
    dec.validate_issue428_evidence_boundary(sessions)
    return prereg, features, sessions, families, {
        "source_evidence": source_evidence,
        "selection_support": selection_support,
    }


def preflight() -> dict[str, object]:
    prereg, features, sessions, families, support = _load_inputs()
    failures: list[str] = []
    expected_rows = 3088
    if len(features) != expected_rows:
        failures.append(f"feature_row_count_changed:{len(features)}!={expected_rows}")
    selected_reps = _selected_representations()
    for outer_id in prereg["chronology"]["fusion_outer_blocks"]:
        try:
            signal_columns = _signal_columns_for_outer(str(outer_id), selected_reps)
        except RuntimeError as exc:
            failures.append(str(exc))
            continue
        missing = sorted(set(signal_columns[:4]) - set(features.columns))
        if missing:
            failures.append(f"missing_signal_columns:{outer_id}:{missing}")
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    minimum_oi_history = int(prereg["open_interest_lane"]["minimum_history_rows"])
    trade_dates = pd.to_datetime(features["trade_date"], utc=True, errors="raise")
    for block_id in map(str, prereg["open_interest_lane"]["eligible_outer_blocks"]):
        try:
            oi_column = _oi_representation_for_block(block_id, selected_reps)
            block = _oi_block_spec(block_id, cfg)
        except RuntimeError as exc:
            failures.append(str(exc))
            continue
        if oi_column not in features.columns:
            failures.append(f"missing_oi_column:{block_id}:{oi_column}")
            continue
        prior = pd.to_numeric(
            features.loc[trade_dates < pd.Timestamp(str(block["start"]), tz="UTC"), oi_column],
            errors="coerce",
        )
        if int(prior.notna().sum()) < minimum_oi_history:
            failures.append(f"insufficient_oi_history:{block_id}:{int(prior.notna().sum())}")
    enriched = _features_with_volatility_tail(features)
    for column in ("feature_issue427_jump_intensity", "feature_issue427_vol_of_vol"):
        if int(pd.to_numeric(enriched[column], errors="coerce").notna().sum()) < 1000:
            failures.append(f"insufficient_volatility_tail_support:{column}")
    grid = dec.build_issue428_candidate_grid(prereg)
    if len(grid) != int(prereg["candidate_grid"]["expected_configuration_count"]):
        failures.append("candidate_grid_count_changed")
    report = {
        "schema_version": 1,
        "issue": 428,
        "status": "PASS" if not failures else "FAIL",
        "scoring_performed": False,
        "protected_confirmation_accessed": False,
        "feature_rows": len(features),
        "session_rows": len(sessions),
        "family_count": len(families),
        "candidate_count": len(grid),
        "oi_candidate_count": int(prereg["budgets"]["oi_incremental_configurations"]),
        "failures": failures,
        "prereg_sha256": sha256_file(PREREG),
        "issue448_preflight_sha256": sha256_file(issue448.PREFLIGHT),
        "issue448_feature_cache_sha256": sha256_file(issue448.CACHE / "preflight-features.parquet"),
        "source_evidence_sha256": stable_sha(support["source_evidence"]),
        "runner_sha256": sha256_file(Path(__file__)),
        "decision_code_sha256": sha256_file(REPO / "src/commodity/v2_decision_optimization.py"),
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


def _require_preflight() -> dict[str, object]:
    if not PREFLIGHT.exists():
        raise RuntimeError("issue428 scoring requires completed preflight")
    report = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("scoring_performed") is not False:
        raise RuntimeError("issue428 preflight is not a passing no-scoring report")
    expected = {
        "prereg_sha256": sha256_file(PREREG),
        "issue448_preflight_sha256": sha256_file(issue448.PREFLIGHT),
        "issue448_feature_cache_sha256": sha256_file(issue448.CACHE / "preflight-features.parquet"),
        "runner_sha256": sha256_file(Path(__file__)),
        "decision_code_sha256": sha256_file(REPO / "src/commodity/v2_decision_optimization.py"),
        "model_code_sha256": sha256_file(REPO / "src/commodity/v2_model_optimization.py"),
        "v2_code_sha256": sha256_file(REPO / "src/commodity/v2_optimization.py"),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"issue428 preflight is stale: {key}")
    return report


def _prepare_outer_origins(
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    config: Mapping[str, object],
    signal_columns: Sequence[str],
    *,
    round_trip_per_mmbtu: float,
) -> tuple[pd.DataFrame, list[str]]:
    prepared, _candidate_transformed, control_columns = opt.prepare_issue427_feature_set(
        features, config, signal_columns
    )
    origins, rebuilt = opt._build_segmented_decision_origins(
        sessions, prepared, horizon_sessions=int(config["target.horizon_sessions"])
    )
    if origins.empty or set(rebuilt) != set(prepared.columns) - {"trade_date", "available_at"}:
        raise RuntimeError("issue428 origin reconstruction changed")
    origins, _ = opt._canonicalize_one_origin_per_fill(origins)
    attached = v2._attach_issue425_targets(
        origins,
        sessions,
        horizon_sessions=int(config["target.horizon_sessions"]),
        role=str(config["target.target_role"]),
        aggregation=str(config["target.aggregation"]),
        round_trip_per_mmbtu=float(round_trip_per_mmbtu),
    )
    return attached, list(control_columns)


def _attach_context_signal_to_origins(
    origins: pd.DataFrame,
    features: pd.DataFrame,
    config: Mapping[str, object],
    signal_column: str,
) -> pd.DataFrame:
    prepared, candidate_transformed, _control_columns = opt.prepare_issue427_feature_set(
        features,
        config,
        [signal_column],
    )
    if signal_column not in candidate_transformed:
        raise RuntimeError(f"issue428 context transform missing {signal_column}")
    context = prepared[["trade_date", "available_at", signal_column]].copy()
    if context.duplicated(["trade_date", "available_at"]).any():
        raise RuntimeError("issue428 context signal is not unique by feature timestamp")
    merged = origins.merge(
        context,
        on=["trade_date", "available_at"],
        how="left",
        validate="many_to_one",
    )
    return merged


def _forecast_window(
    origins: pd.DataFrame,
    feature_columns: Sequence[str],
    config: Mapping[str, object],
    *,
    start: str,
    end: str,
    multiplier: float,
    round_trip_usd: float,
    minimum_training_rows: int,
) -> pd.DataFrame:
    forecasts, _diagnostics = v2._fit_issue425_forecast_window(
        origins,
        feature_columns,
        config,
        start_timestamp=pd.Timestamp(start, tz="UTC"),
        boundary_timestamp=pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1),
        contract_multiplier=multiplier,
        round_trip_usd=round_trip_usd,
        minimum_training_rows=minimum_training_rows,
    )
    return forecasts


def _opportunity_frame(
    origins: pd.DataFrame,
    selected_forecasts: pd.DataFrame,
    matched_forecasts: pd.DataFrame,
    signal_columns: Sequence[str],
    *,
    round_trip_usd: float,
    multiplier: float,
) -> pd.DataFrame:
    context_columns = ["signal_timestamp", "trade_date", *signal_columns]
    context = origins[context_columns].drop_duplicates("signal_timestamp").copy()
    if context["signal_timestamp"].duplicated().any():
        raise RuntimeError("issue428 origin context is not unique by signal timestamp")
    selected = selected_forecasts.merge(
        context, on="signal_timestamp", how="left", validate="many_to_one"
    )
    matched = matched_forecasts[[
        "fill_timestamp", "predicted_path_move_per_mmbtu", "predicted_gross_pnl_usd"
    ]].rename(
        columns={
            "predicted_path_move_per_mmbtu": "matched_predicted_path_move_per_mmbtu",
            "predicted_gross_pnl_usd": "matched_predicted_gross_pnl_usd",
        }
    )
    frame = selected.merge(matched, on="fill_timestamp", how="left", validate="one_to_one")
    if frame[[*signal_columns, "matched_predicted_gross_pnl_usd"]].isna().any().any():
        raise RuntimeError("issue428 matched opportunity join is incomplete")
    predicted = pd.to_numeric(frame["predicted_gross_pnl_usd"], errors="raise").astype(float)
    matched_predicted = pd.to_numeric(frame["matched_predicted_gross_pnl_usd"], errors="raise").astype(float)
    baseline_position = np.where(
        predicted.abs() > float(round_trip_usd), np.sign(predicted), 0.0
    ).astype(float)
    actual_gross = pd.to_numeric(frame["actual_gross_pnl_usd"], errors="raise").astype(float)
    frame["baseline_position"] = baseline_position
    frame["primary_strength"] = predicted.abs() / float(round_trip_usd)
    frame["model_agreement"] = (np.sign(predicted) == np.sign(matched_predicted)).astype(float)
    frame["normalized_model_disagreement"] = (
        (predicted - matched_predicted).abs() / float(round_trip_usd)
    )
    frame["net_trade_utility_usd"] = np.where(
        baseline_position != 0.0,
        baseline_position * actual_gross - float(round_trip_usd),
        0.0,
    )
    frame["trade_profitable"] = (
        (baseline_position != 0.0) & (frame["net_trade_utility_usd"] > 0.0)
    ).astype(int)
    frame["jump_intensity"] = pd.to_numeric(
        frame["feature_issue427_jump_intensity"], errors="raise"
    ).astype(float)
    frame["vol_of_vol"] = pd.to_numeric(
        frame["feature_issue427_vol_of_vol"], errors="raise"
    ).astype(float)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    frame["fill_trade_date"] = pd.to_datetime(frame["fill_trade_date"], utc=True, errors="raise")
    frame["fill_timestamp"] = pd.to_datetime(frame["fill_timestamp"], utc=True, errors="raise")
    frame["target_end_timestamp"] = pd.to_datetime(frame["target_end_timestamp"], utc=True, errors="raise")
    dec.validate_issue428_evidence_boundary(frame)
    return frame.sort_values("fill_timestamp", kind="stable").reset_index(drop=True)


def _forecast_pair(
    origins: pd.DataFrame,
    control_columns: Sequence[str],
    selected_config: Mapping[str, object],
    matched_config: Mapping[str, object],
    *,
    start: str,
    end: str,
    multiplier: float,
    round_trip_usd: float,
    minimum_training_rows: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = _forecast_window(
        origins, control_columns, selected_config,
        start=start, end=end, multiplier=multiplier,
        round_trip_usd=round_trip_usd, minimum_training_rows=minimum_training_rows,
    )
    matched = _forecast_window(
        origins, control_columns, matched_config,
        start=start, end=end, multiplier=multiplier,
        round_trip_usd=round_trip_usd, minimum_training_rows=minimum_training_rows,
    )
    if len(selected) != len(matched):
        raise RuntimeError("issue428 selected/matched forecast row counts differ")
    return selected, matched


def _build_outer_opportunities(
    *,
    target_outer_id: str,
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, Any],
    selected_config: Mapping[str, object],
    matched_config: Mapping[str, object],
    signal_columns: Sequence[str],
    round_trip_usd: float,
    target_block: Mapping[str, str] | None = None,
    context_only_signal_columns: Sequence[str] = (),
) -> pd.DataFrame:
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    minimum_training_rows = int(cfg["execution_contract"]["minimum_training_rows"])
    origins, control_columns = _prepare_outer_origins(
        features,
        sessions,
        selected_config,
        signal_columns,
        round_trip_per_mmbtu=float(round_trip_usd) / multiplier,
    )
    context_columns = [str(column) for column in context_only_signal_columns]
    if set(context_columns) & set(signal_columns):
        raise RuntimeError("issue428 context-only signal overlaps model context")
    for column in context_columns:
        origins = _attach_context_signal_to_origins(origins, features, selected_config, column)
    opportunity_signal_columns = [*signal_columns, *context_columns]
    outer = dict(target_block) if target_block is not None else _outer_blocks(cfg)[target_outer_id]
    if str(outer.get("id", target_outer_id)) != target_outer_id:
        raise RuntimeError("issue428 target block identity changed")
    outer_start_year = int(str(outer["start"])[:4])
    windows: list[tuple[str, str]] = []
    for year in range(2017, outer_start_year):
        windows.append((f"{year}-01-01", f"{year}-12-31"))
    windows.append((str(outer["start"]), str(outer["end"])))
    frames: list[pd.DataFrame] = []
    for start, end in windows:
        selected, matched = _forecast_pair(
            origins,
            control_columns,
            selected_config,
            matched_config,
            start=start,
            end=end,
            multiplier=multiplier,
            round_trip_usd=round_trip_usd,
            minimum_training_rows=minimum_training_rows,
        )
        frames.append(
            _opportunity_frame(
                origins,
                selected,
                matched,
                opportunity_signal_columns,
                round_trip_usd=round_trip_usd,
                multiplier=multiplier,
            )
        )
    combined = pd.concat(frames, ignore_index=True).sort_values("fill_timestamp", kind="stable")
    if combined["fill_timestamp"].duplicated().any():
        raise RuntimeError("issue428 opportunity windows overlap")
    return combined.reset_index(drop=True)


def _policy_decisions(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.to_datetime(frame["fill_trade_date"], utc=True),
            "target_end_timestamp": pd.to_datetime(frame["target_end_timestamp"], utc=True),
            "forecast_id": frame["forecast_id"].astype(str),
            "signal_requested_position": pd.to_numeric(
                frame["signal_requested_position"], errors="raise"
            ).astype(float),
            "signal_reason": frame["signal_reason"].astype(str),
        }
    ).sort_values("trade_date", kind="stable")


def _score_policy_window(
    sessions: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    start: str,
    end: str,
    risk: object,
    costs: object,
    multiplier: float,
) -> tuple[dict[str, object], pd.DataFrame, dict[str, object]]:
    path, _start, _boundary = _path_window(sessions, start_date=start, end_date=end)
    ledger, summary = replay_fractional_policy(
        path,
        decisions,
        risk,
        costs,
        contract_multiplier=multiplier,
        enforce_risk=True,
    )
    score = v2.score_monthly_path(
        v2._phase2_ledger_for_monthly_score(ledger),
        starting_capital_usd=float(risk.capital_usd),
        latest_allowed_timestamp="2022-12-31",
    )
    return score, ledger, summary


def _fill_year(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame["fill_trade_date"], utc=True, errors="raise").dt.year


def _history_outcome_diagnostics(
    history: pd.DataFrame,
    boundary: pd.Timestamp,
) -> dict[str, object]:
    target_end = pd.to_datetime(history["target_end_timestamp"], utc=True, errors="raise")
    maximum = target_end.max() if len(target_end) else None
    if maximum is not None and maximum >= boundary:
        raise RuntimeError("issue428 policy history outcome crosses scoring boundary")
    return {
        "history_rows": len(history),
        "boundary": str(boundary),
        "max_target_end_timestamp": str(maximum) if maximum is not None else None,
        "strictly_prior": True,
    }


def _effective_sample(
    policy: pd.DataFrame,
    ledger: pd.DataFrame,
    replay_summary: Mapping[str, object],
    prereg: Mapping[str, Any],
) -> dict[str, object]:
    baseline = pd.to_numeric(policy["baseline_position"], errors="raise").ne(0.0)
    requested = pd.to_numeric(policy["signal_requested_position"], errors="raise").ne(0.0)
    decision_dates = pd.to_datetime(policy["fill_trade_date"], utc=True, errors="raise")
    ledger_dates = pd.to_datetime(ledger["trade_date"], utc=True, errors="raise")
    if ledger_dates.duplicated().any():
        raise RuntimeError("issue428 replay ledger has duplicate trade dates")
    executed_by_date = pd.Series(
        pd.to_numeric(ledger["target_position"], errors="raise").to_numpy(dtype=float),
        index=ledger_dates,
    )
    executed_position = decision_dates.map(executed_by_date)
    if executed_position.isna().any():
        raise RuntimeError("issue428 policy decision is missing from replay ledger")
    executed = requested & executed_position.ne(0.0)
    executed_dates = decision_dates.loc[executed]
    month_counts = (
        executed_dates.dt.tz_convert(None).dt.to_period("M").value_counts().sort_index()
    )
    controls = prereg["effective_sample_controls"]
    trade_opportunities = int(baseline.sum())
    requested_selected_trades = int(requested.sum())
    selected_trades = int(executed.sum())
    nonempty_months = len(month_counts)
    return {
        "trade_opportunities": trade_opportunities,
        "requested_selected_trades": requested_selected_trades,
        "selected_trades": selected_trades,
        "risk_or_margin_excluded_selected_trades": requested_selected_trades - selected_trades,
        "abstention_rate": float(policy.loc[baseline, "policy_abstained"].mean()) if trade_opportunities else 0.0,
        "nonempty_months": nonempty_months,
        "monthly_trade_counts": {str(k): int(v) for k, v in month_counts.items()},
        "signal_abstention_sessions": int(replay_summary.get("signal_abstention_sessions", 0)),
        "risk_shutdown_sessions": int(replay_summary.get("risk_shutdown_sessions", 0)),
        "passes_outer_minimums": bool(
            trade_opportunities >= int(controls["minimum_outer_trade_opportunities"])
            and selected_trades >= int(controls["minimum_selected_trades"])
            and nonempty_months >= int(controls["minimum_nonempty_months"])
        ),
    }


def _meta_diagnostics(state: dec.MetaConfidenceState | None) -> dict[str, object]:
    if state is None:
        return {"active": False}
    return {
        "active": bool(state.active),
        "mode": state.mode,
        "training_rows": int(state.training_rows),
        "calibration_rows": int(state.calibration_rows),
        "training_end": str(state.training_end) if state.training_end is not None else None,
        "calibration_start": str(state.calibration_start) if state.calibration_start is not None else None,
        "positive_label_rate": state.positive_label_rate,
        "brier_score": state.brier_score,
        "ece": state.ece,
    }


def _annotated_context(
    history: pd.DataFrame,
    score_frame: pd.DataFrame,
    signal_columns: Sequence[str],
    prereg: Mapping[str, Any],
    *,
    outcome_available_before: pd.Timestamp,
) -> tuple[dec.Issue428State, pd.DataFrame, pd.DataFrame]:
    state = dec.fit_issue428_state(
        history,
        signal_columns=signal_columns,
        minimum_state_rows=int(prereg["signal_state_contract"]["minimum_state_rows"]),
        outcome_available_before=outcome_available_before,
    )
    annotated_history = dec.annotate_issue428_states(history, state, signal_columns=signal_columns)
    annotated_score = dec.annotate_issue428_states(score_frame, state, signal_columns=signal_columns)
    return state, annotated_history, annotated_score


def _fit_meta_states(
    annotated_history: pd.DataFrame,
    signal_columns: Sequence[str],
    prereg: Mapping[str, Any],
    *,
    outcome_available_before: pd.Timestamp,
) -> tuple[dict[str, dec.MetaConfidenceState], dict[str, dict[str, object]]]:
    states: dict[str, dec.MetaConfidenceState] = {}
    diagnostics: dict[str, dict[str, object]] = {}
    contract = prereg["confidence_contract"]
    for mode in ("basic", "interactions"):
        try:
            state = dec.fit_meta_confidence(
                annotated_history,
                signal_columns=signal_columns,
                mode=mode,
                minimum_train_rows=int(contract["minimum_meta_train_rows"]),
                minimum_calibration_rows=int(contract["minimum_calibration_rows"]),
                outcome_available_before=outcome_available_before,
            )
        except dec.Issue428DecisionError as exc:
            diagnostics[mode] = {"active": False, "reason": str(exc)}
            continue
        states[mode] = state
        diagnostics[mode] = _meta_diagnostics(state)
    return states, diagnostics


def _score_policy(
    frame: pd.DataFrame,
    config: dec.DecisionConfig,
    state: dec.Issue428State,
    meta_states: Mapping[str, dec.MetaConfidenceState],
    signal_columns: Sequence[str],
) -> pd.DataFrame:
    work = frame.copy()
    if config.kind == "meta":
        mode = str(config.meta_mode)
        if mode not in meta_states:
            raise dec.Issue428DecisionError(f"issue-428 meta state unavailable: {mode}")
        work["meta_probability"] = dec.predict_meta_confidence(
            work, meta_states[mode], signal_columns=signal_columns
        )
    return dec.apply_issue428_policy(work, config, state)


def _apply_admission_mask(
    frame: pd.DataFrame,
    admit: pd.Series,
    *,
    reason: str,
) -> pd.DataFrame:
    out = frame.copy()
    baseline = pd.to_numeric(out["baseline_position"], errors="raise").astype(float)
    mask = pd.Series(admit, index=out.index).astype(bool) & baseline.ne(0.0)
    out["trade_admitted"] = mask
    out["signal_requested_position"] = np.where(mask, baseline, 0.0).astype(float)
    out["policy_abstained"] = baseline.ne(0.0) & ~mask
    out["signal_reason"] = np.where(
        baseline.eq(0.0),
        "baseline_abstain",
        np.where(mask, "forecast_signal", reason),
    )
    return out


def _score_policy_frame(
    sessions: pd.DataFrame,
    policy: pd.DataFrame,
    *,
    start: str,
    end: str,
    risk: object,
    costs: object,
    multiplier: float,
    prereg: Mapping[str, Any],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    score, ledger, replay_summary = _score_policy_window(
        sessions,
        _policy_decisions(policy),
        start=start,
        end=end,
        risk=risk,
        costs=costs,
        multiplier=multiplier,
    )
    effective = _effective_sample(policy, ledger, replay_summary, prereg)
    return score, replay_summary, effective


def _selection_row(
    config: dec.DecisionConfig,
    year: int,
    score: Mapping[str, object],
) -> dict[str, object]:
    return {
        "config_id": config.config_id,
        "year": int(year),
        "net_pnl_usd": float(score["total_net_pnl_usd"]),
        "mean_monthly_net_return": float(score["mean_monthly_net_return"]),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"]),
        "transaction_cost_usd": float(score["transaction_cost_usd"]),
        "complexity": int(config.complexity),
    }


def _apply_complexity_control(
    selection: Mapping[str, Any],
    configs: Mapping[str, dec.DecisionConfig],
) -> dict[str, Any]:
    chosen = dict(selection)
    ranking = [dict(row) for row in selection["ranking"]]
    top_id = str(chosen["config_id"])
    top = configs[top_id]
    if top.kind != "meta":
        chosen["complexity_control"] = "not_needed"
        return chosen
    simple = next(
        (row for row in ranking if configs[str(row["config_id"])].kind != "meta"),
        None,
    )
    if simple is None:
        raise RuntimeError("issue428 complexity control has no simple-gate comparator")
    if float(chosen["median_yearly_net_pnl_usd"]) > float(simple["median_yearly_net_pnl_usd"]):
        chosen["complexity_control"] = "meta_primary_objective_strictly_better"
        return chosen
    ranking_copy = ranking
    chosen = dict(simple)
    chosen["years"] = [int(value) for value in chosen["years"]]
    chosen["ranking"] = ranking_copy
    chosen["complexity_control"] = "meta_not_strictly_better_selected_best_simple"
    return chosen


def _config_map(prereg: Mapping[str, Any]) -> dict[str, dec.DecisionConfig]:
    return {item.config_id: item for item in dec.build_issue428_candidate_grid(prereg)}


def _score_delta(
    score: Mapping[str, object],
    reference: Mapping[str, object],
) -> dict[str, float | int]:
    return {
        "mean_monthly_net_return": float(score["mean_monthly_net_return"])
        - float(reference["mean_monthly_net_return"]),
        "total_net_pnl_usd": float(score["total_net_pnl_usd"])
        - float(reference["total_net_pnl_usd"]),
        "max_drawdown_fraction": float(score["max_drawdown_fraction"])
        - float(reference["max_drawdown_fraction"]),
        "transaction_cost_usd": float(score["transaction_cost_usd"])
        - float(reference["transaction_cost_usd"]),
        "trade_count": int(score["trade_count"]) - int(reference["trade_count"]),
    }


def _simple_ablation_configs(
    config: dec.DecisionConfig,
) -> list[tuple[str, dec.DecisionConfig]]:
    baseline = dec.DecisionConfig("ablation-baseline", "baseline", 0)
    if config.kind == "baseline":
        return []
    if config.kind in {"strength", "model_agreement", "favored_count", "jump_veto", "vol_of_vol_veto"}:
        return [(config.kind, baseline)]
    if config.kind == "strength_fusion":
        return [
            (
                "primary_strength",
                dec.DecisionConfig(
                    "ablation-favored-only",
                    "favored_count",
                    1,
                    favored_signal_count=config.favored_signal_count,
                ),
            ),
            (
                "favored_signal_count",
                dec.DecisionConfig(
                    "ablation-strength-only",
                    "strength",
                    1,
                    strength_quantile=config.strength_quantile,
                ),
            ),
        ]
    if config.kind == "joint_volatility_veto":
        return [
            (
                "jump_intensity",
                dec.DecisionConfig(
                    "ablation-vol-of-vol-only",
                    "vol_of_vol_veto",
                    1,
                    veto_quantile=config.veto_quantile,
                ),
            ),
            (
                "vol_of_vol",
                dec.DecisionConfig(
                    "ablation-jump-only",
                    "jump_veto",
                    1,
                    veto_quantile=config.veto_quantile,
                ),
            ),
        ]
    if config.kind == "favorable_regime":
        rows: list[tuple[str, dec.DecisionConfig]] = [("favorable_regime", baseline)]
        if int(config.persistence or 1) > 1:
            rows.append((
                "persistence",
                dec.DecisionConfig(
                    "ablation-persistence-p1",
                    "favorable_regime",
                    2,
                    persistence=1,
                ),
            ))
        return rows
    return []


def _score_remove_one_input_ablations(
    *,
    selected_config: dec.DecisionConfig,
    state: dec.Issue428State,
    annotated_history: pd.DataFrame,
    annotated_outer: pd.DataFrame,
    outer_meta_states: Mapping[str, dec.MetaConfidenceState],
    signal_columns: Sequence[str],
    sessions: pd.DataFrame,
    start: str,
    end: str,
    risk: object,
    costs: object,
    multiplier: float,
    prereg: Mapping[str, Any],
    selected_score: Mapping[str, object],
    outer_id: str,
    trials: list[dict[str, object]],
) -> dict[str, object]:
    results: dict[str, object] = {}
    if selected_config.kind == "meta":
        mode = str(selected_config.meta_mode)
        full_state = outer_meta_states.get(mode)
        if full_state is None:
            raise RuntimeError("issue428 selected meta policy lacks outer meta state")
        contract = prereg["confidence_contract"]
        for feature in full_state.feature_columns:
            ablated_state = dec.fit_meta_confidence(
                annotated_history,
                signal_columns=signal_columns,
                mode=mode,
                minimum_train_rows=int(contract["minimum_meta_train_rows"]),
                minimum_calibration_rows=int(contract["minimum_calibration_rows"]),
                outcome_available_before=pd.Timestamp(start, tz="UTC"),
                excluded_features=[feature],
            )
            work = annotated_outer.copy()
            work["meta_probability"] = dec.predict_meta_confidence(
                work,
                ablated_state,
                signal_columns=signal_columns,
            )
            policy = dec.apply_issue428_policy(work, selected_config, state)
            score, replay_summary, effective = _score_policy_frame(
                sessions,
                policy,
                start=start,
                end=end,
                risk=risk,
                costs=costs,
                multiplier=multiplier,
                prereg=prereg,
            )
            key = str(feature)
            results[key] = {
                "score": score,
                "delta_vs_selected": _score_delta(score, selected_score),
                "effective_sample": effective,
                "replay_summary": replay_summary,
            }
            trials.append(_trial("remove_one_input_ablation", {
                "outer_block_id": outer_id,
                "selected_config_id": selected_config.config_id,
                "removed_input": key,
                "status": "complete",
                "score": score,
            }))
        return results

    for removed_input, ablated_config in _simple_ablation_configs(selected_config):
        policy = _score_policy(
            annotated_outer,
            ablated_config,
            state,
            outer_meta_states,
            signal_columns,
        )
        score, replay_summary, effective = _score_policy_frame(
            sessions,
            policy,
            start=start,
            end=end,
            risk=risk,
            costs=costs,
            multiplier=multiplier,
            prereg=prereg,
        )
        results[removed_input] = {
            "ablation_config": ablated_config.__dict__,
            "score": score,
            "delta_vs_selected": _score_delta(score, selected_score),
            "effective_sample": effective,
            "replay_summary": replay_summary,
        }
        trials.append(_trial("remove_one_input_ablation", {
            "outer_block_id": outer_id,
            "selected_config_id": selected_config.config_id,
            "removed_input": removed_input,
            "status": "complete",
            "score": score,
        }))
    return results


def _score_outer_lane(
    *,
    outer_id: str,
    opportunities: pd.DataFrame,
    signal_columns: Sequence[str],
    sessions: pd.DataFrame,
    cfg: Mapping[str, Any],
    prereg: Mapping[str, Any],
    risk: object,
    cost_profiles: Mapping[str, object],
    trials: list[dict[str, object]],
) -> dict[str, object]:
    configs = _config_map(prereg)
    grid = list(configs.values())
    outer = _outer_blocks(cfg)[outer_id]
    outer_start_year = int(str(outer["start"])[:4])
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    base_costs = cost_profiles["base"]
    years = [
        int(year)
        for year in prereg["chronology"]["prequential_score_years"]
        if int(year) < outer_start_year
    ]
    meta_years = {int(year) for year in prereg["chronology"]["meta_score_years"]}
    fill_year = _fill_year(opportunities)
    selection_rows: list[dict[str, object]] = []
    calibration: dict[str, object] = {}
    history_outcomes: dict[str, object] = {}

    for year in years:
        scoring_boundary = pd.Timestamp(f"{year}-01-01", tz="UTC")
        history = dec.completed_history_before(opportunities, scoring_boundary)
        history_outcomes[str(year)] = _history_outcome_diagnostics(history, scoring_boundary)
        score_frame = opportunities.loc[fill_year == year].copy()
        if history.empty or score_frame.empty:
            raise RuntimeError(f"issue428 missing policy support for {outer_id}:{year}")
        state, annotated_history, annotated_score = _annotated_context(
            history,
            score_frame,
            signal_columns,
            prereg,
            outcome_available_before=scoring_boundary,
        )
        if year in meta_years:
            meta_states, meta_diag = _fit_meta_states(
                annotated_history,
                signal_columns,
                prereg,
                outcome_available_before=scoring_boundary,
            )
        else:
            meta_states, meta_diag = {}, {
                "basic": {"active": False, "reason": "preregistered_meta_year_ineligible"},
                "interactions": {"active": False, "reason": "preregistered_meta_year_ineligible"},
            }
        calibration[str(year)] = meta_diag
        for config in grid:
            if config.kind == "meta" and year not in meta_years:
                trials.append(_trial("policy_score", {
                    "outer_block_id": outer_id,
                    "score_year": year,
                    "config_id": config.config_id,
                    "status": "ineligible",
                    "reason": "preregistered_meta_year_ineligible",
                    "complexity": config.complexity,
                }))
                continue
            try:
                policy = _score_policy(
                    annotated_score, config, state, meta_states, signal_columns
                )
            except dec.Issue428DecisionError as exc:
                trials.append(_trial("policy_score", {
                    "outer_block_id": outer_id,
                    "score_year": year,
                    "config_id": config.config_id,
                    "status": "ineligible",
                    "reason": str(exc),
                    "complexity": config.complexity,
                }))
                continue
            score, replay_summary, effective = _score_policy_frame(
                sessions, policy,
                start=f"{year}-01-01", end=f"{year}-12-31",
                risk=risk, costs=base_costs, multiplier=multiplier, prereg=prereg,
            )
            selection_rows.append(_selection_row(config, year, score))
            trials.append(_trial("policy_score", {
                "outer_block_id": outer_id,
                "score_year": year,
                "config_id": config.config_id,
                "status": "complete",
                "complexity": config.complexity,
                "score": score,
                "effective_sample": effective,
                "replay_summary": replay_summary,
            }))

    selection_years = [
        int(year) for year in prereg["chronology"]["selection_years_by_outer"][outer_id]
    ]
    selected = dec.select_issue428_policy(
        pd.DataFrame(selection_rows),
        outer_start_year=outer_start_year,
        required_years=selection_years,
    )
    selected = _apply_complexity_control(selected, configs)
    selected_config = configs[str(selected["config_id"])]

    fill_dates = pd.to_datetime(opportunities["fill_trade_date"], utc=True, errors="raise")
    outer_start = pd.Timestamp(str(outer["start"]), tz="UTC")
    outer_end = pd.Timestamp(str(outer["end"]), tz="UTC")
    history = dec.completed_history_before(opportunities, outer_start)
    outer_history_outcome = _history_outcome_diagnostics(history, outer_start)
    outer_frame = opportunities.loc[(fill_dates >= outer_start) & (fill_dates <= outer_end)].copy()
    if history.empty or outer_frame.empty:
        raise RuntimeError(f"issue428 outer support missing for {outer_id}")
    state, annotated_history, annotated_outer = _annotated_context(
        history,
        outer_frame,
        signal_columns,
        prereg,
        outcome_available_before=outer_start,
    )
    outer_meta_states, outer_meta_diag = _fit_meta_states(
        annotated_history,
        signal_columns,
        prereg,
        outcome_available_before=outer_start,
    )
    selected_policy = _score_policy(
        annotated_outer, selected_config, state, outer_meta_states, signal_columns
    )
    baseline_config = configs["baseline"]
    baseline_policy = _score_policy(
        annotated_outer, baseline_config, state, outer_meta_states, signal_columns
    )
    selected_score, selected_summary, effective = _score_policy_frame(
        sessions, selected_policy,
        start=str(outer["start"]), end=str(outer["end"]),
        risk=risk, costs=base_costs, multiplier=multiplier, prereg=prereg,
    )
    baseline_score, baseline_summary, baseline_effective = _score_policy_frame(
        sessions, baseline_policy,
        start=str(outer["start"]), end=str(outer["end"]),
        risk=risk, costs=base_costs, multiplier=multiplier, prereg=prereg,
    )
    cost_sensitivity: dict[str, object] = {}
    for profile_name, profile in cost_profiles.items():
        score, summary, _ = _score_policy_frame(
            sessions, selected_policy,
            start=str(outer["start"]), end=str(outer["end"]),
            risk=risk, costs=profile, multiplier=multiplier, prereg=prereg,
        )
        cost_sensitivity[str(profile_name)] = {
            "score": score,
            "replay_summary": summary,
        }
    delta = _score_delta(selected_score, baseline_score)
    remove_one = _score_remove_one_input_ablations(
        selected_config=selected_config,
        state=state,
        annotated_history=annotated_history,
        annotated_outer=annotated_outer,
        outer_meta_states=outer_meta_states,
        signal_columns=signal_columns,
        sessions=sessions,
        start=str(outer["start"]),
        end=str(outer["end"]),
        risk=risk,
        costs=base_costs,
        multiplier=multiplier,
        prereg=prereg,
        selected_score=selected_score,
        outer_id=outer_id,
        trials=trials,
    )
    kill_regression = bool(selected_summary.get("kill_triggered")) and not bool(
        baseline_summary.get("kill_triggered")
    )
    outer_result = {
        "outer_block": dict(outer),
        "signal_columns": list(signal_columns),
        "selection_years": selection_years,
        "selected": selected,
        "selected_config": selected_config.__dict__,
        "selected_score": selected_score,
        "matched_baseline_score": baseline_score,
        "delta": delta,
        "selected_effective_sample": effective,
        "baseline_effective_sample": baseline_effective,
        "selected_replay_summary": selected_summary,
        "baseline_replay_summary": baseline_summary,
        "kill_trigger_regression": kill_regression,
        "cost_sensitivity": cost_sensitivity,
        "remove_one_input_ablations": remove_one,
        "confidence_calibration": {
            "prequential": calibration,
            "outer_fit": outer_meta_diag,
        },
        "policy_history_outcome_diagnostics": {
            "prequential": history_outcomes,
            "outer_fit": outer_history_outcome,
        },
    }
    trials.append(_trial("outer_evaluation", {
        "outer_block_id": outer_id,
        "config_id": selected_config.config_id,
        "status": "complete",
        "role": "selected_policy",
        "score": selected_score,
        "effective_sample": effective,
        "replay_summary": selected_summary,
    }))
    trials.append(_trial("outer_evaluation", {
        "outer_block_id": outer_id,
        "config_id": "baseline",
        "status": "complete",
        "role": "matched_baseline",
        "score": baseline_score,
        "effective_sample": baseline_effective,
        "replay_summary": baseline_summary,
    }))
    return outer_result


def _score_oi_lane_block(
    *,
    block_id: str,
    opportunities: pd.DataFrame,
    base_signal_columns: Sequence[str],
    oi_column: str,
    sessions: pd.DataFrame,
    cfg: Mapping[str, Any],
    prereg: Mapping[str, Any],
    risk: object,
    cost_profiles: Mapping[str, object],
    trials: list[dict[str, object]],
) -> dict[str, object]:
    block = _oi_block_spec(block_id, cfg)
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    base_costs = cost_profiles["base"]
    fill_dates = pd.to_datetime(opportunities["fill_trade_date"], utc=True, errors="raise")
    start = pd.Timestamp(str(block["start"]), tz="UTC")
    end = pd.Timestamp(str(block["end"]), tz="UTC")
    history = dec.completed_history_before(opportunities, start)
    history_outcome = _history_outcome_diagnostics(history, start)
    scored = opportunities.loc[(fill_dates >= start) & (fill_dates <= end)].copy()
    if history.empty or scored.empty:
        raise RuntimeError(f"issue428 OI support missing for {block_id}")

    state, annotated_history, annotated_scored = _annotated_context(
        history,
        scored,
        base_signal_columns,
        prereg,
        outcome_available_before=start,
    )
    oi_state = dec.fit_conditional_signal_state(
        annotated_history,
        column=oi_column,
        minimum_history_rows=int(prereg["open_interest_lane"]["minimum_history_rows"]),
        minimum_state_rows=int(prereg["signal_state_contract"]["minimum_state_rows"]),
        outcome_available_before=start,
    )
    annotated_history = dec.annotate_conditional_signal(annotated_history, oi_state)
    annotated_scored = dec.annotate_conditional_signal(annotated_scored, oi_state)
    oi_z = f"{oi_column}__z"
    oi_favored = f"{oi_column}__favored"
    oi_cross = f"{oi_column}__z_x_favored_fraction"
    annotated_history[oi_cross] = annotated_history[oi_z] * annotated_history["favored_fraction"]
    annotated_scored[oi_cross] = annotated_scored[oi_z] * annotated_scored["favored_fraction"]

    baseline_config = dec.DecisionConfig("baseline", "baseline", 0)
    baseline_policy = dec.apply_issue428_policy(annotated_scored, baseline_config, state)
    baseline_score, baseline_summary, baseline_effective = _score_policy_frame(
        sessions,
        baseline_policy,
        start=str(block["start"]),
        end=str(block["end"]),
        risk=risk,
        costs=base_costs,
        multiplier=multiplier,
        prereg=prereg,
    )
    trials.append(_trial("oi_matched_baseline", {
        "outer_block_id": block_id,
        "config_id": "baseline",
        "status": "complete",
        "score": baseline_score,
        "effective_sample": baseline_effective,
    }))

    candidates: dict[str, object] = {}
    gate_policy = _apply_admission_mask(
        annotated_scored,
        annotated_scored[oi_favored].astype(bool),
        reason="issue428_oi_unfavored_state_abstain",
    )
    candidate_policies: dict[str, tuple[pd.DataFrame, dict[str, object]]] = {
        "oi_favored_state_gate": (
            gate_policy,
            {"kind": "oi_favored_state_gate", "threshold": oi_state.threshold, "favored": oi_state.favored},
        )
    }

    contract = prereg["confidence_contract"]
    extra_meta_features = [oi_z, oi_cross]
    try:
        oi_meta = dec.fit_meta_confidence(
            annotated_history,
            signal_columns=base_signal_columns,
            mode="interactions",
            minimum_train_rows=int(contract["minimum_meta_train_rows"]),
            minimum_calibration_rows=int(contract["minimum_calibration_rows"]),
            outcome_available_before=start,
            extra_feature_columns=extra_meta_features,
        )
    except dec.Issue428DecisionError as exc:
        oi_meta = None
        meta_failure = str(exc)
    else:
        meta_failure = None
        probabilities = dec.predict_meta_confidence(
            annotated_scored,
            oi_meta,
            signal_columns=base_signal_columns,
            extra_feature_columns=extra_meta_features,
        )
        for threshold in (0.55, 0.60):
            config_id = f"meta_interactions_oi_p{int(threshold * 100):03d}"
            policy = _apply_admission_mask(
                annotated_scored,
                probabilities.ge(threshold),
                reason=f"issue428_{config_id}_abstain",
            )
            candidate_policies[config_id] = (
                policy,
                {
                    "kind": "meta_interactions_oi",
                    "probability_threshold": threshold,
                    "meta_diagnostics": _meta_diagnostics(oi_meta),
                    "extra_meta_features": extra_meta_features,
                },
            )

    expected = set(map(str, prereg["open_interest_lane"]["incremental_candidates"]))
    observed = set(candidate_policies)
    if meta_failure is None and observed != expected:
        raise RuntimeError(f"issue428 OI candidate identity changed: {sorted(observed)}")
    if meta_failure is not None:
        for config_id in sorted(expected - observed):
            trials.append(_trial("oi_incremental_outer", {
                "outer_block_id": block_id,
                "config_id": config_id,
                "status": "ineligible",
                "reason": meta_failure,
            }))

    for config_id, (policy, diagnostics) in candidate_policies.items():
        score, replay_summary, effective = _score_policy_frame(
            sessions,
            policy,
            start=str(block["start"]),
            end=str(block["end"]),
            risk=risk,
            costs=base_costs,
            multiplier=multiplier,
            prereg=prereg,
        )
        cost_sensitivity: dict[str, object] = {}
        for profile_name, profile in cost_profiles.items():
            profile_score, profile_summary, _ = _score_policy_frame(
                sessions,
                policy,
                start=str(block["start"]),
                end=str(block["end"]),
                risk=risk,
                costs=profile,
                multiplier=multiplier,
                prereg=prereg,
            )
            cost_sensitivity[str(profile_name)] = {
                "score": profile_score,
                "replay_summary": profile_summary,
            }
        candidates[config_id] = {
            "diagnostics": diagnostics,
            "score": score,
            "delta_vs_matched_baseline": _score_delta(score, baseline_score),
            "effective_sample": effective,
            "replay_summary": replay_summary,
            "cost_sensitivity": cost_sensitivity,
        }
        trials.append(_trial("oi_incremental_outer", {
            "outer_block_id": block_id,
            "config_id": config_id,
            "status": "complete",
            "score": score,
            "effective_sample": effective,
        }))

    return {
        "outer_block": dict(block),
        "parent_outer_block_id": _oi_parent_outer_id(block_id),
        "oi_representation": oi_column,
        "oi_state": oi_state.__dict__,
        "uniform_value_claim_allowed": False,
        "matched_baseline_score": baseline_score,
        "matched_baseline_replay_summary": baseline_summary,
        "matched_baseline_effective_sample": baseline_effective,
        "candidates": candidates,
        "meta_failure": meta_failure,
        "policy_history_outcome_diagnostics": history_outcome,
    }


def _score_open_interest_lane(
    *,
    features: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: Mapping[str, Any],
    prereg: Mapping[str, Any],
    selected_reps: Mapping[str, Mapping[str, str]],
    selected_models: Mapping[str, Mapping[str, object]],
    matched_controls: Mapping[str, Mapping[str, object]],
    risk: object,
    cost_profiles: Mapping[str, object],
    trials: list[dict[str, object]],
) -> dict[str, object]:
    results: dict[str, object] = {}
    base_costs = cost_profiles["base"]
    for block_id in map(str, prereg["open_interest_lane"]["eligible_outer_blocks"]):
        parent_outer = _oi_parent_outer_id(block_id)
        base_signal_columns = _signal_columns_for_outer(parent_outer, selected_reps)
        oi_column = _oi_representation_for_block(block_id, selected_reps)
        block = _oi_block_spec(block_id, cfg)
        opportunities = _build_outer_opportunities(
            target_outer_id=block_id,
            target_block=block,
            features=features,
            sessions=sessions,
            cfg=cfg,
            selected_config=selected_models[parent_outer],
            matched_config=matched_controls[parent_outer]["config"],
            signal_columns=base_signal_columns,
            context_only_signal_columns=[oi_column],
            round_trip_usd=float(base_costs.round_trip_usd),
        )
        results[block_id] = _score_oi_lane_block(
            block_id=block_id,
            opportunities=opportunities,
            base_signal_columns=base_signal_columns,
            oi_column=oi_column,
            sessions=sessions,
            cfg=cfg,
            prereg=prereg,
            risk=risk,
            cost_profiles=cost_profiles,
            trials=trials,
        )
    return {
        "uniform_value_claim_allowed": False,
        "blocks": results,
    }


def score_decision_optimization() -> dict[str, object]:
    preflight_report = _require_preflight()
    prereg, features, sessions, _families, support = _load_inputs()
    cfg = json.loads(PHASE2.read_text(encoding="utf-8"))
    risk, cost_profiles = _load_inherited_risk_and_costs(cfg)
    features = _features_with_volatility_tail(features)
    selected_reps = _selected_representations()
    selected_models = _selected_model_configs()
    matched_controls = v2.load_issue426_outer_matched_controls(ISSUE425)
    base_costs = cost_profiles["base"]
    trials: list[dict[str, object]] = []
    outer_results: dict[str, object] = {}

    for outer_id in map(str, prereg["chronology"]["fusion_outer_blocks"]):
        signal_columns = _signal_columns_for_outer(outer_id, selected_reps)
        opportunities = _build_outer_opportunities(
            target_outer_id=outer_id,
            features=features,
            sessions=sessions,
            cfg=cfg,
            selected_config=selected_models[outer_id],
            matched_config=matched_controls[outer_id]["config"],
            signal_columns=signal_columns,
            round_trip_usd=float(base_costs.round_trip_usd),
        )
        outer_results[outer_id] = _score_outer_lane(
            outer_id=outer_id,
            opportunities=opportunities,
            signal_columns=signal_columns,
            sessions=sessions,
            cfg=cfg,
            prereg=prereg,
            risk=risk,
            cost_profiles=cost_profiles,
            trials=trials,
        )

    open_interest_lane = _score_open_interest_lane(
        features=features,
        sessions=sessions,
        cfg=cfg,
        prereg=prereg,
        selected_reps=selected_reps,
        selected_models=selected_models,
        matched_controls=matched_controls,
        risk=risk,
        cost_profiles=cost_profiles,
        trials=trials,
    )
    outer_block_stability = {
        outer_id: {
            "selected_config_id": str(item["selected_config"]["config_id"]),
            "mean_monthly_net_return_delta": float(item["delta"]["mean_monthly_net_return"]),
            "total_net_pnl_usd_delta": float(item["delta"]["total_net_pnl_usd"]),
            "effective_sample_pass": bool(item["selected_effective_sample"]["passes_outer_minimums"]),
            "kill_trigger_regression": bool(item["kill_trigger_regression"]),
        }
        for outer_id, item in outer_results.items()
    }

    deltas = [
        float(item["delta"]["mean_monthly_net_return"])
        for item in outer_results.values()
    ]
    effective_pass = all(
        bool(item["selected_effective_sample"]["passes_outer_minimums"])
        for item in outer_results.values()
    )
    kill_regression = any(
        bool(item["kill_trigger_regression"]) for item in outer_results.values()
    )
    promotion = {
        "mean_outer_monthly_net_return_delta": float(np.mean(deltas)),
        "nonnegative_outer_fraction": float(np.mean([value >= 0.0 for value in deltas])),
        "effective_sample_pass": effective_pass,
        "kill_trigger_regression": kill_regression,
    }
    gate = prereg["promotion_gate"]
    promotion["passes"] = bool(
        promotion["mean_outer_monthly_net_return_delta"] > float(gate["mean_outer_monthly_net_return_delta_gt"])
        and promotion["nonnegative_outer_fraction"] >= float(gate["nonnegative_outer_fraction_gte"])
        and (effective_pass or not bool(gate["effective_sample_required"]))
        and (not kill_regression or bool(gate["kill_trigger_regression_allowed"]))
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "issue": 428,
        "evidence_class": "development",
        "claim_boundary": prereg["claim_boundary"],
        "protected_confirmation_accessed": False,
        "outer_results": outer_results,
        "outer_block_stability": outer_block_stability,
        "open_interest_lane": open_interest_lane,
        "promotion": promotion,
        "disposition": "RETAIN_CONDITIONAL_DECISION_RULE" if promotion["passes"] else "HOLD_NO_ROBUST_CONDITIONAL_GAIN",
        "trial_count": len(trials),
        "trial_accounting": {
            "frozen_fusion_configuration_budget": int(prereg["budgets"]["fusion_configurations"]),
            "frozen_oi_incremental_configuration_budget": int(prereg["budgets"]["oi_incremental_configurations"]),
            "ledger_rows": len(trials),
            "complete": sum(row.get("status") == "complete" for row in trials),
            "ineligible": sum(row.get("status") == "ineligible" for row in trials),
            "failed": sum(row.get("status") == "failed" for row in trials),
        },
        "source_evidence_sha256": stable_sha(support["source_evidence"]),
        "preflight_sha256": preflight_report["preflight_sha256"],
        "prereg_sha256": sha256_file(PREREG),
        "runner_sha256": sha256_file(Path(__file__)),
        "decision_code_sha256": sha256_file(REPO / "src/commodity/v2_decision_optimization.py"),
    }
    LEDGER.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in trials),
        encoding="utf-8",
        newline="\n",
    )
    result["trial_ledger_file_sha256"] = sha256_file(LEDGER)
    result["result_sha256"] = stable_sha({
        key: value for key, value in result.items() if key != "result_sha256"
    })
    RESULT.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--preflight"
    if mode == "--preflight":
        report = preflight()
        print(json.dumps({
            "status": report["status"],
            "scoring_performed": report["scoring_performed"],
            "feature_rows": report["feature_rows"],
            "session_rows": report["session_rows"],
            "candidate_count": report["candidate_count"],
            "failures": report["failures"],
            "preflight_sha256": report["preflight_sha256"],
        }, indent=2, sort_keys=True, default=str))
        if report["status"] != "PASS":
            raise SystemExit(2)
        return
    if mode != "--score":
        raise SystemExit("usage: run_issue428_decision_optimization.py [--preflight|--score]")
    result = score_decision_optimization()
    print(json.dumps({
        "disposition": result["disposition"],
        "promotion": result["promotion"],
        "trial_count": result["trial_count"],
        "result_sha256": result["result_sha256"],
    }, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
