from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from commodity.timesfm_ensemble_reanalysis import (
    EXPECTED_CONTRACT_SHA256,
    TimesFMEnsembleReanalysisError,
    evaluate_reanalysis,
    validate_reanalysis_authority,
)


def test_authority_binds_landed_contract() -> None:
    root = Path.cwd()
    authority = validate_reanalysis_authority(root)
    assert authority["contract"]["issue"] == 226
    assert authority["authority"]["issue"] == 228
    assert authority["authority"]["frozen_contract_sha256"] == EXPECTED_CONTRACT_SHA256


def test_authority_rejects_contract_drift(tmp_path: Path) -> None:
    contract = tmp_path / "docs/development/timesfm-ensemble-successor-preregistration/contract.json"
    auth = tmp_path / "docs/development/timesfm-ensemble-reanalysis/execution-authority.json"
    contract.parent.mkdir(parents=True)
    auth.parent.mkdir(parents=True)
    contract.write_text('{}\n', encoding='utf-8')
    auth.write_text(
        json.dumps({"execution_authorized": True, "frozen_contract_sha256": EXPECTED_CONTRACT_SHA256}),
        encoding="utf-8",
    )
    with pytest.raises(TimesFMEnsembleReanalysisError, match="contract hash drifted"):
        validate_reanalysis_authority(tmp_path)


def _prepared_for_decision() -> dict[str, object]:
    root = Path.cwd()
    contract = json.loads(
        (root / "docs/development/timesfm-ensemble-successor-preregistration/contract.json").read_text()
    )
    actual = np.resize(np.array([0.10, -0.10, 0.05, -0.05]), 204)
    histgb = np.resize(np.array([0.08, -0.08, 0.04, -0.04]), 204)
    cases = [type("Case", (), {"actual_return": value})() for value in actual]
    rows = []
    prior = []
    for candidate in contract["candidates"]["members"]:
        representation = candidate["representation"]
        context = candidate["context"]
        point = np.zeros(204, dtype=float)
        for index, value in enumerate(actual):
            rows.append({
                "representation": representation,
                "context": context,
                "actual": value,
                "point": point[index],
            })
        prior.append({
            "representation": representation,
            "context": context,
            "rmse_improvement": 0.001,
            "adjusted_p_value": 0.01,
        })
    return {
        "successor_contract": contract,
        "predictions": pd.DataFrame(rows),
        "cases": cases,
        "histgb": pd.DataFrame({"prediction": histgb}),
        "prior_result": {"complementarity_family": prior},
    }


def test_joint_gate_requires_zero_and_histgb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prepared = _prepared_for_decision()
    monkeypatch.setattr(
        "commodity.timesfm_ensemble_reanalysis._rmse_improvement",
        lambda actual, challenger, baseline: {
            "rmse_improvement": 0.001,
            "p_value_one_sided_improvement": 0.001,
        },
    )
    result = evaluate_reanalysis(prepared, tmp_path)
    assert result["decision"]["reanalysis_pass"] is True
    assert all(item["passes_joint_gate"] for item in result["candidates"])


def test_joint_gate_fails_without_histgb_increment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prepared = _prepared_for_decision()
    prepared["prior_result"]["complementarity_family"][0]["adjusted_p_value"] = 0.20
    monkeypatch.setattr(
        "commodity.timesfm_ensemble_reanalysis._rmse_improvement",
        lambda actual, challenger, baseline: {
            "rmse_improvement": 0.001,
            "p_value_one_sided_improvement": 0.001,
        },
    )
    result = evaluate_reanalysis(prepared, tmp_path)
    assert result["candidates"][0]["passes_zero_gate"] is True
    assert result["candidates"][0]["passes_histgb_gate"] is False
    assert result["candidates"][0]["passes_joint_gate"] is False


def test_execution_source_does_not_generate_new_forecasts() -> None:
    source = Path("src/commodity/timesfm_ensemble_reanalysis.py").read_text(encoding="utf-8")
    assert "generate_predictions" not in source
    assert "_load_model" not in source
    assert "forecast(" not in source


def test_reanalysis_rejects_reduced_oos_panel(tmp_path: Path) -> None:
    prepared = _prepared_for_decision()
    prepared["cases"] = prepared["cases"][:-1]
    with pytest.raises(
        TimesFMEnsembleReanalysisError,
        match="requires exactly 204 frozen OOS rows",
    ):
        evaluate_reanalysis(prepared, tmp_path)
