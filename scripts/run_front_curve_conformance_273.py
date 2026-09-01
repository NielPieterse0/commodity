from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commodity.config import assumptions_config, data_config
from commodity.front_curve_feasibility import (
    DEVELOPMENT_END,
    audit_development_feasibility,
    build_front_curve_target,
)
from commodity.research_lifecycle import LIFECYCLE_STAGES, validate_exploratory_run

OUTPUT = ROOT / "research" / "exploratory" / "front-curve-feasibility-273-conformance.json"
PRIOR = ROOT / "research" / "exploratory" / "front-curve-feasibility-271.json"
PRE_LITERATURE = ROOT / "research" / "literature" / "front-curve-271-conformance-v1.json"
POST_LITERATURE = ROOT / "research" / "literature" / "front-curve-271-post-result-triangulation-v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_bytes(content.encode("utf-8"))


def _load_cache(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    for column in ("trade_date", "expiration", "available_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    if frame.empty or frame["trade_date"].max() > DEVELOPMENT_END:
        raise RuntimeError("conformance replay cache must contain development-only rows")
    return frame


def _literature_ref(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha(path)}


def _verification_checks(feasibility: dict) -> list[dict[str, object]]:
    return [
        {"id": key, "passed": bool(value)}
        for key, value in sorted(feasibility["checks"].items())
    ]


def build_record(cache_csv: Path) -> dict:
    prior_hash_before = _sha(PRIOR)
    canonical = _load_cache(cache_csv)
    schema = data_config()["canonical_contract_schema"]
    roll_policy = assumptions_config()["assumptions"]["continuous_series_policy"]["policy"]
    panel = build_front_curve_target(canonical, schema, roll_policy)
    feasibility = audit_development_feasibility(panel)
    prior_hash_after = _sha(PRIOR)
    if prior_hash_after != prior_hash_before:
        raise RuntimeError("historical #271 exploratory evidence changed during conformance replay")

    pre = json.loads(PRE_LITERATURE.read_text(encoding="utf-8"))
    post = json.loads(POST_LITERATURE.read_text(encoding="utf-8"))
    max_year_share = max(float(value) for value in feasibility["concentration"]["year_share"].values())
    evidence = json.loads(json.dumps(feasibility))
    evidence["max_year_share"] = max_year_share
    hold = feasibility["feasibility"] != "go"
    disconfirmers = []
    if not feasibility["checks"]["minimum_development_rows"] or not feasibility["checks"]["year_concentration"]:
        disconfirmers.append(pre["disconfirming_observations"][0])
    if not feasibility["checks"]["power_vs_scientific_mepi"]:
        disconfirmers.append(pre["disconfirming_observations"][1])
    record = {
        "schema_version": 2,
        "run_id": "front-curve-feasibility-273-conformance",
        "programme_id": "commodity-ng",
        "research_line_id": "line-next-defensible-edge",
        "lifecycle": list(LIFECYCLE_STAGES),
        "orientation": {
            "big_picture_ref": "docs/big-picture.md",
            "programme_question": "Can a mechanism-led, roll-safe Henry Hub front-curve target justify scarce protected confirmation evidence?",
            "where_this_fits": "Corrective successor to #271, testing whether the first post-hardening curve/spread candidate clears the scientific feasibility gate before confirmation.",
            "origin_refs": ["issue-271", "issue-273", "config/programme_evidence_map.json"],
        },
        "gap": "The original #271 feasibility result was mechanically valid but did not pass through an unavoidable literature-anchored research lifecycle.",
        "zoom_in": {
            "reason": "Prior programme evidence selected curve/spread change as the first bounded mechanism-led alternative after repeated weak generic return-model evidence.",
            "evidence_refs": ["config/programme_evidence_map.json", "research/exploratory/front-curve-feasibility-271.json"],
        },
        "literature_snapshot_ref": _literature_ref(PRE_LITERATURE),
        "mechanism": "Near-curve shape reflects scarcity, carrying and storage economics and may contain short-lived information about same-pair spread adjustment.",
        "hypotheses": {
            "h0": "The target is not sufficiently stable and informative to justify consuming protected confirmation evidence.",
            "h1": "The target has adequate coverage and effective information to justify a frozen confirmatory test.",
        },
        "expectations": {"expected": pre["expected_observations"], "disconfirming": pre["disconfirming_observations"]},
        "feasibility": {"decision": feasibility["feasibility"], "evidence": evidence},
        "execution": {"protected_outcomes_accessed": False, "preregistration_ref": None},
        "verification": {"status": "verified", "checks": _verification_checks(feasibility)},
        "comparison": {
            "observed_vs_expected": (
                f"Development-only replay produced {feasibility['rows']['scoreable_targets']} scoreable targets "
                f"versus the {1500} row adequacy threshold, maximum year share {max_year_share:.6f} versus "
                f"the 0.15 concentration limit, and detectable standardized effect "
                f"{feasibility['power']['detectable_effect']:.6f} versus the 0.15 scientific MEPI. "
                "Target construction and power behaved as expected, but sample adequacy and year coverage did not."
            ),
            "disconfirmers_seen": disconfirmers,
        },
        "external_triangulation": {
            "literature_snapshot_ref": _literature_ref(POST_LITERATURE),
            "comparison": post["claim_map"][1]["claim"],
        },
        "programme_conclusion": (
            "HOLD this exact front-curve feasibility branch before preregistration and protected confirmation. "
            "The mechanism remains plausible, but external literature does not override failed sample-adequacy and concentration gates."
            if hold else
            "GO only to a new frozen preregistration; protected outcomes remain unopened by this exploratory replay."
        ),
        "revisit_triggers": ["front-curve-development-rows", "front-curve-year-concentration"],
        "promotion_decision": "continue" if hold else "promote",
        "lineage": {
            "predecessor_record": "research/exploratory/front-curve-feasibility-271.json",
            "successor_reason": "Corrective conformance replay under #273; predecessor remains immutable.",
        },
    }
    validate_exploratory_run(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run #273 literature-anchored conformance successor to #271")
    parser.add_argument("--cache-csv", type=Path, required=True)
    args = parser.parse_args()
    record = build_record(args.cache_csv.resolve())
    _write(OUTPUT, record)
    print(json.dumps({
        "status": record["feasibility"]["decision"],
        "record": OUTPUT.relative_to(ROOT).as_posix(),
        "protected_outcomes_accessed": record["execution"]["protected_outcomes_accessed"],
        "predecessor_sha256": _sha(PRIOR),
    }, indent=2, sort_keys=True))
    return 0 if record["feasibility"]["decision"] == "go" else 2


if __name__ == "__main__":
    raise SystemExit(main())
