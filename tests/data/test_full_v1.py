from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest


def _market_snapshot(tmp_path: Path) -> Path:
    canonical = tmp_path / "canonical.csv"
    canonical.write_text(
        "trade_date,contract_id,expiration,settle\n"
        "2026-01-02,NGF26,2026-01-28,3.1\n",
        encoding="utf-8",
        newline="",
    )
    content = canonical.read_bytes()
    manifest = {
        "schema_version": 1,
        "provider": "massive",
        "snapshot_id": "fixture",
        "artifacts": [{
            "path": "canonical.csv",
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }],
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8", newline=""
    )
    return canonical


def test_full_v1_market_input_uses_raw_archive_reconstruction_before_dataset_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from commodity import full_v1

    canonical = _market_snapshot(tmp_path)
    monkeypatch.setattr(full_v1, "_load_sources", lambda _: ())

    captured: dict[str, object] = {}

    def fake_reconstruct(manifest_path: Path, schema: dict) -> pd.DataFrame:
        captured["replay_manifest"] = manifest_path
        captured["schema"] = schema
        return pd.read_csv(canonical)

    def fake_build(*args, **kwargs):
        from commodity.data_assurance import build_construction_contract

        captured["contracts"] = kwargs["canonical_contracts"]
        captured["source"] = kwargs["market_source_id"]
        assurance = build_construction_contract(
            source_inputs=[{"id": "market:massive_henry_hub_evaluation", "sha256": "1" * 64}],
            layers=[
                {"name": "retained_source_evidence", "status": "constructed", "sha256": "2" * 64},
                {"name": "canonical_normalization", "status": "constructed", "sha256": "3" * 64},
            ],
            transformation_sha256={"fixture": "4" * 64},
        )
        return pd.DataFrame(), {"data_assurance": assurance}

    monkeypatch.setattr(full_v1, "reconstruct_massive_archive", fake_reconstruct)
    monkeypatch.setattr(full_v1, "build_pit_dataset", fake_build)
    _, manifest = full_v1._build_once(tmp_path, canonical)
    assert captured["replay_manifest"] == tmp_path / "manifest.json"
    assert captured["source"] == "massive_henry_hub_evaluation"
    assert len(captured["contracts"]) == 1
    assurance = manifest["data_assurance"]
    assert any(
        item["id"] == "market-archive:massive_henry_hub_evaluation"
        for item in assurance["source_inputs"]
    )
    assert "massive_futures_provider" in assurance["transformation_sha256"]
    assert "full_v1" in assurance["transformation_sha256"]
