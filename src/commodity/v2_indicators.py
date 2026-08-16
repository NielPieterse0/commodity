from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from commodity.v2_indicator_contract import (
    ALL_INCREMENT_FEATURES,
    ATTRIBUTION_VARIANTS,
    CANDIDATE_ID as CANDIDATE_ID,
    EmpiricalReleaseBlocked as EmpiricalReleaseBlocked,
    FEATURES_BY_FAMILY,
    FAMILIES,
    IndicatorContractError,
    PRIMARY_VARIANT,
    PinnedSourcePolicy as PinnedSourcePolicy,
    SOURCE_POLICY_SHA256 as SOURCE_POLICY_SHA256,
    SPEC_PATH as SPEC_PATH,
    SPEC_REVISION as SPEC_REVISION,
    _json_copy,
    bind_activation_contract as bind_activation_contract,
    build_lineage_handoff as build_lineage_handoff,
    canonical_sha256 as canonical_sha256,
    dataframe_sha256 as dataframe_sha256,
    parse_pinned_source_policy as parse_pinned_source_policy,
    require_empirical_release as require_empirical_release,
)
from commodity.v2_indicator_market import (
    build_curve_increments as build_curve_increments,
    build_positioning_increments as build_positioning_increments,
    build_power_increments as build_power_increments,
    build_volatility_increment as build_volatility_increment,
)
from commodity.v2_indicator_weather_storage import (
    build_storage_increment as build_storage_increment,
    build_storage_public_value_events as build_storage_public_value_events,
    build_weather_revision as build_weather_revision,
)


def validate_preprocessing_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _json_copy(plan)
    if normalized.get("fit_scope") != "fold_train_only":
        raise IndicatorContractError(
            "fitted transforms must use fold_train_only scope"
        )
    prohibited = (
        "imputation",
        "clipping",
        "winsorization",
        "target_encoding",
        "learned_feature_selection",
    )
    active = [
        key
        for key in prohibited
        if normalized.get(key) not in (None, False, "none")
    ]
    if active:
        raise IndicatorContractError(
            f"#83 preprocessing uses prohibited transforms: {active}"
        )
    return normalized


def require_i_all_valid(family_status: Mapping[str, bool]) -> None:
    if set(family_status) != set(FAMILIES):
        raise IndicatorContractError("family status must cover exactly W/S/C/V/P/L")
    failed = [family for family in FAMILIES if family_status[family] is not True]
    if failed:
        raise IndicatorContractError(
            f"I-ALL is invalid before fitting because required families failed: {failed}"
        )


def variant_role(variant: str) -> str:
    if variant == PRIMARY_VARIANT:
        return "primary"
    if variant in ATTRIBUTION_VARIANTS:
        return "attribution_only"
    raise IndicatorContractError(f"unlisted #83 variant: {variant!r}")


def build_variant_matrix(
    inherited_control: pd.DataFrame,
    increments: pd.DataFrame,
    *,
    variant: str,
    family_status: Mapping[str, bool],
) -> pd.DataFrame:
    role = variant_role(variant)
    require_i_all_valid(family_status)
    if tuple(increments.columns) != ALL_INCREMENT_FEATURES:
        missing = [
            name for name in ALL_INCREMENT_FEATURES if name not in increments.columns
        ]
        extras = [
            name for name in increments.columns if name not in ALL_INCREMENT_FEATURES
        ]
        raise IndicatorContractError(
            "#83 increment columns must match the frozen list; "
            f"missing={missing}, extras={extras}"
        )
    if not inherited_control.index.equals(increments.index):
        raise IndicatorContractError(
            "inherited controls and #83 increments must share row identity"
        )
    overlap = sorted(set(inherited_control.columns) & set(ALL_INCREMENT_FEATURES))
    if overlap:
        raise IndicatorContractError(
            f"inherited controls must not shadow #83 increment columns: {overlap}"
        )
    excluded_family = ATTRIBUTION_VARIANTS.get(variant)
    selected = [
        name
        for family in FAMILIES
        if family != excluded_family
        for name in FEATURES_BY_FAMILY[family]
    ]
    result = inherited_control.join(increments.loc[:, selected])
    result.attrs["variant"] = variant
    result.attrs["variant_role"] = role
    result.attrs["can_promote"] = role == "primary"
    return result


def validate_required_coverage(
    increments: pd.DataFrame,
    *,
    fit_rows: Sequence[bool],
    scored_rows: Sequence[bool],
) -> dict[str, float]:
    if tuple(increments.columns) != ALL_INCREMENT_FEATURES:
        raise IndicatorContractError(
            "coverage validation requires the exact frozen increment set"
        )
    fit_values = list(fit_rows)
    scored_values = list(scored_rows)
    if len(fit_values) != len(increments) or len(scored_values) != len(increments):
        raise IndicatorContractError("coverage masks must align with increment rows")
    fit_mask = pd.Series(fit_values, index=increments.index, dtype=bool)
    scored_mask = pd.Series(scored_values, index=increments.index, dtype=bool)
    if not fit_mask.any() or not scored_mask.any():
        raise IndicatorContractError(
            "coverage validation requires both fit and scored rows"
        )
    selected = increments.loc[fit_mask | scored_mask]
    numeric = selected.apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(numeric.to_numpy())
    if numeric.isna().any().any() or not finite.all():
        raise IndicatorContractError(
            "required #83 features must have 1.000 finite coverage on all "
            "fit/scored rows"
        )
    return {
        "fit_rows_for_required_features": 1.0,
        "primary_scored_rows": 1.0,
    }


__all__ = [
    "ALL_INCREMENT_FEATURES",
    "ATTRIBUTION_VARIANTS",
    "CANDIDATE_ID",
    "EmpiricalReleaseBlocked",
    "FEATURES_BY_FAMILY",
    "FAMILIES",
    "IndicatorContractError",
    "PRIMARY_VARIANT",
    "PinnedSourcePolicy",
    "SOURCE_POLICY_SHA256",
    "SPEC_PATH",
    "SPEC_REVISION",
    "bind_activation_contract",
    "build_curve_increments",
    "build_lineage_handoff",
    "build_positioning_increments",
    "build_power_increments",
    "build_storage_increment",
    "build_storage_public_value_events",
    "build_variant_matrix",
    "build_volatility_increment",
    "build_weather_revision",
    "canonical_sha256",
    "dataframe_sha256",
    "parse_pinned_source_policy",
    "require_empirical_release",
    "require_i_all_valid",
    "validate_preprocessing_plan",
    "validate_required_coverage",
    "variant_role",
]
