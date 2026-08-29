from __future__ import annotations

import math

from commodity import entrypoint  # noqa: F401
from commodity import research_methodology
from commodity.methodology_extensions import compute_effective_information
from commodity.programme_inference import (
    hansen_spa,
    model_confidence_set,
    white_reality_check,
)


def test_entrypoint_installs_extended_effective_information() -> None:
    assert research_methodology.compute_effective_information is compute_effective_information


def test_newey_west_effective_information_is_machine_derived() -> None:
    result = compute_effective_information(
        {
            "raw_n": 100,
            "method": "newey_west",
            "parameters": {"lag": 2, "autocorrelations": [0.2, 0.1]},
        }
    )
    expected_vif = 1 + 2 * ((1 - 1 / 3) * 0.2 + (1 - 2 / 3) * 0.1)
    assert math.isclose(result["effective_information"], 100 / expected_vif)


def test_block_bootstrap_effective_information_uses_block_units() -> None:
    result = compute_effective_information(
        {
            "raw_n": 250,
            "method": "block_bootstrap",
            "parameters": {"block_length": 5},
        }
    )
    assert result["effective_information"] == 50


def _differentials() -> dict[str, list[float]]:
    return {
        "candidate_a": [0.8, 0.7, 0.9, 0.6, 0.8, 0.7, 0.9, 0.8, 0.7, 0.8],
        "candidate_b": [-0.1, 0.0, 0.1, -0.1, 0.0, 0.1, 0.0, -0.1, 0.1, 0.0],
    }


def test_white_reality_check_is_native_and_deterministic() -> None:
    result = white_reality_check(
        _differentials(), bootstrap_samples=100, block_length=2, seed=17
    )
    assert result["procedure"] == "white_reality_check"
    assert result["best_candidate"] == "candidate_a"
    assert 0 <= result["p_value"] <= 1
    assert len(result["inputs_sha256"]) == 64


def test_hansen_spa_is_native_and_deterministic() -> None:
    result = hansen_spa(
        _differentials(), bootstrap_samples=100, block_length=2, seed=17
    )
    assert result["procedure"] == "hansen_spa"
    assert result["best_candidate"] == "candidate_a"
    assert 0 <= result["p_value"] <= 1


def test_model_confidence_set_removes_clearly_worse_model() -> None:
    losses = {
        "good": [0.9, 1.0, 1.1, 0.9, 1.0, 1.1, 0.9, 1.0, 1.1, 1.0],
        "bad": [2.0, 2.1, 2.2, 2.0, 2.1, 2.2, 2.0, 2.1, 2.2, 2.1],
    }
    result = model_confidence_set(
        losses, alpha=0.05, bootstrap_samples=100, block_length=2, seed=17
    )
    assert result["procedure"] == "model_confidence_set"
    assert "good" in result["included_models"]
    assert len(result["inputs_sha256"]) == 64
