from __future__ import annotations

import json
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
P = WT / "research" / "programmes" / "002-henry-hub-fresh"
C = WT / ".work" / "changes" / "289-l0-l3-henry-hub-research"
files = {
    "designs": P / "experiment-designs.json", "setup": P / "experiment-setup.json",
    "programme": P / "programme.json", "synthesis": P / "research-synthesis.json",
    "closeout": P / "l0-l3-closeout.json", "map": P / "evidence-map.json",
    "ledger": P / "feasibility-ledger.json", "scan": C / "feasibility-scan.json",
}
data = {name: json.loads(path.read_text(encoding="utf-8-sig")) for name, path in files.items()}
design_ids = [row["design_id"] for row in data["designs"]["designs"]]
ledger_ids = [row["design_id"] for row in data["ledger"]["entries"]]
map_ids = [row["design_id"] for row in data["map"]["feasibility_map"]]
checks = {
    "json_parse": len(data) == len(files),
    "design_count_21": len(design_ids) == 21 and len(set(design_ids)) == 21,
    "design_identity_match": set(design_ids) == set(ledger_ids) == set(map_ids),
    "decision_counts": data["ledger"]["decision_counts"] == {"GO": 10, "HOLD": 6, "REDESIGN": 5} == data["map"]["decision_counts"] == data["setup"]["feasibility_summary"]["decision_counts"],
    "map_setup_sets": all(set(data["setup"]["feasibility_summary"][k.lower()]) == {r["design_id"] for r in data["map"]["feasibility_map"] if r["feasibility"] == k} for k in ("GO", "HOLD", "REDESIGN")),
    "scan_no_outcomes": data["scan"]["outcome_effect_testing_performed"] is False and data["scan"]["protected_evidence_opened"] is False,
    "ledger_no_outcomes": data["ledger"]["outcome_effect_testing_performed"] is False and data["ledger"]["protected_evidence_opened"] is False,
    "ledger_no_execution": data["ledger"]["empirical_execution_authority"] is False and data["ledger"]["preregistration_freeze_authority"] is False and all(not r["freeze_ready"] and not r["empirical_execution_authority"] for r in data["ledger"]["entries"]),
    "programme_no_execution": data["programme"]["empirical_execution_authority"] is False,
    "setup_no_execution": all(value is False for value in data["setup"]["authority"].values()),
    "designs_no_execution": data["designs"]["empirical_execution_authority"] is False and data["designs"]["preregistration_authority"] is False and data["designs"]["confirmation_authority"] is False,
    "map_no_execution": all(data["map"]["semantics"][key] is False for key in ("empirical_execution_authority", "preregistration_freeze_authority", "protected_evidence_opening_authority")),
    "weather_retained_window": data["scan"]["weather"]["rows"] == 723 and data["scan"]["weather"]["coverage_start"] == "2024-08-13" and data["scan"]["weather"]["coverage_end"] == "2026-08-12",
    "storage_dependence": abs(data["scan"]["storage_history"]["storage_anomaly_ar1_effective_n"] - 3.9822831866766637) < 1e-9,
    "cftc_dependence": abs(data["scan"]["cftc"]["managed_money_net_dependence"]["change_ar1_effective_n"] - 96.47346878667378) < 1e-9,
    "canonical_owner": data["ledger"]["canonical_feasibility_owner"].endswith("evidence-map.json") and data["map"]["semantics"]["feasibility_owner"] == "this_file",
}
status = "pass" if all(checks.values()) else "fail"
payload = {"schema_version": 1, "status": status, "checks": checks, "files": {name: str(path.relative_to(WT)) for name, path in files.items()}}
out = C / "feasibility-verification.json"
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2, sort_keys=True))
raise SystemExit(0 if status == "pass" else 1)
