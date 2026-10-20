"""Source-specific undated statistic recovery safety, without opening history."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.data import recover_ng_unreferenced_statistics as recovery


class UnreferencedSourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = self.root / "raw_checked" / "statistics"
        self.raw.mkdir(parents=True)
        self.file = self.raw / "glbx-mdp3-20100606-20101231.statistics.dbn.zst"
        self.file.write_bytes(b"raw_fixture")
        self.record = {
            "family": "statistics",
            "filename": self.file.name,
            "bytes": self.file.stat().st_size,
            "sha256": hashlib.sha256(self.file.read_bytes()).hexdigest(),
        }
        (self.root / "definitions-2010.csv").write_text(
            "instrument_id,asset\n1,NG\n2,NG\n", encoding="utf-8"
        )
        self.patcher = patch.object(recovery, "STAGE", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_source_requires_exact_pinned_bytes_and_name(self):
        source, digest = recovery.expected_source(2010, {"raw_objects": [self.record]})
        self.assertEqual(source, self.file)
        self.assertEqual(digest, self.record["sha256"])
        self.file.write_bytes(b"mutated")
        with self.assertRaisesRegex(ValueError, "integrity failure"):
            recovery.expected_source(2010, {"raw_objects": [self.record]})

    def test_missing_year_and_ambiguous_receipt_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "missing pinned"):
            recovery.expected_source(2011, {"raw_objects": [self.record]})
        with self.assertRaisesRegex(ValueError, "missing pinned"):
            recovery.expected_source(2010, {"raw_objects": [self.record, self.record]})
        self.assertEqual(recovery.YEARS, tuple(range(2010, 2016)))

    def test_unverified_2023_confirmation_is_rejected_before_extraction(self):
        receipt = {
            "dataset": "GLBX.MDP3",
            "protected_confirmation_accessed": True,
            "raw_objects": [self.record],
        }
        (self.root / "raw-stage-receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "development evidence"):
            recovery.run()
        self.assertFalse((self.root / recovery.OUTPUT_NAME).exists())

    def test_interrupted_extraction_retained_and_next_run_can_succeed(self):
        (self.root / "raw-stage-receipt.json").write_text(
            json.dumps({
                "dataset": "GLBX.MDP3",
                "protected_confirmation_accessed": False,
                "raw_objects": [self.record],
            }), encoding="utf-8", newline="\n",
        )

        def failure(year, receipt, output):
            (output / f"partial-{year}.txt").write_text(
                "incomplete", encoding="utf-8", newline="\n",
            )
            raise ValueError("artificial mid-extraction failure")

        with (
            patch.object(recovery, "extract_year", side_effect=failure),
            self.assertRaisesRegex(ValueError, "artificial"),
        ):
            recovery.run()
        self.assertFalse((self.root / recovery.OUTPUT_NAME).exists())
        incomplete = list(self.root.glob(recovery.OUTPUT_NAME + "-incomplete-*"))
        self.assertEqual(len(incomplete), 1)
        self.assertTrue((incomplete[0] / "partial-2010.txt").exists())

        def success(year, receipt, output):
            name = f"undefined-ref-{year}.csv.gz"
            (output / name).write_bytes(b"synthetic output")
            return {
                "year": year, "relative_path": name,
                "recovered_unreferenced_type6": 1,
                "recovered_unreferenced_type9": 1,
            }

        with patch.object(recovery, "extract_year", side_effect=success):
            result = recovery.run()
        self.assertEqual(result["totals"], {"type6": 6, "type9": 6})
        self.assertTrue((self.root / recovery.OUTPUT_NAME / "receipt.json").exists())
        self.assertTrue((incomplete[0] / "partial-2010.txt").exists())
        with (
            patch.object(recovery, "extract_year", side_effect=success),
            self.assertRaisesRegex(ValueError, "overwrite"),
        ):
            recovery.run()

    def test_local_target_instrument_set_is_explicit(self):
        self.assertEqual(recovery.accepted_instruments(2010), {1, 2})
        with self.assertRaisesRegex(ValueError, "missing curated"):
            recovery.accepted_instruments(2015)


if __name__ == "__main__":
    unittest.main()
