from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import commodity.kronos_confirmation_run as run


def _freeze(tmp_path: Path, rows: int = 2) -> dict[str, object]:
    root = tmp_path / "artifacts"
    return {
        "experiment_id": "kronos-180-corrected-three-checkpoint-v1",
        "data_and_target": {
            "oos_rows": rows,
            "forecast_target": "target_ret_1",
        },
        "common_execution": {
            "seed": 0,
            "max_context": 512,
            "inference": {"T": 1.0, "top_p": 0.9, "sample_count": 1, "verbose": False},
        },
        "artifacts": {
            "root": str(root),
            "mini": str(root / "mini"),
            "small": str(root / "small"),
            "base": str(root / "base"),
        },
        "evaluation": {
            "bootstrap": {"block_size": 20, "resamples": 1000, "confidence": 0.95, "seed": 0},
            "primary_comparisons": [
                "mini_vs_zero",
                "mini_vs_v1_hist_gb",
                "small_vs_zero",
                "small_vs_v1_hist_gb",
                "base_vs_zero",
                "base_vs_v1_hist_gb",
                "small_vs_mini",
                "base_vs_mini",
                "base_vs_small",
            ],
            "multiple_testing": {"max_adjusted_p_value": 0.05},
        },
        "benchmarks": {
            "zero_return_naive": {"rmse": 0.1},
            "phase_d_full_v1_hist_gb": {"rmse": 0.11},
        },
        "resource_observations": {
            "max_wall_clock_hours_per_checkpoint": 12,
        },
    }


def test_comparison_family_order_is_fixed() -> None:
    index = pd.date_range("2026-01-01", periods=2, tz="UTC")
    frame = pd.DataFrame({"prediction": [0.0, 0.0], "actual": [0.1, -0.1]}, index=index)
    predictions = {name: frame.copy() for name in run.CHECKPOINTS}

    pairs = run._comparison_pairs(predictions, frame, frame)

    assert list(pairs) == [
        "mini_vs_zero",
        "mini_vs_v1_hist_gb",
        "small_vs_zero",
        "small_vs_v1_hist_gb",
        "base_vs_zero",
        "base_vs_v1_hist_gb",
        "small_vs_mini",
        "base_vs_mini",
        "base_vs_small",
    ]


def test_peak_rss_measurement_is_positive() -> None:
    assert run._peak_rss_bytes() > 0


def test_atomic_json_writes_lf_only(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    run._atomic_json(path, {"value": 1})

    payload = path.read_bytes()
    assert b"\r" not in payload
    assert payload.endswith(b"\n")


def test_atomic_csv_writes_lf_only(tmp_path: Path) -> None:
    path = tmp_path / "predictions.csv"
    run._atomic_csv(path, pd.DataFrame({"prediction": [0.1], "actual": [0.2]}))

    payload = path.read_bytes()
    assert b"\r" not in payload
    assert payload.endswith(b"\n")


def _prepared_for_checkpoint(tmp_path: Path) -> dict[str, object]:
    freeze = _freeze(tmp_path)
    index = pd.date_range("2026-01-05T23:59:00Z", periods=2, freq="D")
    oos = pd.DataFrame({"target_ret_1": [0.01, -0.02]}, index=index)
    target_map = pd.DataFrame(
        {
            "target_timestamp": index + pd.Timedelta(days=1),
            "target_contract_id": ["NGF26", "NGF26"],
        },
        index=index,
    )
    return {
        "freeze": freeze,
        "oos": oos,
        "target_map": target_map,
        "canonical": pd.DataFrame(),
        "selected": pd.DataFrame(),
        "canonical_market_sha256": "b" * 64,
    }


def test_checkpoint_writes_prediction_only_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prepared = _prepared_for_checkpoint(tmp_path)
    freeze = prepared["freeze"]
    adapter = SimpleNamespace(artifact_manifest={"model": {}, "tokenizer": {}})
    monkeypatch.setattr(run, "_prepare_inputs", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(run, "_require_clean_tracked_tree", lambda root: "a" * 40)
    monkeypatch.setattr(run, "_set_seed", lambda seed: None)
    monkeypatch.setattr(run, "_peak_rss_bytes", lambda: 123)
    monkeypatch.setattr(run, "validate_confirmation_freeze", lambda root: freeze)
    monkeypatch.setattr(run, "_validate_evaluator_source", lambda root: {})
    monkeypatch.setattr(
        run,
        "validate_installed_runtime",
        lambda root: {
            "path": "requirements.kronos-cpu.lock.txt",
            "sha256": "a" * 64,
            "python": "3.11",
            "platform": "windows_x86_64",
            "torch": "2.13.0+cpu",
        },
    )
    monkeypatch.setattr(
        run,
        "build_released_checkpoint_adapter",
        lambda root, checkpoint: (adapter, freeze),
    )

    def fake_forecast(**kwargs: object) -> tuple[pd.DataFrame, pd.DataFrame]:
        prediction_time = pd.Timestamp(kwargs["prediction_time"])
        target_timestamp = pd.Timestamp(kwargs["target_timestamp"])
        context = pd.DataFrame(
            {
                "close": [100.0, 100.0],
                "contract_id": ["NGF26", "NGF26"],
                "transformation": ["same_contract_history_v1", "same_contract_history_v1"],
            },
            index=[prediction_time - pd.Timedelta(days=1), prediction_time],
        )
        return pd.DataFrame({"close": [101.0]}, index=[target_timestamp]), context

    monkeypatch.setattr(run, "governed_kronos_forecast", fake_forecast)
    monkeypatch.setattr(run, "governed_return_prediction", lambda **kwargs: 0.01)

    manifest = run.run_checkpoint(
        repo_root=tmp_path,
        dataset_dir=tmp_path / "dataset",
        canonical_market_csv=tmp_path / "canonical.csv",
        checkpoint="mini",
    )

    predictions_path, manifest_path = run._checkpoint_paths(tmp_path, freeze, "mini")
    assert predictions_path.is_file()
    assert manifest_path.is_file()
    assert manifest["state"] == "prediction_complete_pending_joint_evaluation"
    assert manifest["execution_runner_commit"] == "a" * 40
    assert manifest["rows"] == 2
    assert manifest["inference"] == {"T": 1.0, "top_p": 0.9, "sample_count": 1, "verbose": False}
    assert manifest["runtime_lock"] == {
        "path": "requirements.kronos-cpu.lock.txt",
        "sha256": "a" * 64,
        "python": "3.11",
        "platform": "windows_x86_64",
        "torch": "2.13.0+cpu",
    }
    for forbidden in ("metrics", "rmse", "mae", "direction_accuracy", "prediction_actual_corr"):
        assert forbidden not in manifest
    assert not (predictions_path.parent / "metrics.json").exists()

    monkeypatch.setattr(
        run,
        "validate_installed_runtime",
        lambda root: (_ for _ in ()).throw(AssertionError("runtime validation must be skipped on reuse")),
    )
    resumed = run.run_checkpoint(
        repo_root=tmp_path,
        dataset_dir=tmp_path / "dataset",
        canonical_market_csv=tmp_path / "canonical.csv",
        checkpoint="mini",
    )
    assert resumed["predictions_sha256"] == manifest["predictions_sha256"]
