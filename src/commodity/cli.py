from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from commodity.canonical_provider import load_canonical_provider
from commodity.cftc import CftcCotClient, capture_cftc_v1_window, load_cftc_v1_window
from commodity.config import (
    REPO_ROOT,
    assumptions_config,
    data_config,
    experiment_config,
    model_config,
    policy_config,
    signal_policy_config,
    simulation_config,
)
from commodity.data import CsvMarketDataSource, YFinanceMarketDataSource, save_raw
from commodity.eia import (
    EiaBulkClient,
    capture_eia_api_dataset,
    capture_eia_bulk_dataset,
)
from commodity.evaluation import (
    audit_walk_forward_label_isolation,
    evaluate_predictions,
    walk_forward_predict,
)
from commodity.features import make_supervised
from commodity.market_data import canonical_market_readiness
from commodity.models import baseline_factory
from commodity.policy import assert_model_cannot_submit_orders
from commodity.provenance import sha256_file, utc_now, write_json
from commodity.providers import EiaApiV2Client
from commodity.records import build_baseline_record, build_tournament_record
from commodity.research_dataset import TARGET_COLUMN, build_pit_dataset
from commodity.saxo import SaxoSimMarketDataClient, probe_henry_hub
from commodity.simulation import simulate_forecasts
from commodity.tournament import run_tournament
from commodity.weather import (
    OpenMeteoSingleRunClient,
    capture_weather_run,
    capture_weather_v1_window,
    load_weather_v1_window,
)
from commodity.wngsr import (
    WngsrEvidenceClient,
    capture_wngsr_v1_window,
    load_wngsr_v1_window,
)


def _fetch_market(args: argparse.Namespace) -> None:
    cfg = data_config()["sources"]["market_bootstrap"]
    frame = YFinanceMarketDataSource(cfg["symbol"]).fetch(args.start, args.end)
    output = Path(args.output)
    save_raw(frame, output)
    fetched_at = utc_now()
    write_json(
        output.with_suffix(".meta.json"),
        {
            "fetched_at_utc": fetched_at,
            "provider": cfg["provider"],
            "symbol": cfg["symbol"],
            "requested_start": args.start,
            "requested_end": args.end,
            "rows": len(frame),
            "sha256": sha256_file(output),
            "vintage": f"retrieval_snapshot:{fetched_at}",
            "authoritative_for_execution": False,
        },
    )
    print(f"saved_rows={len(frame)} path={output}")


def _fetch_canonical_market(args: argparse.Namespace) -> None:
    cfg = data_config()
    source = cfg["sources"]["market_canonical"]
    fetched_at = utc_now()
    provider = load_canonical_provider(source["provider"])
    frame, metadata = provider.fetch_contract_history(
        cfg["canonical_contract_schema"],
        product_code=source["product_code"],
        start_trade_date=args.start,
        end_trade_date=args.end,
        retrieved_at=fetched_at,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    metadata.update(
        {
            "requested_start": args.start,
            "requested_end": args.end,
            "rows": len(frame),
            "canonical_evidence": False,
            "evidence_tier": "canonical_price_history_roll_unvalidated",
        }
    )
    write_json(output.with_suffix(".meta.json"), metadata)
    print(f"saved_rows={len(frame)} path={output}")


def _capture_canonical_market_v1(args: argparse.Namespace) -> None:
    cfg = data_config()
    source = cfg["sources"]["market_canonical"]
    provider = load_canonical_provider(source["provider"])
    manifest = provider.capture_archive(
        cfg["canonical_contract_schema"],
        source["product_code"],
        args.start,
        args.end,
        utc_now(),
        Path(args.output_root),
        args.snapshot_id,
        max_contracts=args.curve_contracts,
    )
    print(f"manifest={manifest}")

def _capture_eia_v1(args: argparse.Namespace) -> None:
    root = Path(args.output_root)
    retrieved_at = utc_now()
    manifests = [
        capture_eia_bulk_dataset(
            EiaBulkClient(), "NG", root, f"{args.snapshot_id}-ng-bulk", retrieved_at
        )
    ]
    demand_params = {
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": "US48",
        "facets[type][]": ["D", "DF"],
        "start": f"{args.start}T00",
        "end": f"{args.end}T23",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }
    fuel_params = {
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": "US48",
        "facets[fueltype][]": "NG",
        "start": f"{args.start}T00",
        "end": f"{args.end}T23",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }
    client = EiaApiV2Client()
    manifests.append(
        capture_eia_api_dataset(
            client,
            "electricity/rto/region-data",
            demand_params,
            root,
            f"{args.snapshot_id}-power-demand",
            retrieved_at,
        )
    )
    manifests.append(
        capture_eia_api_dataset(
            client,
            "electricity/rto/fuel-type-data",
            fuel_params,
            root,
            f"{args.snapshot_id}-power-ng",
            retrieved_at,
        )
    )
    print(json.dumps({"manifests": [str(path) for path in manifests]}, indent=2))


def _capture_weather_run(args: argparse.Namespace) -> None:
    hourly = tuple(item.strip() for item in args.hourly.split(",") if item.strip())
    manifest = capture_weather_run(
        OpenMeteoSingleRunClient(),
        args.latitude,
        args.longitude,
        args.run,
        args.model,
        hourly,
        args.forecast_days,
        Path(args.output_root),
        args.snapshot_id,
        utc_now(),
    )
    print(f"manifest={manifest}")


def _capture_weather_v1_window(args: argparse.Namespace) -> None:
    root = Path(args.output_root)
    manifests = capture_weather_v1_window(
        OpenMeteoSingleRunClient(),
        args.start,
        args.end,
        root,
        utc_now(),
    )
    frame = load_weather_v1_window(root, args.start, args.end)
    print(
        json.dumps(
            {"manifests": [str(path) for path in manifests], "feature_rows": len(frame)},
            indent=2,
        )
    )


def _capture_cftc_v1_window(args: argparse.Namespace) -> None:
    root = Path(args.output_root)
    manifests = capture_cftc_v1_window(
        CftcCotClient(), args.start, args.end, root, utc_now()
    )
    frame = load_cftc_v1_window(root, args.start, args.end)
    print(
        json.dumps(
            {"manifests": [str(path) for path in manifests], "feature_rows": len(frame)},
            indent=2,
        )
    )


def _capture_wngsr_v1_window(args: argparse.Namespace) -> None:
    root = Path(args.output_root)
    manifest = capture_wngsr_v1_window(
        WngsrEvidenceClient(), args.start, args.end, root, utc_now()
    )
    frame = load_wngsr_v1_window(root, args.start, args.end)
    print(json.dumps({"manifest": str(manifest), "feature_rows": len(frame)}, indent=2))


def _freeze_v1_dataset(args: argparse.Namespace) -> None:
    frame = CsvMarketDataSource(Path(args.input)).fetch(args.start, args.end)
    exp = experiment_config()
    dataset_cfg = exp["dataset"]
    dataset, manifest = build_pit_dataset(
        frame,
        evidence_mode=dataset_cfg["evidence_mode"],
        required_families=tuple(dataset_cfg["required_feature_families"]),
        require_full_v1=args.require_full_v1,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output, index_label="prediction_time")
    manifest.update(
        {
            "artifact_sha256": sha256_file(output),
            "source_market_path": str(Path(args.input)),
            "source_market_sha256": sha256_file(Path(args.input)),
        }
    )
    manifest_path = output.with_suffix(".manifest.json")
    write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2))


def _run_tournament(args: argparse.Namespace) -> None:
    dataset_path = Path(args.input)
    manifest_path = dataset_path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        raise ValueError("Frozen dataset manifest is required for tournament execution")
    dataset_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_sha256 = sha256_file(dataset_path)
    if dataset_manifest.get("artifact_sha256") != artifact_sha256:
        raise ValueError("Frozen dataset artifact hash does not match its manifest")
    frame = pd.read_csv(dataset_path, index_col="prediction_time", parse_dates=["prediction_time"])
    if TARGET_COLUMN not in frame.columns:
        raise ValueError(f"Frozen dataset must contain {TARGET_COLUMN!r}")
    x = frame.drop(columns=[TARGET_COLUMN])
    y = frame[TARGET_COLUMN]
    exp = experiment_config()
    tournament_cfg = exp["tournament"]
    names = tuple(tournament_cfg["models"])
    leakage_check = audit_walk_forward_label_isolation(
        x,
        y,
        initial_train=args.initial_train,
        retrain_every=args.retrain_every,
    )
    summary, predictions = run_tournament(
        x,
        y,
        model_names=names,
        models=model_config()["models"],
        initial_train=args.initial_train,
        retrain_every=args.retrain_every,
        primary_metric=tournament_cfg["primary_metric"],
        baseline_model=tournament_cfg["baseline_model"],
        significance=tournament_cfg["significance"],
    )
    run_dir = Path(args.output)
    run_dir.mkdir(parents=True, exist_ok=True)
    for model_name, pred in predictions.items():
        model_dir = run_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        pred.to_csv(model_dir / "predictions.csv", index_label="date")
        row = summary.loc[summary["model"] == model_name].iloc[0].to_dict()
        write_json(model_dir / "metrics.json", row)
        significance = {
            "method": tournament_cfg["significance"]["method"],
            "baseline_model": tournament_cfg["baseline_model"],
            "rmse_improvement": float(row["rmse_improvement_vs_baseline"]),
            "ci_lower": float(row["significance_ci_lower"]),
            "ci_upper": float(row["significance_ci_upper"]),
            "p_value": float(row["significance_p_value"]),
            "significant": bool(row["significant_vs_baseline"]),
            "block_size": int(tournament_cfg["significance"]["block_size"]),
            "resamples": int(tournament_cfg["significance"]["resamples"]),
        }
        metric_keys = (
            "n", "mae", "rmse", "bias", "direction_accuracy", "prediction_actual_corr"
        )
        record = build_tournament_record(
            dataset_manifest=dataset_manifest,
            dataset_path=dataset_path,
            model_dir=model_dir,
            model_name=model_name,
            metrics={key: float(row[key]) for key in metric_keys},
            feature_index=x.index,
            initial_train=args.initial_train,
            significance=significance,
            leakage_check=leakage_check,
        )
        write_json(model_dir / "experiment.json", record)
    summary.to_csv(run_dir / "summary.csv", index=False)
    report = {
        "schema_version": 1,
        "experiment_id": exp["experiment_id"],
        "dataset_id": dataset_manifest.get("dataset_id"),
        "dataset_sha256": dataset_manifest.get("dataset_sha256"),
        "dataset_artifact_sha256": artifact_sha256,
        "dataset_manifest_sha256": sha256_file(manifest_path),
        "dataset_completeness": dataset_manifest.get("completeness"),
        "missing_feature_families": dataset_manifest.get("missing_feature_families", []),
        "research_promotion_eligible": dataset_manifest.get("completeness") == "full_v1",
        "primary_metric": tournament_cfg["primary_metric"],
        "split_strategy": tournament_cfg["split_strategy"],
        "models": names,
        "ranking": summary.to_dict(orient="records"),
    }
    write_json(run_dir / "summary.json", report)
    print(json.dumps(report, indent=2))


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
    write_json(
        run_dir / "simulation_metrics.json",
        {
            "schema_version": 1,
            "policy_id": args.policy,
            "simulation_id": args.simulation,
            "canonical_evidence": canonical_evidence,
            "evidence_tier": "canonical" if canonical_evidence else "research_noncanonical",
            "metrics": metrics,
        },
    )
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
    readiness = canonical_market_readiness(data_cfg, assumptions_config())
    simulation_cfg = simulation_config()
    default_simulation = simulation_cfg["simulations"][simulation_cfg["default_simulation"]]
    canonical_reason = None if readiness["canonical_evidence_allowed"] else readiness["reasons"][0]
    print(
        json.dumps(
            {
                "repo": str(REPO_ROOT),
                "default_model": model_config()["default_model"],
                "market_source": data_cfg["sources"]["market_bootstrap"],
                "research_backtesting_available": simulation_cfg["semantics"]["research_backtesting_available"],
                "canonical_source_history_ready": readiness["source_history_ready"],
                "canonical_roll_method_ready": readiness["roll_method_ready"],
                "canonical_licensing_ready": readiness["licensing_ready"],
                "canonical_market_evidence_allowed": readiness["canonical_evidence_allowed"],
                "canonical_market_evidence_reason": canonical_reason,
                "default_simulation_canonical_evidence_allowed": default_simulation["canonical_evidence_allowed"],
                "execution": policy_config()["execution"],
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    exp = experiment_config()
    period = exp["research_period"]
    walk = exp["walk_forward"]
    models_cfg = model_config()
    data_cfg = data_config()
    canonical_source = data_cfg["sources"]["market_canonical"]
    snapshot_root = str(REPO_ROOT / "data/raw/snapshots")
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
    canonical.add_argument("--start", required=True)
    canonical.add_argument("--end", required=True)
    canonical.add_argument("--output", default=str(REPO_ROOT / "data/raw/ng_contract_history.csv"))
    canonical.set_defaults(func=_fetch_canonical_market)

    preserve_canonical = sub.add_parser("capture-canonical-market-v1")
    preserve_canonical.add_argument(
        "--start", default=canonical_source["history_earliest_verified_trade_date"]
    )
    preserve_canonical.add_argument("--end", required=True)
    preserve_canonical.add_argument("--snapshot-id", required=True)
    preserve_canonical.add_argument("--curve-contracts", type=int, default=12)
    preserve_canonical.add_argument("--output-root", default=snapshot_root)
    preserve_canonical.set_defaults(func=_capture_canonical_market_v1)

    preserve_eia = sub.add_parser("capture-eia-v1")
    preserve_eia.add_argument(
        "--start", default=canonical_source["history_earliest_verified_trade_date"]
    )
    preserve_eia.add_argument("--end", required=True)
    preserve_eia.add_argument("--snapshot-id", required=True)
    preserve_eia.add_argument("--output-root", default=snapshot_root)
    preserve_eia.set_defaults(func=_capture_eia_v1)

    preserve_weather = sub.add_parser("capture-weather-run")
    preserve_weather.add_argument("--run", required=True)
    preserve_weather.add_argument("--latitude", type=float, required=True)
    preserve_weather.add_argument("--longitude", type=float, required=True)
    preserve_weather.add_argument("--snapshot-id", required=True)
    preserve_weather.add_argument("--model", default="ecmwf_ifs")
    preserve_weather.add_argument("--forecast-days", type=int, default=10)
    preserve_weather.add_argument(
        "--hourly",
        default="temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
    )
    preserve_weather.add_argument("--output-root", default=snapshot_root)
    preserve_weather.set_defaults(func=_capture_weather_run)

    preserve_weather_v1 = sub.add_parser("capture-weather-v1-window")
    preserve_weather_v1.add_argument(
        "--start", default=canonical_source["history_earliest_verified_trade_date"]
    )
    preserve_weather_v1.add_argument("--end", required=True)
    preserve_weather_v1.add_argument("--output-root", default=snapshot_root)
    preserve_weather_v1.set_defaults(func=_capture_weather_v1_window)

    preserve_cftc_v1 = sub.add_parser("capture-cftc-v1-window")
    preserve_cftc_v1.add_argument(
        "--start", default=canonical_source["history_earliest_verified_trade_date"]
    )
    preserve_cftc_v1.add_argument("--end", required=True)
    preserve_cftc_v1.add_argument("--output-root", default=snapshot_root)
    preserve_cftc_v1.set_defaults(func=_capture_cftc_v1_window)

    preserve_wngsr_v1 = sub.add_parser("capture-wngsr-v1-window")
    preserve_wngsr_v1.add_argument(
        "--start", default=canonical_source["history_earliest_verified_trade_date"]
    )
    preserve_wngsr_v1.add_argument("--end", required=True)
    preserve_wngsr_v1.add_argument("--output-root", default=snapshot_root)
    preserve_wngsr_v1.set_defaults(func=_capture_wngsr_v1_window)

    freeze = sub.add_parser("freeze-v1-dataset")
    freeze.add_argument("--input", default=str(REPO_ROOT / "data/raw/ng_f_daily.csv"))
    freeze.add_argument("--start", default=period["start"])
    freeze.add_argument("--end", default=period["end"])
    freeze.add_argument(
        "--output", default=str(REPO_ROOT / "data/processed/us_ng_v1_pit.csv")
    )
    freeze.add_argument("--require-full-v1", action="store_true")
    freeze.set_defaults(func=_freeze_v1_dataset)

    tournament = sub.add_parser("run-tournament")
    tournament.add_argument(
        "--input", default=str(REPO_ROOT / "data/processed/us_ng_v1_pit.csv")
    )
    tournament.add_argument(
        "--initial-train", type=int, default=walk["initial_train_rows"]
    )
    tournament.add_argument(
        "--retrain-every", type=int, default=walk["retrain_every_rows"]
    )
    tournament.add_argument(
        "--output", default=str(REPO_ROOT / "artifacts/runs/v1-pit-tournament")
    )
    tournament.set_defaults(func=_run_tournament)

    run = sub.add_parser("run-baseline")
    run.add_argument("--input", default=str(REPO_ROOT / "data/raw/ng_f_daily.csv"))
    run.add_argument("--start", default=period["start"])
    run.add_argument("--end", default=period["end"])
    run.add_argument("--model", choices=baseline_choices, default=models_cfg["default_model"])
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
