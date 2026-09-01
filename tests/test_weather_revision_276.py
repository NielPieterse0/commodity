from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_weather_revision_276_holds_before_outcomes() -> None:
    record = _json("research/exploratory/weather-revision-mechanism-276.json")
    assert record["schema_version"] == 2
    assert record["feasibility"]["decision"] == "hold"
    assert record["execution"]["protected_outcomes_accessed"] is False
    assert record["execution"]["preregistration_ref"] is None
    assert record["feasibility"]["evidence"]["target_outcomes_inspected"] is False
    frozen = record["feasibility"]["evidence"]["frozen_candidate"]
    assert frozen["cycle"] == "00 UTC only"
    assert "+24h through +168h" in frozen["valid_horizons"]
    assert "same trade-date final settlement" in frozen["response_target"]


def test_weather_revision_276_source_contract_fails_closed() -> None:
    source = _json("config/data_sources.json")["sources"]["noaa_gfs_weather_revision"]
    assert source["status"] == "feasibility_hold_source_audit_required"
    assert source["forbidden_substitute"] == "reanalysis_or_realized_weather"
    assert source["missing_cycle_policy"].startswith("drop_event")
    assert source["weighting_status"].startswith("hold_until_pit")
