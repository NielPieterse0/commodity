import json
from pathlib import Path

import numpy as np

from commodity.volatility_nuisance_calibration import (
    CALIBRATION_IDENTITY_SHA256,
    TRAIN_IDENTITY_SHA256,
    _centered_block_sd,
)

FORBIDDEN_OUTPUTS = {
    "mean_challenger_qlike",
    "mean_paired_improvement",
    "p_value",
    "confidence_interval",
    "period_result",
    "regime_result",
    "secondary_performance",
}


def test_centered_block_sd_is_translation_invariant() -> None:
    values = np.arange(1.0, 81.0)
    assert _centered_block_sd(values, 20) == _centered_block_sd(values + 1000.0, 20)


def test_calibration_result_contains_only_permitted_performance_outputs() -> None:
    result_path = Path(__file__).parents[1] / "docs" / "development" / "volatility-nuisance-calibration" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert FORBIDDEN_OUTPUTS.isdisjoint(result)
    assert result["train_identity_sha256"] == TRAIN_IDENTITY_SHA256
    assert result["calibration_identity_sha256"] == CALIBRATION_IDENTITY_SHA256
    assert result["calibration_rows"] == 720
    assert result["protected_1800_performance_inspected"] is False
    assert result["existing_504_future_rows_inspected"] is False
    assert result["power_gate_pass"] is False
    assert set(result["relative_mde_at_1800"]) == {
        "20_sessions",
        "40_sessions",
        "60_sessions",
    }
