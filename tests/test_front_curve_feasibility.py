from __future__ import annotations

import pandas as pd
import pytest

from commodity.config import assumptions_config, data_config
from commodity.front_curve_feasibility import (
    CONFIRMATION_START,
    MIN_CONFIRMATION_ROWS,
    SCIENTIFIC_MEPI,
    audit_development_feasibility,
    build_front_curve_target,
    build_frozen_feature_frame,
    fixed_confirmatory_design,
    target_contract,
)
from commodity.market_data import DataContractViolation
from scripts.run_front_curve_feasibility import _update_programme


def _rows() -> pd.DataFrame:
    dates = pd.date_range("2018-01-02", periods=6, freq="B", tz="UTC")
    contracts = [
        ("NGA18", pd.Timestamp("2018-01-31", tz="UTC")),
        ("NGB18", pd.Timestamp("2018-02-28", tz="UTC")),
        ("NGC18", pd.Timestamp("2018-03-31", tz="UTC")),
    ]
    rows = []
    volumes = {
        "NGA18": [100, 100, 80, 70, 60, 50],
        "NGB18": [50, 120, 130, 140, 150, 160],
        "NGC18": [20, 30, 40, 50, 60, 70],
    }
    bases = {"NGA18": 3.0, "NGB18": 3.1, "NGC18": 3.2}
    for idx, date in enumerate(dates):
        for contract_id, expiration in contracts:
            rows.append(
                {
                    "trade_date": date,
                    "contract_id": contract_id,
                    "expiration": expiration,
                    "settle": bases[contract_id] + 0.01 * idx,
                    "volume": volumes[contract_id][idx],
                    "available_at": date + pd.Timedelta(hours=22),
                }
            )
    return pd.DataFrame(rows)


def _schema() -> dict:
    return data_config()["canonical_contract_schema"]


def _policy() -> dict:
    return assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]


def test_target_uses_active_front_and_nearest_later_contract() -> None:
    panel = build_front_curve_target(_rows(), _schema(), _policy())
    assert panel.iloc[0]["m1_contract_id"] == "NGA18"
    assert panel.iloc[0]["m2_contract_id"] == "NGB18"
    assert panel.iloc[-1]["m1_contract_id"] == "NGB18"
    assert panel.iloc[-1]["m2_contract_id"] == "NGC18"
    assert (panel["prediction_time"] >= panel["trade_date"]).all()


def test_target_never_scores_across_pair_transition() -> None:
    panel = build_front_curve_target(_rows(), _schema(), _policy())
    transitions = panel["excluded_pair_transition"]
    assert transitions.sum() == 1
    transition_row = panel.loc[transitions].iloc[0]
    assert pd.isna(transition_row["target_spread_change"])
    scored = panel.loc[panel["target_spread_change"].notna()]
    assert (
        scored["m1_contract_id"].to_numpy()
        == panel.loc[scored.index + 1, "m1_contract_id"].to_numpy()
    ).all()
    assert (
        scored["m2_contract_id"].to_numpy()
        == panel.loc[scored.index + 1, "m2_contract_id"].to_numpy()
    ).all()


def test_feature_contract_is_fixed_and_market_only() -> None:
    panel = build_front_curve_target(_rows(), _schema(), _policy())
    features = build_frozen_feature_frame(panel)
    expected = {
        "spread",
        "lag1_spread_change",
        "lag5_mean_spread_change",
        "m1_calendar_dte",
        "log_m2_m1_volume_ratio",
        "calendar_month_sin",
        "calendar_month_cos",
    }
    assert expected.issubset(features.columns)
    assert target_contract()["transition_rule"].startswith("score only when both")


def test_feasibility_audit_refuses_protected_rows() -> None:
    panel = build_front_curve_target(_rows(), _schema(), _policy())
    protected = panel.copy()
    protected["trade_date"] = protected["trade_date"] + (CONFIRMATION_START - protected["trade_date"].min())
    protected["target_trade_date"] = protected["target_trade_date"] + (CONFIRMATION_START - panel["trade_date"].min())
    with pytest.raises(DataContractViolation, match="protected confirmation rows"):
        audit_development_feasibility(protected)


def test_fixed_design_has_no_unresolved_model_search() -> None:
    feasibility = {"feasibility": "go", "dependence": {"preregistered_rho": 0.25}}
    design = fixed_confirmatory_design(feasibility)
    assert design["split"]["minimum_scored_confirmation_rows"] == MIN_CONFIRMATION_ROWS
    assert design["split"]["development"] == "2015-01-01/2021-12-31"
    assert design["split"]["protected_confirmation"] == "2022-01-01/2026-08-12"
    assert f">={MIN_CONFIRMATION_ROWS}" in design["features"]["missing_rule"]
    assert "2022-2026" in design["evaluation"]["promotion"]
    assert "2019-2026" not in design["evaluation"]["promotion"]
    assert len(design["models"]) == 3
    assert design["models"][1]["alpha"] == 1.0
    assert design["models"][2]["random_state"] == 271
    assert design["evaluation"]["scientific_mepi_standardized_paired_loss_effect"] == SCIENTIFIC_MEPI
    assert "no tuning" in design["training"]


def test_zero_price_missing_volume_placeholders_are_not_curve_legs() -> None:
    rows = _rows()
    placeholder = rows.iloc[[0]].copy()
    placeholder["contract_id"] = "NGZ99"
    placeholder["expiration"] = pd.Timestamp("2099-12-31", tz="UTC")
    placeholder["settle"] = 0.0
    placeholder["volume"] = float("nan")
    rows = pd.concat([rows, placeholder], ignore_index=True)

    panel = build_front_curve_target(rows, _schema(), _policy())

    assert "NGZ99" not in set(panel["m1_contract_id"])
    assert "NGZ99" not in set(panel["m2_contract_id"])
    assert target_contract()["input_validity_rule"].startswith("curve legs require finite positive settlement")


def test_programme_hold_update_is_idempotent_and_keeps_evidence_ref() -> None:
    programme = {
        "research_lines": [
            {
                "research_line_id": "line-next-defensible-edge",
                "evidence_refs": ["docs/big-picture.md"],
                "experiment_history": [],
                "remaining_untested_roles": ["curve/spread change"],
            }
        ],
        "feasibility_map": [],
    }
    feasibility = {
        "feasibility": "hold",
        "rows": {"scoreable_targets": 1462},
        "dependence": {"preregistered_rho": 0.25},
        "power": {"detectable_effect": 0.109},
        "hold_reasons": ["minimum_development_rows", "year_concentration"],
    }

    once = _update_programme(programme, feasibility)
    twice = _update_programme(once, feasibility)

    assert twice == once
    line = once["research_lines"][0]
    assert line["experiment_history"] == [
        {"issue": 271, "result": "front_curve_feasibility_hold_before_preregistration"}
    ]
    assert "research/exploratory/front-curve-feasibility-271.json" in line["evidence_refs"]
