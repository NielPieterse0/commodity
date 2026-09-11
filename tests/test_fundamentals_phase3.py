from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import commodity.cli as commodity_cli
from commodity import phase3_runtime
from commodity.fundamentals_phase3 import (
    PHYSICAL_FEATURES,
    Phase3FundamentalsError,
    augment_market_features_with_physical,
    decide_phase3_survival,
    load_bhlr_physical_vintages,
)
from commodity.phase3_runtime import Phase3RuntimeError, validate_phase3_authority


def _member_bytes(base: float) -> bytes:
    matrix = np.arange(12 * 8, dtype=float).reshape(12, 8) + base
    buf = io.StringIO()
    np.savetxt(buf, matrix)
    return buf.getvalue().encode("utf-8")


def _source_zip(path: Path) -> tuple[dict[str, str], dict[str, bytes]]:
    members = {
        "production": _member_bytes(100.0),
        "storage": _member_bytes(200.0),
        "consumption": _member_bytes(300.0),
    }
    names = {
        "production": "BHLR_nowcasts/PROD_DRY.txt",
        "storage": "BHLR_nowcasts/STORE_WORK.txt",
        "consumption": "BHLR_nowcasts/CONS_TOT.txt",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for key, name in names.items():
            archive.writestr(name, members[key])
    return (
        {key: hashlib.sha256(value).hexdigest() for key, value in members.items()},
        members,
    )


def _cfg(member_hashes: dict[str, str]) -> dict[str, object]:
    return {
        "source": {
            "members": {
                "production": {"path": "BHLR_nowcasts/PROD_DRY.txt", "sha256": member_hashes["production"]},
                "storage": {"path": "BHLR_nowcasts/STORE_WORK.txt", "sha256": member_hashes["storage"]},
                "consumption": {"path": "BHLR_nowcasts/CONS_TOT.txt", "sha256": member_hashes["consumption"]},
            },
            "first_vintage_month": "2000-01",
            "first_origin_row": 2,
            "first_origin_column": 1,
        },
        "evidence_boundary": {"last_allowed_trade_date": "2000-04-30"},
    }


def test_loads_only_frozen_physical_diagonal_and_month_end_availability(tmp_path: Path) -> None:
    source = tmp_path / "physical.zip"
    hashes, _ = _source_zip(source)
    frame, provenance = load_bhlr_physical_vintages(source, _cfg(hashes))

    assert frame["origin_month"].tolist() == ["2000-01", "2000-02", "2000-03", "2000-04"]
    assert frame["feature_fund_log_production"].iloc[0] == pytest.approx(np.log(117.0))
    assert frame["feature_fund_log_storage"].iloc[1] == pytest.approx(np.log(226.0))
    assert frame["available_at"].iloc[0] == pd.Timestamp("2000-01-31T23:59:00Z")
    assert provenance["member_sha256"] == hashes
    assert "NG_HENRY" not in json.dumps(provenance)


def test_rejects_member_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "physical.zip"
    hashes, _ = _source_zip(source)
    cfg = _cfg(hashes)
    cfg["source"]["members"]["storage"]["sha256"] = "0" * 64
    with pytest.raises(Phase3FundamentalsError, match="hash mismatch"):
        load_bhlr_physical_vintages(source, cfg)


def test_loads_extracted_predictor_package_without_reading_other_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "physical.zip"
    hashes, members = _source_zip(archive_path)
    extracted = tmp_path / "source"
    target = extracted / "BHLR_nowcasts"
    target.mkdir(parents=True)
    names = {"production": "PROD_DRY.txt", "storage": "STORE_WORK.txt", "consumption": "CONS_TOT.txt"}
    for key, name in names.items():
        (target / name).write_bytes(members[key])
    (target / "NG_HENRY.txt").write_bytes(b"not-a-predictor-and-must-not-be-read")
    frame, provenance = load_bhlr_physical_vintages(extracted, _cfg(hashes))
    assert len(frame) == 4
    assert provenance["source_role"] == "predictor_only_bhlr_realtime_nowcasts"


def test_strict_pit_join_never_uses_same_timestamp() -> None:
    market = pd.DataFrame({
        "trade_date": pd.to_datetime(["2000-02-01", "2000-03-01"], utc=True),
        "available_at": pd.to_datetime(["2000-01-31T23:59Z", "2000-03-01T00:00Z"], utc=True),
        "feature_ret_1": [0.1, 0.2],
    })
    physical = pd.DataFrame({
        "origin_month": ["1999-12", "2000-01", "2000-02"],        "available_at": pd.to_datetime([
            "1999-12-31T23:59Z", "2000-01-31T23:59Z", "2000-02-29T23:59Z"
        ], utc=True),
        "feature_fund_log_production": [1.0, 2.0, 3.0],
        "feature_fund_log_storage": [4.0, 5.0, 6.0],
        "feature_fund_log_consumption": [7.0, 8.0, 9.0],
    })
    joined, diagnostics = augment_market_features_with_physical(market, physical)
    assert joined["physical_origin_month"].tolist() == ["1999-12", "2000-02"]
    assert diagnostics["rows"] == 2
    assert diagnostics["missing_rows"] == 0
    assert (joined["physical_available_at"] < joined["available_at"]).all()


def test_rejects_market_features_after_protected_cutoff() -> None:
    market = pd.DataFrame({
        "trade_date": pd.to_datetime(["2023-01-02"], utc=True),
        "available_at": pd.to_datetime(["2023-01-02T23:59Z"], utc=True),
    })
    physical = pd.DataFrame({
        "origin_month": ["2022-12"],
        "available_at": pd.to_datetime(["2022-12-31T23:59Z"], utc=True),
        "feature_fund_log_production": [1.0],
        "feature_fund_log_storage": [2.0],
        "feature_fund_log_consumption": [3.0],
    })
    with pytest.raises(Phase3FundamentalsError, match="protected cutoff"):
        augment_market_features_with_physical(market, physical, cutoff="2022-12-31")

def test_survival_rule_requires_repeatability_and_preserves_risk_alternative() -> None:
    economic = decide_phase3_survival(
        baseline_pnl=100.0,
        baseline_drawdown=0.10,
        challenger_pnl=105.0,
        challenger_drawdown=0.11,
        block_deltas=[10.0, 1.0, -6.0],
    )
    assert economic["retained"] is True
    assert economic["route"] == "economic"

    risk = decide_phase3_survival(
        baseline_pnl=100.0,
        baseline_drawdown=0.10,
        challenger_pnl=96.0,
        challenger_drawdown=0.07,
        block_deltas=[-1.0, 1.0, 0.0],
    )
    assert risk["retained"] is True
    assert risk["route"] == "risk"

    rejected = decide_phase3_survival(
        baseline_pnl=100.0,
        baseline_drawdown=0.10,
        challenger_pnl=110.0,
        challenger_drawdown=0.05,
        block_deltas=[12.0, -1.0, -1.0],
    )
    assert rejected["retained"] is False

def _authority_fixture() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    features = ["feature_ret_1", "feature_ret_5"]
    phase3 = {
        "evidence_boundary": {
            "protected_confirmation_accessed": False,
            "last_allowed_trade_date": "2022-12-31",
        },
        "baseline": {"candidate_id": "histgb-core-v1", "freeze_sha256": "freeze"},
        "challenger": {"physical_features": list(PHYSICAL_FEATURES)},
    }
    phase2 = {"feature_sets": {"core": features}}
    result = {
        "baseline_freeze": {"candidate_id": "histgb-core-v1", "freeze_sha256": "freeze"},
        "evaluation": {"final_baseline": {"feature_columns": features}},
    }
    return phase3, phase2, result


def test_validate_phase3_authority_accepts_exact_frozen_contract() -> None:
    phase3, phase2, result = _authority_fixture()
    authority = validate_phase3_authority(phase3, phase2, result)
    assert authority == {
        "candidate_id": "histgb-core-v1",
        "freeze_sha256": "freeze",
        "phase2_feature_columns": ["feature_ret_1", "feature_ret_5"],
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p3, p2, r: p3["evidence_boundary"].update(protected_confirmation_accessed=True), "protected confirmation"),
        (lambda p3, p2, r: p3["evidence_boundary"].update(last_allowed_trade_date="2023-01-01"), "development boundary"),
        (lambda p3, p2, r: r["baseline_freeze"].update(candidate_id="other"), "candidate identity"),
        (lambda p3, p2, r: r["baseline_freeze"].update(freeze_sha256="other"), "freeze identity"),
        (lambda p3, p2, r: r["evaluation"]["final_baseline"].update(feature_columns=["other"]), "feature contract"),
        (lambda p3, p2, r: p3["challenger"].update(physical_features=["other"]), "physical feature set"),
    ],
)
def test_validate_phase3_authority_rejects_drift(mutate, message: str) -> None:
    phase3, phase2, result = _authority_fixture()
    mutate(phase3, phase2, result)
    with pytest.raises(Phase3RuntimeError, match=message):
        validate_phase3_authority(phase3, phase2, result)


def test_pit_join_accepts_cutoff_but_rejects_mixed_post_cutoff_frame() -> None:
    physical = pd.DataFrame({
        "origin_month": ["2022-11"],
        "available_at": pd.to_datetime(["2022-11-30T23:59Z"], utc=True),
        **{name: [1.0] for name in PHYSICAL_FEATURES},
    })
    allowed = pd.DataFrame({
        "trade_date": pd.to_datetime(["2022-12-31"], utc=True),
        "available_at": pd.to_datetime(["2022-12-31T12:00Z"], utc=True),
    })
    joined, diagnostics = augment_market_features_with_physical(allowed, physical)
    assert diagnostics["coverage_fraction"] == 1.0
    assert joined["physical_origin_month"].tolist() == ["2022-11"]

    mixed = pd.concat([
        allowed,
        pd.DataFrame({
            "trade_date": pd.to_datetime(["2023-01-01"], utc=True),
            "available_at": pd.to_datetime(["2023-01-01T12:00Z"], utc=True),
        }),
    ], ignore_index=True)
    with pytest.raises(Phase3FundamentalsError, match="protected cutoff"):
        augment_market_features_with_physical(mixed, physical)


@pytest.mark.parametrize(
    ("challenger_pnl", "drawdown", "deltas", "expected_route"),
    [
        (100.0, 0.05, [1.0, 0.0, -1.0], "risk"),
        (95.0, 0.08, [1.0, 0.0, -1.0], "risk"),
        (95.0, 0.0800001, [1.0, 0.0, -1.0], "rejected"),
        (110.0, 0.05, [1.0, -1.0, -1.0], "rejected"),
    ],
)
def test_survival_rule_threshold_boundaries(
    challenger_pnl: float,
    drawdown: float,
    deltas: list[float],
    expected_route: str,
) -> None:
    result = decide_phase3_survival(
        baseline_pnl=100.0,
        baseline_drawdown=0.10,
        challenger_pnl=challenger_pnl,
        challenger_drawdown=drawdown,
        block_deltas=deltas,
    )
    assert result["route"] == expected_route
    assert result["retained"] is (expected_route != "rejected")
    assert result["nonnegative_incremental_outer_blocks"] == sum(value >= 0.0 for value in deltas)


def test_missing_physical_member_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "physical.zip"
    hashes, members = _source_zip(source)
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("BHLR_nowcasts/PROD_DRY.txt", members["production"])
        archive.writestr("BHLR_nowcasts/STORE_WORK.txt", members["storage"])
    with pytest.raises(Phase3FundamentalsError, match="physical source member is missing"):
        load_bhlr_physical_vintages(source, _cfg(hashes))


def test_zip_loader_reads_only_authorized_predictor_members(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "physical.zip"
    hashes, _ = _source_zip(source)
    observed: list[str] = []
    original = zipfile.ZipFile.read

    def tracked_read(self, name, *args, **kwargs):
        observed.append(str(name))
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", tracked_read)
    load_bhlr_physical_vintages(source, _cfg(hashes))
    assert observed == [
        "BHLR_nowcasts/PROD_DRY.txt",
        "BHLR_nowcasts/STORE_WORK.txt",
        "BHLR_nowcasts/CONS_TOT.txt",
    ]
    assert all("HENRY" not in item for item in observed)


def _patch_phase3_runtime(monkeypatch, *, session_hash="session", feature_hash="features", coverage=1.0, baseline_shift=0.0):
    core = ["feature_ret_1", "feature_vol_20"]
    blocks = [
        {"id": "b1", "start": "2017-01-01", "end": "2018-12-31"},
        {"id": "b2", "start": "2019-01-01", "end": "2020-12-31"},
        {"id": "b3", "start": "2021-01-01", "end": "2022-12-31"},
    ]
    phase2_cfg = {
        "feature_sets": {"core": core},
        "candidates": [{"id": "histgb-core-v1", "feature_set": "core", "model": "hist_gb", "parameters": {}}],
        "execution_contract": {"horizon_sessions": 5},
        "validation": {"outer_blocks": blocks},
    }
    phase2_result = {
        "baseline_freeze": {"candidate_id": "histgb-core-v1", "freeze_sha256": "freeze", "session_path_sha256": "session", "features_sha256": "features"},
        "evaluation": {"final_baseline": {"feature_columns": core}},
    }
    phase3_cfg = {
        "schema_version": 1,
        "programme_id": "003-natural-gas-trading-decision-system",
        "authority": "test-authority",
        "claim_boundary": "development",
        "evidence_boundary": {"protected_confirmation_accessed": False, "last_allowed_trade_date": "2022-12-31"},
        "baseline": {"candidate_id": "histgb-core-v1", "freeze_sha256": "freeze", "expected_outer_net_pnl_usd": {"b1": 10.0, "b2": 20.0, "b3": 30.0}, "expected_aggregate_net_pnl_usd": 60.0, "volatility_regime_thresholds": {"low_upper": 0.02, "mid_upper": 0.04}},
        "challenger": {"candidate_id": "challenger", "model": "hist_gb", "parameters": {}, "physical_features": list(PHYSICAL_FEATURES)},
    }
    payloads = {"Phase-3 config": phase3_cfg, "Phase-2 config": phase2_cfg, "Phase-2 baseline result": phase2_result}
    monkeypatch.setattr(phase3_runtime, "_load_json", lambda path, label: payloads[label])
    session = pd.DataFrame({"trade_date": pd.to_datetime(["2017-01-02", "2019-01-02", "2021-01-04"], utc=True)})
    market = pd.DataFrame({
        "trade_date": session["trade_date"],
        "available_at": session["trade_date"] - pd.Timedelta(hours=1),
        "feature_ret_1": [0.1, 0.2, 0.3],
        "feature_vol_20": [0.01, 0.03, 0.05],
    })
    augmented = market.assign(**{name: [1.0, 1.1, 1.2] for name in PHYSICAL_FEATURES})
    monkeypatch.setattr(phase3_runtime, "reconstruct_market_history", lambda *a, **k: (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"provenance_sha256": "prov"}))
    monkeypatch.setattr(phase3_runtime, "build_phase2_inputs", lambda *a, **k: (session, market))
    monkeypatch.setattr(phase3_runtime, "_frame_sha256", lambda frame: session_hash if frame is session else feature_hash if frame is market else "other")
    physical = pd.DataFrame({"origin_month": ["2016-12"], "available_at": pd.to_datetime(["2016-12-31T23:59Z"]), **{name: [1.0] for name in PHYSICAL_FEATURES}})
    monkeypatch.setattr(phase3_runtime, "load_bhlr_physical_vintages", lambda *a, **k: (physical, {"source_role": "predictor_only"}))
    monkeypatch.setattr(phase3_runtime, "augment_market_features_with_physical", lambda *a, **k: (augmented, {"coverage_fraction": coverage, "rows": 3, "missing_rows": 0}))
    monkeypatch.setattr(phase3_runtime, "_load_inherited_risk_and_costs", lambda cfg: (SimpleNamespace(capital_usd=100000.0), {"base": object()}))
    def origins(session_path, features, **kwargs):
        available = set(core)
        if features is augmented:
            available.update(PHYSICAL_FEATURES)
        return features.copy(), available

    monkeypatch.setattr(phase3_runtime, "_build_segmented_decision_origins", origins)
    monkeypatch.setattr(phase3_runtime, "_canonicalize_one_origin_per_fill", lambda frame: (frame, {"input_origins": len(frame), "output_origins": len(frame), "collapsed": 0}))
    baseline_scores = [
        {"block_id": "b1", "net_pnl_usd": 10.0 + baseline_shift, "latest_training_target_end": "2016-12-31"},
        {"block_id": "b2", "net_pnl_usd": 20.0, "latest_training_target_end": "2018-12-31"},
        {"block_id": "b3", "net_pnl_usd": 30.0, "latest_training_target_end": "2020-12-31"},
    ]
    challenger_scores = [
        {"block_id": "b1", "net_pnl_usd": 8.0, "latest_training_target_end": "2016-12-31"},
        {"block_id": "b2", "net_pnl_usd": 22.0, "latest_training_target_end": "2018-12-31"},
        {"block_id": "b3", "net_pnl_usd": 31.0, "latest_training_target_end": "2020-12-31"},
    ]
    score_calls = {"count": 0}

    def score_blocks(*args, **kwargs):
        score_calls["count"] += 1
        scores = baseline_scores if score_calls["count"] == 1 else challenger_scores
        pnl = [row["net_pnl_usd"] for row in scores]
        ledger = pd.DataFrame({"outer_block_id": ["b1", "b2", "b3"], "trade_date": session["trade_date"], "net_pnl_usd": pnl, "execution_side_count": [1, 1, 1]})
        return scores, pd.DataFrame({"forecast": [1.0, 1.0, 1.0]}), ledger
    monkeypatch.setattr(phase3_runtime, "_score_blocks", score_blocks)
    monkeypatch.setattr(
        phase3_runtime,
        "summarize_ledger",
        lambda ledger, starting_capital_usd: {
            "net_pnl_usd": float(ledger["net_pnl_usd"].sum()),
            "max_drawdown_fraction": 0.05,
            "transaction_cost_usd": 0.0,
        },
    )
    return phase3_cfg


def test_phase3_runtime_emits_complete_development_result(monkeypatch, tmp_path: Path) -> None:
    _patch_phase3_runtime(monkeypatch)
    result = phase3_runtime.run_phase3_fundamentals(
        tmp_path / "phase3.json", tmp_path / "phase2.json", tmp_path / "result.json", tmp_path, tmp_path
    )
    assert result["protected_confirmation_accessed"] is False
    assert result["baseline_replay"]["identity_check"] == "passed"
    assert result["baseline_replay"]["aggregate"]["net_pnl_usd"] == 60.0
    assert result["challenger"]["aggregate"]["net_pnl_usd"] == 61.0
    assert result["disposition"]["route"] == "economic"
    assert result["result_sha256"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"session_hash": "drift"}, "session path identity drifted"),
        ({"feature_hash": "drift"}, "feature identity drifted"),
        ({"coverage": 0.5}, "physical block is incomplete"),
        ({"baseline_shift": 1.0}, "baseline b1 P&L drifted"),
    ],
)
def test_phase3_runtime_fails_closed_on_integration_drift(monkeypatch, tmp_path: Path, kwargs, message: str) -> None:
    _patch_phase3_runtime(monkeypatch, **kwargs)
    with pytest.raises(Phase3RuntimeError, match=message):
        phase3_runtime.run_phase3_fundamentals(
            tmp_path / "phase3.json",
            tmp_path / "phase2.json",
            tmp_path / "result.json",
            tmp_path,
            tmp_path,
        )


def test_phase3_cli_writes_new_result_and_forwards_arguments(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "nested" / "phase3.json"
    checkpoint = tmp_path / "checkpoints"
    observed: dict[str, object] = {}

    def fake_run(config3, config2, result2, databento, bhlr, **kwargs):
        observed.update({
            "config3": config3,
            "config2": config2,
            "result2": result2,
            "databento": databento,
            "bhlr": bhlr,
            **kwargs,
        })
        return {"disposition": {"retained": False, "route": "rejected"}, "value": 7}

    monkeypatch.setattr(commodity_cli, "run_phase3_fundamentals", fake_run)
    args = SimpleNamespace(
        databento_root=str(tmp_path / "db"),
        bhlr_root=str(tmp_path / "bhlr"),
        checkpoint_dir=str(checkpoint),
        heartbeat_seconds=12.5,
        output=str(output),
    )
    commodity_cli._phase3_fundamentals(args)
    assert json.loads(output.read_text(encoding="utf-8"))["value"] == 7
    assert observed["databento"] == tmp_path / "db"
    assert observed["bhlr"] == tmp_path / "bhlr"
    assert observed["checkpoint_dir"] == checkpoint
    assert observed["heartbeat_seconds"] == 12.5


def test_phase3_cli_refuses_to_overwrite_existing_result(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "phase3.json"
    output.write_text("preserve-me", encoding="utf-8")
    monkeypatch.setattr(
        commodity_cli,
        "run_phase3_fundamentals",
        lambda *a, **k: {"disposition": {"retained": False, "route": "rejected"}},
    )
    args = SimpleNamespace(
        databento_root=str(tmp_path / "db"),
        bhlr_root=str(tmp_path / "bhlr"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        heartbeat_seconds=30.0,
        output=str(output),
    )
    with pytest.raises(Phase3RuntimeError, match="refusing to overwrite"):
        commodity_cli._phase3_fundamentals(args)
    assert output.read_text(encoding="utf-8") == "preserve-me"
