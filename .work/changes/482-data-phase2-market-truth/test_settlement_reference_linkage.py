"""Small synthetic checks; no private archive or protected outcomes needed."""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("audit_settlement_reference_linkage.py")
SPEC = importlib.util.spec_from_file_location("ng_settlement_linkage", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def clock(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class LinkageTests(unittest.TestCase):
    def test_exception_categories_remain_non_promotable(self):
        cases = (
            ("no_prior_settlement", "2015-11-20T10:00:00Z",
             "no_prior_settlement"),
            ("ambiguous_same_clock_settlement", "2015-11-20T10:00:00Z",
             "ambiguous_same_clock_settlement"),
            ("2015-11-19", "2015-11-20T10:00:00Z",
             "candidate_1_4_day_lag"),
            ("2015-11-16", "2015-11-20T10:00:00Z",
             "candidate_1_4_day_lag"),
            ("2015-11-15", "2015-11-20T10:00:00Z",
             "outside_1_4_day_lag"),
            ("2015-11-20", "2015-11-20T10:00:00Z",
             "outside_1_4_day_lag"),
        )
        for outcome, event, expected in cases:
            with self.subTest(outcome=outcome):
                self.assertEqual(AUDIT.classify_link(outcome, event), expected)

    def test_year_local_missing_prior_can_be_boundary_artifact(self):
        previous = [(clock("2012-12-31T16:00:00Z"), "2012-12-28")]
        current = [(clock("2013-01-02T16:00:00Z"), "2013-01-02")]
        event = "2013-01-01T15:00:00Z"
        self.assertEqual(AUDIT.correlate(current, event), "no_prior_settlement")
        candidate = AUDIT.correlate(previous, event)
        self.assertEqual(candidate, "2012-12-28")
        self.assertEqual(AUDIT.classify_link(candidate, event), "candidate_1_4_day_lag")

    def test_source_digest_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixed.csv"
            path.write_bytes(b"original")
            AUDIT.checked(path, hashlib.sha256(b"original").hexdigest())
            path.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                AUDIT.checked(path, hashlib.sha256(b"original").hexdigest())

    def test_never_look_ahead_to_future_settlement(self):
        rows = [
            (clock("2015-11-18T15:00:00Z"), "2015-11-17"),
            (clock("2015-11-19T16:00:00Z"), "2015-11-19"),
        ]
        self.assertEqual(
            AUDIT.correlate(rows, "2015-11-19T15:00:00Z"), "2015-11-17"
        )
        self.assertEqual(
            AUDIT.correlate(rows, "2015-11-19T17:00:00Z"), "2015-11-19"
        )

    def test_delayed_receive_time_never_used_early(self):
        item = {"ts_event": "2015-11-19T15:00:00Z",
                "ts_recv": "2015-11-19T16:00:00Z"}
        published = AUDIT.publication_clock(item)
        self.assertEqual(published, clock("2015-11-19T16:00:00Z"))
        settlement = [(published, "2015-11-18")]
        self.assertEqual(
            AUDIT.correlate(settlement, "2015-11-19T15:30:00Z"),
            "no_prior_settlement",
        )
        self.assertEqual(
            AUDIT.correlate(settlement, "2015-11-19T16:00:00Z"),
            "2015-11-18",
        )

    def test_conflicting_same_clock_revisions_fail_closed(self):
        t = clock("2015-11-19T16:00:00Z")
        rows = [(t, "2015-11-17"), (t, "2015-11-19"),
                (t, "2015-11-19")]
        self.assertEqual(
            AUDIT.correlate(rows, "2015-11-20T07:00:00Z"),
            "ambiguous_same_clock_settlement",
        )

    def test_no_previously_published_settlement(self):
        t = clock("2015-11-19T16:00:00Z")
        self.assertEqual(AUDIT.correlate([], "2015-11-20T07:00:00Z"),
                         "no_prior_settlement")
        self.assertEqual(
            AUDIT.correlate([(t, "2015-11-19")], "2015-11-19T15:00:00Z"),
            "no_prior_settlement",
        )


if __name__ == "__main__":
    unittest.main()
