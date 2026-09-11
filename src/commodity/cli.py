from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import types
from contextlib import ExitStack
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

from commodity.config import (
    REPO_ROOT,
    assumptions_config,
    config_path,
    data_config,
    model_config,
    policy_config,
    signal_policy_config,
    simulation_config,
)
from commodity.data import YFinanceMarketDataSource, save_raw
from commodity.data_assurance import assert_preoutcome_freeze_ready
from commodity.market_data import canonical_market_readiness, resolve_market_source
from commodity.market_only_phase2 import Phase2MarketOnlyError, run_phase2_market_only
from commodity.phase3_runtime import Phase3RuntimeError, run_phase3_fundamentals
from commodity.policy import assert_model_cannot_submit_orders
from commodity.provenance import sha256_file, utc_now, write_json
from commodity.providers.canonical import load_canonical_provider
from commodity.providers.saxo import SaxoSimMarketDataClient, probe_henry_hub
from commodity.research_methodology import (
    MethodologyError,
    assert_confirmatory_execution_allowed,
    audit_leakage,
    build_results,
    execute_reproduction,
    record_family_inference,
    record_inference_outcome,
    record_sealed_opening,
    register_experiment_ref,
    register_inference_entry,
    render_executive_summary_from_interpretation,
    update_programme_evidence_map,
    update_research_line,
    validate_inference_ledger,
    validate_post_unblinding_dataset_assurance,
    validate_programme_context,
    validate_sealed_policy,
    verify_lineage,
    verify_power,
    verify_preregistration,
    verify_reference_artifact,
    verify_remote_prereg_binding,
    verify_reproduction,
    verify_results,
    write_immutable_json,
)
from commodity.research_methodology import load_json as load_methodology_json
from commodity.research_metrics import (
    MetricsContractError,
    latest_closeout,
    load_ledger,
    render_markdown_summary,
)
from commodity.simulation import simulate_forecasts
from commodity.trading_decision_v0 import (
    DecisionSystemError,
    build_roll_safe_session_path,
    build_walk_forward_forecasts,
    governed_input_authority_identity,
    parse_cost_assumptions,
    parse_input_boundary,
    parse_risk_policy,
    selected_model_forecasts,
    simulate_policy,
)
from commodity.weather import OpenMeteoSingleRunClient, capture_weather_run


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
    source_id, source = resolve_market_source(cfg)
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
            "market_source_id": source_id,
            "requested_start": args.start,
            "requested_end": args.end,
            "rows": len(frame),
            "canonical_evidence": False,
            "evidence_tier": "canonical_price_history_roll_unvalidated",
        }
    )
    write_json(output.with_suffix(".meta.json"), metadata)
    print(f"saved_rows={len(frame)} path={output}")

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

def _programme_artifact_path(prereg: dict, explicit: Path | None, filename: str) -> Path:
    if explicit is not None:
        return Path(explicit)
    programme_ref = prereg.get("lineage", {}).get("programme_ref")
    if not isinstance(programme_ref, str) or not programme_ref:
        raise MethodologyError(f"preregistration lineage is missing programme_ref for {filename}")
    programme_path = (REPO_ROOT / programme_ref).resolve()
    if REPO_ROOT.resolve() not in programme_path.parents:
        raise MethodologyError("programme_ref escapes repository root")
    return programme_path.parent / filename


def _experiment_register(args: argparse.Namespace) -> None:
    prereg_path = Path(args.prereg)
    prereg = load_methodology_json(prereg_path)
    verify_preregistration(prereg)
    verify_lineage(prereg, repo_root=REPO_ROOT)
    if prereg["experiment_id"] != args.experiment_id:
        raise MethodologyError("experiment_id does not match preregistration")
    line_path = REPO_ROOT / prereg["lineage"]["research_line_ref"]
    line = load_methodology_json(line_path)
    updated_line = register_experiment_ref(line, prereg, prereg_path)
    ledger_path = _programme_artifact_path(prereg, args.ledger, "inference-ledger.json")
    ledger = load_methodology_json(ledger_path)
    updated = register_inference_entry(ledger, prereg)
    write_json(line_path, updated_line)
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

    ledger_path = _programme_artifact_path(prereg, args.ledger, "inference-ledger.json")
    ledger = load_methodology_json(ledger_path)
    validate_inference_ledger(ledger)
    programme_evidence_path = _programme_artifact_path(prereg, args.programme_evidence, "evidence-map.json")
    programme_evidence = load_methodology_json(programme_evidence_path)
    programme_context = validate_programme_context(prereg, programme_evidence)
    evidence_scan = verify_reference_artifact(prereg["evidence_scan_ref"], REPO_ROOT)
    literature_snapshot = verify_reference_artifact(prereg["literature_snapshot_ref"], REPO_ROOT)
    verify_lineage(prereg, repo_root=REPO_ROOT)
    sealed_registry_path = _programme_artifact_path(prereg, args.sealed_registry, "sealed-windows.json")
    sealed_registry = load_methodology_json(sealed_registry_path)
    validate_sealed_policy(prereg, sealed_registry)

    matches = [
        item
        for item in ledger["entries"]
        if item["entry_id"] == prereg["inference_ledger_entry_id"]
        and item["experiment_id"] == args.experiment_id
    ]
    if len(matches) > 1:
        raise MethodologyError("preregistration is registered more than once in programme inference ledger")
    if not matches:
        write_json(ledger_path, register_inference_entry(ledger, prereg))
        print(
            json.dumps(
                {
                    "status": "registration_prepared",
                    "entry_id": prereg["inference_ledger_entry_id"],
                    "next": "commit preregistration and ledger, create/push signed tag, then rerun freeze",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    binding = verify_remote_prereg_binding(REPO_ROOT, Path(args.prereg), args.tag, args.remote)
    dataset_manifest_path = Path(args.dataset_manifest)
    dataset_manifest = load_methodology_json(dataset_manifest_path)
    assurance = assert_preoutcome_freeze_ready(dataset_manifest.get("preoutcome_data_assurance"))
    expected_dataset = prereg["datasets"][0]
    identity = assurance["dataset_identity"]
    expected_identity = {
        "dataset_id": str(expected_dataset.get("id", "")),
        "vintage_id": str(expected_dataset.get("vintage", "")),
        "split_id": str(expected_dataset.get("split_id", "")),
    }
    observed_identity = {
        "dataset_id": str(identity.get("dataset_id", "")),
        "vintage_id": str(identity.get("vintage_id", "")),
        "split_id": str(identity.get("split_id", "")),
    }
    if observed_identity != expected_identity:
        raise MethodologyError("pre-outcome dataset assurance identity does not match preregistration")
    record = {
        "schema_version": 3,
        "experiment_id": args.experiment_id,
        "frozen": True,
        "prereg_sha256": verification["prereg_sha256"],
        "power": verification["power"],
        "programme_context": {
            **programme_context,
            "path": programme_evidence_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
            "sha256": sha256_file(programme_evidence_path),
        },
        "evidence_scan": evidence_scan,
        "literature_snapshot": literature_snapshot,
        "dataset_assurance": {
            "assurance_stage": "pre_outcome",
            "outcome_access_state": assurance["outcome_access_state"],
            "dataset_id": observed_identity["dataset_id"],
            "vintage_id": observed_identity["vintage_id"],
            "split_id": observed_identity["split_id"],
            "manifest_path": dataset_manifest_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
            "manifest_sha256": sha256_file(dataset_manifest_path),
            "assurance_sha256": assurance["assurance_sha256"],
        },
        "binding": binding,
        "inference_registration": {
            "entry_id": prereg["inference_ledger_entry_id"],
            "status": "remote_bound",
        },
    }
    write_immutable_json(Path(args.output), record)
    print(json.dumps(record, indent=2, sort_keys=True))

def _experiment_can_run(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    freeze = load_methodology_json(Path(args.freeze))
    ledger = load_methodology_json(_programme_artifact_path(prereg, args.ledger, "inference-ledger.json"))
    sealed = load_methodology_json(_programme_artifact_path(prereg, args.sealed_registry, "sealed-windows.json"))
    result = assert_confirmatory_execution_allowed(prereg, freeze, ledger, sealed)
    print(json.dumps(result, indent=2, sort_keys=True))

def _experiment_open_sealed(args: argparse.Namespace) -> None:
    prereg = load_methodology_json(Path(args.prereg))
    registry_path = _programme_artifact_path(prereg, args.sealed_registry, "sealed-windows.json")
    registry = load_methodology_json(registry_path)
    freeze = load_methodology_json(Path(args.freeze))
    ledger = load_methodology_json(_programme_artifact_path(prereg, args.ledger, "inference-ledger.json"))
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
    ledger_path = _programme_artifact_path(prereg, args.ledger, "inference-ledger.json")
    ledger = load_methodology_json(ledger_path)
    sealed = load_methodology_json(_programme_artifact_path(prereg, args.sealed_registry, "sealed-windows.json"))
    assert_confirmatory_execution_allowed(prereg, freeze, ledger, sealed)
    assurance = None
    if args.dataset_manifest is not None:
        dataset_manifest = load_methodology_json(Path(args.dataset_manifest))
        assurance = validate_post_unblinding_dataset_assurance(prereg, freeze, dataset_manifest)
    elif int(freeze.get("schema_version", 1)) >= 3:
        raise MethodologyError("schema-v3 confirmatory results require --dataset-manifest with post-unblinding assurance")
    run = load_methodology_json(Path(args.run_evidence))
    checks = load_methodology_json(Path(args.checks))
    verification = audit_leakage(checks)
    run_data = dict(run["data"])
    if assurance is not None:
        run_data["dataset_assurance_sha256"] = assurance["assurance_sha256"]
        run_data["preoutcome_assurance_sha256"] = assurance.get("preoutcome_assurance_sha256")
    results = build_results(
        prereg,
        run_id=str(run["run_id"]),
        code=run["code"],
        data=run_data,
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
    write_json(ledger_path, updated_ledger)
    programme_path = _programme_artifact_path(prereg, args.programme_evidence, "evidence-map.json")
    programme = load_methodology_json(programme_path)
    line_path = REPO_ROOT / prereg["lineage"]["research_line_ref"]
    line = load_methodology_json(line_path)
    new_scan_id = args.new_scan_id or f"{programme['current_scan_id']}:after:{prereg['experiment_id']}"
    updated_line = update_research_line(line, prereg, results)
    updated_programme = update_programme_evidence_map(programme, prereg, results, new_scan_id=new_scan_id)
    write_json(line_path, updated_line)
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

def _json_snapshot(path: Path, label: str) -> tuple[dict[str, object], str]:
    data = path.read_bytes()
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecisionSystemError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DecisionSystemError(f"{label} JSON must contain an object")
    return payload, hashlib.sha256(data).hexdigest()


def _stream_sha256(handle) -> str:
    handle.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _create_exclusive_run_directory(output: Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise DecisionSystemError(
            "refusing to overwrite an existing decision-system run path"
        ) from exc
    if output.is_symlink() or not output.is_dir():
        raise DecisionSystemError("decision-system run path is not an exclusive directory")
    return output


def _write_csv_exclusive(frame: pd.DataFrame, path: Path) -> None:
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        for value in frame[column].dropna():
            if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
                raise DecisionSystemError(
                    f"decision-system CSV contains spreadsheet formula text: {column}"
                )
    try:
        with Path(path).open("x", encoding="utf-8", newline="") as handle:
            frame.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise DecisionSystemError(f"decision-system output already exists: {path.name}") from exc


def _write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    content = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    try:
        with Path(path).open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise DecisionSystemError(f"decision-system output already exists: {path.name}") from exc


def _stable_code_identity(code: types.CodeType) -> dict[str, object]:
    def stable_constant(value: object) -> dict[str, object]:
        if isinstance(value, types.CodeType):
            return {"type": "code", "value": _stable_code_identity(value)}
        if value is None:
            return {"type": "none"}
        if value is Ellipsis:
            return {"type": "ellipsis"}
        if isinstance(value, bool):
            return {"type": "bool", "value": value}
        if isinstance(value, int):
            return {"type": "int", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value.hex()}
        if isinstance(value, complex):
            return {
                "type": "complex",
                "real": value.real.hex(),
                "imag": value.imag.hex(),
            }
        if isinstance(value, str):
            return {"type": "str", "value": value}
        if isinstance(value, bytes):
            return {"type": "bytes", "value": value.hex()}
        if isinstance(value, tuple):
            return {"type": "tuple", "items": [stable_constant(item) for item in value]}
        if isinstance(value, frozenset):
            items = [stable_constant(item) for item in value]
            items.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
            return {"type": "frozenset", "items": items}
        raise DecisionSystemError(
            f"unsupported loaded-code constant type: {type(value).__qualname__}"
        )

    return {
        "name": code.co_name,
        "qualname": code.co_qualname,
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "nlocals": code.co_nlocals,
        "stacksize": code.co_stacksize,
        "flags": code.co_flags,
        "code": code.co_code.hex(),
        "constants": [stable_constant(value) for value in code.co_consts],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
        "linetable": code.co_linetable.hex(),
        "exceptiontable": getattr(code, "co_exceptiontable", b"").hex(),
    }


def _loaded_module_code_sha256(module: types.ModuleType) -> str:
    source_path = Path(str(module.__file__)).resolve()
    records: list[tuple[str, dict[str, object]]] = []

    def add_code(label: str, function: object) -> None:
        code = getattr(function, "__code__", None)
        if isinstance(code, types.CodeType) and Path(code.co_filename).resolve() == source_path:
            records.append((label, _stable_code_identity(code)))

    for name, value in sorted(vars(module).items()):
        if inspect.isfunction(value) and getattr(value, "__module__", None) == module.__name__:
            add_code(name, value)
        elif inspect.isclass(value) and getattr(value, "__module__", None) == module.__name__:
            for member_name, member in sorted(vars(value).items()):
                if isinstance(member, (staticmethod, classmethod)):
                    add_code(f"{name}.{member_name}", member.__func__)
                elif isinstance(member, property):
                    for accessor, function in (("get", member.fget), ("set", member.fset), ("del", member.fdel)):
                        if function is not None:
                            add_code(f"{name}.{member_name}.{accessor}", function)
                else:
                    add_code(f"{name}.{member_name}", member)
    if not records:
        raise DecisionSystemError(f"no loaded module code objects found for module {module.__name__}")
    digest = hashlib.sha256()
    for label, code_identity in records:
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(
            json.dumps(
                code_identity,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        )
        digest.update(b"\0")
    return digest.hexdigest()


def _trading_decision_v0(args: argparse.Namespace) -> None:
    simulation_root, simulation_hash = _json_snapshot(
        config_path("simulation.json"), "simulation config"
    )
    simulation_id = args.simulation or str(simulation_root["default_decision_system_simulation"])
    simulations = simulation_root.get("decision_system_simulations")
    if not isinstance(simulations, dict) or simulation_id not in simulations:
        raise DecisionSystemError(f"decision-system simulation is unavailable: {simulation_id}")
    decision_cfg = simulations[simulation_id]
    if not isinstance(decision_cfg, dict):
        raise DecisionSystemError(f"decision-system simulation is invalid: {simulation_id}")
    if not decision_cfg.get("enabled", False):
        raise RuntimeError(f"decision-system simulation is disabled: {simulation_id}")
    if decision_cfg.get("state_mode") != "fresh_offline_replay":
        raise DecisionSystemError("Phase-1 decision engine requires fresh offline replay state")
    if decision_cfg.get("persistent_paper_state_supported") is not False:
        raise DecisionSystemError("Phase-1 decision engine must not claim persistent paper state")

    risk_root, trading_policy_hash = _json_snapshot(
        config_path("trading-policy.json"), "trading policy"
    )
    risk_policy_id = str(decision_cfg.get("risk_policy_id", "")).strip()
    if not risk_policy_id:
        raise DecisionSystemError("decision-system simulation must bind a fixed risk policy")
    if args.risk_policy is not None and args.risk_policy != risk_policy_id:
        raise DecisionSystemError(
            f"Phase-1 risk policy is fixed by the selected simulation: {risk_policy_id}"
        )
    try:
        risk_payload = risk_root["paper_risk_policies"][risk_policy_id]
    except KeyError as exc:
        raise DecisionSystemError(
            f"fixed decision-system risk policy is unavailable: {risk_policy_id}"
        ) from exc
    risk = parse_risk_policy(risk_payload)
    model_root, models_hash = _json_snapshot(config_path("models.json"), "models config")
    runtime_paths = {
        "decision_engine_sha256": REPO_ROOT / "src/commodity/trading_decision_v0.py",
        "cli_sha256": Path(__file__),
        "baseline_models_sha256": REPO_ROOT / "src/commodity/models/baselines.py",
        "requirements_lock_sha256": REPO_ROOT / "requirements.lock.txt",
    }
    runtime_hashes = {name: sha256_file(path) for name, path in runtime_paths.items()}
    loaded_modules = {
        "decision_engine_loaded_code_objects_sha256": sys.modules["commodity.trading_decision_v0"],
        "cli_loaded_code_objects_sha256": sys.modules[__name__],
        "baseline_models_loaded_code_objects_sha256": sys.modules["commodity.models.baselines"],
    }
    loaded_code_hashes = {
        name: _loaded_module_code_sha256(module) for name, module in loaded_modules.items()
    }

    market_path = Path(args.market)
    selected_path = Path(args.selected_path)
    features_path = Path(args.features)
    cost_path = Path(args.cost_assumptions)
    boundary_path = Path(args.input_boundary)
    cost_payload, cost_hash = _json_snapshot(cost_path, "cost assumptions")
    boundary_payload, boundary_hash = _json_snapshot(boundary_path, "input authority")
    authority_identity = governed_input_authority_identity(
        boundary_path,
        repo_root=REPO_ROOT,
        expected_sha256=boundary_hash,
    )

    with ExitStack() as stack:
        handles = {
            "market_sha256": stack.enter_context(market_path.open("rb")),
            "selected_path_sha256": stack.enter_context(selected_path.open("rb")),
            "features_sha256": stack.enter_context(features_path.open("rb")),
        }
        observed_hashes = {name: _stream_sha256(handle) for name, handle in handles.items()}
        boundary = parse_input_boundary(
            boundary_payload,
            allowed_partitions=set(decision_cfg["allowed_evidence_partitions"]),
            observed_hashes=observed_hashes,
            expected_instrument=str(decision_cfg["instrument"]),
            expected_roll_policy=str(decision_cfg["roll_policy"]),
        )
        for handle in handles.values():
            handle.seek(0)
        market = pd.read_csv(handles["market_sha256"])
        selected = pd.read_csv(handles["selected_path_sha256"])
        features = pd.read_csv(handles["features_sha256"])
        post_hashes = {name: _stream_sha256(handle) for name, handle in handles.items()}
        if post_hashes != observed_hashes:
            raise DecisionSystemError("decision-system input changed while being read")

    costs = parse_cost_assumptions(
        cost_payload,
        tick_value_usd=float(decision_cfg["tick_value_usd"]),
    )

    session_path = build_roll_safe_session_path(market, selected, price_col="open")
    models = model_root["models"]
    selected_model = args.model or decision_cfg["selected_model"]
    forecasts = build_walk_forward_forecasts(
        session_path,
        features,
        models=models,
        horizon_sessions=int(decision_cfg["horizon_sessions"]),
        contract_multiplier=float(decision_cfg["contract_multiplier_mmbtu"]),
        selected_model=selected_model,
        min_train_rows=int(decision_cfg["minimum_training_rows"]),
    )
    policy_forecasts = selected_model_forecasts(forecasts, selected_model)

    output = Path(args.output)
    if output.exists():
        raise DecisionSystemError("refusing to overwrite an existing decision-system run path")
    identity = {
        "schema_version": 1,
        "workflow": "phase1_trading_decision_system_v0",
        **observed_hashes,
        "cost_assumptions_sha256": cost_hash,
        "input_authority_sha256": authority_identity["sha256"],
        "input_authority_path": authority_identity["repo_relative_path"],
        "input_authority_git_commit": authority_identity["git_commit"],
        "input_authority_git_blob": authority_identity["git_blob"],
        "data_assurance_sha256": boundary.data_assurance_sha256,
        "models_config_sha256": models_hash,
        "simulation_config_sha256": simulation_hash,
        "trading_policy_config_sha256": trading_policy_hash,
        **runtime_hashes,
        **loaded_code_hashes,
        "simulation_id": simulation_id,
        "risk_policy_id": risk_policy_id,
        "selected_model": selected_model,
        "instrument": boundary.instrument,
        "roll_policy": boundary.roll_policy,
        "evidence_partition": boundary.evidence_partition,
        "protected_confirmation_accessed": boundary.protected_confirmation_accessed,
        "canonical_execution_evidence": False,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity["run_id"] = hashlib.sha256(encoded).hexdigest()
    session_path.insert(0, "run_id", identity["run_id"])
    forecasts.insert(0, "run_id", identity["run_id"])
    run_output = _create_exclusive_run_directory(output)
    _write_csv_exclusive(session_path, run_output / "session_path.csv")
    _write_csv_exclusive(forecasts, run_output / "forecasts.csv")
    summaries: dict[str, object] = {}
    empty = pd.DataFrame()
    for policy_id in decision_cfg["benchmark_policies"]:
        consumed = policy_forecasts if policy_id == "forecast_sign" else empty
        ledger, summary = simulate_policy(
            session_path,
            consumed,
            policy_id,
            risk,
            costs,
            contract_multiplier=float(decision_cfg["contract_multiplier_mmbtu"]),
        )
        ledger.insert(0, "run_id", identity["run_id"])
        _write_csv_exclusive(ledger, run_output / f"ledger-{policy_id}.csv")
        _write_csv_exclusive(
            ledger[["run_id", "trade_date", "session_open", "equity_usd"]],
            run_output / f"equity-{policy_id}.csv",
        )
        summaries[policy_id] = summary

    _write_json_exclusive(run_output / "input_manifest.json", identity)
    _write_json_exclusive(
        run_output / "summary.json",
        {
            "schema_version": 1,
            "run_id": identity["run_id"],
            "selected_model": selected_model,
            "instrument": boundary.instrument,
            "roll_policy": boundary.roll_policy,
            "round_trip_cost_usd": costs.round_trip_usd,
            "benchmark_summaries": summaries,
            "risk_state_scope": "fresh_offline_replay",
            "persistent_paper_state_supported": False,
            "scientific_scope": "plumbing_and_executable_benchmark_only_no_edge_claim",
        },
    )
    if {name: sha256_file(path) for name, path in runtime_paths.items()} != runtime_hashes:
        raise DecisionSystemError("decision-system runtime source changed during execution")
    if {
        name: _loaded_module_code_sha256(module) for name, module in loaded_modules.items()
    } != loaded_code_hashes:
        raise DecisionSystemError("decision-system loaded code-object identity changed during execution")
    if governed_input_authority_identity(
        boundary_path,
        repo_root=REPO_ROOT,
        expected_sha256=boundary_hash,
    ) != authority_identity:
        raise DecisionSystemError("input authority identity changed during execution")
    output_hashes = {
        path.name: sha256_file(path)
        for path in sorted(run_output.iterdir(), key=lambda item: item.name)
        if path.is_file()
    }
    completion = {
        "schema_version": 1,
        "status": "complete",
        "run_id": identity["run_id"],
        "outputs": output_hashes,
    }
    _write_json_exclusive(run_output / "completion_manifest.json", completion)
    print(json.dumps({"run_id": identity["run_id"], "output": str(run_output)}, indent=2))


def _phase2_market_only(args: argparse.Namespace) -> None:
    result = run_phase2_market_only(
        config_path("phase2_market_only.json"),
        Path(args.databento_root),
        checkpoint_dir=Path(args.checkpoint_dir),
        heartbeat_seconds=float(args.heartbeat_seconds),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise Phase2MarketOnlyError("refusing to overwrite an existing Phase-2 freeze") from exc
    print(
        json.dumps(
            {
                "output": str(output),
                "candidate_id": result["baseline_freeze"]["candidate_id"],
                "freeze_sha256": result["baseline_freeze"]["freeze_sha256"],
            },
            indent=2,
        )
    )


def _phase3_fundamentals(args: argparse.Namespace) -> None:
    result = run_phase3_fundamentals(
        config_path("phase3_fundamentals.json"),
        config_path("phase2_market_only.json"),
        REPO_ROOT / "research/programmes/003-natural-gas-trading-decision-system/phase2-market-only-baseline-v1.json",
        Path(args.databento_root),
        Path(args.bhlr_root),
        checkpoint_dir=Path(args.checkpoint_dir),
        heartbeat_seconds=float(args.heartbeat_seconds),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise Phase3RuntimeError("refusing to overwrite an existing Phase-3 result") from exc
    print(json.dumps({"output": str(output), "disposition": result["disposition"]}, indent=2))


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
    snapshot_root = str(REPO_ROOT / "data/raw/snapshots")
    metrics_ledger_path = REPO_ROOT / "artifacts/research-metrics/longitudinal-ledger.json"
    parser = argparse.ArgumentParser(prog="commodity")
    sub = parser.add_subparsers(required=True)

    fetch = sub.add_parser("fetch-market")
    fetch.add_argument("--start", required=True)
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--output", default=str(REPO_ROOT / "data/raw/ng_f_daily.csv"))
    fetch.set_defaults(func=_fetch_market)

    canonical = sub.add_parser("fetch-canonical-market")
    canonical.add_argument("--start", required=True)
    canonical.add_argument("--end", required=True)
    canonical.add_argument("--output", default=str(REPO_ROOT / "data/raw/ng_contract_history.csv"))
    canonical.set_defaults(func=_fetch_canonical_market)

    weather = sub.add_parser("capture-weather-run")
    weather.add_argument("--run", required=True)
    weather.add_argument("--latitude", type=float, required=True)
    weather.add_argument("--longitude", type=float, required=True)
    weather.add_argument("--snapshot-id", required=True)
    weather.add_argument("--model", default="ecmwf_ifs")
    weather.add_argument("--forecast-days", type=int, default=10)
    weather.add_argument("--hourly", default="temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m")
    weather.add_argument("--output-root", default=snapshot_root)
    weather.set_defaults(func=_capture_weather_run)

    signal_cfg = signal_policy_config()
    simulation_cfg = simulation_config()
    for command in ("simulate", "backtest"):
        sim = sub.add_parser(command)
        sim.add_argument("--predictions", required=True)
        sim.add_argument("--policy", default=signal_cfg["default_policy"])
        sim.add_argument("--simulation", default=simulation_cfg["default_simulation"])
        sim.add_argument("--output", required=True)
        sim.set_defaults(func=_simulate)

    decision = sub.add_parser(
        "trading-decision-v0",
        help="Phase-1 fresh offline NG forecast-to-equity replay",
    )
    decision.add_argument("--market", required=True)
    decision.add_argument("--selected-path", required=True)
    decision.add_argument("--features", required=True)
    decision.add_argument("--cost-assumptions", required=True)
    decision.add_argument("--input-boundary", required=True)
    decision.add_argument("--simulation")
    decision.add_argument("--risk-policy")
    decision.add_argument("--model")
    decision.add_argument("--output", required=True)
    decision.set_defaults(func=_trading_decision_v0)

    phase2 = sub.add_parser(
        "phase2-market-only",
        help="Phase-2 pre-2023 nested market-only development and baseline freeze",
    )
    phase2.add_argument("--databento-root", required=True)
    phase2.add_argument(
        "--checkpoint-dir",
        default=str(REPO_ROOT / ".work/checkpoints/phase2-market-only-v1"),
    )
    phase2.add_argument("--heartbeat-seconds", type=float, default=30.0)
    phase2.add_argument(
        "--output",
        default=str(
            REPO_ROOT
            / "research/programmes/003-natural-gas-trading-decision-system/phase2-market-only-baseline-v1.json"
        ),
    )
    phase2.set_defaults(func=_phase2_market_only)

    phase3 = sub.add_parser(
        "phase3-fundamentals",
        help="Phase-3 pre-2023 PIT physical-balance contribution test",
    )
    phase3.add_argument("--databento-root", required=True)
    phase3.add_argument("--bhlr-root", required=True)
    phase3.add_argument(
        "--checkpoint-dir",
        default=str(REPO_ROOT / ".work/checkpoints/phase3-pit-fundamentals-v1"),
    )
    phase3.add_argument("--heartbeat-seconds", type=float, default=30.0)
    phase3.add_argument(
        "--output",
        default=str(
            REPO_ROOT
            / "research/programmes/003-natural-gas-trading-decision-system/phase3-pit-fundamentals-v1.json"
        ),
    )
    phase3.set_defaults(func=_phase3_fundamentals)

    saxo = sub.add_parser("probe-saxo-market")
    saxo.add_argument("--continuous-uic", type=int)
    saxo.add_argument("--max-contracts", type=int, default=24)
    saxo.add_argument("--output")
    saxo.set_defaults(func=_probe_saxo_market)

    metrics_check = sub.add_parser("check-research-metrics")
    metrics_check.add_argument("--ledger", type=Path, default=metrics_ledger_path)
    metrics_check.set_defaults(func=_check_research_metrics)

    metrics_summary = sub.add_parser("summarize-research-metrics")
    metrics_summary.add_argument("--ledger", type=Path, default=metrics_ledger_path)
    metrics_summary.add_argument("--output", type=Path)
    metrics_summary.set_defaults(func=_summarize_research_metrics)

    experiment = sub.add_parser("experiment", help="Governed hypothesis/experiment lifecycle")
    experiment_sub = experiment.add_subparsers(required=True)
    register = experiment_sub.add_parser("register")
    register.add_argument("experiment_id")
    register.add_argument("--prereg", type=Path, required=True)
    register.add_argument("--ledger", type=Path)
    register.set_defaults(func=_experiment_register)

    verify = experiment_sub.add_parser("verify")
    verify.add_argument("--prereg", type=Path, required=True)
    verify.set_defaults(func=_experiment_verify)

    verify_power_cmd = experiment_sub.add_parser("verify-power")
    verify_power_cmd.add_argument("--prereg", type=Path, required=True)
    verify_power_cmd.set_defaults(func=_experiment_verify_power)

    freeze_exp = experiment_sub.add_parser("freeze")
    freeze_exp.add_argument("experiment_id")
    freeze_exp.add_argument("--prereg", type=Path, required=True)
    freeze_exp.add_argument("--ledger", type=Path)
    freeze_exp.add_argument("--programme-evidence", type=Path)
    freeze_exp.add_argument("--sealed-registry", type=Path)
    freeze_exp.add_argument("--dataset-manifest", type=Path, required=True)
    freeze_exp.add_argument("--tag", required=True)
    freeze_exp.add_argument("--remote", default="origin")
    freeze_exp.add_argument("--output", type=Path, required=True)
    freeze_exp.set_defaults(func=_experiment_freeze)

    can_run = experiment_sub.add_parser("can-run")
    can_run.add_argument("--prereg", type=Path, required=True)
    can_run.add_argument("--freeze", type=Path, required=True)
    can_run.add_argument("--ledger", type=Path)
    can_run.add_argument("--sealed-registry", type=Path)
    can_run.set_defaults(func=_experiment_can_run)

    open_sealed = experiment_sub.add_parser("open-sealed")
    open_sealed.add_argument("experiment_id")
    open_sealed.add_argument("sealed_window_id")
    open_sealed.add_argument("--prereg", type=Path, required=True)
    open_sealed.add_argument("--freeze", type=Path, required=True)
    open_sealed.add_argument("--ledger", type=Path)
    open_sealed.add_argument("--artifacts-exposed", required=True)
    open_sealed.add_argument("--sealed-registry", type=Path)
    open_sealed.set_defaults(func=_experiment_open_sealed)

    build_results_cmd = experiment_sub.add_parser("build-results")
    build_results_cmd.add_argument("--prereg", type=Path, required=True)
    build_results_cmd.add_argument("--freeze", type=Path, required=True)
    build_results_cmd.add_argument("--ledger", type=Path)
    build_results_cmd.add_argument("--sealed-registry", type=Path)
    build_results_cmd.add_argument("--programme-evidence", type=Path)
    build_results_cmd.add_argument("--new-scan-id")
    build_results_cmd.add_argument("--dataset-manifest", type=Path)
    build_results_cmd.add_argument("--run-evidence", type=Path, required=True)
    build_results_cmd.add_argument("--checks", type=Path, required=True)
    build_results_cmd.add_argument("--output", type=Path, required=True)
    build_results_cmd.set_defaults(func=_experiment_build_results)

    verify_results_cmd = experiment_sub.add_parser("verify-results")
    verify_results_cmd.add_argument("--prereg", type=Path, required=True)
    verify_results_cmd.add_argument("--results", type=Path, required=True)
    verify_results_cmd.set_defaults(func=_experiment_verify_results)

    leakage = experiment_sub.add_parser("audit-leakage")
    leakage.add_argument("--checks", type=Path, required=True)
    leakage.set_defaults(func=_experiment_audit_leakage)

    reproduce_exp = experiment_sub.add_parser("reproduce")
    reproduce_exp.add_argument("--reference", type=Path, required=True)
    reproduce_exp.add_argument("--candidate", type=Path)
    reproduce_exp.add_argument("--tolerance", type=Path, required=True)
    reproduce_exp.add_argument("--byte", action="store_true")
    reproduce_exp.add_argument("--command", type=Path)
    reproduce_exp.add_argument("--output", type=Path)
    reproduce_exp.add_argument("--cwd", type=Path, default=REPO_ROOT)
    reproduce_exp.set_defaults(func=_experiment_reproduce)

    summary_exp = experiment_sub.add_parser("executive-summary")
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
