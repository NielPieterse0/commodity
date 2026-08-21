from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from commodity.research_dataset import dataframe_sha256


def _dataset(rows: int = 300) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "ret_1": np.linspace(-0.02, 0.02, rows),
            "curve_slope": np.linspace(-0.1, 0.1, rows),
            "storage_signal": np.linspace(0.0, 1.0, rows),
            "weather_signal": np.linspace(10.0, 20.0, rows),
            "power_signal": np.linspace(100.0, 120.0, rows),
            "positioning_signal": np.linspace(-1.0, 1.0, rows),
            "target_ret_1": np.linspace(-0.01, 0.01, rows),
        },
        index=index,
    )


def _manifest(frame: pd.DataFrame) -> dict:
    required = [
        "market", "market_structure", "storage", "weather", "power",
        "positioning", "calendar_seasonality",
    ]
    exogenous = []
    for family in ("storage", "weather", "power", "positioning"):
        exogenous.append(
            {
                "name": f"{family}_pit",
                "family": family,
                "source_id": f"source-{family}",
                "source_vintage": "2025-v1",
                "source_sha256": {
                    "storage": "a", "weather": "b", "power": "c", "positioning": "d"
                }[family] * 64,
                "availability_statuses": ["verified"],
                "availability_bases": ["source_timestamp"],
                "revision_statuses": ["point_in_time"],
                "join_coverage_ratio": 1.0,
                "unmatched_rows": 0,
            }
        )
    return {
        "schema_version": 1,
        "dataset_id": "us-ng-v1-pit-test",
        "dataset_sha256": dataframe_sha256(frame),
        "evidence_mode": "research_pit",
        "completeness": "full_v1",
        "required_feature_families": required,
        "included_feature_families": required,
        "missing_feature_families": [],
        "rows": len(frame),
        "initial_train_rows": 252,
        "minimum_exogenous_join_coverage": 1.0,
        "columns": list(frame.columns),
        "start": frame.index[0].isoformat(),
        "end": frame.index[-1].isoformat(),
        "target": "target_ret_1",
        "prediction_timestamp_semantics": "after_current_daily_bar_close",
        "exogenous_sources": exogenous,
        "exogenous_family_audits": {
            family: [{"verdict": "fit", "full_v1_ready": True}]
            for family in ("storage", "weather", "power", "positioning")
        },
        "market_structure": {
            "contract_input_sha256": "a" * 64,
            "selected_path_sha256": "b" * 64,
            "roll_ledger_sha256": "c" * 64,
            "curve_features_sha256": "d" * 64,
            "curve_audit_sha256": "e" * 64,
            "roll_policy_sha256": "f" * 64,
        },
    }


def test_freeze_requires_real_full_v1_contract(tmp_path: Path) -> None:
    from commodity.dataset_freeze import freeze_full_v1_dataset

    frame = _dataset()
    manifest = _manifest(frame)
    manifest["completeness"] = "pit_core"
    with pytest.raises(ValueError, match="full_v1"):
        freeze_full_v1_dataset(frame, manifest, tmp_path)


def test_freeze_is_content_addressed_and_repeatable(tmp_path: Path) -> None:
    from commodity.dataset_freeze import freeze_full_v1_dataset, load_frozen_dataset

    frame = _dataset()
    manifest = _manifest(frame)
    first = freeze_full_v1_dataset(frame, manifest, tmp_path)
    second = freeze_full_v1_dataset(frame, manifest, tmp_path)
    assert first == second
    restored, frozen = load_frozen_dataset(first)
    pd.testing.assert_frame_equal(restored, frame, check_freq=False)
    assert frozen["freeze_id"] in first.name
    assert frozen["dataset_sha256"] == manifest["dataset_sha256"]
    assert frozen["dataset_artifact_sha256"] == manifest["dataset_sha256"]
    assert frozen["upstream_manifest_sha256"]
    assert frozen["configuration_sha256"]["experiment"]
    assert frozen["transformation_sha256"]["research_dataset"]
    assert frozen["dataset_audit"]["verdict"] == "fit"
    assert (first / "upstream-manifest.json").is_file()


def test_freeze_hashes_the_config_files_resolved_at_runtime(monkeypatch, tmp_path: Path) -> None:
    from commodity import config
    from commodity.dataset_freeze import freeze_full_v1_dataset

    override = tmp_path / "config"
    override.mkdir()
    for name in ("experiment.json", "data_sources.json"):
        shutil.copy2(config.SOURCE_CONFIG_DIR / name, override / name)
    data_path = override / "data_sources.json"
    data_path.write_text(data_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    monkeypatch.setenv("COMMODITY_CONFIG_DIR", str(override))

    frozen = freeze_full_v1_dataset(_dataset(), _manifest(_dataset()), tmp_path / "frozen")
    payload = json.loads((frozen / "manifest.json").read_text(encoding="utf-8"))
    expected = hashlib.sha256(data_path.read_bytes()).hexdigest()
    source_digest = hashlib.sha256((config.SOURCE_CONFIG_DIR / "data_sources.json").read_bytes()).hexdigest()
    assert payload["configuration_sha256"]["data_sources"] == expected
    assert expected != source_digest


def test_freeze_refuses_conflicting_existing_artifact(tmp_path: Path) -> None:
    from commodity.dataset_freeze import (
        FrozenDatasetIntegrityError,
        freeze_full_v1_dataset,
    )

    frame = _dataset()
    manifest = _manifest(frame)
    frozen = freeze_full_v1_dataset(frame, manifest, tmp_path)
    (frozen / "dataset.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(FrozenDatasetIntegrityError):
        freeze_full_v1_dataset(frame, manifest, tmp_path)


def test_freeze_manifest_has_no_volatile_timestamp(tmp_path: Path) -> None:
    from commodity.dataset_freeze import freeze_full_v1_dataset

    frame = _dataset()
    frozen = freeze_full_v1_dataset(frame, _manifest(frame), tmp_path)
    payload = json.loads((frozen / "manifest.json").read_text(encoding="utf-8"))
    assert "created_at" not in payload
    assert payload["grain"] == "one row per prediction_time"
    assert payload["unique_key"] == ["prediction_time"]


def test_freeze_requires_independent_fit_audit(tmp_path: Path) -> None:
    from commodity.dataset_freeze import freeze_full_v1_dataset

    frame = _dataset()
    manifest = _manifest(frame)
    manifest["exogenous_sources"][0]["source_sha256"] = None
    with pytest.raises(ValueError, match="audit"):
        freeze_full_v1_dataset(frame, manifest, tmp_path)


def test_freeze_preserves_evaluation_only_promotion_boundary(tmp_path: Path) -> None:
    from commodity.dataset_freeze import freeze_full_v1_dataset

    frame = _dataset()
    manifest = _manifest(frame)
    manifest.update(
        {
            "evidence_mode": "evaluation_pit",
            "canonical_market_evidence": False,
            "market_evaluation_evidence": True,
            "research_evaluation_eligible": True,
            "research_promotion_eligible": False,
        }
    )
    frozen = freeze_full_v1_dataset(frame, manifest, tmp_path)
    payload = json.loads((frozen / "manifest.json").read_text(encoding="utf-8"))
    assert payload["evidence_mode"] == "evaluation_pit"
    assert payload["canonical_market_evidence"] is False
    assert payload["market_evaluation_evidence"] is True
    assert payload["research_promotion_eligible"] is False
    assert payload["dataset_audit"]["verdict"] == "fit-with-caveats"
    assert "evaluation_only_market_evidence" in payload["dataset_audit"]["caveats"]
