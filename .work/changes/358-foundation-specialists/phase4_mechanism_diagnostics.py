from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.market_only_phase2 import (
    _build_segmented_decision_origins,
    _canonicalize_one_origin_per_fill,
    _load_inherited_risk_and_costs,
    _score_candidate_window,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    for column in ("trade_date", "prediction_time", "generated_at"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True, format="mixed")
    return frame


def _candidate_config(enriched: pd.DataFrame) -> dict[str, Any]:
    cfg0 = json.loads((REPO_ROOT / "config" / "phase2_market_only.json").read_text())
    cfg = json.loads(json.dumps(cfg0))
    core = list(cfg0["feature_sets"]["core"])
    kronos = [c for c in enriched.columns if c.startswith("feature_kronos_")]
    timesfm = [c for c in enriched.columns if c.startswith("feature_timesfm_")]
    cfg["feature_sets"] = {
        "core": core,
        "core_kronos": [*core, *kronos],
        "core_timesfm": [*core, *timesfm],
        "core_both": [*core, *kronos, *timesfm],
    }
    frozen = next(x for x in cfg0["candidates"] if x["id"] == "histgb-core-v1")
    cfg["candidates"] = [json.loads(json.dumps(frozen))]
    for candidate_id, feature_set, rank in (
        ("histgb-core-kronos-v1", "core_kronos", 5),
        ("histgb-core-timesfm-v1", "core_timesfm", 5),
        ("histgb-core-both-v1", "core_both", 6),
    ):
        candidate = json.loads(json.dumps(frozen))
        candidate.update(id=candidate_id, feature_set=feature_set, simplicity_rank=rank)
        cfg["candidates"].append(candidate)
    return cfg


def _build_context(
    checkpoint_root: Path, timesfm_path: Path, kronos_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    market = pd.read_parquet(checkpoint_root / "inputs" / "features.parquet")
    session = pd.read_parquet(checkpoint_root / "inputs" / "session-path.parquet")
    market["trade_date"] = pd.to_datetime(market["trade_date"], utc=True)
    market["available_at"] = pd.to_datetime(market["available_at"], utc=True)
    timesfm = _load_frame(timesfm_path)
    kronos = _load_frame(kronos_path)
    tf_cols = ["timesfm_point_return", "timesfm_q10_return", "timesfm_q90_return", "timesfm_interval_width"]
    kr_cols = ["kronos_close_return", "kronos_range_pct"]
    timesfm_features = timesfm[["trade_date", *tf_cols]].rename(
        columns={column: f"feature_{column}" for column in tf_cols}
    )
    kronos_features = kronos[["trade_date", *kr_cols]].rename(
        columns={column: f"feature_{column}" for column in kr_cols}
    )
    enriched = market.merge(kronos_features, on="trade_date", validate="one_to_one")
    enriched = enriched.merge(timesfm_features, on="trade_date", validate="one_to_one")
    if len(enriched) != len(market):
        raise RuntimeError("specialist feature coverage is incomplete")
    return market, session, timesfm, kronos, enriched


def _period_frames(
    origins: pd.DataFrame,
    session: pd.DataFrame,
    cfg: dict[str, Any],
) -> tuple[dict[str, pd.DataFrame], dict[str, float]]:
    risk, costs = _load_inherited_risk_and_costs(cfg)
    candidates = [c for c in cfg["candidates"] if c["id"] != "histgb-core-both-v1"]
    frames: dict[str, list[pd.DataFrame]] = {str(c["id"]): [] for c in candidates}
    totals: dict[str, float] = {str(c["id"]): 0.0 for c in candidates}
    for block in cfg["validation"]["outer_blocks"]:
        for candidate in candidates:
            _, forecasts, ledger = _score_candidate_window(
                origins,
                session,
                candidate,
                cfg,
                costs["base"],
                risk,
                start_date=block["start"],
                end_date=block["end"],
            )
            candidate_id = str(candidate["id"])
            totals[candidate_id] += float(ledger["net_pnl_usd"].sum())
            pnl = ledger.groupby("forecast_id", as_index=False).agg(
                period_net_pnl_usd=("net_pnl_usd", "sum"),
                period_transaction_cost_usd=("transaction_cost_usd", "sum"),
                period_sessions=("trade_date", "size"),
            )
            frame = forecasts.merge(pnl, on="forecast_id", validate="one_to_one")
            frame["outer_block_id"] = str(block["id"])
            frames[str(candidate["id"])].append(frame)
    combined = {key: pd.concat(value, ignore_index=True) for key, value in frames.items()}
    return combined, totals


def _sign(values: pd.Series) -> pd.Series:
    numeric = values.astype(float)
    return pd.Series(np.where(numeric > 0, "long", np.where(numeric < 0, "short", "flat")), index=values.index)


def _bucket(values: pd.Series, low: float, high: float) -> pd.Series:
    numeric = values.astype(float)
    return pd.Series(
        np.where(numeric <= low, "low", np.where(numeric <= high, "mid", "high")),
        index=values.index,
    )


def _corr(left: pd.Series, right: pd.Series, method: str) -> float | None:
    value = left.astype(float).corr(right.astype(float), method=method)
    return None if pd.isna(value) else float(value)


def _segment_summary(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, group in frame.groupby(column, dropna=False):
        result[str(key)] = {
            "origins": len(group),
            "baseline_net_pnl_usd": float(group["baseline_period_net_pnl_usd"].sum()),
            "specialist_net_pnl_usd": float(group["specialist_period_net_pnl_usd"].sum()),
            "incremental_net_pnl_usd": float(group["incremental_period_net_pnl_usd"].sum()),
            "baseline_direction_accuracy": float(group["baseline_direction_correct"].mean()),
            "specialist_direction_accuracy": float(group["specialist_direction_correct"].mean()),
        }
    return result


def _block_segment_summary(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    return {
        str(block): _segment_summary(group, column)
        for block, group in frame.groupby("outer_block_id", dropna=False)
    }


def _diagnose(
    *,
    name: str,
    specialist_candidate: str,
    raw: pd.DataFrame,
    raw_point_column: str,
    raw_uncertainty_column: str,
    baseline: pd.DataFrame,
    specialist: pd.DataFrame,
    baseline_total_net_pnl_usd: float,
    specialist_total_net_pnl_usd: float,
    market: pd.DataFrame,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    keys = ["outer_block_id", "signal_timestamp", "fill_timestamp", "fill_contract_id"]
    base = baseline[keys + ["prediction", "actual_path_move_per_mmbtu", "period_net_pnl_usd"]].rename(
        columns={"prediction": "baseline_prediction", "period_net_pnl_usd": "baseline_period_net_pnl_usd"}
    )
    challenger = specialist[keys + ["prediction", "period_net_pnl_usd"]].rename(
        columns={"prediction": "specialist_prediction", "period_net_pnl_usd": "specialist_period_net_pnl_usd"}
    )
    frame = base.merge(challenger, on=keys, validate="one_to_one")
    market_join = market[["trade_date", "available_at", "feature_vol_20", "feature_ret_20"]].copy()
    market_join = market_join.rename(columns={"available_at": "signal_timestamp", "trade_date": "feature_trade_date"})
    frame = frame.merge(market_join, on="signal_timestamp", validate="many_to_one")
    raw_join = raw[["trade_date", raw_point_column, raw_uncertainty_column]].copy()
    raw_join = raw_join.rename(columns={"trade_date": "feature_trade_date"})
    frame = frame.merge(raw_join, on="feature_trade_date", validate="many_to_one")
    frame["incremental_period_net_pnl_usd"] = (
        frame["specialist_period_net_pnl_usd"] - frame["baseline_period_net_pnl_usd"]
    )
    frame["baseline_side"] = _sign(frame["baseline_prediction"])
    frame["raw_specialist_side"] = _sign(frame[raw_point_column])
    frame["specialist_side"] = _sign(frame["specialist_prediction"])
    actual_side = _sign(frame["actual_path_move_per_mmbtu"])
    frame["baseline_direction_correct"] = frame["baseline_side"].eq(actual_side)
    frame["specialist_direction_correct"] = frame["specialist_side"].eq(actual_side)
    frame["raw_agreement"] = np.where(
        frame["baseline_side"].eq(frame["raw_specialist_side"]), "agree", "disagree"
    )
    frame["direction_effect"] = np.select(
        [~frame["baseline_direction_correct"] & frame["specialist_direction_correct"],
         frame["baseline_direction_correct"] & ~frame["specialist_direction_correct"]],
        ["corrected", "harmed"],
        default="unchanged",
    )
    frame["model_shift"] = frame["specialist_prediction"] - frame["baseline_prediction"]
    frame["baseline_error"] = frame["actual_path_move_per_mmbtu"] - frame["baseline_prediction"]
    frame["year"] = pd.to_datetime(frame["fill_timestamp"], utc=True).dt.year.astype(str)
    frame["magnitude_bucket"] = ""
    frame["uncertainty_bucket"] = ""
    frame["volatility_regime"] = ""
    thresholds: dict[str, Any] = {}
    for block in cfg["validation"]["outer_blocks"]:
        block_id = str(block["id"])
        start = pd.Timestamp(block["start"], tz="UTC")
        prior_raw = raw.loc[raw["trade_date"] < start]
        prior_market = market.loc[market["trade_date"] < start]
        mag_low, mag_high = prior_raw[raw_point_column].abs().quantile([1 / 3, 2 / 3]).tolist()
        unc_low, unc_high = prior_raw[raw_uncertainty_column].quantile([1 / 3, 2 / 3]).tolist()
        vol_low, vol_high = prior_market["feature_vol_20"].quantile([1 / 3, 2 / 3]).tolist()
        mask = frame["outer_block_id"].eq(block_id)
        frame.loc[mask, "magnitude_bucket"] = _bucket(frame.loc[mask, raw_point_column].abs(), mag_low, mag_high)
        frame.loc[mask, "uncertainty_bucket"] = _bucket(frame.loc[mask, raw_uncertainty_column], unc_low, unc_high)
        frame.loc[mask, "volatility_regime"] = _bucket(frame.loc[mask, "feature_vol_20"], vol_low, vol_high)
        thresholds[block_id] = {
            "magnitude_terciles": [float(mag_low), float(mag_high)],
            "uncertainty_terciles": [float(unc_low), float(unc_high)],
            "volatility_terciles": [float(vol_low), float(vol_high)],
        }
    frame["trend_regime"] = np.where(frame["feature_ret_20"] >= 0, "nonnegative_20d", "negative_20d")
    month = pd.to_datetime(frame["feature_trade_date"], utc=True).dt.month
    frame["season_regime"] = np.where(month.isin([11, 12, 1, 2, 3]), "winter_nov_mar", "non_winter")
    abs_increment = frame["incremental_period_net_pnl_usd"].abs().sort_values(ascending=False)
    abs_total = float(abs_increment.sum())
    concentration = {
        "largest_origin_abs_increment_fraction": 0.0 if abs_total == 0 else float(abs_increment.iloc[:1].sum() / abs_total),
        "top5_origin_abs_increment_fraction": 0.0 if abs_total == 0 else float(abs_increment.iloc[:5].sum() / abs_total),
        "top10_origin_abs_increment_fraction": 0.0 if abs_total == 0 else float(abs_increment.iloc[:10].sum() / abs_total),
    }
    groups = {}
    for column in (
        "raw_agreement",
        "baseline_side",
        "raw_specialist_side",
        "direction_effect",
        "magnitude_bucket",
        "uncertainty_bucket",
        "outer_block_id",
        "year",
        "volatility_regime",
        "trend_regime",
        "season_regime",
    ):
        groups[column] = _segment_summary(frame, column)
    cross_block = {
        column: _block_segment_summary(frame, column)
        for column in (
            "raw_agreement",
            "baseline_side",
            "magnitude_bucket",
            "uncertainty_bucket",
            "volatility_regime",
            "trend_regime",
            "season_regime",
        )
    }
    attributed_incremental = float(frame["incremental_period_net_pnl_usd"].sum())
    full_incremental = float(specialist_total_net_pnl_usd - baseline_total_net_pnl_usd)
    return {
        "specialist": name,
        "candidate_id": specialist_candidate,
        "origins": len(frame),
        "aggregate_incremental_net_pnl_usd": full_incremental,
        "attributed_incremental_net_pnl_usd": attributed_incremental,
        "unattributed_incremental_net_pnl_usd": full_incremental - attributed_incremental,
        "model_shift_vs_baseline_error_pearson": _corr(frame["model_shift"], frame["baseline_error"], "pearson"),
        "model_shift_vs_baseline_error_spearman": _corr(frame["model_shift"], frame["baseline_error"], "spearman"),
        "model_shift_help_rate": float((np.sign(frame["model_shift"]) == np.sign(frame["baseline_error"])).mean()),
        "thresholds": thresholds,
        "concentration": concentration,
        "segments": groups,
        "cross_block_segments": cross_block,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded Phase-4 specialist mechanism diagnostics")
    parser.add_argument("--phase2-checkpoint-root", type=Path, required=True)
    parser.add_argument("--timesfm-feature-output", type=Path, required=True)
    parser.add_argument("--kronos-feature-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    market, session, timesfm, kronos, enriched = _build_context(
        args.phase2_checkpoint_root,
        args.timesfm_feature_output,
        args.kronos_feature_output,
    )
    cfg = _candidate_config(enriched)
    origins, _ = _build_segmented_decision_origins(
        session,
        enriched,
        horizon_sessions=int(cfg["execution_contract"]["horizon_sessions"]),
    )
    origins, canonicalization = _canonicalize_one_origin_per_fill(origins)
    frames, totals = _period_frames(origins, session, cfg)
    baseline = frames["histgb-core-v1"]
    payload = {
        "schema_version": 1,
        "authority_clarification": "github-issue-358-comment-5632161050",
        "evidence_role": "exploratory_mechanism_diagnostics_not_promotion_selection",
        "protected_confirmation_accessed": False,
        "origin_canonicalization": canonicalization,
        "policy_optimization_deferred_to": "github-issue-359",
        "timesfm": _diagnose(
            name="timesfm_2_5",
            specialist_candidate="histgb-core-timesfm-v1",
            raw=timesfm,
            raw_point_column="timesfm_point_return",
            raw_uncertainty_column="timesfm_interval_width",
            baseline=baseline,
            specialist=frames["histgb-core-timesfm-v1"],
            baseline_total_net_pnl_usd=totals["histgb-core-v1"],
            specialist_total_net_pnl_usd=totals["histgb-core-timesfm-v1"],
            market=market,
            cfg=cfg,
        ),
        "kronos_one_step": _diagnose(
            name="kronos_base_one_step",
            specialist_candidate="histgb-core-kronos-v1",
            raw=kronos,
            raw_point_column="kronos_close_return",
            raw_uncertainty_column="kronos_range_pct",
            baseline=baseline,
            specialist=frames["histgb-core-kronos-v1"],
            baseline_total_net_pnl_usd=totals["histgb-core-v1"],
            specialist_total_net_pnl_usd=totals["histgb-core-kronos-v1"],
            market=market,
            cfg=cfg,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "output": str(args.output),
        "timesfm_incremental": payload["timesfm"]["aggregate_incremental_net_pnl_usd"],
        "kronos_incremental": payload["kronos_one_step"]["aggregate_incremental_net_pnl_usd"],
        "protected_confirmation_accessed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
