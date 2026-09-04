from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "research" / "programmes" / "002-henry-hub-fresh"
CHANGE = ROOT / ".work" / "changes" / "289-l0-l3-henry-hub-research"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


line_ids = [
    "001-market-structure",
    "002-storage-inventory",
    "003-weather",
    "004-volatility",
    "005-fundamental-balance",
    "006-cross-market-globalization",
    "007-positioning-announcements",
]
line_refs = [
    {"research_line_id": line_id, "path": f"research/programmes/002-henry-hub-fresh/lines/{line_id}/line.json"}
    for line_id in line_ids
]
programme = {
    "schema_version": 1,
    "zoom_level": "L1",
    "programme_id": "002-henry-hub-fresh",
    "legacy_programme_ids": [],
    "name": "Henry Hub literature-replication research programme",
    "mission": (
        "Independently establish which externally documented Henry Hub behaviours reproduce under source-faithful "
        "data and semantics, understand the variables and mechanisms that create them, and only then consider bounded "
        "predictive tests under a separate operator-authorized transition."
    ),
    "status": "active",
    "line_refs": line_refs,
}
write(P / "programme.json", programme)

source_scan = json.loads((CHANGE / "feasibility-scan.json").read_text(encoding="utf-8"))
source_scan["authority_note"] = (
    "Durable non-outcome source/coverage/dependence evidence copied from the governed feasibility scan so programme "
    "scientific state does not depend on ignored .work runtime state."
)
write(P / "feasibility-source-scan.json", source_scan)
feasibility = [
    ("rep-001-samuelson-maturity-volatility", "same-contract daily volatility by time-to-maturity", "daily listed-contract state", "maturity structure", 5025, {"method": "contract/calendar clustering screen", "contract_identities": 209}, 0.194, "go"),
    ("rep-002-seasonal-forward-curve", "seasonal forward-curve slope/shape", "monthly/year-block curve state", "curve seasonality", 195, {"method": "year-block lower-bound", "year_blocks": 17}, 0.680, "go"),
    ("rep-003-storage-surprise-response", "event return response to signed storage surprise", "EIA storage release event", "storage surprise", 0, {"method": "unavailable until fixed pre-release consensus is qualified"}, None, "hold"),
    ("rep-004-storage-state-nonlinearity", "storage-regime difference in market dynamics", "weekly historical storage state", "storage scarcity regime", 844, {"method": "AR1 and year-block sensitivity", "ar1_effective_n": 3.9823, "year_blocks": 17}, 1.401, "go"),
    ("rep-005-scarcity-volatility", "winter scarcity interaction in volatility", "weekly historical storage state", "scarcity volatility", 844, {"method": "AR1 and year-block sensitivity", "ar1_effective_n": 3.9823, "year_blocks": 17}, 1.401, "go"),
    ("rep-006-inventory-forward-curve-scarcity", "inventory association with front-versus-13th-month scarcity spread", "monthly exact-contract curve state", "inventory curve scarcity", 195, {"method": "year-block lower-bound", "year_blocks": 17}, 0.680, "go"),
    ("rep-007-weather-return-volatility-response", "observed-weather departure response in returns/volatility", "trade-day weather state", "observed weather", 0, {"method": "invalid until source-faithful observed-weather construction exists"}, None, "redesign"),
    ("rep-008-weather-season-sign-asymmetry", "season-by-sign observed-weather volatility asymmetry", "trade-day weather state", "weather asymmetry", 0, {"method": "invalid until source-faithful observed-weather cells exist"}, None, "redesign"),
]
feasibility += [
    ("rep-009-announcement-volatility", "announcement-day volatility elevation", "EIA release-day event", "announcement volatility", 106, {"method": "event-count screen with later HAC/year-block inference"}, 0.276, "go"),
    ("rep-010-volatility-state-dependence", "synthesis of source-faithful state-specific volatility effects", "family-specific state observations", "volatility state dependence", 0, {"method": "no valid joint effective N before family-specific redesign"}, None, "redesign"),
    ("rep-011-weather-enhanced-volatility-oos", "weather GARCH-MIDAS OOS forecast-loss improvement", "source-study daily forecast origins", "weather volatility forecasting", 0, {"method": "pending source-study weather/model reconstruction"}, None, "hold"),
    ("rep-012-physical-balance-drivers", "family-specific physical-balance explanatory contribution", "source-specific weekly/monthly state", "physical balance", 0, {"method": "omnibus N invalid until family-specific redesign"}, None, "redesign"),
    ("rep-013-lng-export-demand-channel", "LNG feedgas/capacity tightening channel", "terminal/month or terminal/day state", "LNG demand", 0, {"method": "pending terminal mapping and source contract"}, None, "hold"),
    ("rep-014-monthly-real-time-forecastability", "real-time monthly forecast MSPE versus no-change", "monthly origin x 1-24 month horizon", "real-time fundamentals", 0, {"method": "pending exact author-package import and overlapping-horizon audit"}, None, "go"),
    ("rep-015-oil-gas-linkage-regimes", "oil-Henry Hub linkage change across structural regimes", "monthly market state", "oil-gas linkage", 195, {"method": "raw monthly overlap screen; block/regime inference pending"}, 0.201, "go"),
    ("rep-016-europe-us-transmission-limited", "Henry Hub response to identified European gas shock", "source-study monthly structural system", "cross-basin transmission", 0, {"method": "pending exact RepOD package import and structural-system audit"}, None, "go"),
]
feasibility += [
    ("ctx-017-connectedness-congestion", "contextual congestion/connectedness design constraint", "context only", "cross-market contextual evidence", 0, {"method": "not a Henry Hub reproduction target"}, None, "hold"),
    ("rep-018-announcement-day-return-puzzle", "announcement-day return contrast with declared surprise controls", "EIA release-day event", "announcement return puzzle", 0, {"method": "full near-replication N unavailable until fixed pre-release consensus is qualified"}, None, "hold"),
    ("rep-019-friday-attention-effect", "Friday attenuation of storage-surprise response", "EIA storage release event", "release-day attention", 3, {"method": "Friday-event binding cell", "friday_events": 3, "thursday_events": 97}, 1.64, "hold"),
    ("rep-020-positioning-incremental-information", "incremental positioning information after physical controls", "weekly CFTC publication state", "managed-money positioning", 136, {"method": "representation sensitivity", "level_ar1_effective_n": 6.6277, "change_ar1_effective_n": 96.4735}, None, "redesign"),
    ("exp-021-issued-weather-revisions", "same-valid-time issued forecast revision mechanism", "issued forecast vintage", "issued weather revisions", 723, {"method": "immutable-vintage coverage screen"}, None, "go"),
]

ledger = json.loads((P / "feasibility-ledger.json").read_text(encoding="utf-8"))
reason_by_id = {item["design_id"]: item["power_sensitivity"] for item in ledger["entries"]}
entries = []
for design_id, target, horizon, family, raw_n, method, detectable, decision in feasibility:
    entries.append({
        "design_id": design_id,
        "target": target,
        "horizon": horizon,
        "information_family": family,
        "scientific_mepi": None,
        "raw_information": raw_n,
        "effective_information_method": method,
        "detectable_effect": detectable,
        "expected_snr": None,
        "costs": {},
        "feasibility": decision,
        "hold_reason": reason_by_id.get(design_id, "Feasibility/design disposition retained from the non-outcome ledger."),
    })
evidence_map = {
    "schema_version": 2,
    "zoom_level": "L1",
    "programme_id": "002-henry-hub-fresh",
    "current_scan_id": "non-outcome-feasibility-2026-09-03",
    "refresh_triggers": [
        "source_fidelity_or_entitlement_changes",
        "redesign_contract_completed",
        "implementation_verification_completed",
        "operator_authorizes_next_research_transition",
    ],
    "research_line_refs": line_refs,
    "feasibility_map": entries,
    "semantics": {
        "empirical_execution_authority": False,
        "preregistration_freeze_authority": False,
        "protected_evidence_opening_authority": False,
        "scientific_history_inherited": False,
        "supporting_detail_ref": "research/programmes/002-henry-hub-fresh/feasibility-ledger.json",
        "source_scan_ref": "research/programmes/002-henry-hub-fresh/feasibility-source-scan.json",
        "decision_counts": {"go": 10, "hold": 6, "redesign": 5},
        "rule": "GO authorizes implementation and verification of design machinery only; it does not authorize literature-result execution, preregistration, sealing, confirmation, or promotion.",
    },
}
write(P / "evidence-map.json", evidence_map)
line_meta = {
    "001-market-structure": ("maturity and seasonal curve structure", "Exact-contract market structure is the cleanest calibration layer for testing whether canonical Henry Hub market data preserve published stylized facts."),
    "002-storage-inventory": ("storage state, scarcity and forward-curve relations", "Storage is a central physical state variable in the Henry Hub literature, but revised-history descriptive reproduction must remain separate from PIT event/predictive use."),
    "003-weather": ("observed and issued weather mechanisms", "Weather affects gas demand, but observed-weather reproduction and issued-forecast/revision research are different information sets and must not be silently substituted."),
    "004-volatility": ("announcement and state-dependent volatility", "Volatility is a downstream market response that should be decomposed by source-faithful state families before any predictive model is selected."),
    "005-fundamental-balance": ("physical-balance and real-time fundamental mechanisms", "Production, demand, LNG, storage and other fundamentals need source-specific timing and frequency contracts before they can support explanation or forecasting."),
    "006-cross-market-globalization": ("oil, European gas and cross-market transmission", "Cross-market effects are regime- and infrastructure-dependent and must distinguish contemporaneous linkage from forecastable information."),
    "007-positioning-announcements": ("announcement anomalies, attention and positioning", "Scheduled information events and trader positioning are secondary mechanisms that require correct publication timing and adequate event/effective information."),
}
designs = json.loads((P / "experiment-designs.json").read_text(encoding="utf-8"))["designs"]
feasibility_by_id = {item["design_id"]: item["feasibility"] for item in entries}
for line_id in line_ids:
    role, why = line_meta[line_id]
    line_designs = [d["design_id"] for d in designs if d.get("line_id") == line_id]
    statuses = [f"{design_id}:{feasibility_by_id[design_id]}" for design_id in line_designs]
    line = {
        "schema_version": 1,
        "zoom_level": "L2",
        "programme_id": "002-henry-hub-fresh",
        "research_line_id": line_id,
        "legacy_research_line_ids": [],
        "status": "active",
        "selection_basis": "Fresh external-literature mapping under programme 002; no legacy internal result is used as scientific calibration or expected outcome.",
        "stopping_rules": {"empirical_execution_requires_operator_transition": True, "protected_outcome_access": False},
        "big_picture": f"This line tests {role} as part of the wider goal of understanding Henry Hub before prediction or model selection.",
        "why_zoomed_in": why,
        "tested_role_target_horizon": "No literature outcome has been tested in programme 002. Current evidence covers literature mapping, source semantics, source capacity, dependence and feasibility only.",
        "historical_facts": {
            "observed": "External literature findings and source/design feasibility have been mapped; programme 002 has completed zero internal empirical reproductions.",
            "rules_out": "Feasibility failures rule out the invalid source/design substitutions explicitly classified REDESIGN or HOLD; they do not establish a market null.",
            "does_not_rule_out": "Source-faithful versions of the mapped mechanisms remain open until implementation is verified and empirical execution is separately authorized.",
        },
        "useful_secondary_observations": statuses,
        "remaining_untested_roles": line_designs,
        "revisit_trigger": "Revisit empirical execution only after applicable HOLD/REDESIGN blockers are resolved, implementation/power contracts are verified, and the operator explicitly authorizes the transition.",
        "programme_interpretation": "This line remains pre-empirical. Literature support is external evidence, not an internal programme result.",
        "evidence_refs": [
            f"research/programmes/002-henry-hub-fresh/lines/{line_id}/findings/literature-findings.json",
            "research/programmes/002-henry-hub-fresh/evidence-map.json",
            "research/programmes/002-henry-hub-fresh/feasibility-ledger.json",
            "research/programmes/002-henry-hub-fresh/feasibility-source-scan.json",
        ],
        "experiment_history": [],
        "experiment_refs": [],
    }
    write(P / "lines" / line_id / "line.json", line)
write(P / "inference-ledger.json", {
    "schema_version": 1,
    "zoom_level": "L1",
    "programme_id": "002-henry-hub-fresh",
    "entries": [],
    "family_inference": [],
})
write(P / "sealed-windows.json", {
    "schema_version": 1,
    "zoom_level": "L1",
    "programme_id": "002-henry-hub-fresh",
    "windows": [],
})

readiness = {
    "schema_version": 1,
    "programme_id": "002-henry-hub-fresh",
    "holds": {
        "rep003": {"ready": False, "reason": "Historically fixed pre-release consensus source not yet qualified."},
        "rep011": {"ready": False, "reason": "Source-study historical weather provider/formulas/loss metric not yet reconstructed."},
        "rep013": {"ready": False, "reason": "Terminal mapping, EBB history and posting semantics not yet source-contracted."},
        "ctx017": {"ready": False, "reason": "No direct Henry Hub reproduction claim exists from the contextual European source alone."},
        "rep018": {"ready": False, "reason": "Full near replication still lacks fixed pre-release surprise controls."},
        "rep019": {"ready": False, "reason": "Exact subscription data unresolved and the retained Friday cell is only three events."},
    },
}
write(P / "feasibility-readiness.json", readiness)
write(P / "decisions.json", {
    "schema_version": 1,
    "zoom_level": "L1",
    "programme_id": "002-henry-hub-fresh",
    "generated_projection": False,
    "decisions": [
        {"id": "fresh-science-no-legacy-carry", "decision": "Programme 002 starts scientific state from external literature and fresh reproductions only; legacy repository outcomes are not inherited as programme evidence.", "status": "active", "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json", "superseded_by": None},
        {"id": "weather-information-sets-separated", "decision": "Observed-weather literature reproductions and issued-forecast/revision studies are separate information sets; the retained issued archive cannot substitute for observed-weather reproduction.", "status": "active", "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json", "superseded_by": None},
        {"id": "go-is-implementation-only", "decision": "A GO feasibility disposition authorizes implementation and verification only; empirical literature-result execution and any freeze/protected-evidence transition remain operator-gated.", "status": "active", "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json", "superseded_by": None},
    ],
})

backlog_items = [
    ("redesign-weather-reproduction", "Replace the invalid issued-weather reproduction inputs for rep-007/008 and downstream rep-010/012 with source-faithful observed-weather/climatology contracts."),
    ("redesign-volatility-state-synthesis", "Split rep-010 into family-specific valid state estimands before any joint volatility-state synthesis."),
    ("redesign-physical-balance", "Split rep-012 into source/frequency-specific balance mechanisms before any omnibus test."),
    ("redesign-positioning-primary", "Choose one predeclared primary positioning representation for rep-020, with weekly changes favored by effective-information diagnostics unless literature fidelity requires another route."),
    ("resolve-hold-sources", "Resolve the six HOLD source/power/context gates in revisit-triggers.json before successor execution."),
    ("implement-go-machinery", "Implement and verify source/estimand/power construction for the ten GO routes without opening literature outcomes."),
]
write(P / "backlog.json", {"schema_version": 1, "zoom_level": "L1", "programme_id": "002-henry-hub-fresh", "generated_projection": False, "items": [
    {"id": item_id, "item": text, "kind": "recommendation", "status": "open", "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json", "work_ref": "issue-289"}
    for item_id, text in backlog_items
]})
hold_specs = [
    ("rep003-source-ready", "rep003", "research-line:002-storage-inventory/rep-003-successor"),
    ("rep011-source-ready", "rep011", "research-line:004-volatility/rep-011-successor"),
    ("rep013-source-ready", "rep013", "research-line:005-fundamental-balance/rep-013-successor"),
    ("ctx017-direct-hh-evidence", "ctx017", "research-line:006-cross-market-globalization/ctx-017-successor"),
    ("rep018-surprise-controls-ready", "rep018", "research-line:007-positioning-announcements/rep-018-successor"),
    ("rep019-source-and-power-ready", "rep019", "research-line:007-positioning-announcements/rep-019-successor"),
]
triggers = []
history = []
stamp = "2026-09-03T16:30:00+02:00"
for trigger_id, key, trace_ref in hold_specs:
    triggers.append({
        "trigger_id": trigger_id,
        "source_record": "research/programmes/002-henry-hub-fresh/evidence-map.json",
        "disposition": "hold",
        "status": "active",
        "evidence_input": "research/programmes/002-henry-hub-fresh/feasibility-readiness.json",
        "metric": f"holds.{key}.ready",
        "operator": "eq",
        "threshold": True,
        "successor_action": {"kind": "release_successor", "trace_ref": trace_ref},
    })
    history.append({
        "evaluation_id": f"{trigger_id}:{stamp}",
        "evaluated_at": stamp,
        "trigger_id": trigger_id,
        "observed": False,
        "satisfied": False,
        "evidence_ref": "research/programmes/002-henry-hub-fresh/feasibility-readiness.json",
        "successor_ref": None,
    })
write(P / "revisit-triggers.json", {
    "schema_version": 1,
    "zoom_level": "L1",
    "programme_id": "002-henry-hub-fresh",
    "registry_id": "002-henry-hub-fresh-revisit-v1",
    "triggers": triggers,
    "evaluation_history": history,
})

ledger["source_scan_ref"] = "research/programmes/002-henry-hub-fresh/feasibility-source-scan.json"
ledger["empirical_execution_authority"] = False
write(P / "feasibility-ledger.json", ledger)

print(json.dumps({
    "programme": str(P / "programme.json"),
    "line_count": len(line_refs),
    "feasibility_entries": len(entries),
    "hold_triggers": len(triggers),
    "source_scan": str(P / "feasibility-source-scan.json"),
}, indent=2))
