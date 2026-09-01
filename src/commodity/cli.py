from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

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
from commodity.dataset_audit import audit_full_v1_dataset
from commodity.dataset_freeze import load_frozen_dataset
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
from commodity.exogenous_audit import audit_required_exogenous_families
from commodity.features import make_supervised
from commodity.market_data import canonical_market_readiness
from commodity.models import baseline_factory
from commodity.nyiso import (
    NyisoLoadForecastClient,
    capture_nyiso_v1_window,
    load_nyiso_v1_window,
)
from commodity.phase_d_run import run_phase_d_from_frozen
from commodity.policy import assert_model_cannot_submit_orders
from commodity.provenance import (
    git_code_state,
    locked_environment_mismatches,
    sha256_file,
    utc_now,
    write_json,
)
from commodity.providers import EiaApiV2Client
from commodity.records import build_baseline_record, build_tournament_record
from commodity.research_dataset import TARGET_COLUMN, build_pit_dataset
from commodity.research_methodology import (
    MethodologyError,
    assert_confirmatory_execution_allowed,
    audit_leakage,
    build_results,
    execute_reproduction,
    record_family_inference,
    record_inference_outcome,
    record_sealed_opening,
    register_inference_entry,
    render_executive_summary_from_interpretation,
    update_programme_evidence_map,
    validate_inference_ledger,
    validate_programme_context,
    validate_sealed_policy,
    verify_power,
    verify_preregistration,
    verify_remote_prereg_binding,
    verify_reproduction,
    verify_results,
    write_immutable_json,
)
from commodity.research_methodology import (
    load_json as load_methodology_json,
)
from commodity.research_metrics import (
    MetricsContractError,
    latest_closeout,
    load_ledger,
    render_markdown_summary,
)
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


def _capture_nyiso_v1_window(args: argparse.Namespace) -> None:
    root = Path(args.output_root)
    manifests = capture_nyiso_v1_window(
        NyisoLoadForecastClient(), args.start, args.end, root, utc_now()
    )
    frame = load_nyiso_v1_window(root, args.start, args.end)
    print(
        json.dumps(
            {"manifests": [str(path) for path in manifests], "feature_rows": len(frame)},
            indent=2,
        )
    )


def _audit_v1_exogenous(args: argparse.Namespace) -> None:
    root = Path(args.snapshot_root)
    loaders = {
        "storage": load_wngsr_v1_window,
        "weather": load_weather_v1_window,
        "power": load_nyiso_v1_window,
        "positioning": load_cftc_v1_window,
    }
    frames: dict[str, pd.DataFrame | None] = {}
    load_errors: dict[str, str] = {}
    for family, loader in loaders.items():
        try:
            frames[family] = loader(root, args.start, args.end)
        except (OSError, ValueError) as exc:
            frames[family] = None
            load_errors[family] = str(exc)
    audits = audit_required_exogenous_families(
        frames=frames,
        required_start=args.start,
        required_end=args.end,
        evidence_mode="research_pit",
    )
    evidence = {
        "schema_version": 1,
        "phase": "B",
        "assessment_as_of": utc_now(),
        "research_window": {
            "start": args.start,
            "end": args.end,
            "basis": "preserved V1 point-in-time source snapshots",
        },
        "policy_inputs": {
            "data_sources_sha256": sha256_file(REPO_ROOT / "config/data_sources.json"),
            "experiment_sha256": sha256_file(REPO_ROOT / "config/experiment.json"),
        },
        "snapshot_root": str(root.resolve()),
        "full_v1_ready": all(result.full_v1_ready for result in audits.values()),
        "families": {
            family: {
                **result.to_dict(),
                **({"load_error": load_errors[family]} if family in load_errors else {}),
            }
            for family, result in audits.items()
        },
    }
    write_json(Path(args.output), evidence)
    print(json.dumps(evidence, indent=2))


def _reproduce_v1(args: argparse.Namespace) -> None:
    dataset_dir = Path(args.dataset_dir)
    frame, manifest = load_frozen_dataset(dataset_dir)
    audit = audit_full_v1_dataset(frame, manifest)
    if audit.verdict == "not-fit":
        raise ValueError(f"Frozen V1 dataset fails current audit: {list(audit.blockers)}")
    environment_mismatches = locked_environment_mismatches(Path(args.dependency_lock))
    if environment_mismatches:
        raise ValueError(
            "Research-grade V1 reproduction requires the exact locked environment: "
            + "; ".join(environment_mismatches[:10])
        )
    code = git_code_state(REPO_ROOT)
    if code["commit_sha"] is None or code["working_tree_dirty"]:
        raise ValueError("Research-grade V1 reproduction requires a clean exact Git commit")
    output_dir = Path(args.output)
    evidence = run_phase_d_from_frozen(
        dataset_dir=dataset_dir,
        config_path=Path(args.config),
        models_path=Path(args.models),
        dependency_lock_path=Path(args.dependency_lock),
        output_dir=output_dir,
        code_commit=str(code["commit_sha"]),
    )
    write_json(output_dir / "current-dataset-audit.json", audit.to_dict())
    print(json.dumps({
        "disposition": evidence["results"]["robustness"]["disposition"],
        "dataset_rows": evidence["dataset"]["rows"],
        "oos_rows": evidence["dataset"]["oos_rows"],
        "audit_verdict": audit.verdict,
        "research_promotion_eligible": evidence["authority"]["research_promotion_eligible"],
        "trading_authority": evidence["authority"]["trading_authority"],
        "output": str(output_dir),
    }, indent=2))


def _freeze_v1_dataset(args: argparse.Namespace) -> None:
    if args.require_full_v1:
        raise ValueError(
            "The CSV/yfinance bootstrap path cannot claim full V1 evidence; use reproduce-v1 "
            "with the governed frozen dataset."
        )
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
            metrics={
                key: float(row[key]) if pd.notna(row[key]) else None
                for key in metric_keys
            },
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
        "evidence_mode": dataset_manifest.get("evidence_mode"),
        "canonical_market_evidence": dataset_manifest.get("canonical_market_evidence") is True,
        "research_evaluation_eligible": (
            dataset_manifest.get("research_evaluation_eligible") is True
        ),
        "research_promotion_eligible": dataset_manifest.get("research_promotion_eligible") is True,
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


def _check_research_metrics(args: argparse.Namespace) -> None:
    try:
        ledger = load_ledger(Path(args.ledger))
        result = latest_closeout(ledger)
    except (OSError, json.JSONDecodeError, MetricsContractError) as exc:
        result = {"status": "blocked", "blockers": [f"invalid_ledger:{exc}"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(2)


def _summarize_research_metrics(args: argparse.Namespace) -> None:
    ledger = load_ledger(Path(args.ledger))
    summary = render_markdown_summary(ledger)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(summary, encoding="utf-8", newline="\n")
        print(f"summary={output}")
    else:
        print(summary)


def _experiment_register(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    verify_preregistration(prereg)
    if prereg["experiment_id"] != args.experiment_id:
        raise MethodologyError("experiment_id does not match preregistration")
    ledger_path = Path(args.ledger)
    ledger = load_methodology_json(ledger_path)
    updated = register_inference_entry(ledger, prereg)
    write_json(ledger_path, updated)
    print(json.dumps({"status": "registered", "entry_id": prereg["inference_ledger_entry_id"]}, indent=2))


def _experiment_verify(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    result = verify_preregistration(prereg)
    print(json.dumps(result, indent=2, sort_keys=True))


def _experiment_verify_power(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    result = verify_power(prereg)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(2)


def _experiment_freeze(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    verification = verify_preregistration(prereg)
    if prereg["experiment_id"] != args.experiment_id:
        raise MethodologyError("experiment_id does not match preregistration")
    ledger = load_methodology_json(Path(args.ledger))
    validate_inference_ledger(ledger)
    programme_evidence_path = Path(args.programme_evidence)
    programme_evidence = load_methodology_json(programme_evidence_path)
    programme_context = validate_programme_context(prereg, programme_evidence)
    sealed_registry = load_methodology_json(Path(args.sealed_registry))
    validate_sealed_policy(prereg, sealed_registry)
    matches = [item for item in ledger["entries"] if item["entry_id"] == prereg["inference_ledger_entry_id"] and item["experiment_id"] == args.experiment_id]
    if len(matches) != 1:
        raise MethodologyError("preregistration is not registered exactly once in programme inference ledger")
    binding = verify_remote_prereg_binding(REPO_ROOT, Path(args.prereg), args.tag, args.remote)
    record = {
        "schema_version": 1,
        "experiment_id": args.experiment_id,
        "frozen": True,
        "prereg_sha256": verification["prereg_sha256"],
        "power": verification["power"],
        "programme_context": {
            **programme_context,
            "path": programme_evidence_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
            "sha256": sha256_file(programme_evidence_path),
        },
        "binding": binding,
    }
    output = Path(args.output)
    write_immutable_json(output, record)
    print(json.dumps(record, indent=2, sort_keys=True))


def _experiment_can_run(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    freeze = load_methodology_json(Path(args.freeze))
    ledger = load_methodology_json(Path(args.ledger))
    sealed = load_methodology_json(Path(args.sealed_registry))
    result = assert_confirmatory_execution_allowed(prereg, freeze, ledger, sealed)
    print(json.dumps(result, indent=2, sort_keys=True))


def _experiment_open_sealed(args: argparse.Namespace) -> None:
    registry_path = Path(args.sealed_registry)
    registry = load_methodology_json(registry_path)
    prereg = load_methodology_json(Path(args.prereg))
    freeze = load_methodology_json(Path(args.freeze))
    ledger = load_methodology_json(Path(args.ledger))
    assert_confirmatory_execution_allowed(prereg, freeze, ledger, registry)
    if prereg["experiment_id"] != args.experiment_id:
        raise MethodologyError("experiment_id does not match preregistration")
    if prereg.get("sealed_window", {}).get("sealed_window_id") != args.sealed_window_id:
        raise MethodologyError("sealed_window_id does not match preregistration")
    updated = record_sealed_opening(
        registry,
        args.sealed_window_id,
        args.experiment_id,
        [item.strip() for item in args.artifacts_exposed.split(",") if item.strip()],
    )
    write_json(registry_path, updated)
    print(json.dumps({"status": "opened", "sealed_window_id": args.sealed_window_id, "experiment_id": args.experiment_id}, indent=2))


def _experiment_build_results(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    freeze = load_methodology_json(Path(args.freeze))
    ledger = load_methodology_json(Path(args.ledger))
    sealed = load_methodology_json(Path(args.sealed_registry))
    assert_confirmatory_execution_allowed(prereg, freeze, ledger, sealed)
    run = load_methodology_json(Path(args.run_evidence))
    checks = load_methodology_json(Path(args.checks))
    verification = audit_leakage(checks)
    results = build_results(
        prereg,
        run_id=str(run["run_id"]),
        code=run["code"],
        data=run["data"],
        features=run.get("features"),
        model=run["model"],
        environment=run["environment"],
        raw_evidence=run["raw_evidence"],
        verification=verification,
        coherence=run["coherence"],
        artifacts=run.get("artifacts", []),
    )
    verified = verify_results(prereg, results)
    results_schema = load_methodology_json(REPO_ROOT / "contracts/results.schema.json")
    validator = Draft202012Validator(results_schema)
    schema_errors = sorted(validator.iter_errors(results), key=lambda item: list(item.path))
    if schema_errors:
        details = "; ".join(error.message for error in schema_errors[:5])
        raise MethodologyError(f"results violate results.schema.json: {details}")
    write_immutable_json(Path(args.output), results)
    updated_ledger = ledger
    if results.get("family_inference") is not None:
        updated_ledger = record_family_inference(updated_ledger, results["family_inference"])
    updated_ledger = record_inference_outcome(
        updated_ledger,
        prereg["experiment_id"],
        f"{verified['scientific_evidence']}:{verified['method_compliance']}",
    )
    write_json(Path(args.ledger), updated_ledger)
    programme_path = Path(args.programme_evidence)
    programme = load_methodology_json(programme_path)
    new_scan_id = args.new_scan_id or f"{programme['current_scan_id']}:after:{prereg['experiment_id']}"
    updated_programme = update_programme_evidence_map(programme, prereg, results, new_scan_id=new_scan_id)
    write_json(programme_path, updated_programme)
    print(json.dumps({**verified, "programme_scan_id": new_scan_id}, indent=2, sort_keys=True))


def _experiment_verify_results(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    results = load_methodology_json(Path(args.results))
    print(json.dumps(verify_results(prereg, results), indent=2, sort_keys=True))


def _experiment_audit_leakage(args: argparse.Namespace) -> None:
    checks = load_methodology_json(Path(args.checks))
    findings = audit_leakage(checks)
    print(json.dumps({"findings": findings}, indent=2, sort_keys=True))
    if any("failed" in item["message"].lower() or "incomplete" in item["message"].lower() for item in findings):
        raise SystemExit(2)


def _experiment_reproduce(args: argparse.Namespace) -> None:
    reference = load_methodology_json(Path(args.reference))
    tolerance = load_methodology_json(Path(args.tolerance))
    if args.command:
        if args.output is None:
            raise MethodologyError("reproduce --command requires --output")
        command_spec = load_methodology_json(Path(args.command))
        argv = command_spec.get("argv")
        result = execute_reproduction(argv, Path(args.output), reference, tolerance, cwd=Path(args.cwd))
    else:
        if args.candidate is None:
            raise MethodologyError("reproduce requires --candidate or --command")
        candidate = load_methodology_json(Path(args.candidate))
        result = verify_reproduction(reference, candidate, tolerance, byte_mode=args.byte)
    print(json.dumps(result, indent=2, sort_keys=True))


def _experiment_summary(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    results = load_methodology_json(Path(args.results))
    interpretation = Path(args.interpretation).read_text(encoding="utf-8")
    summary = render_executive_summary_from_interpretation(interpretation, prereg, results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(summary, encoding="utf-8", newline="\n")
    print(f"summary={output}")


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
    phase_d_config_path = REPO_ROOT / "config/phase_d_evaluation.json"
    metrics_ledger_path = REPO_ROOT / "artifacts/research-metrics/longitudinal-ledger.json"
    phase_d_cfg = json.loads(phase_d_config_path.read_text(encoding="utf-8"))
    frozen = phase_d_cfg["dataset"]
    frozen_dataset_dir = REPO_ROOT / "data/processed/full-v1-freezes" / (
        f"{frozen['dataset_id']}-{frozen['freeze_id']}"
    )
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

    preserve_nyiso_v1 = sub.add_parser("capture-nyiso-v1-window")
    preserve_nyiso_v1.add_argument(
        "--start", default=canonical_source["history_earliest_verified_trade_date"]
    )
    preserve_nyiso_v1.add_argument("--end", required=True)
    preserve_nyiso_v1.add_argument("--output-root", default=snapshot_root)
    preserve_nyiso_v1.set_defaults(func=_capture_nyiso_v1_window)

    audit_exogenous = sub.add_parser("audit-v1-exogenous")
    audit_exogenous.add_argument(
        "--start", default=canonical_source["history_earliest_verified_trade_date"]
    )
    audit_exogenous.add_argument("--end", required=True)
    audit_exogenous.add_argument("--snapshot-root", default=snapshot_root)
    audit_exogenous.add_argument(
        "--output",
        default=str(
            REPO_ROOT
            / "docs/development/v1-research-completion/phase-b-evidence.json"
        ),
    )
    audit_exogenous.set_defaults(func=_audit_v1_exogenous)

    reproduce = sub.add_parser(
        "reproduce-v1",
        help="Re-audit and reproduce the frozen research-grade V1 Phase D evaluation",
    )
    reproduce.add_argument("--dataset-dir", type=Path, default=frozen_dataset_dir)
    reproduce.add_argument("--config", type=Path, default=phase_d_config_path)
    reproduce.add_argument("--models", type=Path, default=REPO_ROOT / "config/models.json")
    reproduce.add_argument(
        "--dependency-lock", type=Path, default=REPO_ROOT / "requirements.lock.txt"
    )
    reproduce.add_argument(
        "--output", type=Path, default=REPO_ROOT / "artifacts/runs/v1-reproduction"
    )
    reproduce.set_defaults(func=_reproduce_v1)

    freeze = sub.add_parser("freeze-v1-dataset", help="Development/bootstrap dataset path only")
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

    metrics_check = sub.add_parser(
        "check-research-metrics",
        help="Validate longitudinal research metrics and fail if latest closeout is blocked",
    )
    metrics_check.add_argument("--ledger", type=Path, default=metrics_ledger_path)
    metrics_check.set_defaults(func=_check_research_metrics)

    metrics_summary = sub.add_parser(
        "summarize-research-metrics",
        help="Generate a human-readable summary from the governed metrics ledger",
    )
    metrics_summary.add_argument("--ledger", type=Path, default=metrics_ledger_path)
    metrics_summary.add_argument("--output", type=Path)
    metrics_summary.set_defaults(func=_summarize_research_metrics)

    experiment = sub.add_parser("experiment", help="Governed hypothesis/experiment lifecycle")
    experiment_sub = experiment.add_subparsers(required=True)
    methodology_ledger = REPO_ROOT / "config/programme_inference_ledger.json"

    register = experiment_sub.add_parser("register", help="Allocate the preregistered programme inference entry before release")
    register.add_argument("experiment_id")
    register.add_argument("--prereg", type=Path, required=True)
    register.add_argument("--ledger", type=Path, default=methodology_ledger)
    register.set_defaults(func=_experiment_register)

    verify = experiment_sub.add_parser("verify", help="Verify preregistration invariants")
    verify.add_argument("--prereg", type=Path, required=True)
    verify.set_defaults(func=_experiment_verify)

    verify_power_cmd = experiment_sub.add_parser("verify-power", help="Recompute MEPI/power and dependence-adjusted information")
    verify_power_cmd.add_argument("--prereg", type=Path, required=True)
    verify_power_cmd.set_defaults(func=_experiment_verify_power)

    freeze_exp = experiment_sub.add_parser("freeze", help="Declare an exact remotely bound preregistration frozen")
    freeze_exp.add_argument("experiment_id")
    freeze_exp.add_argument("--prereg", type=Path, required=True)
    freeze_exp.add_argument("--ledger", type=Path, default=methodology_ledger)
    freeze_exp.add_argument("--programme-evidence", type=Path, default=REPO_ROOT / "config/programme_evidence_map.json")
    freeze_exp.add_argument("--sealed-registry", type=Path, default=REPO_ROOT / "config/sealed_windows.json")
    freeze_exp.add_argument("--tag", required=True)
    freeze_exp.add_argument("--remote", default="origin")
    freeze_exp.add_argument("--output", type=Path, required=True)
    freeze_exp.set_defaults(func=_experiment_freeze)

    can_run = experiment_sub.add_parser("can-run", help="Fail closed unless the exact frozen confirmatory experiment may execute")
    can_run.add_argument("--prereg", type=Path, required=True)
    can_run.add_argument("--freeze", type=Path, required=True)
    can_run.add_argument("--ledger", type=Path, default=methodology_ledger)
    can_run.add_argument("--sealed-registry", type=Path, default=REPO_ROOT / "config/sealed_windows.json")
    can_run.set_defaults(func=_experiment_can_run)

    open_sealed = experiment_sub.add_parser("open-sealed", help="Account for a sealed confirmation opening before protected access")
    open_sealed.add_argument("experiment_id")
    open_sealed.add_argument("sealed_window_id")
    open_sealed.add_argument("--prereg", type=Path, required=True)
    open_sealed.add_argument("--freeze", type=Path, required=True)
    open_sealed.add_argument("--ledger", type=Path, default=methodology_ledger)
    open_sealed.add_argument("--artifacts-exposed", required=True)
    open_sealed.add_argument("--sealed-registry", type=Path, default=REPO_ROOT / "config/sealed_windows.json")
    open_sealed.set_defaults(func=_experiment_open_sealed)

    build_results_cmd = experiment_sub.add_parser("build-results", help="Machine-author immutable results from raw run evidence")
    build_results_cmd.add_argument("--prereg", type=Path, required=True)
    build_results_cmd.add_argument("--freeze", type=Path, required=True)
    build_results_cmd.add_argument("--ledger", type=Path, default=methodology_ledger)
    build_results_cmd.add_argument("--sealed-registry", type=Path, default=REPO_ROOT / "config/sealed_windows.json")
    build_results_cmd.add_argument("--programme-evidence", type=Path, default=REPO_ROOT / "config/programme_evidence_map.json")
    build_results_cmd.add_argument("--new-scan-id")
    build_results_cmd.add_argument("--run-evidence", type=Path, required=True)
    build_results_cmd.add_argument("--checks", type=Path, required=True)
    build_results_cmd.add_argument("--output", type=Path, required=True)
    build_results_cmd.set_defaults(func=_experiment_build_results)

    verify_results_cmd = experiment_sub.add_parser("verify-results", help="Verify results bind to the exact preregistration and derived evidence")
    verify_results_cmd.add_argument("--prereg", type=Path, required=True)
    verify_results_cmd.add_argument("--results", type=Path, required=True)
    verify_results_cmd.set_defaults(func=_experiment_verify_results)

    leakage = experiment_sub.add_parser("audit-leakage", help="Run bounded natural-gas/futures leakage checks")
    leakage.add_argument("--checks", type=Path, required=True)
    leakage.set_defaults(func=_experiment_audit_leakage)

    reproduce_exp = experiment_sub.add_parser("reproduce", help="Verify supplied output or execute a governed local reproduction command")
    reproduce_exp.add_argument("--reference", type=Path, required=True)
    reproduce_exp.add_argument("--candidate", type=Path)
    reproduce_exp.add_argument("--command", type=Path, help="JSON object containing argv for governed local reproduction")
    reproduce_exp.add_argument("--output", type=Path, help="Declared output produced by --command")
    reproduce_exp.add_argument("--cwd", type=Path, default=REPO_ROOT)
    reproduce_exp.add_argument("--tolerance", type=Path, required=True)
    reproduce_exp.add_argument("--byte", action="store_true")
    reproduce_exp.set_defaults(func=_experiment_reproduce)

    summary_exp = experiment_sub.add_parser("executive-summary", help="Generate the compact six-part operator summary from interpretation authority")
    summary_exp.add_argument("--prereg", type=Path, required=True)
    summary_exp.add_argument("--results", type=Path, required=True)
    summary_exp.add_argument("--interpretation", type=Path, required=True)
    summary_exp.add_argument("--output", type=Path, required=True)
    summary_exp.set_defaults(func=_experiment_summary)

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=_doctor)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
