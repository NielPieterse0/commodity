import importlib.util
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).parents[1] / "scripts" / "replicate_natural_gas_market_findings_285.py"
spec = importlib.util.spec_from_file_location("replicate_285", SCRIPT)
replicate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(replicate)


def test_infer_delivery_supports_pre_and_post_symbology_change():
    old = replicate.infer_delivery("NGX2", pd.Timestamp("2012-01-02", tz="UTC"))
    new = replicate.infer_delivery("NGG26", pd.Timestamp("2026-01-02", tz="UTC"))
    assert old == pd.Timestamp("2012-11-01", tz="UTC")
    assert new == pd.Timestamp("2026-02-01", tz="UTC")


def test_infer_delivery_rejects_spreads_and_far_contracts():
    day = pd.Timestamp("2012-01-02", tz="UTC")
    assert replicate.infer_delivery("NGG2-NGH2", day) is None
    assert replicate.infer_delivery("NGZ3", day) is None


def test_returns_are_computed_by_contract_before_rank():
    bars = pd.DataFrame({
        "ts_event": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"], utc=True),
        "contract": ["NG-2024-02", "NG-2024-03", "NG-2024-02", "NG-2024-03"],
        "delivery": pd.to_datetime(["2024-02-01", "2024-03-01", "2024-02-01", "2024-03-01"], utc=True),
        "close": [2.0, 3.0, 2.2, 2.7],
    })
    out = replicate.attach_contract_returns_and_rank(bars)
    second_day = out[out["ts_event"] == pd.Timestamp("2024-01-02", tz="UTC")].sort_values("rank")
    assert second_day["rank"].tolist() == [1, 2]
    assert second_day["log_return"].round(10).tolist() == [0.0953101798, -0.1053605157]


def test_committed_replication_covers_full_owned_history_and_expected_directions():
    result_path = Path(__file__).parents[1] / "artifacts" / "natural-gas-market-replication-285" / "result.json"
    import json
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["date_start"].startswith("2010-06-06")
    assert result["date_end"].startswith("2026-08-12")
    assert result["unique_dates"] == 5025
    assert result["data_semantics"].endswith("not official settlement")
    assert result["samuelson_effect"]["expected_direction_pass"] is True
    assert result["samuelson_effect"]["cross_era_direction_pass"] is True
    assert result["seasonal_term_structure"]["expected_direction_pass"] is True


def test_confirmatory_successor_design_freeze_binds_spec_and_blocks_execution():
    import hashlib
    import json

    root = Path(__file__).parents[1]
    base = root / "research" / "confirmatory-specifications" / "natural-gas-samuelson-confirmation-285-v1"
    spec_path = base / "spec.json"
    freeze = json.loads((base / "freeze.json").read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(spec_path.read_bytes()).hexdigest() == freeze["spec_sha256"]
    assert freeze["frozen"] is True
    assert freeze["execution_authorized"] is False
    assert freeze["future_preregistration_required"] is True
    assert freeze["sealed_window_registration_required"] is True
    assert spec["untouched_confirmation_allocation"]["required_eligible_dates"] == 504
    assert spec["power"]["detectable_effect"] <= spec["power"]["minimum_effect"]
