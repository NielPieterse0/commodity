from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import commodity.cli as cli_module
from commodity.cli import _loaded_module_code_sha256, _write_csv_exclusive, build_parser
from commodity.data_assurance import canonical_json_sha256
from commodity.provenance import sha256_file
from commodity.trading_decision_v0 import (
    DecisionSystemError,
    _decision_origins,
    build_roll_safe_session_path,
    build_walk_forward_forecasts,
    governed_input_authority_identity,
    parse_cost_assumptions,
    parse_input_boundary,
    parse_risk_policy,
    selected_model_forecasts,
    simulate_policy,
)


def _market() -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=14, tz="UTC")
    rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        for contract, base in (("NGA", 3.0), ("NGB", 10.0)):
            rows.append({
                "trade_date": date,
                "contract_id": contract,
                "open": base + i * 0.1,
            })
    return pd.DataFrame(rows)


def _selected() -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=14, tz="UTC")
    rows = []
    for i, date in enumerate(dates):
        contract = "NGA" if i < 7 else "NGB"
        rows.append({
            "trade_date": date,
            "contract_id": contract,
            "available_at": date + pd.Timedelta(hours=13),
            "session_open": date + pd.Timedelta(hours=14, minutes=30),
            "roll_reason": "volume_crossover" if i == 7 else "hold",
        })
    return pd.DataFrame(rows)


def _features() -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=14, tz="UTC")
    return pd.DataFrame({
        "trade_date": dates,
        "available_at": dates + pd.Timedelta(hours=21),
        "feature_curve": [float(i) for i in range(14)],
        "feature_return": [(-1.0) ** i * 0.01 for i in range(14)],
    })


def _costs() -> dict[str, object]:
    return {
        "schema_version": 1,
        "assumption_status": "declared_research_assumption_unverified_broker_terms",
        "commission_usd_per_side": 2.0,
        "exchange_clearing_fees_usd_per_side": 3.0,
        "half_spread_ticks_per_side": 0.5,
        "slippage_ticks_per_side": 0.5,
        "initial_margin_usd_per_contract": 5_000.0,
    }


def _risk() -> dict[str, object]:
    return {
        "capital_usd": 100_000.0,
        "max_standard_contracts": 1,
        "daily_loss_fraction": 0.02,
        "peak_drawdown_kill_fraction": 0.10,
        "after_kill": "remain_flat_until_explicit_operator_restart",
        "live_trading_allowed": False,
        "model_tunable": False,
    }


def _policy_forecast(
    path: pd.DataFrame,
    index: int,
    forecast_id: str,
    predicted_gross_pnl_usd: float,
    *,
    horizon: int = 5,
) -> dict[str, object]:
    return {
        "forecast_id": forecast_id,
        "model_id": "ridge",
        "fill_trade_date": path.iloc[index]["trade_date"],
        "target_end_timestamp": path.iloc[index + horizon - 1]["next_session_open"],
        "predicted_gross_pnl_usd": predicted_gross_pnl_usd,
        "horizon_sessions": horizon,
    }


def _research_ready_assurance() -> dict[str, object]:
    semantic_evidence = {
        "method": "explicit_dataset_semantics_v1",
        "verifier_ref": "tests.synthetic_semantic_verifier",
        "verifier_source_sha256": "a" * 64,
        "checks": {"point_in_time_semantics": True},
    }
    assurance: dict[str, object] = {
        "schema_version": 1,
        "source_inputs": [{"id": "synthetic", "sha256": "b" * 64}],
        "layers": [
            {"name": "reconstruction", "status": "verified", "sha256": "c" * 64},
            {
                "name": "semantic_validation",
                "status": "verified",
                "sha256": canonical_json_sha256(semantic_evidence),
            },
        ],
        "transformation_sha256": {"synthetic": "d" * 64},
        "reconstruction_status": "verified",
        "semantic_status": "verified",
        "verification_method": "deterministic_rebuild_exact_comparison",
        "reconstruction_independence": "same_implementation_repeatability_only",
        "comparison_contract": "rows_columns_timestamps_values_and_canonical_identity",
        "semantic_verification_method": "explicit_dataset_semantics_v1",
        "semantic_evidence": semantic_evidence,
    }
    assurance["assurance_sha256"] = canonical_json_sha256(assurance)
    return assurance


def test_roll_safe_path_excludes_cross_contract_gap() -> None:
    market = _market()
    selected = _selected()
    path = build_roll_safe_session_path(market, selected)
    roll_interval = path.iloc[6]

    assert roll_interval["contract_id"] == "NGA"
    assert roll_interval["next_selected_contract_id"] == "NGB"
    assert roll_interval["path_move_per_mmbtu"] == pytest.approx(0.1)
    assert roll_interval["path_move_per_mmbtu"] != pytest.approx(10.7 - 3.6)


def test_roll_safe_path_rejects_contract_selection_known_after_session_open() -> None:
    selected = _selected()
    selected.loc[selected.index[3], "available_at"] = selected.loc[selected.index[3], "session_open"] + pd.Timedelta(minutes=1)
    with pytest.raises(DecisionSystemError, match="known no later than.*session open"):
        build_roll_safe_session_path(_market(), selected)


def test_roll_safe_path_fails_closed_when_held_contract_next_open_is_missing() -> None:
    market = _market()
    selected = _selected()
    missing_date = pd.Timestamp("2026-01-12", tz="UTC")
    market = market.loc[
        ~((market["trade_date"] == missing_date) & (market["contract_id"] == "NGA"))
    ]

    with pytest.raises(DecisionSystemError, match="same-contract next open"):
        build_roll_safe_session_path(market, selected)


def test_cost_assumptions_are_explicit_and_tick_based() -> None:
    costs = parse_cost_assumptions(_costs(), tick_value_usd=10.0)

    assert costs.per_side_usd == pytest.approx(15.0)
    assert costs.round_trip_usd == pytest.approx(30.0)


def test_cost_assumptions_reject_verified_broker_claim() -> None:
    payload = _costs()
    payload["assumption_status"] = "verified"

    with pytest.raises(DecisionSystemError, match="research assumption"):
        parse_cost_assumptions(payload, tick_value_usd=10.0)


def test_csv_output_rejects_spreadsheet_formula_text(tmp_path: Path) -> None:
    output = tmp_path / "unsafe.csv"
    with pytest.raises(DecisionSystemError, match="spreadsheet formula"):
        _write_csv_exclusive(pd.DataFrame({"contract_id": ["=HYPERLINK(\"x\")"]}), output)
    assert not output.exists()


def test_risk_policy_is_fixed_operator_policy() -> None:
    policy = parse_risk_policy(_risk())
    assert policy.capital_usd == 100_000.0
    assert policy.max_contracts == 1


def test_risk_policy_rejects_model_tunable_policy() -> None:
    payload = _risk()
    payload["model_tunable"] = True
    with pytest.raises(DecisionSystemError, match="model-tunable"):
        parse_risk_policy(payload)


def test_loaded_code_identity_binds_imported_code_not_later_source_bytes(tmp_path: Path) -> None:
    source = tmp_path / "identity_probe.py"
    source.write_text("def value():\n    return 1\n", encoding="utf-8")
    module_name = "commodity_test_identity_probe"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        loaded_hash = _loaded_module_code_sha256(module)
        source_hash = sha256_file(source)
        for _ in range(100):
            assert module.value() == 1
        assert _loaded_module_code_sha256(module) == loaded_hash
        source.write_text("def value():\n    return 2\n", encoding="utf-8")
        assert _loaded_module_code_sha256(module) == loaded_hash
        assert sha256_file(source) != source_hash
    finally:
        sys.modules.pop(module_name, None)


def test_walk_forward_forecasts_use_strictly_future_fill_and_realized_training_labels() -> None:
    forecasts = build_walk_forward_forecasts(
        build_roll_safe_session_path(_market(), _selected()),
        _features(),
        models={
            "naive": {"enabled": True, "baseline_implementation": "zero_return"},
            "expanding_mean": {"enabled": True, "baseline_implementation": "expanding_mean_return"},
            "ridge": {"enabled": True, "baseline_implementation": "ridge_return", "alpha": 10.0},
        },
        horizon_sessions=5,
        contract_multiplier=10_000.0,
        selected_model="ridge",
        min_train_rows=2,
    )

    assert not forecasts.empty
    assert (forecasts["fill_timestamp"] > forecasts["signal_timestamp"]).all()
    assert (forecasts["latest_training_target_end"] <= forecasts["signal_timestamp"]).all()
    assert set(forecasts["model_id"].unique()) == {"zero", "expanding_mean", "ridge"}
    assert forecasts["forecast_id"].is_unique


def test_decision_origin_fill_is_strictly_after_feature_availability() -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    features = _features()
    first_trade_date = features.iloc[0]["trade_date"]
    features.loc[features.index[0], "available_at"] = path.iloc[1]["session_open"]
    origins, _ = _decision_origins(path, features, horizon_sessions=5)
    first = origins.loc[origins["trade_date"] == first_trade_date].iloc[0]
    assert first["signal_timestamp"] == path.iloc[1]["session_open"]
    assert first["fill_timestamp"] == path.iloc[2]["session_open"]

    features.loc[features.index[0], "available_at"] = path.iloc[-1]["session_open"] + pd.Timedelta(days=1)
    late_origins, _ = _decision_origins(path, features, horizon_sessions=5)
    assert first_trade_date not in set(late_origins["trade_date"])


def test_walk_forward_respects_governed_baseline_enablement() -> None:
    models = {
        "naive": {"enabled": False, "baseline_implementation": "zero_return"},
        "expanding_mean": {"enabled": True, "baseline_implementation": "expanding_mean_return"},
        "ridge": {"enabled": True, "baseline_implementation": "ridge_return", "alpha": 10.0},
    }
    path = build_roll_safe_session_path(_market(), _selected())
    forecasts = build_walk_forward_forecasts(
        path,
        _features(),
        models=models,
        horizon_sessions=5,
        contract_multiplier=10_000.0,
        selected_model="ridge",
        min_train_rows=2,
    )
    assert "zero" not in set(forecasts["model_id"])
    with pytest.raises(DecisionSystemError, match="selected model is not in the Phase-1 ladder"):
        build_walk_forward_forecasts(
            path,
            _features(),
            models=models,
            horizon_sessions=5,
            contract_multiplier=10_000.0,
            selected_model="zero",
            min_train_rows=2,
        )


def test_selected_model_forecasts_rejects_empty_run() -> None:
    with pytest.raises(DecisionSystemError, match="selected model produced no forecasts"):
        selected_model_forecasts(pd.DataFrame(), "ridge")


def test_policy_uses_one_net_target_and_never_stacks_forecasts() -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    forecasts = pd.DataFrame([
        _policy_forecast(path, 2, "f1", 100.0),
        _policy_forecast(path, 3, "f2", -100.0),
    ])
    ledger, _ = simulate_policy(path, forecasts, "forecast_sign", parse_risk_policy(_risk()), parse_cost_assumptions(_costs(), tick_value_usd=10.0), contract_multiplier=10_000.0)

    assert ledger["target_position"].abs().max() <= 1
    assert ledger.loc[ledger["forecast_id"] == "f1", "target_position"].iloc[0] == 1
    assert ledger.loc[ledger["forecast_id"] == "f2", "target_position"].iloc[0] == -1
    assert ledger.loc[ledger["forecast_id"] == "f2", "order_delta"].iloc[0] == -2
    assert ledger.loc[ledger["forecast_id"] == "f2", "remaining_horizon_sessions"].iloc[0] == 5


def test_policy_rejects_conflicting_forecasts_for_same_fill_session() -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    forecasts = pd.DataFrame([
        _policy_forecast(path, 2, "same-fill-long", 100.0),
        _policy_forecast(path, 2, "same-fill-short", -100.0),
    ])
    with pytest.raises(DecisionSystemError, match="only one selected-model forecast"):
        simulate_policy(
            path, forecasts, "forecast_sign", parse_risk_policy(_risk()),
            parse_cost_assumptions(_costs(), tick_value_usd=10.0), contract_multiplier=10_000.0,
        )


def test_forecast_target_persists_without_replacement_and_horizon_decrements() -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    fill_index = 2
    horizon = 5
    target_end = path.iloc[fill_index + horizon - 1]["next_session_open"]
    forecasts = pd.DataFrame([
        {
            "forecast_id": "hold-five",
            "model_id": "ridge",
            "fill_trade_date": path.iloc[fill_index]["trade_date"],
            "target_end_timestamp": target_end,
            "predicted_gross_pnl_usd": 100.0,
            "horizon_sessions": horizon,
        },
    ])

    ledger, _ = simulate_policy(
        path,
        forecasts,
        "forecast_sign",
        parse_risk_policy(_risk()),
        parse_cost_assumptions(_costs(), tick_value_usd=10.0),
        contract_multiplier=10_000.0,
    )

    held = ledger.iloc[fill_index : fill_index + horizon]
    assert held["target_position"].eq(1).all()
    assert held["forecast_id"].eq("hold-five").all()
    assert held["remaining_horizon_sessions"].tolist() == [5, 4, 3, 2, 1]
    assert held["order_delta"].tolist() == [1, 0, 0, 0, 0]
    expired = ledger.iloc[fill_index + horizon]
    assert expired["target_position"] == 0
    assert expired["no_trade_reason"] == "forecast_horizon_expired"


def test_active_forecast_crosses_roll_without_stacking_and_charges_roll() -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    forecasts = pd.DataFrame([
        _policy_forecast(path, 3, "cross-roll", 100.0),
    ])
    ledger, _ = simulate_policy(
        path,
        forecasts,
        "forecast_sign",
        parse_risk_policy(_risk()),
        parse_cost_assumptions(_costs(), tick_value_usd=10.0),
        contract_multiplier=10_000.0,
    )

    roll_row = ledger.loc[ledger["contract_id"] == "NGB"].iloc[0]
    assert roll_row["forecast_id"] == "cross-roll"
    assert roll_row["target_position"] == 1
    assert roll_row["remaining_horizon_sessions"] == 1
    assert roll_row["roll_at_open"]
    assert roll_row["execution_side_count"] == 2
    assert roll_row["roll_side_count"] == 2


@pytest.mark.parametrize(
    ("predicted_gross", "expected_position", "expected_reason"),
    [
        (29.0, 0, "predicted_gross_pnl_not_above_round_trip_cost"),
        (30.0, 0, "predicted_gross_pnl_not_above_round_trip_cost"),
        (31.0, 1, None),
        (-29.0, 0, "predicted_gross_pnl_not_above_round_trip_cost"),
        (-30.0, 0, "predicted_gross_pnl_not_above_round_trip_cost"),
        (-31.0, -1, None),
    ],
)
def test_forecast_sign_no_trade_region_uses_strict_round_trip_cost_boundary(
    predicted_gross: float,
    expected_position: int,
    expected_reason: str | None,
) -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    forecasts = pd.DataFrame([
        _policy_forecast(path, 2, "cost-boundary", predicted_gross),
    ])
    ledger, _ = simulate_policy(
        path,
        forecasts,
        "forecast_sign",
        parse_risk_policy(_risk()),
        parse_cost_assumptions(_costs(), tick_value_usd=10.0),
        contract_multiplier=10_000.0,
    )

    row = ledger.loc[ledger["forecast_id"] == "cost-boundary"].iloc[0]
    assert row["target_position"] == expected_position
    assert row["no_trade_reason"] == expected_reason


def test_long_only_and_flat_share_same_risk_and_execution_engine() -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    empty_forecasts = pd.DataFrame(columns=["forecast_id", "model_id", "fill_trade_date", "predicted_gross_pnl_usd"])
    risk = parse_risk_policy(_risk())
    costs = parse_cost_assumptions(_costs(), tick_value_usd=10.0)
    flat, _ = simulate_policy(path, empty_forecasts, "flat", risk, costs, contract_multiplier=10_000.0)
    long_only, _ = simulate_policy(path, empty_forecasts, "long_only", risk, costs, contract_multiplier=10_000.0)

    assert flat["target_position"].eq(0).all()
    assert long_only["target_position"].abs().max() == 1
    assert set(flat.columns) == set(long_only.columns)


def test_roll_transition_charges_close_and_reopen_sides() -> None:
    path = build_roll_safe_session_path(_market(), _selected())
    ledger, _ = simulate_policy(
        path,
        pd.DataFrame(),
        "long_only",
        parse_risk_policy(_risk()),
        parse_cost_assumptions(_costs(), tick_value_usd=10.0),
        contract_multiplier=10_000.0,
    )
    roll_row = ledger.loc[ledger["contract_id"] == "NGB"].iloc[0]
    assert roll_row["roll_at_open"]
    assert roll_row["execution_side_count"] == 2
    assert roll_row["roll_side_count"] == 2
    assert roll_row["transaction_cost_usd"] == pytest.approx(30.0)


def test_daily_loss_kill_persists_flat_until_restart() -> None:
    path = build_roll_safe_session_path(_market(), _selected()).copy()
    path.loc[path.index[2], "path_move_per_mmbtu"] = -0.25
    forecasts = pd.DataFrame([
        _policy_forecast(path, 2, "enter", 500.0),
        _policy_forecast(path, 3, "stay", 500.0),
        _policy_forecast(path, 4, "later", 500.0),
    ])
    ledger, summary = simulate_policy(
        path,
        forecasts,
        "forecast_sign",
        parse_risk_policy(_risk()),
        parse_cost_assumptions(_costs(), tick_value_usd=10.0),
        contract_multiplier=10_000.0,
    )

    assert summary["kill_triggered"] is True
    assert "daily_loss_limit" in summary["kill_reason"]
    liquidation = ledger.loc[ledger["trade_date"] == path.iloc[3]["trade_date"]].iloc[0]
    assert liquidation["prior_target_position"] == 1
    assert liquidation["target_position"] == 0
    assert liquidation["order_delta"] == -1
    assert liquidation["execution_side_count"] == 1
    assert liquidation["transaction_cost_usd"] == pytest.approx(15.0)
    assert ledger.loc[ledger["trade_date"] >= path.iloc[3]["trade_date"], "target_position"].eq(0).all()
    assert ledger.loc[ledger["trade_date"] >= path.iloc[3]["trade_date"], "risk_state"].eq("killed").all()


def test_peak_drawdown_kill_can_trigger_without_daily_loss_breach() -> None:
    path = build_roll_safe_session_path(_market(), _selected()).copy()
    path.loc[path.index[:7], "path_move_per_mmbtu"] = -0.15
    ledger, summary = simulate_policy(
        path,
        pd.DataFrame(),
        "long_only",
        parse_risk_policy(_risk()),
        parse_cost_assumptions(_costs(), tick_value_usd=10.0),
        contract_multiplier=10_000.0,
    )
    assert summary["kill_triggered"] is True
    assert summary["kill_reason"] == "peak_drawdown_kill"
    killed_rows = ledger.index[ledger["risk_state"] == "killed"]
    assert len(killed_rows) > 0
    trigger_index = int(killed_rows[0])
    assert ledger.loc[trigger_index, "daily_loss_usd"] < 2_000.0
    assert ledger.loc[trigger_index + 1 :, "target_position"].eq(0).all()
    assert ledger.loc[trigger_index + 1 :, "risk_state"].eq("killed").all()
    assert ledger.loc[trigger_index + 1 :, "kill_reason"].eq("peak_drawdown_kill").all()


def test_margin_assumption_can_force_flat_without_weakening_risk_limit() -> None:
    payload = _costs()
    payload["initial_margin_usd_per_contract"] = 150_000.0
    path = build_roll_safe_session_path(_market(), _selected())
    ledger, _ = simulate_policy(path, pd.DataFrame(), "long_only", parse_risk_policy(_risk()), parse_cost_assumptions(payload, tick_value_usd=10.0), contract_multiplier=10_000.0)

    assert ledger["target_position"].eq(0).all()
    assert set(ledger.iloc[:-1]["no_trade_reason"].dropna()) == {"insufficient_margin_assumption"}
    assert ledger.iloc[-1]["no_trade_reason"] == "end_of_sample_liquidation"


def test_input_boundary_requires_research_ready_assurance() -> None:
    hashes = {
        "market_sha256": "1" * 64,
        "selected_path_sha256": "2" * 64,
        "features_sha256": "3" * 64,
    }
    payload: dict[str, object] = {
        "schema_version": 2,
        "evidence_partition": "development",
        "protected_confirmation_accessed": False,
        **hashes,
        "data_assurance": {},
    }
    with pytest.raises(DecisionSystemError, match="research-ready data assurance"):
        parse_input_boundary(
            payload,
            allowed_partitions={"development", "rolling_research_oos"},
            observed_hashes=hashes,
        )


def test_input_boundary_rejects_tampered_research_ready_assurance() -> None:
    hashes = {
        "market_sha256": "1" * 64,
        "selected_path_sha256": "2" * 64,
        "features_sha256": "3" * 64,
    }
    assurance = _research_ready_assurance()
    assurance["assurance_sha256"] = "0" * 64
    payload: dict[str, object] = {
        "schema_version": 2,
        "instrument": "CME_NYMEX_NG",
        "roll_policy": "volume_crossover_dte_v1",
        "evidence_partition": "development",
        "protected_confirmation_accessed": False,
        **hashes,
        "data_assurance": assurance,
    }
    with pytest.raises(DecisionSystemError, match="research-ready data assurance"):
        parse_input_boundary(
            payload,
            allowed_partitions={"development", "rolling_research_oos"},
            observed_hashes=hashes,
        )


def test_input_boundary_rejects_legacy_self_attested_contract() -> None:
    hashes = {
        "market_sha256": "1" * 64,
        "selected_path_sha256": "2" * 64,
        "features_sha256": "3" * 64,
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "evidence_partition": "development",
        "protected_confirmation_accessed": False,
        **hashes,
        "data_assurance": _research_ready_assurance(),
    }
    with pytest.raises(DecisionSystemError, match="schema_version must be 2"):
        parse_input_boundary(
            payload,
            allowed_partitions={"development", "rolling_research_oos"},
            observed_hashes=hashes,
        )


def test_governed_input_authority_requires_committed_unchanged_file(tmp_path: Path) -> None:
    repo = tmp_path / "authority-repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Commodity Test"],
        check=True,
        capture_output=True,
    )
    authority = repo / "input-authority.json"
    authority.write_text("{}\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "input-authority.json"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--no-gpg-sign", "-m", "authority"],
        check=True,
        capture_output=True,
    )

    identity = governed_input_authority_identity(
        authority,
        repo_root=repo,
        expected_sha256=sha256_file(authority),
    )
    assert identity["repo_relative_path"] == "input-authority.json"
    with pytest.raises(DecisionSystemError, match="changed while being validated"):
        governed_input_authority_identity(
            authority,
            repo_root=repo,
            expected_sha256="0" * 64,
        )
    assert len(identity["git_commit"]) == 40
    assert len(identity["git_blob"]) == 40
    assert identity["sha256"] == sha256_file(authority)

    authority.write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(DecisionSystemError, match="committed and unchanged"):
        governed_input_authority_identity(
            authority,
            repo_root=repo,
            expected_sha256=sha256_file(authority),
        )

    untracked = repo / "untracked-authority.json"
    untracked.write_text("{}\n", encoding="utf-8")
    with pytest.raises(DecisionSystemError, match="committed"):
        governed_input_authority_identity(
            untracked,
            repo_root=repo,
            expected_sha256=sha256_file(untracked),
        )


def _write_cli_inputs(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    dates = pd.date_range("2025-01-02", periods=40, freq="B", tz="UTC")
    market_rows: list[dict[str, object]] = []
    selected_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []
    for i, date in enumerate(dates):
        for contract, base in (("NGA", 3.0), ("NGB", 6.0)):
            market_rows.append({
                "trade_date": date.isoformat(),
                "contract_id": contract,
                "open": base + 0.01 * i,
            })
        selected_rows.append({
            "trade_date": date.isoformat(),
            "contract_id": "NGA" if i < 20 else "NGB",
            "available_at": (date + pd.Timedelta(hours=13)).isoformat(),
            "session_open": (date + pd.Timedelta(hours=14, minutes=30)).isoformat(),
            "roll_reason": "volume_crossover" if i == 20 else "hold",
        })
        feature_rows.append({
            "trade_date": date.isoformat(),
            "available_at": (date + pd.Timedelta(hours=21)).isoformat(),
            "feature_curve": float(i),
            "feature_return": float((i % 5) - 2) / 100.0,
        })
    market = root / "market.csv"
    selected = root / "selected.csv"
    features = root / "features.csv"
    costs = root / "costs.json"
    boundary = root / "input-boundary.json"
    pd.DataFrame(market_rows).to_csv(market, index=False)
    pd.DataFrame(selected_rows).to_csv(selected, index=False)
    pd.DataFrame(feature_rows).to_csv(features, index=False)
    costs.write_text(json.dumps(_costs(), sort_keys=True), encoding="utf-8")
    boundary.write_text(
        json.dumps({
            "schema_version": 2,
            "instrument": "CME_NYMEX_NG",
            "roll_policy": "volume_crossover_dte_v1",
            "evidence_partition": "development",
            "protected_confirmation_accessed": False,
            "market_sha256": sha256_file(market),
            "selected_path_sha256": sha256_file(selected),
            "features_sha256": sha256_file(features),
            "data_assurance": _research_ready_assurance(),
        }, sort_keys=True),
        encoding="utf-8",
    )
    return market, selected, features, costs, boundary


def _allow_test_input_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    def identity(path: Path, *, repo_root: Path, expected_sha256: str) -> dict[str, str]:
        del repo_root
        observed = sha256_file(Path(path))
        if observed != expected_sha256:
            raise DecisionSystemError("input authority changed while being validated")
        return {
            "repo_relative_path": "tests/synthetic-input-authority.json",
            "git_commit": "e" * 40,
            "git_blob": "f" * 40,
            "sha256": observed,
        }

    monkeypatch.setattr(cli_module, "governed_input_authority_identity", identity)


def test_cli_rejects_unknown_decision_simulation() -> None:
    args = build_parser().parse_args([
        "trading-decision-v0",
        "--market", "market.csv",
        "--selected-path", "selected.csv",
        "--features", "features.csv",
        "--cost-assumptions", "costs.json",
        "--input-boundary", "boundary.json",
        "--simulation", "unknown-simulation",
        "--output", "artifacts/runs/unknown",
    ])
    with pytest.raises(DecisionSystemError, match="simulation.*unavailable|unavailable.*simulation"):
        args.func(args)


def test_cli_rejects_alternative_valid_risk_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    real_snapshot = cli_module._json_snapshot

    def snapshot(path: Path, label: str) -> tuple[dict[str, object], str]:
        payload, digest = real_snapshot(path, label)
        if label == "trading policy":
            payload = json.loads(json.dumps(payload))
            policies = payload["paper_risk_policies"]
            assert isinstance(policies, dict)
            alternate = dict(policies["phase1_standard_ng_v0"])
            alternate["capital_usd"] = 200_000.0
            policies["alternate_valid_policy"] = alternate
        return payload, digest

    monkeypatch.setattr(cli_module, "_json_snapshot", snapshot)
    args = build_parser().parse_args([
        "trading-decision-v0",
        "--market", str(market),
        "--selected-path", str(selected),
        "--features", str(features),
        "--cost-assumptions", str(costs),
        "--input-boundary", str(boundary),
        "--risk-policy", "alternate_valid_policy",
        "--output", str(tmp_path / "alternate-risk"),
    ])
    with pytest.raises(DecisionSystemError, match="risk policy.*fixed|fixed.*risk policy"):
        args.func(args)


def test_cli_decision_loop_is_deterministic_and_reconstructable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    outputs = [tmp_path / "run-a", tmp_path / "run-b"]
    for output in outputs:
        args = build_parser().parse_args([
            "trading-decision-v0",
            "--market", str(market),
            "--selected-path", str(selected),
            "--features", str(features),
            "--cost-assumptions", str(costs),
            "--input-boundary", str(boundary),
            "--output", str(output),
        ])
        args.func(args)

    manifest_a = json.loads((outputs[0] / "input_manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((outputs[1] / "input_manifest.json").read_text(encoding="utf-8"))
    assert manifest_a == manifest_b
    assert manifest_a["evidence_partition"] == "development"
    assert manifest_a["instrument"] == "CME_NYMEX_NG"
    assert manifest_a["roll_policy"] == "volume_crossover_dte_v1"
    assert manifest_a["protected_confirmation_accessed"] is False
    assert manifest_a["input_authority_sha256"] == sha256_file(boundary)
    assert manifest_a["input_authority_git_commit"] == "e" * 40
    assert manifest_a["input_authority_git_blob"] == "f" * 40
    assert manifest_a["input_authority_path"] == "tests/synthetic-input-authority.json"
    assert manifest_a["data_assurance_sha256"] == _research_ready_assurance()["assurance_sha256"]
    assert len(manifest_a["decision_engine_sha256"]) == 64
    assert len(manifest_a["requirements_lock_sha256"]) == 64
    assert manifest_a["canonical_execution_evidence"] is False
    expected_identity = dict(manifest_a)
    observed_run_id = expected_identity.pop("run_id")
    encoded = json.dumps(
        expected_identity, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert observed_run_id == hashlib.sha256(encoded).hexdigest()

    alt_costs = tmp_path / "costs-alt.json"
    alt_payload = _costs()
    alt_payload["commission_usd_per_side"] = 2.5
    alt_costs.write_text(json.dumps(alt_payload, sort_keys=True), encoding="utf-8")
    alt_output = tmp_path / "run-c"
    alt_args = build_parser().parse_args([
        "trading-decision-v0", "--market", str(market),
        "--selected-path", str(selected), "--features", str(features),
        "--cost-assumptions", str(alt_costs), "--input-boundary", str(boundary),
        "--output", str(alt_output),
    ])
    alt_args.func(alt_args)
    manifest_c = json.loads((alt_output / "input_manifest.json").read_text(encoding="utf-8"))
    assert manifest_c["run_id"] != manifest_a["run_id"]

    for filename in (
        "session_path.csv",
        "forecasts.csv",
        "ledger-flat.csv",
        "ledger-long_only.csv",
        "ledger-forecast_sign.csv",
        "equity-flat.csv",
        "equity-long_only.csv",
        "equity-forecast_sign.csv",
        "summary.json",
        "completion_manifest.json",
    ):
        assert (outputs[0] / filename).read_bytes() == (outputs[1] / filename).read_bytes()

    forecasts = pd.read_csv(outputs[0] / "forecasts.csv")
    assert set(forecasts["model_id"]) == {"zero", "expanding_mean", "ridge", "hist_gb"}
    ledger = pd.read_csv(outputs[0] / "ledger-forecast_sign.csv")
    assert ledger["target_position"].abs().max() <= 1
    summary = json.loads((outputs[0] / "summary.json").read_text(encoding="utf-8"))
    assert summary["risk_state_scope"] == "fresh_offline_replay"
    assert summary["persistent_paper_state_supported"] is False
    assert summary["scientific_scope"] == "plumbing_and_executable_benchmark_only_no_edge_claim"
    assert set(summary["benchmark_summaries"]) == {"flat", "long_only", "forecast_sign"}
    completion = json.loads(
        (outputs[0] / "completion_manifest.json").read_text(encoding="utf-8")
    )
    assert completion["status"] == "complete"
    assert completion["run_id"] == manifest_a["run_id"]
    assert set(completion["outputs"]) == {
        "session_path.csv", "forecasts.csv", "input_manifest.json", "summary.json",
        "ledger-flat.csv", "ledger-long_only.csv", "ledger-forecast_sign.csv",
        "equity-flat.csv", "equity-long_only.csv", "equity-forecast_sign.csv",
    }
    for filename, digest in completion["outputs"].items():
        assert sha256_file(outputs[0] / filename) == digest


def test_cli_decision_loop_is_process_independent(tmp_path: Path) -> None:
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    runner = tmp_path / "decision_runner.py"
    runner.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "from commodity import cli\n"
        "from commodity.provenance import sha256_file\n"
        "def identity(path, *, repo_root, expected_sha256):\n"
        "    del repo_root\n"
        "    observed = sha256_file(Path(path))\n"
        "    assert observed == expected_sha256\n"
        "    return {'repo_relative_path':'tests/synthetic-input-authority.json','git_commit':'e'*40,'git_blob':'f'*40,'sha256':observed}\n"
        "cli.governed_input_authority_identity = identity\n"
        "args = cli.build_parser().parse_args(sys.argv[1:])\n"
        "args.func(args)\n",
        encoding="utf-8",
    )
    outputs: list[Path] = []
    for seed, timezone in (("1", "UTC"), ("777", "Europe/Oslo")):
        output = tmp_path / f"process-{seed}"
        env = os.environ.copy()
        env.update({"PYTHONHASHSEED": seed, "TZ": timezone})
        subprocess.run(
            [
                sys.executable, str(runner), "trading-decision-v0",
                "--market", str(market), "--selected-path", str(selected),
                "--features", str(features), "--cost-assumptions", str(costs),
                "--input-boundary", str(boundary), "--output", str(output),
            ],
            cwd=Path(__file__).parents[1],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(output)
    names = sorted(path.name for path in outputs[0].iterdir())
    assert names == sorted(path.name for path in outputs[1].iterdir())
    for name in names:
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()


def test_cli_rejects_input_authority_with_wrong_instrument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    payload = json.loads(boundary.read_text(encoding="utf-8"))
    payload["instrument"] = "UNRELATED_FUTURE"
    boundary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    args = build_parser().parse_args([
        "trading-decision-v0", "--market", str(market),
        "--selected-path", str(selected), "--features", str(features),
        "--cost-assumptions", str(costs), "--input-boundary", str(boundary),
        "--output", str(tmp_path / "wrong-instrument"),
    ])
    with pytest.raises(DecisionSystemError, match="instrument"):
        args.func(args)


def test_cli_rejects_input_authority_with_wrong_roll_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    payload = json.loads(boundary.read_text(encoding="utf-8"))
    payload["roll_policy"] = "unrelated_roll_policy"
    boundary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    args = build_parser().parse_args([
        "trading-decision-v0", "--market", str(market),
        "--selected-path", str(selected), "--features", str(features),
        "--cost-assumptions", str(costs), "--input-boundary", str(boundary),
        "--output", str(tmp_path / "wrong-roll"),
    ])
    with pytest.raises(DecisionSystemError, match="roll policy"):
        args.func(args)


def test_cli_rejects_reserved_confirmation_partition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    payload = json.loads(boundary.read_text(encoding="utf-8"))
    payload["evidence_partition"] = "reserved_confirmation"
    boundary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    args = build_parser().parse_args([
        "trading-decision-v0", "--market", str(market),
        "--selected-path", str(selected), "--features", str(features),
        "--cost-assumptions", str(costs), "--input-boundary", str(boundary),
        "--output", str(tmp_path / "reserved-rejected"),
    ])
    with pytest.raises(DecisionSystemError, match="partition"):
        args.func(args)


def test_cli_rejects_declared_protected_confirmation_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    payload = json.loads(boundary.read_text(encoding="utf-8"))
    payload["protected_confirmation_accessed"] = True
    boundary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    args = build_parser().parse_args([
        "trading-decision-v0", "--market", str(market),
        "--selected-path", str(selected), "--features", str(features),
        "--cost-assumptions", str(costs), "--input-boundary", str(boundary),
        "--output", str(tmp_path / "protected-rejected"),
    ])
    with pytest.raises(DecisionSystemError, match="protected confirmation"):
        args.func(args)

@pytest.mark.parametrize("input_index", [0, 1, 2])
def test_cli_rejects_boundary_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, input_index: int
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    inputs = [market, selected, features]
    with inputs[input_index].open("a", encoding="utf-8") as handle:
        handle.write("\n")
    args = build_parser().parse_args([
        "trading-decision-v0",
        "--market", str(market),
        "--selected-path", str(selected),
        "--features", str(features),
        "--cost-assumptions", str(costs),
        "--input-boundary", str(boundary),
        "--output", str(tmp_path / f"mismatch-{input_index}"),
    ])
    with pytest.raises(DecisionSystemError, match="hash"):
        args.func(args)

def test_cli_refuses_to_overwrite_existing_run_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    output = tmp_path / "existing-run"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    args = build_parser().parse_args([
        "trading-decision-v0",
        "--market", str(market),
        "--selected-path", str(selected),
        "--features", str(features),
        "--cost-assumptions", str(costs),
        "--input-boundary", str(boundary),
        "--output", str(output),
    ])
    with pytest.raises(DecisionSystemError, match="overwrite|non-empty"):
        args.func(args)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_cli_failed_publication_has_no_completion_marker_or_predictable_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    output = tmp_path / "failed-run"

    def fail_policy(*args: object, **kwargs: object) -> tuple[pd.DataFrame, dict[str, object]]:
        del args, kwargs
        raise RuntimeError("synthetic policy failure")

    monkeypatch.setattr(cli_module, "simulate_policy", fail_policy)
    args = build_parser().parse_args([
        "trading-decision-v0",
        "--market", str(market),
        "--selected-path", str(selected),
        "--features", str(features),
        "--cost-assumptions", str(costs),
        "--input-boundary", str(boundary),
        "--output", str(output),
    ])
    with pytest.raises(RuntimeError, match="synthetic policy failure"):
        args.func(args)

    assert output.is_dir()
    assert not (output / "completion_manifest.json").exists()
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))


def test_cli_late_write_failure_never_publishes_completion_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_test_input_authority(monkeypatch)
    market, selected, features, costs, boundary = _write_cli_inputs(tmp_path)
    output = tmp_path / "late-failed-run"
    real_write_json = cli_module._write_json_exclusive

    def fail_summary(path: Path, payload: dict[str, object]) -> None:
        if path.name == "summary.json":
            raise RuntimeError("synthetic late write failure")
        real_write_json(path, payload)

    monkeypatch.setattr(cli_module, "_write_json_exclusive", fail_summary)
    args = build_parser().parse_args([
        "trading-decision-v0", "--market", str(market),
        "--selected-path", str(selected), "--features", str(features),
        "--cost-assumptions", str(costs), "--input-boundary", str(boundary),
        "--output", str(output),
    ])
    with pytest.raises(RuntimeError, match="synthetic late write failure"):
        args.func(args)
    assert (output / "input_manifest.json").exists()
    assert not (output / "completion_manifest.json").exists()
