import json
from pathlib import Path

import numpy as np

from commodity.volatility_event_nuisance_calibration import (
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


def test_event_block_sd_is_translation_invariant() -> None:
    values = np.arange(1.0, 81.0)
    assert _centered_block_sd(values, 4) == _centered_block_sd(values + 1000.0, 4)


def test_event_calibration_result_is_fail_closed() -> None:
    result_path = Path(__file__).parents[1] / (
        "docs/development/volatility-event-nuisance-calibration/result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert FORBIDDEN_OUTPUTS.isdisjoint(result)
    assert result["train_identity_sha256"] == TRAIN_IDENTITY_SHA256
    assert result["calibration_identity_sha256"] == CALIBRATION_IDENTITY_SHA256
    assert result["calibration_events"] == 80
    assert result["confirmation_events"] == 342
    assert result["power_gate_pass"] is False
    assert result["protected_confirmation_performance_inspected"] is False
    assert result["future_504_performance_inspected"] is False
    assert set(result["relative_mde_at_exact_confirmation_n"]) == {
        "2_events",
        "4_events",
        "8_events",
    }
