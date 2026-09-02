from __future__ import annotations

from pathlib import Path

import pandas as pd

from commodity.cftc import load_cftc_v1_window
from commodity.config import REPO_ROOT, data_config, research_dataset_config
from commodity.data_assurance import (
    build_construction_contract,
    canonical_json_sha256,
    verify_reconstruction_pair,
    verify_semantic_assurance,
)
from commodity.dataset_audit import DatasetAudit, audit_full_v1_dataset
from commodity.dataset_freeze import freeze_full_v1_dataset
from commodity.evidence_authority import evaluation_authority_is_valid
from commodity.nyiso import load_nyiso_v1_window
from commodity.provenance import sha256_file
from commodity.providers.massive_futures import reconstruct_massive_archive
from commodity.research_dataset import PitFeatureSource, build_pit_dataset
from commodity.weather import load_weather_v1_window
from commodity.wngsr import load_wngsr_v1_window

FULL_V1_START = "2024-08-13T23:59:00Z"
FULL_V1_END = "2026-08-12T23:59:00Z"
SNAPSHOT_ROOT = REPO_ROOT / "data" / "raw" / "snapshots"
MARKET_SOURCE_ID = "massive_henry_hub_evaluation"
MARKET_CONTRACTS = (
    SNAPSHOT_ROOT
    / "massive"
    / "20240813-20260812-v1-m1-m12"
    / "canonical.csv"
)


def _source(
    name: str,
    family: str,
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    source_id: str,
) -> PitFeatureSource:
    return PitFeatureSource(
        name=name,
        family=family,
        frame=frame,
        value_columns=columns,
        group_columns=(),
        evidence_mode="research_pit",
        source_id=source_id,
        source_vintage=f"v1-window:{FULL_V1_START}:{FULL_V1_END}",
    )


def _load_sources(snapshot_root: Path) -> tuple[PitFeatureSource, ...]:
    storage = load_wngsr_v1_window(snapshot_root, FULL_V1_START, FULL_V1_END)
    weather = load_weather_v1_window(snapshot_root, FULL_V1_START, FULL_V1_END)
    power = load_nyiso_v1_window(snapshot_root, FULL_V1_START, FULL_V1_END)
    positioning = load_cftc_v1_window(snapshot_root, FULL_V1_START, FULL_V1_END)
    weather_columns = tuple(column for column in weather if column.startswith("weather_"))
    return (
        _source(
            "wngsr_storage",
            "storage",
            storage,
            ("storage_lower48_bcf", "storage_weekly_change_bcf"),
            "eia_wngsr_vintage_reconstruction",
        ),
        _source(
            "issued_weather",
            "weather",
            weather,
            weather_columns,
            "open_meteo_single_runs_v1",
        ),
        _source(
            "nyiso_load_forecast",
            "power",
            power,
            (
                "power_next_day_load_mean_mw",
                "power_next_day_load_max_mw",
                "power_next_day_load_min_mw",
            ),
            "nyiso_p7_iso_load_forecast",
        ),
        _source(
            "cftc_positioning",
            "positioning",
            positioning,
            (
                "open_interest",
                "producer_merchant_net",
                "swap_dealer_net",
                "managed_money_net",
                "other_reportable_net",
                "managed_money_long_pct_oi",
                "managed_money_short_pct_oi",
            ),
            "cftc_disaggregated_futures_only_023651",
        ),
    )


def _bind_market_archive_assurance(manifest: dict, market_manifest: Path) -> None:
    assurance = manifest.get("data_assurance")
    if not isinstance(assurance, dict):
        raise TypeError("V1 dataset build did not produce provisional data assurance")
    archive_sha256 = sha256_file(market_manifest)
    source_inputs = [*list(assurance["source_inputs"])]
    source_inputs.append(
        {
            "id": f"market-archive:{MARKET_SOURCE_ID}",
            "sha256": archive_sha256,
        }
    )
    layers = [dict(item) for item in assurance["layers"]]
    for layer in layers:
        if layer.get("name") == "retained_source_evidence":
            layer["sha256"] = canonical_json_sha256(source_inputs)
            break
    else:
        raise ValueError("V1 dataset assurance lacks retained_source_evidence layer")
    transformation_sha256 = dict(assurance["transformation_sha256"])
    transformation_sha256.update(
        {
            "full_v1": sha256_file(Path(__file__)),
            "massive_futures_provider": sha256_file(
                REPO_ROOT / "src" / "commodity" / "providers" / "massive_futures.py"
            ),
        }
    )
    manifest["market_archive_manifest_sha256"] = archive_sha256
    manifest["data_assurance"] = build_construction_contract(
        source_inputs=source_inputs,
        layers=layers,
        transformation_sha256=transformation_sha256,
    )


def _build_once(
    snapshot_root: Path,
    market_contracts: Path,
) -> tuple[pd.DataFrame, dict]:
    market_manifest = Path(market_contracts).parent / "manifest.json"
    if not market_manifest.is_file():
        raise ValueError(f"Massive V1 market snapshot manifest is missing: {market_manifest}")
    contracts = reconstruct_massive_archive(
        market_manifest,
        data_config()["canonical_contract_schema"],
    )
    dataset, manifest = build_pit_dataset(
        None,
        exogenous=_load_sources(snapshot_root),
        evidence_mode="evaluation_pit",
        require_full_v1=True,
        canonical_contracts=contracts,
        market_source_id=MARKET_SOURCE_ID,
    )
    _bind_market_archive_assurance(manifest, market_manifest)
    return dataset, manifest


def _full_v1_semantic_evidence(manifest: dict) -> dict:
    required = set(research_dataset_config()["dataset"]["required_feature_families"])
    market = manifest.get("market_structure") or {}
    representation = market.get("representation") or {}
    family_audits = manifest.get("exogenous_family_audits") or {}
    checks = {
        "full_v1_contract": manifest.get("completeness") == "full_v1",
        "required_feature_families": (
            set(manifest.get("required_feature_families", [])) == required
            and required.issubset(set(manifest.get("included_feature_families", [])))
            and not manifest.get("missing_feature_families")
        ),
        "evaluation_authority": evaluation_authority_is_valid(manifest),
        "market_source_identity": manifest.get("market_source_id") == MARKET_SOURCE_ID,
        "target_semantics": manifest.get("target") == "target_ret_1",
        "prediction_cutoff_semantics": manifest.get("prediction_timestamp_semantics")
        == "explicit_or_conservatively_derived_market_available_at_cutoff",
        "selected_contract_feature_returns": market.get("feature_return_semantics")
        == "selected_contract_own_prior_session",
        "same_contract_target_returns": market.get("target_return_semantics")
        == "consecutive_selected_rows_same_contract_only",
        "cross_contract_returns_prohibited": market.get("cross_contract_returns_allowed") is False,
        "synthetic_series_not_tradable": market.get("synthetic_series_tradable") is False,
        "raw_contract_authority": representation.get("authoritative_storage") == "raw_per_contract",
        "unadjusted_storage": representation.get("adjustment_method") == "none_stored_raw",
        "exogenous_family_semantics": all(
            family in family_audits
            and family_audits[family]
            and all(item.get("full_v1_ready") is True for item in family_audits[family])
            for family in ("storage", "weather", "power", "positioning")
        ),
    }
    return {"method": "explicit_dataset_semantics_v1", "checks": checks}


def build_verified_full_v1_evaluation_dataset(
    *,
    snapshot_root: Path = SNAPSHOT_ROOT,
    market_contracts: Path = MARKET_CONTRACTS,
) -> tuple[pd.DataFrame, dict, DatasetAudit]:
    first, first_manifest = _build_once(snapshot_root, market_contracts)
    second, second_manifest = _build_once(snapshot_root, market_contracts)
    reconstruction = verify_reconstruction_pair(
        first,
        first_manifest["data_assurance"],
        second,
        second_manifest["data_assurance"],
    )
    first_manifest["data_assurance"] = verify_semantic_assurance(
        reconstruction,
        semantic_evidence=_full_v1_semantic_evidence(first_manifest),
    )
    audit = audit_full_v1_dataset(first, first_manifest)
    if audit.verdict == "not-fit":
        raise ValueError(f"verified full_v1 reconstruction failed audit: {audit.blockers}")
    return first, first_manifest, audit


def freeze_verified_full_v1(output_root: Path) -> Path:
    frame, manifest, _ = build_verified_full_v1_evaluation_dataset()
    return freeze_full_v1_dataset(frame, manifest, output_root)
