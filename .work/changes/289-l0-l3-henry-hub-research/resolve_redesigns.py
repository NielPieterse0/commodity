from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "research" / "programmes" / "002-henry-hub-fresh"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


data_sources_path = ROOT / "config" / "data_sources.json"
data_sources = load(data_sources_path)
data_sources["providers"]["noaa_ncei_observed_climate"] = {
    "access": "public_http",
    "role": "historical_observed_weather_and_climate_normals",
    "ghcn_daily_root": "https://www.ncei.noaa.gov/pub/data/ghcn/daily/",
    "daily_normals_metadata": "https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc:C01621",
}
data_sources["sources"]["noaa_observed_weather"] = {
    "provider": "noaa_ncei_observed_climate",
    "status": "public_source_route_verified_not_acquired",
    "purpose": "source-faithful observed weather and climatological-normal construction for descriptive Henry Hub literature reproductions",
    "product": "GHCN-Daily observations plus U.S. Daily Climate Normals 1991-2020",
    "point_in_time_required": False,
    "predictive_use_allowed": False,
    "historical_truth_only": True,
    "required_variables": ["TMAX", "TMIN", "TAVG_or_derived_mean", "heating_degree_day_normal", "cooling_degree_day_normal"],
    "snapshot_rule": "Pin station inventory, observation files, normals version and content hashes before empirical execution; later NOAA revisions must not silently mutate a reproduction.",
    "weighting_rule": "Use literature-derived locations/weights where recoverable; otherwise predeclare a gas-demand-region station/weighting rule before outcome access.",
    "availability_semantics": "Observed-weather explanatory reproduction only. Do not reuse as issued-forecast or trading-at-origin evidence.",
}
registry = data_sources["source_library"]["registry"]
registry["US-WX-OBSERVED"] = {
    "sources": [
        {"name": "NOAA GHCN-Daily", "url": "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"},
        {"name": "NOAA U.S. Daily Climate Normals 1991-2020", "url": "https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals"},
    ],
    "access": "Public bulk/search access",
    "primary_use": "Observed temperature/HDD/CDD departures from fixed climatological normals for source-faithful descriptive weather reproductions",
}
assessments = data_sources["source_library"]["discovered_after_recovery"]["assessments"]
assessments["observed_weather_reproduction"] = {
    "status": "public_official_route_verified_not_acquired",
    "preferred_route": "NOAA GHCN-Daily observations plus U.S. Daily Climate Normals 1991-2020",
    "reason": "The retained Open-Meteo archive is issued-forecast data. NOAA GHCN-Daily supplies quality-controlled historical daily observations and the official daily normals supply fixed temperature/HDD/CDD climatology for descriptive mechanism replication.",
}
write(data_sources_path, data_sources)

designs_path = P / "experiment-designs.json"
payload = load(designs_path)
by_id = {item["design_id"]: item for item in payload["designs"]}

rep7 = by_id["rep-007-weather-return-volatility-response"]
rep7["source_route"] = {
    "observed_weather": "noaa_observed_weather",
    "market": "databento_henry_hub",
    "climatology": "NOAA U.S. Daily Climate Normals 1991-2020",
}
rep7["sample"] = "Maximum 2010-06-06 onward overlap of canonical Databento and a pinned NOAA observed-weather snapshot after station/weighting rules are fixed before outcome access."
rep7["inputs"] = ["observed daily temperature", "HDD/CDD departure from fixed NOAA normal", "season", "same-contract return", "volatility"]
rep7["information_fidelity"] = "Primary reproduction is historical observed-weather explanatory evidence. Issued forecast vintages are prohibited substitutes and belong only to separate forecast/revision designs."
rep7["implementation_gate"] = "Acquire/pin GHCN-Daily observations and daily normals, recover literature locations/weights where possible, otherwise predeclare gas-demand-region weights, then recompute season-cell counts and power without reading market outcomes."
rep7["pit_contract"] = {
    "forecast_origin_or_event_time": "observed calendar day for descriptive reproduction",
    "target_timestamp": "same-day/predeclared contemporaneous market response",
    "source_release_timestamp": "record NOAA observation/source retrieval lineage; no trading-at-origin claim",
    "revision_policy": "fixed acquired GHCN-Daily snapshot plus fixed normals version; later revisions excluded from the bound reproduction",
    "vintage_rule": "snapshot identity and hashes fixed before market-outcome execution",
    "timezone": "station-local observation mapped to America/New_York market calendar",
    "contract_identity_and_roll_rule": "same listed contract",
    "availability_lag": "not predictive",
    "evaluation_sample": "maximum source-valid historical-truth overlap after fixed station/weighting rules",
}

rep8 = by_id["rep-008-weather-season-sign-asymmetry"]
rep8["source_route"] = rep7["source_route"].copy()
rep8["sample"] = "Same pinned NOAA observed-weather/Databento overlap as rep-007, with season and signed departure cells fixed from weather information alone before market-outcome access."
rep8["inputs"] = ["observed daily temperature", "signed HDD/CDD or temperature departure from fixed NOAA normal", "season", "same-contract volatility"]
rep8["implementation_gate"] = "Construct fixed season x sign cells from source-faithful observed weather, count cell capacity, and run multiplicity-aware power simulation before outcome execution."
rep8["pit_contract"] = rep7["pit_contract"].copy()

rep10 = by_id["rep-010-volatility-state-dependence"]
rep10["replication_class_target"] = "programme_synthesis_after_component_reproductions"
rep10["empirical_execution_planned"] = False
rep10["prerequisite_designs"] = [
    "rep-001-samuelson-maturity-volatility", "rep-002-seasonal-forward-curve",
    "rep-004-storage-state-nonlinearity", "rep-005-scarcity-volatility",
    "rep-007-weather-return-volatility-response", "rep-008-weather-season-sign-asymmetry",
    "rep-009-announcement-volatility",
]
rep10["primary_estimand"] = "No direct omnibus empirical estimand. After component reproductions are completed, synthesize their standardized effect directions, magnitudes, uncertainty and regime dependence without pooling incompatible raw observations."
rep10["primary_test"] = "No direct empirical test at this stage; synthesis is prerequisite-gated and cannot rescue a failed component reproduction."
rep10["disconfirmers"] = ["one or more claimed state families fail source-faithful reproduction", "a synthesis claim would require pooling incompatible grains or information sets"]

rep12 = by_id["rep-012-physical-balance-drivers"]
rep12["primary_frequency"] = "monthly"
rep12["primary_input_families"] = [
    "dry_or_marketed_production",
    "consumption",
    "pipeline_and_lng_import_exports",
    "storage_change",
]
rep12["source_route"] = {
    "physical_history": "eia_fundamentals current revised historical truth",
    "storage_history": "eia_storage revised historical truth",
    "market_reference": "EIA Henry Hub spot/reference price matched to selected source-study specification",
    "monthly_series": {
        "production": "NG.N9070US2.M",
        "consumption": "NG.N9140US2.M",
        "imports": "NG.N9100US2.M",
        "exports": "NG.N9130US2.M",
        "storage_working_gas": "NG.NGM_EPG0_SAO_R48_MMCF.M",
        "henry_hub_reference": "NG.RNGWHHD.M",
    },
    "physical_unit": "Million Cubic Feet",
    "metadata_basis": "retained EIA NG bulk snapshot metadata only; market outcome values not opened during selection",
}
rep12["sample"] = "Maximum monthly overlap of a fixed EIA historical snapshot for the four primary physical-balance families and the selected Henry Hub reference series. This is revised historical-truth mechanism replication only."
rep12["inputs"] = rep12["primary_input_families"]
rep12["primary_estimand"] = "Incremental explanatory contribution of the fixed monthly physical-balance core over calendar and lagged-price controls, with every component kept at native monthly availability rather than forward-filled to daily frequency."
rep12["secondary_estimands"] = ["power-sector gas demand under a separately verified source contract", "observed-weather departures under rep-007 source semantics", "LNG capacity/feedgas under rep-013 once released"]
rep12["implementation_gate"] = "Pin exact EIA series IDs/units and the Henry Hub reference-price specification before outcome access; preserve current-snapshot revised-history labeling and prohibit predictive interpretation."
rep20 = by_id["rep-020-positioning-incremental-information"]
rep20["primary_positioning_measure"] = "managed_money_net_change"
rep20["secondary_positioning_measures"] = ["managed_money_net_level", "managed_money_long_change", "managed_money_short_change"]
rep20["inputs"] = ["managed_money_net_change", "physical-control block", "season", "regime"]
rep20["primary_estimand"] = "Incremental explanatory contribution of weekly Managed Money net-position change after predeclared physical controls."
rep20["primary_test"] = "Nested weekly model block test with HAC uncertainty and publication-lag-correct joins; persistent position levels are secondary only."
rep20["representation_rationale"] = "The retained PIT series has AR1 about 0.907 for net levels (effective N about 6.63) versus AR1 about 0.166 for weekly net changes (effective N about 96.47). Choosing weekly change is a pre-outcome effective-information decision, not outcome tuning."
rep20["disconfirmers"] = ["weekly positioning change block below MEPI under informative power", "effect exists only when report date is incorrectly treated as publication date", "physical controls absorb the effect", "only persistent level specifications appear favorable while the predeclared change primary fails"]

payload["next_gate"] = "All five prior REDESIGN defects have been converted into source-coherent GO designs or a prerequisite HOLD. Current feasibility is 14 GO / 7 HOLD / 0 REDESIGN. Implement and verify GO machinery without empirical literature-result execution; HOLD releases remain governed by revisit-triggers.json and any empirical/freeze transition remains operator-gated."
write(designs_path, payload)
evidence_path = P / "evidence-map.json"
evidence = load(evidence_path)
evidence_by_id = {item["design_id"]: item for item in evidence["feasibility_map"]}
for design_id in (
    "rep-007-weather-return-volatility-response",
    "rep-008-weather-season-sign-asymmetry",
    "rep-012-physical-balance-drivers",
    "rep-020-positioning-incremental-information",
):
    evidence_by_id[design_id]["feasibility"] = "go"
evidence_by_id["rep-010-volatility-state-dependence"]["feasibility"] = "hold"
evidence_by_id["rep-007-weather-return-volatility-response"]["raw_information"] = 0
evidence_by_id["rep-007-weather-return-volatility-response"]["effective_information_method"] = {"method": "pending NOAA observed-weather acquisition and fixed station/weighting audit"}
evidence_by_id["rep-007-weather-return-volatility-response"]["hold_reason"] = "Official NOAA observed-weather and daily-normal source route is verified; implementation must pin stations/weights and count cells before outcome access."
evidence_by_id["rep-008-weather-season-sign-asymmetry"]["effective_information_method"] = {"method": "pending NOAA observed-weather season/sign cell construction"}
evidence_by_id["rep-008-weather-season-sign-asymmetry"]["hold_reason"] = "Observed-weather source mismatch is resolved in design; implementation must construct fixed source-faithful cells and power before outcomes."
evidence_by_id["rep-010-volatility-state-dependence"]["hold_reason"] = "Redesign is complete: this is now a non-empirical synthesis gated on successful source-faithful component reproductions."
evidence_by_id["rep-012-physical-balance-drivers"]["effective_information_method"] = {"method": "monthly source-coherent core; exact series IDs and dependence audit pending implementation"}
evidence_by_id["rep-012-physical-balance-drivers"]["hold_reason"] = "Omnibus mixed-frequency defect is resolved by a monthly EIA physical-balance core; implementation must pin exact series before outcomes."
evidence_by_id["rep-020-positioning-incremental-information"]["detectable_effect"] = 0.285
evidence_by_id["rep-020-positioning-incremental-information"]["effective_information_method"] = {"method": "weekly-change AR1 screen", "ar1": 0.1664403761, "effective_n": 96.4735}
evidence_by_id["rep-020-positioning-incremental-information"]["hold_reason"] = "Primary representation is fixed to Managed Money net weekly change using pre-outcome effective-information evidence; persistent levels remain secondary."
evidence["semantics"]["decision_counts"] = {"go": 14, "hold": 7, "redesign": 0}
write(evidence_path, evidence)
ledger_path = P / "feasibility-ledger.json"
ledger = load(ledger_path)
ledger_by_id = {item["design_id"]: item for item in ledger["entries"]}
for design_id in (
    "rep-007-weather-return-volatility-response",
    "rep-008-weather-season-sign-asymmetry",
    "rep-012-physical-balance-drivers",
    "rep-020-positioning-incremental-information",
):
    ledger_by_id[design_id]["decision"] = "GO"
ledger_by_id["rep-010-volatility-state-dependence"]["decision"] = "HOLD"
ledger_by_id["rep-007-weather-return-volatility-response"]["semantic_fidelity_class"] = "mechanism_replication_observed_weather_source_route_ready"
ledger_by_id["rep-007-weather-return-volatility-response"]["source_identities"] = ["noaa_observed_weather", "databento_henry_hub"]
ledger_by_id["rep-007-weather-return-volatility-response"]["remaining_blockers"] = ["acquire and pin NOAA observed-weather snapshot", "fix station/weighting rule", "count season cells and run block power"]
ledger_by_id["rep-008-weather-season-sign-asymmetry"]["semantic_fidelity_class"] = "near_replication_observed_weather_source_route_ready"
ledger_by_id["rep-008-weather-season-sign-asymmetry"]["source_identities"] = ["noaa_observed_weather", "databento_henry_hub"]
ledger_by_id["rep-008-weather-season-sign-asymmetry"]["remaining_blockers"] = ["acquire/pin NOAA observed weather", "fix season/sign cells", "multiplicity-aware cell power"]
ledger_by_id["rep-010-volatility-state-dependence"]["semantic_fidelity_class"] = "programme_synthesis_prerequisite_gated"
ledger_by_id["rep-010-volatility-state-dependence"]["remaining_blockers"] = ["complete prerequisite component reproductions under separate operator-authorized executions"]
ledger_by_id["rep-012-physical-balance-drivers"]["semantic_fidelity_class"] = "mechanism_replication_monthly_historical_truth_core_ready"
ledger_by_id["rep-012-physical-balance-drivers"]["source_identities"] = ["eia_fundamentals revised historical truth", "eia_storage revised historical truth", "EIA Henry Hub spot/reference"]
ledger_by_id["rep-012-physical-balance-drivers"]["remaining_blockers"] = ["pin exact EIA monthly series IDs/units", "fix source-study-compatible Henry Hub reference target", "derive family MEPI and time-series power"]
ledger_by_id["rep-020-positioning-incremental-information"]["effective_information"] = "Managed Money net weekly changes: AR1 0.16644 and effective N about 96.47; persistent net levels are secondary with effective N about 6.63."
ledger_by_id["rep-020-positioning-incremental-information"]["detectable_effect_screen"] = "Standardized weekly-change screen: 2.802/sqrt(96.47) about 0.285 SD before covariate/HAC inflation."
ledger_by_id["rep-020-positioning-incremental-information"]["remaining_blockers"] = ["fix physical-control block semantics", "derive numeric MEPI", "weekly HAC power simulation"]
ledger["decision_counts"] = {"GO": 14, "HOLD": 7, "REDESIGN": 0}
write(ledger_path, ledger)
setup_path = P / "experiment-setup.json"
setup = load(setup_path)
setup["canonical_inputs"]["observed_weather"] = {
    "source_id": "noaa_observed_weather",
    "status": "public_source_route_verified_not_acquired",
    "semantics": "GHCN-Daily observations plus fixed NOAA daily climate normals for historical-truth weather reproduction only; not a substitute for issued forecasts or PIT prediction.",
}
readiness_by_id = {item["design_id"]: item for item in setup["design_readiness"]}
readiness_by_id["rep-007-weather-return-volatility-response"] = {
    "design_id": "rep-007-weather-return-volatility-response",
    "source_readiness": "READY_FOR_IMPLEMENTATION_SOURCE_ROUTE",
    "reason": "Official NOAA GHCN-Daily plus daily-normal route resolves the issued-versus-observed source mismatch; acquire/pin stations and weighting before outcome access.",
}
readiness_by_id["rep-008-weather-season-sign-asymmetry"] = {
    "design_id": "rep-008-weather-season-sign-asymmetry",
    "source_readiness": "READY_FOR_IMPLEMENTATION_SOURCE_ROUTE",
    "reason": "Uses the same observed-weather route as rep-007; fixed season/sign cells and cell power remain implementation gates.",
}
readiness_by_id["rep-010-volatility-state-dependence"] = {
    "design_id": "rep-010-volatility-state-dependence",
    "source_readiness": "HOLD_COMPONENT_REPRODUCTIONS",
    "reason": "The design is now a non-empirical synthesis and remains held until its source-faithful component reproductions exist.",
}
readiness_by_id["rep-012-physical-balance-drivers"] = {
    "design_id": "rep-012-physical-balance-drivers",
    "source_readiness": "READY_FOR_MONTHLY_HISTORICAL_TRUTH_IMPLEMENTATION",
    "reason": "The prior mixed-frequency omnibus is replaced by a source-coherent monthly EIA physical-balance core; exact series IDs and target semantics remain pre-outcome implementation gates.",
}
readiness_by_id["rep-020-positioning-incremental-information"] = {
    "design_id": "rep-020-positioning-incremental-information",
    "source_readiness": "READY_FOR_WEEKLY_CHANGE_IMPLEMENTATION",
    "reason": "Managed Money net weekly change is fixed as the primary representation from pre-outcome effective-information evidence; levels remain secondary.",
}
setup["design_readiness"] = [readiness_by_id[item["design_id"]] for item in setup["design_readiness"]]
go_ids = [item["design_id"] for item in evidence["feasibility_map"] if item["feasibility"] == "go"]
hold_ids = [item["design_id"] for item in evidence["feasibility_map"] if item["feasibility"] == "hold"]
setup["feasibility_summary"] = {
    "decision_counts": {"GO": 14, "HOLD": 7, "REDESIGN": 0},
    "go": go_ids,
    "hold": hold_ids,
    "redesign": [],
    "authority_ref": "evidence-map.json",
}
setup["post_feasibility_work_order"] = [
    "Implement and verify the fourteen GO source/estimand/power constructions without executing literature outcomes.",
    "Keep rep-010 synthesis held until component reproductions are separately executed and verified.",
    "Resolve the six source/context/power HOLD gates through revisit-triggers.json.",
    "Return to the operator before any empirical literature-result execution, preregistration freeze, sealing, protected-evidence opening or confirmation transition.",
]
setup["next_action"] = "All prior REDESIGN defects are resolved in design. Implement/verify the fourteen GO routes; seven HOLD routes remain blocked. No empirical literature-result execution or freeze transition is authorized."
write(setup_path, setup)
readiness_path = P / "feasibility-readiness.json"
readiness = load(readiness_path)
readiness["holds"]["rep010"] = {
    "ready": False,
    "reason": "Programme synthesis cannot release until component reproductions have been separately executed and verified.",
}
write(readiness_path, readiness)

triggers_path = P / "revisit-triggers.json"
registry_payload = load(triggers_path)
if not any(item["trigger_id"] == "rep010-components-complete" for item in registry_payload["triggers"]):
    registry_payload["triggers"].append({
        "trigger_id": "rep010-components-complete",
        "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json",
        "disposition": "hold",
        "status": "active",
        "evidence_input": "research/programmes/002-henry-hub-fresh/feasibility-readiness.json",
        "metric": "holds.rep010.ready",
        "operator": "eq",
        "threshold": True,
        "successor_action": {"kind": "release_successor", "trace_ref": "research-line:004-volatility/rep-010-synthesis"},
    })
    registry_payload["evaluation_history"].append({
        "evaluation_id": "rep010-components-complete:2026-09-03T16:45:00+02:00",
        "evaluated_at": "2026-09-03T16:45:00+02:00",
        "trigger_id": "rep010-components-complete",
        "observed": False,
        "satisfied": False,
        "evidence_ref": "research/programmes/002-henry-hub-fresh/feasibility-readiness.json",
        "successor_ref": None,
    })
write(triggers_path, registry_payload)
decisions_path = P / "decisions.json"
decisions = load(decisions_path)
for item in [
    {"id": "observed-weather-route-selected", "decision": "Use NOAA GHCN-Daily plus U.S. Daily Climate Normals for programme-002 observed-weather reproductions; keep issued weather isolated to forecast/revision research.", "status": "active", "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json", "superseded_by": None},
    {"id": "volatility-state-synthesis-prerequisite-gated", "decision": "rep-010 is a non-empirical synthesis held until component reproductions exist; it will not pool incompatible raw state observations into one omnibus test.", "status": "active", "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json", "superseded_by": None},
    {"id": "positioning-change-primary", "decision": "Use Managed Money net weekly change as rep-020 primary because pre-outcome dependence diagnostics retain materially more effective information than levels; levels remain secondary.", "status": "active", "source_record": "research/programmes/002-henry-hub-fresh/feasibility-ledger.json", "superseded_by": None},
]:
    if not any(existing["id"] == item["id"] for existing in decisions["decisions"]):
        decisions["decisions"].append(item)
write(decisions_path, decisions)

backlog_path = P / "backlog.json"
backlog = load(backlog_path)
backlog["items"] = [
    {"id": "implement-go-machinery", "item": "Implement and verify source/estimand/power construction for the fourteen GO routes without opening literature outcomes.", "kind": "recommendation", "status": "open", "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json", "work_ref": "issue-289"},
    {"id": "resolve-held-source-contracts", "item": "Resolve the six source/context/power HOLD gates and re-evaluate their machine-readable revisit triggers.", "kind": "recommendation", "status": "open", "source_record": "research/programmes/002-henry-hub-fresh/revisit-triggers.json", "work_ref": "issue-289"},
    {"id": "release-volatility-synthesis-after-components", "item": "Release rep-010 only after its component reproductions have separately completed and been verified.", "kind": "recommendation", "status": "open", "source_record": "research/programmes/002-henry-hub-fresh/revisit-triggers.json", "work_ref": "issue-289"},
]
write(backlog_path, backlog)
synthesis_path = P / "research-synthesis.json"
synthesis = load(synthesis_path)
synthesis["scientific_design_state"] = "all_redesign_defects_resolved_non_outcome_implementation_stage_unfrozen"
synthesis["feasibility_summary"] = {
    "decision_counts": {"GO": 14, "HOLD": 7, "REDESIGN": 0},
    "go": go_ids,
    "hold": hold_ids,
    "redesign": [],
}
synthesis["next_stage"] = "Implement and verify the fourteen GO design constructions without empirical literature-result execution. Seven HOLD designs remain governed by revisit-triggers.json; all empirical/freeze/protected-evidence transitions remain operator-gated."
write(synthesis_path, synthesis)

closeout_path = P / "l0-l3-closeout.json"
closeout = load(closeout_path)
closeout["status"] = "reopened_design_feasibility_and_redesign_resolution_complete_unfrozen"
closeout["feasibility"] = {
    "authority_ref": "evidence-map.json",
    "supporting_detail_ref": "feasibility-ledger.json",
    "decision_counts": {"GO": 14, "HOLD": 7, "REDESIGN": 0},
    "redesign": [],
    "protected_evidence_opened": False,
    "outcome_effect_testing_performed": False,
}
closeout["next_stage"] = "Implement/verify GO machinery and resolve HOLD triggers only. No empirical literature-result execution, protected-evidence opening, preregistration, sealing or confirmation is authorized."
write(closeout_path, closeout)

print(json.dumps({"go": len(go_ids), "hold": len(hold_ids), "redesign": 0, "observed_weather_source": "noaa_observed_weather"}, indent=2))
