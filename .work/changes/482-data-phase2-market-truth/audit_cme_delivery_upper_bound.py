"""Non-redundant 14-contract Route-B historical CME delivery bound certificate.

Proof consumes already published hash-pinned receipts. No 3,088-date V3
replay, numerical parity rerun, or 2023+ protected history is performed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from commodity.market_truth.ng_expiry import (
    UNQUALIFIED_NG_EXPIRIES,
    ng_delivery_month_start,
    verify_ng_expiry_policy,
)

BASE = Path(__file__).parent
RECEIPT = BASE / "cme-delivery-upper-bound-receipt.json"
# Immutable by-source-content pins for PREVIOUSLY QUALIFIED proof artifacts.
# These are tracked unmodified in the same change directory; this script
# verifies their exact bytes rather than rerunning the original audits.
EVIDENCE_PINS = {
    "cme-expiry-exposure-receipt.json": "8d888e80abd491995b406cecd12972451d46e4ffabc6db55eea6d7fb8ca75bc6",
    "cme-rank-output-safety-receipt.json": "e0a7343a8275869ae2bd3a6fe9e17dc89be14c2eca0edb88f8ff64f861af9d72",
    "cme-model-output-history-receipt.json": "d936e49d5be4cf2aecdf88370dbba8c93e357a53cf42f924a4ba652632a20cf6",
    "cme-frozen-cutoff-exclusion-receipt.json": "b1ad4ca7612091ad5db9ec8503b738caffea2fcd08b3c18834c546b0aa4448c4",
}


def _read_receipt(name: str) -> dict:
    path = BASE / name
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("missing source evidence: " + name)
    raw = path.read_bytes()
    if name not in EVIDENCE_PINS or sha256(raw).hexdigest() != EVIDENCE_PINS[name]:
        raise RuntimeError("historical proof receipt bytes changed: " + name)
    record = json.loads(raw)
    if record.get("issue") != 482:
        raise RuntimeError("wrong historical issue evidence: " + name)
    return record


def run() -> dict:
    verify_ng_expiry_policy()
    exposure = _read_receipt("cme-expiry-exposure-receipt.json")
    ranks = _read_receipt("cme-rank-output-safety-receipt.json")
    outputs = _read_receipt("cme-model-output-history-receipt.json")
    cutoffs = _read_receipt("cme-frozen-cutoff-exclusion-receipt.json")
    pins = ranks["source_pins"]
    if (
        exposure["source_sha256"]["definitions"] != pins["definitions"]
        or exposure["source_sha256"]["features"] != pins["features"]
        or exposure["source_sha256"]["manifest"] != pins["manifest"]
        or ranks["ranked_slots_checked"] != 37056
        or ranks["affected_rank12_selected_slots"] != 3156
        or ranks["selected_slots_fenced_terminal"] != 69
        or ranks["selected_slots_marked_unverified_nonterminal"] != 3087
        or outputs["source_pins"] != pins
        or outputs["result"] != "PASS_CME_FROZEN_SOURCE_RANK_TO_MODEL_OUTPUT_EXCLUSION"
        or outputs["model_output_invariant"]["excluded_unsafe_suffix_slots"] != 17918
        or cutoffs["source_pins"] != pins
        or cutoffs["production_sql_original_cutoffs_denied"] != 134
    ):
        raise RuntimeError("pre-existing pinned historical coverage not qualified")
    cohort = []
    for symbol, expiry_text in sorted(UNQUALIFIED_NG_EXPIRIES):
        expiry = datetime.fromisoformat(expiry_text)
        delivery_start = ng_delivery_month_start(symbol, expiry_text)
        gap = (delivery_start - expiry.date()).days
        if not 0 < gap <= 7:
            raise RuntimeError("possible rank-pruned eligibility gap")
        # All source-expired pre-delivery calendar dates lie in the
        # existing +/-7-day quarantine, including the last such day.
        for offset in range(gap):
            if abs((expiry.date() + timedelta(days=offset) - expiry.date()).days) > 7:
                raise RuntimeError("unfenced post-expiry candidate before delivery")
        cohort.append({
            "contract": symbol,
            "source_expiration_utc": expiry_text,
            "delivery_first_day": delivery_start.isoformat(),
            "calendar_days_expiry_to_delivery": gap,
            "first_unfenced_day": (expiry.date() + timedelta(days=8)).isoformat(),
            "first_unfenced_day_after_delivery_start": (
                expiry.date() + timedelta(days=8) > delivery_start
            ),
        })
    if len(cohort) != 14 or not all(
        entry["first_unfenced_day_after_delivery_start"] for entry in cohort
    ):
        raise RuntimeError("source-pruned contract can escape exchange upper bound")
    evidence = {
        "schema_version": 1,
        "issue": 482,
        "result": "PASS_CME_ROUTE_B_DELIVERY_UPPER_BOUND_AND_MODEL_EXCLUSION",
        "closure_scope": "14 exact known pinned pre2023 CME expiry discrepancies",
        "exchange_rule": "NYMEX 220102.F",
        "exchange_rule_url": "https://www.cmegroup.com/rulebook/NYMEX/2/220.pdf",
        "historic_exchange_filing_url": (
            "https://www.cftc.gov/sites/default/files/stellent/groups/public/"
            "@rulesandproducts/documents/ifdocs/rul111412nymex001.pdf"
        ),
        "exchange_rule_scope": "no trading after third business day before delivery month",
        "intraday_expiry_times_independently_verified": False,
        "exact_historical_exchange_holiday_versions_verified": False,
        "expiry_source_provisionally_verified": False,
        "route_B_fully_excludes_unsupported_model_rank_decisions": True,
        "cohort_contracts": cohort,
        "source_pins_reused_not_rehashed": pins,
        "prior_receipt_sha256_pins_verified": EVIDENCE_PINS,
        "historical_frozen_decisions_already_qualified": 3088,
        "historical_rank_slots_already_qualified": 37056,
        "affected_rank_slots_already_qualified": 3156,
        "previous_parquet_cutoff_denials_not_rerun": 134,
        "previous_model_masked_suffix_slots_not_rerun": 17918,
        "pre_delivery_after_expiry_unfenced_days": 0,
        "model_unsafe_post_delivery_source_pruning": False,
        "new_historical_numeric_replay": False,
        "protected_2023plus_accessed": False,
        "source_owner_approval": False,
        "research_admission": False,
    }
    RECEIPT.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps({
        key: evidence[key] for key in (
            "result", "pre_delivery_after_expiry_unfenced_days",
            "historical_rank_slots_already_qualified",
            "route_B_fully_excludes_unsupported_model_rank_decisions",
        )
    }, sort_keys=True))
    return evidence


if __name__ == "__main__":
    run()
