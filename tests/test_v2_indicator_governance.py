from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from commodity.v2_indicator_contract import (
    CANDIDATE_ID,
    IMPLEMENTATION_SOURCE_PATHS,
    EmpiricalReleaseBlocked,
    IndicatorContractError,
    bind_activation_contract,
    build_implementation_source_manifest,
    build_lineage_handoff,
    canonical_sha256,
    require_empirical_release,
)
from commodity.v2_indicators import build_power_increments, build_weather_revision

ROOT = Path(__file__).resolve().parents[1]
BOUND_IMPLEMENTATION = "1" * 40
RUNTIME_REVISION = "2" * 40


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def _manifest() -> dict:
    return build_implementation_source_manifest(ROOT)


def _binding() -> dict:
    candidates = _load("config/experiment_candidates.json")
    manifest = _manifest()
    candidates["candidates"][CANDIDATE_ID]["implementation_revision"] = {
        "pr": 99,
        "head": BOUND_IMPLEMENTATION,
        "path": "src/commodity/v2_indicator_contract.py",
        "source_manifest_sha256": manifest["manifest_sha256"],
        "source_manifest_paths": list(IMPLEMENTATION_SOURCE_PATHS),
    }
    return bind_activation_contract(
        _load("docs/development/v2-activation-preregistration/activation-contract.json"),
        candidates,
    )


def _released(binding: dict, *, candidate_released: bool) -> dict:
    released = json.loads(json.dumps(binding))
    released["activation_execution_authorized"] = True
    gate = released["empirical_release_gate"]
    gate["88"]["satisfied"] = True
    gate["88"]["current_state"] = gate["88"]["required_state"]
    gate["release_state"]["83"] = candidate_released
    released.pop("binding_sha256")
    released["binding_sha256"] = canonical_sha256(released)
    return released


def test_release_requires_candidate_specific_83_state() -> None:
    binding = _binding()
    with pytest.raises(EmpiricalReleaseBlocked):
        require_empirical_release(_released(binding, candidate_released=False))
    require_empirical_release(_released(binding, candidate_released=True))


def test_source_manifest_is_exact_and_runtime_revision_is_separate() -> None:
    binding = _binding()
    manifest = _manifest()
    assert tuple(manifest["files"]) == IMPLEMENTATION_SOURCE_PATHS
    handoff = build_lineage_handoff(
        binding=binding,
        input_frame=pd.DataFrame({"x": [1.0]}),
        feature_frame=pd.DataFrame({"y": [2.0]}),
        implementation_config={"fit_scope": "fold_train_only"},
        implementation_revision=RUNTIME_REVISION,
        runtime_source_manifest=manifest,
    )
    assert handoff["bound_implementation_revision"] == BOUND_IMPLEMENTATION
    assert handoff["runtime_code_revision"] == RUNTIME_REVISION
    assert handoff["implementation_source_manifest_sha256"] == manifest["manifest_sha256"]

    mutated = json.loads(json.dumps(manifest))
    first = IMPLEMENTATION_SOURCE_PATHS[0]
    mutated["files"][first] = "f" * 64
    body = {key: value for key, value in mutated.items() if key != "manifest_sha256"}
    mutated["manifest_sha256"] = canonical_sha256(body)
    with pytest.raises(IndicatorContractError, match="sources differ"):
        build_lineage_handoff(
            binding=binding,
            input_frame=pd.DataFrame({"x": [1.0]}),
            feature_frame=pd.DataFrame({"y": [2.0]}),
            implementation_config={"fit_scope": "fold_train_only"},
            implementation_revision=RUNTIME_REVISION,
            runtime_source_manifest=mutated,
        )


def _source_policy() -> object:
    from commodity.v2_indicator_contract import parse_pinned_source_policy

    return parse_pinned_source_policy((ROOT / "config" / "data_sources.json").read_bytes())


def _weather_rows() -> tuple[pd.DataFrame, pd.Timestamp]:
    policy = _source_policy()
    cfg = policy.payload["sources"]["weather"]
    anchors = [str(item["id"]) for item in cfg["v1_anchors"]]
    lead_start, lead_end = [int(value) for value in cfg["v1_feature_lead_hours"]]
    base = float(cfg["v1_degree_day_base_c"])
    cycle = int(cfg["v1_run_cycle_utc_hour"])
    current = pd.Timestamp("2026-01-02T00:00Z") + pd.Timedelta(hours=cycle)
    prior = current - pd.Timedelta(days=1)
    valid = pd.date_range(
        current + pd.Timedelta(hours=lead_start),
        current + pd.Timedelta(hours=lead_end),
        freq="h",
        inclusive="left",
    )
    source_id = cfg["accepted_source_ids"][0]
    rows = []
    for run_id, issued_at in (("prior", prior), ("current", current)):
        for anchor in anchors:
            for valid_at in valid:
                rows.append(
                    {
                        "run_id": run_id,
                        "issued_at": issued_at,
                        "available_at": issued_at + pd.Timedelta(hours=1),
                        "anchor_id": anchor,
                        "forecast_valid_at": valid_at,
                        "temperature_2m": base - 8.0,
                        "source_id": source_id,
                    }
                )
    return pd.DataFrame(rows), current + pd.Timedelta(hours=2)


@pytest.mark.parametrize("column", ["available_at", "issued_at", "forecast_valid_at"])
def test_weather_pit_timestamps_require_explicit_timezone(column: str) -> None:
    rows, cutoff = _weather_rows()
    rows[column] = rows[column].dt.tz_localize(None)
    with pytest.raises(IndicatorContractError, match="timezone-aware"):
        build_weather_revision(rows, cutoff, _source_policy())


def _power_rows() -> pd.DataFrame:
    policy = _source_policy()
    source_id = policy.payload["sources"]["nyiso_load_forecast"]["accepted_source_ids"][0]
    return pd.DataFrame(
        {
            "issued_at": pd.to_datetime(["2026-01-01T17:00Z", "2026-01-02T17:00Z"]),
            "available_at": pd.to_datetime(["2026-01-01T17:05Z", "2026-01-02T17:05Z"]),
            "forecast_valid_at": pd.to_datetime(["2026-01-02T05:00Z", "2026-01-03T05:00Z"]),
            "power_next_day_load_mean_mw": [100.0, 110.0],
            "power_next_day_load_max_mw": [120.0, 135.0],
            "power_next_day_load_min_mw": [90.0, 95.0],
            "revision_status": ["issued_run_immutable", "issued_run_immutable"],
            "source_id": [source_id, source_id],
        }
    )


@pytest.mark.parametrize("column", ["available_at", "issued_at", "forecast_valid_at"])
def test_power_pit_timestamps_require_explicit_timezone(column: str) -> None:
    rows = _power_rows()
    rows[column] = rows[column].dt.tz_localize(None)
    with pytest.raises(IndicatorContractError, match="timezone-aware"):
        build_power_increments(rows, "2026-01-02T18:00Z", _source_policy())
