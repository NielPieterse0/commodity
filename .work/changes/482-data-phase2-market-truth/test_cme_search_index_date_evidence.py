"""Check externally indexed CME date evidence without promoting research authority."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_four_historical_notice_rows_match_exact_source_dates():
    evidence = json.loads((ROOT / "cme-exchange-date-corroboration.json").read_bytes())
    source = json.loads((ROOT / "cme-official-evidence-queue.json").read_bytes())
    by_month = {case["delivery_month"]: case for case in source["cases"]}
    new_cases = [
        case
        for case in evidence["verified_dates"]
        if case.get("evidence_access")
        == "indexed_CME_PDF_text_only_direct_PDF_not_retrieved"
    ]
    assert {case["delivery_month"] for case in new_cases} == {
        "2011-01",
        "2011-06",
        "2018-04",
        "2014-12",
    }
    assert evidence["indexed_pdf_row_matches_without_download"] == 4
    assert len(new_cases) == 4
    for case in new_cases:
        assert (
            case["official_last_trade_date"]
            == by_month[case["delivery_month"]]["source_expiration_ny_date"]
        )
        assert case["source_url"].startswith("https://www.cmegroup.com/")
        assert (
            case["evidence_access"]
            == "indexed_CME_PDF_text_only_direct_PDF_not_retrieved"
        )
        assert case["independent_pdf_bytes_verified"] is False
        assert case["external_archive_sha256"] is None
        assert "Natural Gas" in case["official_row_context"]


def test_no_date_only_exchange_rows_remain_unmatched():
    evidence = json.loads((ROOT / "cme-exchange-date-corroboration.json").read_bytes())
    assert evidence["open_cases"] == []
    assert evidence["exchange_day_matched_count"] == 14
    assert evidence["not_yet_independently_row_verified_count"] == 0
    assert "original PDFs not downloaded" in evidence["date_corroboration_basis"]


def test_index_results_are_not_exchange_archive_or_research_approval():
    evidence = json.loads((ROOT / "cme-exchange-date-corroboration.json").read_bytes())
    boundary = json.loads((ROOT / "cme-expiry-closeout-boundary.json").read_bytes())
    assert evidence["original_blocker_closed"] is False
    assert evidence["research_admission_granted"] is False
    assert evidence["exchange_notice_raw_bytes_immutably_pinned"] is False
    assert evidence["source_expiry_intraday_time_exchange_verified"] is False
    assert evidence["protected_2023plus_accessed"] is False
    assert boundary["CME_notice_bytes_immutably_pinned"] == 0
    assert boundary["official_contract_dates_verified"] == 0
    assert boundary["CME_indexed_PDF_rows_recovered"] == 4
    assert boundary["CME_contract_rows_not_independently_read"] == 4
    assert boundary["CME_contract_rows_independently_read_not_archived"] == 10
    assert evidence["direct_official_document_rows_read"] == 10
    assert evidence["index_only_not_directly_retrieved"] == 4
    assert boundary["research_admission_granted"] is False
