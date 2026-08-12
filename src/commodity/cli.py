from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from commodity.config import (
    REPO_ROOT,
    data_config,
    experiment_config,
    model_config,
    policy_config,
    signal_policy_config,
    simulation_config,
)
from commodity.data import CsvMarketDataSource, YFinanceMarketDataSource, save_raw
from commodity.evaluation import evaluate_predictions, walk_forward_predict
from commodity.features import make_supervised
from commodity.market_data import DataContractViolation, assert_canonical_market_ready
from commodity.massive import MassiveFuturesClient, fetch_massive_canonical_history
from commodity.models import baseline_factory
from commodity.policy import assert_model_cannot_submit_orders
from commodity.provenance import sha256_file, utc_now, write_json
from commodity.records import build_baseline_record
from commodity.saxo import SaxoSimMarketDataClient, probe_henry_hub
from commodity.simulation import simulate_forecasts


def _fetch_market(args: argparse.Namespace) -> None:
    cfg = data_config()["sources"]["market_bootstrap"]
    frame = YFinanceMarketDataSource(cfg["symbol"]).fetch(args.start, args.end)
    output = Path(args.output)
    save_raw(frame, output)
    fetched_at = utc_now()
    write_json(output.with_suffix(".meta.json"), {
        "fetched_at_utc": fetched_at, "provider": cfg["provider"], "symbol": cfg["symbol"],
        "requested_start": args.start, "requested_end": args.end, "rows": len(frame),
        "sha256": sha256_file(output), "vintage": f"retrieval_snapshot:{fetched_at}",
        "authoritative_for_execution": False,
    })
    print(f"saved_rows={len(frame)} path={output}")


def _fetch_canonical_market(args: argparse.Namespace) -> None:
    cfg = data_config()
    source = cfg["sources"]["market_canonical"]
    fetched_at = utc_now()
    frame, metadata = fetch_massive_canonical_history(
        MassiveFuturesClient(),
        cfg["canonical_contract_schema"],
        product_code=source["product_code"],
        start_trade_date=args.start,
        end_trade_date=args.end,
        retrieved_at=fetched_at,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    metadata.update({
        "requested_start": args.start,
        "requested_end": args.end,
        "rows": len(frame),
        "canonical_evidence": False,
        "evidence_tier": "canonical_price_history_roll_unvalidated",
    })
    write_json(output.with_suffix(".meta.json"), metadata)
    print(f"saved_rows={len(frame)} path={output}")


def _run_baseline(args: argparse.Namespace) -> None:
    frame = CsvMarketDataSource(Path(args.input)).fetch(args.start, args.end)
    x, y = make_supervised(frame)
    cfg = model_config()["models"]
    factory = baseline_factory(args.model, cfg)
    pred = walk_forward_predict(factory, x, y, args.initial_train, args.retrain_every)
    metrics = evaluate_predictions(pred)
    run_dir = Path(args.output)
    run_dir.mkdir(parents=True, exist_ok=True)
    pred.to_csv(run_dir / "predictions.csv", index_label="date")
    write_json(run_dir / "metrics.json", metrics)
    record = build_baseline_record(
        Path(args.input), run_dir, args.model, metrics, x.index, args.initial_train
    )
    write_json(run_dir / "experiment.json", record)
    print(json.dumps(metrics, indent=2))


def _simulate(args: argparse.Namespace) -> None:
    pred = pd.read_csv(args.predictions, index_col="date", parse_dates=["date"])
    policy_cfg = signal_policy_config()
    simulation_cfg = simulation_config()
    policy = policy_cfg["policies"][args.policy]
    simulation = simulation_cfg["simulations"][args.simulation]
    path, metrics = simulate_forecasts(pred, policy, simulation)
    run_dir = Path(args.output)
    run_dir.mkdir(parents=True, exist_ok=True)
    path.to_csv(run_dir / "simulation.csv", index_label="date")
    canonical_evidence = bool(simulation["canonical_evidence_allowed"])
    write_json(run_dir / "simulation_metrics.json", {
        "schema_version": 1,
        "policy_id": args.policy,
        "simulation_id": args.simulation,
        "canonical_evidence": canonical_evidence,
        "evidence_tier": "canonical" if canonical_evidence else "research_noncanonical",
        "metrics": metrics,
    })
    print(json.dumps(metrics, indent=2))


def _probe_saxo_market(args: argparse.Namespace) -> None:
    report = probe_henry_hub(
        SaxoSimMarketDataClient(),
        continuous_uic=args.continuous_uic,
        max_contracts=args.max_contracts,
    )
    if args.output:
        write_json(Path(args.output), report)
    print(json.dumps(report, indent=2))


def _doctor(_: argparse.Namespace) -> None:
    assert_model_cannot_submit_orders()
    data_cfg = data_config()
    simulation_cfg = simulation_config()
    default_simulation = simulation_cfg["simulations"][simulation_cfg["default_simulation"]]
    try:
        assert_canonical_market_ready(data_cfg)
        canonical_ready = True
        canonical_reason = None
    except DataContractViolation as exc:
        canonical_ready = False
        canonical_reason = str(exc)
    print(json.dumps({
        "repo": str(REPO_ROOT),
        "default_model": model_config()["default_model"],
        "market_source": data_cfg["sources"]["market_bootstrap"],
        "research_backtesting_available": simulation_cfg["semantics"]["research_backtesting_available"],
        "canonical_market_evidence_allowed": canonical_ready,
        "canonical_market_evidence_reason": canonical_reason,
        "default_simulation_canonical_evidence_allowed": default_simulation["canonical_evidence_allowed"],
        "execution": policy_config()["execution"],
    }, indent=2))


def build_parser() -> argparse.ArgumentParser:
    exp = experiment_config()
    period = exp["research_period"]
    walk = exp["walk_forward"]
    models_cfg = model_config()
    baseline_choices = sorted(
        name
        for name, cfg in models_cfg["models"].items()
        if cfg.get("enabled", False) and cfg.get("baseline_implementation")
    )
    if models_cfg["default_model"] not in baseline_choices:
        raise ValueError("Default model is not configured as an enabled baseline")
    parser = argparse.ArgumentParser(prog="commodity")
    sub = parser.add_subparsers(required=True)
    fetch = sub.add_parser("fetch-market")
    fetch.add_argument("--start", default=period["start"])
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--output", default=str(REPO_ROOT / "data/raw/ng_f_daily.csv"))
    fetch.set_defaults(func=_fetch_market)

    canonical = sub.add_parser("fetch-canonical-market")
    # Product code is intentionally config-owned; this command has no override flag.
    canonical.add_argument("--start", required=True)
    canonical.add_argument("--end", required=True)
    canonical.add_argument(
        "--output",
        default=str(REPO_ROOT / "data/raw/ng_contract_history.csv"),
    )
    canonical.set_defaults(func=_fetch_canonical_market)

    run = sub.add_parser("run-baseline")
    run.add_argument("--input", default=str(REPO_ROOT / "data/raw/ng_f_daily.csv"))
    run.add_argument("--start", default=period["start"])
    run.add_argument("--end", default=period["end"])
    run.add_argument(
        "--model", choices=baseline_choices, default=models_cfg["default_model"]
    )
    run.add_argument("--initial-train", type=int, default=walk["initial_train_rows"])
    run.add_argument("--retrain-every", type=int, default=walk["retrain_every_rows"])
    run.add_argument("--output", default=str(REPO_ROOT / "artifacts/runs/baseline"))
    run.set_defaults(func=_run_baseline)

    signal_cfg = signal_policy_config()
    simulation_cfg = simulation_config()
    simulate = sub.add_parser("simulate")
    simulate.add_argument("--predictions", required=True)
    simulate.add_argument("--policy", default=signal_cfg["default_policy"])
    simulate.add_argument("--simulation", default=simulation_cfg["default_simulation"])
    simulate.add_argument("--output", required=True)
    simulate.set_defaults(func=_simulate)

    backtest = sub.add_parser("backtest")
    backtest.add_argument("--predictions", required=True)
    backtest.add_argument("--policy", default=signal_cfg["default_policy"])
    backtest.add_argument("--simulation", default=simulation_cfg["default_simulation"])
    backtest.add_argument("--output", required=True)
    backtest.set_defaults(func=_simulate)

    saxo = sub.add_parser("probe-saxo-market")
    saxo.add_argument("--continuous-uic", type=int)
    saxo.add_argument("--max-contracts", type=int, default=24)
    saxo.add_argument("--output")
    saxo.set_defaults(func=_probe_saxo_market)

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=_doctor)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
