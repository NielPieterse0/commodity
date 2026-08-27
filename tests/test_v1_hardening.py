from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


def _phase_d_frame(rows: int = 60) -> pd.DataFrame:
    index = pd.date_range("2025-01-01T23:59:00Z", periods=rows, freq="D")
    values = pd.Series(range(rows), index=index, dtype=float)
    return pd.DataFrame({
        "ret_1": values / 1000,
        "season_sin": (values % 12) / 12,
        "curve_spread_m1_m2": (values % 5) / 10,
        "storage_signal": values / 100,
        "weather_signal": (values % 9) / 10,
        "power_signal": (values % 11) / 10,
        "positioning_signal": (values % 13) / 10,
        "target_ret_1": ((values.shift(-1).fillna(values.iloc[-1]) % 9) - 4) / 100,
    }, index=index)


def _phase_d_manifest() -> dict:
    families = ["market", "market_structure", "storage", "weather", "power", "positioning", "calendar_seasonality"]
    return {"required_feature_families": families, "source_lineage": {"exogenous_sources": [
        {"family": "storage", "value_columns": ["storage_signal"]},
        {"family": "weather", "value_columns": ["weather_signal"]},
        {"family": "power", "value_columns": ["power_signal"]},
        {"family": "positioning", "value_columns": ["positioning_signal"]},
    ]}}


def _models() -> dict[str, dict]:
    return {
        "naive": {"enabled": True, "baseline_implementation": "zero_return"},
        "ridge": {"enabled": True, "baseline_implementation": "ridge_return", "alpha": 10.0},
        "hist_gb": {"enabled": True, "baseline_implementation": "hist_gradient_boosting_return", "learning_rate": 0.05, "max_iter": 10, "max_leaf_nodes": 7, "random_state": 0},
    }


def _run_phase_d(order: tuple[str, ...], baseline: str = "naive") -> dict:
    from commodity.phase_d_evaluation import run_phase_d_evaluation
    result, _ = run_phase_d_evaluation(
        _phase_d_frame(), _phase_d_manifest(), model_names=order,
        baseline_model=baseline, models=_models(), initial_train=20,
        retrain_every=5, volatility_window=10,
        significance={"block_size": 5, "resamples": 100, "confidence": 0.95, "seed": 0},
    )
    return result


def test_phase_d_baseline_identity_is_not_candidate_order() -> None:
    first = _run_phase_d(("naive", "ridge", "hist_gb"))
    second = _run_phase_d(("hist_gb", "naive", "ridge"))
    assert first["baseline_model"] == second["baseline_model"] == "naive"
    assert {x["model"]: x["rmse_improvement"] for x in first["candidate_comparisons"]} == {
        x["model"]: x["rmse_improvement"] for x in second["candidate_comparisons"]
    }


def test_phase_d_rejects_missing_or_duplicate_baseline() -> None:
    with pytest.raises(ValueError, match="baseline_model"):
        _run_phase_d(("naive", "ridge"), baseline="hist_gb")
    with pytest.raises(ValueError, match="duplicate"):
        _run_phase_d(("naive", "ridge", "naive"))


def test_evaluation_pit_uses_shared_pit_rules() -> None:
    from commodity.availability import validate_availability
    frame = pd.DataFrame({
        "available_at": [pd.Timestamp("2026-01-01T12:00:00Z")],
        "availability_status": ["reconstructed_conservative"],
        "revision_status": ["issued_run_immutable"],
    })
    result = validate_availability(frame, "evaluation_pit")
    assert result.iloc[0]["evidence_mode"] == "evaluation_pit"
    assert not bool(result.iloc[0]["canonical_evidence"])


def test_repository_json_hash_ignores_checkout_line_endings(tmp_path: Path) -> None:
    from commodity.provenance import sha256_json_file
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{\n  "b": 2,\n  "a": 1\n}\n')
    crlf.write_bytes(b'{\r\n  "b": 2,\r\n  "a": 1\r\n}\r\n')
    assert sha256_json_file(lf) == sha256_json_file(crlf)


def test_atomic_json_write_replaces_complete_document(tmp_path: Path) -> None:
    from commodity.provenance import write_json
    target = tmp_path / "evidence.json"
    write_json(target, {"old": True})
    write_json(target, {"new": [1, 2, 3]})
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": [1, 2, 3]}
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_write_normalizes_non_finite_values_to_null(tmp_path: Path) -> None:
    from commodity.provenance import write_json

    target = tmp_path / "metrics.json"
    write_json(target, {"corr": float("nan"), "nested": [float("inf"), -float("inf")]})
    text = target.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text) == {"corr": None, "nested": [None, None]}


def test_bootstrap_rejects_full_v1_claim_without_governed_sources(tmp_path: Path) -> None:
    import numpy as np

    from commodity.cli import build_parser
    source = tmp_path / "bootstrap.csv"
    dates = pd.date_range("2025-01-01", periods=40, freq="D", tz="UTC")
    pd.DataFrame({"date": dates, "open": 1.0, "high": 1.1, "low": 0.9,
                  "close": 1.0 + np.arange(40) / 100, "volume": 100}).to_csv(source, index=False)
    args = build_parser().parse_args(["freeze-v1-dataset", "--input", str(source),
                                      "--output", str(tmp_path / "pit.csv"), "--require-full-v1"])
    with pytest.raises(ValueError, match="bootstrap"):
        args.func(args)


def test_reproduce_v1_cli_points_at_frozen_research_path() -> None:
    from commodity.cli import build_parser
    args = build_parser().parse_args(["reproduce-v1"])
    assert args.func.__name__ == "_reproduce_v1"
    assert "full-v1-freezes" in str(args.dataset_dir)
    assert str(args.config).endswith("config\\phase_d_evaluation.json") or str(args.config).endswith("config/phase_d_evaluation.json")


def test_block_bootstrap_rejects_too_few_effective_blocks() -> None:
    import numpy as np

    from commodity.evaluation import paired_block_bootstrap_rmse
    index = pd.date_range("2026-01-01", periods=40, freq="D", tz="UTC")
    actual = np.linspace(-0.1, 0.1, len(index))
    baseline = pd.DataFrame({"actual": actual, "prediction": 0.0}, index=index)
    challenger = pd.DataFrame({"actual": actual, "prediction": actual}, index=index)
    with pytest.raises(ValueError, match="effective blocks"):
        paired_block_bootstrap_rmse(challenger, baseline, block_size=20, resamples=100, confidence=0.95, seed=0)


def test_hist_gb_random_state_comes_from_model_config() -> None:
    from commodity.models import baseline_factory
    factory = baseline_factory("hist_gb", _models())
    model = factory()
    assert model.model.random_state == 0
    changed = _models()
    changed["hist_gb"]["random_state"] = 17
    assert baseline_factory("hist_gb", changed)().model.random_state == 17


def test_v1_empirical_sources_cannot_retain_pending_authority() -> None:
    from commodity.config import data_config
    sources = [
        source for source in data_config()["sources"].values()
        if source.get("v1_empirical_evidence")
    ]
    assert sources
    for source in sources:
        statuses = (source.get("status", ""), source.get("acquisition_status", ""))
        assert all("pending" not in str(value).lower() for value in statuses)
        assert all("acquisition_required" not in str(value).lower() for value in statuses)


def test_wngsr_release_logic_has_one_authoritative_resolver() -> None:
    from commodity.availability import (
        annotate_wngsr_availability,
        resolve_wngsr_release,
    )
    from commodity.config import data_config
    from commodity.wngsr import resolve_wngsr_release_availability
    cfg = data_config()["sources"]["eia_storage"]
    observed = pd.Timestamp("2025-10-31T00:00:00Z")
    direct, status, _ = resolve_wngsr_release(observed, cfg)
    annotated = annotate_wngsr_availability(pd.DataFrame({"period": [observed]}), cfg)
    assert status == "reconstructed_conservative"
    assert pd.Timestamp(direct) == annotated.iloc[0]["available_at"]
    assert resolve_wngsr_release_availability(observed) == pd.Timestamp(direct)


def test_locked_environment_check_detects_version_drift(tmp_path: Path) -> None:
    from commodity.provenance import locked_environment_mismatches
    lock = tmp_path / "requirements.lock.txt"
    lock.write_text("pip==0.0\n", encoding="utf-8")
    mismatches = locked_environment_mismatches(lock)
    assert mismatches and mismatches[0].startswith("pip:")
