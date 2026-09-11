from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from commodity.foundation_specialists import (
    SpecialistIdentity,
    merge_specialist_features,
    probabilistic_interval_diagnostics,
    remove_one_component_sets,
    validate_specialist_features,
)


def _runner_module():
    path = Path(__file__).parents[1] / "scripts" / "research" / "run_phase4_foundation_specialists.py"
    spec = importlib.util.spec_from_file_location("phase4_foundation_specialists_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _identity(**overrides: str) -> SpecialistIdentity:
    values = {
        "name": "timesfm_2_5",
        "model_id": "google/timesfm-2.5-200m-pytorch",
        "model_revision": "1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
        "checkpoint_sha256": "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8",
        "pretraining_exposure": "not_proven_pre_target",
        "license_status": "verified_for_research_use",
    }
    values.update(overrides)
    return SpecialistIdentity(**values)


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prediction_time": ["2022-01-03T23:59:00Z", "2022-01-04T23:59:00Z"],
            "generated_at": ["2022-01-03T23:59:00Z", "2022-01-04T23:59:00Z"],
            "contract_id": ["NGG2", "NGG2"],
            "timesfm_point": [0.01, -0.02],
        }
    )


def test_specialist_features_reject_post_cutoff_generation() -> None:
    frame = _features()
    frame.loc[0, "generated_at"] = "2022-01-04T00:00:00Z"
    with pytest.raises(ValueError, match="after its prediction cutoff"):
        validate_specialist_features(
            frame, identity=_identity(), feature_columns=["timesfm_point"]
        )


def test_specialist_features_accept_mixed_iso_timestamp_precision() -> None:
    frame = _features()
    frame.loc[1, "prediction_time"] = "2022-01-04T23:59:00.123456+00:00"
    frame.loc[1, "generated_at"] = "2022-01-04T23:59:00.123456+00:00"

    checked = validate_specialist_features(
        frame,
        identity=_identity(),
        feature_columns=["timesfm_point"],
    )

    assert checked["prediction_time"].dt.tz is not None


def test_specialist_features_reject_target_leakage_columns() -> None:
    frame = _features().assign(target_ret_1=[0.1, 0.2])
    with pytest.raises(ValueError, match="target leakage"):
        validate_specialist_features(
            frame, identity=_identity(), feature_columns=["timesfm_point"]
        )


def test_specialist_identity_requires_verified_research_license() -> None:
    with pytest.raises(ValueError, match="license"):
        validate_specialist_features(
            _features(),
            identity=_identity(license_status="unverified"),
            feature_columns=["timesfm_point"],
        )


def test_merge_requires_complete_exact_pit_coverage() -> None:
    market = pd.DataFrame(
        {
            "prediction_time": ["2022-01-03T23:59:00Z", "2022-01-04T23:59:00Z"],
            "contract_id": ["NGG2", "NGG2"],
            "market_signal": [1.0, 2.0],
        }
    )
    specialist = _features().iloc[:1]
    with pytest.raises(ValueError, match="coverage is incomplete"):
        merge_specialist_features(
            market,
            specialist,
            identity=_identity(),
            feature_columns=["timesfm_point"],
        )


def test_phase4_runner_rejects_specialist_contract_mismatch() -> None:
    runner = _runner_module()
    market = pd.DataFrame(
        {
            "trade_date": ["2022-01-03T00:00:00Z"],
            "available_at": ["2022-01-03T23:59:00Z"],
            "feature_ret_1": [0.01],
        }
    )
    session = pd.DataFrame(
        {"trade_date": ["2022-01-03T00:00:00Z"], "contract_id": ["NGG2"]}
    )
    specialist = pd.DataFrame(
        {
            "trade_date": ["2022-01-03T00:00:00Z"],
            "prediction_time": ["2022-01-03T23:59:00Z"],
            "generated_at": ["2022-01-03T23:59:00Z"],
            "contract_id": ["NGH2"],
            "timesfm_point": [0.02],
        }
    )

    with pytest.raises(ValueError, match="coverage is incomplete"):
        runner._merge_specialist_at_phase2_origin(
            market,
            session,
            specialist,
            identity=_identity(),
            feature_columns=["timesfm_point"],
        )


def test_phase4_runner_accepts_sub_microsecond_serialization_loss() -> None:
    runner = _runner_module()
    market = pd.DataFrame(
        {
            "trade_date": ["2022-01-03T00:00:00Z"],
            "available_at": ["2022-01-03T23:59:00.123456789Z"],
            "feature_ret_1": [0.01],
        }
    )
    session = pd.DataFrame(
        {"trade_date": ["2022-01-03T00:00:00Z"], "contract_id": ["NGG2"]}
    )
    specialist = pd.DataFrame(
        {
            "trade_date": ["2022-01-03T00:00:00Z"],
            "prediction_time": ["2022-01-03T23:59:00.123456Z"],
            "generated_at": ["2022-01-03T23:59:00.123456Z"],
            "contract_id": ["NGG2"],
            "timesfm_point": [0.02],
        }
    )

    merged = runner._merge_specialist_at_phase2_origin(
        market,
        session,
        specialist,
        identity=_identity(),
        feature_columns=["timesfm_point"],
    )
    assert merged.loc[0, "timesfm_point"] == pytest.approx(0.02)


def test_phase4_runner_rejects_one_microsecond_cutoff_drift() -> None:
    runner = _runner_module()
    market = pd.DataFrame(
        {
            "trade_date": ["2022-01-03T00:00:00Z"],
            "available_at": ["2022-01-03T23:59:00.123456Z"],
            "feature_ret_1": [0.01],
        }
    )
    session = pd.DataFrame(
        {"trade_date": ["2022-01-03T00:00:00Z"], "contract_id": ["NGG2"]}
    )
    specialist = pd.DataFrame(
        {
            "trade_date": ["2022-01-03T00:00:00Z"],
            "prediction_time": ["2022-01-03T23:59:00.123457Z"],
            "generated_at": ["2022-01-03T23:59:00.123457Z"],
            "contract_id": ["NGG2"],
            "timesfm_point": [0.02],
        }
    )

    with pytest.raises(ValueError, match="prediction time"):
        runner._merge_specialist_at_phase2_origin(
            market,
            session,
            specialist,
            identity=_identity(),
            feature_columns=["timesfm_point"],
        )


def test_remove_one_component_sets_are_deterministic() -> None:
    result = remove_one_component_sets(["market", "kronos", "timesfm", "kronos"])
    assert result == {
        "market": ("kronos", "timesfm"),
        "kronos": ("market", "timesfm"),
        "timesfm": ("market", "kronos"),
    }


def test_probabilistic_interval_diagnostics_reports_quantile_calibration() -> None:
    result = probabilistic_interval_diagnostics(
        actual=pd.Series([-0.03, 0.00, 0.02, 0.08]),
        lower=pd.Series([-0.02, -0.01, 0.00, 0.01]),
        upper=pd.Series([0.03, 0.02, 0.04, 0.06]),
        lower_quantile=0.10,
        upper_quantile=0.90,
    )

    assert result == {
        "rows": 4,
        "nominal_coverage": pytest.approx(0.8),
        "empirical_coverage": pytest.approx(0.5),
        "coverage_error": pytest.approx(-0.3),
        "lower_hit_rate": pytest.approx(0.25),
        "lower_calibration_error": pytest.approx(0.15),
        "upper_hit_rate": pytest.approx(0.75),
        "upper_calibration_error": pytest.approx(-0.15),
        "below_interval_rate": pytest.approx(0.25),
        "above_interval_rate": pytest.approx(0.25),
        "mean_interval_width": pytest.approx(0.0425),
    }


def test_phase4_runner_rejects_concurrent_checkpoint_writer(tmp_path: Path) -> None:
    runner = _runner_module()
    lock_path = tmp_path / "kronos-features.csv.writer.lock"

    with (
        runner._checkpoint_writer_lock(lock_path),
        pytest.raises(RuntimeError, match="checkpoint writer already active"),
        runner._checkpoint_writer_lock(lock_path),
    ):
        pass

    with runner._checkpoint_writer_lock(lock_path):
        pass
