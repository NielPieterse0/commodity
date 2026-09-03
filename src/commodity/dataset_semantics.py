from __future__ import annotations

from typing import Any

import pandas as pd

from commodity.config import research_dataset_config
from commodity.evidence_authority import evaluation_authority_is_valid


def verify_full_v1_semantics(frame: pd.DataFrame, manifest: dict[str, Any]) -> dict[str, bool]:
    """Independently derive the semantic checks required for the retained full-V1 evaluation dataset."""
    required = set(research_dataset_config()["dataset"]["required_feature_families"])
    market = manifest.get("market_structure") or {}
    representation = market.get("representation") or {}
    family_audits = manifest.get("exogenous_family_audits") or {}
    return {
        "frame_non_empty": not frame.empty,
        "prediction_index_datetime": isinstance(frame.index, pd.DatetimeIndex),
        "prediction_index_ordered_unique": frame.index.is_monotonic_increasing and frame.index.is_unique,
        "target_column_present": "target_ret_1" in frame.columns,
        "full_v1_contract": manifest.get("completeness") == "full_v1",
        "required_feature_families": (
            set(manifest.get("required_feature_families", [])) == required
            and required.issubset(set(manifest.get("included_feature_families", [])))
            and not manifest.get("missing_feature_families")
        ),
        "evaluation_authority": evaluation_authority_is_valid(manifest),
        "market_source_identity": manifest.get("market_source_id") == "massive_henry_hub_evaluation",
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
