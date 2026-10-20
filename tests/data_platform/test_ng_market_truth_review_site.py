"""Isolated source-owner review-site contract and HTTP-boundary tests."""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from commodity.market_truth import review_site


class ReviewSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = {
            "source_sha256": "a" * 64,
            "final_sha256": "b" * 64,
            "dataset_content_sha256": "c" * 64,
            "approved": False,
            "research_admitted": False,
        }

    def payload(self, **updates):
        value = {
            "decision": "approve",
            "reviewer": "Project owner",
            "notes": "Reviewed exact identities",
            "dataset_content_sha256": self.meta["dataset_content_sha256"],
            "acknowledge_not_admitted": True,
        }
        value.update(updates)
        return value

    def test_dashboard_uses_owner_approved_local_storage_policy(self):
        html = (review_site.ASSETS / "index.html").read_text(encoding="utf-8")
        self.assertIn("Three remaining release gates", html)
        self.assertEqual(html.count('class="gate"'), 3)
        self.assertIn("Local C: drive storage is accepted", html)
        for withdrawn_requirement in (
            "Immutable research archive", "WORM archive proof",
            "owner/WORM approval", "immutable storage remain pending",
            "independent signing and immutable storage",
        ):
            with self.subTest(withdrawn_requirement=withdrawn_requirement):
                self.assertNotIn(withdrawn_requirement, html)
        self.assertIn("Record unsigned approval intent", html)
        self.assertIn("independent signing and verified source/Parquet identities", html)

    def test_v3_selection_rejects_protected_or_invalid_requested_parameters(self):
        review = object.__new__(review_site.ReviewData)
        for arguments in (
            (2023, "2023-01-03", "23:59", 1, "close"),
            (2022, "2023-01-03", "23:59", 1, "close"),
            (2022, "2022-01-03", "24:00", 1, "close"),
            (2022, "2022-01-03", "23:59", 0, "close"),
            (2022, "2022-01-03", "23:59", 13, "close"),
            (2022, "2022-01-03", "23:59", 1, "secret"),
            (2022, "2022-01-03", "23:59", 1, "close;DROP"),
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                review.v3_series(*arguments)
        with self.assertRaisesRegex(ValueError, "invalid V3"):
            review.v3_series(2022, "2022-12-30", "23:59", 1, "close", window="all")

    def test_v3_diagnostic_uses_real_production_selection_method(self):
        from commodity.market_truth.query import MarketTruthDataset

        self.assertIs(
            review_site._VerifiedDiagnosticCurve._curve_from_parquet,
            MarketTruthDataset._curve_from_parquet,
        )

    def test_v3_curve_source_join_requires_selected_instrument_and_session(self):
        import contextlib

        import duckdb

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "bars.csv"
            source.write_text(
                "instrument_id,trade_date,close\n"
                "123,2022-01-03,3.5\n"
                "456,2022-01-04,3.8\n"
                "999,2022-01-04,90.0\n",
                encoding="utf-8",
            )
            bars = root / "bars.parquet"
            with duckdb.connect(":memory:") as db:
                db.execute(
                    "COPY (SELECT * FROM (VALUES "
                    "('123','2022-01-03','2022-01-03T12:00:00+00:00'),"
                    "('456','2022-01-04','2022-01-04T12:00:00+00:00')) "
                    "AS t(instrument_id,trade_date,available_at)) "
                    f"TO '{bars.as_posix()}' (FORMAT PARQUET)"
                )
            calls = []

            def selected(self, db, session, cutoff, ranks):
                calls.append((str(session), cutoff.isoformat(), ranks))
                instrument, value = (
                    ("123", 3.5) if session.isoformat() == "2022-01-03"
                    else ("456", 4.0)
                )
                point = {
                    "instrument_id": instrument,
                    "close": value,
                    "contract_identity": instrument,
                    "contract_symbol": "NG" + instrument,
                    "rank_boundary_status": "expiry_fallback_unverified",
                    "available_at": cutoff.isoformat(),
                    "evidence_ids": ["synthetic-" + instrument],
                }
                return [point] * ranks

            with (
                patch.object(review_site, "pinned_metadata", return_value=self.meta),
                patch.object(review_site, "SOURCE_CSV", source),
                patch.object(review_site, "FINAL_BARS", bars),
                patch.object(review_site, "FINAL", root),
                patch.object(
                    review_site, "protected_table_reads",
                    side_effect=lambda paths: contextlib.nullcontext(),
                ),
                patch.object(
                    review_site._VerifiedDiagnosticCurve,
                    "_curve_from_parquet", new=selected,
                ),
            ):
                reader = review_site.ReviewData()
                try:
                    result = reader.v3_series(2022, "2022-01-04", "18:30", 1, "close")
                    full_year = reader.v3_series(
                        2022, "2022-01-04", "18:30", 1, "close", window="year",
                    )
                finally:
                    reader.db.close()
            self.assertEqual([p["instrument_id"] for p in result["points"]], ["123", "456"])
            self.assertEqual(result["points"][0]["delta"], 0.0)
            self.assertAlmostEqual(result["points"][1]["delta"], 0.2)
            self.assertEqual([p["roll_transition"] for p in result["points"]], [False, True])
            self.assertEqual(result["summary"]["roll_transitions"], 1)
            self.assertEqual(result["summary"]["unverified_expiry_boundaries"], 2)
            self.assertEqual(result["summary"]["different"], 1)
            self.assertEqual(result["selection"], "production_V3_curve_selector_preapproval_diagnostic")
            self.assertFalse(result["research_admitted"])
            self.assertEqual(full_year["window"], "year")
            self.assertEqual(full_year["points"], result["points"])
            self.assertEqual(len(calls), 4)
            self.assertTrue(all(cutoff.endswith("18:30:00+00:00") for _, cutoff, _ in calls))

    def test_actual_v3_parquet_selector_obeys_rank_and_revision_cutoffs(self):
        """Exercise unpatched production V3 selection with fixture-only Parquet."""
        import contextlib

        import duckdb

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "bars.csv"
            source.write_text(
                "instrument_id,trade_date,close\n"
                "111,2022-01-03,3.5\n"
                "222,2022-01-03,4.6\n",
                encoding="utf-8",
            )
            definitions = [
                {
                    "instrument_id": instrument, "venue": "GLBX",
                    "symbol": symbol, "expiration": expiration,
                    "last_trade_at": last_trade, "available_at": "2022-01-02T00:00:00+00:00",
                    "evidence_id": "definition-" + instrument,
                }
                for instrument, symbol, expiration, last_trade in (
                    ("111", "NGG22", "2022-02-01T00:00:00+00:00",
                     "2022-01-03T18:00:00+00:00"),
                    ("222", "NGH22", "2022-03-01T00:00:00+00:00",
                     "2022-02-25T00:00:00+00:00"),
                )
            ]
            bars = [
                {
                    "instrument_id": instrument, "trade_date": "2022-01-03",
                    "available_at": clock, "evidence_id": evidence,
                    "open": close, "high": close, "low": close,
                    "close": close, "volume": 10,
                }
                for instrument, clock, evidence, close in (
                    ("111", "2022-01-03T15:30:00+00:00", "bar-111", 3.5),
                    ("222", "2022-01-03T17:30:00+00:00", "bar-222", 4.6),
                    ("222", "2022-01-03T20:00:00+00:00", "bar-222-late", 8.8),
                )
            ]
            statistics = [
                {
                    "instrument_id": instrument, "trade_date": "2022-01-03",
                    "stat_type": "settle", "available_at": clock,
                    "evidence_id": "stat-" + instrument, "value": close,
                }
                for instrument, clock, close in (
                    ("111", "2022-01-03T15:30:00+00:00", 3.5),
                    ("222", "2022-01-03T17:30:00+00:00", 4.6),
                )
            ]
            with duckdb.connect(":memory:") as db:
                for family, rows in (
                    ("definitions", definitions), ("bars", bars),
                    ("statistics", statistics),
                ):
                    document = root / f"{family}.json"
                    document.write_text(
                        "\n".join(json.dumps(row) for row in rows),
                        encoding="utf-8",
                    )
                    clocks = ["available_at"]
                    if family == "definitions":
                        clocks.extend(("expiration", "last_trade_at"))
                    # Production Parquet encodes exact offset-aware source clocks.
                    # DuckDB's JSON inference otherwise produces naive datetimes.
                    fields = ["CAST(instrument_id AS VARCHAR) AS instrument_id"]
                    if family != "definitions":
                        fields.append("CAST(trade_date AS VARCHAR) AS trade_date")
                    fields.extend(
                        f"strftime(CAST({column} AS TIMESTAMP), "
                        f"'%Y-%m-%dT%H:%M:%S+00:00') AS {column}"
                        for column in clocks
                    )
                    replacements = ", ".join(fields)
                    db.execute(
                        f"COPY (SELECT * REPLACE({replacements}) FROM read_json_auto(?)) "
                        f"TO '{(root / (family + '.parquet')).as_posix()}' "
                        "(FORMAT PARQUET)",
                        [str(document)],
                    )
            with (
                patch.object(review_site, "pinned_metadata", return_value=self.meta),
                patch.object(review_site, "SOURCE_CSV", source),
                patch.object(review_site, "FINAL_BARS", root / "bars.parquet"),
                patch.object(review_site, "FINAL", root),
                # Fixture files are synthetic and ephemeral; production still
                # requires protected_table_reads and pinned_metadata.
                patch.object(
                    review_site, "protected_table_reads",
                    side_effect=lambda paths: contextlib.nullcontext(),
                ),
            ):
                reader = review_site.ReviewData()
                try:
                    early = reader.v3_series(2022, "2022-01-03", "16:00", 1, "close")
                    second_rank = reader.v3_series(2022, "2022-01-03", "16:00", 2, "close")
                    later = reader.v3_series(2022, "2022-01-03", "19:00", 1, "close")
                    revised = reader.v3_series(2022, "2022-01-03", "21:00", 1, "close")
                finally:
                    reader.db.close()
            self.assertEqual(early["points"][0]["instrument_id"], "111")
            self.assertEqual(second_rank["points"][0]["instrument_id"], "222")
            self.assertIsNone(second_rank["points"][0]["final"])
            self.assertEqual(later["points"][0]["instrument_id"], "222")
            self.assertEqual(revised["points"][0]["instrument_id"], "222")
            self.assertEqual(early["points"][0]["final"], 3.5)
            self.assertEqual(later["points"][0]["final"], 4.6)
            self.assertEqual(revised["points"][0]["final"], 8.8)
            self.assertAlmostEqual(revised["points"][0]["delta"], 4.2)
            self.assertEqual(later["points"][0]["source"], 4.6)
            self.assertFalse(later["research_admitted"])

    def test_v3_preserves_null_row_presence_and_does_not_invent_rolls(self):
        import contextlib

        import duckdb

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv = root / "source.csv"
            csv.write_text(
                "instrument_id,trade_date,close\n"
                "111,2022-01-03,\n"
                "111,2022-01-04,\n"
                "111,2022-01-05,3.5\n"
                "222,2022-01-08,5.0\n",
                encoding="utf-8",
            )
            path = root / "bars.parquet"
            with duckdb.connect(":memory:") as db:
                db.execute(
                    "COPY (SELECT * FROM (VALUES "
                    "('111','2022-01-03',2.2),"
                    "('111','2022-01-04',NULL),"
                    "('999','2022-01-05',9.0),"
                    "('111','2022-01-06',4.0),"
                    "('999','2022-01-07',9.0),"
                    "('222','2022-01-08',5.0)) "
                    "AS t(instrument_id,trade_date,close) "
                    "CROSS JOIN (SELECT "
                    "'2022-01-01T00:00:00+00:00' AS available_at)) "
                    f"TO '{path.as_posix()}' (FORMAT PARQUET)"
                )

            def selected(self, connection, session, cutoff, ranks):
                day = session.isoformat()
                instrument = (
                    None if day == "2022-01-07"
                    else "222" if day == "2022-01-08"
                    else "111"
                )
                values = {
                    "2022-01-03": 2.2,
                    "2022-01-04": None,
                    "2022-01-05": None,
                    "2022-01-06": 4.0,
                    "2022-01-07": None,
                    "2022-01-08": 5.0,
                }
                entry = {
                    "instrument_id": instrument,
                    "close": values[day],
                    "contract_identity": instrument,
                    "contract_symbol": instrument,
                    "rank_boundary_status": (
                        "not_listed" if instrument is None
                        else "expiry_fallback_unverified"
                    ),
                    "available_at": cutoff.isoformat(),
                    "evidence_ids": [],
                }
                return [entry] * ranks

            with (
                patch.object(review_site, "pinned_metadata", return_value=self.meta),
                patch.object(review_site, "SOURCE_CSV", csv),
                patch.object(review_site, "FINAL", root),
                patch.object(review_site, "FINAL_BARS", path),
                patch.object(review_site, "protected_table_reads",
                             side_effect=lambda files: contextlib.nullcontext()),
                patch.object(review_site._VerifiedDiagnosticCurve,
                             "_curve_from_parquet", new=selected),
            ):
                reader = review_site.ReviewData()
                try:
                    result = reader.v3_series(2022, "2022-01-08", "23:59", 1, "close")
                finally:
                    reader.db.close()
            self.assertEqual(
                [point["status"] for point in result["points"]],
                ["null_mismatch", "both_null", "source_only",
                 "final_only", "not_listed", "equal"],
            )
            self.assertEqual(
                [point["source_present"] for point in result["points"]],
                [True, True, True, False, False, True],
            )
            self.assertEqual(result["summary"]["different"], 1)
            self.assertEqual(result["summary"]["both_null"], 1)
            self.assertEqual(result["summary"]["missing_final"], 1)
            self.assertEqual(result["summary"]["extra_final"], 1)
            self.assertEqual(result["summary"]["roll_transitions"], 0)

    def test_v3_session_membership_excludes_later_only_bars(self):
        import contextlib

        import duckdb

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with duckdb.connect(":memory:") as db:
                db.execute(
                    "COPY (SELECT * FROM (VALUES "
                    "('111','2022-01-03','2022-01-03T14:00:00+00:00'),"
                    "('111','2022-01-04','2022-01-04T23:00:00+00:00')) "
                    "AS t(instrument_id,trade_date,available_at)) "
                    f"TO '{(root / 'bars.parquet').as_posix()}' (FORMAT PARQUET)"
                )
            source = root / "bars.csv"
            source.write_text("instrument_id,trade_date,close\n111,2022-01-03,3.5\n", encoding="utf-8")

            def selected(self, conn, day, cutoff, ranks):
                return [{
                    "instrument_id": "111", "close": 3.5,
                    "contract_identity": "GLBX:NG111", "contract_symbol": "NG111",
                    "rank_boundary_status": "expiry_fallback_unverified",
                    "available_at": cutoff.isoformat(), "evidence_ids": [],
                }] * ranks

            with (
                patch.object(review_site, "pinned_metadata", return_value=self.meta),
                patch.object(review_site, "SOURCE_CSV", source),
                patch.object(review_site, "FINAL_BARS", root / "bars.parquet"),
                patch.object(review_site, "FINAL", root),
                patch.object(review_site, "protected_table_reads",
                             side_effect=lambda paths: contextlib.nullcontext()),
                patch.object(review_site._VerifiedDiagnosticCurve,
                             "_curve_from_parquet", new=selected),
            ):
                reader = review_site.ReviewData()
                try:
                    report = reader.v3_series(2022, "2022-01-04", "16:00", 1, "close")
                finally:
                    reader.db.close()
            self.assertEqual([p["date"] for p in report["points"]], ["2022-01-03"])
            self.assertEqual(report["summary"]["matched"], 1)

    def test_v3_review_records_fenced_cme_session_without_failing_chart(self):
        """Terminal-window model rejection stays fail-closed and chart-visible."""
        import contextlib

        import duckdb

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv = root / "bars.csv"
            csv.write_text(
                "instrument_id,trade_date,close\n"
                "111,2022-05-10,3.5\n"
                "111,2022-05-26,4.1\n",
                encoding="utf-8",
            )
            bars = root / "bars.parquet"
            with duckdb.connect(":memory:") as db:
                db.execute(
                    "COPY (SELECT * FROM (VALUES "
                    "('111','2022-05-10','2022-05-10T18:00:00+00:00'),"
                    "('111','2022-05-26','2022-05-26T18:00:00+00:00')) "
                    "AS t(instrument_id,trade_date,available_at)) "
                    f"TO '{bars.as_posix()}' (FORMAT PARQUET)"
                )

            def selected(self, db, session, cutoff, ranks):
                if session.isoformat() == "2022-05-26":
                    raise review_site.MarketTruthError(
                        "unverified CME historical expiry decision window; "
                        "no market-truth curve selection permitted"
                    )
                entry = {
                    "instrument_id": "111", "close": 3.5,
                    "contract_identity": "NYMEX:NGN2", "contract_symbol": "NGN2",
                    "rank_boundary_status": "expiry_fallback_unverified",
                    "available_at": cutoff.isoformat(), "evidence_ids": ["e111"],
                }
                return [entry.copy() for _ in range(ranks)]

            with (
                patch.object(review_site, "pinned_metadata", return_value=self.meta),
                patch.object(review_site, "SOURCE_CSV", csv),
                patch.object(review_site, "FINAL_BARS", bars),
                patch.object(review_site, "FINAL", root),
                patch.object(
                    review_site, "protected_table_reads",
                    side_effect=lambda files: contextlib.nullcontext(),
                ),
                patch.object(
                    review_site._VerifiedDiagnosticCurve,
                    "_curve_from_parquet", new=selected,
                ),
            ):
                review = review_site.ReviewData()
                try:
                    result = review.v3_series(2022, "2022-05-26", "23:59", 1, "close")
                finally:
                    review.db.close()

            self.assertEqual(
                [p["status"] for p in result["points"]],
                ["equal", "excluded_unverified_expiry_window"],
            )
            blocked = result["points"][1]
            self.assertIsNone(blocked["instrument_id"])
            self.assertIsNone(blocked["source"])
            self.assertIsNone(blocked["final"])
            self.assertIsNone(blocked["delta"])
            self.assertIsNone(blocked["roll_transition"])
            self.assertEqual(result["summary"]["excluded_unverified_expiry_window"], 1)
            self.assertEqual(result["summary"]["matched"], 1)
            self.assertEqual(result["summary"]["roll_transitions"], 0)
            self.assertFalse(result["research_admitted"])

    def test_v3_owner_chart_marks_cme_rank_exclusion_not_false_match(self):
        """Owner evidence must use the exact model-safe rank policy, not raw SQL."""
        import contextlib

        import duckdb

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv = root / "bars.csv"
            csv.write_text(
                "instrument_id,trade_date,close\n"
                "111,2022-05-10,3.5\n"
                "222,2022-05-10,4.0\n",
                encoding="utf-8",
            )
            bars = root / "bars.parquet"
            with duckdb.connect(":memory:") as db:
                db.execute(
                    "COPY (SELECT * FROM (VALUES "
                    "('111','2022-05-10','2022-05-10T18:00:00+00:00'),"
                    "('222','2022-05-10','2022-05-10T18:00:00+00:00')) "
                    "AS t(instrument_id,trade_date,available_at)) "
                    f"TO '{bars.as_posix()}' (FORMAT PARQUET)"
                )

            def selected(self, db, session, cutoff, ranks):
                rows = [
                    {
                        "instrument_id": instrument,
                        "close": value, "contract_identity": instrument,
                        "contract_symbol": instrument,
                        "rank_boundary_status": (
                            "verified_last_trade" if index == 0
                            else "unverified_exchange_expiry"
                            if index == 1 else "expiry_fallback_unverified"
                        ),
                        "available_at": cutoff.isoformat(),
                        "evidence_ids": ["synthetic-" + instrument],
                    }
                    for index, (instrument, value) in enumerate(
                        [("111", 3.5), ("222", 4.0)]
                        + [(f"X{i}", 5.0) for i in range(3, 13)]
                    )
                ]
                return rows[:ranks]

            with (
                patch.object(review_site, "pinned_metadata", return_value=self.meta),
                patch.object(review_site, "SOURCE_CSV", csv),
                patch.object(review_site, "FINAL_BARS", bars),
                patch.object(review_site, "FINAL", root),
                patch.object(
                    review_site, "protected_table_reads",
                    side_effect=lambda files: contextlib.nullcontext(),
                ),
                patch.object(
                    review_site._VerifiedDiagnosticCurve,
                    "_curve_from_parquet", new=selected,
                ),
            ):
                review = review_site.ReviewData()
                try:
                    safe = review.v3_series(2022, "2022-05-10", "23:59", 1, "close")
                    excluded = review.v3_series(2022, "2022-05-10", "23:59", 2, "close")
                finally:
                    review.db.close()

            self.assertEqual(safe["points"][0]["status"], "equal")
            self.assertEqual(safe["points"][0]["final"], 3.5)
            self.assertEqual(safe["summary"]["matched"], 1)
            hidden = excluded["points"][0]
            self.assertEqual(hidden["status"], "excluded_unverified_expiry_rank")
            self.assertIsNone(hidden["instrument_id"])
            self.assertIsNone(hidden["contract_identity"])
            self.assertIsNone(hidden["final"])
            self.assertIsNone(hidden["source"])
            self.assertEqual(hidden["evidence_ids"], [])
            self.assertEqual(excluded["summary"]["excluded_unverified_expiry_rank"], 1)
            self.assertEqual(excluded["summary"]["unverified_expiry_boundaries"], 1)
            self.assertEqual(excluded["summary"]["matched"], 0)
            self.assertFalse(excluded["research_admitted"])

    def test_v3_endpoint_is_read_only_and_blocks_protected_years(self):
        class StubReview:
            def __init__(self, meta):
                self.meta = meta
                self.requests = []

            def v3_series(self, year, day, clock, rank, metric, window="20"):
                self.requests.append((year, day, clock, rank, metric))
                return {"selection": "diagnostic", "research_admitted": False, "points": []}

        instance = StubReview(self.meta)
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), review_site.make_handler(instance, "fixture-token"),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            url = (
                base + "/api/v3-series?year=2022&end_day=2022-12-30"
                "&clock=18%3A30&rank=2&metric=close"
            )
            response = json.loads(urlopen(url, timeout=8).read())
            self.assertFalse(response["research_admitted"])
            self.assertEqual(
                instance.requests, [(2022, "2022-12-30", "18:30", 2, "close")]
            )
            for query in (
                "year=2023&end_day=2023-01-03&rank=1",
                "year=2022&end_day=2022-12-30&rank=untrusted",
            ):
                with self.subTest(query=query), self.assertRaises(HTTPError) as caught:
                    urlopen(base + "/api/v3-series?" + query, timeout=8)
                self.assertEqual(caught.exception.code, 422)
            self.assertEqual(len(instance.requests), 1)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_pinned_full_history_v3_receipt_rejects_tampering_and_missing_slots(self):
        statuses = review_site.V3_AUDIT_STATUSES
        fields = ("open", "high", "low", "close", "volume")
        groups = []
        for year in range(2010, 2023):
            for rank in range(1, 13):
                for metric in fields:
                    bucket = {key: 0 for key in (*statuses, "exact", "different")}
                    bucket["numeric_pairs"] = 3
                    bucket["exact"] = 3
                    groups.append({"year": year, "rank": rank, "metric": metric,
                                   **bucket})
        totals = {key: sum(group[key] for group in groups)
                  for key in (*statuses, "exact", "different")}
        report = {
            "schema_version": 1, "issue": 482,
            "status": "full_history_v3_selected_preapproval_diagnostic",
            "dataset_content_sha256": self.meta["dataset_content_sha256"],
            "original_sha256": self.meta["source_sha256"],
            "final_sha256": self.meta["final_sha256"],
            "decision_clock_utc": "23:59",
            "research_admitted": False, "signed_owner_approval": False,
            "source_pit_qualified": False, "protected_2023plus_accessed": False,
            "scanned_sessions": 39, "year_rank_field_groups": 780,
            "totals": totals, "by_year_rank_field": groups,
        }
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "receipt.json"

            def write_and_pin():
                receipt.write_text(json.dumps(report), encoding="utf-8")
                return hashlib.sha256(receipt.read_bytes()).hexdigest()

            with patch.object(review_site, "V3_AUDIT_SHA256", write_and_pin()):
                result = review_site.verify_v3_history_receipt(receipt, self.meta)
                self.assertEqual(result["classified_slots"], 39 * 12 * 5)
                self.assertEqual(result["totals"]["different"], 0)
                self.assertEqual(len(result["by_year"]), 13)
                self.assertFalse(result["owner_signed"])
                receipt.write_text("tampered", encoding="utf-8")
                with self.assertRaisesRegex(
                    review_site.MarketTruthError, "not verified"
                ):
                    review_site.verify_v3_history_receipt(receipt, self.meta)
            report["by_year_rank_field"].pop()
            with (
                patch.object(review_site, "V3_AUDIT_SHA256", write_and_pin()),
                self.assertRaisesRegex(review_site.MarketTruthError, "incomplete"),
            ):
                review_site.verify_v3_history_receipt(receipt, self.meta)
            report["by_year_rank_field"].append(groups[-1])
            report["by_year_rank_field"][0]["different"] = 1
            with (
                patch.object(review_site, "V3_AUDIT_SHA256", write_and_pin()),
                self.assertRaisesRegex(review_site.MarketTruthError, "numeric pair"),
            ):
                review_site.verify_v3_history_receipt(receipt, self.meta)
            report["by_year_rank_field"][0]["different"] = 0
            report["signed_owner_approval"] = True
            with (
                patch.object(review_site, "V3_AUDIT_SHA256", write_and_pin()),
                self.assertRaisesRegex(review_site.MarketTruthError, "identity or boundaries"),
            ):
                review_site.verify_v3_history_receipt(receipt, self.meta)

    def test_full_history_audit_route_is_read_only(self):
        class StubReview:
            def v3_full_history_audit(self):
                return {"status": "verified_pinned_preapproval_diagnostic_only",
                        "research_admitted": False, "classified_slots": 234000}

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), review_site.make_handler(StubReview(), "fixture-token"),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}/api/v3-full-history-audit"
            with urlopen(endpoint, timeout=8) as response:
                data = json.load(response)
            self.assertEqual(data["classified_slots"], 234000)
            self.assertFalse(data["research_admitted"])
            with self.assertRaises(HTTPError) as denied:
                urlopen(Request(endpoint, data=b"{}"), timeout=8)
            self.assertEqual(denied.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_complete_bar_audit_http_route_is_read_only(self):
        class StubReview:
            def bars_audit(self):
                return {"exact": True, "research_admitted": False, "metrics": []}

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), review_site.make_handler(StubReview(), "fixture-token"),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/api/bars-audit", timeout=8) as response:
                data = json.load(response)
            self.assertTrue(data["exact"])
            self.assertFalse(data["research_admitted"])
            with self.assertRaises(HTTPError) as invalid:
                urlopen(Request(base + "/api/bars-audit", data=b"{}"), timeout=8)
            self.assertEqual(invalid.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_year_boundary_blocks_protected_period(self):
        self.assertEqual(review_site.validate_year("2010"), 2010)
        self.assertEqual(review_site.validate_year("2022"), 2022)
        for value in ("2023", "2024", "2009", "x", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                review_site.validate_year(value)

    def test_owner_intent_never_grants_admission(self):
        result = review_site._decision_payload(self.payload(), self.meta)
        self.assertEqual(result["decision"], "approve")
        self.assertFalse(result["signed_admission"])
        self.assertFalse(result["external_storage_required"])
        self.assertFalse(result["research_admitted"])
        self.assertEqual(result["dataset_content_sha256"], "c" * 64)

    def test_source_version_pin_and_explicit_ack_required(self):
        for updates in (
            {"dataset_content_sha256": "d" * 64},
            {"acknowledge_not_admitted": False},
            {"reviewer": " "},
            {"decision": "signed_approval"},
        ):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                review_site._decision_payload(self.payload(**updates), self.meta)

    def test_all_source_families_are_hash_pinned_and_counts_reconciled(self):
        import duckdb

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            final_dir = root / "final"
            final_dir.mkdir()
            names = {
                "bars": "bars-full-2010-2022.csv",
                "definitions": "definitions-full-2010-2022.csv",
                "statistics": "statistics-full-2010-2022-curated.csv",
            }
            original = {"inputs": {}, "evidence_class": "development",
                        "max_trade_date": "2022-12-31",
                        "protected_confirmation_accessed": False}
            imported = {
                "dataset_scope": "development_pre2023",
                "protected_confirmation_accessed": False,
                "tables": {}, "source_sha256": {},
                "source_row_reconciliation": {}, "content_sha256": "c" * 64,
            }
            for family, name in names.items():
                source_file = root / name
                final_file = final_dir / f"{family}.parquet"
                source_file.write_text(
                    "instrument_id\n" + "".join(f"{i}\n" for i in range(10)),
                    encoding="utf-8",
                )
                with duckdb.connect(":memory:") as connection:
                    connection.execute(
                        f"COPY (SELECT n FROM range(8) AS rows(n)) "
                        f"TO '{final_file.as_posix()}' (FORMAT PARQUET)"
                    )
                source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
                output_hash = hashlib.sha256(final_file.read_bytes()).hexdigest()
                original["inputs"][family] = {
                    "relative_path": name, "sha256": source_hash, "row_count": 10,
                }
                imported["tables"][family] = {
                    "relative_path": final_file.name, "sha256": output_hash, "rows": 8,
                }
                imported["source_sha256"][family] = source_hash
                imported["source_row_reconciliation"][family] = {
                    "source_rows": 10, "normalized_rows": 8,
                    "excluded_or_exact_retransmissions": 2,
                }
            source_manifest = root / "source.json"
            final_manifest = final_dir / "manifest.json"
            source_manifest.write_text(json.dumps(original), encoding="utf-8")
            imported["source_manifest_sha256"] = hashlib.sha256(
                source_manifest.read_bytes()
            ).hexdigest()
            final_manifest.write_text(json.dumps(imported), encoding="utf-8")
            with (
                patch.object(review_site, "DATA", root),
                patch.object(review_site, "FINAL", final_dir),
                patch.object(review_site, "SOURCE_MANIFEST", source_manifest),
                patch.object(review_site, "FINAL_MANIFEST", final_manifest),
                patch.object(review_site, "SOURCE_CSV", root / names["bars"]),
                patch.object(review_site, "FINAL_BARS", final_dir / "bars.parquet"),
            ):
                metadata = review_site.pinned_metadata()
                self.assertEqual(set(metadata["families"]), set(names))
                self.assertEqual(
                    metadata["families"]["statistics"]["excluded_or_retransmissions"], 2
                )
                self.assertFalse(metadata["research_admitted"])
                for family, name in names.items():
                    file = root / name
                    before = file.read_bytes()
                    file.write_bytes(b"tampered")
                    try:
                        with self.subTest(family=family), self.assertRaises(
                            review_site.MarketTruthError
                        ):
                            review_site.pinned_metadata()
                    finally:
                        file.write_bytes(before)
                imported["source_row_reconciliation"]["statistics"][
                    "excluded_or_exact_retransmissions"
                ] = 1
                final_manifest.write_text(json.dumps(imported), encoding="utf-8")
                with self.assertRaisesRegex(
                    review_site.MarketTruthError, "statistics source/final"
                ):
                    review_site.pinned_metadata()
                # All declared counts can agree with each other but contradict the
                # file contents; hash checks alone cannot certify physical counts.
                original["inputs"]["statistics"]["row_count"] = 11
                imported["tables"]["statistics"]["rows"] = 9
                imported["source_row_reconciliation"]["statistics"] = {
                    "source_rows": 11, "normalized_rows": 9,
                    "excluded_or_exact_retransmissions": 2,
                }
                source_manifest.write_text(json.dumps(original), encoding="utf-8")
                imported["source_manifest_sha256"] = hashlib.sha256(
                    source_manifest.read_bytes()
                ).hexdigest()
                final_manifest.write_text(json.dumps(imported), encoding="utf-8")
                with self.assertRaisesRegex(
                    review_site.MarketTruthError, "statistics physical row-count"
                ):
                    review_site.pinned_metadata()

    def test_real_inventory_when_private_pre2023_fixtures_available(self):
        if not review_site.SOURCE_MANIFEST.is_file():
            self.skipTest("Private pre-2023 dataset not present in this checkout")
        metadata = review_site.pinned_metadata()
        self.assertEqual(
            {name: data["source_rows"] for name, data in metadata["families"].items()},
            {"bars": 103793, "definitions": 525810, "statistics": 2282697},
        )
        self.assertEqual(metadata["families"]["statistics"]["final_rows"], 1177700)
        self.assertEqual(
            metadata["families"]["statistics"]["excluded_or_retransmissions"], 1104997
        )
        self.assertFalse(metadata["approved"])
        self.assertFalse(metadata["research_admitted"])

    def test_real_duckdb_reconciliation_detects_duplicates_and_gaps(self):
        import duckdb

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            original = directory / "raw.csv"

            def compare(label, csv_rows, final_rows):
                parquet = directory / f"{label}.parquet"
                original.write_text(
                    "instrument_id,trade_date,close\n"
                    + "".join(f"{id},{day},{close}\n" for id, day, close in csv_rows),
                    encoding="utf-8",
                )
                conn = duckdb.connect(":memory:")
                try:
                    conn.execute(
                        "CREATE TABLE imported (instrument_id VARCHAR, trade_date VARCHAR, close DOUBLE)"
                    )
                    conn.executemany("INSERT INTO imported VALUES (?,?,?)", final_rows)
                    conn.execute(
                        f"COPY imported TO '{parquet.as_posix()}' (FORMAT PARQUET)"
                    )
                finally:
                    conn.close()
                with (
                    patch.object(
                        review_site, "pinned_metadata", return_value=self.meta
                    ),
                    patch.object(review_site, "SOURCE_CSV", original),
                    patch.object(review_site, "FINAL_BARS", parquet),
                ):
                    reader = review_site.ReviewData()
                    try:
                        return reader.series(2022, "123", "close")
                    finally:
                        reader.db.close()

            matched = compare(
                "matched",
                [("123", "2022-02-01", 3.5), ("123", "2022-02-02", 3.7)],
                [("123", "2022-02-01", 3.5), ("123", "2022-02-02", 3.7)],
            )
            self.assertEqual(matched["summary"]["matched"], 2)
            self.assertEqual(matched["summary"]["different"], 0)

            changed = compare(
                "changed",
                [("123", "2022-02-01", 3.5)],
                [("123", "2022-02-01", 3.6)],
            )
            self.assertEqual(changed["summary"]["different"], 1)
            self.assertAlmostEqual(changed["points"][0]["delta"], 0.1)

            gaps = compare(
                "gaps",
                [("123", "2022-02-01", 3.5)],
                [("123", "2022-02-02", 3.6)],
            )
            self.assertEqual(gaps["summary"]["matched"], 0)
            self.assertEqual(gaps["summary"]["missing_final"], 1)
            self.assertEqual(gaps["summary"]["extra_final"], 1)

            source_null = compare(
                "source_null",
                [("123", "2022-02-01", "")],
                [("123", "2022-02-01", 3.6)],
            )
            self.assertEqual(source_null["summary"]["matched"], 1)
            self.assertEqual(source_null["summary"]["different"], 1)
            self.assertEqual(source_null["summary"]["null_mismatches"], 1)
            self.assertEqual(source_null["points"][0]["status"], "null_mismatch")

            final_null = compare(
                "final_null",
                [("123", "2022-02-01", 3.5)],
                [("123", "2022-02-01", None)],
            )
            self.assertEqual(final_null["summary"]["different"], 1)
            self.assertEqual(final_null["summary"]["null_mismatches"], 1)

            both_null = compare(
                "both_null",
                [("123", "2022-02-01", "")],
                [("123", "2022-02-01", None)],
            )
            self.assertEqual(both_null["summary"]["matched"], 1)
            self.assertEqual(both_null["summary"]["different"], 0)
            self.assertEqual(both_null["summary"]["both_null"], 1)
            self.assertEqual(both_null["summary"]["numeric_pairs"], 0)

            with self.assertRaisesRegex(review_site.MarketTruthError, "duplicate"):
                compare(
                    "duplicate_source",
                    [("123", "2022-02-01", 3.5), ("123", "2022-02-01", 3.7)],
                    [("123", "2022-02-01", 3.5)],
                )
            with self.assertRaisesRegex(review_site.MarketTruthError, "duplicate"):
                compare(
                    "duplicate_final",
                    [("123", "2022-02-01", 3.5)],
                    [("123", "2022-02-01", 3.5), ("123", "2022-02-01", 3.6)],
                )

    def test_contract_selector_includes_entirely_missing_and_extra_instruments(self):
        import duckdb

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            bars = root / "bars.parquet"
            defs = root / "definitions.parquet"
            source.write_text(
                "instrument_id,trade_date,close\n123,2022-02-01,3.5\n",
                encoding="utf-8",
            )
            conn = duckdb.connect(":memory:")
            try:
                conn.execute(
                    f"COPY (SELECT '456' AS instrument_id, '2022-02-02' AS trade_date, "
                    f"3.6::DOUBLE AS close) TO '{bars.as_posix()}' (FORMAT PARQUET)"
                )
                conn.execute(
                    f"COPY (SELECT '456' AS instrument_id, 'NGM2' AS symbol, "
                    f"'2022-01-01T00:00:00+00:00' AS available_at) "
                    f"TO '{defs.as_posix()}' (FORMAT PARQUET)"
                )
            finally:
                conn.close()
            with (
                patch.object(review_site, "pinned_metadata", return_value=self.meta),
                patch.object(review_site, "SOURCE_CSV", source),
                patch.object(review_site, "FINAL_BARS", bars),
                patch.object(review_site, "FINAL", root),
            ):
                reader = review_site.ReviewData()
                try:
                    contracts = {
                        record["id"]: record for record in reader.contracts(2022)
                    }
                    self.assertEqual(set(contracts), {"123", "456"})
                    self.assertEqual(contracts["123"]["source_rows"], 1)
                    self.assertEqual(contracts["123"]["final_rows"], 0)
                    self.assertEqual(contracts["456"]["source_rows"], 0)
                    self.assertEqual(contracts["456"]["final_rows"], 1)
                    missing = reader.series(2022, "123", "close")["summary"]
                    extra = reader.series(2022, "456", "close")["summary"]
                    self.assertEqual(
                        (missing["missing_final"], missing["extra_final"]), (1, 0)
                    )
                    self.assertEqual(
                        (extra["missing_final"], extra["extra_final"]), (0, 1)
                    )
                finally:
                    reader.db.close()

    def test_loopback_write_authentication_and_receipt_status(self):
        class FakeReview:
            meta = self.meta

            def _assert_current(self):
                return None

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(review_site, "DECISIONS", Path(directory) / "decisions"),
        ):
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                review_site.make_handler(FakeReview(), "fixed-test-token"),
            )
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                body = json.dumps(self.payload()).encode()

                def submit(token, origin):
                    request = Request(
                        base + "/api/decision",
                        data=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-Review-Token": token,
                            "Origin": origin,
                        },
                        method="POST",
                    )
                    return urlopen(request, timeout=10)

                with self.assertRaises(HTTPError) as unauthorized:
                    submit("invalid", base)
                self.assertEqual(unauthorized.exception.code, 403)
                with self.assertRaises(HTTPError) as cross_origin:
                    submit("fixed-test-token", "http://untrusted.invalid")
                self.assertEqual(cross_origin.exception.code, 403)
                with submit("fixed-test-token", base) as approved:
                    saved = json.load(approved)
                self.assertTrue(saved["saved"])
                self.assertFalse(saved["receipt"]["signed_admission"])
                receipts = list((Path(directory) / "decisions").glob("*.json"))
                self.assertEqual(len(receipts), 1)
                self.assertFalse(
                    json.loads(receipts[0].read_text())["research_admitted"]
                )
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)


class BarAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.csv"
        self.final = self.root / "final.parquet"

    def compare(self, rows, final_sql="SELECT * FROM read_csv_auto(?)"):
        self.source.write_text(
            "instrument_id,trade_date,open,high,low,close,volume\n"
            + "".join(",".join(str(value) for value in row) + "\n" for row in rows),
            encoding="utf-8",
        )
        import duckdb

        with duckdb.connect(":memory:") as db:
            db.execute(
                f"COPY ({final_sql}) TO '{self.final.as_posix()}' (FORMAT PARQUET)",
                [str(self.source)],
            )
            return review_site.reconcile_bar_fields(db, self.source, self.final)

    def test_all_years_all_metrics_exact(self):
        result = self.compare([
            ("101", "2010-01-03", 1, 2, 0.5, 1.5, 100),
            ("102", "2022-12-30", 3, 4, 2.5, 3.5, 200),
        ])
        self.assertTrue(result["exact"], result)
        self.assertEqual({r["year"] for r in result["years"]}, {2010, 2022})
        self.assertEqual(len(result["metrics"]), 5)
        self.assertTrue(all(r["paired_rows"] == 2 for r in result["metrics"]))
        self.assertFalse(result["research_admitted"])

    def test_same_row_count_value_corruption_detected_per_metric(self):
        result = self.compare(
            [("101", "2022-01-03", 1, 2, 0.5, 1.5, 100)],
            "SELECT * REPLACE (high + 1 AS high) FROM read_csv_auto(?)",
        )
        self.assertFalse(result["exact"])
        high = next(row for row in result["metrics"] if row["metric"] == "high")
        self.assertEqual(high["differing"], 1)
        self.assertEqual(high["max_abs_delta"], 1)
        self.assertEqual(high["mean_abs_delta"], 1)
        self.assertTrue(all(row["exact"] for row in result["metrics"] if row["metric"] != "high"))

    def test_same_count_wrong_identity_is_not_matched_by_day(self):
        result = self.compare(
            [("101", "2022-01-03", 1, 2, 0.5, 1.5, 100)],
            "SELECT * REPLACE ('999' AS instrument_id) FROM read_csv_auto(?)",
        )
        self.assertFalse(result["exact"])
        self.assertTrue(all(
            row["source_only"] == 1 and row["final_only"] == 1
            for row in result["metrics"]
        ))

    def test_null_mismatch_does_not_invent_numeric_delta(self):
        result = self.compare(
            [("101", "2022-01-03", 1, 2, 0.5, 1.5, 100)],
            "SELECT * REPLACE (NULL::DOUBLE AS low) FROM read_csv_auto(?)",
        )
        low = next(row for row in result["metrics"] if row["metric"] == "low")
        self.assertFalse(result["exact"])
        self.assertEqual(low["null_mismatch"], 1)
        self.assertEqual(low["numeric_pairs"], 0)
        self.assertIsNone(low["max_abs_delta"])
        self.assertIsNone(low["mean_abs_delta"])

    def test_duplicate_original_key_rejected(self):
        rows = [("101", "2022-01-03", 1, 2, 0.5, 1.5, 100)] * 2
        with self.assertRaisesRegex(review_site.MarketTruthError, "duplicate"):
            self.compare(rows)

    def test_out_of_scope_year_rejected(self):
        with self.assertRaisesRegex(review_site.MarketTruthError, "out-of-scope"):
            self.compare([("101", "2023-01-03", 1, 2, 0.5, 1.5, 100)])



if __name__ == "__main__":
    unittest.main()
