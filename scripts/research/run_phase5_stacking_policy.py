from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pandas as pd

from commodity.market_only_phase2 import forecast_candidate_window
from commodity.stacking_policy import (
    PolicyConfig,
    build_policy_decisions,
    build_policy_grid,
    fit_timesfm_uncertainty_state,
    replay_fractional_policy,
    select_policy_from_prior_oos,
    validate_phase5_evidence_boundary,
)
from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_REPO = ROOT.parents[2] if ROOT.parent.name == "worktrees" else ROOT
CHANGE = ROOT / ".work/changes/359-stacking-policy"
RUNTIME = RUNTIME_REPO / ".work/runtime/359-stacking-policy/phase5-inputs"
OUT = CHANGE / "phase5-results"
OUT.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _costs(profile: dict[str, Any], tick_value: float) -> ExecutionCostAssumptions:
    return ExecutionCostAssumptions(
        commission_usd_per_side=float(profile["commission_usd_per_side"]),
        exchange_clearing_fees_usd_per_side=float(profile["exchange_clearing_fees_usd_per_side"]),
        half_spread_ticks_per_side=float(profile["half_spread_ticks_per_side"]),
        slippage_ticks_per_side=float(profile["slippage_ticks_per_side"]),
        initial_margin_usd_per_contract=float(profile["initial_margin_usd_per_contract"]),
        tick_value_usd=float(tick_value),
    )


def _risk() -> PaperRiskPolicy:
    policy = _load_json(ROOT / "config/trading-policy.json")["paper_risk_policies"]["phase1_standard_ng_v0"]
    return PaperRiskPolicy(
        capital_usd=float(policy["capital_usd"]),
        max_contracts=int(policy["max_standard_contracts"]),
        daily_loss_fraction=float(policy["daily_loss_fraction"]),
        peak_drawdown_kill_fraction=float(policy["peak_drawdown_kill_fraction"]),
        after_kill=str(policy["after_kill"]),
        live_trading_allowed=False,
    )


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    session = pd.read_csv(RUNTIME / "session-path.csv")
    origins = pd.read_csv(RUNTIME / "origins.csv")
    metadata = _load_json(RUNTIME / "metadata.json")
    for column in ("trade_date", "session_open"):
        if column in session:
            session[column] = pd.to_datetime(session[column], utc=True, errors="raise")
    for column in ("trade_date", "signal_timestamp", "fill_trade_date", "fill_timestamp", "target_end_timestamp"):
        if column in origins:
            origins[column] = pd.to_datetime(origins[column], utc=True, errors="raise")
    validate_phase5_evidence_boundary(session)
    validate_phase5_evidence_boundary(origins)
    return session, origins, metadata


def _specialists() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    phase4 = ROOT / ".work/changes/358-foundation-specialists"
    timesfm = pd.read_csv(phase4 / "timesfm-features.csv")
    kronos = pd.read_csv(phase4 / "kronos-features.csv")
    path = pd.read_csv(phase4 / "kronos-path-features.csv")
    for frame in (timesfm, kronos, path):
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    return timesfm, kronos, path


def _forecast_year(
    origins: pd.DataFrame,
    candidate: dict[str, Any],
    features: list[str],
    *,
    year: int,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    forecasts = forecast_candidate_window(
        origins,
        candidate,
        features,
        start_timestamp=pd.Timestamp(f"{year}-01-01", tz="UTC"),
        boundary_timestamp=pd.Timestamp(f"{year + 1}-01-01", tz="UTC"),
        contract_multiplier=float(cfg["execution_contract"]["contract_multiplier_mmbtu"]),
        min_train_rows=int(cfg["execution_contract"]["minimum_training_rows"]),
        horizon_sessions=int(cfg["execution_contract"]["horizon_sessions"]),
    )
    origin_dates = origins[["signal_timestamp", "trade_date"]].drop_duplicates("signal_timestamp")
    forecasts = forecasts.merge(origin_dates, on="signal_timestamp", how="left", validate="many_to_one")
    if forecasts["trade_date"].isna().any():
        raise RuntimeError(f"cannot recover origin trade date for {year}")
    return forecasts


def _year_path(session: pd.DataFrame, year: int) -> pd.DataFrame:
    frame = session.loc[session["trade_date"].dt.year.eq(year)].copy()
    if frame.empty:
        raise RuntimeError(f"no replay sessions for {year}")
    return frame.reset_index(drop=True)


def _score_one(
    session: pd.DataFrame,
    forecasts: pd.DataFrame,
    timesfm: pd.DataFrame,
    kronos: pd.DataFrame,
    path_features: pd.DataFrame,
    config: PolicyConfig,
    uncertainty_state: dict[str, Any],
    risk: PaperRiskPolicy,
    costs: ExecutionCostAssumptions,
    multiplier: float,
    year: int,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    decisions = build_policy_decisions(
        forecasts, timesfm, kronos, path_features,
        config=config, costs=costs, uncertainty_state=uncertainty_state,
    )
    replay_path = _year_path(session, year)
    standard, standard_summary = replay_fractional_policy(
        replay_path, decisions, risk, costs,
        contract_multiplier=multiplier, enforce_risk=True,
    )
    continuous, continuous_summary = replay_fractional_policy(
        replay_path, decisions, risk, costs,
        contract_multiplier=multiplier, enforce_risk=False,
    )
    score = {
        "config_id": config.config_id,
        "year": year,
        "net_pnl_usd": standard_summary["net_pnl_usd"],
        "transaction_cost_usd": standard_summary["total_transaction_cost_usd"],
        "max_drawdown_fraction": standard_summary["max_drawdown_fraction"],
        "execution_side_count": standard_summary["execution_side_count"],
        "signal_abstention_sessions": standard_summary["signal_abstention_sessions"],
        "risk_shutdown_sessions": standard_summary["risk_shutdown_sessions"],
        "kill_triggered": standard_summary["kill_triggered"],
        "continuous_net_pnl_usd": continuous_summary["net_pnl_usd"],
        "continuous_max_drawdown_fraction": continuous_summary["max_drawdown_fraction"],
        "complexity": config.complexity,
    }
    return score, standard, continuous


def _config_by_id(grid: list[PolicyConfig]) -> dict[str, PolicyConfig]:
    return {item.config_id: item for item in grid}


def _ablation_ids(config: PolicyConfig) -> dict[str, str]:
    fields = {
        "timesfm_short": "short_mode",
        "kronos_long": "long_mode",
        "kronos_path": "path_mode",
        "timesfm_uncertainty": "uncertainty_mode",
    }
    result: dict[str, str] = {}
    for label, field in fields.items():
        if getattr(config, field) == "none":
            continue
        ablated = replace(config, **{field: "none"})
        result[label] = (
            f"s-{ablated.short_mode}__l-{ablated.long_mode}__p-{ablated.path_mode}__u-{ablated.uncertainty_mode}"
        )
    return result


def main() -> None:
    cfg = _load_json(ROOT / "config/phase2_market_only.json")
    prereg = _load_json(CHANGE / "phase5-preregistration.json")
    session, origins, metadata = _load_inputs()
    timesfm, kronos, path_features = _specialists()
    grid = build_policy_grid()
    by_id = _config_by_id(grid)
    candidate = next(item for item in cfg["candidates"] if item["id"] == prereg["baseline"]["candidate_id"])
    feature_columns = list(cfg["feature_sets"][candidate["feature_set"]])
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    risk = _risk()
    base_costs = _costs(cfg["cost_profiles"]["base"], cfg["execution_contract"]["tick_value_usd"])

    specialist_files = {
        key: ROOT / value["path"]
        for key, value in prereg["specialist_artifacts"].items()
    }
    for key, path in specialist_files.items():
        if _sha256(path) != prereg["specialist_artifacts"][key]["sha256"]:
            raise RuntimeError(f"specialist artifact hash mismatch: {key}")

    years = list(range(2014, 2023))
    forecasts_by_year = {
        year: _forecast_year(origins, candidate, feature_columns, year=year, cfg=cfg)
        for year in years
    }
    print("FORECASTS_READY", {year: len(frame) for year, frame in forecasts_by_year.items()})

    calibration_rows: list[pd.DataFrame] = []
    uncertainty_by_year: dict[int, dict[str, Any]] = {}
    baseline_config = by_id["s-none__l-none__p-none__u-none"]
    for year in years:
        history = pd.concat(calibration_rows, ignore_index=True) if calibration_rows else pd.DataFrame(
            columns=["fill_timestamp", "timesfm_interval_width", "baseline_abs_error"]
        )
        uncertainty_by_year[year] = fit_timesfm_uncertainty_state(
            history,
            boundary_timestamp=pd.Timestamp(f"{year}-01-01", tz="UTC"),
            minimum_rows=int(prereg["uncertainty_calibration"]["minimum_prior_oos_rows"]),
        )
        decisions = build_policy_decisions(
            forecasts_by_year[year], timesfm, kronos, path_features,
            config=baseline_config, costs=base_costs, uncertainty_state=None,
        )
        calibration_rows.append(
            decisions[["fill_timestamp", "timesfm_interval_width", "baseline_abs_error"]].copy()
        )

    scores: list[dict[str, Any]] = []
    standard_ledgers: dict[tuple[str, int], pd.DataFrame] = {}
    continuous_ledgers: dict[tuple[str, int], pd.DataFrame] = {}
    for year in years:
        for config in grid:
            score, standard, continuous = _score_one(
                session, forecasts_by_year[year], timesfm, kronos, path_features,
                config, uncertainty_by_year[year], risk, base_costs, multiplier, year,
            )
            scores.append(score)
            standard_ledgers[(config.config_id, year)] = standard
            continuous_ledgers[(config.config_id, year)] = continuous
        print("YEAR_SCORED", year)

    score_frame = pd.DataFrame(scores)
    score_frame.to_csv(OUT / "policy-year-scores.csv", index=False, lineterminator="\n")
    outer_selections: list[dict[str, Any]] = []
    for block in cfg["validation"]["outer_blocks"]:
        start_year = int(str(block["start"])[:4])
        end_year = int(str(block["end"])[:4])
        selected = select_policy_from_prior_oos(score_frame, outer_start_year=start_year)
        selected_id = str(selected["config_id"])
        observed = score_frame.loc[
            score_frame["config_id"].eq(selected_id)
            & score_frame["year"].between(start_year, end_year)
        ].copy()
        outer_selections.append(
            {
                "block_id": block["id"],
                "selected_before_block": selected_id,
                "selection_years": selected["years"],
                "observed_years": observed["year"].astype(int).tolist(),
                "observed_net_pnl_usd": float(observed["net_pnl_usd"].sum()),
                "observed_continuous_net_pnl_usd": float(observed["continuous_net_pnl_usd"].sum()),
                "observed_max_drawdown_fraction": float(observed["max_drawdown_fraction"].max()),
                "observed_transaction_cost_usd": float(observed["transaction_cost_usd"].sum()),
            }
        )

    final_selection = select_policy_from_prior_oos(score_frame, outer_start_year=2023)
    final_id = str(final_selection["config_id"])
    final_config = by_id[final_id]
    final_scores = score_frame.loc[score_frame["config_id"].eq(final_id)].copy()

    selected_standard = pd.concat(
        [standard_ledgers[(final_id, year)].assign(score_year=year) for year in years],
        ignore_index=True,
    )
    selected_continuous = pd.concat(
        [continuous_ledgers[(final_id, year)].assign(score_year=year) for year in years],
        ignore_index=True,
    )
    selected_standard.to_csv(OUT / "selected-standard-ledger.csv", index=False, lineterminator="\n")
    selected_continuous.to_csv(OUT / "selected-continuous-ledger.csv", index=False, lineterminator="\n")

    pnl_by_side = (
        selected_standard.assign(
            side=selected_standard["target_position"].map(
                lambda value: "long" if value > 0 else ("short" if value < 0 else "flat")
            )
        )
        .groupby("side", dropna=False)["net_pnl_usd"]
        .sum()
        .to_dict()
    )
    yearly = {
        str(int(row.year)): float(row.net_pnl_usd)
        for row in final_scores.itertuples(index=False)
    }
    positive_total = sum(max(0.0, value) for value in yearly.values())
    concentration = (
        max((max(0.0, value) for value in yearly.values()), default=0.0) / positive_total
        if positive_total > 0 else None
    )
    ablations = {}
    for label, ablated_id in _ablation_ids(final_config).items():
        base_total = float(final_scores["net_pnl_usd"].sum())
        ablated_total = float(score_frame.loc[score_frame["config_id"].eq(ablated_id), "net_pnl_usd"].sum())
        ablations[label] = {
            "ablated_config_id": ablated_id,
            "selected_total_net_pnl_usd": base_total,
            "ablated_total_net_pnl_usd": ablated_total,
            "incremental_net_pnl_usd": base_total - ablated_total,
        }

    cost_sensitivity: dict[str, Any] = {}
    for profile_id, profile in cfg["cost_profiles"].items():
        profile_costs = _costs(profile, cfg["execution_contract"]["tick_value_usd"])
        profile_rows = []
        for year in years:
            decisions = build_policy_decisions(
                forecasts_by_year[year], timesfm, kronos, path_features,
                config=final_config, costs=profile_costs,
                uncertainty_state=uncertainty_by_year[year],
            )
            _, summary = replay_fractional_policy(
                _year_path(session, year), decisions, risk, profile_costs,
                contract_multiplier=multiplier, enforce_risk=True,
            )
            profile_rows.append(summary)
        cost_sensitivity[profile_id] = {
            "net_pnl_usd": float(sum(row["net_pnl_usd"] for row in profile_rows)),
            "transaction_cost_usd": float(sum(row["total_transaction_cost_usd"] for row in profile_rows)),
            "kill_years": int(sum(bool(row["kill_triggered"]) for row in profile_rows)),
        }

    all_forecasts = pd.concat(forecasts_by_year.values(), ignore_index=True)
    signal_time = pd.to_datetime(all_forecasts["signal_timestamp"], utc=True)
    fill_time = pd.to_datetime(all_forecasts["fill_timestamp"], utc=True)
    latency_seconds = (fill_time - signal_time).dt.total_seconds()
    metric_reconciliation = {
        "selected_year_score_sum_net_pnl_usd": float(final_scores["net_pnl_usd"].sum()),
        "selected_ledger_sum_net_pnl_usd": float(selected_standard["net_pnl_usd"].sum()),
        "difference_usd": float(final_scores["net_pnl_usd"].sum() - selected_standard["net_pnl_usd"].sum()),
    }
    if abs(metric_reconciliation["difference_usd"]) > 1e-8:
        raise RuntimeError("selected score and ledger P&L do not reconcile")

    result: dict[str, Any] = {
        "schema_version": 1,
        "programme_id": "003-natural-gas-trading-decision-system",
        "phase": 5,
        "issue": 359,
        "status": "development_policy_candidate_selected",
        "protected_confirmation_accessed": False,
        "evidence_boundary": {"last_allowed_trade_date": "2022-12-31", "role": "adaptive_development"},
        "preregistration_sha256": _sha256(CHANGE / "phase5-preregistration.json"),
        "input_identity": {
            "metadata": metadata,
            "session_path_sha256": _sha256(RUNTIME / "session-path.csv"),
            "origins_sha256": _sha256(RUNTIME / "origins.csv"),
            "specialist_artifacts": {key: _sha256(path) for key, path in specialist_files.items()},
        },
        "search": {
            "configuration_count": len(grid),
            "score_years": years,
            "attempt_count": len(score_frame),
            "primary_objective": prereg["selection"]["primary_objective"],
            "failed_configuration_count": 0,
        },
        "outer_selections": outer_selections,
        "selected_candidate": {
            "config": asdict(final_config),
            "selection_years": final_selection["years"],
            "ranking": final_selection["ranking"],
            "yearly_net_pnl_usd": yearly,
            "total_net_pnl_usd": float(final_scores["net_pnl_usd"].sum()),
            "total_continuous_net_pnl_usd": float(final_scores["continuous_net_pnl_usd"].sum()),
            "max_yearly_drawdown_fraction": float(final_scores["max_drawdown_fraction"].max()),
            "transaction_cost_usd": float(final_scores["transaction_cost_usd"].sum()),
        },
        "diagnostics": {
            "long_short_flat_net_pnl_usd": {str(k): float(v) for k, v in pnl_by_side.items()},
            "cost_sensitivity": cost_sensitivity,
            "remove_one_specialist_ablations": ablations,
            "signal_abstention_sessions": int(selected_standard["signal_abstained"].sum()),
            "risk_shutdown_sessions": int(selected_standard["risk_shutdown"].sum()),
            "standard_kill_years": int(final_scores["kill_triggered"].sum()),
            "execution_side_count": float(final_scores["execution_side_count"].sum()),
            "profit_concentration_largest_positive_year_fraction": concentration,
            "prediction_to_fill_latency_seconds": {
                "minimum": float(latency_seconds.min()),
                "median": float(latency_seconds.median()),
                "maximum": float(latency_seconds.max()),
            },
            "target_horizon_sessions": int(cfg["execution_contract"]["horizon_sessions"]),
            "uncertainty_state_by_year": uncertainty_by_year,
            "adaptive_history": "Phase-4 hypotheses and Phase-5 policy are development-adaptive; no clean confirmation claim.",
            "metric_reconciliation": metric_reconciliation,
        },
        "artifacts": {
            "policy_year_scores": "phase5-results/policy-year-scores.csv",
            "selected_standard_ledger": "phase5-results/selected-standard-ledger.csv",
            "selected_continuous_ledger": "phase5-results/selected-continuous-ledger.csv",
        },
        "claim_boundary": "development_policy_selection_only_no_clean_confirmation_claim",
        "next_evidence_stage": "Phase 6/7 may consume exactly this selected configuration under their own registered authority; protected 2023+ confirmation remains sealed until its explicit gate.",
    }
    result_path = CHANGE / "phase5-stacking-policy-result.json"
    result_path.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    print("PHASE5_SELECTED", final_id, result["selected_candidate"]["total_net_pnl_usd"])
    print("RESULT", result_path)


if __name__ == "__main__":
    main()
