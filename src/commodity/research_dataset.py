from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from commodity.availability import asof_join_point_in_time
from commodity.config import assumptions_config, data_config, experiment_config
from commodity.features import build_market_features, make_supervised
from commodity.market_data import (
    assert_canonical_market_ready,
    build_market_structure_features,
    ensure_canonical_market_availability,
    validate_contract_history,
)
from commodity.rolls import build_derived_continuous_series

TARGET_COLUMN = "target_ret_1"
_PIT_MODES = {"research_pit", "canonical"}


@dataclass(frozen=True)
class PitFeatureSource:
    name: str
    family: str
    frame: pd.DataFrame
    value_columns: tuple[str, ...]
    evidence_mode: str = "research_pit"


def _required_families() -> tuple[str, ...]:
    dataset_cfg = experiment_config()["dataset"]
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
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.sort_index()
    if frame.index.has_duplicates:
        raise ValueError("Market frame must have a unique chronological index")
    return frame


def _table_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=True, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_supervised_dataset(
    contracts: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = data_config()
    assumptions = assumptions_config()
    assert_canonical_market_ready(cfg, assumptions)
    schema = cfg["canonical_contract_schema"]
    source = cfg["sources"]["market_canonical"]
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
    within_contract_returns = path["settle_log_return"].astype(float)
    synthetic_close = np.exp(within_contract_returns.fillna(0.0).cumsum())
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
        within_contract_returns.shift(-1).to_numpy(),
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
    market_semantics = {
        "availability_policy": source.get("availability_policy", {}),
        "representation": representation,
    }
    lineage = {
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
        "representation": representation,
        "market_semantics_sha256": _json_sha256(market_semantics),
        "synthetic_series": "return_neutral_within_contract_index",
        "synthetic_series_tradable": False,
        "cross_contract_returns_allowed": False,
    }
    return dataset, lineage


def _join_source(dataset: pd.DataFrame, source: PitFeatureSource) -> pd.DataFrame:
    if source.evidence_mode not in _PIT_MODES:
        raise ValueError(f"{source.evidence_mode} evidence is not eligible for a PIT dataset")
    if not source.value_columns:
        raise ValueError(f"PIT source {source.name!r} has no value columns")
    cutoffs = pd.DataFrame({"prediction_time": dataset.index})
    joined = asof_join_point_in_time(
        cutoffs,
        source.frame,
        list(source.value_columns),
        mode=source.evidence_mode,
    )
    out = dataset.copy()
    for column in source.value_columns:
        if column in out.columns:
            raise ValueError(f"Duplicate feature column from {source.name!r}: {column}")
        out[column] = joined[column].to_numpy()
    return out.dropna(subset=list(source.value_columns))


def build_pit_dataset(
    ohlcv: pd.DataFrame | None,
    exogenous: list[PitFeatureSource] | tuple[PitFeatureSource, ...] = (),
    *,
    evidence_mode: str = "research_pit",
    required_families: tuple[str, ...] | None = None,
    require_full_v1: bool = False,
    canonical_contracts: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if evidence_mode not in _PIT_MODES:
        raise ValueError(f"Unsupported PIT dataset mode: {evidence_mode!r}")
    families = {"market", "calendar_seasonality"}
    market_structure_lineage: dict[str, Any] | None = None
    if evidence_mode == "canonical":
        if canonical_contracts is None:
            raise ValueError("Canonical dataset requires provider-neutral canonical contract rows")
        dataset, market_structure_lineage = _canonical_supervised_dataset(canonical_contracts)
        market_input = "canonical_contracts"
        families.add("market_structure")
    else:
        if ohlcv is None:
            raise ValueError("Research PIT dataset requires a market frame")
        if canonical_contracts is not None:
            raise ValueError("Canonical contract rows require evidence_mode='canonical'")
        market = _validate_market_frame(ohlcv)
        market_input = "market_frame"
        x, y = make_supervised(market)
        dataset = x.join(y.rename(TARGET_COLUMN))

    for source in exogenous:
        if evidence_mode == "canonical" and source.evidence_mode != "canonical":
            raise ValueError("Canonical dataset requires canonical exogenous evidence")
        dataset = _join_source(dataset, source)
        families.add(source.family)

    required = tuple(required_families or _required_families())
    missing = sorted(set(required) - families)
    if require_full_v1 and missing:
        raise ValueError(f"Missing required V1 feature families: {missing}")
    if dataset.empty:
        raise ValueError("PIT dataset is empty after availability-safe joins")

    digest = dataframe_sha256(dataset)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": f"us-ng-pit-{digest[:12]}",
        "dataset_sha256": digest,
        "evidence_mode": evidence_mode,
        "market_input": market_input,
        "canonical_market_evidence": evidence_mode == "canonical",
        "completeness": "full_v1" if not missing else "pit_core",
        "required_feature_families": list(required),
        "included_feature_families": sorted(families),
        "missing_feature_families": missing,
        "rows": len(dataset),
        "columns": list(dataset.columns),
        "start": dataset.index[0].isoformat(),
        "end": dataset.index[-1].isoformat(),
        "target": TARGET_COLUMN,
        "prediction_timestamp_semantics": "after_current_daily_bar_close",
        "material_exclusions": [
            f"{family}: not included as PIT-admissible evidence" for family in missing
        ],
    }
    if market_structure_lineage is not None:
        manifest["market_structure"] = market_structure_lineage
    return dataset, manifest
