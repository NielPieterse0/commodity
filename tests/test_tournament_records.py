import hashlib
import json
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator


def test_tournament_record_is_schema_valid_and_carries_controls(tmp_path: Path) -> None:
    from commodity.records import build_tournament_record

    dataset_path = tmp_path / "dataset.csv"
    dataset_path.write_text("prediction_time,a,target_ret_1\n", encoding="utf-8")
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    manifest = {
        "dataset_id": "pit-test",
        "dataset_sha256": digest,
        "artifact_sha256": digest,
        "end": "2026-08-12T00:00:00+00:00",
    }
    model_dir = tmp_path / "ridge"
    model_dir.mkdir()
    (model_dir / "predictions.csv").write_text("date,prediction,actual\n", encoding="utf-8")
    (model_dir / "metrics.json").write_text("{}", encoding="utf-8")
    index = pd.date_range("2026-01-01", periods=40, freq="D", tz="UTC")
    significance = {
        "method": "moving_block_bootstrap",
        "rmse_improvement": 0.001,
        "ci_lower": -0.001,
        "ci_upper": 0.002,
        "p_value": 0.2,
        "significant": False,
        "block_size": 10,
        "resamples": 200,
    }
    record = build_tournament_record(
        dataset_manifest=manifest,
        dataset_path=dataset_path,
        model_dir=model_dir,
        model_name="ridge",
        metrics={"rmse": 0.1, "mae": 0.08, "n": 10.0},
        feature_index=index,
        initial_train=30,
        significance=significance,
        leakage_check="passed",
    )
    schema_path = Path(__file__).resolve().parents[1] / "contracts" / "experiment.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(record)
    assert record["controls"]["leakage_check"] == "passed"
    assert record["results"]["significance"]["p_value"] == 0.2
