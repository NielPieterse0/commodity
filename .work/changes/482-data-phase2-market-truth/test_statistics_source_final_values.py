"""Source-bound statistics reconciliation contract tests for #482 owner evidence."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_statistics_source_final_values as audit

from commodity.market_truth.errors import MarketTruthError
from commodity.market_truth.ng import databento_ng_settlement_eligible
from commodity.market_truth.revision import REVISION_GRAINS, canonicalize_versions

RECEIPT = Path(__file__).with_name("statistics-source-final-value-receipt.json")


class StatisticsOwnerEvidenceTests(unittest.TestCase):
    def test_receipt_is_exactly_pinned_and_not_owner_admission(self):
        item = json.loads(RECEIPT.read_bytes())
        self.assertEqual(item["source_sha256"], audit.PINNED["source_statistics"])
        self.assertEqual(item["final_sha256"], audit.PINNED["final_statistics"])
        self.assertEqual(
            item["source_manifest_sha256"], audit.PINNED["source_manifest"]
        )
        self.assertEqual(item["final_manifest_sha256"], audit.PINNED["final_manifest"])
        self.assertEqual(item["source_rows"], 2282697)
        self.assertEqual(item["final_rows"], 1177700)
        self.assertEqual(
            item["source_rows_by_type"],
            {"settle": 1594207, "cleared_volume": 344245, "open_interest": 344245},
        )
        self.assertEqual(
            item["final_rows_by_type"],
            {"settle": 489214, "cleared_volume": 344243, "open_interest": 344243},
        )
        self.assertEqual(item["unmatched_final_by_type"], {})
        self.assertEqual(item["duplicate_final_natural_grains"], 0)
        self.assertEqual(item["excess_final_source_occurrences"], 0)
        self.assertEqual(item["source_side_exclusion_total"], 1104997)
        self.assertEqual(item["source_side_exclusion_policy_rejected"], 1104466)
        self.assertEqual(item["source_side_economic_equivalent_retransmissions"], 531)
        self.assertEqual(item["source_side_exact_full_tuple_retransmissions"], 160)
        self.assertEqual(item["source_side_different_event_time_retransmissions"], 371)
        self.assertEqual(
            item["source_side_exact_full_tuple_retransmissions"]
            + item["source_side_different_event_time_retransmissions"], 531,
        )
        self.assertEqual(
            item["source_side_exclusion_policy_rejected"]
            + item["source_side_economic_equivalent_retransmissions"],
            item["source_side_exclusion_total"],
        )
        self.assertEqual(
            item["eligible_source_revision_grains_by_type"]["settle"]["economic_equivalent_retransmissions"], 527
        )
        self.assertTrue(all(
            value["conflicting_eligible_values"] == 0
            for value in item["eligible_source_revision_grains_by_type"].values()
        ))
        self.assertIs(item["parquet_final_has_exact_source_row"], True)
        self.assertIs(item["research_admitted"], False)
        self.assertIs(item["protected_2023plus_accessed"], False)
        self.assertTrue(any("V3 snapshot" in note for note in item["not_verified"]))

    def test_owner_dashboard_receipt_keeps_unfinished_acceptance_explicit(self):
        item = json.loads(RECEIPT.read_bytes())
        owner = json.loads(
            RECEIPT.with_name("owner-review-site-receipt.json").read_bytes()
        )
        summary = owner["statistics_value_reconciliation"]
        self.assertEqual(summary["receipt"], RECEIPT.name)
        self.assertEqual(summary["source_rows"], item["source_rows"])
        self.assertEqual(summary["final_rows"], item["final_rows"])
        self.assertEqual(summary["exact_source_matched_final_rows"], item["final_rows"])
        self.assertEqual(summary["unmatched_final_rows"], 0)
        self.assertTrue(summary["source_final_table_only_not_V3_selected_view"])
        self.assertFalse(summary["source_side_exclusion_reconciliation_pending"])
        self.assertEqual(summary["source_side_exclusion_total"], item["source_side_exclusion_total"])
        self.assertEqual(summary["source_side_exclusion_unaccounted"], 0)
        self.assertEqual(
            summary["source_side_economic_equivalent_retransmissions"],
            item["source_side_economic_equivalent_retransmissions"],
        )
        self.assertEqual(
            summary["source_side_exclusion_policy_rejected"],
            item["source_side_exclusion_policy_rejected"],
        )
        self.assertEqual(
            summary["source_side_exact_full_tuple_retransmissions"],
            item["source_side_exact_full_tuple_retransmissions"],
        )
        self.assertEqual(
            summary["source_side_different_event_time_retransmissions"],
            item["source_side_different_event_time_retransmissions"],
        )
        self.assertEqual(
            summary["source_side_exclusion_unaccounted"],
            summary["source_side_exclusion_total"]
            - summary["source_side_exclusion_policy_rejected"]
            - summary["source_side_economic_equivalent_retransmissions"],
        )
        self.assertFalse(summary["independent_settlement_finality_verified"])
        self.assertFalse(summary["owner_research_approval_issued"])
        self.assertFalse(owner["review_intent"]["production_admission_granted"])
        self.assertTrue(
            any("quarantined undated" in value for value in item["not_verified"])
        )
        self.assertTrue(
            any("signed research admission" in value for value in item["not_verified"])
        )

    def test_ng_settlement_finality_boundaries_are_explicit(self):
        row = {"trade_date": "2015-11-19", "stat_flags": "2"}
        self.assertTrue(databento_ng_settlement_eligible(row))
        row["trade_date"] = "2015-11-20"
        self.assertFalse(databento_ng_settlement_eligible(row))
        for flags, expected in ((1, True), (3, True), (100, False),
                                (101, False), (9, False), (0, False)):
            row["stat_flags"] = str(flags)
            self.assertIs(databento_ng_settlement_eligible(row), expected)

    def test_same_grain_distinct_event_clock_is_not_exact_tuple(self):
        fact = {
            "instrument_id": "42", "trade_date": "2020-01-02",
            "stat_type": "settle", "available_at": "2020-01-03T12:00:00+00:00",
            "event_at": "2020-01-03T10:00:00+00:00",
            "value": 2.5, "source_vintage_id": None, "evidence_id": "a" * 64,
        }
        replay = {**fact, "event_at": "2020-01-03T11:00:00+00:00",
                  "evidence_id": "b" * 64}
        self.assertNotEqual(fact["event_at"], replay["event_at"])
        selected = canonicalize_versions(
            [replay, fact], REVISION_GRAINS["statistics"], "statistic"
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["event_at"], fact["event_at"])
        with self.assertRaisesRegex(MarketTruthError, "ambiguous statistic revision"):
            canonicalize_versions(
                [fact, {**replay, "value": 2.6}],
                REVISION_GRAINS["statistics"], "statistic",
            )

    def test_modified_final_manifest_fails_before_analytic_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "manifest.json"
            fake.write_text('{"dataset_scope":"development_pre2023"}')
            with (
                patch.object(audit, "FINAL_MANIFEST", fake),
                self.assertRaisesRegex(
                    RuntimeError, "pinned source/final statistics changed"
                ),
            ):
                audit.verify_pins()

    def test_modified_source_fails_before_analytic_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            altered = Path(temporary) / "fake.csv"
            altered.write_text("stat_type,trade_date\n3,2012-01-01\n")
            with (
                patch.object(audit, "SOURCE", altered),
                self.assertRaisesRegex(
                    RuntimeError, "pinned source/final statistics changed"
                ),
            ):
                audit.verify_pins()

    def test_private_pinned_full_replay_offline(self):
        if os.name == "nt":
            self.skipTest("Windows native DuckDB is blocked by Application Control")
        self.assertEqual(audit.audit(), json.loads(RECEIPT.read_bytes()))
