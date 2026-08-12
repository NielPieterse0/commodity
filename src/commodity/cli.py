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
from commodity.models import RidgeReturnModel, ZeroReturnModel
from commodity.policy import assert_model_cannot_submit_orders
from commodity.provenance import sha256_file, utc_now, write_json
from commodity.records import build_baseline_record
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


def _run_baseline(args: argparse.Namespace) -> None:
    frame = CsvMarketDataSource(Path(args.input)).fetch(args.start, args.end)
    x, y = make_supervised(frame)
    cfg = model_config()["models"]
    if args.model == "ridge":
        factory = lambda: RidgeReturnModel(alpha=float(cfg["ridge"]["alpha"]))
    else:
        factory = ZeroReturnModel
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
    write_json(run_dir / "simulation_metrics.json", {
        "schema_version": 1,
        "policy_id": args.policy,
        "simulation_id": args.simulation,
        "canonical_evidence": simulation["canonical_evidence_allowed"],
        "metrics": metrics,
    })
    print(json.dumps(metrics, indent=2))


def _doctor(_: argparse.Namespace) -> None:
    assert_model_cannot_submit_orders()
    print(json.dumps({
        "repo": str(REPO_ROOT),
        "default_model": model_config()["default_model"],
        "market_source": data_config()["sources"]["market_bootstrap"],
        "execution": policy_config()["execution"],
    }, indent=2))


def build_parser() -> argparse.ArgumentParser:
    exp = experiment_config()
    period = exp["research_period"]
    walk = exp["walk_forward"]
    parser = argparse.ArgumentParser(prog="commodity")
    sub = parser.add_subparsers(required=True)
    fetch = sub.add_parser("fetch-market")
    fetch.add_argument("--start", default=period["start"])
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--output", default=str(REPO_ROOT / "data/raw/ng_f_daily.csv"))
    fetch.set_defaults(func=_fetch_market)

    run = sub.add_parser("run-baseline")
    run.add_argument("--input", default=str(REPO_ROOT / "data/raw/ng_f_daily.csv"))
    run.add_argument("--start", default=period["start"])
    run.add_argument("--end", default=period["end"])
    run.add_argument("--model", choices=["naive", "ridge"], default=model_config()["default_model"])
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

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=_doctor)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
