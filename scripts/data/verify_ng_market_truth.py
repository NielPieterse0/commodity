"""Fail-closed Phase 2 market-truth policy checks; never reads raw market data."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from commodity.market_truth.approval import TRUSTED_SIGNERS, verify_catalog_signature

ROOT = Path(__file__).resolve().parents[2]


def verify() -> None:
    platform = json.loads(
        (ROOT / "config/data_platform.json").read_text(encoding="utf-8")
    )
    phase = platform["stages"]["phase_2"]
    expected = {
        "name": "natural_gas_market_truth",
        "implementation_issue": 482,
        "source_authority": "config/data_sources.json#sources.databento_henry_hub",
        "source_attestation_schema": "contracts/ng_market_truth.schema.json",
        "build_entrypoint": "scripts/data/build_ng_market_truth.py",
        "module": "commodity.market_truth",
        "development_max_session": "2022-12-31",
        "curve_ranks": 12,
        "no_synthetic_continuous_authority": True,
        "source_revision_policy": "append_only",
        "development_input_root": ".work/runtime/market_truth_development",
        "source_license": "private_project_research_only",
        "real_history_completion_rule": (
            "blocked_until_development_only_original_source_and_processed_parquet_identities_are_verified_and_owner_approved"
        ),
        "incremental_recurring_spend_target_usd": 0,
    }
    if phase != expected:
        raise ValueError("PHASE2_ARCHITECTURE_CONTRACT_DRIFT")
    storage = platform["raw_evidence"]
    if (
        storage.get("local_working_copy_is_canonical_archive") is not True
        or storage.get("restore_drill_required") is not False
        or storage.get("phase_1_archive_ladder") != []
        or storage.get("archive_interface")
        != "local_original_source_and_parquet_manifest_with_sha256; external_archival_optional"
    ):
        raise ValueError("PHASE2_LOCAL_STORAGE_OWNER_POLICY_DRIFT")
    schema = json.loads(
        (ROOT / phase["source_attestation_schema"]).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    for key in ("definitions", "bars", "statistics"):
        if key not in schema["properties"]["inputs"]["properties"]:
            raise ValueError("PHASE2_SOURCE_SCHEMA_MISSING_" + key.upper())
    sources = json.loads(
        (ROOT / "config/data_sources.json").read_text(encoding="utf-8")
    )
    databento = sources["sources"]["databento_henry_hub"]
    if not (
        databento["dataset"] == "GLBX.MDP3"
        and databento["product_code"] == "NG"
        and databento["canonical_market_source"] is True
        and databento["backtest_evidence_allowed"] is True
        and databento["redistribution_allowed"] is False
    ):
        raise ValueError("PHASE2_APPROVED_SOURCE_BOUNDARY_CHANGED")
    # Research readers may admit only externally reviewed content identities.
    # Empty is the safe initial state; the build script never writes approvals.
    catalog_bytes = (ROOT / "data/manifests/ng-phase2-market-truth.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    if (
        not isinstance(catalog, dict)
        or not {"schema_version", "authority", "datasets"}.issubset(catalog)
        or catalog["schema_version"] != 2
        or catalog["authority"] != "governed_source_owner_review"
        or not isinstance(catalog["datasets"], list)
    ):
        raise ValueError("PHASE2_SOURCE_APPROVAL_CATALOG_INVALID")
    identities = set()
    for item in catalog["datasets"]:
        if not isinstance(item, dict) or set(item) != {
            "content_sha256", "source_manifest_sha256", "source_sha256",
            "tables_sha256", "source_review_id", "local_evidence_verified",
        }:
            raise ValueError("PHASE2_SOURCE_APPROVAL_ENTRY_INVALID")
        if (
            item["local_evidence_verified"] is not True
            or not isinstance(item["source_review_id"], str)
            or not item["source_review_id"].strip()
            or not isinstance(item["source_sha256"], dict)
            or set(item["source_sha256"]) != {"definitions", "bars", "statistics"}
            or not isinstance(item["tables_sha256"], dict)
            or set(item["tables_sha256"]) != {"definitions", "bars", "statistics"}
            or any(
                not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in (
                    item["content_sha256"], item["source_manifest_sha256"],
                    *item["source_sha256"].values(), *item["tables_sha256"].values(),
                )
            )
        ):
            raise ValueError("PHASE2_SOURCE_APPROVAL_EVIDENCE_INVALID")
        if item["content_sha256"] in identities:
            raise ValueError("PHASE2_SOURCE_APPROVAL_DUPLICATE")
        identities.add(item["content_sha256"])
    verify_catalog_signature(
        catalog, catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        trusted_signers=TRUSTED_SIGNERS,
    )
    for owned in [
        "src/commodity/market_truth/core.py",
        "src/commodity/market_truth/ng.py",
        "src/commodity/market_truth/query.py",
        "scripts/data/build_ng_market_truth.py",
        "tests/data_platform/test_ng_market_truth.py",
    ]:
        if not (ROOT / owned).is_file():
            raise ValueError("PHASE2_MISSING_IMPLEMENTATION:" + owned)


def main() -> int:
    try:
        verify()
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"ng-market-truth-verification: FAILED: {exc}")
        return 2
    print("ng-market-truth-verification: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
