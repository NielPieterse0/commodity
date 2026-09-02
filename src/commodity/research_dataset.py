from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from commodity.availability import asof_join_point_in_time, validate_availability
from commodity.config import (
    REPO_ROOT,
    assumptions_config,
    data_config,
    research_dataset_config,
)
from commodity.data_assurance import (
    build_construction_contract,
    canonical_json_sha256,
    file_identity,
)
from commodity.exogenous_audit import (
    REQUIRED_EXOGENOUS_FAMILIES,
    audit_configured_exogenous_family,
    exogenous_frame_sha256,
)
from commodity.features import build_market_features, make_supervised
from commodity.market_data import (
    assert_canonical_market_ready,
    assert_market_evaluation_ready,
    build_market_structure_features,
    ensure_canonical_market_availability,
    resolve_market_source,
    validate_contract_history,
)
from commodity.roll_safe_market import same_contract_selected_returns
from commodity.rolls import build_derived_continuous_series

TARGET_COLUMN = "target_ret_1"
_PIT_MODES = {"research_pit", "evaluation_pit", "canonical"}


@dataclass(frozen=True)
class PitFeatureSource:
    name: str
    family: str
    frame: pd.DataFrame
    value_columns: tuple[str, ...]
    group_columns: tuple[str, ...]
    evidence_mode: str = "research_pit"
    source_id: str | None = None
    source_vintage: str | None = None

    def __post_init__(self) -> None:
        if self.group_columns is None:
            raise TypeError(
                "PitFeatureSource.group_columns must explicitly declare () for a "
                "single/pre-aggregated source or name the source group identity"
            )


def _required_families() -> tuple[str, ...]:
    dataset_cfg = research_dataset_config()["dataset"]
    return tuple(str(value) for value in dataset_cfg["required_feature_families"])


def dataframe_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.copy()
    canonical.index = pd.to_datetime(canonical.index, utc=True)
    payload = canonical.to_csv(
        index=True,
        index_label="prediction_time",
        lineterminator="\n",
        float_format="%.17g",
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_market_frame(ohlcv: pd.DataFrame) -> pd.DataFrame:
    frame = ohlcv.copy()
    raw_index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True))
    if "available_at" in frame.columns:
        available = pd.DatetimeIndex(pd.to_datetime(frame.pop("available_at"), utc=True, errors="coerce"))
        if available.isna().any():
            raise ValueError("Market available_at must be explicit and valid")
        frame.index = available
    elif (raw_index == raw_index.normalize()).all():
        # Date-only daily bars do not literally encode when their values became knowable.
        # Use the same conservative bound owned by canonical market availability policy.
        frame.index = raw_index.normalize() + pd.Timedelta(hours=23, minutes=59)
    else:
        frame.index = raw_index
    frame = frame.sort_index()
    if frame.index.has_duplicates:
        raise ValueError("Market frame must have a unique chronological availability index")
    return frame


def _table_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=True, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_supervised_dataset(
    contracts: pd.DataFrame,
    *,
    promotion_required: bool,
    market_source_id: str | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = data_config()
    assumptions = assumptions_config()
    selected_source_id, source = resolve_market_source(cfg, market_source_id)
    if promotion_required:
        assert_canonical_market_ready(cfg, assumptions, selected_source_id)
    else:
        assert_market_evaluation_ready(cfg, assumptions, selected_source_id)
    schema = cfg["canonical_contract_schema"]
    policy = assumptions["assumptions"]["continuous_series_policy"]["policy"]
    available = ensure_canonical_market_availability(
        contracts, source.get("availability_policy", {})
    )
    normalized = validate_contract_history(available, schema)
    required = {"available_at", "settle", "high", "low", "volume"}
    missing = sorted(required - set(normalized.columns))
    if missing:
        raise ValueError(f"Canonical contract rows missing market features: {missing}")
    if normalized["available_at"].isna().any():
        raise ValueError("Canonical contract rows require non-null available_at")

    path, ledger = build_derived_continuous_series(normalized, schema, policy)
    prediction_time = pd.DatetimeIndex(pd.to_datetime(path["available_at"], utc=True))
    target_returns = path["settle_log_return"].astype(float)
    feature_returns = same_contract_selected_returns(
        normalized, path, price_col="settle"
    ).reset_index(drop=True)
    missing_positions = np.flatnonzero(feature_returns.isna().to_numpy())
    missing_positions = missing_positions[missing_positions != 0]
    if len(missing_positions):
        missing_dates = path.iloc[missing_positions]["trade_date"]
        raise ValueError(
            "Canonical roll-safe features require selected-contract prior-session history; "
            f"missing at {list(pd.to_datetime(missing_dates, utc=True))}"
        )
    feature_steps = feature_returns.copy()
    if pd.isna(feature_steps.iloc[0]):
        feature_steps.iloc[0] = 0.0
    synthetic_close = np.exp(feature_steps.cumsum())
    settle = path["settle"].astype(float)
    synthetic_market = pd.DataFrame(
        {
            "close": synthetic_close.to_numpy(),
            "high": (synthetic_close * path["high"].astype(float) / settle).to_numpy(),
            "low": (synthetic_close * path["low"].astype(float) / settle).to_numpy(),
            "volume": path["volume"].astype(float).to_numpy(),
        },
        index=prediction_time,
    )
    synthetic_market = _validate_market_frame(synthetic_market)
    features = build_market_features(synthetic_market)
    target = pd.Series(
        target_returns.shift(-1).to_numpy(),
        index=prediction_time,
        name=TARGET_COLUMN,
    )
    dataset = features.join(target)

    cutoffs = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(path["trade_date"], utc=True),
            "prediction_time": prediction_time,
        }
    )
    curve, curve_audit = build_market_structure_features(
        normalized, schema, cutoffs, max_contracts=4
    )
    required_curve = [
        *(f"curve_settle_m{rank}" for rank in range(1, 5)),
        *(f"curve_dte_m{rank}" for rank in range(1, 5)),
        "curve_volume_m1",
        "curve_volume_m2",
        "curve_volume_ratio_m1_m2",
        "curve_spread_m1_m2",
        "curve_spread_m2_m3",
        "curve_spread_m3_m4",
        "curve_slope_m1_m4",
    ]
    curve_complete = curve.dropna(subset=required_curve)
    if curve_complete.empty:
        raise ValueError("Canonical dataset requires complete M1-M4 market structure")
    dataset = dataset.join(curve_complete, how="inner").dropna(subset=[TARGET_COLUMN])
    dataset = dataset.dropna(subset=list(features.columns))

    representation = {
        "status": schema["continuous_contract"]["status"],
        "adjustment_method": schema["continuous_contract"]["adjustment_method"],
        "authoritative_storage": schema["continuous_contract"]["authoritative_storage"],
        "exchange": source["exchange"],
        "product_code": source["product_code"],
        "session_timezone": source["session_timezone"],
        "calendar": source["calendar"],
    }
    evidence_scope = "canonical_promotion" if promotion_required else "evaluation_only"
    market_semantics = {
        "availability_policy": source.get("availability_policy", {}),
        "representation": representation,
        "evidence_scope": evidence_scope,
    }
    lineage = {
        "market_source_id": selected_source_id,
        "market_provider": str(source["provider"]),
        "market_source_status": str(source.get("status", "")),
        "configured_canonical_source": bool(source.get("canonical_market_source")),
        "contract_input_sha256": _table_sha256(normalized),
        "selected_path_sha256": _table_sha256(path),
        "roll_ledger_sha256": _table_sha256(ledger),
        "curve_features_sha256": _table_sha256(curve),
        "curve_audit_sha256": _table_sha256(curve_audit),
        "roll_policy_sha256": _json_sha256(policy),
        "roll_policy_method": str(policy["method"]),
        "roll_count": len(ledger),
        "curve_contracts": 4,
        "availability_status": str(normalized["availability_status"].iloc[0]),
        "availability_policy": source.get("availability_policy", {}),
        "evidence_scope": evidence_scope,
        "representation": representation,
        "market_semantics_sha256": _json_sha256(market_semantics),
        "synthetic_series": "return_neutral_within_contract_index",
        "synthetic_series_tradable": False,
        "feature_return_semantics": "selected_contract_own_prior_session",
        "feature_returns_sha256": _table_sha256(feature_returns.to_frame()),
        "target_return_semantics": "consecutive_selected_rows_same_contract_only",
        "cross_contract_returns_allowed": False,
    }
    return dataset, lineage


def _join_source(
    dataset: pd.DataFrame, source: PitFeatureSource
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if source.evidence_mode not in _PIT_MODES:
        raise ValueError(f"{source.evidence_mode} evidence is not eligible for a PIT dataset")
    if not source.value_columns:
        raise ValueError(f"PIT source {source.name!r} has no value columns")
    validated = validate_availability(source.frame, source.evidence_mode)
    if source.group_columns:
        raise ValueError(
            f"PIT source {source.name!r} declares group identity {list(source.group_columns)}; "
            "build_pit_dataset currently requires grouped sources to be aggregated or pivoted "
            "to one row per available_at before joining"
        )
    input_rows = len(dataset)
    cutoffs = pd.DataFrame({"prediction_time": dataset.index})
    joined = asof_join_point_in_time(
        cutoffs,
        validated,
        list(source.value_columns),
        mode=source.evidence_mode,
        source_group_columns=list(source.group_columns),
    )
    out = dataset.copy()
    for column in source.value_columns:
        if column in out.columns:
            raise ValueError(f"Duplicate feature column from {source.name!r}: {column}")
        out[column] = joined[column].to_numpy()
    out = out.dropna(subset=list(source.value_columns))
    joined_rows = len(out)
    available_at = pd.to_datetime(validated["available_at"], utc=True)
    availability_bases = sorted(
        validated.get("availability_basis", pd.Series(dtype=str))
        .dropna()
        .astype(str)
        .unique()
    )
    lineage = {
        "name": source.name,
        "family": source.family,
        "source_id": source.source_id or source.name,
        "source_vintage": source.source_vintage,
        "evidence_mode": source.evidence_mode,
        "source_sha256": exogenous_frame_sha256(source.frame),
        "source_rows": len(source.frame),
        "input_rows": input_rows,
        "joined_rows": joined_rows,
        "unmatched_rows": input_rows - joined_rows,
        "join_coverage_ratio": joined_rows / input_rows,
        "value_columns": list(source.value_columns),
        "group_columns": list(source.group_columns),
        "available_start": available_at.min().isoformat(),
        "available_end": available_at.max().isoformat(),
        "availability_statuses": sorted(
            validated["availability_status"].astype(str).unique()
        ),
        "availability_bases": availability_bases,
        "revision_statuses": sorted(validated["revision_status"].astype(str).unique()),
    }
    return out, lineage


def build_pit_dataset(
    ohlcv: pd.DataFrame | None,
    exogenous: list[PitFeatureSource] | tuple[PitFeatureSource, ...] = (),
    *,
    evidence_mode: str = "research_pit",
    required_families: tuple[str, ...] | None = None,
    require_full_v1: bool = False,
    canonical_contracts: pd.DataFrame | None = None,
    market_source_id: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if evidence_mode not in _PIT_MODES:
        raise ValueError(f"Unsupported PIT dataset mode: {evidence_mode!r}")
    families = {"market", "calendar_seasonality"}
    market_structure_lineage: dict[str, Any] | None = None
    contract_market_mode = evidence_mode in {"evaluation_pit", "canonical"}
    if contract_market_mode:
        if canonical_contracts is None:
            raise ValueError(
                f"{evidence_mode} dataset requires provider-neutral canonical contract rows"
            )
        if not market_source_id:
            raise ValueError(f"{evidence_mode} contract rows require explicit market_source_id")
        dataset, market_structure_lineage = _canonical_supervised_dataset(
            canonical_contracts,
            promotion_required=evidence_mode == "canonical",
            market_source_id=market_source_id,
        )
        market_input = "canonical_contracts"
        market_source_sha256 = str(market_structure_lineage["contract_input_sha256"])
        families.add("market_structure")
    else:
        if ohlcv is None:
            raise ValueError("Research PIT dataset requires a market frame")
        if canonical_contracts is not None:
            raise ValueError(
                "Canonical contract rows require evidence_mode='canonical' or 'evaluation_pit'"
            )
        if market_source_id is not None:
            raise ValueError("market_source_id is only valid for contract-market datasets")
        market = _validate_market_frame(ohlcv)
        market_input = "market_frame"
        market_source_sha256 = dataframe_sha256(market)
        x, y = make_supervised(market)
        dataset = x.join(y.rename(TARGET_COLUMN))

    if dataset.empty:
        raise ValueError("PIT dataset has no market rows before exogenous joins")
    required = tuple(required_families or _required_families())
    base_start = dataset.index[0]
    base_end = dataset.index[-1]
    exogenous_lineage: list[dict[str, Any]] = []
    family_audits: dict[str, list[Any]] = {}
    for source in exogenous:
        if evidence_mode == "canonical" and source.evidence_mode != "canonical":
            raise ValueError("Canonical dataset requires canonical exogenous evidence")
        dataset, source_lineage = _join_source(dataset, source)
        exogenous_lineage.append(source_lineage)
        families.add(source.family)
        if source.family in REQUIRED_EXOGENOUS_FAMILIES:
            audit = audit_configured_exogenous_family(
                family=source.family,
                evidence_source_id=source.source_id or source.name,
                frame=source.frame,
                required_start=base_start,
                required_end=base_end,
                evidence_mode=source.evidence_mode,
            )
            family_audits.setdefault(source.family, []).append(audit)

    missing = sorted(set(required) - families)
    if require_full_v1 and missing:
        raise ValueError(f"Missing required V1 feature families: {missing}")
    if require_full_v1:
        required_exogenous = set(required) & set(REQUIRED_EXOGENOUS_FAMILIES)
        missing_audits = sorted(required_exogenous - set(family_audits))
        if missing_audits:
            raise ValueError(
                f"Missing full-V1 exogenous audits for families: {missing_audits}"
            )
        not_ready = {
            family: tuple(
                dict.fromkeys(
                    blocker
                    for audit in family_audits[family]
                    if not audit.full_v1_ready
                    for blocker in audit.blockers
                )
            )
            for family in sorted(required_exogenous)
            if any(not audit.full_v1_ready for audit in family_audits[family])
        }
        if not_ready:
            details = "; ".join(
                f"{family}: {','.join(blockers)}"
                for family, blockers in not_ready.items()
            )
            raise ValueError(f"Full V1 exogenous evidence is not ready: {details}")
    if dataset.empty:
        raise ValueError("PIT dataset is empty after availability-safe joins")
    dataset_cfg = research_dataset_config()["dataset"]
    minimum_join_coverage = float(dataset_cfg.get("minimum_exogenous_join_coverage", 0.0))
    if require_full_v1:
        below_threshold = {
            str(item["family"]): float(item["join_coverage_ratio"])
            for item in exogenous_lineage
            if float(item["join_coverage_ratio"]) < minimum_join_coverage
        }
        if below_threshold:
            raise ValueError(
                "Full V1 exogenous join coverage is below the configured minimum: "
                f"{below_threshold}"
            )

    digest = dataframe_sha256(dataset)
    completeness = "full_v1" if require_full_v1 and not missing else "pit_core"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": f"us-ng-pit-{digest[:12]}",
        "dataset_sha256": digest,
        "evidence_mode": evidence_mode,
        "market_input": market_input,
        "market_evaluation_evidence": contract_market_mode,
        "canonical_market_evidence": evidence_mode == "canonical",
        "research_evaluation_eligible": completeness == "full_v1",
        "research_promotion_eligible": completeness == "full_v1" and evidence_mode == "canonical",
        "completeness": completeness,
        "required_feature_families": list(required),
        "included_feature_families": sorted(families),
        "missing_feature_families": missing,
        "rows": len(dataset),
        "initial_train_rows": int(research_dataset_config()["walk_forward"]["initial_train_rows"]),
        "minimum_exogenous_join_coverage": minimum_join_coverage,
        "columns": list(dataset.columns),
        "start": dataset.index[0].isoformat(),
        "end": dataset.index[-1].isoformat(),
        "target": TARGET_COLUMN,
        "prediction_timestamp_semantics": "explicit_or_conservatively_derived_market_available_at_cutoff",
        "material_exclusions": [
            f"{family}: not included as PIT-admissible evidence" for family in missing
        ],
        "exogenous_sources": exogenous_lineage,
        "exogenous_family_audits": {
            family: [item.to_dict() for item in audit] for family, audit in sorted(family_audits.items())
        },
    }
    if market_structure_lineage is not None:
        manifest["market_source_id"] = market_structure_lineage["market_source_id"]
        manifest["market_provider"] = market_structure_lineage["market_provider"]
        manifest["market_source_status"] = market_structure_lineage["market_source_status"]
        manifest["market_structure"] = market_structure_lineage
    source_input_id = (
        f"market:{market_structure_lineage['market_source_id']}"
        if market_structure_lineage is not None
        else market_input
    )
    source_inputs = [{"id": source_input_id, "sha256": market_source_sha256}]
    source_inputs.extend(
        {
            "id": str(item["source_id"]),
            "vintage": item.get("source_vintage"),
            "sha256": str(item["source_sha256"]),
        }
        for item in exogenous_lineage
    )
    transformation_sha256 = file_identity(
        REPO_ROOT / "src" / "commodity" / name
        for name in (
            "research_dataset.py", "availability.py", "features.py", "market_data.py",
            "rolls.py", "roll_policy.py", "roll_safe_market.py", "exogenous_audit.py",
            "data_assurance.py",
        )
    )
    layers = [
        {"name": "retained_source_evidence", "status": "constructed", "sha256": canonical_json_sha256(source_inputs)},
        {"name": "canonical_normalization", "status": "constructed", "sha256": market_source_sha256},
        {"name": "pit_availability", "status": "constructed", "sha256": canonical_json_sha256({"prediction_times": [value.isoformat() for value in dataset.index], "sources": exogenous_lineage})},
        {"name": "feature_construction", "status": "constructed", "sha256": digest},
    ]
    manifest["data_assurance"] = build_construction_contract(
        source_inputs=source_inputs,
        layers=layers,
        transformation_sha256=transformation_sha256,
    )
    return dataset, manifest
