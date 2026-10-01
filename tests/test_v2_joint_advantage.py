from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from commodity.v2_joint_advantage import (
    JointAdvantageError,
    apply_joint_candidate,
    apply_wave2_specialists,
    build_wave1_configs,
    build_wave2_configs,
)

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-prereg-v1.json"
WAVE2_PREREG = ROOT / "research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-wave2-prereg-v2.json"


def _prereg() -> dict:
    return json.loads(PREREG.read_text(encoding="utf-8"))


def _wave2_prereg() -> dict:
    return json.loads(WAVE2_PREREG.read_text(encoding="utf-8"))


def _frame() -> pd.DataFrame:
    fill = pd.to_datetime(
        ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"],
        utc=True,
    )
    return pd.DataFrame(
        {
            "signal_timestamp": fill - pd.Timedelta(hours=1),
            "fill_timestamp": fill,
            "target_end_timestamp": fill + pd.to_timedelta([2, 2, 1, 1, 1], unit="D"),
            "signal_requested_position": [1.0, -1.0, 1.0, -1.0, 1.0],
            "net_trade_utility_usd": [100.0, -200.0, 150.0, -50.0, 80.0],
        }
    )

def test_wave1_grid_matches_frozen_cartesian_budget() -> None:
    configs = build_wave1_configs(_prereg())

    assert len(configs) == 1584
    assert len({config.config_id for config in configs}) == 1584
    wave = _prereg()["wave1_joint_scarcity_repair"]
    assert {config.side_scope for config in configs} == set(wave["side_scopes"])
    assert {config.gate_id for config in configs} == set(wave["gate_families"])
    assert {config.position_fraction for config in configs} == {
        float(value) for value in wave["position_fractions"]
    }
    assert {config.lifecycle for config in configs} == set(wave["lifecycle_variants"])
    assert {config.cost_profile for config in configs} == set(wave["cost_profiles"])
    expected = {
        (side, gate, float(fraction), lifecycle, cost)
        for side in wave["side_scopes"]
        for gate in wave["gate_families"]
        for fraction in wave["position_fractions"]
        for lifecycle in wave["lifecycle_variants"]
        for cost in wave["cost_profiles"]
    }
    assert {
        (
            config.side_scope,
            config.gate_id,
            config.position_fraction,
            config.lifecycle,
            config.cost_profile,
        )
        for config in configs
    } == expected


def test_side_and_fraction_are_applied_without_flipping_direction() -> None:
    config = next(
        cfg for cfg in build_wave1_configs(_prereg())
        if cfg.side_scope == "long_only"
        and cfg.gate_id == "baseline"
        and cfg.position_fraction == 0.5
        and cfg.lifecycle == "inherited_horizon"
        and cfg.cost_profile == "base"
    )

    out = apply_joint_candidate(_frame(), config)

    assert out["signal_requested_position"].tolist() == [0.5, 0.0, 0.5, 0.0, 0.5]
    assert out["joint_abstained"].tolist() == [False, True, False, True, False]


def test_one_signal_per_target_window_blocks_overlapping_reentry() -> None:
    config = next(
        cfg for cfg in build_wave1_configs(_prereg())
        if cfg.side_scope == "both"
        and cfg.gate_id == "baseline"
        and cfg.position_fraction == 1.0
        and cfg.lifecycle == "one_signal_per_target_window"
        and cfg.cost_profile == "base"
    )

    out = apply_joint_candidate(_frame(), config)

    assert out["signal_requested_position"].tolist() == [1.0, 0.0, 1.0, -1.0, 1.0]

def test_loss_cooldown_waits_for_outcome_availability() -> None:
    frame = _frame()
    frame.loc[1, "target_end_timestamp"] = pd.Timestamp("2020-01-06 12:00:00", tz="UTC")
    config = next(
        cfg for cfg in build_wave1_configs(_prereg())
        if cfg.side_scope == "both"
        and cfg.gate_id == "baseline"
        and cfg.position_fraction == 1.0
        and cfg.lifecycle == "loss_cooldown_1_session"
        and cfg.cost_profile == "base"
    )

    out = apply_joint_candidate(frame, config)

    # The losing Jan-03 signal is not observable at the Jan-06 fill, so it cannot suppress it.
    assert out.loc[2, "signal_requested_position"] == 1.0
    # By Jan-07 that loss is observable; exactly one otherwise-admitted opportunity is suppressed.
    assert out.loc[3, "signal_requested_position"] == 0.0
    assert out.loc[4, "signal_requested_position"] == 1.0


def test_joint_candidate_rejects_protected_or_invalid_chronology() -> None:
    config = build_wave1_configs(_prereg())[0]
    frame = _frame()
    frame.loc[0, "fill_timestamp"] = pd.Timestamp("2023-01-03", tz="UTC")

    with pytest.raises(JointAdvantageError, match="protected"):
        apply_joint_candidate(frame, config)

    frame = _frame()
    frame.loc[0, "target_end_timestamp"] = frame.loc[0, "fill_timestamp"]
    with pytest.raises(JointAdvantageError, match="target end"):
        apply_joint_candidate(frame, config)


def test_wave1_gate_ids_map_to_frozen_issue428_configs() -> None:
    from commodity.v2_joint_advantage import issue428_config_id_for_gate

    expected = {
        "baseline": "baseline",
        "model_agreement": "model-agreement",
        "strength_q50": "strength-q50",
        "strength_q65": "strength-q65",
        "strength_q80": "strength-q80",
        "favored_count_3": "favored-signals-ge3",
        "favored_count_4": "favored-signals-ge4",
        "vol_of_vol_veto_q75": "vol-of-vol-veto-q75",
        "vol_of_vol_veto_q90": "vol-of-vol-veto-q90",
        "meta_interactions_p55": "meta-interactions-p55",
        "meta_interactions_p60": "meta-interactions-p60",
    }
    assert {
        gate: issue428_config_id_for_gate(gate)
        for gate in _prereg()["wave1_joint_scarcity_repair"]["gate_families"]
    } == expected


def test_wave1_policy_evaluation_requires_material_effect_sample_and_cost_robustness() -> None:
    from commodity.v2_joint_advantage import evaluate_wave1_policies

    rows = []
    for policy_id, base_delta, selected_trades, active_months in (
        ("strong", 0.0015, 30, 8),
        ("tiny", 0.0004, 60, 12),
    ):
        for outer_id in ("outer-2019-2020", "outer-2021-2022"):
            for cost, multiplier in (("base", 1.0), ("higher_1_5x", 0.8), ("higher_2x", 0.6)):
                rows.append(
                    {
                        "policy_id": policy_id,
                        "outer_id": outer_id,
                        "cost_profile": cost,
                        "mean_monthly_net_return_delta": base_delta * multiplier,
                        "selected_trades": selected_trades,
                        "nonempty_months": active_months,
                        "kill_trigger_regression": False,
                        "largest_incremental_month_fraction": 0.4,
                        "max_drawdown_fraction": 0.08,
                    }
                )

    evaluated = evaluate_wave1_policies(pd.DataFrame(rows), _prereg())
    by_id = {row["policy_id"]: row for row in evaluated}

    assert by_id["strong"]["passes_promotion_gate"] is True
    assert by_id["tiny"]["passes_promotion_gate"] is False
    assert by_id["strong"]["mean_outer_monthly_net_return_delta"] == pytest.approx(0.0015)


def test_incremental_month_concentration_uses_aligned_realized_ledger() -> None:
    from commodity.v2_joint_advantage import largest_incremental_month_fraction

    dates = pd.to_datetime(
        ["2020-01-02", "2020-01-03", "2020-02-03", "2020-03-03"], utc=True
    )
    baseline = pd.DataFrame(
        {"trade_date": dates, "net_pnl_usd": [0.0, 0.0, 0.0, 0.0]}
    )
    candidate = pd.DataFrame(
        {"trade_date": dates, "net_pnl_usd": [60.0, 0.0, 40.0, -10.0]}
    )

    assert largest_incremental_month_fraction(candidate, baseline) == pytest.approx(0.6)


def test_executed_sample_counts_fractional_positions_not_requested_signals() -> None:
    from commodity.v2_joint_advantage import executed_sample_summary

    policy = pd.DataFrame(
        {
            "fill_trade_date": pd.to_datetime(
                ["2020-01-02", "2020-02-03", "2020-03-03"], utc=True
            ),
            "baseline_position": [1.0, 1.0, -1.0],
            "signal_requested_position": [0.25, 0.5, -0.25],
        }
    )
    ledger = pd.DataFrame(
        {
            "trade_date": policy["fill_trade_date"],
            "target_position": [0.25, 0.0, -0.25],
        }
    )

    summary = executed_sample_summary(policy, ledger)
    assert summary["requested_selected_trades"] == 3
    assert summary["selected_trades"] == 2
    assert summary["nonempty_months"] == 2


def test_wave2_grid_matches_frozen_parent_and_specialist_budget() -> None:
    configs = build_wave2_configs(_wave2_prereg())

    assert len(configs) == 46
    assert len({config.config_id for config in configs}) == 46
    wave2 = _wave2_prereg()
    parents = wave2["parent_wave1"]["eligible_parent_policy_ids"]
    assert {config.parent_policy_id for config in configs} == set(parents)
    assert all(not (config.short_mode == "none" and config.long_mode == "none") for config in configs)
    assert all(
        config.long_mode == "none"
        for config in configs
        if config.parent_policy_id.startswith("short_only__")
    )
    expected = {
        (parent, short_mode, long_mode)
        for parent in parents
        for short_mode in wave2["candidate_space"]["short_modes"]
        for long_mode in wave2["candidate_space"]["long_modes"]
        if not (short_mode == "none" and long_mode == "none")
        and not (parent.startswith("short_only__") and long_mode != "none")
    }
    assert {
        (config.parent_policy_id, config.short_mode, config.long_mode)
        for config in configs
    } == expected


def test_wave2_specialists_apply_directional_half_and_veto_without_flipping() -> None:
    config = next(
        item for item in build_wave2_configs(_wave2_prereg())
        if item.parent_policy_id.startswith("both__")
        and item.short_mode == "half"
        and item.long_mode == "veto"
    )
    frame = pd.DataFrame(
        {
            "signal_requested_position": [-1.0, -0.5, 1.0, 0.5, 0.0],
            "timesfm_point_return": [0.01, -0.01, 0.02, -0.02, 0.0],
            "kronos_close_return": [0.01, -0.01, -0.01, 0.01, 0.0],
            "signal_timestamp": pd.date_range("2020-01-01", periods=5, tz="UTC"),
            "fill_timestamp": pd.date_range("2020-01-02", periods=5, tz="UTC"),
            "target_end_timestamp": pd.date_range("2020-01-03", periods=5, tz="UTC"),
        }
    )

    out = apply_wave2_specialists(frame, config)

    assert out["signal_requested_position"].tolist() == [-0.5, -0.5, 0.0, 0.5, 0.0]
    assert out["wave2_short_modified"].tolist() == [True, False, False, False, False]
    assert out["wave2_long_modified"].tolist() == [False, False, True, False, False]



def test_wave2_specialists_reject_protected_timestamps() -> None:
    config = next(
        item for item in build_wave2_configs(_wave2_prereg())
        if item.parent_policy_id.startswith("both__")
        and item.short_mode == "half"
        and item.long_mode == "veto"
    )
    frame = pd.DataFrame(
        {
            "signal_requested_position": [1.0],
            "timesfm_point_return": [-0.01],
            "kronos_close_return": [-0.01],
            "signal_timestamp": [pd.Timestamp("2022-12-30", tz="UTC")],
            "fill_timestamp": [pd.Timestamp("2023-01-01", tz="UTC")],
            "target_end_timestamp": [pd.Timestamp("2022-12-31", tz="UTC")],
        }
    )

    with pytest.raises(JointAdvantageError, match="protected"):
        apply_wave2_specialists(frame, config)


def test_executed_sample_rejects_opposite_direction_replay() -> None:
    from commodity.v2_joint_advantage import executed_sample_summary

    dates = pd.to_datetime(["2020-01-02", "2020-02-03"], utc=True)
    policy = pd.DataFrame(
        {
            "fill_trade_date": dates,
            "baseline_position": [1.0, -1.0],
            "signal_requested_position": [0.25, -0.5],
        }
    )
    ledger = pd.DataFrame(
        {
            "trade_date": dates,
            "target_position": [-0.25, -0.5],
        }
    )

    with pytest.raises(JointAdvantageError, match="direction"):
        executed_sample_summary(policy, ledger)


@pytest.mark.parametrize(
    ("mutation", "expected_field"),
    [
        ("concentration", "concentration_pass"),
        ("kill", "kill_trigger_regression"),
        ("higher_cost", "higher_cost_nonnegative"),
        ("trades", "effective_sample_pass"),
        ("months", "effective_sample_pass"),
        ("outer_sign", "nonnegative_outer_fraction"),
    ],
)
def test_wave1_promotion_gate_rejects_each_required_failure(
    mutation: str,
    expected_field: str,
) -> None:
    from commodity.v2_joint_advantage import evaluate_wave1_policies

    rows = []
    for outer_id in ("outer-2019-2020", "outer-2021-2022"):
        for cost, multiplier in (("base", 1.0), ("higher_1_5x", 0.8), ("higher_2x", 0.6)):
            rows.append(
                {
                    "policy_id": "candidate",
                    "outer_id": outer_id,
                    "cost_profile": cost,
                    "mean_monthly_net_return_delta": 0.002 * multiplier,
                    "selected_trades": 30,
                    "nonempty_months": 8,
                    "kill_trigger_regression": False,
                    "largest_incremental_month_fraction": 0.4,
                    "max_drawdown_fraction": 0.05,
                }
            )
    frame = pd.DataFrame(rows)
    if mutation == "concentration":
        frame.loc[frame["cost_profile"].eq("base"), "largest_incremental_month_fraction"] = 0.51
    elif mutation == "kill":
        frame.loc[0, "kill_trigger_regression"] = True
    elif mutation == "higher_cost":
        frame.loc[frame["cost_profile"].eq("higher_2x"), "mean_monthly_net_return_delta"] = -0.0001
    elif mutation == "trades":
        frame.loc[frame["cost_profile"].eq("base"), "selected_trades"] = 23
    elif mutation == "months":
        frame.loc[frame["cost_profile"].eq("base"), "nonempty_months"] = 5
    elif mutation == "outer_sign":
        mask = frame["outer_id"].eq("outer-2019-2020") & frame["cost_profile"].eq("base")
        frame.loc[mask, "mean_monthly_net_return_delta"] = -0.0001
        other = frame["outer_id"].eq("outer-2021-2022") & frame["cost_profile"].eq("base")
        frame.loc[other, "mean_monthly_net_return_delta"] = 0.003

    evaluated = evaluate_wave1_policies(frame, _prereg())[0]
    assert evaluated["passes_promotion_gate"] is False
    if expected_field == "kill_trigger_regression":
        assert evaluated[expected_field] is True
    elif expected_field == "nonnegative_outer_fraction":
        assert evaluated[expected_field] == pytest.approx(0.5)
    else:
        assert evaluated[expected_field] is False


def test_loss_cooldown_outcome_equal_to_fill_is_not_yet_observable() -> None:
    frame = _frame().iloc[:4].copy()
    frame.loc[0, "net_trade_utility_usd"] = -100.0
    frame.loc[0, "target_end_timestamp"] = frame.loc[1, "fill_timestamp"]
    config = next(
        cfg for cfg in build_wave1_configs(_prereg())
        if cfg.side_scope == "both"
        and cfg.gate_id == "baseline"
        and cfg.position_fraction == 1.0
        and cfg.lifecycle == "loss_cooldown_1_session"
        and cfg.cost_profile == "base"
    )

    out = apply_joint_candidate(frame, config)
    assert out.loc[1, "signal_requested_position"] == -1.0
    assert out.loc[2, "signal_requested_position"] == 0.0


def test_loss_cooldown_three_sessions_suppresses_three_admissible_fills() -> None:
    frame = _frame().copy()
    frame.loc[0, "net_trade_utility_usd"] = -100.0
    frame.loc[0, "target_end_timestamp"] = frame.loc[0, "fill_timestamp"] + pd.Timedelta(hours=12)
    config = next(
        cfg for cfg in build_wave1_configs(_prereg())
        if cfg.side_scope == "both"
        and cfg.gate_id == "baseline"
        and cfg.position_fraction == 1.0
        and cfg.lifecycle == "loss_cooldown_3_sessions"
        and cfg.cost_profile == "base"
    )

    out = apply_joint_candidate(frame, config)
    assert out["signal_requested_position"].tolist() == [1.0, 0.0, 0.0, 0.0, 1.0]


@pytest.mark.parametrize(
    ("side", "mode", "specialist_value", "expected"),
    [
        ("short", "half", 0.0, -0.25),
        ("short", "veto", 0.01, 0.0),
        ("short", "none", 0.01, -0.5),
        ("long", "half", 0.0, 0.25),
        ("long", "veto", -0.01, 0.0),
        ("long", "none", -0.01, 0.5),
    ],
)
def test_wave2_specialist_modes_cover_zero_boundaries(
    side: str,
    mode: str,
    specialist_value: float,
    expected: float,
) -> None:
    parent = next(value for value in _wave2_prereg()["parent_wave1"]["eligible_parent_policy_ids"] if value.startswith("both__"))
    short_mode = mode if side == "short" else "none"
    long_mode = mode if side == "long" else "none"
    if short_mode == "none" and long_mode == "none":
        if side == "short":
            long_mode = "half"
        else:
            short_mode = "half"
    config = next(
        item for item in build_wave2_configs(_wave2_prereg())
        if item.parent_policy_id == parent
        and item.short_mode == short_mode
        and item.long_mode == long_mode
    )
    position = -0.5 if side == "short" else 0.5
    frame = pd.DataFrame(
        {
            "signal_requested_position": [position],
            "timesfm_point_return": [specialist_value if side == "short" else -0.01],
            "kronos_close_return": [specialist_value if side == "long" else 0.01],
            "signal_timestamp": [pd.Timestamp("2020-01-02", tz="UTC")],
            "fill_timestamp": [pd.Timestamp("2020-01-03", tz="UTC")],
            "target_end_timestamp": [pd.Timestamp("2020-01-06", tz="UTC")],
        }
    )

    out = apply_wave2_specialists(frame, config)
    assert out.loc[0, "signal_requested_position"] == expected
    modified_column = "wave2_short_modified" if side == "short" else "wave2_long_modified"
    assert bool(out.loc[0, modified_column]) is (mode != "none")


@pytest.mark.parametrize("missing_column", ["signal_timestamp", "fill_timestamp", "target_end_timestamp"])
def test_wave2_specialists_require_all_provenance_timestamps(missing_column: str) -> None:
    config = build_wave2_configs(_wave2_prereg())[0]
    frame = pd.DataFrame(
        {
            "signal_requested_position": [-0.5],
            "timesfm_point_return": [0.01],
            "kronos_close_return": [0.01],
            "signal_timestamp": [pd.Timestamp("2020-01-02", tz="UTC")],
            "fill_timestamp": [pd.Timestamp("2020-01-03", tz="UTC")],
            "target_end_timestamp": [pd.Timestamp("2020-01-06", tz="UTC")],
        }
    ).drop(columns=[missing_column])

    with pytest.raises(JointAdvantageError, match="missing provenance timestamps"):
        apply_wave2_specialists(frame, config)


@pytest.mark.parametrize("protected_column", ["signal_timestamp", "fill_timestamp", "target_end_timestamp"])
def test_wave2_specialists_reject_each_protected_timestamp(protected_column: str) -> None:
    config = build_wave2_configs(_wave2_prereg())[0]
    frame = pd.DataFrame(
        {
            "signal_requested_position": [-0.5],
            "timesfm_point_return": [0.01],
            "kronos_close_return": [0.01],
            "signal_timestamp": [pd.Timestamp("2022-12-30", tz="UTC")],
            "fill_timestamp": [pd.Timestamp("2022-12-30", tz="UTC")],
            "target_end_timestamp": [pd.Timestamp("2022-12-31", tz="UTC")],
        }
    )
    frame.loc[0, protected_column] = pd.Timestamp("2023-01-01", tz="UTC")

    with pytest.raises(JointAdvantageError, match="protected"):
        apply_wave2_specialists(frame, config)


def test_executed_sample_rejects_duplicate_policy_decision_dates() -> None:
    from commodity.v2_joint_advantage import executed_sample_summary

    date = pd.Timestamp("2020-01-02", tz="UTC")
    policy = pd.DataFrame(
        {
            "fill_trade_date": [date, date],
            "baseline_position": [1.0, 1.0],
            "signal_requested_position": [0.25, 0.25],
        }
    )
    ledger = pd.DataFrame(
        {
            "trade_date": [date],
            "target_position": [0.25],
        }
    )

    with pytest.raises(JointAdvantageError, match="duplicate decision dates"):
        executed_sample_summary(policy, ledger)


@pytest.mark.parametrize("missing_column", ["signal_timestamp", "fill_timestamp", "target_end_timestamp"])
def test_wave1_requires_all_provenance_timestamps(missing_column: str) -> None:
    frame = _frame().drop(columns=[missing_column])
    config = build_wave1_configs(_prereg())[0]

    with pytest.raises(JointAdvantageError, match="missing columns"):
        apply_joint_candidate(frame, config)


@pytest.mark.parametrize("protected_column", ["signal_timestamp", "fill_timestamp", "target_end_timestamp"])
def test_wave1_rejects_each_protected_timestamp(protected_column: str) -> None:
    frame = _frame()
    frame.loc[0, protected_column] = pd.Timestamp("2023-01-01", tz="UTC")
    config = build_wave1_configs(_prereg())[0]

    with pytest.raises(JointAdvantageError, match="protected"):
        apply_joint_candidate(frame, config)


def test_one_signal_per_target_window_admits_fill_at_exact_release_boundary() -> None:
    frame = _frame().iloc[:2].copy()
    frame.loc[0, "target_end_timestamp"] = frame.loc[1, "fill_timestamp"]
    config = next(
        cfg for cfg in build_wave1_configs(_prereg())
        if cfg.side_scope == "both" and cfg.gate_id == "baseline"
        and cfg.position_fraction == 1.0 and cfg.lifecycle == "one_signal_per_target_window"
        and cfg.cost_profile == "base"
    )
    out = apply_joint_candidate(frame, config)
    assert out["signal_requested_position"].tolist() == [1.0, -1.0]


def test_executed_sample_rejects_duplicate_replay_dates() -> None:
    from commodity.v2_joint_advantage import executed_sample_summary

    date = pd.Timestamp("2020-01-02", tz="UTC")
    policy = pd.DataFrame(
        {
            "fill_trade_date": [date],
            "baseline_position": [1.0],
            "signal_requested_position": [0.25],
        }
    )
    ledger = pd.DataFrame(
        {
            "trade_date": [date, date],
            "target_position": [0.25, 0.25],
        }
    )

    with pytest.raises(JointAdvantageError, match="duplicate trade dates"):
        executed_sample_summary(policy, ledger)


@pytest.mark.parametrize("duplicate_side", ["candidate", "baseline"])
def test_concentration_rejects_duplicate_ledger_dates(duplicate_side: str) -> None:
    from commodity.v2_joint_advantage import largest_incremental_month_fraction

    dates = pd.to_datetime(["2020-01-02", "2020-02-03"], utc=True)
    candidate = pd.DataFrame(
        {"trade_date": dates, "net_pnl_usd": [10.0, 20.0]}
    )
    baseline = pd.DataFrame(
        {"trade_date": dates, "net_pnl_usd": [0.0, 0.0]}
    )
    target = candidate if duplicate_side == "candidate" else baseline
    duplicate = target.iloc[[0]].copy()
    if duplicate_side == "candidate":
        candidate = pd.concat([candidate, duplicate], ignore_index=True)
    else:
        baseline = pd.concat([baseline, duplicate], ignore_index=True)

    with pytest.raises(JointAdvantageError, match="duplicate trade dates"):
        largest_incremental_month_fraction(candidate, baseline)


@pytest.mark.parametrize("offset", [pd.Timedelta(0), pd.Timedelta(seconds=1)])
def test_wave1_rejects_signal_at_or_after_fill(offset: pd.Timedelta) -> None:
    frame = _frame()
    frame.loc[0, "signal_timestamp"] = frame.loc[0, "fill_timestamp"] + offset
    config = build_wave1_configs(_prereg())[0]

    with pytest.raises(JointAdvantageError, match="signal timestamp must be before fill"):
        apply_joint_candidate(frame, config)


@pytest.mark.parametrize(
    ("column", "offset", "message"),
    [
        ("signal_timestamp", pd.Timedelta(0), "signal timestamp must be before fill"),
        ("signal_timestamp", pd.Timedelta(seconds=1), "signal timestamp must be before fill"),
        ("target_end_timestamp", pd.Timedelta(0), "target end must be strictly after fill"),
        ("target_end_timestamp", pd.Timedelta(seconds=-1), "target end must be strictly after fill"),
    ],
)
def test_wave2_rejects_invalid_timestamp_order(
    column: str, offset: pd.Timedelta, message: str
) -> None:
    config = build_wave2_configs(_wave2_prereg())[0]
    frame = pd.DataFrame(
        {
            "signal_requested_position": [-0.5],
            "timesfm_point_return": [0.01],
            "kronos_close_return": [0.01],
            "signal_timestamp": [pd.Timestamp("2020-01-02", tz="UTC")],
            "fill_timestamp": [pd.Timestamp("2020-01-03", tz="UTC")],
            "target_end_timestamp": [pd.Timestamp("2020-01-06", tz="UTC")],
        }
    )
    frame.loc[0, column] = frame.loc[0, "fill_timestamp"] + offset

    with pytest.raises(JointAdvantageError, match=message):
        apply_wave2_specialists(frame, config)


def _promotion_rows(
    *,
    base_delta: float = 0.002,
    trades: int = 24,
    months: int = 6,
    concentration: float = 0.5,
    higher_delta: float = 0.0,
    first_outer_base_delta: float | None = None,
) -> pd.DataFrame:
    rows = []
    for outer_id in ("outer-2019-2020", "outer-2021-2022"):
        for cost in ("base", "higher_1_5x", "higher_2x"):
            delta = base_delta if cost == "base" else higher_delta
            if cost == "base" and outer_id == "outer-2019-2020" and first_outer_base_delta is not None:
                delta = first_outer_base_delta
            rows.append(
                {
                    "policy_id": "boundary",
                    "outer_id": outer_id,
                    "cost_profile": cost,
                    "mean_monthly_net_return_delta": delta,
                    "selected_trades": trades,
                    "nonempty_months": months,
                    "kill_trigger_regression": False,
                    "largest_incremental_month_fraction": concentration,
                    "max_drawdown_fraction": 0.05,
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("field", "relation", "expected_pass"),
    [
        ("mean", "below", False), ("mean", "equal", False), ("mean", "above", True),
        ("trades", "below", False), ("trades", "equal", True), ("trades", "above", True),
        ("months", "below", False), ("months", "equal", True), ("months", "above", True),
        ("concentration", "below", True), ("concentration", "equal", True), ("concentration", "above", False),
        ("higher", "below", False), ("higher", "equal", True), ("higher", "above", True),
    ],
)
def test_promotion_gate_exact_threshold_boundaries(
    field: str, relation: str, expected_pass: bool
) -> None:
    from commodity.v2_joint_advantage import evaluate_wave1_policies

    prereg = _prereg()
    gate = prereg["promotion_gate"]
    controls = prereg["effective_sample_controls"]
    epsilon = 1e-9
    kwargs: dict[str, object] = {}
    if field == "mean":
        threshold = float(gate["mean_outer_monthly_net_return_delta_gt"])
        kwargs["base_delta"] = threshold + {"below": -epsilon, "equal": 0.0, "above": epsilon}[relation]
    elif field == "trades":
        threshold = int(controls["minimum_risk_executed_trades_per_outer"])
        kwargs["trades"] = threshold + {"below": -1, "equal": 0, "above": 1}[relation]
    elif field == "months":
        threshold = int(controls["minimum_nonempty_months_per_outer"])
        kwargs["months"] = threshold + {"below": -1, "equal": 0, "above": 1}[relation]
    elif field == "concentration":
        kwargs["concentration"] = 0.5 + {"below": -epsilon, "equal": 0.0, "above": epsilon}[relation]
    else:
        kwargs["higher_delta"] = {"below": -epsilon, "equal": 0.0, "above": epsilon}[relation]

    evaluated = evaluate_wave1_policies(_promotion_rows(**kwargs), prereg)[0]
    assert evaluated["passes_promotion_gate"] is expected_pass


def test_promotion_gate_nonnegative_outer_fraction_boundary() -> None:
    from commodity.v2_joint_advantage import evaluate_wave1_policies

    prereg = _prereg()
    passing = evaluate_wave1_policies(_promotion_rows(), prereg)[0]
    assert passing["nonnegative_outer_fraction"] == pytest.approx(1.0)
    assert passing["passes_promotion_gate"] is True

    mixed = _promotion_rows(base_delta=0.003, first_outer_base_delta=-0.0001)
    failing = evaluate_wave1_policies(mixed, prereg)[0]
    assert failing["mean_outer_monthly_net_return_delta"] > float(
        prereg["promotion_gate"]["mean_outer_monthly_net_return_delta_gt"]
    )
    assert failing["nonnegative_outer_fraction"] == pytest.approx(0.5)
    assert failing["passes_promotion_gate"] is False


def test_wave2_v2_is_identity_only_rebind_of_v1() -> None:
    v1_path = ROOT / "research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-wave2-prereg-v1.json"
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    v2 = _wave2_prereg()

    assert v2["identity_rebind"]["candidate_space_changed"] is False
    assert v2["identity_rebind"]["eligible_parent_set_changed"] is False
    assert v2["identity_rebind"]["wave1_trial_ledger_unchanged"] is True
    assert v2["candidate_space"] == v1["candidate_space"]
    assert v2["evaluation"] == v1["evaluation"]
    assert v2["specialist_inputs"] == v1["specialist_inputs"]
    assert v2["parent_wave1"]["eligible_parent_policy_ids"] == v1["parent_wave1"]["eligible_parent_policy_ids"]
