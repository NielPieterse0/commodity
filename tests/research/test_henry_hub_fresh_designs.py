import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME = ROOT / "research" / "programmes" / "002-henry-hub-fresh"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def designs_by_id() -> dict[str, dict]:
    payload = load(PROGRAMME / "experiment-designs.json")
    return {item["design_id"]: item for item in payload["designs"]}


def test_observed_weather_reproductions_bind_reconstruction_fidelity_without_issued_forecasts():
    sources = load(ROOT / "config" / "data_sources.json")["sources"]
    designs = designs_by_id()
    source = sources["noaa_observed_weather"]
    recipe = load(ROOT / "data" / "acquisition-recipes" / "noaa-richman-lamb-reconstruction.json")

    assert not source["purpose"].startswith("source-faithful observed weather")
    assert recipe["recipe_id"] == "noaa-richman-lamb-reconstruction"
    assert recipe["fidelity_policy"]["default_reconstruction_tier"] == "tier_c_noaa_near_reconstruction"
    assert recipe["fidelity_policy"]["no_outcome_tuning"] is True
    assert recipe["fidelity_policy"]["issued_forecast_substitution_allowed"] is False
    assert recipe["reconstruction_contract"]["source_study_climatology"].startswith(
        "For each calendar day and target year, use the prior 30 years"
    )
    assert source["acquisition_recipe"] == "data/acquisition-recipes/noaa-richman-lamb-reconstruction.json"
    assert set(source["fidelity_tiers"]) == {
        "tier_a_exact_original",
        "tier_b_algorithmic_richman_lamb",
        "tier_c_noaa_near_reconstruction",
        "tier_d_modern_normals_robustness",
    }
    assert source["fidelity_tiers"]["tier_c_noaa_near_reconstruction"]["climatology"] == (
        "rolling prior-30-year day-of-year climatology from the bound observed-temperature history"
    )
    assert source["fidelity_tiers"]["tier_d_modern_normals_robustness"]["climatology"] == (
        "NOAA U.S. Daily Climate Normals 1991-2020"
    )

    rep007 = designs["rep-007-weather-return-volatility-response"]
    assert rep007["source_route"]["fidelity_tier"] == "tier_c_noaa_near_reconstruction"
    assert rep007["source_route"]["climatology"] == (
        "rolling prior-30-year day-of-year climatology from bound observed temperatures"
    )

    rep008 = designs["rep-008-weather-season-sign-asymmetry"]
    construction = rep008["literature_construction"]
    assert construction["basis"] == "ergen_dissertation_precursor"
    assert construction["final_2016_continuity"] == "not_assumed_without_final-paper evidence"
    assert construction["locations"] == ["Chicago", "New York", "Atlanta", "Dallas"]
    assert construction["weights"] == {
        "Chicago": 0.42,
        "New York": 0.28,
        "Atlanta": 0.17,
        "Dallas": 0.13,
    }
    assert construction["weather_shock_horizon_days"] == 7
    assert construction["seasonal_normal"] == "prior 30-year historical daily average"
    assert construction["oos_weather_forecast"] == {
        "model": "ARIMA(1,2,1)",
        "training_window_calendar_days": 500,
        "selection": "SIC",
    }

    for design in (rep007, rep008):
        assert design["source_route"]["observed_weather"] == "noaa_observed_weather"
        assert "issued" not in " ".join(design["inputs"]).lower()


def test_storage_consensus_public_contract_is_resolved_but_entitled_extraction_remains_fail_closed():
    setup = load(PROGRAMME / "experiment-setup.json")
    missing = {item["input_id"]: item for item in setup["missing_or_unproven_inputs"]}
    consensus = missing["historical_storage_consensus"]
    assert consensus["status"] == "bloomberg_pit_public_contract_resolved_entitled_key_resolution_pending"
    assert any("last survey state strictly before release" in item for item in consensus["entitled_extraction_acceptance"])
    assert any("DOENUSCH" in item for item in consensus["entitled_extraction_acceptance"])

    rep003 = designs_by_id()["rep-003-storage-surprise-response"]
    contract = rep003["source_route"]["bloomberg_public_contract"]
    assert contract["aggregate_product"] == "Economic Releases and Surveys Point-in-Time (PiT)"
    assert contract["advertised_history_start"] == 1997
    assert contract["required_components"] == ["Actuals and Surveys", "Actuals and Surveys (Changes)"]
    assert "Individual Economist Estimates" in contract["microdata_product"]
    assert "strictly before release" in rep003["pit_contract"]["source_release_timestamp"]


def test_all_redesigns_are_resolved_without_expanding_execution_authority():
    evidence = load(PROGRAMME / "evidence-map.json")
    counts = Counter(item["feasibility"] for item in evidence["feasibility_map"])
    assert counts == {"go": 14, "hold": 7}
    assert evidence["semantics"]["empirical_execution_authority"] is False
    assert evidence["semantics"]["preregistration_freeze_authority"] is False
    assert evidence["semantics"]["protected_evidence_opening_authority"] is False


def test_volatility_state_design_is_prerequisite_gated_synthesis():
    design = designs_by_id()["rep-010-volatility-state-dependence"]
    assert design["replication_class_target"] == "programme_synthesis_after_component_reproductions"
    assert design["empirical_execution_planned"] is False
    assert set(design["prerequisite_designs"]) >= {
        "rep-001-samuelson-maturity-volatility",
        "rep-005-scarcity-volatility",
        "rep-007-weather-return-volatility-response",
        "rep-009-announcement-volatility",
    }


def test_physical_balance_primary_is_source_coherent_monthly_core():
    design = designs_by_id()["rep-012-physical-balance-drivers"]
    assert design["primary_frequency"] == "monthly"
    assert design["primary_input_families"] == [
        "dry_or_marketed_production",
        "consumption",
        "pipeline_and_lng_import_exports",
        "storage_change",
    ]
    assert "weather" not in design["primary_input_families"]


def test_positioning_primary_uses_weekly_change_not_persistent_level():
    design = designs_by_id()["rep-020-positioning-incremental-information"]
    assert design["primary_positioning_measure"] == "managed_money_net_change"
    assert "managed_money_net_level" in design["secondary_positioning_measures"]


def test_physical_balance_monthly_series_are_pinned_before_outcome_access():
    design = designs_by_id()["rep-012-physical-balance-drivers"]
    assert design["source_route"]["monthly_series"] == {
        "production": "NG.N9070US2.M",
        "consumption": "NG.N9140US2.M",
        "imports": "NG.N9100US2.M",
        "exports": "NG.N9130US2.M",
        "storage_working_gas": "NG.NGM_EPG0_SAO_R48_MMCF.M",
        "henry_hub_reference": "NG.RNGWHHD.M",
    }
    assert design["source_route"]["physical_unit"] == "Million Cubic Feet"


def test_external_go_routes_remain_source_bounded():
    contracts = load(PROGRAMME / "implementation-contracts.json")
    entries = {item["design_id"]: item for item in contracts["entries"]}
    assert entries["rep-014-monthly-real-time-forecastability"]["source_ids"] == ["LIT-BHLR-RTDB"]
    assert entries["rep-016-europe-us-transmission-limited"]["source_ids"] == ["LIT-RS-EUUS"]
    assert entries["rep-015-oil-gas-linkage-regimes"]["source_ids"] == ["US-OIL"]
    assert entries["rep-006-inventory-forward-curve-scarcity"]["source_parameters"]["one_year_rate"] == "FRED:GS1"


def test_go_implementation_contracts_match_feasibility_and_existing_primitives():
    import commodity.research_construction as construction

    ledger = load(PROGRAMME / "feasibility-ledger.json")
    contracts = load(PROGRAMME / "implementation-contracts.json")
    go_ids = {item["design_id"] for item in ledger["entries"] if item["decision"] == "GO"}
    hold_ids = {item["design_id"] for item in ledger["entries"] if item["decision"] == "HOLD"}
    entries = {item["design_id"]: item for item in contracts["entries"]}

    assert set(entries) == go_ids
    assert not set(entries) & hold_ids
    for item in entries.values():
        assert item["constructors"]
        assert all(hasattr(construction, name) for name in item["constructors"])
        assert item["real_data_literature_outcome_execution_allowed"] is False
        assert item["empirical_execution_authority"] is False
        assert item["preregistration_freeze_authority"] is False
        assert item["protected_evidence_opening_authority"] is False
