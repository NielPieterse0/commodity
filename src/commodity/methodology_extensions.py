from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def compute_effective_information(dependence: dict[str, Any]) -> dict[str, Any]:
    """Compute effective information from declared dependence assumptions.

    Newey-West/HAC uses declared autocorrelations with Bartlett weights. Block-bootstrap
    designs use the declared block length as the conservative information unit.
    """
    from commodity.research_methodology import MethodologyError

    raw_n = int(dependence.get("raw_n", 0))
    if raw_n <= 1:
        raise MethodologyError("dependence.raw_n must exceed one")
    method = dependence.get("method")
    parameters = dependence.get("parameters") or {}
    if method == "independent":
        effective = float(raw_n)
    elif method == "ar1":
        rho = float(parameters.get("rho"))
        if not -0.99 < rho < 0.99:
            raise MethodologyError("ar1 rho must be inside (-0.99, 0.99)")
        effective = raw_n * (1.0 - rho) / (1.0 + rho)
    elif method == "overlapping_horizon":
        horizon = int(parameters.get("horizon", 0))
        if horizon < 1:
            raise MethodologyError("overlapping horizon must be positive")
        effective = raw_n / horizon
    elif method == "event_clusters":
        clusters = int(parameters.get("clusters", 0))
        if not 1 < clusters <= raw_n:
            raise MethodologyError("event clusters must be between two and raw_n")
        effective = float(clusters)
    elif method in {"newey_west", "hac"}:
        autocorrelations = parameters.get("autocorrelations")
        if not isinstance(autocorrelations, list) or not autocorrelations:
            raise MethodologyError("Newey-West/HAC requires declared autocorrelations")
        lag = int(parameters.get("lag", len(autocorrelations)))
        if lag < 1 or lag > len(autocorrelations) or lag >= raw_n:
            raise MethodologyError("Newey-West/HAC lag is invalid")
        rhos = [float(value) for value in autocorrelations[:lag]]
        if any(not math.isfinite(value) or not -1 < value < 1 for value in rhos):
            raise MethodologyError("Newey-West/HAC autocorrelations must be finite inside (-1, 1)")
        variance_inflation = 1.0 + 2.0 * sum(
            (1.0 - index / (lag + 1.0)) * rho
            for index, rho in enumerate(rhos, start=1)
        )
        if not math.isfinite(variance_inflation) or variance_inflation <= 0:
            raise MethodologyError("Newey-West/HAC variance inflation must be positive")
        effective = raw_n / variance_inflation
    elif method == "block_bootstrap":
        block_length = int(parameters.get("block_length", 0))
        if block_length < 1 or block_length >= raw_n:
            raise MethodologyError("block-bootstrap block_length must be inside [1, raw_n)")
        effective = raw_n / block_length
    else:
        raise MethodologyError(f"unsupported dependence method: {method!r}")
    if not math.isfinite(effective) or effective <= 1:
        raise MethodologyError("effective information is insufficient")
    return {
        "raw_n": raw_n,
        "method": method,
        "parameters": parameters,
        "effective_information": effective,
    }


def freeze_with_registration(args: Any, cli: Any) -> None:
    """Make freeze own programme-inference registration in a safe two-pass flow.

    First invocation validates all design gates and writes the missing ledger registration.
    The operator then commits/tags/pushes the preregistration and ledger together. A second
    invocation verifies that remote binding and writes the immutable freeze record.
    """
    prereg = cli.load_methodology_json(Path(args.prereg))
    verification = cli.verify_preregistration(prereg)
    if prereg["experiment_id"] != args.experiment_id:
        raise cli.MethodologyError("experiment_id does not match preregistration")

    ledger_path = Path(args.ledger)
    ledger = cli.load_methodology_json(ledger_path)
    cli.validate_inference_ledger(ledger)
    programme_evidence_path = Path(args.programme_evidence)
    programme_evidence = cli.load_methodology_json(programme_evidence_path)
    from commodity.research_methodology import verify_lineage, verify_reference_artifact

    programme_context = cli.validate_programme_context(prereg, programme_evidence)
    evidence_scan = verify_reference_artifact(prereg["evidence_scan_ref"], cli.REPO_ROOT)
    literature_snapshot = verify_reference_artifact(prereg["literature_snapshot_ref"], cli.REPO_ROOT)
    verify_lineage(prereg, repo_root=cli.REPO_ROOT)
    sealed_registry = cli.load_methodology_json(Path(args.sealed_registry))
    cli.validate_sealed_policy(prereg, sealed_registry)

    matches = [
        item
        for item in ledger["entries"]
        if item["entry_id"] == prereg["inference_ledger_entry_id"]
        and item["experiment_id"] == args.experiment_id
    ]
    if len(matches) > 1:
        raise cli.MethodologyError(
            "preregistration is registered more than once in programme inference ledger"
        )
    if not matches:
        updated = cli.register_inference_entry(ledger, prereg)
        cli.write_json(ledger_path, updated)
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

    binding = cli.verify_remote_prereg_binding(
        cli.REPO_ROOT,
        Path(args.prereg),
        args.tag,
        args.remote,
    )
    record = {
        "schema_version": 1,
        "experiment_id": args.experiment_id,
        "frozen": True,
        "prereg_sha256": verification["prereg_sha256"],
        "power": verification["power"],
        "programme_context": {
            **programme_context,
            "path": programme_evidence_path.resolve()
            .relative_to(cli.REPO_ROOT.resolve())
            .as_posix(),
            "sha256": cli.sha256_file(programme_evidence_path),
        },
        "evidence_scan": evidence_scan,
        "literature_snapshot": literature_snapshot,
        "binding": binding,
        "inference_registration": {
            "entry_id": prereg["inference_ledger_entry_id"],
            "status": "remote_bound",
        },
    }
    cli.write_immutable_json(Path(args.output), record)
    print(json.dumps(record, indent=2, sort_keys=True))
