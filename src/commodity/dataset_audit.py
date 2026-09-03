from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from commodity.config import research_dataset_config
from commodity.data_assurance import DataAssuranceError, assert_research_ready
from commodity.evidence_authority import (
    PIT_EVIDENCE_MODES,
    evaluation_authority_is_valid,
)
from commodity.research_dataset import dataframe_sha256

_REQUIRED_EXOGENOUS = {"storage", "weather", "power", "positioning"}
_MARKET_STRUCTURE_HASHES = {
    "contract_input_sha256",
    "selected_path_sha256",
    "roll_ledger_sha256",
    "curve_features_sha256",
    "curve_audit_sha256",
    "roll_policy_sha256",
}


@dataclass(frozen=True)
class DatasetAudit:
    verdict: str
    blockers: tuple[str, ...]
    caveats: tuple[str, ...]
    rows: int
    oos_rows: int
    duplicate_prediction_times: int
    missing_cells: int
    non_finite_numeric_cells: int
    minimum_join_coverage: float | None
    distribution_shift_max_z: float | None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["blockers"] = list(self.blockers)
        value["caveats"] = list(self.caveats)
        return value


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def _source_lineage(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    lineage = manifest.get("source_lineage", {})
    if isinstance(lineage, dict) and "exogenous_sources" in lineage:
        return list(lineage.get("exogenous_sources", []))
    return list(manifest.get("exogenous_sources", []))


def _distribution_shift(frame: pd.DataFrame) -> float | None:
    numeric = frame.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)
    if numeric.empty or len(numeric) < 4:
        return None
    midpoint = len(numeric) // 2
    first = numeric.iloc[:midpoint]
    second = numeric.iloc[midpoint:]
    pooled = numeric.std(ddof=0).replace(0.0, np.nan)
    shift = ((second.mean() - first.mean()).abs() / pooled).replace([np.inf], np.nan)
    if shift.dropna().empty:
        return 0.0
    return float(shift.max(skipna=True))


def audit_full_v1_dataset(
    frame: pd.DataFrame,
    manifest: dict[str, Any],
) -> DatasetAudit:
    blockers: list[str] = []
    caveats: list[str] = []
    required = set(research_dataset_config()["dataset"]["required_feature_families"])
    declared_required = set(manifest.get("required_feature_families", []))
    included = set(manifest.get("included_feature_families", []))
    if manifest.get("completeness") != "full_v1":
        blockers.append("not_full_v1")
    if declared_required != required:
        blockers.append("required_feature_contract_mismatch")
    if not required.issubset(included) or manifest.get("missing_feature_families"):
        blockers.append("required_feature_families_incomplete")
    evidence_mode = manifest.get("evidence_mode")
    if evidence_mode not in PIT_EVIDENCE_MODES:
        blockers.append("non_pit_evidence_mode")
    elif evidence_mode == "evaluation_pit":
        caveats.append("evaluation_only_market_evidence")
        if not evaluation_authority_is_valid(manifest):
            blockers.append("evaluation_mode_claims_promotable_evidence")
    try:
        assert_research_ready(manifest.get("data_assurance"))
    except DataAssuranceError:
        blockers.append("data_assurance_unverified")

    lineage = manifest.get("source_lineage", {})
    family_audits = manifest.get("exogenous_family_audits", {})
    market_structure = manifest.get("market_structure")
    if isinstance(lineage, dict):
        family_audits = lineage.get("exogenous_family_audits", family_audits)
        market_structure = lineage.get("market_structure", market_structure)
    audits_ready = all(
        family in family_audits
        and bool(family_audits[family])
        and all(item.get("full_v1_ready") is True for item in family_audits[family])
        for family in _REQUIRED_EXOGENOUS
    )
    if not audits_ready:
        blockers.append("required_family_audits_incomplete")
    if "market_structure" in required:
        valid_market_structure = isinstance(market_structure, dict) and all(
            _is_sha256(market_structure.get(key)) for key in _MARKET_STRUCTURE_HASHES
        )
        if not valid_market_structure:
            blockers.append("market_structure_lineage_incomplete")

    actual_hash = dataframe_sha256(frame)
    if manifest.get("dataset_sha256") != actual_hash:
        blockers.append("dataset_identity_mismatch")
    artifact_hash = manifest.get("dataset_artifact_sha256")
    if artifact_hash is not None and artifact_hash != actual_hash:
        blockers.append("dataset_artifact_hash_mismatch")

    index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True))
    duplicate_count = int(index.duplicated().sum())
    if duplicate_count:
        blockers.append("duplicate_prediction_time")
    if not index.is_monotonic_increasing:
        blockers.append("prediction_time_not_monotonic")
    if int(manifest.get("rows", -1)) != len(frame):
        blockers.append("row_count_mismatch")
    if frame.columns.duplicated().any():
        blockers.append("duplicate_columns")
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
        blockers.append("non_numeric_columns")
    target = str(manifest.get("target", ""))
    if not target or target not in frame.columns:
        blockers.append("target_missing")
    else:
        target_values = frame.loc[:, target]
        target_dtypes = (
            list(target_values.dtypes)
            if isinstance(target_values, pd.DataFrame)
            else [target_values.dtype]
        )
        if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in target_dtypes):
            blockers.append("target_not_numeric")

    missing_cells = int(frame.isna().sum().sum())
    if missing_cells:
        blockers.append("missing_values")
    numeric = frame.select_dtypes(include=[np.number])
    non_finite = int((~np.isfinite(numeric.to_numpy(dtype=float))).sum()) if not numeric.empty else 0
    if non_finite:
        blockers.append("non_finite_numeric_values")

    configured_initial_train = int(
        research_dataset_config()["walk_forward"]["initial_train_rows"]
    )
    try:
        manifest_initial_train = int(manifest["initial_train_rows"])
    except (KeyError, TypeError, ValueError):
        manifest_initial_train = -1
    if manifest_initial_train != configured_initial_train:
        blockers.append("split_contract_mismatch")
    initial_train_rows = configured_initial_train
    oos_rows = max(0, len(frame) - initial_train_rows)
    if oos_rows < 1:
        blockers.append("insufficient_oos_rows")

    sources = _source_lineage(manifest)
    source_families = {str(item.get("family")) for item in sources}
    if not _REQUIRED_EXOGENOUS.issubset(source_families):
        blockers.append("required_source_lineage_missing")
    join_coverages: list[float] = []
    for source in sources:
        complete = all(
            source.get(key)
            for key in (
                "source_id",
                "source_vintage",
                "source_sha256",
                "availability_statuses",
                "availability_bases",
                "revision_statuses",
            )
        )
        if not complete or not _is_sha256(source.get("source_sha256")):
            blockers.append("incomplete_source_lineage")
        try:
            coverage = float(source.get("join_coverage_ratio"))
        except (TypeError, ValueError):
            blockers.append("invalid_join_coverage")
            continue
        join_coverages.append(coverage)
        if not 0.0 < coverage <= 1.0:
            blockers.append("invalid_join_coverage")
        elif coverage < 1.0:
            caveats.append("partial_source_join_coverage")
        unmatched = int(source.get("unmatched_rows", 0) or 0)
        if coverage == 1.0 and unmatched != 0:
            blockers.append("inconsistent_join_diagnostics")

    minimum_join_coverage = min(join_coverages) if join_coverages else None
    required_join_coverage = float(
        research_dataset_config()["dataset"].get("minimum_exogenous_join_coverage", 0.0)
    )
    if minimum_join_coverage is None or minimum_join_coverage < required_join_coverage:
        blockers.append("minimum_join_coverage_not_met")
    distribution_shift = _distribution_shift(frame)
    if distribution_shift is not None and distribution_shift > 3.0:
        caveats.append("material_distribution_shift")

    blockers_tuple = tuple(dict.fromkeys(blockers))
    caveats_tuple = tuple(dict.fromkeys(caveats))
    if blockers_tuple:
        verdict = "not-fit"
    elif caveats_tuple:
        verdict = "fit-with-caveats"
    else:
        verdict = "fit"
    return DatasetAudit(
        verdict,
        blockers_tuple,
        caveats_tuple,
        len(frame),
        oos_rows,
        duplicate_count,
        missing_cells,
        non_finite,
        minimum_join_coverage,
        distribution_shift,
    )
