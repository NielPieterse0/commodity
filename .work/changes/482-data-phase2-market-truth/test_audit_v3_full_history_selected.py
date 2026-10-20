"""Fresh narrow tests for full-history selected V3 audit accounting."""
from __future__ import annotations

import runpy
import unittest
from pathlib import Path

MODULE = runpy.run_path(str(Path(__file__).with_name("audit_v3_full_history_selected.py")))
new_bucket = MODULE["_new_bucket"]
update = MODULE["update_bucket"]


class BucketTests(unittest.TestCase):
    def test_numeric_equal_difference_and_signed_magnitude(self):
        bucket = new_bucket()
        update(bucket, "numeric", 0.0)
        update(bucket, "numeric", -0.4)
        self.assertEqual(bucket["numeric_pairs"], 2)
        self.assertEqual(bucket["exact"], 1)
        self.assertEqual(bucket["different"], 1)
        self.assertAlmostEqual(bucket["max_abs_delta"], 0.4)
        self.assertAlmostEqual(bucket["sum_abs_delta"], 0.4)

    def test_exclusion_and_unavailable_never_count_as_comparison(self):
        bucket = new_bucket()
        for status in (
            "excluded_rank", "excluded_window", "unavailable_rank",
            "missing_source", "null_value",
        ):
            update(bucket, status)
            self.assertEqual(bucket[status], 1)
        self.assertEqual(bucket["numeric_pairs"], 0)
        self.assertEqual(bucket["exact"], 0)

    def test_unknown_or_missing_numeric_delta_fails(self):
        bucket = new_bucket()
        with self.assertRaisesRegex(ValueError, "outcome"):
            update(bucket, "approved")
        with self.assertRaisesRegex(ValueError, "delta"):
            update(bucket, "numeric")


if __name__ == "__main__":
    unittest.main()
