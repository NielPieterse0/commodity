from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHADOW_SCRIPT = ROOT / "scripts" / "research" / "run_phase7_saxo_shadow.py"
PHASE7_SCRIPT = ROOT / "scripts" / "research" / "run_phase7_frozen_evaluation.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_decision(ledger: Path) -> dict[str, object]:
    phase7 = _load(PHASE7_SCRIPT, "phase7_shadow_seed")
    event = {
        "event_type": "decision",
        "recorded_at": "2026-09-13T12:00:01+00:00",
        "record_id": "prospective-1",
        "decision_timestamp": "2026-09-13T12:00:00+00:00",
        "planned_fill_timestamp": "2026-09-14T00:00:00+00:00",
        "target_end_timestamp": "2026-09-19T00:00:00+00:00",
        "contract_id": "NGX6",
        "forecast_id": "forecast-2026-09-13",
        "intended_position": -0.5,
    }
    return phase7._append_prospective_event(event, ledger=ledger)


class FakeLiveClient:
    provider_id = "saxo_openapi_live"

    def search_contract_futures(self, keywords: str, top: int = 100):
        assert "Natural Gas" in keywords
        return [{
            "AssetType": "ContractFutures",
            "DisplayHint": "Continuous",
            "Identifier": 100,
            "Symbol": "NG",
        }]

    def futures_space(self, continuous_uic: int):
        assert continuous_uic == 100
        return {"BaseIdentifier": "NG", "Elements": [
            {"Symbol": "NGV6", "Uic": 200, "ExpiryDate": "2026-09-28T00:00:00Z"},
            {"Symbol": "NGX6", "Uic": 201, "ExpiryDate": "2026-10-28T00:00:00Z"},
        ]}

    def chart_snapshot(self, uic: int, horizon: int = 1):
        assert uic == 201
        assert horizon == 1
        return {
            "ChartInfo": {"ExchangeId": "NYMEX", "DelayedByMinutes": 0},
            "DisplayAndFormat": {"Symbol": "NGX6", "Currency": "USD"},
            "Data": [{
                "Time": "2026-09-13T11:59:00Z",
                "Open": 3.01,
                "High": 3.02,
                "Low": 3.00,
                "Close": 3.015,
                "Volume": 25,
            }],
        }


def test_shadow_capture_binds_existing_decision_without_mutating_scientific_ledger(tmp_path: Path) -> None:
    module = _load(SHADOW_SCRIPT, "phase7_saxo_shadow")
    canonical = tmp_path / "prospective.jsonl"
    shadow = tmp_path / "saxo-shadow.jsonl"
    decision = _seed_decision(canonical)
    before = canonical.read_bytes()

    captured = module.capture_decision_shadow(
        client=FakeLiveClient(),
        record_id="prospective-1",
        canonical_ledger=canonical,
        shadow_ledger=shadow,
        recorded_at="2026-09-13T12:00:05+00:00",
    )

    assert canonical.read_bytes() == before
    assert captured["event_type"] == "saxo_execution_shadow"
    assert captured["phase7_record_id"] == "prospective-1"
    assert captured["phase7_decision_record_sha256"] == decision["record_sha256"]
    assert captured["contract_id"] == "NGX6"
    assert captured["saxo_uic"] == 201
    assert captured["chart_sample"]["close"] == pytest.approx(3.015)
    assert captured["canonical_scientific_source"] is False
    assert captured["phase7_decision_source_allowed"] is False
    assert captured["phase7_settlement_source_allowed"] is False
    assert captured["order_submission_attempted"] is False


def test_shadow_capture_requires_live_provider_and_existing_decision(tmp_path: Path) -> None:
    module = _load(SHADOW_SCRIPT, "phase7_saxo_shadow_guards")
    canonical = tmp_path / "prospective.jsonl"
    _seed_decision(canonical)

    class FakeSimClient(FakeLiveClient):
        provider_id = "saxo_openapi_sim"

    with pytest.raises(ValueError, match="LIVE"):
        module.capture_decision_shadow(
            client=FakeSimClient(),
            record_id="prospective-1",
            canonical_ledger=canonical,
            shadow_ledger=tmp_path / "shadow.jsonl",
        )

    with pytest.raises(ValueError, match="existing Phase-7 decision"):
        module.capture_decision_shadow(
            client=FakeLiveClient(),
            record_id="missing",
            canonical_ledger=canonical,
            shadow_ledger=tmp_path / "shadow.jsonl",
        )


def test_shadow_ledger_hash_chain_detects_tampering(tmp_path: Path) -> None:
    module = _load(SHADOW_SCRIPT, "phase7_saxo_shadow_chain")
    canonical = tmp_path / "prospective.jsonl"
    shadow = tmp_path / "shadow.jsonl"
    _seed_decision(canonical)
    module.capture_decision_shadow(
        client=FakeLiveClient(), record_id="prospective-1",
        canonical_ledger=canonical, shadow_ledger=shadow,
        recorded_at="2026-09-13T12:00:05+00:00",
    )
    shadow.write_text(shadow.read_text(encoding="utf-8").replace("3.015", "9.999"), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        module.read_shadow_events(shadow)
