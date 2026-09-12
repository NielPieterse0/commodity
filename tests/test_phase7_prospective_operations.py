from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research" / "run_phase7_prospective_operations.py"


def _module():
    spec = importlib.util.spec_from_file_location("phase7_prospective_operations", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _activate_contract(module, tmp_path: Path, *, merged_at: str = "2026-09-12T08:00:00Z") -> None:
    payload = json.loads(module.CONTRACT.read_text(encoding="utf-8"))
    payload["status"] = "prospective_active"
    payload["prospective_serving_contract"]["status"] = "frozen_active"
    payload["prospective_serving_contract"]["specialist_runtime_proof"] = {
        "status": "verified",
        "runtime_evidence_sha256": "3" * 64,
    }
    payload["prospective_serving_contract"]["landing"] = {
        "pull_request": 999,
        "head_sha": "1" * 40,
        "merge_commit_sha": "2" * 40,
        "merged_at": merged_at,
    }
    contract = tmp_path / "phase7-active.json"
    contract.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    module.CONTRACT = contract


def _runtime_args(tmp_path: Path) -> dict[str, Path]:
    return {
        "timesfm_runtime_root": tmp_path / "timesfm-runtime",
        "timesfm_source_zip": tmp_path / "timesfm-source.zip",
        "timesfm_cache_dir": tmp_path / "timesfm-cache",
        "kronos_source_root": tmp_path / "kronos-source",
        "kronos_cache_dir": tmp_path / "kronos-cache",
    }


def test_pinned_specialist_runtime_cache_is_path_sensitive(tmp_path: Path) -> None:
    module = _module()
    created: list[dict[str, Path]] = []

    class _Runtime:
        def __init__(self, **kwargs):
            created.append(kwargs)

    class _Derivation:
        PinnedSpecialistServingRuntime = _Runtime

    first_args = _runtime_args(tmp_path)
    first = module._pinned_specialist_runtime(_Derivation, **first_args)
    assert module._pinned_specialist_runtime(_Derivation, **first_args) is first

    second_args = dict(first_args)
    second_args["timesfm_cache_dir"] = tmp_path / "timesfm-cache-2"
    second = module._pinned_specialist_runtime(_Derivation, **second_args)
    assert second is not first
    assert len(created) == 2


def _decision(module, record_id: str = "prospective-1") -> dict[str, object]:
    phase7 = module._phase7_module()
    input_snapshot = {"fixture": "prospective-decision-input"}
    return {
        "record_id": record_id,
        "decision_timestamp": "2026-09-13T12:00:00Z",
        "planned_fill_timestamp": "2026-09-14T00:00:00Z",
        "target_end_timestamp": "2026-09-19T00:00:00Z",
        "horizon_sessions": 5,
        "candidate_config_id": "s-veto__l-none__p-half__u-none",
        "prospective_serving_deployment_id": "phase7-prospective-serving-v2",
        "prospective_origin_index": 0,
        "path_counter_advanced": True,
        "kronos_path_eligible": True,
        "phase7_contract_sha256": phase7._sha256(module.CONTRACT),
        "input_snapshot_sha256": module._json_sha256(input_snapshot),
        "decision_input_snapshot": input_snapshot,
        "source_snapshot_sha256": "b" * 64,
        "forecast_id": "forecast-2026-09-13",
        "market_model_id": "histgb-core-v1",
        "predicted_path_move_per_mmbtu": -0.025,
        "predicted_gross_pnl_usd": -250.0,
        "baseline_position": -1.0,
        "prior_position": 0.0,
        "intended_position": -0.5,
        "policy_modifiers": ["kronos_path_half"],
        "contract_id": "NGX6",
        "fill_rule": "first_retained_interval_open_strictly_after_all_inputs_available",
        "cost_profile_id": "base",
        "risk_state": "active",
        "source_freshness_ok": True,
        "source_completeness_ok": True,
        "skip_reason": None,
        "derivation": {
            "method": "phase7_frozen_candidate_v1",
            "serving_deployment_identity": "phase7-prospective-serving-v2",
            "phase2_freeze_sha256": "c" * 64,
            "policy_refit_cadence": "retain_phase5_two_year_outer_block_cadence_no_annual_refit",
            "training_cutoff": "2022-12-31",
            "origin_sequence_index": 0,
            "kronos_path_eligible": True,
            "kronos_path_cycle_length": 109,
            "kronos_path_active_residues": [0, 13, 27, 40, 54, 68, 81, 95],
            "outcome_fields_consumed": False,
        },
    }


def _outcome(module, record_id: str = "prospective-1") -> dict[str, object]:
    record = _decision(module, record_id)
    record.update(
        {
            "outcome_timestamp": "2026-09-19T00:00:00Z",
            "actual_contract_id": "NGX6",
            "actual_position": -0.5,
            "fill_price": 3.25,
            "transaction_cost_usd": 15.0,
            "net_pnl_usd": 125.0,
            "miss_reason": None,
        }
    )
    return record


def test_decision_requires_full_forecast_and_input_identity(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    record = _decision(module)
    del record["forecast_id"]
    try:
        module.append_decision(
            record,
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-13T12:00:01Z",
        )
    except ValueError as exc:
        assert "forecast_id" in str(exc)
    else:
        raise AssertionError("thin prospective decision was accepted")


def test_complete_decision_is_bound_before_later_settlement(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    decision = _decision(module)
    appended = module.append_decision(
        decision,
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    assert appended["event_type"] == "decision"
    assert appended["forecast_id"] == decision["forecast_id"]
    assert appended["input_snapshot_sha256"] == decision["input_snapshot_sha256"]
    assert appended["decision_input_snapshot"] == decision["decision_input_snapshot"]
    assert appended["target_end_timestamp"] == "2026-09-19T00:00:00Z"
    assert appended["policy_modifiers"] == ["kronos_path_half"]

    settled = module._append_derived_outcome(
        _outcome(module),
        ledger=ledger,
        recorded_at="2026-09-19T00:00:01Z",
    )
    assert settled["event_type"] == "outcome"
    assert settled["decision_record_sha256"] == appended["record_sha256"]

    status = module.ledger_status(ledger)
    assert status["decision_events"] == 1
    assert status["settled_outcomes"] == 1
    assert status["pending_decisions"] == 0
    assert status["active_exposure_outcomes"] == 1
    assert status["short_exposure_outcomes"] == 1
    assert status["episode_outcome_net_pnl_usd"] == 125.0
    assert status["net_pnl_usd"] == 0.0
    assert status["session_events"] == 0
    assert status["phase8_entry_eligible"] is False


def test_settlement_rejects_decision_time_identity_drift(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module),
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    outcome = _outcome(module)
    outcome["decision_input_snapshot"] = {"fixture": "drifted-input"}
    outcome["input_snapshot_sha256"] = module._json_sha256(outcome["decision_input_snapshot"])
    try:
        module._append_derived_outcome(
            outcome,
            ledger=ledger,
            recorded_at="2026-09-19T00:00:01Z",
        )
    except ValueError as exc:
        assert "input_snapshot_sha256" in str(exc)
    else:
        raise AssertionError("settlement accepted drift from the persisted decision")


def test_outcome_cannot_precede_frozen_target_end(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module),
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    outcome = _outcome(module)
    outcome["outcome_timestamp"] = "2026-09-18T11:59:59Z"
    try:
        module._append_derived_outcome(
            outcome,
            ledger=ledger,
            recorded_at="2026-09-19T00:00:01Z",
        )
    except ValueError as exc:
        assert "target_end_timestamp" in str(exc)
    else:
        raise AssertionError("outcome before target end was accepted")


def test_stale_source_must_fail_closed_to_flat(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    record = _decision(module)
    record["source_freshness_ok"] = False
    record["path_counter_advanced"] = False
    record["prospective_origin_index"] = None
    record["kronos_path_eligible"] = False
    record["derivation"]["origin_sequence_index"] = None
    record["derivation"]["kronos_path_eligible"] = False
    try:
        module.append_decision(
            record,
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-13T12:00:01Z",
        )
    except ValueError as exc:
        assert "fail closed" in str(exc)
    else:
        raise AssertionError("active decision with stale source was accepted")


def test_later_missed_fill_is_not_frozen_at_decision_time(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module),
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    outcome = _outcome(module)
    outcome["actual_contract_id"] = None
    outcome["actual_position"] = 0.0
    outcome["fill_price"] = None
    outcome["transaction_cost_usd"] = 0.0
    outcome["net_pnl_usd"] = 0.0
    outcome["miss_reason"] = "eligible_interval_missing"

    settled = module._append_derived_outcome(
        outcome,
        ledger=ledger,
        recorded_at="2026-09-19T00:00:01Z",
    )
    assert settled["miss_reason"] == "eligible_interval_missing"
    assert settled["skip_or_miss_reason"] == "eligible_interval_missing"
    assert settled["actual_position"] == 0.0


def _session(
    start: str,
    end: str,
    *,
    open_price: float,
    next_open: float,
    contract_id: str = "NGX6",
    next_contract_id: str = "NGX6",
) -> dict[str, object]:
    return {
        "session_timestamp": start,
        "next_session_timestamp": end,
        "contract_id": contract_id,
        "next_selected_contract_id": next_contract_id,
        "open_price": open_price,
        "next_open_same_contract": next_open,
        "source_snapshot_sha256": "d" * 64,
        "source_freshness_ok": True,
        "source_completeness_ok": True,
    }


def test_fifth_gap_free_session_auto_settles_episode_from_persisted_evidence(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    decision = module.append_decision(
        _decision(module), ledger=ledger, recorded_at="2026-09-13T12:00:01Z"
    )
    prices = [3.0, 3.1, 3.2, 3.3, 3.4, 3.5]
    dates = [
        "2026-09-14T00:00:00Z",
        "2026-09-15T00:00:00Z",
        "2026-09-16T00:00:00Z",
        "2026-09-17T00:00:00Z",
        "2026-09-18T00:00:00Z",
        "2026-09-19T00:00:00Z",
    ]
    appended_sessions = []
    for index in range(5):
        appended_sessions.append(
            module.append_session_observation(
                _session(
                    dates[index],
                    dates[index + 1],
                    open_price=prices[index],
                    next_open=prices[index + 1],
                ),
                ledger=ledger,
                recorded_at=f"2026-09-{15 + index:02d}T00:00:01Z",
            )
        )
        if index < 4:
            assert module.ledger_status(ledger)["settled_outcomes"] == 0

    _, events = module._phase7_module()._read_prospective_events(ledger)
    outcomes = [event for event in events if event.get("event_type") == "outcome"]
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["record_id"] == decision["record_id"]
    assert outcome["outcome_timestamp"] == "2026-09-19T00:00:00+00:00"
    assert outcome["actual_position"] == -0.5
    assert outcome["actual_contract_id"] == "NGX6"
    assert outcome["fill_price"] == pytest.approx(3.0)
    assert outcome["actual_path_move_per_mmbtu"] == pytest.approx(0.5)
    assert outcome["gross_pnl_usd"] == pytest.approx(-2500.0)
    assert outcome["transaction_cost_usd"] == pytest.approx(7.5)
    assert outcome["net_pnl_usd"] == pytest.approx(-2507.5)
    assert outcome["economic_role"] == "informational_five_session_system_window_not_economic_gate"
    assert outcome["daily_session_ledger_is_economic_gate"] is True
    assert outcome["session_record_sha256s"] == [
        event["record_sha256"] for event in appended_sessions
    ]
    status = module.ledger_status(ledger)
    assert status["settled_outcomes"] == 1
    assert status["pending_decisions"] == 0
    assert status["net_pnl_usd"] == pytest.approx(-2507.5)
    assert status["episode_outcome_net_pnl_usd"] == pytest.approx(-2507.5)
    assert status["episode_outcome_economic_role"] == (
        "informational_five_session_system_window_not_economic_gate"
    )


def test_independent_episode_counts_are_deterministic_and_non_overlapping(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"

    first = _decision(module, "prospective-1")
    module.append_decision(first, ledger=ledger, recorded_at="2026-09-13T12:00:01Z")
    second = _decision(module, "prospective-2")
    second.update({
        "decision_timestamp": "2026-09-15T23:59:00Z",
        "planned_fill_timestamp": "2026-09-16T00:00:00Z",
        "target_end_timestamp": "2026-09-21T00:00:00Z",
        "prospective_origin_index": 1,
        "kronos_path_eligible": False,
        "policy_modifiers": [],
    })
    second["derivation"]["origin_sequence_index"] = 1
    second["derivation"]["kronos_path_eligible"] = False
    second["forecast_id"] = "forecast-2026-09-15"
    third = _decision(module, "prospective-3")
    third.update({
        "decision_timestamp": "2026-09-18T23:59:00Z",
        "planned_fill_timestamp": "2026-09-19T00:00:00Z",
        "target_end_timestamp": "2026-09-24T00:00:00Z",
        "prospective_origin_index": 2,
        "kronos_path_eligible": False,
        "policy_modifiers": [],
    })
    third["derivation"]["origin_sequence_index"] = 2
    third["derivation"]["kronos_path_eligible"] = False
    third["forecast_id"] = "forecast-2026-09-18"

    module._append_derived_outcome(
        _outcome(module), ledger=ledger, recorded_at="2026-09-19T00:00:01Z"
    )
    module.append_decision(second, ledger=ledger, recorded_at="2026-09-15T23:59:01Z")
    second_outcome = dict(second)
    second_outcome.update({
        "outcome_timestamp": "2026-09-21T00:00:00Z",
        "actual_contract_id": "NGX6",
        "actual_position": -0.5,
        "fill_price": 3.2,
        "transaction_cost_usd": 0.0,
        "net_pnl_usd": 50.0,
        "miss_reason": None,
    })
    module._append_derived_outcome(
        second_outcome, ledger=ledger, recorded_at="2026-09-21T00:00:01Z"
    )
    module.append_decision(third, ledger=ledger, recorded_at="2026-09-18T23:59:01Z")
    third_outcome = dict(third)
    third_outcome.update({
        "outcome_timestamp": "2026-09-24T00:00:00Z",
        "actual_contract_id": "NGX6",
        "actual_position": -0.5,
        "fill_price": 3.4,
        "transaction_cost_usd": 0.0,
        "net_pnl_usd": 75.0,
        "miss_reason": None,
    })
    module._append_derived_outcome(
        third_outcome, ledger=ledger, recorded_at="2026-09-24T00:00:01Z"
    )

    status = module.ledger_status(ledger)
    assert status["settled_outcomes"] == 3
    assert status["independent_episode_count"] == 2
    assert status["independent_active_exposure_count"] == 2
    assert status["independent_long_exposure_count"] == 0
    assert status["independent_short_exposure_count"] == 2


def test_session_accounting_derives_cost_pnl_and_risk_kill(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module), ledger=ledger, recorded_at="2026-09-13T12:00:01Z"
    )
    first = module.append_session_observation(
        _session(
            "2026-09-14T00:00:00Z",
            "2026-09-15T00:00:00Z",
            open_price=3.0,
            next_open=3.1,
        ),
        ledger=ledger,
        recorded_at="2026-09-15T00:00:01Z",
    )
    assert first["target_position"] == -0.5
    assert first["transaction_cost_usd"] == 7.5
    assert first["gross_pnl_usd"] == pytest.approx(-500.0)
    assert first["net_pnl_usd"] == pytest.approx(-507.5)
    assert first["risk_state"] == "active"
    second = module.append_session_observation(
        _session(
            "2026-09-15T00:00:00Z",
            "2026-09-16T00:00:00Z",
            open_price=3.1,
            next_open=3.6,
        ),
        ledger=ledger,
        recorded_at="2026-09-16T00:00:01Z",
    )
    assert second["target_position"] == -0.5
    assert second["transaction_cost_usd"] == 0.0
    assert second["gross_pnl_usd"] == pytest.approx(-2500.0)
    assert second["daily_loss_usd"] == pytest.approx(2500.0)
    assert second["risk_state"] == "killed"
    assert "daily_loss_limit" in second["kill_reason"]
    third = module.append_session_observation(
        _session(
            "2026-09-16T00:00:00Z",
            "2026-09-17T00:00:00Z",
            open_price=3.6,
            next_open=3.7,
        ),
        ledger=ledger,
        recorded_at="2026-09-17T00:00:01Z",
    )
    assert third["target_position"] == 0.0
    assert third["risk_shutdown"] is True
    assert third["order_delta"] == 0.5
    assert third["transaction_cost_usd"] == 7.5
    assert third["net_pnl_usd"] == -7.5
    assert third["risk_state"] == "killed"
    status = module.ledger_status(ledger)
    assert status["session_events"] == 3
    assert status["net_pnl_usd"] == pytest.approx(-3015.0)
    assert status["transaction_cost_usd"] == pytest.approx(15.0)
    assert status["max_daily_loss_usd"] == pytest.approx(2500.0)
    assert status["max_daily_loss_fraction"] == pytest.approx(0.025)
    assert status["risk_state"] == "killed"
    assert status["kill_triggered"] is True
    assert status["unauthorized_post_kill_restart_count"] == 0


def test_new_decision_cannot_ignore_persisted_kill_state(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module), ledger=ledger, recorded_at="2026-09-13T12:00:01Z"
    )
    module.append_session_observation(
        _session(
            "2026-09-14T00:00:00Z",
            "2026-09-15T00:00:00Z",
            open_price=3.0,
            next_open=3.1,
        ),
        ledger=ledger,
        recorded_at="2026-09-15T00:00:01Z",
    )
    module.append_session_observation(
        _session(
            "2026-09-15T00:00:00Z",
            "2026-09-16T00:00:00Z",
            open_price=3.1,
            next_open=3.6,
        ),
        ledger=ledger,
        recorded_at="2026-09-16T00:00:01Z",
    )
    decision = _decision(module, "prospective-2")
    decision["decision_timestamp"] = "2026-09-15T23:59:00Z"
    decision["planned_fill_timestamp"] = "2026-09-16T00:00:00Z"
    decision["target_end_timestamp"] = "2026-09-23T00:00:00Z"
    decision["prior_position"] = -0.5
    with pytest.raises(ValueError, match="risk_state"):
        module.append_decision(
            decision, ledger=ledger, recorded_at="2026-09-15T23:59:01Z"
        )


def test_landed_refreeze_still_blocks_operational_derivation_until_phase_activation(
    tmp_path: Path,
) -> None:
    module = _module()
    contract = json.loads(module.CONTRACT.read_text(encoding="utf-8"))
    serving = contract["prospective_serving_contract"]
    assert serving["status"] == "frozen_active"
    assert serving["landing"] == {
        "pull_request": 381,
        "head_sha": "a8dfeb67614945f3e764d8ade39ac9f7eeb63095",
        "merge_commit_sha": "969c2ec957e249d8b405a4b73d851e6321c5639b",
        "merged_at": "2026-09-12T18:07:04Z",
    }
    with pytest.raises(ValueError, match="active prospective-evidence state"):
        module.derive_and_append_decision(
            {},
            checkpoint_root=tmp_path,
            databento_root=tmp_path,
            **_runtime_args(tmp_path),
            ledger=tmp_path / "prospective.jsonl",
        )


def test_direct_decision_append_is_blocked_until_phase_activation(tmp_path: Path) -> None:
    module = _module()
    with pytest.raises(ValueError, match="active prospective-evidence state"):
        module.append_decision(
            _decision(module),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-13T12:00:01Z",
        )


def test_operational_decision_wires_internal_source_and_specialist_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    observed: dict[str, object] = {}

    class _Runtime:
        def __init__(self, **kwargs):
            observed["runtime_kwargs"] = kwargs

        def generate(self, contexts):
            observed["contexts"] = contexts
            return {"generated_specialists": True}

    class _Derivation:
        PinnedSpecialistServingRuntime = _Runtime

        @staticmethod
        def prospective_kronos_path_eligible(index):
            observed["origin_index"] = index
            return True

        @staticmethod
        def verified_databento_source_snapshot(root, *, required_trade_date):
            observed["source_root"] = root
            observed["source_date"] = required_trade_date
            return {
                "sha256": "b" * 64,
                "latest_trade_date": "2026-09-13",
                "complete": True,
                "manifest": {"files": []},
            }

        @staticmethod
        def load_specialist_histories_from_databento(root, *, source_snapshot, retrieved_at):
            observed["history_args"] = (root, source_snapshot, retrieved_at)
            return "canonical-history", "ohlcv-history"

        @staticmethod
        def build_specialist_serving_contexts(canonical, ohlcv, **kwargs):
            observed["context_args"] = (canonical, ohlcv, kwargs)
            return {"serving_context": True}

        @staticmethod
        def load_verified_training_origins(root):
            observed["training_root"] = root
            return "training-origins"

        @staticmethod
        def derive_decision(bundle, **kwargs):
            observed["derived_bundle"] = bundle
            observed["derive_kwargs"] = kwargs
            return _decision(module)

    monkeypatch.setattr(module, "_derivation_module", lambda: _Derivation)
    monkeypatch.setattr(module, "_utc_now", lambda: "2026-09-13T12:00:01+00:00")
    bundle = {
        "decision_timestamp": "2026-09-13T12:00:00Z",
        "planned_fill_timestamp": "2026-09-14T00:00:00Z",
        "target_session_timestamps": [
            "2026-09-15T00:00:00Z",
            "2026-09-16T00:00:00Z",
            "2026-09-17T00:00:00Z",
            "2026-09-18T00:00:00Z",
            "2026-09-19T00:00:00Z",
        ],
        "current_origin": {
            "trade_date": "2026-09-13T00:00:00Z",
            "available_at": "2026-09-13T11:59:00Z",
            "contract_id": "NGX6",
            "features": {},
        },
    }
    result = module.derive_and_append_decision(
        bundle,
        checkpoint_root=tmp_path / "checkpoint",
        databento_root=tmp_path / "databento",
        timesfm_runtime_root=tmp_path / "timesfm-runtime",
        timesfm_source_zip=tmp_path / "timesfm-source.zip",
        timesfm_cache_dir=tmp_path / "timesfm-cache",
        kronos_source_root=tmp_path / "kronos-source",
        kronos_cache_dir=tmp_path / "kronos-cache",
        ledger=ledger,
    )

    assert result["event_type"] == "decision"
    derived = observed["derived_bundle"]
    assert isinstance(derived, dict)
    assert derived["source_snapshot"]["sha256"] == "b" * 64
    assert derived["specialists"] == {"generated_specialists": True}
    assert observed["contexts"] == {"serving_context": True}
    assert observed["derive_kwargs"] == {
        "training_origins": "training-origins",
        "prior_position": 0.0,
        "risk_state": "active",
        "origin_sequence_index": 0,
    }


def test_operational_decision_records_deadline_miss_instead_of_late_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"

    class _Runtime:
        def __init__(self, **kwargs):
            pass

        def generate(self, contexts):
            return {"generated_specialists": True}

    class _Derivation:
        PinnedSpecialistServingRuntime = _Runtime

        @staticmethod
        def prospective_kronos_path_eligible(index):
            return True

        @staticmethod
        def verified_databento_source_snapshot(root, *, required_trade_date):
            return {
                "sha256": "b" * 64,
                "latest_trade_date": "2026-09-13",
                "complete": True,
                "manifest": {"files": []},
            }

        @staticmethod
        def load_specialist_histories_from_databento(root, *, source_snapshot, retrieved_at):
            return "canonical-history", "ohlcv-history"

        @staticmethod
        def build_specialist_serving_contexts(canonical, ohlcv, **kwargs):
            return {"serving_context": True}

        @staticmethod
        def load_verified_training_origins(root):
            return "training-origins"

        @staticmethod
        def derive_decision(bundle, **kwargs):
            return _decision(module)

    monkeypatch.setattr(module, "_derivation_module", lambda: _Derivation)
    monkeypatch.setattr(module, "_utc_now", lambda: "2026-09-14T00:00:01+00:00")
    result = module.derive_and_append_decision(
        {
            "decision_timestamp": "2026-09-13T12:00:00Z",
            "planned_fill_timestamp": "2026-09-14T00:00:00Z",
            "target_session_timestamps": [
                "2026-09-15T00:00:00Z",
                "2026-09-16T00:00:00Z",
                "2026-09-17T00:00:00Z",
                "2026-09-18T00:00:00Z",
                "2026-09-19T00:00:00Z",
            ],
            "current_origin": {
                "trade_date": "2026-09-13T00:00:00Z",
                "available_at": "2026-09-13T11:59:00Z",
                "contract_id": "NGX6",
                "features": {},
            },
        },
        checkpoint_root=tmp_path / "checkpoint",
        databento_root=tmp_path / "databento",
        timesfm_runtime_root=tmp_path / "timesfm-runtime",
        timesfm_source_zip=tmp_path / "timesfm-source.zip",
        timesfm_cache_dir=tmp_path / "timesfm-cache",
        kronos_source_root=tmp_path / "kronos-source",
        kronos_cache_dir=tmp_path / "kronos-cache",
        ledger=ledger,
    )

    assert result["event_type"] == "origin_miss"
    assert result["miss_reason"] == "serving_deadline_missed"
    assert module.ledger_status(ledger)["decision_events"] == 0
    assert module.ledger_status(ledger)["missed_origins"] == 1


def test_active_serving_contract_rejects_decision_before_its_landing(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path, merged_at="2026-09-13T13:00:00Z")
    with pytest.raises(ValueError, match="landed serving freeze"):
        module.append_decision(
            _decision(module),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-13T13:00:01Z",
        )


def test_active_serving_contract_rejects_frozen_configuration_drift(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    payload = json.loads(module.CONTRACT.read_text(encoding="utf-8"))
    payload["bound_configuration_sha256"]["models"] = "0" * 64
    module.CONTRACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen configuration drift: models"):
        module.append_decision(
            _decision(module),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-13T12:00:01Z",
        )


def test_decision_must_be_recorded_before_planned_fill(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    with pytest.raises(ValueError, match="before its planned fill"):
        module.append_decision(
            _decision(module),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-14T00:00:00Z",
        )


def test_operational_derivation_rejects_caller_source_snapshot(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    with pytest.raises(ValueError, match="caller-supplied source_snapshot"):
        module.derive_and_append_decision(
            {"source_snapshot": {}},
            checkpoint_root=tmp_path,
            databento_root=tmp_path,
            **_runtime_args(tmp_path),
            ledger=tmp_path / "prospective.jsonl",
        )


def test_active_contract_requires_verified_specialist_runtime_proof(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    payload = json.loads(module.CONTRACT.read_text(encoding="utf-8"))
    payload["prospective_serving_contract"]["specialist_runtime_proof"] = {
        "status": "required_before_activation"
    }
    module.CONTRACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="runtime is not verified"):
        module.append_decision(
            _decision(module),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-13T12:00:01Z",
        )


def test_operational_derivation_rejects_caller_specialist_outputs(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    with pytest.raises(ValueError, match="caller-supplied specialist outputs"):
        module.derive_and_append_decision(
            {"specialists": {"timesfm_point_return": -0.01}},
            checkpoint_root=tmp_path,
            databento_root=tmp_path,
            **_runtime_args(tmp_path),
            ledger=tmp_path / "prospective.jsonl",
        )


def test_operational_derivation_requires_decision_time_inputs(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    with pytest.raises(ValueError, match="operational prospective derivation missing fields"):
        module.derive_and_append_decision(
            {},
            checkpoint_root=tmp_path,
            databento_root=tmp_path,
            **_runtime_args(tmp_path),
            ledger=tmp_path / "prospective.jsonl",
        )


def test_missed_fresh_origin_advances_cadence_and_cannot_be_backfilled(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    missed = module.record_origin_miss(
        decision_timestamp="2026-09-13T23:59:00Z",
        planned_fill_timestamp="2026-09-14T00:00:00Z",
        source_snapshot_sha256="a" * 64,
        miss_reason="serving_deadline_missed",
        ledger=ledger,
        recorded_at="2026-09-14T00:00:01Z",
    )
    assert missed["event_type"] == "origin_miss"
    assert missed["prospective_origin_index"] == 0
    assert missed["path_counter_advanced"] is True
    assert missed["kronos_path_eligible"] is True

    decision = _decision(module, "prospective-2")
    decision["decision_timestamp"] = "2026-09-14T23:59:00Z"
    decision["planned_fill_timestamp"] = "2026-09-15T00:00:00Z"
    decision["target_end_timestamp"] = "2026-09-22T00:00:00Z"
    decision["prospective_origin_index"] = 1
    decision["kronos_path_eligible"] = False
    decision["policy_modifiers"] = []
    decision["intended_position"] = -1.0
    decision["derivation"]["origin_sequence_index"] = 1
    decision["derivation"]["kronos_path_eligible"] = False
    appended = module.append_decision(
        decision,
        ledger=ledger,
        recorded_at="2026-09-14T23:59:01Z",
    )
    assert appended["prospective_origin_index"] == 1

    with pytest.raises(ValueError, match="already has an origin record"):
        module.append_decision(
            _decision(module, "late-backfill"),
            ledger=ledger,
            recorded_at="2026-09-13T23:59:30Z",
        )
    status = module.ledger_status(ledger)
    assert status["missed_origins"] == 1
    assert status["decision_events"] == 1


def test_session_append_is_blocked_until_phase_activation(tmp_path: Path) -> None:
    module = _module()
    with pytest.raises(ValueError, match="active prospective-evidence state"):
        module.append_session_observation(
            _session(
                "2026-09-14T00:00:00Z",
                "2026-09-15T00:00:00Z",
                open_price=3.0,
                next_open=3.1,
            ),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-15T00:00:01Z",
        )


def test_session_append_cannot_precede_serving_landing(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path, merged_at="2026-09-14T01:00:00Z")
    with pytest.raises(ValueError, match="after the landed serving freeze"):
        module.append_session_observation(
            _session(
                "2026-09-14T00:00:00Z",
                "2026-09-15T00:00:00Z",
                open_price=3.0,
                next_open=3.1,
            ),
            ledger=tmp_path / "prospective.jsonl",
            recorded_at="2026-09-15T00:00:01Z",
        )


def test_operational_session_rejects_caller_execution_evidence(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    with pytest.raises(ValueError, match="caller-supplied execution evidence"):
        module.derive_and_append_session_observation(
            _session(
                "2026-09-14T00:00:00Z",
                "2026-09-15T00:00:00Z",
                open_price=3.0,
                next_open=3.1,
            ),
            databento_root=tmp_path,
            ledger=tmp_path / "prospective.jsonl",
        )


def test_operational_session_requires_internal_contract_identity(tmp_path: Path) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    with pytest.raises(RuntimeError, match="internally established held contract"):
        module.derive_and_append_session_observation(
            {
                "session_timestamp": "2026-09-14T00:00:00Z",
                "next_session_timestamp": "2026-09-15T00:00:00Z",
            },
            databento_root=tmp_path,
            ledger=tmp_path / "prospective.jsonl",
        )


def test_operational_session_derives_internal_prices_and_records_actual_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    _activate_contract(module, tmp_path)
    ledger = tmp_path / "prospective.jsonl"
    module.append_decision(
        _decision(module),
        ledger=ledger,
        recorded_at="2026-09-13T12:00:01Z",
    )
    monkeypatch.setattr(module, "_utc_now", lambda: "2026-09-15T00:00:01Z", raising=False)

    class _Derivation:
        @staticmethod
        def derive_session_observation_from_databento(*args, **kwargs):
            assert kwargs["current_contract_id"] == "NGX6"
            assert kwargs["next_selected_contract_id"] == "NGX6"
            return _session(
                "2026-09-14T00:00:00Z",
                "2026-09-15T00:00:00Z",
                open_price=3.0,
                next_open=3.1,
            )

    monkeypatch.setattr(module, "_derivation_module", lambda: _Derivation)
    result = module.derive_and_append_session_observation(
        {
            "session_timestamp": "2026-09-14T00:00:00Z",
            "next_session_timestamp": "2026-09-15T00:00:00Z",
        },
        databento_root=tmp_path,
        ledger=ledger,
    )
    assert result["recorded_at"] == "2026-09-15T00:00:01+00:00"
    assert result["contract_id"] == "NGX6"
    assert result["open_price"] == pytest.approx(3.0)
    assert result["next_open_same_contract"] == pytest.approx(3.1)


def test_operational_cli_forbids_recorded_at_and_manual_outcome() -> None:
    module = _module()
    assert not hasattr(module, "append_outcome")
    parser = module._parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "derive-decision",
            "bundle.json",
            "--checkpoint-root",
            "checkpoint",
            "--databento-root",
            "databento",
            "--recorded-at",
            "2026-09-13T12:00:01Z",
        ])
    with pytest.raises(SystemExit):
        parser.parse_args([
            "derive-session",
            "bundle.json",
            "--databento-root",
            "databento",
            "--recorded-at",
            "2026-09-15T00:00:01Z",
        ])
    with pytest.raises(SystemExit):
        parser.parse_args(["outcome", "payload.json"])
