"""Synthetic tests for source-pinned contract identity continuity; no private archive reads."""
from __future__ import annotations

import unittest

from audit_cross_year_contract_identity import latest_identity, require_same_contract


def definition(*, event: str = "2013-01-01T00:00:00Z",
               received: str = "2013-01-01T00:00:00Z",
               symbol: str = "NGF8", expiry: str = "2017-12-27T19:30:00Z"):
    return {
        "ts_event": event, "ts_recv": received,
        "asset": "NG", "instrument_class": "F", "exchange": "XNYM",
        "raw_symbol": symbol, "expiration": expiry,
    }


class CrossYearIdentityTests(unittest.TestCase):
    def test_matching_contract_crosses_year(self):
        old = definition(event="2012-12-31T00:00:00Z",
                         received="2012-12-31T00:00:00Z")
        new = definition()
        self.assertEqual(latest_identity([old], "2013-01-02T10:00:00Z"),
                         latest_identity([new], "2013-01-02T10:00:00Z"))

    def test_future_definition_does_not_attest_prior_publication(self):
        future = definition(received="2013-01-03T00:00:00Z")
        self.assertIsNone(latest_identity([future], "2013-01-02T10:00:00Z"))

    def test_revised_definition_time_is_respected(self):
        old = definition(event="2012-12-30T00:00:00Z",
                         received="2012-12-31T00:00:00Z")
        changed = definition(received="2013-01-03T00:00:00Z", expiry="2020-12-27T19:30:00Z")
        self.assertEqual(latest_identity([old, changed], "2013-01-02T00:00:00Z"),
                         latest_identity([old], "2013-01-02T00:00:00Z"))
        self.assertNotEqual(latest_identity([old, changed], "2013-01-04T00:00:00Z"),
                            latest_identity([old], "2013-01-04T00:00:00Z"))

    def test_reused_instrument_id_is_not_contract_continuity(self):
        with self.assertRaisesRegex(ValueError, "identity not proven"):
            require_same_contract([definition(symbol="NGF8")],
                                  [definition(symbol="NGF9")],
                                  "2013-01-02T00:00:00Z")

    def test_missing_current_definition_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "identity not proven"):
            require_same_contract([definition()], [], "2013-01-02T00:00:00Z")

    def test_equal_clock_conflict_fails_closed(self):
        old = definition()
        conflicting = definition(symbol="NGF9")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            latest_identity([old, conflicting], "2013-01-02T00:00:00Z")

    def test_timezone_offsets_compared_as_instants(self):
        old = definition(received="2013-01-01T02:00:00+02:00")
        new = definition(received="2013-01-01T00:00:00Z")
        self.assertEqual(latest_identity([old], "2013-01-01T00:00:00Z"),
                         latest_identity([new], "2013-01-01T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()
