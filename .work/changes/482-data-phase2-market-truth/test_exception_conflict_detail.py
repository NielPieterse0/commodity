"""Synthetic tests for the exception-only settlement clock diagnostic."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import audit_exception_conflict_detail as audit_module
from audit_exception_conflict_detail import (
    clock_identity,
    detail_for,
    exact_clock,
    inspect,
)


def entry(clock: str, reference_day: str, flags: str = "0"):
    normalized = clock_identity(clock)
    return (normalized, reference_day, flags, "")


class ExceptionConflictDetailTests(unittest.TestCase):
    def test_two_reference_days_at_same_clock_stay_ambiguous(self):
        clock = "2011-02-03T08:00:00+00:00"
        result = detail_for(sorted([
            entry(clock, "2011-02-01", "100"),
            entry(clock, "2011-02-02", "0"),
        ]), clock)
        self.assertEqual(result["status"], "ambiguous_same_clock_settlement")
        self.assertEqual(result["distinct_reference_dates"], 2)
        self.assertEqual(result["settlement_versions"], 2)
        self.assertEqual(result["flag_shapes"], ["0", "100"])

    def test_distinct_nanosecond_clocks_cannot_be_mislabeled_same_clock(self):
        # Python datetime truncates the seventh through ninth fractional digits.
        first = entry("2012-06-07T09:00:00.123456001+00:00",
                      "2012-06-05", "100")
        second = entry("2012-06-07T09:00:00.123456002+00:00",
                       "2012-06-06", "0")
        self.assertEqual(first[0][0], second[0][0])
        self.assertLess(first[0], second[0])
        result = detail_for(sorted([first, second]),
                            "2012-06-07T09:00:00.123456002+00:00")
        self.assertEqual(result["status"], "candidate_1_4_day_lag")
        self.assertEqual(result["calendar_day_lag"], 1)

    def test_mixed_timezone_forms_never_create_false_nanosecond_ties(self):
        first = entry("2012-06-07 09:00:00.123456001+00:00",
                      "2012-06-05", "100")
        second = entry("2012-06-07T11:00:00.123456002+02:00",
                       "2012-06-06", "0")
        self.assertEqual(first[0][0], second[0][0])
        self.assertTrue(first[0][0].isoformat().endswith("+00:00"))
        self.assertTrue(second[0][0].isoformat().endswith("+00:00"))
        self.assertLess(first[0], second[0])
        result = detail_for(sorted([first, second]),
                            "2012-06-07T09:00:00.123456003Z")
        self.assertEqual(result["calendar_day_lag"], 1)

    def test_single_future_nanosecond_settlement_not_used(self):
        newer = entry("2012-06-07T09:00:00.123456999+00:00",
                      "2012-06-06")
        result = detail_for([newer], "2012-06-07T09:00:00.123456001Z")
        self.assertEqual(result["status"], "no_prior_settlement")

    def test_mixed_causal_and_future_nanosecond_rows_ignore_reference_sort(self):
        for future_reference in ("2012-06-04", "2012-06-07"):
            with self.subTest(future_reference=future_reference):
                past = entry("2012-06-07T09:00:00.123456001+00:00",
                             "2012-06-06")
                future = entry("2012-06-07T09:00:00.123456999+00:00",
                               future_reference)
                result = detail_for(
                    sorted([past, future]), "2012-06-07T09:00:00.123456002Z"
                )
                self.assertEqual(result["status"], "candidate_1_4_day_lag")
                self.assertEqual(result["calendar_day_lag"], 1)

    def test_known_preliminary_flag_is_not_silently_resolved(self):
        clock = "2012-06-07T09:00:00+00:00"
        result = detail_for(sorted([
            entry(clock, "2012-06-05", "100"),
            entry(clock, "2012-06-06", "0"),
        ]), "2012-06-07T09:00:01+00:00")
        self.assertEqual(result["status"], "ambiguous_same_clock_settlement")

    def test_same_day_lag_is_not_accepted_as_date(self):
        result = detail_for([
            entry("2010-11-16T07:00:00+00:00", "2010-11-16")
        ], "2010-11-16T08:00:00+00:00")
        self.assertEqual(result["status"], "outside_1_4_day_lag")
        self.assertEqual(result["calendar_day_lag"], 0)

    def test_1_to_4_days_is_candidate_only_not_verified_truth(self):
        source = [entry("2015-11-20T07:00:00+00:00", "2015-11-19")]
        result = detail_for(source, "2015-11-20T07:00:01+00:00")
        self.assertEqual(result["status"], "candidate_1_4_day_lag")
        self.assertEqual(result["calendar_day_lag"], 1)

    def test_lag_boundaries_are_inclusive_only_for_days_one_to_four(self):
        source = [entry("2015-04-05T08:00:00+00:00", "2015-04-01")]
        accepted = detail_for(source, "2015-04-05T08:01:00+00:00")
        self.assertEqual(accepted["status"], "candidate_1_4_day_lag")
        self.assertEqual(accepted["calendar_day_lag"], 4)
        rejected = detail_for(source, "2015-04-06T08:01:00+00:00")
        self.assertEqual(rejected["status"], "outside_1_4_day_lag")
        self.assertEqual(rejected["calendar_day_lag"], 5)

    def test_malformed_event_or_settlement_reference_fails_closed(self):
        prior = entry("2015-04-05T08:00:00+00:00", "2015-04-01")
        for event in ("not-an-event", "2015-13-01T08:00:00+00:00"):
            with self.subTest(event=event), self.assertRaises(ValueError):
                detail_for([prior], event)
        with self.assertRaises(ValueError):
            detail_for([
                entry("2015-04-05T08:00:00+00:00", "not-a-date"),
                prior,
            ], "2015-04-05T08:01:00+00:00")

    def test_future_settlement_cannot_retroactively_supply_reference(self):
        result = detail_for([
            entry("2013-01-02T09:00:00+00:00", "2012-12-31")
        ], "2013-01-02T08:59:59+00:00")
        self.assertEqual(result["status"], "no_prior_settlement")

    def test_future_settlement_does_not_replace_last_prior_candidate(self):
        older = entry("2013-01-02T08:00:00+00:00", "2012-12-31")
        later = entry("2013-01-02T09:00:00+00:00", "2013-01-02", "100")
        result = detail_for([older, later], "2013-01-02T08:15:00+00:00")
        self.assertEqual(result["status"], "candidate_1_4_day_lag")
        self.assertEqual(result["calendar_day_lag"], 2)

    def test_incomplete_or_timezone_free_source_clocks_fail_closed(self):
        valid = exact_clock("2015-11-20 07:12:02.615473825+00:00")
        self.assertEqual(valid.year, 2015)
        for value in (
            "2015-11-20", "2015-11-20T07",
            "2015-11-20T07:12", "2015-11-20T07:12:02",
            "2015-11-20T07:12:02.615473825",
            "2015-11-20T07:12:02Zinvalid",
            "2015-11-20T07:12:02+24:00",
            "2015-11-20T07:12:02+00:60",
            "2015-11-20T07:12:02-00:60",
            "2015-11-20T07:12:02+12:99",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exact_clock(value)

    def test_loader_rejects_malformed_complete_reference_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "statistics-2015.csv"
            for ts_ref in (
                "2015-04-01Tbad", "2015-04-01-invalid", "2015-04-01",
            ):
                with self.subTest(ts_ref=ts_ref):
                    path.write_text(
                        "instrument_id,stat_type,ts_ref,ts_event,ts_recv,"
                        "stat_flags,is_final\n"
                        "sample,3," + ts_ref + ",2015-04-02 07:00:00+00:00,"
                        "2015-04-02 07:00:00+00:00,100,\n",
                        encoding="utf-8",
                    )
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    with (
                        patch.object(audit_module, "STAGE", root),
                        patch.dict(audit_module.STATISTICS_SHA256, {2015: digest}),
                        self.assertRaisesRegex(
                            ValueError, "settlement ts_ref"
                        ),
                    ):
                        audit_module.settlement_clock_rows(2015)

    def test_loader_uses_latest_nanosecond_source_clock_in_utc(self):
        cases = (
            ("2015-06-07T09:00:00.123456001Z",
             "2015-06-07T11:00:00.123456999+02:00", "receive"),
            ("2015-06-07T09:00:00.123456999Z",
             "2015-06-07T04:00:00.123456001-05:00", "event"),
            # Wall-clock and lexicographic ordering DISAGREE with UTC.
            ("2015-06-07T12:00:00.123456001+03:00",
             "2015-06-07T04:00:00.123456999-05:00", "receive"),
            ("2015-06-07T04:00:00.123456999-05:00",
             "2015-06-07T12:00:00.123456001+03:00", "event"),
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "statistics-2015.csv"
            for event, received, winner in cases:
                with self.subTest(winner=winner):
                    path.write_text(
                        "instrument_id,stat_type,ts_ref,ts_event,ts_recv,"
                        "stat_flags,is_final\n"
                        f"sample,3,2015-06-06 00:00:00+00:00,{event},{received},0,\n",
                        encoding="utf-8",
                    )
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    with (
                        patch.object(audit_module, "STAGE", root),
                        patch.dict(audit_module.STATISTICS_SHA256, {2015: digest}),
                    ):
                        rows = audit_module.settlement_clock_rows(2015)["sample"]
                    self.assertEqual(
                        rows[0][0], clock_identity(received if winner == "receive"
                                                   else event)
                    )
                    too_early = detail_for(
                        rows, "2015-06-07T09:00:00.123456002Z"
                    )
                    self.assertEqual(too_early["status"], "no_prior_settlement")
                    eligible = detail_for(
                        rows, "2015-06-07T09:00:00.123457000Z"
                    )
                    self.assertEqual(eligible["status"], "candidate_1_4_day_lag")

    def test_snapshot_parsing_is_bound_to_verified_bytes(self):
        original = b"source-test-header\noriginal\n"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "sample.csv"
            path.write_bytes(original)
            digest = hashlib.sha256(original).hexdigest()
            with patch.object(audit_module, "STAGE", root):
                with audit_module.verified_bytes(path, digest) as snapshot:
                    path.write_bytes(b"untrusted-replacement\n")
                    self.assertEqual(snapshot.read(), original)
                with (
                    self.assertRaisesRegex(ValueError, "hash mismatch"),
                    audit_module.verified_bytes(path, digest),
                ):
                    self.fail("changed source unexpectedly accepted")

    def test_historical_signature_guards_fail_closed_under_mutation(self):
        settlement_header = (
            "instrument_id,stat_type,ts_ref,ts_event,ts_recv,"
            "stat_flags,is_final\n"
        )
        undated_header = (
            "source_year,instrument_id,stat_type,ts_ref,ts_event,ts_recv\n"
        )

        def replay(change):
            b_day = "2010-12-16" if change == "month" else "2010-11-16"
            b_ref = "2010-11-10" if change == "lag" else b_day
            flag = "101" if change == "flag" else "100"
            settlements = settlement_header + (
                "A,3,2010-11-14 00:00:00+00:00,"
                "2010-11-16T08:00:00Z,2010-11-16T08:00:00Z,0,\n"
                "A,3,2010-11-15 00:00:00+00:00,"
                f"2010-11-16T08:00:00Z,2010-11-16T08:00:00Z,{flag},\n"
                f"B,3,{b_ref} 00:00:00+00:00,"
                f"{b_day}T08:00:00Z,{b_day}T08:00:00Z,0,\n"
            )
            undated = undated_header + (
                "2010,A,6,,2010-11-16T09:00:00Z,"
                "2010-11-16T09:00:00Z\n"
            )
            if change != "count":
                undated += (
                    f"2010,B,9,,{b_day}T09:00:00Z,"
                    f"{b_day}T09:00:00Z\n"
                )
            @contextmanager
            def controlled(path, _expected_digest):
                if path.name.startswith("statistics-"):
                    text = settlements if path.name == "statistics-2010.csv" else settlement_header
                    payload = text.encode("utf-8")
                else:
                    text = undated if path.name == "undefined-ref-2010.csv.gz" else undated_header
                    payload = gzip.compress(text.encode("utf-8"))
                with io.BytesIO(payload) as stream:
                    yield stream

            with (
                patch.object(audit_module, "verified_bytes", controlled),
                patch.object(audit_module, "EXPECTED_AMBIGUOUS", 1),
                patch.object(audit_module, "EXPECTED_OUTSIDE", 1),
            ):
                return audit_module.inspect()

        self.assertEqual(
            replay("baseline")["exception_records"],
            {"same_clock": 1, "outside_lag": 1},
        )
        for change, diagnostic in (
            ("count", "denominator drift"),
            ("flag", "flag signature drift"),
            ("lag", "zero-day signature drift"),
            ("month", "publication month signature drift"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                ValueError, diagnostic
            ):
                replay(change)

    def test_aggregate_receipt_never_publishes_reference_days(self):
        receipt = json.loads(
            Path(__file__).with_name("exception-conflict-detail-receipt.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(set(receipt), {
            "schema_version", "issue", "status", "exception_records",
            "by_source_year", "by_statistic_type",
            "same_clock_shape_year_dates_versions", "same_clock_flags",
            "same_clock_finality", "outside_calendar_lags",
            "independent_contract_date_confirmation",
            "publication_clocks_are_not_verified_original_exchange_reference_dates",
            "historical_dates_promoted", "protected_confirmation_accessed",
        })
        self.assertEqual(set(receipt["by_source_year"]), {
            str(year) for year in range(2010, 2016)
        })
        for summary in receipt["by_source_year"].values():
            self.assertEqual(set(summary), {
                "ambiguous_same_clock_settlement", "outside_1_4_day_lag",
                "exception_cohort_sha256",
            })
            for digest in summary["exception_cohort_sha256"].values():
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["historical_dates_promoted"], 0)
        self.assertFalse(receipt["independent_contract_date_confirmation"])
        self.assertEqual(receipt["exception_records"], {
            "same_clock": 1870, "outside_lag": 190,
        })
        self.assertEqual(receipt["outside_calendar_lags"], {"0": 190})
        self.assertEqual(receipt["same_clock_flags"], [
            {"flags": ["0", "100"], "records": 1870},
        ])
        self.assertFalse(receipt["protected_confirmation_accessed"])
        self.assertTrue(
            receipt["publication_clocks_are_not_verified_original_exchange_reference_dates"]
        )
        self.assertEqual(receipt, inspect())  # Replay every pinned cohort and hash.
        date_pattern = r"\b20[0-9]{2}-[0-9]{2}-[0-9]{2}\b"
        self.assertIsNotNone(re.search(date_pattern, "forbidden: 2010-11-16"))
        encoded = json.dumps(receipt, sort_keys=True)
        self.assertIsNone(re.search(date_pattern, encoded))
        month_pattern = r"\b20[0-9]{2}-(?:0[1-9]|1[0-2])\b"
        self.assertIsNotNone(re.search(month_pattern, "private 2010-11"))
        self.assertIsNone(re.search(month_pattern, encoded))


if __name__ == "__main__":
    unittest.main()
