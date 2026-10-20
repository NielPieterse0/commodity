"""Source-free calendar comparator regressions for the #482 one-off audit."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import audit_last_trade_metadata as source


class CalendarComparatorTests(unittest.TestCase):
    def test_third_prior_weekday_without_holiday_inference(self):
        self.assertEqual(source.third_prior_weekday(date(2022, 8, 1)), date(2022, 7, 27))
        self.assertEqual(source.third_prior_weekday(date(2023, 1, 1)), date(2022, 12, 28))

    def test_exact_month_identity_and_eastern_local_clock(self):
        report = source.analyze_contract_expirations([
            ("NYMEX", "NGQ2", "2022-07-27T18:30:00+00:00"),
            ("NYMEX", "NGF3", "2022-12-28T19:30:00+00:00"),
        ])
        self.assertEqual(report["counts"]["distinct_contracts"], 2)
        self.assertEqual(report["counts"]["adjacent_symbol_delivery_month"], 2)
        self.assertEqual(report["counts"]["third_prior_weekday_exact_match"], 2)
        self.assertEqual(report["counts"]["local_1430_expiration"], 2)
        self.assertEqual(report["counts"]["EDT"], 1)
        self.assertEqual(report["counts"]["EST"], 1)
        self.assertEqual(report["counts"]["symbol_year_suffix_matches_delivery_year"], 2)
        self.assertFalse(report["regulatory_exchange_calendar_independently_verified"])
    def test_holiday_proxy_difference_never_implies_exchange_error(self):
        report = source.analyze_contract_expirations([
            ("NYMEX", "NGM2", "2022-05-26T18:30:00Z"),
        ])
        self.assertEqual(report["counts"]["weekday_only_comparator_mismatch"], 1)
        self.assertEqual(report["weekday_comparator_deviation_days"], {"-1": 1})
        self.assertFalse(report["weekday_model_is_official_CME_holiday_calendar"])

    def test_clock_and_year_suffix_outliers_are_explicit(self):
        report = source.analyze_contract_expirations([
            ("NYMEX", "NGQ2", "2022-07-27T17:30:00+00:00"),
            ("NYMEX", "NGQ3", "2022-07-27T18:30:00+00:00"),
            ("NYMEX", "NG-BAD", "2022-07-27T18:30:00+00:00"),
        ])
        self.assertEqual(report["counts"]["non_1430_local_expiration"], 1)
        self.assertEqual(
            report["development_expiration_cohorts"]["expired_before_2023"]
            ["non_1430_local_expiration"], 1,
        )
        self.assertEqual(
            report["development_expiration_cohorts"]["future_listed_expiration_2023_plus"]
            .get("non_1430_local_expiration", 0), 0,
        )
        self.assertEqual(report["unusual_local_clock_values"], {"13:30:00": 1})
        self.assertEqual(report["counts"]["symbol_year_suffix_mismatch"], 1)
        self.assertEqual(report["counts"]["unparseable_NG_symbol"], 1)

    def test_reject_timezone_naive_source_clock(self):
        with self.assertRaisesRegex(RuntimeError, "lacks timezone"):
            source.analyze_contract_expirations([
                ("NYMEX", "NGQ2", "2022-07-27T18:30:00"),
            ])

    def test_empty_contract_set_not_a_pass(self):
        with self.assertRaisesRegex(RuntimeError, "no pinned futures"):
            source.analyze_contract_expirations([])


def pinned_fixture():
    calendar = {
        "counts": dict(source.EXPECTED_CONTRACT_COUNTS),
        "weekday_comparator_mismatch_by_expiration_year":
            dict(source.EXPECTED_YEAR_MISMATCHES),
        "weekday_comparator_deviation_days": {"-1": 22, "-2": 1, "-3": 4},
        "unusual_local_clock_values": {"13:30:00": 1},
        "unusual_local_clock_years": {"2021": 1},
        "development_expiration_cohorts": {
            name: dict(counters)
            for name, counters in source.EXPECTED_EXPIRATION_COHORTS.items()
        },
        "weekday_model_is_official_CME_holiday_calendar": False,
        "regulatory_exchange_calendar_independently_verified": False,
    }
    years = [
        {"available_year": year, "rows": rows, "explicit_last_trade": 0,
         "distinct_instrument_ids": source.EXPECTED_YEAR_INSTRUMENT_IDS[year]}
        for year, rows in source.EXPECTED_YEAR_ROWS.items()
    ]
    clocks = [
        {"utc_clock": "18:30:00", "definition_versions": 352720, "distinct_contracts": 206},
        {"utc_clock": "19:30:00", "definition_versions": 173090, "distinct_contracts": 101},
    ]
    return dict(source.EXPECTED_DEFINITION_TOTALS), calendar, years, clocks


class PinnedMetadataRegressionTests(unittest.TestCase):
    def test_exact_pinned_coverage_passes(self):
        source.verify_expected_coverage(*pinned_fixture())

    def test_changed_definition_metadata_fails_closed(self):
        args = pinned_fixture()
        args[0]["missing_last_trade_at"] -= 1
        with self.assertRaisesRegex(RuntimeError, "definition metadata"):
            source.verify_expected_coverage(*args)

    def test_unexpected_contract_anomaly_fails_closed(self):
        args = pinned_fixture()
        args[1]["counts"]["weekend_expiration"] = 1
        with self.assertRaisesRegex(RuntimeError, "contract anomaly"):
            source.verify_expected_coverage(*args)

    def test_reclassified_calendar_offset_fails_closed(self):
        args = pinned_fixture()
        args[1]["weekday_comparator_deviation_days"]["-1"] -= 1
        args[1]["weekday_comparator_deviation_days"]["-2"] += 1
        with self.assertRaisesRegex(RuntimeError, "expiration anomalies"):
            source.verify_expected_coverage(*args)

    def test_expiration_cohort_reclassification_fails_with_same_total(self):
        args = pinned_fixture()
        cohorts = args[1]["development_expiration_cohorts"]
        cohorts["expired_before_2023"]["contracts"] -= 1
        cohorts["future_listed_expiration_2023_plus"]["contracts"] += 1
        with self.assertRaisesRegex(RuntimeError, "forward-listed contract cohorts"):
            source.verify_expected_coverage(*args)

    def test_calendar_cohorts_never_count_future_listed_as_historical(self):
        report = source.analyze_contract_expirations([
            ("NYMEX", "NGZ2", "2022-11-28T19:30:00+00:00"),
            ("NYMEX", "NGF3", "2022-12-28T19:30:00+00:00"),
            ("NYMEX", "NGF24", "2023-12-27T19:30:00+00:00"),
        ])
        cohorts = report["development_expiration_cohorts"]
        self.assertEqual(cohorts["expired_before_2023"]["contracts"], 2)
        self.assertEqual(cohorts["future_listed_expiration_2023_plus"]["contracts"], 1)
        self.assertFalse(report["regulatory_exchange_calendar_independently_verified"])

    def test_2023_cutoff_uses_eastern_local_day_not_utc_day(self):
        report = source.analyze_contract_expirations([
            ("NYMEX", "NGF23", "2023-01-01T00:30:00+00:00"),
            ("NYMEX", "NGF23", "2023-01-01T05:30:00+00:00"),
        ])
        cohorts = report["development_expiration_cohorts"]
        self.assertEqual(cohorts["expired_before_2023"]["contracts"], 1)
        self.assertEqual(cohorts["future_listed_expiration_2023_plus"]["contracts"], 1)

    def test_2020_leap_and_2021_dst_local_expiration_scope(self):
        report = source.analyze_contract_expirations([
            ("NYMEX", "NGH20", "2020-02-25T19:30:00+00:00"),
            ("NYMEX", "NGJ21", "2021-03-29T18:30:00+00:00"),
        ])
        self.assertEqual(
            report["development_expiration_cohorts"]["expired_before_2023"]["contracts"], 2,
        )
        self.assertEqual(report["counts"]["EST"], 1)
        self.assertEqual(report["counts"]["EDT"], 1)

    def test_receipt_digest_matches_closeout_pointer(self):
        base = Path(__file__).resolve().parent
        receipt = json.loads((base / "calendar-last-trade-audit-receipt.json").read_text())
        documented = (base / "closeout.md").read_text(encoding="utf-8")
        self.assertIn(receipt["canonical_sorted_compact_json_report_sha256"], documented)

    def test_changed_annual_distribution_fails_even_if_total_unchanged(self):
        args = pinned_fixture()
        args[2][0]["rows"] += 1
        args[2][1]["rows"] -= 1
        with self.assertRaisesRegex(RuntimeError, "annual definition coverage"):
            source.verify_expected_coverage(*args)

    def test_missing_year_and_duplicate_year_fail_closed(self):
        args = pinned_fixture()
        args[2][0] = dict(args[2][1])
        with self.assertRaisesRegex(RuntimeError, "annual definition coverage"):
            source.verify_expected_coverage(*args)

    def test_changed_expiry_clock_distribution_fails_closed(self):
        args = pinned_fixture()
        args[3][0]["definition_versions"] -= 1
        args[3][1]["definition_versions"] += 1
        with self.assertRaisesRegex(RuntimeError, "expiration clock distribution"):
            source.verify_expected_coverage(*args)

    def test_cannot_reclassify_weekday_comparator_as_official(self):
        args = pinned_fixture()
        args[1]["regulatory_exchange_calendar_independently_verified"] = True
        with self.assertRaisesRegex(RuntimeError, "expiration anomalies"):
            source.verify_expected_coverage(*args)

    def test_modified_original_does_not_change_verified_snapshot(self):
        with tempfile.TemporaryDirectory(dir=source.DATA) as scratch:
            original = Path(scratch) / "fixture.csv"
            original.write_bytes(b"original pinned data")
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            with (
                patch.object(source, "SOURCE_FILES", {"fixture": (original, digest, 1024)}),
                source.verified_source_snapshots() as snapshots,
            ):
                original.write_bytes(b"later altered original")
                snapshot = snapshots["fixture"]
                self.assertEqual(snapshot.read_bytes(), b"original pinned data")
                self.assertEqual(source.sha(snapshot), digest)

    def test_wrong_pinned_source_digest_rejected(self):
        with tempfile.TemporaryDirectory(dir=source.DATA) as scratch:
            original = Path(scratch) / "fixture.csv"
            original.write_bytes(b"untrusted bytes")
            with (
                patch.object(source, "SOURCE_FILES", {"fixture": (original, "0" * 64, 1024)}),
                self.assertRaisesRegex(RuntimeError, "source bytes changed"),
                source.verified_source_snapshots(),
            ):
                self.fail("mismatched source should never be yielded")

    def test_oversized_source_snapshot_rejected(self):
        with tempfile.TemporaryDirectory(dir=source.DATA) as scratch:
            original = Path(scratch) / "fixture.csv"
            original.write_bytes(b"beyond size limit")
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            with (
                patch.object(source, "SOURCE_FILES", {"fixture": (original, digest, 2)}),
                self.assertRaisesRegex(RuntimeError, "byte budget"),
                source.verified_source_snapshots(),
            ):
                self.fail("oversized source should never be yielded")


    def test_missing_source_file_rejected(self):
        with tempfile.TemporaryDirectory(dir=source.DATA) as scratch:
            missing = Path(scratch) / "absent.csv"
            with (
                patch.object(source, "SOURCE_FILES", {"missing": (missing, "0" * 64, 1024)}),
                self.assertRaisesRegex(RuntimeError, "input unavailable"),
                source.verified_source_snapshots(),
            ):
                self.fail("missing source should never be yielded")

    def test_inaccessible_source_file_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=source.DATA) as scratch:
            original = Path(scratch) / "fixture.csv"
            original.write_bytes(b"pinned source")
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            with (
                patch.object(source, "SOURCE_FILES", {"fixture": (original, digest, 1024)}),
                patch.object(Path, "open", side_effect=PermissionError("source access denied")),
                self.assertRaisesRegex(PermissionError, "source access denied"),
                source.verified_source_snapshots(),
            ):
                self.fail("inaccessible source should never be yielded")

    @unittest.skipUnless(
        all(file.is_file() for file, _, _ in source.SOURCE_FILES.values()),
        "pinned local pre-2023 sources are not available in this checkout",
    )
    def test_real_pinned_audit_end_to_end(self):
        report = source.audit()
        self.assertEqual(report["result"], "SOURCE_METADATA_COVERAGE_DIAGNOSTIC_ONLY")
        self.assertEqual(report["definitions"], source.EXPECTED_DEFINITION_TOTALS)
        self.assertEqual(
            report["contract_calendar_coverage"]["counts"], source.EXPECTED_CONTRACT_COUNTS,
        )
        self.assertEqual(len(report["per_available_year"]), 13)
        self.assertEqual(report["official_date_candidates_promoted"], 0)
        self.assertFalse(report["CME_official_last_trade_calendar_independently_verified"])
        self.assertFalse(report["protected_confirmation_accessed"])
        digest = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        receipt = json.loads(
            (Path(__file__).resolve().parent / "calendar-last-trade-audit-receipt.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(digest, receipt["canonical_sorted_compact_json_report_sha256"])

    @unittest.skipUnless(
        all(file.is_file() for file, _, _ in source.SOURCE_FILES.values()),
        "pinned local pre-2023 sources are not available in this checkout",
    )
    def test_valid_parquet_with_wrong_schema_fails_closed(self):
        import duckdb

        with (
            tempfile.TemporaryDirectory(dir=source.DATA) as scratch,
            source.verified_source_snapshots() as snapshots,
        ):
            wrong_schema = Path(scratch) / "invalid-schema.parquet"
            with duckdb.connect(":memory:") as connection:
                connection.execute(
                    f"COPY (SELECT 1 AS wrong_column) TO '{wrong_schema.as_posix()}' "
                    "(FORMAT PARQUET)"
                )
            swapped = dict(snapshots, definitions=wrong_schema)
            with self.assertRaises(duckdb.Error):
                source._audit_verified_snapshots(swapped)

    @unittest.skipUnless(
        all(file.is_file() for file, _, _ in source.SOURCE_FILES.values()),
        "pinned local pre-2023 sources are not available in this checkout",
    )
    def test_corrupted_parquet_fails_in_full_audit_query(self):
        with (
            tempfile.TemporaryDirectory(dir=source.DATA) as scratch,
            source.verified_source_snapshots() as snapshots,
        ):
            corrupt = Path(scratch) / "definitions.parquet"
            corrupt.write_bytes(b"not a parquet table")
            swapped = dict(snapshots, definitions=corrupt)
            import duckdb

            with self.assertRaises(duckdb.Error):
                source._audit_verified_snapshots(swapped)

if __name__ == "__main__":
    unittest.main()
