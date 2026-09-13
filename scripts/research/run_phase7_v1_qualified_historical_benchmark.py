from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.kronos import resolve_kronos_artifacts, verify_kronos_source_checkout
from commodity.market_only_phase2 import (
    _build_segmented_decision_origins,
    _canonicalize_one_origin_per_fill,
    build_phase2_inputs,
    reconstruct_market_history,
)
from commodity.phase2_runtime import Phase2CheckpointStore, Phase2Telemetry
from commodity.stacking_policy import (
    PolicyConfig,
    build_prospective_policy_decisions,
    replay_post_freeze_policy,
)
from commodity.trading_decision_v0 import ExecutionCostAssumptions, PaperRiskPolicy

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME = ROOT / "research/programmes/003-natural-gas-trading-decision-system"
PREREG = PROGRAMME / "phase7-v1-qualified-historical-benchmark-prereg-v1.json"
PREREG_SHA256 = "d41b5c84d3187baeb9575fbd8c18037e0711a2e5e73163bf71401b79821b1d1d"
PHASE2_CONFIG = ROOT / "config/phase2_market_only.json"
TRADING_POLICY = ROOT / "config/trading-policy.json"
MODELS_CONFIG = ROOT / "config/models.json"
PHASE4_SCRIPT = ROOT / "scripts/research/run_phase4_foundation_specialists.py"
DERIVATION_SCRIPT = ROOT / "scripts/research/derive_phase7_prospective_decision.py"
DEV_SPECIALISTS = ROOT / ".work/changes/358-foundation-specialists"
POLICY_ID = "s-veto__l-none__p-half__u-none"
COMPARATOR_ID = "s-none__l-none__p-none__u-none"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_script(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_preregistered() -> dict[str, Any]:
    observed = _sha256(PREREG)
    if observed != PREREG_SHA256:
        raise RuntimeError("qualified historical benchmark preregistration identity drift")
    prereg = _load_json(PREREG)
    if prereg.get("status") != "authorized_pending_execution":
        raise RuntimeError("qualified historical benchmark is not authorized for execution")
    return prereg


def _extended_phase2_config(prereg: dict[str, Any]) -> dict[str, Any]:
    cfg = json.loads(json.dumps(_load_json(PHASE2_CONFIG)))
    cfg["evidence_boundary"]["last_allowed_trade_date"] = prereg["window"]["latest_source_trade_date"]
    return cfg


def _risk_policy() -> PaperRiskPolicy:
    policy = _load_json(TRADING_POLICY)["paper_risk_policies"]["phase1_standard_ng_v0"]
    return PaperRiskPolicy(
        capital_usd=float(policy["capital_usd"]),
        max_contracts=int(policy["max_standard_contracts"]),
        daily_loss_fraction=float(policy["daily_loss_fraction"]),
        peak_drawdown_kill_fraction=float(policy["peak_drawdown_kill_fraction"]),
        after_kill=str(policy["after_kill"]),
        live_trading_allowed=False,
    )


def _base_costs(cfg: dict[str, Any]) -> ExecutionCostAssumptions:
    profile = cfg["cost_profiles"]["base"]
    return ExecutionCostAssumptions(
        commission_usd_per_side=float(profile["commission_usd_per_side"]),
        exchange_clearing_fees_usd_per_side=float(profile["exchange_clearing_fees_usd_per_side"]),
        half_spread_ticks_per_side=float(profile["half_spread_ticks_per_side"]),
        slippage_ticks_per_side=float(profile["slippage_ticks_per_side"]),
        initial_margin_usd_per_contract=float(profile["initial_margin_usd_per_contract"]),
        tick_value_usd=float(cfg["execution_contract"]["tick_value_usd"]),
    )

def prepare_full_checkpoint(
    raw_root: Path,
    checkpoint_root: Path,
    prereg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = _extended_phase2_config(prereg)
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    telemetry = Phase2Telemetry(checkpoint_root / "telemetry.jsonl", heartbeat_seconds=15, echo=True)
    store = Phase2CheckpointStore(checkpoint_root, telemetry)
    with store.run_lock():
        canonical, market, bars, _ = reconstruct_market_history(
            raw_root,
            cfg,
            checkpoint_store=store,
            telemetry=telemetry,
        )
        session, features = build_phase2_inputs(canonical, market, bars, cfg, telemetry=telemetry)
    inputs = checkpoint_root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    session.to_parquet(inputs / "session-path.parquet", index=False)
    features.to_parquet(inputs / "features.parquet", index=False)
    return session, features


def benchmark_origins(
    session: pd.DataFrame,
    features: pd.DataFrame,
    prereg: dict[str, Any],
) -> pd.DataFrame:
    cfg = _extended_phase2_config(prereg)
    origins, _ = _build_segmented_decision_origins(
        session,
        features,
        horizon_sessions=int(cfg["execution_contract"]["horizon_sessions"]),
    )
    origins, _ = _canonicalize_one_origin_per_fill(origins)
    fill = pd.to_datetime(origins["fill_trade_date"], utc=True, errors="raise")
    target_end = pd.to_datetime(origins["target_end_timestamp"], utc=True, errors="raise")
    target = pd.to_numeric(origins["target_path_move_per_mmbtu"], errors="coerce")
    start = pd.Timestamp(prereg["window"]["start_trade_date"], tz="UTC")
    latest = pd.Timestamp(prereg["window"]["latest_source_trade_date"], tz="UTC")
    mask = fill.ge(start) & target_end.le(latest) & target.notna()
    selected = origins.loc[mask].copy().sort_values("fill_timestamp", kind="stable")
    if selected.empty:
        raise RuntimeError("qualified historical benchmark has no eligible origins")
    if selected["fill_timestamp"].duplicated().any():
        raise RuntimeError("qualified historical benchmark origins are not unique by fill")
    selected["benchmark_origin_index"] = np.arange(len(selected), dtype=int)
    return selected.reset_index(drop=True)


def _initialise_feature_checkpoint(destination: Path, source: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def generate_one_step_specialists(    checkpoint_root: Path,
    runtime_root: Path,
    *,
    timesfm_runtime_root: Path,
    timesfm_cache_dir: Path,
    kronos_source_root: Path,
    kronos_cache_dir: Path,
) -> tuple[Path, Path]:
    phase4 = _load_script(PHASE4_SCRIPT, "phase4_specialists_for_v1_benchmark")
    timesfm_output = runtime_root / "timesfm-features.csv"
    kronos_output = runtime_root / "kronos-features.csv"
    _initialise_feature_checkpoint(timesfm_output, DEV_SPECIALISTS / "timesfm-features.csv")
    _initialise_feature_checkpoint(kronos_output, DEV_SPECIALISTS / "kronos-features.csv")
    phase4._generate_timesfm_features(
        checkpoint_root,
        timesfm_runtime_root,
        timesfm_cache_dir,
        timesfm_output,
        context=128,
        batch_size=32,
        max_origins=None,
    )
    previous = os.environ.get("COMMODITY_KRONOS_CACHE_DIR")
    os.environ["COMMODITY_KRONOS_CACHE_DIR"] = str(kronos_cache_dir.resolve())
    try:
        phase4._generate_kronos_features(
            checkpoint_root,
            kronos_source_root,
            kronos_output,
            batch_size=32,
            max_new_origins=None,
        )
    finally:
        if previous is None:
            os.environ.pop("COMMODITY_KRONOS_CACHE_DIR", None)
        else:
            os.environ["COMMODITY_KRONOS_CACHE_DIR"] = previous
    return timesfm_output, kronos_output


def _ohlcv_from_checkpoint(checkpoint_root: Path) -> pd.DataFrame:
    paths = sorted((checkpoint_root / "reconstruction/partitions").glob("*-ohlcv.parquet"))
    if not paths:
        raise RuntimeError("qualified benchmark checkpoint has no OHLCV partitions")
    frame = pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    return frame.sort_values(["contract_id", "trade_date"], kind="stable").reset_index(drop=True)


def _path_active(index: int, prereg: dict[str, Any]) -> bool:
    rule = prereg["specialist_contract"]["kronos_path"]
    cycle = int(rule["cycle_length"])
    residues = {int(item) for item in rule["active_residues_zero_based"]}
    return int(index) % cycle in residues


def generate_kronos_path_features(
    checkpoint_root: Path,
    origins: pd.DataFrame,
    runtime_root: Path,
    *,    prereg: dict[str, Any],
    kronos_source_root: Path,
    kronos_cache_dir: Path,
) -> Path:
    output = runtime_root / "kronos-path-features.csv"
    session = pd.read_parquet(checkpoint_root / "inputs/session-path.parquet")
    session["trade_date"] = pd.to_datetime(session["trade_date"], utc=True, errors="raise")
    ohlcv = _ohlcv_from_checkpoint(checkpoint_root)
    selected = session[["trade_date", "contract_id"]].drop_duplicates("trade_date")
    contract_by_date = selected.set_index("trade_date")["contract_id"].astype(str)
    grouped = {str(key): group for key, group in ohlcv.groupby("contract_id", sort=False)}
    cases: list[dict[str, Any]] = []
    for row in origins.itertuples(index=False):
        if not _path_active(int(row.benchmark_origin_index), prereg):
            continue
        origin_date = pd.Timestamp(row.trade_date)
        contract = str(contract_by_date.loc[origin_date])
        history_all = grouped.get(contract)
        if history_all is None:
            raise RuntimeError(f"missing Kronos history for {contract}")
        history = history_all.loc[history_all["trade_date"].le(origin_date)].tail(512)
        if len(history) < 20:
            raise RuntimeError(f"insufficient Kronos history for {contract}")
        fill_index = int(row.fill_index)
        path_dates = pd.DatetimeIndex(session.iloc[fill_index : fill_index + 5]["trade_date"])
        if len(path_dates) != 5:
            raise RuntimeError("benchmark Kronos path lacks five future sessions")
        values = history[["open", "high", "low", "close", "volume"]].astype(float)
        values.index = pd.DatetimeIndex(history["trade_date"])
        cases.append({"row": row, "contract": contract, "history": values, "path_dates": path_dates})
    models = _load_json(MODELS_CONFIG)
    model_cfg = models["models"]["kronos_base"]
    verify_kronos_source_checkout(kronos_source_root, model_cfg["source_revision"])
    previous = os.environ.get("COMMODITY_KRONOS_CACHE_DIR")
    os.environ["COMMODITY_KRONOS_CACHE_DIR"] = str(kronos_cache_dir.resolve())
    try:
        artifacts = resolve_kronos_artifacts(model_cfg)
    finally:
        if previous is None:
            os.environ.pop("COMMODITY_KRONOS_CACHE_DIR", None)
        else:
            os.environ["COMMODITY_KRONOS_CACHE_DIR"] = previous
    if str(kronos_source_root.resolve()) not in sys.path:
        sys.path.insert(0, str(kronos_source_root.resolve()))
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer = KronosTokenizer.from_pretrained(artifacts["tokenizer"]["snapshot_path"])
    model = Kronos.from_pretrained(artifacts["model"]["snapshot_path"])
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=int(model_cfg["max_context"]))
    profile = models["kronos_confirmation_profile"]["upstream_usage_defaults"]
    torch.manual_seed(0)
    rows: list[dict[str, Any]] = []
    by_length: dict[int, list[dict[str, Any]]] = {}
    for case in cases:
        by_length.setdefault(len(case["history"]), []).append(case)
    for history_length in sorted(by_length):
        group = by_length[history_length]
        for start in range(0, len(group), 16):
            batch = group[start : start + 16]
            forecasts = predictor.predict_batch(
                [case["history"] for case in batch],
                [pd.Series(case["history"].index) for case in batch],
                [pd.Series(case["path_dates"]) for case in batch],
                pred_len=5,
                T=float(profile["T"]),
                top_p=float(profile["top_p"]),
                sample_count=int(profile["sample_count"]),
                verbose=False,
            )
            for case, forecast in zip(batch, forecasts, strict=True):
                if len(forecast) != 5 or "close" not in forecast:
                    raise RuntimeError("Kronos benchmark path output is malformed")
                current_close = float(case["history"]["close"].iloc[-1])
                terminal = float(forecast["close"].iloc[-1]) / current_close - 1.0
                row = case["row"]
                rows.append({
                    "trade_date": pd.Timestamp(row.trade_date).isoformat(),
                    "prediction_time": pd.Timestamp(row.signal_timestamp).isoformat(),
                    "contract_id": case["contract"],
                    "benchmark_origin_index": int(row.benchmark_origin_index),
                    "pred_terminal_return": terminal,
                })
    pd.DataFrame(rows).sort_values("benchmark_origin_index").to_csv(output, index=False, lineterminator="\n")
    return output

def build_frozen_forecasts(origins: pd.DataFrame, training_checkpoint: Path) -> pd.DataFrame:
    derivation = _load_script(DERIVATION_SCRIPT, "phase7_derivation_for_v1_benchmark")
    training = derivation.load_verified_training_origins(training_checkpoint)
    candidate = derivation._frozen_candidate()
    model = derivation._candidate_model(candidate)
    if model is None:
        raise RuntimeError("frozen v1 market model is unavailable")
    columns = derivation.frozen_feature_columns()
    model.fit(training[columns], training["target_path_move_per_mmbtu"].astype(float))
    predicted = model.predict(origins[columns])
    cfg = _load_json(PHASE2_CONFIG)
    multiplier = float(cfg["execution_contract"]["contract_multiplier_mmbtu"])
    frame = origins[[
        "trade_date", "signal_timestamp", "fill_trade_date", "fill_timestamp", "target_end_timestamp"
    ]].copy()
    frame["forecast_id"] = [
        derivation._forecast_id("histgb-core-v1", pd.Timestamp(value))
        for value in frame["fill_timestamp"]
    ]
    frame["predicted_path_move_per_mmbtu"] = np.asarray(predicted, dtype=float)
    frame["predicted_gross_pnl_usd"] = frame["predicted_path_move_per_mmbtu"] * multiplier
    return frame


def _policy(config_id: str) -> PolicyConfig:
    if config_id == POLICY_ID:
        return PolicyConfig(config_id, "veto", "none", "half", "none")
    if config_id == COMPARATOR_ID:
        return PolicyConfig(config_id, "none", "none", "none", "none")
    raise ValueError(f"unsupported frozen benchmark policy: {config_id}")

def build_decisions(
    forecasts: pd.DataFrame,
    origins: pd.DataFrame,
    timesfm_path: Path,
    kronos_path: Path,
    kronos_terminal_path: Path,
    config_id: str,
) -> pd.DataFrame:
    origin_dates = set(pd.to_datetime(origins["trade_date"], utc=True))
    timesfm = pd.read_csv(timesfm_path)
    kronos = pd.read_csv(kronos_path)
    terminal = pd.read_csv(kronos_terminal_path)
    for frame in (timesfm, kronos, terminal):
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    timesfm = timesfm.loc[timesfm["trade_date"].isin(origin_dates)].copy()
    kronos = kronos.loc[kronos["trade_date"].isin(origin_dates)].copy()
    expected = len(origins)
    if len(timesfm) != expected or len(kronos) != expected:
        raise RuntimeError("qualified benchmark one-step specialist coverage is incomplete")
    cfg = _load_json(PHASE2_CONFIG)
    costs = _base_costs(cfg)
    return build_prospective_policy_decisions(
        forecasts,
        timesfm,
        kronos,
        terminal,
        config=_policy(config_id),
        costs=costs,
        uncertainty_state=None,
    )


def replay_window(
    session: pd.DataFrame,
    decisions: pd.DataFrame,
    origins: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = session.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"], utc=True, errors="raise")
    first_fill = pd.to_datetime(origins["fill_trade_date"], utc=True).min()
    last_target = pd.to_datetime(origins["target_end_timestamp"], utc=True).max()
    work = work.loc[work["trade_date"].between(first_fill, last_target)].reset_index(drop=True)
    if work.empty:
        raise RuntimeError("qualified benchmark replay window is empty")
    cfg = _load_json(PHASE2_CONFIG)
    return replay_post_freeze_policy(
        work,
        decisions,
        _risk_policy(),
        _base_costs(cfg),
        contract_multiplier=float(cfg["execution_contract"]["contract_multiplier_mmbtu"]),
        enforce_risk=True,
    )


def summarize_ledger(ledger: pd.DataFrame, summary: dict[str, Any]) -> dict[str, Any]:
    frame = ledger.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True, errors="raise")
    monthly = frame.set_index("trade_date")["net_pnl_usd"].resample("ME").sum()
    position = pd.to_numeric(frame["target_position"], errors="raise")
    by_side: dict[str, float] = {}
    side_counts: dict[str, int] = {}
    for name, mask in {
        "long": position.gt(0),
        "short": position.lt(0),
        "flat": position.eq(0),
    }.items():
        by_side[name] = float(frame.loc[mask, "net_pnl_usd"].sum())
        side_counts[name] = int(mask.sum())
    elapsed_days = max(1, int((frame["trade_date"].max() - frame["trade_date"].min()).days) + 1)
    annualized = float(summary["net_pnl_usd"] / summary["starting_capital_usd"] * 365.25 / elapsed_days)
    return {
        "net_pnl_usd_after_frozen_trading_costs": float(summary["net_pnl_usd"]),
        "ending_equity_usd": float(summary["ending_equity_usd"]),
        "total_transaction_cost_usd": float(summary["total_transaction_cost_usd"]),
        "maximum_peak_drawdown_fraction": float(summary["max_drawdown_fraction"]),
        "annualized_simple_return": annualized,
        "average_calendar_month_net_pnl_usd": float(monthly.mean()),
        "positive_calendar_month_count": int(monthly.gt(0).sum()),
        "negative_calendar_month_count": int(monthly.lt(0).sum()),
        "zero_calendar_month_count": int(monthly.eq(0).sum()),
        "calendar_month_count": len(monthly),
        "execution_side_count": float(summary["execution_side_count"]),
        "active_session_counts": side_counts,
        "net_pnl_usd_by_position_side": by_side,
        "risk_kill_triggered": bool(summary["kill_triggered"]),
        "risk_kill_reason": summary["kill_reason"],
        "risk_shutdown_sessions": int(summary["risk_shutdown_sessions"]),
        "first_trade_date": frame["trade_date"].min().date().isoformat(),
        "last_trade_date": frame["trade_date"].max().date().isoformat(),
    }


def execute_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    prereg = _assert_preregistered()
    if args.result.exists():
        raise RuntimeError("qualified historical benchmark result already exists; one-shot rerun refused")
    session, features = prepare_full_checkpoint(args.raw_root, args.runtime_root / "checkpoint", prereg)
    origins = benchmark_origins(session, features, prereg)
    timesfm, kronos = generate_one_step_specialists(
        args.runtime_root / "checkpoint",
        args.runtime_root,
        timesfm_runtime_root=args.timesfm_runtime_root,
        timesfm_cache_dir=args.timesfm_cache_dir,
        kronos_source_root=args.kronos_source_root,
        kronos_cache_dir=args.kronos_cache_dir,
    )
    path_features = generate_kronos_path_features(
        args.runtime_root / "checkpoint",
        origins,
        args.runtime_root,
        prereg=prereg,
        kronos_source_root=args.kronos_source_root,
        kronos_cache_dir=args.kronos_cache_dir,
    )
    forecasts = build_frozen_forecasts(origins, args.training_checkpoint_root)
    v1_decisions = build_decisions(forecasts, origins, timesfm, kronos, path_features, POLICY_ID)
    comparator_decisions = build_decisions(
        forecasts, origins, timesfm, kronos, path_features, COMPARATOR_ID
    )
    v1_ledger, v1_summary = replay_window(session, v1_decisions, origins)
    comparator_ledger, comparator_summary = replay_window(session, comparator_decisions, origins)
    args.runtime_root.mkdir(parents=True, exist_ok=True)
    v1_ledger_path = args.runtime_root / "v1-ledger.csv"
    comparator_ledger_path = args.runtime_root / "market-only-comparator-ledger.csv"
    v1_ledger.to_csv(v1_ledger_path, index=False, lineterminator="\n")
    comparator_ledger.to_csv(comparator_ledger_path, index=False, lineterminator="\n")
    result = {
        "schema_version": 1,
        "benchmark_id": prereg["benchmark_id"],
        "status": "complete",
        "evidence_class": prereg["evidence_class"],
        "clean_confirmation_eligible": False,
        "preregistration_sha256": PREREG_SHA256,
        "protected_historical_outcomes_accessed": True,
        "v1_frozen_unchanged": True,
        "benchmark_origin_count": len(origins),
        "kronos_path_origin_count": int(sum(_path_active(i, prereg) for i in range(len(origins)))),
        "v1": summarize_ledger(v1_ledger, v1_summary),
        "market_only_no_modifier_comparator": summarize_ledger(comparator_ledger, comparator_summary),
        "runtime_evidence": {
            "timesfm_features_sha256": _sha256(timesfm),
            "kronos_features_sha256": _sha256(kronos),
            "kronos_path_features_sha256": _sha256(path_features),
            "v1_ledger_sha256": _sha256(v1_ledger_path),
            "market_only_comparator_ledger_sha256": _sha256(comparator_ledger_path),
            "training_checkpoint_root": str(args.training_checkpoint_root.resolve()),
            "benchmark_checkpoint_root": str((args.runtime_root / "checkpoint").resolve()),
        },
        "interpretation_boundary": prereg["interpretation_rule"],
        "prospective_evidence_rule": prereg["prospective_evidence_rule"],
        "live_capital_authorized": False,
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.result.with_suffix(args.result.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(args.result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the preregistered frozen-v1 qualified historical benchmark.")
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--training-checkpoint-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--timesfm-runtime-root", type=Path, required=True)
    parser.add_argument("--timesfm-cache-dir", type=Path, required=True)
    parser.add_argument("--kronos-source-root", type=Path, required=True)
    parser.add_argument("--kronos-cache-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    result = execute_benchmark(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
