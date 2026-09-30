from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from commodity.v2_coverage import (
    Issue448CoverageError,
    build_issue448_event_timing_features,
    build_issue448_market_structure_features,
    build_issue448_technical_features,
    evaluate_issue448_options_preflight,
    evaluate_issue448_storage_surprise_gate,
    issue448_family_outer_blocks,
    issue448_family_registry,
    issue448_source_dispositions,
    issue448_volatility_tail_handoff,
    load_issue448_contract,
    match_issue448_open_interest_to_contract_path,
    prepare_issue448_candidate_features,
    run_issue448_development_coverage,
)

PREREG_SHA = "4ea610d1f0b42e8cf8d77efd787d0a8a45d4bb2744318c2ba43be2a40c5239d7"
SOURCE_SHA = "c7bace7e8fc49116b45cfde6d1aa4df3bf0a6fec3375177a9d80362c08f286b9"


def _authority_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[1]
    programme = root / "research" / "programmes" / "004-v2-maximum-reproducible-one-month-return"
    return programme / "issue448-prereg-v2.json", programme / "issue448-source-feasibility-v2.json"


def test_issue448_contract_binds_frozen_authority_and_boundary() -> None:
    prereg, source = _authority_paths()
    contract = load_issue448_contract(prereg, source)

    assert contract.prereg_sha256 == PREREG_SHA
    assert contract.source_feasibility_sha256 == SOURCE_SHA
    assert contract.latest_allowed_trade_date == "2022-12-31"
    assert contract.protected_confirmation_accessed is False
    assert contract.prereg["authority"]["downstream_consumers"] == [427, 428, 429, 430]


def test_issue448_contract_exposes_preregistered_oi_availability_outer_lane() -> None:
    prereg, source = _authority_paths()
    contract = load_issue448_contract(prereg, source)

    family_outers = issue448_family_outer_blocks(contract)

    assert set(family_outers) == {"market_structure.open_interest"}
    oi_outers = family_outers["market_structure.open_interest"]
    assert [block["id"] for block in oi_outers] == ["outer-2020-oi", "outer-2021-2022"]
    assert [block["parent_control_outer_id"] for block in oi_outers] == [
        "outer-2019-2020",
        "outer-2021-2022",
    ]
    assert oi_outers[0]["selection_inner_block_ids"] == [
        "inner-2019-01-01-2019-12-31"
    ]
    assert oi_outers[1]["selection_inner_block_ids"] == [
        "inner-2019-01-01-2019-12-31",
        "inner-2020-01-01-2020-12-31",
    ]


def test_issue448_family_registry_matches_preregistered_grids() -> None:
    prereg, source = _authority_paths()
    registry = issue448_family_registry(load_issue448_contract(prereg, source))

    assert registry["ta.trend_momentum"]["ema_pairs"] == ((5, 20), (10, 40))
    assert registry["ta.trend_momentum"]["macd_style"] == ((12, 26, 9),)
    assert registry["ta.oscillator_mean_reversion"]["rsi_windows"] == (7, 14, 28)
    assert registry["ta.oscillator_mean_reversion"]["price_zscore_windows"] == (10, 20, 60)
    assert registry["ta.range_breakout"]["donchian_windows"] == (10, 20, 55)
    assert registry["ta.range_breakout"]["normalized_range_windows"] == (14, 28)
    assert registry["ta.range_breakout"]["alias_policy"] == "shared_normalized_range_family"
    assert registry["ta.volatility_envelope"]["atr_windows"] == (10, 20)
    assert registry["ta.volatility_envelope"]["bollinger_windows"] == (10, 20, 60)
    assert registry["ta.trend_strength"]["adx_windows"] == (14, 28)
    assert registry["ta.volume_confirmation"]["volume_zscore_windows"] == (20, 60)
    assert registry["ta.volume_confirmation"]["directional_volume_window"] == 20


def test_issue448_source_dispositions_preserve_hold_and_downstream_boundaries() -> None:
    prereg, source = _authority_paths()
    dispositions = issue448_source_dispositions(load_issue448_contract(prereg, source))

    assert dispositions["futures_open_interest"] == "GO_IMPLEMENT_PIT_STAT9"
    assert dispositions["storage_consensus_surprise"] == "HOLD_SOURCE_NOT_PROVEN"
    assert dispositions["options_implied"] == "GO_ZERO_SPEND_PREFLIGHT_HOLD_ACTIVATION"
    assert dispositions["eia_event_timing"] == "GO_EXISTING_AVAILABILITY_CONTRACT"
    assert dispositions["volatility_tail_specialists"] == "DOWNSTREAM_REQUIREMENT_REGISTERED"


def test_issue448_contract_rejects_protected_or_post_cutoff_mutation(tmp_path: Path) -> None:
    prereg, source = _authority_paths()
    prereg_payload = json.loads(prereg.read_text(encoding="utf-8"))
    source_payload = json.loads(source.read_text(encoding="utf-8"))

    prereg_payload["protected_confirmation_accessed"] = True
    bad_prereg = tmp_path / "prereg.json"
    bad_prereg.write_text(json.dumps(prereg_payload), encoding="utf-8")
    source_copy = tmp_path / "source.json"
    source_copy.write_text(json.dumps(source_payload), encoding="utf-8")
    with pytest.raises(Issue448CoverageError, match="protected"):
        load_issue448_contract(bad_prereg, source_copy)

    prereg_payload = json.loads(prereg.read_text(encoding="utf-8"))
    prereg_payload["latest_allowed_trade_date"] = "2023-01-01"
    bad_prereg.write_text(json.dumps(prereg_payload), encoding="utf-8")
    with pytest.raises(Issue448CoverageError, match="cutoff"):
        load_issue448_contract(bad_prereg, source_copy)


def test_issue448_contract_rejects_authority_hash_drift(tmp_path: Path) -> None:
    prereg, source = _authority_paths()
    prereg_copy = tmp_path / "prereg.json"
    prereg_copy.write_bytes(prereg.read_bytes())
    source_payload = json.loads(source.read_text(encoding="utf-8"))
    source_payload["decision"] += " altered"
    source_copy = tmp_path / "source.json"
    source_copy.write_text(json.dumps(source_payload), encoding="utf-8")

    with pytest.raises(Issue448CoverageError, match="SHA-256"):
        load_issue448_contract(prereg_copy, source_copy)


def _technical_fixture(rows: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=rows, freq="D", tz="UTC")
    step = np.arange(rows, dtype=float)
    settle = 3.0 + 0.01 * step + 0.05 * np.sin(step / 4.0)
    close = settle + 0.005 * np.cos(step / 3.0)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "available_at": dates + pd.Timedelta(hours=23),
            "settle": settle,
            "high": np.maximum(settle, close) + 0.04 + 0.005 * np.sin(step),
            "low": np.minimum(settle, close) - 0.04 - 0.005 * np.cos(step),
            "close": close,
            "volume": 1000.0 + 7.0 * step + 50.0 * np.sin(step / 5.0),
        }
    )


def _contract():
    prereg, source = _authority_paths()
    return load_issue448_contract(prereg, source)


def test_issue448_technical_features_cover_exact_registered_families() -> None:
    features, families = build_issue448_technical_features(_technical_fixture(), _contract())

    assert set(families) == {
        "ta.trend_momentum", "ta.oscillator_mean_reversion", "ta.range_breakout",
        "ta.volatility_envelope", "ta.trend_strength", "ta.volume_confirmation",
    }
    assert "feature_issue448_ema_gap_5_20" in families["ta.trend_momentum"]
    assert "feature_issue448_macd_12_26_9" in families["ta.trend_momentum"]
    assert "feature_issue448_rsi_14" in families["ta.oscillator_mean_reversion"]
    assert "feature_issue448_donchian_position_55" in families["ta.range_breakout"]
    assert "feature_issue448_normalized_range_14" in families["ta.range_breakout"]
    assert "feature_issue448_atr_20" in families["ta.volatility_envelope"]
    assert "feature_issue448_adx_28" in families["ta.trend_strength"]
    assert "feature_issue448_volume_zscore_60" in families["ta.volume_confirmation"]
    assert features.loc[features.index[-1], list(sum(families.values(), ()) )].notna().all()


def test_issue448_range_aliases_do_not_multiply_feature_families() -> None:
    features, families = build_issue448_technical_features(_technical_fixture(), _contract())
    range_columns = families["ta.range_breakout"]

    assert not any("stochastic" in column for column in features.columns)
    assert not any("williams" in column for column in features.columns)
    assert {column for column in range_columns if "normalized_range" in column} == {
        "feature_issue448_normalized_range_14",
        "feature_issue448_normalized_range_28",
    }
    registry = issue448_family_registry(_contract())
    assert registry["ta.range_breakout"]["alias_policy"] == "shared_normalized_range_family"


def test_issue448_technical_features_are_future_mutation_safe() -> None:
    source = _technical_fixture()
    first, families = build_issue448_technical_features(source, _contract())
    mutated = source.copy()
    mutated.loc[mutated.index[-1], ["settle", "high", "low", "close", "volume"]] = [99, 101, 98, 100, 999999]
    second, second_families = build_issue448_technical_features(mutated, _contract())

    assert families == second_families
    columns = list(sum(families.values(), ()))
    pd.testing.assert_frame_equal(first.loc[first.index[:-1], columns], second.loc[second.index[:-1], columns])


def test_issue448_technical_features_fail_closed_on_bad_availability() -> None:
    duplicate = _technical_fixture(80)
    duplicate.loc[duplicate.index[-1], "available_at"] = duplicate.loc[duplicate.index[-2], "available_at"]
    with pytest.raises(Issue448CoverageError, match="availability"):
        build_issue448_technical_features(duplicate, _contract())

    reversed_frame = _technical_fixture(80).iloc[::-1].reset_index(drop=True)
    with pytest.raises(Issue448CoverageError, match="chronological"):
        build_issue448_technical_features(reversed_frame, _contract())


def _curve_fixture(rows: int = 12) -> pd.DataFrame:
    dates = pd.date_range("2022-06-01", periods=rows, freq="D", tz="UTC")
    step = np.arange(rows, dtype=float)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "available_at": dates + pd.Timedelta(hours=23),
            "log_settle_m1": np.log(3.00 + 0.02 * step),
            "log_settle_m2": np.log(3.05 + 0.018 * step),
            "log_settle_m3": np.log(3.10 + 0.016 * step),
            "log_settle_m4": np.log(3.18 + 0.014 * step),
            "dte_m1": 25.0 - step % 10,
            "dte_m2": 55.0 - step % 10,
            "dte_m4": 115.0 - step % 10,
            "volume_m1": 1000.0 + 10.0 * step,
        }
    )


def _oi_fixture() -> pd.DataFrame:
    dates = pd.date_range("2022-06-01", periods=12, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "available_at": dates + pd.Timedelta(hours=22),
            "ts_ref": dates,
            "open_interest_m1": 5000.0 + 100.0 * np.arange(12),
        }
    )


def _positioning_fixture() -> pd.DataFrame:
    available = pd.to_datetime(["2022-05-31T20:00:00Z", "2022-06-07T20:00:00Z"])
    return pd.DataFrame(
        {
            "available_at": available,
            "open_interest": [10000.0, 11000.0],
            "managed_money_net": [1200.0, 1540.0],
            "producer_merchant_net": [-2100.0, -2420.0],
        }
    )


def test_issue448_market_structure_features_cover_registered_representations() -> None:
    features, families = build_issue448_market_structure_features(
        _curve_fixture(), _oi_fixture(), _positioning_fixture(), _contract()
    )

    assert set(families) == {
        "market_structure.carry_basis", "market_structure.curve",
        "market_structure.open_interest", "market_structure.positioning",
    }
    expected = {
        "feature_issue448_dte_normalized_m1_m2_log_basis",
        "feature_issue448_dte_normalized_m1_m4_log_basis",
        "feature_issue448_m1_m2_basis_momentum_1",
        "feature_issue448_m1_m2_basis_momentum_5",
        "feature_issue448_curvature_123",
        "feature_issue448_m1_m2_change_1",
        "feature_issue448_m1_m4_slope_change_1",
        "feature_issue448_log_oi_m1",
        "feature_issue448_oi_change_1",
        "feature_issue448_oi_change_5",
        "feature_issue448_volume_to_oi_m1",
        "feature_issue448_managed_money_net_pct_oi",
        "feature_issue448_managed_money_net_pct_oi_change_1report",
        "feature_issue448_producer_merchant_hedging_pressure",
        "feature_issue448_producer_merchant_hedging_pressure_change_1report",
    }
    assert expected.issubset(features.columns)
    assert features.iloc[-1][list(expected)].notna().all()


def test_issue448_open_interest_join_uses_publication_time_not_reference_time() -> None:
    curve = _curve_fixture(3)
    oi = pd.DataFrame(
        {
            "available_at": pd.to_datetime(["2022-06-01T22:00:00Z", "2022-06-02T23:30:00Z"]),
            "ts_ref": pd.to_datetime(["2022-06-01", "2022-06-02"], utc=True),
            "open_interest_m1": [5000.0, 9000.0],
        }
    )
    features, _ = build_issue448_market_structure_features(
        curve, oi, _positioning_fixture(), _contract()
    )
    assert features.loc[0, "feature_issue448_log_oi_m1"] == pytest.approx(np.log(5000.0))
    assert features.loc[1, "feature_issue448_log_oi_m1"] == pytest.approx(np.log(5000.0))
    assert features.loc[2, "feature_issue448_log_oi_m1"] == pytest.approx(np.log(9000.0))


def test_issue448_market_structure_preserves_zero_oi_as_missing_derived_value() -> None:
    oi = _oi_fixture()
    oi.loc[oi.index[3], "open_interest_m1"] = 0.0
    features, _ = build_issue448_market_structure_features(
        _curve_fixture(), oi, _positioning_fixture(), _contract()
    )

    assert pd.isna(features.loc[3, "feature_issue448_log_oi_m1"])
    assert pd.isna(features.loc[3, "feature_issue448_volume_to_oi_m1"])
    numeric = features.filter(like="feature_issue448_").select_dtypes(include=[np.number])
    assert not np.isinf(numeric.to_numpy()).any()


def test_issue448_market_structure_fails_closed_on_ambiguous_oi_publication() -> None:
    oi = _oi_fixture()
    oi.loc[oi.index[3], "available_at"] = pd.NaT
    with pytest.raises(Issue448CoverageError, match="open-interest availability"):
        build_issue448_market_structure_features(
            _curve_fixture(), oi, _positioning_fixture(), _contract()
        )


def test_issue448_positioning_join_never_uses_future_publication() -> None:
    positioning = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2022-05-31T20:00:00Z", "2022-06-02T23:30:00Z"]
            ),
            "open_interest": [10000.0, 10000.0],
            "managed_money_net": [1000.0, 3000.0],
            "producer_merchant_net": [-2000.0, -2000.0],
        }
    )
    features, _ = build_issue448_market_structure_features(
        _curve_fixture(3), _oi_fixture().iloc[:3].copy(), positioning, _contract()
    )
    column = "feature_issue448_managed_money_net_pct_oi"
    assert features.loc[1, column] == pytest.approx(0.1)
    assert features.loc[2, column] == pytest.approx(0.3)


def test_issue448_positioning_change_is_report_to_report_not_daily() -> None:
    features, _ = build_issue448_market_structure_features(
        _curve_fixture(), _oi_fixture(), _positioning_fixture(), _contract()
    )
    column = "feature_issue448_managed_money_net_pct_oi_change_1report"
    before_second_report = features.loc[5, column]
    after_second_report = features.loc[7, column]
    expected_change = (1540.0 / 11000.0) - (1200.0 / 10000.0)

    assert pd.isna(before_second_report)
    assert after_second_report == pytest.approx(expected_change)
    assert features.loc[8, column] == pytest.approx(expected_change)


def test_issue448_storage_surprise_gate_holds_without_true_consensus() -> None:
    held = evaluate_issue448_storage_surprise_gate(None, _contract())
    assert held["disposition"] == "HOLD"
    assert held["search_budget_consumed"] is False
    assert set(held["missing_gates"]) == {
        "historical PIT publication timestamp",
        "fixed consensus value before release",
        "2010-2022 usable depth",
        "private-research licensing permission",
        "reproducible source identity",
    }


def test_issue448_storage_surprise_rejects_synthetic_consensus_substitution() -> None:
    fake = {
        "expectation_kind": "seasonal_anomaly",
        "historical_pit_publication_timestamp": True,
        "fixed_consensus_value_before_release": True,
        "usable_depth_2010_2022": True,
        "private_research_licensing_permission": True,
        "reproducible_source_identity": True,
    }
    with pytest.raises(Issue448CoverageError, match="consensus substitution"):
        evaluate_issue448_storage_surprise_gate(fake, _contract())


def test_issue448_storage_surprise_can_activate_only_when_all_gates_pass() -> None:
    source = {
        "expectation_kind": "pre_release_market_consensus",
        "historical_pit_publication_timestamp": True,
        "fixed_consensus_value_before_release": True,
        "usable_depth_2010_2022": True,
        "private_research_licensing_permission": True,
        "reproducible_source_identity": True,
    }
    assert evaluate_issue448_storage_surprise_gate(source, _contract())["disposition"] == "SCORE"


def test_issue448_event_timing_respects_public_release_and_first_executable_decision() -> None:
    decisions = pd.to_datetime(
        ["2022-06-09T14:29:00Z", "2022-06-09T14:30:00Z", "2022-06-09T14:31:00Z"], utc=True
    )
    releases = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2022-06-02T14:30:00Z", "2022-06-09T14:30:00Z", "2022-06-16T14:30:00Z"],
                utc=True,
            )
        }
    )
    features = build_issue448_event_timing_features(decisions, releases, _contract())

    assert features.loc[0, "hours_to_next_release"] == pytest.approx(1.0 / 60.0)
    assert features.loc[1, "hours_to_next_release"] == pytest.approx(0.0)
    assert features.loc[1, "first_executable_session_after_release"] == 0.0
    assert features.loc[2, "hours_since_last_release"] == pytest.approx(1.0 / 60.0)
    assert features.loc[2, "first_executable_session_after_release"] == 1.0


def test_issue448_options_preflight_is_zero_spend_and_non_blocking() -> None:
    unknown_cost = evaluate_issue448_options_preflight(
        {
            "local_inventory": False,
            "metadata_schema_compatible": True,
            "quoted_cost_usd": None,
            "private_research_licensing_permission": True,
            "strike_expiry_depth_verified": False,
            "pit_timestamp_semantics_verified": True,
        },
        _contract(),
    )
    assert unknown_cost["activation_disposition"] == "HOLD"
    assert unknown_cost["v2_blocking"] is False
    assert unknown_cost["billable_acquisition_allowed"] is False

    zero_spend = evaluate_issue448_options_preflight(
        {
            "local_inventory": True,
            "metadata_schema_compatible": True,
            "quoted_cost_usd": 0.0,
            "private_research_licensing_permission": True,
            "strike_expiry_depth_verified": True,
            "pit_timestamp_semantics_verified": True,
        },
        _contract(),
    )
    assert zero_spend["preflight_disposition"] == "PASS_ZERO_SPEND"
    assert zero_spend["activation_disposition"] == "SCORE"
    assert zero_spend["billable_acquisition_allowed"] is False


def test_issue448_volatility_tail_handoff_is_fixed_for_downstream_issues() -> None:
    handoff = issue448_volatility_tail_handoff(_contract())

    assert handoff["downstream_issues"] == (427, 428, 430)
    assert handoff["specialists"] == ("ewma", "har", "garch_family")
    assert handoff["state_features"] == ("jump_intensity", "tail_loss_state", "vol_of_vol")
    assert handoff["evaluation_roles"] == (
        "direction", "trade_admission", "confidence", "risk_control"
    )


def _fake_issue448_evaluator(
    stage: str,
    outer_block_id: str,
    blocks: list[dict[str, str]],
    family: str,
    representation: str,
) -> dict[str, object]:
    score = {
        "rep-a": 0.0010,
        "rep-b": 0.0020,
        "rep-c": -0.0010,
    }.get(representation, 0.0)
    # Keep the outer estimate distinct so selection cannot accidentally use it.
    if stage == "outer_evaluation":
        score += 0.0003 if representation == "rep-b" else 0.05
    return {
        "status": "complete",
        "family": family,
        "representation": representation,
        "selection_blocks": [block["id"] for block in blocks],
        "monthly_score": {"mean_monthly_net_return": score},
        "matched_control": {"monthly_score": {"mean_monthly_net_return": 0.0}},
        "ablation": {"mean_monthly_net_return_delta": score},
        "complexity_rank": 1,
        "outer_block_id": outer_block_id,
    }


def test_issue448_development_coverage_selects_only_on_prior_inner_blocks() -> None:
    inner = [
        {"id": "inner-a", "start": "2015-01-01", "end": "2016-12-31"},
        {"id": "inner-b", "start": "2017-01-01", "end": "2018-12-31"},
        {"id": "inner-future", "start": "2021-01-01", "end": "2022-12-31"},
    ]
    outer = [{"id": "outer-2019-2020", "start": "2019-01-01", "end": "2020-12-31"}]
    result = run_issue448_development_coverage(
        contract=_contract(),
        family_candidates={"ta.test": ("rep-a", "rep-b", "rep-c")},
        held_families={},
        inner_blocks=inner,
        outer_blocks=outer,
        evaluator=_fake_issue448_evaluator,
    )

    row = result["family_results"]["ta.test"]["nested_outer"][0]
    assert row["selected_representation"] == "rep-b"
    assert row["selection_block_ids"] == ["inner-a", "inner-b"]
    assert row["outer_result"]["representation"] == "rep-b"
    assert row["outer_result"]["selection_blocks"] == ["outer-2019-2020"]


def test_issue448_development_coverage_uses_common_available_inner_support() -> None:
    inner = [
        {"id": "inner-2014", "start": "2014-01-01", "end": "2014-12-31"},
        {"id": "inner-2016", "start": "2016-01-01", "end": "2016-12-31"},
        {"id": "inner-2017", "start": "2017-01-01", "end": "2017-12-31"},
    ]
    outer = [{"id": "outer-2019-2020", "start": "2019-01-01", "end": "2020-12-31"}]
    calls: list[tuple[str, str, list[str]]] = []

    def supporter(outer_block, family, representations, prior_inner):
        assert family == "market_structure.open_interest"
        assert list(representations) == ["rep-a", "rep-b", "rep-c"]
        assert [block["id"] for block in prior_inner] == [
            "inner-2014", "inner-2016", "inner-2017"
        ]
        return {
            "available_representations": ["rep-a", "rep-b"],
            "held_representations": ["rep-c"],
            "common_selection_block_ids": ["inner-2017"],
            "representation_diagnostics": {
                "rep-c": {"status": "PRE_SOURCE_OR_INSUFFICIENT_HISTORY"}
            },
        }

    def evaluator(stage, outer_block_id, blocks, family, representation):
        calls.append((stage, representation, [block["id"] for block in blocks]))
        return _fake_issue448_evaluator(stage, outer_block_id, blocks, family, representation)

    result = run_issue448_development_coverage(
        contract=_contract(),
        family_candidates={"market_structure.open_interest": ("rep-a", "rep-b", "rep-c")},
        held_families={},
        inner_blocks=inner,
        outer_blocks=outer,
        evaluator=evaluator,
        selection_supporter=supporter,
    )

    row = result["family_results"]["market_structure.open_interest"]["nested_outer"][0]
    assert row["selection_block_ids"] == ["inner-2017"]
    assert row["selected_representation"] == "rep-b"
    assert ("inner_selection", "rep-c", ["inner-2017"]) not in calls
    assert calls[:2] == [
        ("inner_selection", "rep-a", ["inner-2017"]),
        ("inner_selection", "rep-b", ["inner-2017"]),
    ]
    support_holds = [trial for trial in result["trials"] if trial["stage"] == "selection_support_hold"]
    assert len(support_holds) == 1
    assert support_holds[0]["representation"] == "rep-c"


def test_issue448_development_coverage_skips_pre_source_outer_then_scores_later() -> None:
    inner = [
        {"id": "inner-2014", "start": "2014-01-01", "end": "2014-12-31"},
        {"id": "inner-2017", "start": "2017-01-01", "end": "2017-12-31"},
    ]
    outer = [
        {"id": "outer-2017-2018", "start": "2017-01-01", "end": "2018-12-31"},
        {"id": "outer-2019-2020", "start": "2019-01-01", "end": "2020-12-31"},
    ]

    def supporter(outer_block, family, representations, prior_inner):
        if outer_block["id"] == "outer-2017-2018":
            return {
                "available_representations": [],
                "held_representations": list(representations),
                "common_selection_block_ids": [],
            }
        return {
            "available_representations": list(representations),
            "held_representations": [],
            "common_selection_block_ids": ["inner-2017"],
        }

    result = run_issue448_development_coverage(
        contract=_contract(),
        family_candidates={"market_structure.open_interest": ("rep-a", "rep-b")},
        held_families={},
        inner_blocks=inner,
        outer_blocks=outer,
        evaluator=_fake_issue448_evaluator,
        selection_supporter=supporter,
    )

    family = result["family_results"]["market_structure.open_interest"]
    assert [row["outer_block"]["id"] for row in family["nested_outer"]] == [
        "outer-2019-2020"
    ]
    assert family["nested_outer"][0]["selection_block_ids"] == ["inner-2017"]
    assert family["skipped_outer"][0]["disposition"] == (
        "SKIP_INSUFFICIENT_PRIOR_FEATURE_SUPPORT"
    )
    assert family["disposition"] == "RETAIN_MATCHED_MARGINAL_VALUE"


def test_issue448_development_coverage_preserves_held_families_without_search() -> None:
    calls: list[tuple[str, str]] = []

    def evaluator(stage, outer_block_id, blocks, family, representation):
        calls.append((family, representation))
        return _fake_issue448_evaluator(stage, outer_block_id, blocks, family, representation)

    result = run_issue448_development_coverage(
        contract=_contract(),
        family_candidates={"ta.test": ("rep-a",)},
        held_families={
            "storage_consensus_surprise": "HOLD_SOURCE_NOT_PROVEN",
            "options_implied": "HOLD_ZERO_SPEND_PREFLIGHT_INCOMPLETE",
        },
        inner_blocks=[{"id": "inner-a", "start": "2015-01-01", "end": "2016-12-31"}],
        outer_blocks=[{"id": "outer-a", "start": "2017-01-01", "end": "2018-12-31"}],
        evaluator=evaluator,
    )

    assert calls == [("ta.test", "rep-a"), ("ta.test", "rep-a")]
    for family in ("storage_consensus_surprise", "options_implied"):
        held = result["family_results"][family]
        assert held["search_budget_consumed"] is False
        assert held["nested_outer"] == []
        assert held["disposition"].startswith("HOLD")


def test_issue448_development_coverage_has_complete_deterministic_trial_accounting() -> None:
    kwargs = {
        "contract": _contract(),
        "family_candidates": {"ta.test": ("rep-a", "rep-b")},
        "held_families": {"storage_consensus_surprise": "HOLD_SOURCE_NOT_PROVEN"},
        "inner_blocks": [
            {"id": "inner-a", "start": "2015-01-01", "end": "2016-12-31"}
        ],
        "outer_blocks": [
            {"id": "outer-a", "start": "2017-01-01", "end": "2018-12-31"}
        ],
        "evaluator": _fake_issue448_evaluator,
    }
    first = run_issue448_development_coverage(**kwargs)
    second = run_issue448_development_coverage(**kwargs)

    # 2 inner representation trials + 1 selected outer trial + 1 explicit held-family record.
    assert first["trial_count"] == 4
    assert len(first["trials"]) == 4
    assert first["trial_ledger_sha256"] == second["trial_ledger_sha256"]
    assert first["result_sha256"] == second["result_sha256"]
    assert first["latest_allowed_trade_date"] == "2022-12-31"
    assert first["protected_confirmation_accessed"] is False


def test_issue448_candidate_transform_keeps_exact_matched_control_rows() -> None:
    rows = 340
    dates = pd.date_range("2015-01-01", periods=rows, freq="D", tz="UTC")
    step = np.arange(rows, dtype=float)
    features = pd.DataFrame(
        {
            "trade_date": dates,
            "available_at": dates + pd.Timedelta(hours=23),
            "feature_ret_1": 0.001 * np.sin(step / 5),
            "feature_ret_5": 0.003 * np.sin(step / 9),
            "feature_ret_20": 0.01 * np.sin(step / 15),
            "feature_vol_5": 0.02 + 0.001 * np.cos(step / 7),
            "feature_vol_20": 0.03 + 0.001 * np.cos(step / 11),
            "feature_range_pct": 0.04 + 0.001 * np.sin(step / 4),
            "feature_ma_gap_5": 0.01 * np.sin(step / 8),
            "feature_ma_gap_20": 0.02 * np.sin(step / 13),
            "feature_selected_dte": 20.0 + step % 10,
            "feature_roll_event": (step % 30 == 0).astype(float),
            "feature_issue448_test": np.sin(step / 6),
        }
    )
    config = {
        "data.feature_family_subset": "market",
        "data.lookback_sessions": 60,
        "transforms.return_transform": "simple_return",
        "transforms.lag_sessions": 2,
        "transforms.rolling_stat_window_sessions": 20,
        "transforms.normalization_window_sessions": 60,
        "transforms.scaling": "none",
        "transforms.winsor_quantile": 0.01,
    }

    prepared, candidate_columns, control_columns = prepare_issue448_candidate_features(
        features, config, "feature_issue448_test"
    )

    assert candidate_columns == [
        "feature_issue448_test",
        "feature_issue448_test__mean20",
        "feature_issue448_test__std20",
    ]
    assert set(candidate_columns).isdisjoint(control_columns)
    assert all(column in prepared for column in [*candidate_columns, *control_columns])
    assert prepared[[*candidate_columns, *control_columns]].notna().all().all()
    mutated = features.copy()
    mutated.loc[mutated.index[-1], "feature_issue448_test"] = 999.0
    second, _, _ = prepare_issue448_candidate_features(mutated, config, "feature_issue448_test")
    common = prepared.index.intersection(second.index[:-1])
    pd.testing.assert_frame_equal(
        prepared.loc[common, [*candidate_columns, *control_columns]],
        second.loc[common, [*candidate_columns, *control_columns]],
    )


def test_issue448_open_interest_matches_selected_contract_by_publication_time() -> None:
    decisions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-06-02", "2022-06-03"], utc=True),
            "available_at": pd.to_datetime(["2022-06-02T12:00:00Z", "2022-06-03T12:00:00Z"]),
            "contract_id": ["NGN2@2022-06-28", "NGQ2@2022-07-27"],
        }
    )
    oi = pd.DataFrame(
        {
            "contract_id": ["NGN2@2022-06-28", "NGN2@2022-06-28", "NGQ2@2022-07-27"],
            "observed_for": pd.to_datetime(["2022-06-01", "2022-06-01", "2022-06-02"], utc=True),
            "available_at": pd.to_datetime(["2022-06-02T02:00:00Z", "2022-06-02T14:00:00Z", "2022-06-03T02:00:00Z"]),
            "open_interest": [4300.0, 4321.0, 5100.0],
        }
    )
    matched = match_issue448_open_interest_to_contract_path(decisions, oi)

    assert matched["open_interest_m1"].tolist() == [4300.0, 5100.0]
    assert matched["source_available_at"].tolist() == [
        pd.Timestamp("2022-06-02T02:00:00Z"), pd.Timestamp("2022-06-03T02:00:00Z")
    ]
    assert (matched["source_available_at"] <= matched["available_at"]).all()


def test_issue448_open_interest_ignores_holiday_reference_after_trade_date() -> None:
    decisions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2018-03-29"], utc=True),
            "available_at": pd.to_datetime(["2018-04-01T18:03:48Z"]),
            "contract_id": ["NGK8@2018-04-26"],
        }
    )
    oi = pd.DataFrame(
        {
            "contract_id": ["NGK8@2018-04-26", "NGK8@2018-04-26"],
            "observed_for": pd.to_datetime(["2018-03-29", "2018-03-30"], utc=True),
            "available_at": pd.to_datetime(["2018-03-30T13:20:00Z", "2018-04-01T17:30:56Z"]),
            "open_interest": [395227.0, 395227.0],
        }
    )

    matched = match_issue448_open_interest_to_contract_path(decisions, oi)

    assert matched.loc[0, "ts_ref"] == pd.Timestamp("2018-03-29", tz="UTC")
    assert matched.loc[0, "source_available_at"] == pd.Timestamp("2018-03-30T13:20:00Z")
    assert matched.loc[0, "open_interest_m1"] == 395227.0


def test_issue448_open_interest_prefers_newer_observation_over_late_old_revision() -> None:
    decisions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-06-03"], utc=True),
            "available_at": pd.to_datetime(["2022-06-03T12:00:00Z"]),
            "contract_id": ["NGQ2@2022-07-27"],
        }
    )
    oi = pd.DataFrame(
        {
            "contract_id": ["NGQ2@2022-07-27"] * 3,
            "observed_for": pd.to_datetime(["2022-06-01", "2022-06-02", "2022-06-01"], utc=True),
            "available_at": pd.to_datetime(["2022-06-02T02:00:00Z", "2022-06-03T02:00:00Z", "2022-06-03T10:00:00Z"]),
            "open_interest": [5000.0, 5100.0, 5050.0],
        }
    )

    matched = match_issue448_open_interest_to_contract_path(decisions, oi)

    assert matched.loc[0, "ts_ref"] == pd.Timestamp("2022-06-02", tz="UTC")
    assert matched.loc[0, "source_available_at"] == pd.Timestamp("2022-06-03T02:00:00Z")
    assert matched.loc[0, "open_interest_m1"] == 5100.0


def test_issue448_selected_contract_ohlcv_rejects_duplicate_rows() -> None:
    from commodity.v2_coverage import validate_issue448_selected_contract_ohlcv

    path = pd.DataFrame({
        "trade_date": pd.to_datetime(["2022-06-02"], utc=True),
        "contract_id": ["NGN2@2022-06-28"],
    })
    bars = pd.DataFrame({
        "trade_date": pd.to_datetime(["2022-06-02", "2022-06-02"], utc=True),
        "contract_id": ["NGN2@2022-06-28", "NGN2@2022-06-28"],
        "high": [3.1, 3.2], "low": [2.9, 2.8], "close": [3.0, 3.1], "volume": [100, 101],
    })
    with pytest.raises(Issue448CoverageError, match="duplicate selected-contract OHLCV"):
        validate_issue448_selected_contract_ohlcv(path, bars)


def test_issue448_selected_contract_ohlcv_rejects_missing_rows() -> None:
    from commodity.v2_coverage import validate_issue448_selected_contract_ohlcv

    path = pd.DataFrame({
        "trade_date": pd.to_datetime(["2022-06-02"], utc=True),
        "contract_id": ["NGN2@2022-06-28"],
    })
    bars = pd.DataFrame(columns=["trade_date", "contract_id", "high", "low", "close", "volume"])
    with pytest.raises(Issue448CoverageError, match="missing selected-contract OHLCV"):
        validate_issue448_selected_contract_ohlcv(path, bars)


def test_issue448_open_interest_path_excludes_future_reference_observation() -> None:
    decisions = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2022-06-02"], utc=True),
            "available_at": pd.to_datetime(["2022-06-02T12:00:00Z"]),
            "contract_id": ["NGN2@2022-06-28"],
        }
    )
    oi = pd.DataFrame(
        {
            "contract_id": ["NGN2@2022-06-28"],
            "observed_for": pd.to_datetime(["2022-06-03"], utc=True),
            "available_at": pd.to_datetime(["2022-06-02T02:00:00Z"]),
            "open_interest": [4300.0],
        }
    )

    matched = match_issue448_open_interest_to_contract_path(decisions, oi)

    assert pd.isna(matched.loc[0, "ts_ref"])
    assert pd.isna(matched.loc[0, "source_available_at"])
    assert pd.isna(matched.loc[0, "open_interest_m1"])
