from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research" / "derive_phase7_prospective_decision.py"


def _module():
    spec = importlib.util.spec_from_file_location("phase7_prospective_derivation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _training(module) -> pd.DataFrame:
    features = module.frozen_feature_columns()
    rows = []
    for index in range(30):
        row = {name: float(index + offset + 1) / 100.0 for offset, name in enumerate(features)}
        row.update({
            "target_path_move_per_mmbtu": -0.05,
            "target_end_timestamp": pd.Timestamp("2022-01-01", tz="UTC") + pd.Timedelta(days=index),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def _bundle(module) -> dict[str, object]:
    features = {
        name: float(index + 2) / 50.0
        for index, name in enumerate(module.frozen_feature_columns())
    }
    models = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))["models"]
    timesfm = models["timesfm_2_5"]
    kronos = models["kronos_base"]
    return {
        "schema_version": 1,
        "decision_timestamp": "2026-09-14T00:00:01Z",
        "planned_fill_timestamp": "2026-09-15T00:00:00Z",
        "target_session_timestamps": [
            "2026-09-16T00:00:00Z",
            "2026-09-17T00:00:00Z",
            "2026-09-18T00:00:00Z",
            "2026-09-21T00:00:00Z",
            "2026-09-22T00:00:00Z",
        ],
        "current_origin": {
            "trade_date": "2026-09-13T00:00:00Z",
            "available_at": "2026-09-13T23:59:00Z",
            "contract_id": "NGX6",
            "features": features,
        },
        "specialists": {
            "prediction_time": "2026-09-13T23:59:00Z",
            "timesfm_point_return": -0.01,
            "timesfm_interval_width": 0.04,
            "timesfm_model_id": timesfm["model_id"],
            "timesfm_model_revision": timesfm["model_revision"],
            "timesfm_checkpoint_sha256": timesfm["checkpoint_artifacts"]["model"]["sha256"],
            "kronos_close_return": -0.02,
            "kronos_terminal_return": 0.03,
            "kronos_path_generated": True,
            "kronos_model_id": kronos["model_id"],
            "kronos_model_revision": kronos["model_revision"],
            "kronos_model_checkpoint_sha256": kronos["checkpoint_artifacts"]["model"]["sha256"],
            "kronos_tokenizer_revision": kronos["tokenizer_revision"],
            "kronos_tokenizer_checkpoint_sha256": kronos["checkpoint_artifacts"]["tokenizer"]["sha256"],
            "kronos_inference_profile": "upstream_usage_defaults",
        },
        "source_snapshot": {
            "sha256": "a" * 64,
            "latest_trade_date": "2026-09-13",
            "complete": True,
        },
    }


def test_decision_outputs_are_derived_not_caller_supplied() -> None:
    module = _module()
    bundle = _bundle(module)
    bundle["predicted_gross_pnl_usd"] = 999999.0
    with pytest.raises(module.DecisionDerivationError, match="caller-supplied decision output"):
        module.derive_decision(bundle, training_origins=_training(module))


def test_frozen_baseline_and_specialists_derive_intended_position() -> None:
    module = _module()
    record = module.derive_decision(_bundle(module), training_origins=_training(module))
    assert record["candidate_config_id"] == "s-veto__l-none__p-half__u-none"
    assert record["predicted_gross_pnl_usd"] == pytest.approx(-500.0, abs=1e-6)
    assert record["baseline_position"] == -1.0
    assert record["intended_position"] == -0.5
    assert record["policy_modifiers"] == ["kronos_path_half"]
    assert record["target_end_timestamp"] == "2026-09-22T00:00:00+00:00"
    assert record["forecast_id"]
    assert record["decision_input_snapshot"]["current_origin"]["contract_id"] == "NGX6"
    assert record["input_snapshot_sha256"] == module._json_sha256(record["decision_input_snapshot"])


def test_short_side_timesfm_veto_is_derived() -> None:
    module = _module()
    bundle = _bundle(module)
    bundle["specialists"]["timesfm_point_return"] = 0.01
    record = module.derive_decision(bundle, training_origins=_training(module))
    assert record["baseline_position"] == -1.0
    assert record["intended_position"] == 0.0
    assert record["policy_modifiers"] == ["timesfm_short_veto"]
    assert record["skip_reason"] == "specialist_veto"


def test_bundle_rejects_realized_or_outcome_fields() -> None:
    module = _module()
    bundle = _bundle(module)
    bundle["net_pnl_usd"] = 10.0
    with pytest.raises(module.DecisionDerivationError, match="outcome field"):
        module.derive_decision(bundle, training_origins=_training(module))


def test_training_targets_are_locked_to_pre_2023() -> None:
    module = _module()
    training = _training(module)
    training.loc[0, "target_end_timestamp"] = pd.Timestamp("2023-01-01", tz="UTC")
    with pytest.raises(module.DecisionDerivationError, match="2022"):
        module.derive_decision(_bundle(module), training_origins=training)


def test_horizon_is_exactly_five_future_sessions() -> None:
    module = _module()
    bundle = _bundle(module)
    bundle["target_session_timestamps"] = bundle["target_session_timestamps"][:-1]
    with pytest.raises(module.DecisionDerivationError, match="five"):
        module.derive_decision(bundle, training_origins=_training(module))


def test_decision_must_precede_planned_fill() -> None:
    module = _module()
    bundle = _bundle(module)
    bundle["planned_fill_timestamp"] = bundle["decision_timestamp"]
    with pytest.raises(module.DecisionDerivationError, match="planned fill"):
        module.derive_decision(bundle, training_origins=_training(module))


def test_stale_databento_archive_preflight_fails_without_opening_data(tmp_path: Path) -> None:
    module = _module()
    folder = tmp_path / "ohlcv-1d" / "job"
    folder.mkdir(parents=True)
    (folder / "glbx-mdp3-20260101-20260812.ohlcv-1d.dbn.zst").write_bytes(b"sealed")
    result = module.preflight_databento_freshness(
        tmp_path,
        required_trade_date=pd.Timestamp("2026-09-13", tz="UTC"),
    )
    assert result["fresh"] is False
    assert result["latest_trade_date"] == "2026-08-12"
    assert result["reason"] == "prospective_market_source_stale"


def test_kronos_path_cadence_is_exactly_eight_of_109() -> None:
    module = _module()
    active = [index for index in range(109) if module.prospective_kronos_path_eligible(index)]
    assert active == [0, 13, 27, 40, 54, 68, 81, 95]
    assert len(active) == 8
    assert module.prospective_kronos_path_eligible(109) is True


def test_inactive_kronos_path_origin_is_neutral() -> None:
    module = _module()
    bundle = _bundle(module)
    bundle["specialists"]["kronos_path_generated"] = False
    bundle["specialists"]["kronos_terminal_return"] = None
    record = module.derive_decision(
        bundle,
        training_origins=_training(module),
        origin_sequence_index=1,
    )
    assert record["prospective_origin_index"] == 1
    assert record["kronos_path_eligible"] is False
    assert record["intended_position"] == -1.0
    assert record["policy_modifiers"] == []


def test_kronos_path_generation_must_match_frozen_cadence() -> None:
    module = _module()
    bundle = _bundle(module)
    with pytest.raises(module.DecisionDerivationError, match="preregistered cadence"):
        module.derive_decision(
            bundle,
            training_origins=_training(module),
            origin_sequence_index=1,
        )


def test_specialist_model_identity_is_pinned() -> None:
    module = _module()
    bundle = _bundle(module)
    bundle["specialists"]["timesfm_model_revision"] = "drifted"
    with pytest.raises(module.DecisionDerivationError, match="identity mismatch"):
        module.derive_decision(bundle, training_origins=_training(module))


def _write_databento_partition(
    root: Path, schema: str, *, start: str = "20260901", end: str = "20260930"
) -> Path:
    folder = root / schema / "job"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"glbx-mdp3-{start}-{end}.{schema}.dbn.zst"
    path.write_bytes(f"{schema}:{start}:{end}".encode("ascii"))
    return path


def test_verified_databento_source_snapshot_binds_exact_complete_triple(tmp_path: Path) -> None:
    module = _module()
    for schema in ("definition", "statistics", "ohlcv-1d"):
        _write_databento_partition(tmp_path, schema)
    snapshot = module.verified_databento_source_snapshot(
        tmp_path,
        required_trade_date=pd.Timestamp("2026-09-13", tz="UTC"),
    )
    assert snapshot["complete"] is True
    assert snapshot["latest_trade_date"] == "2026-09-30"
    assert snapshot["sha256"] == module._json_sha256(snapshot["manifest"])
    assert [item["schema"] for item in snapshot["manifest"]["files"]] == [
        "definition",
        "statistics",
        "ohlcv-1d",
    ]
    assert all(len(item["sha256"]) == 64 for item in snapshot["manifest"]["files"])


def test_verified_databento_source_snapshot_rejects_incomplete_triple(tmp_path: Path) -> None:
    module = _module()
    _write_databento_partition(tmp_path, "definition")
    _write_databento_partition(tmp_path, "ohlcv-1d")
    with pytest.raises(module.DecisionDerivationError, match="statistics source is missing"):
        module.verified_databento_source_snapshot(
            tmp_path,
            required_trade_date=pd.Timestamp("2026-09-13", tz="UTC"),
        )
