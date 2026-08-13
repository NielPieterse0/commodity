from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from commodity.availability import asof_join_point_in_time
from commodity.config import experiment_config
from commodity.features import make_supervised

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
    ohlcv: pd.DataFrame,
    exogenous: list[PitFeatureSource] | tuple[PitFeatureSource, ...] = (),
    *,
    evidence_mode: str = "research_pit",
    required_families: tuple[str, ...] | None = None,
    require_full_v1: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if evidence_mode not in _PIT_MODES:
        raise ValueError(f"Unsupported PIT dataset mode: {evidence_mode!r}")
    market = _validate_market_frame(ohlcv)
    x, y = make_supervised(market)
    dataset = x.join(y.rename(TARGET_COLUMN))
    families = {"market", "calendar_seasonality"}

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
        "canonical_market_evidence": False,
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
    return dataset, manifest
