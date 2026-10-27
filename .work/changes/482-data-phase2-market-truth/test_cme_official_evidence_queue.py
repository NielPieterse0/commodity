"""Fail-closed tests for the per-contract CME evidence queue (not date approval)."""

import json
import tempfile
import unittest
from pathlib import Path

from audit_cme_official_evidence_queue import SOURCE, SOURCE_SHA256, build_queue


class CmeOfficialEvidenceQueueTests(unittest.TestCase):
    def test_missing_or_altered_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.csv"
            with self.assertRaises(RuntimeError):
                build_queue(bad)
            bad.write_text("invented,expiration\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                build_queue(bad)

    def test_exact_source_replay_matches_retained_queue(self):
        if not SOURCE.is_file():
            self.skipTest("Pinned private development source not mounted")
        expected = json.loads(
            (Path(__file__).parent / "cme-official-evidence-queue.json").read_bytes()
        )
        self.assertEqual(build_queue(), expected)

    def test_pinned_queue_has_no_unverified_promotions(self):
        path = Path(__file__).parent / "cme-official-evidence-queue.json"
        report = json.loads(path.read_bytes())
        self.assertEqual(report["source_csv_sha256"], SOURCE_SHA256)
        self.assertEqual(len(report["cases"]), 14)
        self.assertFalse(report["all_official_expiries_verified"])
        self.assertEqual(report["dates_promoted"], 0)
        self.assertFalse(report["research_admission_approved"])
        self.assertFalse(report["protected_2023plus_accessed"])
        self.assertEqual(
            sum(bool(c["notice_candidate_url"]) for c in report["cases"]), 3
        )
        self.assertTrue(
            all(not c["official_CME_last_trade_verified"] for c in report["cases"])
        )
        self.assertEqual(
            len({(c["delivery_month"], c["source_symbol"]) for c in report["cases"]}),
            14,
        )
