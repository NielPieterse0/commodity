"""Pinned statistics diagnostic: identity, accounting and admission boundaries."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from commodity.market_truth import review_site
from commodity.market_truth.errors import MarketTruthError


class StatisticsReceiptTests(unittest.TestCase):
    def setUp(self):
        self.receipt_path = review_site.STATISTICS_AUDIT_RECEIPT
        self.report = json.loads(self.receipt_path.read_bytes())
        self.meta = {
            "families": {"statistics": {
                "source_sha256": self.report["source_sha256"],
                "final_sha256": self.report["final_sha256"],
                "source_rows": self.report["source_rows"],
                "final_rows": self.report["final_rows"],
            }},
            "source_manifest_sha256": self.report["source_manifest_sha256"],
            "final_manifest_sha256": self.report["final_manifest_sha256"],
            "dataset_content_sha256": "c" * 64,
        }
    def test_pinned_receipt_exposes_eligible_facts_and_real_exclusions(self):
        result = review_site.verify_statistics_receipt(self.receipt_path, self.meta)
        self.assertFalse(result["research_admitted"])
        self.assertFalse(result["source_pit_qualified"])
        self.assertEqual(result["source_rows_by_type"]["settle"], 1594207)
        self.assertEqual(result["final_rows_by_type"]["settle"], 489214)
        self.assertEqual(result["excluded_by_policy"], 1104466)
        self.assertEqual(result["excluded_retransmissions"], 531)
        self.assertEqual(result["final_unmatched"], 0)

    def altered(self, change, *, repin=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            document = json.loads(json.dumps(self.report))
            change(document)
            data = json.dumps(document, sort_keys=True).encode()
            path.write_bytes(data)
            if repin:
                with patch.object(
                    review_site, "STATISTICS_AUDIT_SHA256",
                    hashlib.sha256(data).hexdigest(),
                ):
                    return review_site.verify_statistics_receipt(path, self.meta)
            return review_site.verify_statistics_receipt(path, self.meta)

    def test_changed_receipt_bytes_are_rejected(self):
        with self.assertRaisesRegex(MarketTruthError, "not verified"):
            self.altered(lambda doc: doc.update(source_rows=1))
    def test_rehashed_false_row_accounting_is_rejected(self):
        with self.assertRaisesRegex(MarketTruthError, "accounting"):
            self.altered(
                lambda doc: doc["final_rows_by_type"].update(settle=489215),
                repin=True,
            )

    def test_rehashed_admission_claim_is_rejected(self):
        with self.assertRaisesRegex(MarketTruthError, "release boundary"):
            self.altered(lambda doc: doc.update(research_admitted=True), repin=True)

    def test_rehashed_wrong_dataset_identity_is_rejected(self):
        with self.assertRaisesRegex(MarketTruthError, "release boundary"):
            self.altered(
                lambda doc: doc.update(final_sha256="f" * 64), repin=True,
            )

    def test_receipt_cannot_be_swapped_between_hashing_and_parsing(self):
        """A former separate digest read could accept a forged replacement."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_bytes(self.receipt_path.read_bytes())
            forged = json.loads(json.dumps(self.report))
            forged["source_side_exclusion_policy_rejected"] += 1
            forged["source_side_economic_equivalent_retransmissions"] -= 1

            def legacy_hash_then_swap(_path):
                path.write_text(json.dumps(forged), encoding="utf-8")
                return review_site.STATISTICS_AUDIT_SHA256

            with patch.object(
                review_site, "digest_file", side_effect=legacy_hash_then_swap,
            ) as former_hash_call:
                result = review_site.verify_statistics_receipt(path, self.meta)
                former_hash_call.assert_not_called()
            self.assertEqual(
                result["excluded_by_policy"],
                self.report["source_side_exclusion_policy_rejected"],
            )

    def test_missing_source_is_rejected(self):
        with self.assertRaisesRegex(MarketTruthError, "not verified"):
            review_site.verify_statistics_receipt(
                Path("__missing_statistics_receipt__.json"), self.meta,
            )


if __name__ == "__main__":
    unittest.main()
