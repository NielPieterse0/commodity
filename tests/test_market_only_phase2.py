from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from commodity.config import config_path
from commodity.market_only_phase2 import (
    Phase2MarketOnlyError,
    _archive_parts,
    _build_executable_selected_path,
    _canonicalize_one_origin_per_fill,
    _preflight_evaluation_capacity,
    _validate_executable_selected,
    forecast_candidate_window,
    select_best_candidate,
    summarize_ledger,
    validate_phase2_config,
)
from commodity.phase2_runtime import (
    Phase2CheckpointStore,
    Phase2RuntimeError,
    Phase2Telemetry,
)


def _origins(rows: int = 48) -> pd.DataFrame:
    fills = pd.date_range("2013-01-02", periods=rows, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "trade_date": fills - pd.Timedelta(days=1),
            "signal_timestamp": fills - pd.Timedelta(hours=4),
            "fill_trade_date": fills,
            "fill_timestamp": fills,
            "fill_contract_id": "NGX",
            "target_end_timestamp": fills + pd.Timedelta(days=5),
            "target_path_move_per_mmbtu": np.linspace(-0.2, 0.3, rows),
            "feature_ret_1": np.linspace(-0.05, 0.05, rows),
            "feature_vol_20": np.linspace(0.01, 0.08, rows),
        }
    )


def test_forecast_candidate_window_is_isolated_from_evaluation_outcomes() -> None:
    origins = _origins()
    start = pd.Timestamp(origins.iloc[30]["fill_timestamp"])
    boundary = pd.Timestamp(origins.iloc[45]["fill_timestamp"])
    candidate = {
        "id": "ridge-test",
        "model": "ridge",
        "parameters": {"alpha": 10.0},
    }
    first = forecast_candidate_window(
        origins,
        candidate,
        ["feature_ret_1", "feature_vol_20"],
        start_timestamp=start,
        boundary_timestamp=boundary,
        contract_multiplier=10_000.0,
        min_train_rows=20,
        horizon_sessions=5,
    )
    changed = origins.copy()
    changed.loc[changed["fill_timestamp"] >= start, "target_path_move_per_mmbtu"] += (
        1000.0
    )
    second = forecast_candidate_window(
        changed,
        candidate,
        ["feature_ret_1", "feature_vol_20"],
        start_timestamp=start,
        boundary_timestamp=boundary,
        contract_multiplier=10_000.0,
        min_train_rows=20,
        horizon_sessions=5,
    )
    assert first["prediction"].tolist() == pytest.approx(second["prediction"].tolist())
    assert (first["latest_training_target_end"] < start).all()
    assert (first["target_end_timestamp"] < boundary).all()


def test_origin_canonicalization_keeps_latest_equivalent_signal_per_fill() -> None:
    origins = _origins(12)
    duplicate = origins.iloc[[5]].copy()
    duplicate["trade_date"] = duplicate["trade_date"] - pd.Timedelta(days=1)
    duplicate["signal_timestamp"] = duplicate["signal_timestamp"] - pd.Timedelta(hours=6)
    combined = pd.concat([origins, duplicate], ignore_index=True)

    canonical, stats = _canonicalize_one_origin_per_fill(combined)

    assert len(canonical) == len(origins)
    assert stats == {"input_origins": 13, "output_origins": 12, "collapsed": 1}
    kept = canonical.loc[
        canonical["fill_timestamp"] == origins.iloc[5]["fill_timestamp"]
    ].iloc[0]
    assert kept["signal_timestamp"] == origins.iloc[5]["signal_timestamp"]


def test_origin_canonicalization_rejects_conflicting_duplicate_target() -> None:
    origins = _origins(12)
    duplicate = origins.iloc[[5]].copy()
    duplicate["signal_timestamp"] = duplicate["signal_timestamp"] - pd.Timedelta(hours=1)
    duplicate["target_path_move_per_mmbtu"] += 1.0
    combined = pd.concat([origins, duplicate], ignore_index=True)

    with pytest.raises(Phase2MarketOnlyError, match="disagree on target value"):
        _canonicalize_one_origin_per_fill(combined)


def test_preflight_rejects_insufficient_capacity_before_model_fit() -> None:
    origins = _origins(60)
    path = pd.DataFrame(
        {
            "trade_date": origins["fill_trade_date"],
            "session_open": origins["fill_timestamp"],
        }
    )
    cfg = {
        "execution_contract": {"minimum_training_rows": 1000},
        "feature_sets": {"core": ["feature_ret_1", "feature_vol_20"]},
        "candidates": [
            {"id": "ridge", "model": "ridge", "feature_set": "core"}
        ],
        "validation": {
            "earliest_inner_validation_start": "2013-02-01",
            "inner_validation_block_months": 1,
            "outer_blocks": [
                {"id": "outer", "start": "2013-03-01", "end": "2013-03-29"}
            ],
        },
    }

    with pytest.raises(Phase2MarketOnlyError, match="preflight eliminated every candidate"):
        _preflight_evaluation_capacity(origins, path, cfg)


def test_select_best_candidate_uses_frozen_tie_breakers() -> None:
    rows = [
        {
            "candidate_id": "b",
            "net_pnl_usd": 10.0,
            "transaction_cost_usd": 4.0,
            "simplicity_rank": 1,
        },
        {
            "candidate_id": "a",
            "net_pnl_usd": 10.0,
            "transaction_cost_usd": 3.0,
            "simplicity_rank": 3,
        },
        {
            "candidate_id": "c",
            "net_pnl_usd": 10.0,
            "transaction_cost_usd": 3.0,
            "simplicity_rank": 2,
        },
        {
            "candidate_id": "d",
            "net_pnl_usd": 10.0,
            "transaction_cost_usd": 3.0,
            "simplicity_rank": 2,
        },
    ]
    assert select_best_candidate(rows)["candidate_id"] == "c"


def test_phase2_config_rejects_post_2022_evidence() -> None:
    cfg = {
        "evidence_boundary": {
            "last_allowed_trade_date": "2023-01-01",
            "protected_confirmation_accessed": False,
        },
        "execution_contract": {"horizon_sessions": 5},
        "candidates": [{"id": "zero", "model": "zero", "feature_set": "core"}],
        "feature_sets": {"core": ["feature_ret_1"]},
        "validation": {"outer_blocks": []},
    }
    with pytest.raises(Phase2MarketOnlyError, match="2022-12-31"):
        validate_phase2_config(cfg)
    protected = copy.deepcopy(cfg)
    protected["evidence_boundary"]["last_allowed_trade_date"] = "2022-12-31"
    protected["evidence_boundary"]["protected_confirmation_accessed"] = True
    with pytest.raises(Phase2MarketOnlyError, match="protected"):
        validate_phase2_config(protected)


def test_summarize_ledger_separates_long_and_short() -> None:
    ledger = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2020-01-02", "2020-01-03", "2020-01-06"], utc=True
            ),
            "target_position": [1, -1, 0],
            "gross_pnl_usd": [100.0, 50.0, 0.0],
            "transaction_cost_usd": [30.0, 60.0, 30.0],
            "net_pnl_usd": [70.0, -10.0, -30.0],
            "equity_usd": [100070.0, 100060.0, 100030.0],
            "drawdown_fraction": [0.0, 0.0001, 0.0004],
            "execution_side_count": [1, 2, 1],
        }
    )
    summary = summarize_ledger(ledger, starting_capital_usd=100_000.0)
    assert summary["long"]["net_pnl_usd"] == pytest.approx(70.0)
    assert summary["short"]["net_pnl_usd"] == pytest.approx(-10.0)
    assert summary["flat"]["net_pnl_usd"] == pytest.approx(-30.0)
    assert summary["net_pnl_usd"] == pytest.approx(30.0)


def test_executable_selection_waits_for_strictly_later_utc_interval() -> None:
    trade_dates = pd.to_datetime(
        ["2022-01-03", "2022-01-04", "2022-01-05", "2022-01-06"], utc=True
    )
    selected_raw = pd.DataFrame(
        {
            "trade_date": trade_dates,
            "contract_id": ["NGA"] * 4,
            "expiration": pd.to_datetime(["2022-02-01"] * 4, utc=True),
            "roll_reason": ["initial", "hold", "hold", "hold"],
            "available_at": trade_dates + pd.Timedelta(hours=23, minutes=59),
        }
    )
    execution_bars = pd.DataFrame(
        {
            "trade_date": trade_dates,
            "contract_id": ["NGA"] * 4,
            "open": [3.8, 3.9, 4.0, 4.1],
        }
    )
    selected = _build_executable_selected_path(selected_raw, execution_bars)
    row = selected.loc[
        selected["trade_date"] == pd.Timestamp("2022-01-04", tz="UTC")
    ].iloc[0]
    assert row["selection_source_trade_date"] == pd.Timestamp("2022-01-03", tz="UTC")
    assert row["available_at"] == pd.Timestamp("2022-01-03T23:59:00Z")
    assert row["session_open"] == pd.Timestamp("2022-01-04T00:00:00Z")
    assert row["available_at"] < row["session_open"]


def test_executable_selection_rejects_same_boundary_information() -> None:
    selected_raw = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-01-03", "2022-01-04"], utc=True),
            "contract_id": ["NGA", "NGB"],
            "expiration": pd.to_datetime(["2022-02-01", "2022-03-01"], utc=True),
            "roll_reason": ["initial", "volume_crossover"],
            "available_at": pd.to_datetime(
                ["2022-01-04T00:00:00Z", "2022-01-04T23:59:00Z"], utc=True
            ),
        }
    )
    execution_bars = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2022-01-04", "2022-01-05", "2022-01-05"], utc=True
            ),
            "contract_id": ["NGA", "NGA", "NGB"],
            "open": [3.8, 3.9, 4.0],
        }
    )
    selected = _build_executable_selected_path(selected_raw, execution_bars)
    assert pd.Timestamp("2022-01-04", tz="UTC") not in set(selected["trade_date"])
    row = selected.loc[
        selected["trade_date"] == pd.Timestamp("2022-01-05", tz="UTC")
    ].iloc[0]
    assert row["contract_id"] == "NGB"
    assert row["available_at"] < row["session_open"]


def test_executable_selection_breaks_segment_when_roll_cannot_be_priced() -> None:
    selected_raw = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-01-03", "2022-01-04"], utc=True),
            "contract_id": ["NGA", "NGB"],
            "expiration": pd.to_datetime(["2022-02-01", "2022-03-01"], utc=True),
            "roll_reason": ["initial", "volume_crossover"],
            "available_at": pd.to_datetime(
                ["2022-01-03T23:59:00Z", "2022-01-04T23:59:00Z"], utc=True
            ),
        }
    )
    execution_bars = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                [
                    "2022-01-04",
                    "2022-01-05",
                    "2022-01-06",
                    "2022-01-06",
                ],
                utc=True,
            ),
            "contract_id": ["NGA", "NGB", "NGA", "NGB"],
            "open": [3.8, 4.0, 3.9, 4.1],
        }
    )
    selected = _build_executable_selected_path(selected_raw, execution_bars)
    assert selected["trade_date"].tolist() == [
        pd.Timestamp("2022-01-04", tz="UTC"),
        pd.Timestamp("2022-01-05", tz="UTC"),
        pd.Timestamp("2022-01-06", tz="UTC"),
    ]
    assert selected["contract_id"].tolist() == ["NGA", "NGB", "NGB"]
    assert selected["segment_id"].tolist() == [1, 2, 2]
    _validate_executable_selected(selected, execution_bars)


def test_phase2_config_freezes_amended_utc_execution_clock() -> None:
    cfg = json.loads(config_path("phase2_market_only.json").read_text(encoding="utf-8"))
    validate_phase2_config(cfg)
    changed = copy.deepcopy(cfg)
    changed["execution_contract"]["execution_open_schema"] = "ohlcv-1m"
    with pytest.raises(Phase2MarketOnlyError, match="ohlcv-1d"):
        validate_phase2_config(changed)
    changed = copy.deepcopy(cfg)
    changed["execution_contract"]["fill_clock"] = "session_open"
    with pytest.raises(Phase2MarketOnlyError, match="strictly later eligible UTC-day"):
        validate_phase2_config(changed)


def test_archive_parts_never_selects_protected_partition(tmp_path) -> None:
    folder = tmp_path / "statistics" / "job"
    folder.mkdir(parents=True)
    allowed = folder / "glbx-mdp3-20220101-20221231.statistics.dbn.zst"
    protected = folder / "glbx-mdp3-20230101-20231231.statistics.dbn.zst"
    allowed.write_bytes(b"allowed")
    protected.write_bytes(b"protected")
    parts = _archive_parts(tmp_path, "statistics", pd.Timestamp("2022-12-31", tz="UTC"))
    assert list(parts) == ["20220101-20221231"]
    assert parts["20220101-20221231"] == allowed


def test_checkpoint_rejects_tampered_frame(tmp_path) -> None:
    telemetry = Phase2Telemetry(None, echo=False)
    store = Phase2CheckpointStore(tmp_path, telemetry)
    frame = pd.DataFrame({"value": [1.0, 2.0]})
    identity = {"input_sha256": "abc", "cache_version": 1}
    store.save_frame("sample", frame, identity)
    loaded = store.load_frame("sample", identity)
    assert loaded is not None
    assert loaded["value"].tolist() == [1.0, 2.0]
    (tmp_path / "sample.parquet").write_bytes(b"tampered")
    assert store.load_frame("sample", identity) is None


def test_checkpoint_scoped_identity_upgrades_only_when_explicitly_allowed(tmp_path) -> None:
    telemetry = Phase2Telemetry(None, echo=False)
    store = Phase2CheckpointStore(tmp_path, telemetry)
    frame = pd.DataFrame({"value": [1.0, 2.0]})
    legacy_identity = {"source_sha256": "abc"}
    context = {"implementation_sha256": "def"}
    store.save_frame("sample", frame, legacy_identity)

    strict = store.scoped_identity(context, allow_legacy_identity=False)
    assert strict.load_frame("sample", legacy_identity) is None

    migration = store.scoped_identity(context, allow_legacy_identity=True)
    loaded = migration.load_frame("sample", legacy_identity)
    assert loaded is not None
    assert loaded["value"].tolist() == [1.0, 2.0]
    assert store.load_frame("sample", {**legacy_identity, **context}) is not None


def test_checkpoint_run_lock_blocks_duplicate_process(tmp_path) -> None:
    telemetry = Phase2Telemetry(None, echo=False)
    first = Phase2CheckpointStore(tmp_path, telemetry)
    second = Phase2CheckpointStore(tmp_path, telemetry)
    with (
        first.run_lock(),
        pytest.raises(Phase2RuntimeError, match="already owns"),
        second.run_lock(),
    ):
        pass
