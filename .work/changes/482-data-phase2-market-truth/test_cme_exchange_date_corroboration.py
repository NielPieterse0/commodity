"""Conservative independent-date corroboration ledger checks for #482.

This validates source/evidence alignment, not remote document bytes or approval.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit

DIRECTORY = Path(__file__).resolve().parent


def check_cme_date_evidence(record: dict, queue: dict) -> None:
    if (
        record.get("original_blocker_closed") is not False
        or record.get("exchange_notice_raw_bytes_immutably_pinned") is not False
        or record.get("source_expiry_intraday_time_exchange_verified") is not False
        or record.get("research_admission_granted") is not False
        or record.get("protected_2023plus_accessed") is not False
        or record.get("source_sha256") != queue.get("source_csv_sha256")
    ):
        raise ValueError("unsafe CME provenance or admission assertion")
    cases = queue.get("cases", [])
    indexed = {case["delivery_month"]: case for case in cases}
    if len(cases) != 14 or len(indexed) != 14:
        raise ValueError("unexpected CME contract source cohort")
    confirmed = record.get("verified_dates", [])
    unresolved = record.get("open_cases", [])
    indexed_only = {
        case["delivery_month"]
        for case in confirmed
        if case.get("evidence_access")
        == "indexed_CME_PDF_text_only_direct_PDF_not_retrieved"
        and case.get("independent_pdf_bytes_verified") is False
    }
    if (
        indexed_only != {"2011-01", "2011-06", "2014-12", "2018-04"}
        or record.get("index_only_not_directly_retrieved") != len(indexed_only)
        or record.get("direct_official_document_rows_read") != len(cases) - len(indexed_only)
        or record.get("historical_intraday_context", {}).get(
            "contract_specific_2010_to_2022_expiry_time_certified"
        ) is not False
    ):
        raise ValueError("unqualified CME direct-versus-index-only evidence")
    claimed = [case["delivery_month"] for case in confirmed + unresolved]
    if len(claimed) != 14 or len(set(claimed)) != 14 or set(claimed) != set(indexed):
        raise ValueError("missing, duplicate or extra CME contract evidence")
    if len(confirmed) != record.get("exchange_day_matched_count") or len(
        unresolved
    ) != record.get("not_yet_independently_row_verified_count"):
        raise ValueError("incorrect case evidence totals")
    for case in confirmed:
        origin = indexed[case["delivery_month"]]
        if (
            case["official_last_trade_date"] != origin["source_expiration_ny_date"]
            or case.get("external_archive_sha256") is not None
            or case.get("verification_basis")
            != "CME issuer's dated, product-specific historical record"
            or "Natural Gas" not in case["official_row_context"]
            or urlsplit(case["source_url"]).hostname != "www.cmegroup.com"
            or urlsplit(case["source_url"]).scheme != "https"
        ):
            raise ValueError("unqualified exchange date or forged external source")
    for case in unresolved:
        if (
            case["provider_date_unverified"]
            != indexed[case["delivery_month"]]["source_expiration_ny_date"]
            or case["status"] != "notice_identified_but_contract_row_not_verified"
        ):
            raise ValueError("unqualified date promotion")


class CmeExternalCorroborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(
            (DIRECTORY / "cme-exchange-date-corroboration.json").read_bytes()
        )
        cls.queue = json.loads(
            (DIRECTORY / "cme-official-evidence-queue.json").read_bytes()
        )

    def test_ledger_reconciles_full_source_cohort(self):
        check_cme_date_evidence(self.record, self.queue)
        self.assertEqual(len(self.record["verified_dates"]), 14)
        self.assertEqual(len(self.record["open_cases"]), 0)
        months = [
            row["delivery_month"]
            for row in self.record["verified_dates"] + self.record["open_cases"]
        ]
        expected_months = {row["delivery_month"] for row in self.queue["cases"]}
        self.assertEqual(len(months), 14)
        self.assertEqual(len(set(months)), 14)
        self.assertEqual(set(months), expected_months)

    def test_original_blocker_ledger_remains_open(self):
        boundary = json.loads(
            (DIRECTORY / "cme-expiry-closeout-boundary.json").read_bytes()
        )
        self.assertEqual(
            boundary["official_exchange_date_corroboration_record"],
            "cme-exchange-date-corroboration.json",
        )
        self.assertEqual(boundary["external_CME_date_only_matches_not_byte_pinned"], 14)
        self.assertEqual(boundary["CME_contract_rows_not_independently_read"], 4)
        self.assertEqual(boundary["CME_contract_rows_independently_read_not_archived"], 10)
        self.assertEqual(boundary["CME_notice_bytes_immutably_pinned"], 0)
        self.assertEqual(boundary["official_contract_dates_verified"], 0)
        self.assertFalse(self.record["original_blocker_closed"])

    def test_tampered_exchange_date_fails(self):
        altered = copy.deepcopy(self.record)
        altered["verified_dates"][0]["official_last_trade_date"] = "2099-01-01"
        with self.assertRaisesRegex(ValueError, "unqualified"):
            check_cme_date_evidence(altered, self.queue)

    def test_index_only_evidence_cannot_be_mislabeled_direct(self):
        altered = copy.deepcopy(self.record)
        altered["direct_official_document_rows_read"] = 14
        altered["index_only_not_directly_retrieved"] = 0
        with self.assertRaisesRegex(ValueError, "unqualified CME"):
            check_cme_date_evidence(altered, self.queue)

    def test_historical_regulator_context_cannot_certify_intraday_expiry(self):
        altered = copy.deepcopy(self.record)
        altered["historical_intraday_context"][
            "contract_specific_2010_to_2022_expiry_time_certified"
        ] = True
        with self.assertRaisesRegex(ValueError, "unqualified CME"):
            check_cme_date_evidence(altered, self.queue)

    def test_missing_contract_case_fails(self):
        altered = copy.deepcopy(self.record)
        altered["verified_dates"].pop()
        with self.assertRaisesRegex(ValueError, "missing"):
            check_cme_date_evidence(altered, self.queue)

    def test_external_proof_does_not_self_authorize_research(self):
        altered = copy.deepcopy(self.record)
        altered["original_blocker_closed"] = True
        with self.assertRaisesRegex(ValueError, "unsafe"):
            check_cme_date_evidence(altered, self.queue)

    def test_non_cme_evidence_url_fails(self):
        altered = copy.deepcopy(self.record)
        altered["verified_dates"][0]["source_url"] = "https://example.com/claim.pdf"
        with self.assertRaisesRegex(ValueError, "unqualified"):
            check_cme_date_evidence(altered, self.queue)
