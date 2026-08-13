import numpy as np
import pandas as pd

from commodity.evaluation import evaluate_predictions, walk_forward_predict
from commodity.models import RidgeReturnModel, ZeroReturnModel
from commodity.simulation import simulate_forecasts


def _sample_xy(n: int = 80) -> tuple[pd.DataFrame, pd.Series]:
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    x = pd.DataFrame({"a": np.linspace(0, 1, n), "b": np.sin(np.arange(n))}, index=idx)
    y = pd.Series(np.cos(np.arange(n)) / 100, index=idx)
    return x, y


def test_walk_forward_does_not_use_future_labels() -> None:
    x, y = _sample_xy()
    base = walk_forward_predict(lambda: RidgeReturnModel(1.0), x, y, initial_train=30, retrain_every=1)
    mutated = y.copy()
    mutated.iloc[31:] = 999.0
    changed = walk_forward_predict(lambda: RidgeReturnModel(1.0), x, mutated, initial_train=30, retrain_every=1)
    assert base.iloc[0]["prediction"] == changed.iloc[0]["prediction"]


def test_walk_forward_rejects_nonpositive_retrain_interval() -> None:
    import pytest

    x, y = _sample_xy()
    for retrain_every in (0, -1):
        with pytest.raises(ValueError, match="retrain_every must be at least 1"):
            walk_forward_predict(
                ZeroReturnModel,
                x,
                y,
                initial_train=30,
                retrain_every=retrain_every,
            )


def test_forecast_metrics_exclude_strategy_and_execution_fields() -> None:
    x, y = _sample_xy()
    pred = walk_forward_predict(ZeroReturnModel, x, y, initial_train=30)
    metrics = evaluate_predictions(pred)
    assert metrics["n"] == 50.0
    assert "net_log_return" not in metrics
    assert "cost_bps" not in metrics


def test_simulation_requires_explicit_policy_and_cost_configuration() -> None:
    pred = pd.DataFrame({"prediction": [0.1, -0.1], "actual": [0.02, -0.01]})
    policy = {"enabled": True, "type": "prediction_sign", "position_scale": 1.0}
    simulation = {
        "enabled": True,
        "cost_model": {"type": "turnover_bps", "turnover_bps": 2.0},
    }
    path, metrics = simulate_forecasts(pred, policy, simulation)
    assert list(path["position"]) == [1.0, -1.0]
    assert metrics["net_log_return"] < metrics["gross_log_return"]
    assert "rmse" not in metrics


def test_disabled_signal_policy_blocks_simulation() -> None:
    import pytest

    pred = pd.DataFrame({"prediction": [0.1], "actual": [0.02]})
    policy = {"enabled": False, "type": "prediction_sign"}
    simulation = {
        "enabled": True,
        "cost_model": {"type": "turnover_bps", "turnover_bps": 2.0},
    }
    with pytest.raises(RuntimeError, match="signal policy is disabled"):
        simulate_forecasts(pred, policy, simulation)


def test_backtest_cli_alias_is_available() -> None:
    from commodity.cli import build_parser

    args = build_parser().parse_args([
        "backtest", "--predictions", "predictions.csv", "--output", "out",
    ])
    assert args.func.__name__ == "_simulate"


def test_run_baseline_cli_choices_follow_model_config(monkeypatch) -> None:
    import copy

    from commodity import cli

    cfg = copy.deepcopy(cli.model_config())
    cfg["models"]["naive_alias"] = {
        "kind": "baseline",
        "enabled": True,
        "family": "linear_baseline",
        "architecture": "zero_return",
        "baseline_implementation": "zero_return",
    }
    monkeypatch.setattr(cli, "model_config", lambda: cfg)
    args = cli.build_parser().parse_args(["run-baseline", "--model", "naive_alias"])
    assert args.model == "naive_alias"


def test_backtest_cli_labels_default_output_noncanonical(tmp_path) -> None:
    import json

    from commodity.cli import build_parser

    predictions = tmp_path / "predictions.csv"
    pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02"],
        "prediction": [0.1, -0.1],
        "actual": [0.02, -0.01],
    }).to_csv(predictions, index=False)
    output = tmp_path / "backtest"
    args = build_parser().parse_args([
        "backtest", "--predictions", str(predictions), "--output", str(output),
    ])
    args.func(args)
    report = json.loads((output / "simulation_metrics.json").read_text(encoding="utf-8"))
    assert report["canonical_evidence"] is False
    assert report["evidence_tier"] == "research_noncanonical"


def test_asof_features_respect_release_time() -> None:
    from commodity.features import asof_join_available

    idx = pd.DatetimeIndex(["2026-01-01T20:00Z", "2026-01-02T20:00Z"])
    market = pd.DataFrame({"ret": [0.0, 0.1]}, index=idx)
    exog = pd.DataFrame({
        "available_at": pd.to_datetime(["2026-01-02T12:00Z"], utc=True),
        "storage_surprise": [7.0],
    })
    joined = asof_join_available(market, exog, ["storage_surprise"])
    assert pd.isna(joined.iloc[0]["storage_surprise"])
    assert joined.iloc[1]["storage_surprise"] == 7.0


def test_canonical_experiment_record_matches_shared_schema(tmp_path) -> None:
    import json

    from jsonschema import Draft202012Validator

    from commodity.config import REPO_ROOT
    from commodity.records import build_baseline_record

    source = tmp_path / "ng.csv"
    source.write_text("date,open,high,low,close,volume\n", encoding="utf-8")
    source.with_suffix(".meta.json").write_text(json.dumps({
        "sha256": "a" * 64, "fetched_at_utc": "2026-01-01T00:00:00+00:00",
        "requested_start": "2025-01-01", "requested_end": "2026-01-01",
    }), encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "predictions.csv").write_text("date,prediction,actual\n", encoding="utf-8")
    (run_dir / "metrics.json").write_text("{}", encoding="utf-8")
    idx = pd.date_range("2025-01-01", periods=40, freq="D", tz="UTC")
    metrics = {"rmse": 1.0, "mae": 1.0, "n": 10.0}
    record = build_baseline_record(source, run_dir, "naive", metrics, idx, 30)
    schema_path = REPO_ROOT / "contracts/experiment.schema.json"
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(record)
    assert record["datasets"][0]["vintage"].startswith("retrieval_snapshot:")
    code = record["lineage"]["code_revision"]
    assert {"commit_sha", "working_tree_dirty", "working_tree_diff_sha256"} == set(code)


def test_baseline_record_model_identity_comes_from_config(tmp_path, monkeypatch) -> None:
    import json

    from commodity import records

    source = tmp_path / "ng.csv"
    source.write_text("date,open,high,low,close,volume\n", encoding="utf-8")
    source.with_suffix(".meta.json").write_text(json.dumps({
        "sha256": "b" * 64,
        "fetched_at_utc": "2026-01-01T00:00:00+00:00",
    }), encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "predictions.csv").write_text("date,prediction,actual\n", encoding="utf-8")
    (run_dir / "metrics.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(records, "model_config", lambda: {"models": {"alias": {
        "family": "configured_family",
        "architecture": "configured_architecture",
    }}})
    idx = pd.date_range("2025-01-01", periods=40, freq="D", tz="UTC")
    record = records.build_baseline_record(
        source, run_dir, "alias", {"rmse": 1.0}, idx, 30
    )
    assert record["model"]["family"] == "configured_family"
    assert record["model"]["architecture"] == "configured_architecture"


def test_freeze_v1_dataset_cli_is_available() -> None:
    from commodity.cli import build_parser

    args = build_parser().parse_args(["freeze-v1-dataset"])
    assert args.func.__name__ == "_freeze_v1_dataset"


def test_run_tournament_cli_is_available() -> None:
    from commodity.cli import build_parser

    args = build_parser().parse_args(["run-tournament"])
    assert args.func.__name__ == "_run_tournament"


def test_run_tournament_requires_frozen_dataset_manifest(tmp_path) -> None:
    import pytest

    from commodity.cli import build_parser

    dataset = tmp_path / "pit.csv"
    pd.DataFrame({
        "prediction_time": pd.date_range("2025-01-01", periods=30, tz="UTC"),
        "ret_1": np.linspace(-0.01, 0.01, 30),
        "target_ret_1": np.linspace(0.01, -0.01, 30),
    }).to_csv(dataset, index=False)
    args = build_parser().parse_args([
        "run-tournament", "--input", str(dataset), "--initial-train", "20",
        "--output", str(tmp_path / "out"),
    ])
    with pytest.raises(ValueError, match="manifest"):
        args.func(args)


def test_fetch_canonical_market_cli_is_available() -> None:
    from commodity.cli import build_parser

    args = build_parser().parse_args([
        "fetch-canonical-market", "--start", "2025-01-01", "--end", "2025-01-31",
    ])
    assert args.func.__name__ == "_fetch_canonical_market"


def test_fetch_canonical_market_cli_rejects_product_override(capsys) -> None:
    import pytest

    from commodity.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "fetch-canonical-market", "--start", "2025-01-01", "--end", "2025-01-31",
            "--product-code", "GC",
        ])


    assert "unrecognized arguments: --product-code GC" in capsys.readouterr().err


def test_doctor_reports_canonical_readiness_layers(monkeypatch, capsys) -> None:
    import copy
    import json

    from commodity import cli
    from commodity.config import assumptions_config, data_config

    data = copy.deepcopy(data_config())
    assumptions = copy.deepcopy(assumptions_config())
    source = data["sources"]["market_canonical"]
    source["backtest_evidence_allowed"] = False
    source["non_display_backtesting_rights_verified"] = False
    monkeypatch.setattr(cli, "data_config", lambda: data)
    monkeypatch.setattr(cli, "assumptions_config", lambda: assumptions)
    cli._doctor(None)
    report = json.loads(capsys.readouterr().out)
    assert report["canonical_source_history_ready"] is True
    assert report["canonical_roll_method_ready"] is True
    assert report["canonical_licensing_ready"] is False
    assert report["canonical_market_evidence_allowed"] is False
    assert "non-display/backtesting rights" in report["canonical_market_evidence_reason"]
