from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAMME = ROOT / "research" / "programmes" / "002-henry-hub-fresh"


def load(name: str) -> dict:
    return json.loads((PROGRAMME / name).read_text(encoding="utf-8-sig"))


constructors = {
    "rep-001-samuelson-maturity-volatility": ["rank_contracts_by_expiration", "select_exact_maturity_ranks", "same_contract_log_returns", "ar1_effective_information", "standardized_detectable_effect"],
    "rep-002-seasonal-forward-curve": ["rank_contracts_by_expiration", "build_curve_snapshot_eligibility", "select_exact_maturity_ranks", "standardized_detectable_effect"],
    "rep-004-storage-state-nonlinearity": ["build_storage_seasonal_state", "build_exact_monthly_panel", "ar1_effective_information", "standardized_detectable_effect"],
    "rep-005-scarcity-volatility": ["build_storage_seasonal_state", "same_contract_log_returns", "ar1_effective_information", "standardized_detectable_effect"],
    "rep-006-inventory-forward-curve-scarcity": ["build_storage_seasonal_state", "select_exact_maturity_ranks", "build_exact_monthly_panel", "standardized_detectable_effect"],
    "rep-007-weather-return-volatility-response": ["build_observed_weather_departures", "build_weather_state_cells", "same_contract_log_returns", "ar1_effective_information", "standardized_detectable_effect"],
    "rep-008-weather-season-sign-asymmetry": ["build_observed_weather_departures", "build_weather_state_cells", "same_contract_log_returns", "standardized_detectable_effect"],
}
constructors.update({
    "rep-009-announcement-volatility": ["build_release_calendar", "build_release_day_labels", "same_contract_log_returns", "ar1_effective_information", "standardized_detectable_effect"],
    "rep-012-physical-balance-drivers": ["build_monthly_physical_balance_core", "build_exact_monthly_panel", "ar1_effective_information", "standardized_detectable_effect"],
    "rep-014-monthly-real-time-forecastability": ["validate_replication_package_manifest", "standardized_detectable_effect"],
    "rep-015-oil-gas-linkage-regimes": ["build_exact_monthly_panel", "standardized_detectable_effect"],
    "rep-016-europe-us-transmission-limited": ["validate_replication_package_manifest", "standardized_detectable_effect"],
    "rep-020-positioning-incremental-information": ["managed_money_weekly_changes", "ar1_effective_information", "standardized_detectable_effect"],
    "exp-021-issued-weather-revisions": ["build_same_valid_time_revisions", "ar1_effective_information", "standardized_detectable_effect"],
})

pending_source = {
    "rep-006-inventory-forward-curve-scarcity": "FRED GS1 snapshot and exact source-study spread formula not yet pinned",
    "rep-007-weather-return-volatility-response": "NOAA observed-weather snapshot/station-weight contract not yet acquired and pinned",
    "rep-008-weather-season-sign-asymmetry": "NOAA observed-weather snapshot/station-weight contract not yet acquired and pinned",
    "rep-014-monthly-real-time-forecastability": "author JAE replication package not yet imported/hash-bound in repository evidence",
    "rep-015-oil-gas-linkage-regimes": "public EIA WTI monthly snapshot and paper-compatible regime semantics not yet pinned",
    "rep-016-europe-us-transmission-limited": "author RepOD replication package not yet imported/hash-bound in repository evidence",
}

source_ids = {
    "rep-006-inventory-forward-curve-scarcity": ["databento_henry_hub", "eia_storage", "US-MACRO"],
    "rep-007-weather-return-volatility-response": ["noaa_observed_weather", "databento_henry_hub"],
    "rep-008-weather-season-sign-asymmetry": ["noaa_observed_weather", "databento_henry_hub"],
    "rep-014-monthly-real-time-forecastability": ["LIT-BHLR-RTDB"],
    "rep-015-oil-gas-linkage-regimes": ["US-OIL"],
    "rep-016-europe-us-transmission-limited": ["LIT-RS-EUUS"],
}
source_parameters = {
    "rep-006-inventory-forward-curve-scarcity": {"one_year_rate": "FRED:GS1"},
    "rep-014-monthly-real-time-forecastability": {"archive_doi": "10.15456/jae.2025266.1900967125"},
    "rep-015-oil-gas-linkage-regimes": {"implementation_benchmark": "EIA Cushing WTI spot monthly (rwtc)", "fidelity": "mechanism_replication_candidate_not_exact_paper_substitution"},
    "rep-016-europe-us-transmission-limited": {"archive_doi": "10.18150/KCPFNE"},
}

ledger = load("feasibility-ledger.json")
ledger_by_id = {item["design_id"]: item for item in ledger["entries"]}
go_ids = [item["design_id"] for item in ledger["entries"] if item["decision"] == "GO"]
if set(go_ids) != set(constructors):
    raise SystemExit(f"GO mapping mismatch: missing={sorted(set(go_ids)-set(constructors))} extra={sorted(set(constructors)-set(go_ids))}")

entries = []
for design_id in go_ids:
    source_pending = pending_source.get(design_id)
    entries.append({
        "design_id": design_id,
        "constructors": constructors[design_id],
        "source_ids": source_ids.get(design_id, ledger_by_id[design_id].get("source_identities", [])),
        "source_parameters": source_parameters.get(design_id, {}),
        "remaining_pre_outcome_work": ledger_by_id[design_id].get("remaining_blockers", []),
        "implementation_status": (
            "machinery_implemented_source_artifact_pending"
            if source_pending
            else "machinery_implemented"
        ),
        "source_artifact_blocker": source_pending,
        "verification_mode": "synthetic_and_adversarial_only_for_any_constructor_that_touches_outcome_fields",
        "real_data_literature_outcome_execution_allowed": False,
        "empirical_execution_authority": False,
        "preregistration_freeze_authority": False,
        "protected_evidence_opening_authority": False,
    })

payload = {
    "schema_version": 1,
    "programme_id": "002-henry-hub-fresh",
    "implementation_layer": "outcome_blind_construction_and_power_machinery",
    "reusable_module": "src/commodity/research_construction.py",
    "entries": entries,
    "operator_gate": "Implementation verification does not authorize application to real literature outcomes, preregistration, sealing, protected evidence, confirmation, or promotion.",
}
(PROGRAMME / "implementation-contracts.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
for name in ("experiment-setup.json", "research-synthesis.json", "l0-l3-closeout.json"):
    record = load(name)
    record["implementation_contracts_ref"] = "implementation-contracts.json"
    record["implementation_status"] = {
        "go_designs_mapped": len(entries),
        "machinery_implemented": len(entries) - len(pending_source),
        "machinery_implemented_source_artifact_pending": len(pending_source),
        "empirical_execution_authority": False,
    }
    (PROGRAMME / name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"go_mapped": len(entries), "source_artifact_pending": sorted(pending_source)}, indent=2))
