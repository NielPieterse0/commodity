import numpy as np
import pandas as pd
import pytest

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
    initial_train = 30
    base = walk_forward_predict(
        lambda: RidgeReturnModel(1.0), x, y, initial_train=initial_train, retrain_every=1
    )
    for boundary in (31, 45, 60, 79):
        mutated = y.copy()
        mutated.iloc[boundary:] = mutated.iloc[boundary:] + 999.0
        changed = walk_forward_predict(
            lambda: RidgeReturnModel(1.0),
            x,
            mutated,
            initial_train=initial_train,
            retrain_every=1,
        )
        protected_predictions = boundary - initial_train + 1
        np.testing.assert_allclose(
            base["prediction"].iloc[:protected_predictions],
            changed["prediction"].iloc[:protected_predictions],
            rtol=0.0,
            atol=0.0,
        )


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


def test_walk_forward_rejects_misaligned_feature_and_target_indexes() -> None:
    import pytest

    x, y = _sample_xy()
    shifted = y.copy()
    shifted.index = shifted.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="indexes must match"):
        walk_forward_predict(ZeroReturnModel, x, shifted, initial_train=30)


def test_walk_forward_rejects_nonchronological_inputs() -> None:
    import pytest

    x, y = _sample_xy()
    order = list(range(len(x)))
    order[40], order[41] = order[41], order[40]
    shuffled_x = x.iloc[order]
    shuffled_y = y.iloc[order]
    with pytest.raises(ValueError, match="chronological and unique"):
        walk_forward_predict(ZeroReturnModel, shuffled_x, shuffled_y, initial_train=30)


def test_forecast_metrics_exclude_strategy_and_execution_fields() -> None:
    x, y = _sample_xy()
    pred = walk_forward_predict(ZeroReturnModel, x, y, initial_train=30)
    metrics = evaluate_predictions(pred)
    assert metrics["n"] == 50.0
    assert metrics["prediction_actual_corr"] is None
    assert "net_log_return" not in metrics
    assert "cost_bps" not in metrics


def test_forecast_metrics_preserve_defined_correlation() -> None:
    pred = pd.DataFrame({"prediction": [1.0, 2.0, 3.0], "actual": [2.0, 4.0, 6.0]})
    metrics = evaluate_predictions(pred)
    assert metrics["prediction_actual_corr"] == pytest.approx(1.0)


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
    from commodity.availability import asof_join_point_in_time

    cutoffs = pd.DataFrame({
        "prediction_time": pd.to_datetime(
            ["2026-01-01T20:00Z", "2026-01-02T20:00Z"], utc=True
        )
    })
    exog = pd.DataFrame({
        "available_at": pd.to_datetime(["2026-01-02T12:00Z"], utc=True),
        "availability_status": ["reconstructed_conservative"],
        "revision_status": ["point_in_time"],
        "storage_surprise": [7.0],
    })
    joined = asof_join_point_in_time(
        cutoffs,
        exog,
        ["storage_surprise"],
        mode="research_pit",
        source_group_columns=(),
    )
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


def test_run_tournament_writes_schema_valid_experiment_records(tmp_path) -> None:
    import json

    from jsonschema import Draft202012Validator

    from commodity.cli import build_parser
    from commodity.config import REPO_ROOT
    from commodity.provenance import sha256_file

    n = 200
    index = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    dataset = tmp_path / "pit.csv"
    ret = np.sin(np.arange(n) / 3.0) / 100
    pd.DataFrame(
        {
            "prediction_time": index,
            "ret_1": ret,
            "vol_5": 0.02 + np.cos(np.arange(n) / 7.0) / 1000,
            "target_ret_1": np.roll(ret, -1),
        }
    ).to_csv(dataset, index=False)
    digest = sha256_file(dataset)
    dataset.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": "pit-cli-test",
                "dataset_sha256": digest,
                "artifact_sha256": digest,
                "completeness": "pit_core",
                "missing_feature_families": ["weather"],
                "evidence_mode": "research_pit",
                "market_evaluation_evidence": False,
                "canonical_market_evidence": False,
                "research_evaluation_eligible": False,
                "research_promotion_eligible": False,
                "end": index[-1].isoformat(),
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "tournament"
    args = build_parser().parse_args(
        [
            "run-tournament",
            "--input",
            str(dataset),
            "--initial-train",
            "30",
            "--retrain-every",
            "5",
            "--output",
            str(output),
        ]
    )
    args.func(args)

    summary_text = (output / "summary.json").read_text(encoding="utf-8")
    assert "NaN" not in summary_text
    tournament_summary = json.loads(summary_text)
    assert tournament_summary["evidence_mode"] == "research_pit"
    assert tournament_summary["canonical_market_evidence"] is False
    assert tournament_summary["research_evaluation_eligible"] is False
    assert tournament_summary["research_promotion_eligible"] is False
    naive_summary = next(row for row in tournament_summary["ranking"] if row["model"] == "naive")
    assert naive_summary["prediction_actual_corr"] is None

    schema_path = REPO_ROOT / "contracts" / "experiment.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for model_name in ("naive", "ridge", "hist_gb"):
        record_path = output / model_name / "experiment.json"
        assert record_path.is_file()
        record_text = record_path.read_text(encoding="utf-8")
        assert "NaN" not in record_text
        record = json.loads(record_text)
        validator.validate(record)
        assert record["controls"]["leakage_check"] == "passed"
        assert record["results"]["significance"] is not None
        if model_name == "naive":
            assert record["evaluation"]["metrics"]["prediction_actual_corr"] is None
