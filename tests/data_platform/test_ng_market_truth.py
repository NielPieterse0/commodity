"""Contract-level correctness tests; synthetic data never touches reserved outcomes."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, nullcontext, redirect_stderr
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from _owner_approval_fixture import sign_fixture_catalog

from commodity.market_truth import (
    MarketTruthDataset,
    MarketTruthError,
    approval,
    build_market_truth,
    curve_asof,
    normalize_ng_databento,
    publish_parquet,
    snapshot_asof,
)
from commodity.market_truth import query as market_truth_query


@contextmanager
def _fixture_approval(root: Path):
    """Explicitly approve only synthetic test fixtures, never production data."""
    entries = []
    for location in root.iterdir():
        manifest_path = location / "manifest.json"
        if not location.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            tables = manifest["tables"]
            entries.append({
                "content_sha256": manifest["content_sha256"],
                "source_manifest_sha256": manifest.get("source_manifest_sha256"),
                "source_sha256": manifest.get("source_sha256"),
                "tables_sha256": {
                    family: tables[family]["sha256"]
                    for family in ("definitions", "bars", "statistics")
                },
                "source_review_id": "synthetic-test-fixture-only",
                "local_evidence_verified": True,
            })
        except (KeyError, ValueError, TypeError):
            continue
    approval_path = root / "synthetic-approval-catalog.json"
    signed, trusted = sign_fixture_catalog(root, {
        "schema_version": 2,
        "authority": "governed_source_owner_review",
        "datasets": entries,
    })
    approval_path.write_text(json.dumps(signed), encoding="utf-8")
    # Trust lasts for the full test, including snapshots after fixture exit.
    # The unittest tearDown below removes every synthetic signer.
    approval.TRUSTED_SIGNERS.update(trusted)
    with patch.object(market_truth_query, "DEFAULT_APPROVAL_CATALOG", approval_path):
        yield


OBSERVED = "2022-05-10T23:59:00Z"
QUERY = "2022-05-10T23:59:30Z"
SYMBOLS = [
    ("110", "NGM2", "2022-05-26T00:00:00Z"),
    ("120", "NGN2", "2022-06-27T00:00:00Z"),
    ("130", "NGQ2", "2022-07-27T00:00:00Z"),
]


def fixtures():
    definitions = [
        {
            "instrument_id": num,
            "raw_symbol": symbol,
            "expiration": expiry,
            "exchange": "XNYM",
            "asset": "NG",
            "instrument_class": "F",
            "ts_event": "2022-04-01T13:00:00Z",
            "ts_recv": "2022-04-01T13:00:01Z",
        }
        for num, symbol, expiry in SYMBOLS
    ]
    bars = [
        {
            "instrument_id": num,
            "trade_date": "2022-05-10",
            "ts_event": "2022-05-10T21:00:00Z",
            "available_at": OBSERVED,
            "open": 7 + idx,
            "high": 8 + idx,
            "low": 6 + idx,
            "close": 7.5 + idx,
            "volume": 100 + idx,
        }
        for idx, (num, _, _) in enumerate(SYMBOLS[:2])
    ]
    bars.extend(
        [
            {
                "instrument_id": "110",
                "trade_date": "2022-05-09",
                "ts_event": "2022-05-09T21:00:00Z",
                "available_at": "2022-05-09T23:59:00Z",
                "open": 6,
                "high": 7,
                "low": 5,
                "close": 6.5,
                "volume": 90,
            }
        ]
    )
    stats = [
        {
            "instrument_id": "110",
            "trade_date": "2022-05-10",
            "stat_type": 3,
            "stat_flags": 1,
            "is_final": True,
            "price": 7.7,
            "ts_event": "2022-05-10T20:00:00Z",
            "ts_recv": "2022-05-10T20:00:05Z",
        },
        {
            "instrument_id": "110",
            "trade_date": "2022-05-10",
            "stat_type": 9,
            "quantity": 200,
            "ts_event": "2022-05-10T20:00:00Z",
            "ts_recv": "2022-05-10T20:00:05Z",
        },
        {
            "instrument_id": "110",
            "trade_date": "2022-05-10",
            "stat_type": 3,
            "stat_flags": 8,
            "price": 900,
            "ts_event": "2022-05-10T20:00:00Z",
            "ts_recv": "2022-05-10T20:00:05Z",
        },
    ]
    return normalize_ng_databento(definitions, bars, stats)


def store():
    return build_market_truth(*fixtures(), source_hashes={"definitions": "a" * 64})


class OwnerApprovalTestCase(unittest.TestCase):
    def tearDown(self):
        approval.TRUSTED_SIGNERS.clear()
        super().tearDown()


class MarketTruthTests(OwnerApprovalTestCase):
    def setUp(self):
        # Synthetic Linux fixtures have no kernel immutable filesystem; never
        # treat this test-only bypass as a production admission control.
        if os.name != "nt":
            guard = patch.object(
                market_truth_query, "protected_table_reads",
                lambda files: nullcontext(),
            )
            guard.start()
            self.addCleanup(guard.stop)

    def test_eager_source_reads_exactly_once_before_parsing(self):
        from scripts.data import build_ng_market_truth as pipeline

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.csv"
            source.write_text(
                "trade_date,value\n2022-05-10,7.7\n", encoding="utf-8"
            )
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            open_path = Path.open
            opened = []

            def one_open(path, *args, **kwargs):
                if path == source:
                    opened.append(args[0] if args else kwargs.get("mode"))
                    if len(opened) != 1:
                        raise AssertionError("eager reader reopened source by path")
                return open_path(path, *args, **kwargs)

            with patch.object(Path, "open", one_open):
                parsed = pipeline._read_checked_csv(source, digest)
            self.assertEqual(parsed, [{"trade_date": "2022-05-10", "value": "7.7"}])
            self.assertEqual(opened, ["rb"])

    def test_eager_source_tampering_and_size_fail_closed(self):
        from scripts.data import build_ng_market_truth as pipeline

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.csv"
            source.write_bytes(b"trade_date,value\n2022-05-10,7.7\n")
            approved = hashlib.sha256(source.read_bytes()).hexdigest()
            source.write_bytes(b"trade_date,value\n2022-05-10,999\n")
            with self.assertRaisesRegex(MarketTruthError, "SHA-256 mismatch"):
                pipeline._read_checked_csv(source, approved)
            with source.open("wb") as stream:
                stream.truncate(pipeline.MAX_EAGER_CSV_BYTES + 1)
            with self.assertRaisesRegex(MarketTruthError, "exceeds size limit"):
                pipeline._read_checked_csv(source, approved)

    def test_eager_source_rejects_malformed_csv_shapes(self):
        from scripts.data import build_ng_market_truth as pipeline

        cases = (
            (b"x,x\n1,2\n", "duplicate checked CSV headers"),
            (b"   ,x\n1,2\n", "duplicate checked CSV headers"),
            (b"x ,y\n1,2\n", "duplicate checked CSV headers"),
            (b"x, y\n1,2\n", "duplicate checked CSV headers"),
            (b"x, x\n1,2\n", "duplicate checked CSV headers"),
            (b"x,y\n1,2,3\n", "malformed checked CSV record"),
            (b"x,y\n1\n", "malformed checked CSV record"),
            (b'x\n"unterminated\n', "invalid checked source CSV"),
        )
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.csv"
            for raw, error in cases:
                with self.subTest(raw=raw):
                    source.write_bytes(raw)
                    digest = hashlib.sha256(raw).hexdigest()
                    with self.assertRaisesRegex(MarketTruthError, error):
                        pipeline._read_checked_csv(source, digest)

    def test_curve_sparse_twelve_slots_and_contract_identity(self):
        point = curve_asof(store(), "2022-05-10", QUERY)
        self.assertEqual(len(point), 12)
        self.assertEqual(point[0]["contract_symbol"], "NGM2")
        self.assertEqual(point[0]["instrument_id"], "110")
        self.assertEqual(point[0]["settle"], 7.7)
        self.assertEqual(point[0]["open_interest"], 200)
        self.assertEqual(point[2]["missing_reason"], "source_missing_price")
        self.assertEqual(point[3]["missing_reason"], "no_listed_contract")
        self.assertEqual(point[0]["volume"], 100)
        self.assertTrue(point[0]["evidence_ids"])

    def test_before_ohlcv_available_statistics_only(self):
        observed = curve_asof(store(), "2022-05-10", "2022-05-10T21:00:00Z")
        self.assertIsNone(observed[0]["close"])
        self.assertEqual(observed[0]["settle"], 7.7)

    def test_before_statistics_received_settle_hidden(self):
        observed = curve_asof(store(), "2022-05-10", "2022-05-10T20:00:00Z")
        self.assertIsNone(observed[0]["settle"])

    def test_legacy_explicit_nonfinal_settlement_is_never_accepted(self):
        from commodity.market_truth.core import normalize_statistics
        from commodity.market_truth.ng import databento_ng_settlement_eligible

        def normalized(rows):
            return normalize_statistics(rows, settlement_policy=databento_ng_settlement_eligible)

        base = {
            "instrument_id": "110",
            "trade_date": "2015-06-16",
            "ts_event": "2015-06-16T20:00:00Z",
            "ts_recv": "2015-06-16T20:00:01Z",
            "stat_type": 3,
            "stat_flags": 0,
            "price": 2.9,
        }
        self.assertEqual(normalize_statistics([base]), [])
        self.assertEqual(len(normalized([base])), 1)
        for explicit in (False, 0, "false", "False", "0"):
            with self.subTest(explicit=explicit):
                self.assertEqual(
                    normalized([dict(base, is_final=explicit)]), []
                )
        for explicit in (True, "True", "1"):
            with self.subTest(explicit=explicit):
                self.assertEqual(
                    len(normalized([dict(base, is_final=explicit)])), 1
                )

    def test_legacy_databento_settlement_flags_obey_2015_boundary(self):
        from commodity.market_truth.core import normalize_statistics
        from commodity.market_truth.ng import databento_ng_settlement_eligible

        def item(day, flags, price):
            return {
                "instrument_id": "NG1",
                "trade_date": day,
                "ts_event": day + "T20:00:00Z",
                "ts_recv": day + "T20:00:01Z",
                "stat_type": 3,
                "stat_flags": flags,
                "price": price,
            }

        rows = normalize_statistics([
            item("2015-11-19", 0, 2.5),
            item("2015-11-19", 100, 99.0),
            item("2015-11-19", 101, 99.0),
            item("2015-11-20", 0, 99.0),
            item("2015-11-20", 1, 2.6),
            item("2015-11-20", 8, 99.0),
        ], settlement_policy=databento_ng_settlement_eligible)
        self.assertEqual([(r["trade_date"], r["value"]) for r in rows], [
            ("2015-11-19", 2.5), ("2015-11-20", 2.6),
        ])

    def test_ng_adapter_uses_later_of_source_event_and_receive_clock(self):
        from commodity.market_truth.ng import normalize_ng_databento_record

        row = {
            "instrument_id": "NG2018",
            "ts_ref": "2018-08-21T00:00:00Z",
            "ts_event": "2018-08-22T10:00:01.200000Z",
            "ts_recv": "2018-08-22T10:00:00.500000Z",
            "stat_type": "3", "stat_flags": "1", "price": "2.88",
        }
        actual = normalize_ng_databento_record("statistics", row)
        self.assertEqual(actual["event_at"], actual["available_at"])
        self.assertEqual(actual["trade_date"], "2018-08-21")
        # Caller-supplied explicit availability is an assertion, not an
        # invitation to shift the clock until the assertion passes.
        with self.assertRaisesRegex(
            MarketTruthError, "source fact available before event"
        ):
            normalize_ng_databento_record(
                "statistics", dict(row, available_at="2018-08-22T10:00:00Z")
            )

    def test_vendor_statistics_without_ts_ref_cannot_invent_trade_date(self):
        from commodity.market_truth.ng import normalize_ng_databento_record

        for kind in ("6", "9"):
            with self.subTest(stat_type=kind), self.assertRaisesRegex(
                MarketTruthError, "statistic trade_date/ts_ref missing"
            ):
                normalize_ng_databento_record("statistics", {
                    "instrument_id": "110",
                    "ts_event": "2015-06-16T10:00:00Z",
                    "ts_recv": "2015-06-16T10:00:01Z",
                    "stat_type": kind,
                    "quantity": "100",
                })

    def test_same_contract_momentum_not_roll_cross_price(self):
        decision = snapshot_asof(
            store(), "2022-05-10", QUERY, session_history=["2022-05-09"]
        )
        self.assertAlmostEqual(decision["features"]["front_momentum_1"], 7.7 / 6.5 - 1)
        self.assertIsNone(decision["features"]["front_momentum_5"])
        self.assertAlmostEqual(
            decision["features"]["m1_m2_spread_price_per_unit"], -0.8
        )
        self.assertFalse(decision["protected_confirmation_accessed"])

    def test_future_revision_invariance(self):
        fixture = fixtures()
        base = build_market_truth(*fixture)
        future_stat = dict(fixture[2][0])
        future_stat["price"] = 999
        future_stat["ts_recv"] = "2022-05-11T09:01:00Z"
        later = build_market_truth(fixture[0], fixture[1], [*fixture[2], future_stat])
        self.assertEqual(
            snapshot_asof(base, "2022-05-10", QUERY),
            snapshot_asof(later, "2022-05-10", QUERY),
        )
        self.assertEqual(
            curve_asof(later, "2022-05-10", "2022-05-11T10:00:00Z")[0]["settle"], 999
        )

    def test_ambiguous_identical_clock_revisions_fail(self):
        definitions, bars, stats = fixtures()
        contradictory = dict(bars[0], close=7.1)
        with self.assertRaisesRegex(MarketTruthError, "ambiguous bar revision"):
            build_market_truth(definitions, [*bars, contradictory], stats)

    def test_ng_adapter_scopes_mixed_product_source_facts(self):
        definitions, bars, stats = fixtures()
        foreign_definition = dict(
            definitions[0],
            instrument_id="CL999",
            asset="CL",
            raw_symbol="CLM2",
        )
        foreign_bar = dict(bars[0], instrument_id="CL999")
        foreign_stat = dict(stats[0], instrument_id="CL999")
        scoped = normalize_ng_databento(
            [*definitions, foreign_definition],
            [*bars, foreign_bar],
            [*stats, foreign_stat],
        )
        self.assertEqual(len(scoped[0]), len(definitions))
        self.assertEqual(len(scoped[1]), len(bars))
        self.assertEqual(len(scoped[2]), len(stats))
        truth = build_market_truth(*scoped)
        self.assertEqual(len(truth["definitions"]), len(definitions))
        self.assertEqual(curve_asof(truth, "2022-05-10", QUERY)[0]["settle"], 7.7)

    def test_generic_core_rejects_unscoped_foreign_fact(self):
        definitions, bars, stats = fixtures()
        foreign_bar = dict(bars[0], instrument_id="CL999")
        with self.assertRaisesRegex(MarketTruthError, "no verified source contract"):
            build_market_truth(definitions, [*bars, foreign_bar], stats)

    def test_protected_session_and_query_fail_closed(self):
        item = store()
        for session, time in [
            ("2023-01-01", "2023-01-01T12:00:00Z"),
            ("2022-05-10", "2023-01-01T12:00:00Z"),
        ]:
            with self.assertRaisesRegex(MarketTruthError, "protected_confirmation"):
                curve_asof(item, session, time)
        definitions, bars, stats = fixtures()
        bars[0]["trade_date"] = "2023-01-01"
        with self.assertRaisesRegex(MarketTruthError, "protected_confirmation"):
            build_market_truth(definitions, bars, stats)

    def test_missing_availability_fail_closed(self):
        definitions, bars, stats = fixtures()
        bars[0].pop("available_at")
        with self.assertRaisesRegex(MarketTruthError, "availability"):
            build_market_truth(definitions, bars, stats)

    def test_expiry_and_rank_remap_asof(self):
        data = store()
        point = curve_asof(data, "2022-06-10", "2022-06-10T23:59:59Z")
        self.assertEqual(point[0]["contract_symbol"], "NGN2")
        self.assertEqual(point[1]["contract_symbol"], "NGQ2")
        self.assertIsNone(point[2]["instrument_id"])

    def test_intraday_last_trade_rank_parity_in_memory_and_parquet(self):
        definitions, bars, stats = fixtures()
        definitions[0]["last_trade_at"] = "2022-05-10T19:00:00Z"
        truth = build_market_truth(definitions, bars, stats)
        early = "2022-05-10T18:59:59Z"
        late = "2022-05-10T23:59:59Z"
        self.assertEqual(curve_asof(truth, "2022-05-10", early)[0]["contract_symbol"], "NGM2")
        self.assertEqual(curve_asof(truth, "2022-05-10", late)[0]["contract_symbol"], "NGN2")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            digest = publish_parquet(truth, root / "snapshot")["content_sha256"]
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                reader = MarketTruthDataset(root / "snapshot", expected_content_sha256=digest)
                self.assertEqual(reader.snapshot("2022-05-10", early)["curve_points"][0]["contract_symbol"], "NGM2")
                self.assertEqual(reader.snapshot("2022-05-10", late)["curve_points"][0]["contract_symbol"], "NGN2")

    def test_revised_contract_expiry_is_point_in_time(self):
        definitions, bars, stats = fixtures()
        definitions[2]["expiration"] = "2022-07-27T19:30:00Z"
        revised = dict(
            definitions[2],
            expiration="2022-07-27T18:30:00Z",
            ts_event="2022-05-11T12:00:00Z",
            ts_recv="2022-05-11T12:00:01Z",
        )
        history = build_market_truth([*definitions, revised], bars, stats)
        earlier = curve_asof(history, "2022-05-10", "2022-05-10T23:59:59Z")
        later = curve_asof(history, "2022-05-12", "2022-05-12T23:59:59Z")
        replay = curve_asof(history, "2022-05-10", "2022-05-12T23:59:59Z")
        self.assertEqual(earlier[2]["expiration"], "2022-07-27T19:30:00+00:00")
        self.assertEqual(replay[2]["expiration"], earlier[2]["expiration"])
        self.assertEqual(later[2]["expiration"], "2022-07-27T18:30:00+00:00")

    def test_expiry_fallback_has_intraday_boundary(self):
        definitions, bars, stats = fixtures()
        definitions[0]["expiration"] = "2022-05-10T19:00:00Z"
        truth = build_market_truth(definitions, bars, stats)
        self.assertEqual(curve_asof(truth, "2022-05-10", "2022-05-10T18:59:59Z")[0]["contract_symbol"], "NGM2")
        self.assertEqual(curve_asof(truth, "2022-05-10", "2022-05-10T19:00:00Z")[0]["contract_symbol"], "NGN2")

    def test_publish_has_hashed_zstd_parquet_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder) / "snapshot"
            result = publish_parquet(store(), location)
            self.assertEqual(result["tables"]["bars"]["rows"], 3)
            self.assertEqual(result["tables"]["definitions"]["compression"], "zstd")
            self.assertFalse(result["protected_confirmation_accessed"])
            with self.assertRaisesRegex(MarketTruthError, "refusing overwrite"):
                publish_parquet(store(), location)

    def test_parquet_snapshot_reader_parity_and_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder) / "snapshot"
            source = store()
            metadata = publish_parquet(source, location)
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", location.parent), _fixture_approval(location.parent):
                reader = MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )
            expected = snapshot_asof(
                source, "2022-05-10", QUERY, session_history=["2022-05-09"]
            )
            actual = reader.snapshot(
                "2022-05-10", QUERY, session_history=["2022-05-09"]
            )
            for field in ("features", "curve_points", "evidence_ids"):
                self.assertEqual(actual[field], expected[field])
            self.assertTrue(actual["dataset_content_sha256"])
            self.assertFalse(actual["protected_confirmation_accessed"])
            with self.assertRaisesRegex(MarketTruthError, "protected_confirmation"):
                reader.snapshot("2022-05-10", "2023-01-01T00:00:00Z")
            with (location / "bars.parquet").open("ab") as stream:
                stream.write(b"tampered")
            with (
                self.assertRaisesRegex(MarketTruthError, "size mismatch|checksum failure"),
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", location.parent),
                _fixture_approval(location.parent),
            ):
                MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )

    def test_reader_checks_files_again_at_query_time(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            metadata = publish_parquet(store(), location)
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                reader = MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )
                with (location / "bars.parquet").open("ab") as file:
                    file.write(b"changed-after-initial-check")
                with self.assertRaisesRegex(MarketTruthError, "size mismatch"):
                    reader.snapshot("2022-05-10", QUERY)

    def test_reader_has_no_caller_override_for_trusted_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            metadata = publish_parquet(store(), location)
            with self.assertRaisesRegex(MarketTruthError, "approved development-only root"):
                MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )
            with self.assertRaises(TypeError):
                MarketTruthDataset(
                    location,
                    expected_content_sha256=metadata["content_sha256"],
                    approved_root=root,
                )

    def test_reader_requires_pinned_manifest_and_real_parquet_row_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            original = publish_parquet(store(), location)
            manifest_path = location / "manifest.json"
            forged = json.loads(manifest_path.read_text(encoding="utf-8"))
            forged["tables"]["bars"]["rows"] += 1
            forged["content_sha256"] = market_truth_query._evidence(
                {k: v for k, v in forged.items() if k != "content_sha256"}
            )
            manifest_path.write_text(json.dumps(forged), encoding="utf-8")
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                with self.assertRaisesRegex(MarketTruthError, "identity mismatch"):
                    MarketTruthDataset(
                        location,
                        expected_content_sha256=original["content_sha256"],
                    )
                with self.assertRaisesRegex(MarketTruthError, "row-count mismatch"):
                    MarketTruthDataset(
                        location,
                        expected_content_sha256=forged["content_sha256"],
                    )

    def test_reader_rejects_bad_parquet_metadata_with_domain_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            publish_parquet(store(), location)
            bad_file = location / "bars.parquet"
            bad_file.write_bytes(b"invalid-parquet-file")
            manifest_path = location / "manifest.json"
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
            metadata["tables"]["bars"]["bytes"] = bad_file.stat().st_size
            metadata["tables"]["bars"]["sha256"] = hashlib.sha256(
                bad_file.read_bytes()
            ).hexdigest()
            metadata["content_sha256"] = market_truth_query._evidence(
                {k: v for k, v in metadata.items() if k != "content_sha256"}
            )
            manifest_path.write_text(json.dumps(metadata), encoding="utf-8")
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
                self.assertRaisesRegex(MarketTruthError, "unreadable market table metadata"),
            ):
                MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )

    def test_reader_limits_manifest_read_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            metadata = publish_parquet(store(), location)
            with (location / "manifest.json").open("ab") as file:
                file.write(b" " * (market_truth_query.MAX_MANIFEST_BYTES + 1))
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
                self.assertRaisesRegex(MarketTruthError, "exceeds size limit"),
            ):
                MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )

    def test_definition_first_seen_later_cannot_rewrite_old_rank(self):
        definitions, bars, stats = fixtures()
        later_contract = {
            **definitions[0],
            "instrument_id": "999",
            "raw_symbol": "NGK2",
            "expiration": "2022-05-15T00:00:00Z",
            "ts_event": "2022-05-11T10:00:00Z",
            "ts_recv": "2022-05-11T10:00:01Z",
        }
        # A late definition cannot be projected backwards into a May 10 listing.
        old = build_market_truth(definitions, bars, stats)
        changed = build_market_truth([*definitions, later_contract], bars, stats)
        self.assertEqual(
            curve_asof(old, "2022-05-10", "2022-05-12T12:00:00Z"),
            curve_asof(changed, "2022-05-10", "2022-05-12T12:00:00Z"),
        )

    def test_large_input_uses_streaming_and_checks_sha_before_parsing(self):
        from scripts.data import build_ng_market_truth as pipeline

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = {}
            for name, schema in pipeline.SCHEMAS.items():
                path = root / f"{name}.csv"
                with path.open("wb") as file:
                    file.write(b"instrument_id\\n")
                    if name == "definitions":
                        file.truncate(pipeline.MAX_EAGER_CSV_BYTES + 1)
                records[name] = {
                    "schema": schema,
                    "relative_path": path.name,
                    "sha256": "0" * 64,
                    "row_count": 1,
                }
            manifest = root / "source_manifest.json"
            manifest.write_text(
                json.dumps({
                    "schema_version": 1,
                    "evidence_class": "development",
                    "protected_confirmation_accessed": False,
                    "dataset": "GLBX.MDP3",
                    "product_code": "NG",
                    "max_trade_date": "2022-05-10",
                    "inputs": records,
                }),
                encoding="utf-8",
            )
            with (
                patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                patch.object(pipeline, "_read_checked_csv", side_effect=AssertionError(
                    "oversized input must not be opened"
                )),
                self.assertRaisesRegex(MarketTruthError, "raw input SHA-256 mismatch"),
            ):
                pipeline.build_from_manifest(manifest, root / "not-created")
            self.assertFalse((root / "not-created").exists())

    def test_governed_csv_to_parquet_and_protected_preflight(self):
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, stats = fixtures()
        families = {"definitions": definitions, "bars": bars, "statistics": stats}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = {}
            for name, rows in families.items():
                path = root / f"{name}.csv"
                headers = sorted({field for row in rows for field in row})
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)
                inputs[name] = {
                    "schema": pipeline.SCHEMAS[name],
                    "relative_path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "row_count": len(rows),
                }
            payload = {
                "schema_version": 1,
                "evidence_class": "development",
                "protected_confirmation_accessed": False,
                "dataset": "GLBX.MDP3",
                "product_code": "NG",
                "max_trade_date": "2022-05-10",
                "inputs": inputs,
            }
            source_manifest = root / "source_manifest.json"
            source_manifest.write_text(
                json.dumps(payload), encoding="utf-8", newline="\n"
            )
            with patch.object(pipeline, "ALLOWED_INPUT_ROOT", root):
                built = pipeline.build_from_manifest(
                    source_manifest, root / "verified_output"
                )
                self.assertEqual(built["tables"]["definitions"]["rows"], 3)
                self.assertEqual(built["tables"]["bars"]["rows"], 3)
                self.assertEqual(built["dataset_scope"], "development_pre2023")
                self.assertEqual(
                    built["source_manifest_sha256"],
                    hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
                )
                with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                    self.assertEqual(
                        MarketTruthDataset(
                            root / "verified_output",
                            expected_content_sha256=built["content_sha256"],
                        ).snapshot(
                            "2022-05-10", QUERY
                        )["features"]["front_price"],
                        7.7,
                    )
                payload["max_trade_date"] = "2023-01-01"
                source_manifest.write_text(
                    json.dumps(payload), encoding="utf-8", newline="\n"
                )
                with (
                    patch.object(
                        pipeline,
                        "_read_checked_csv",
                        side_effect=AssertionError("must not open prohibited source"),
                    ),
                    self.assertRaisesRegex(MarketTruthError, "protected_confirmation"),
                ):
                    pipeline.build_from_manifest(source_manifest, root / "denied")

    def test_sparse_history_does_not_compress_momentum_horizon(self):
        definitions, bars, stats = fixtures()
        earlier = dict(
            bars[-1],
            trade_date="2022-05-08",
            available_at="2022-05-08T23:59:00Z",
            ts_event="2022-05-08T21:00:00Z",
        )
        data = build_market_truth(definitions, [*bars[:-1], earlier], stats)
        point = snapshot_asof(
            data,
            "2022-05-10",
            QUERY,
            session_history=["2022-05-08", "2022-05-09"],
        )
        self.assertIsNone(point["features"]["front_momentum_1"])
        self.assertIsNone(point["features"]["front_momentum_5"])

    def test_vendor_instrument_id_reuse_does_not_cross_contract_roll(self):
        definitions, bars, stats = fixtures()
        reused = dict(
            definitions[0],
            raw_symbol="NGK2",
            expiration="2022-05-23T00:00:00Z",
            ts_event="2022-05-10T12:00:00Z",
            ts_recv="2022-05-10T12:00:01Z",
        )
        data = build_market_truth([*definitions, reused], bars, stats)
        point = snapshot_asof(
            data,
            "2022-05-10",
            QUERY,
            session_history=["2022-05-09"],
        )
        self.assertIsNone(point["features"]["front_momentum_1"])
        self.assertTrue(point["roll_transition"]["observed"])

    @unittest.skipIf(os.name == "nt", "non-Windows safety boundary only")
    def test_nonwindows_guard_fails_closed_even_with_mutable_data(self):
        from commodity.market_truth.protected_reads import protected_table_reads

        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "market.parquet"
            raw.write_bytes(b"untrusted")
            with self.assertRaisesRegex(
                MarketTruthError, "non-Windows immutable source protection"
            ), protected_table_reads([raw]):
                self.fail("must not enter unprotected DuckDB read")

    @unittest.skipUnless(os.name == "nt", "Windows sharing boundary only")
    def test_windows_ancestor_rename_denied_while_snapshot_guarded(self):
        from commodity.market_truth.protected_reads import protected_table_reads

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nested = root / "archive" / "dataset"
            nested.mkdir(parents=True)
            data = nested / "market.parquet"
            data.write_bytes(b"approved")
            with protected_table_reads([data]):
                with self.assertRaises(OSError):
                    os.replace(nested.parent, root / "diverted")
                with self.assertRaises(OSError):
                    os.replace(nested, nested.parent / "replacement")
                self.assertEqual(data.read_bytes(), b"approved")
            os.replace(nested.parent, root / "diverted")
            self.assertTrue((root / "diverted" / "dataset" / "market.parquet").exists())

    @unittest.skipUnless(os.name == "nt", "Windows sharing boundary only")
    def test_windows_read_handles_block_concurrent_write_and_replace(self):
        from commodity.market_truth.protected_reads import protected_table_reads

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "approved.parquet"
            replacement = root / "replacement.parquet"
            original.write_bytes(b"pinned-dataset")
            replacement.write_bytes(b"attacker-replacement")
            with protected_table_reads([original]):
                with self.assertRaises(OSError), original.open("ab") as writer:
                    writer.write(b"malicious")
                with self.assertRaises(OSError):
                    os.replace(replacement, original)
                self.assertEqual(original.read_bytes(), b"pinned-dataset")
            os.replace(replacement, original)
            self.assertEqual(original.read_bytes(), b"attacker-replacement")

    @unittest.skipUnless(os.name == "nt", "Windows sharing boundary only")
    def test_windows_snapshot_denies_mutation_while_querying(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            meta = publish_parquet(store(), location)
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                reader = MarketTruthDataset(
                    location, expected_content_sha256=meta["content_sha256"]
                )
                actual = reader._curve_from_parquet

                def attack(connection, day, cutoff, ranks):
                    with self.assertRaises(OSError), (location / "bars.parquet").open("ab") as writer:
                        writer.write(b"unsafe")
                    return actual(connection, day, cutoff, ranks)

                with patch.object(reader, "_curve_from_parquet", side_effect=attack):
                    result = reader.snapshot("2022-05-10", QUERY)
                self.assertEqual(result["features"]["front_price"], 7.7)

    def test_forged_source_attestation_cannot_admit_reader(self):
        from commodity.market_truth.attestation import SourceBuildAttestation

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = publish_parquet(store(), root / "forged")
            # A valid-looking typed attestation is directly constructible. It
            # therefore MUST NOT grant dataset read authority.
            forged = SourceBuildAttestation(
                dataset_scope="development_pre2023",
                protected_confirmation_accessed=False,
                source_manifest_sha256="a" * 64,
            )
            self.assertFalse(forged.protected_confirmation_accessed)
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                self.assertRaisesRegex(
                    MarketTruthError, "no independent source-owner approval"
                ),
            ):
                MarketTruthDataset(
                    root / "forged",
                    expected_content_sha256=metadata["content_sha256"],
                )

    def test_unsigned_or_impersonated_owner_cannot_admit_matching_dataset(self):
        from commodity.market_truth import approval

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = publish_parquet(store(), root / "snapshot")
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                catalog_path = root / "synthetic-approval-catalog.json"
                genuine = json.loads(catalog_path.read_text(encoding="utf-8"))
                attempts = (
                    ("unsigned", lambda value: [
                        value.pop("signer_key_id"), value.pop("signature_ed25519")
                    ], "signed source-owner approval required"),
                    ("impersonated", lambda value: value.update(
                        signer_key_id="attacker-controlled-signing-key"
                    ), "untrusted source-owner signing key"),
                    ("substituted_signature", lambda value: value.update(
                        signature_ed25519="0" * 128
                    ), "source-owner approval signature invalid"),
                    ("modified_review", lambda value: value["datasets"][0].update(
                        source_review_id="forged_review"
                    ), "source-owner approval signature invalid"),
                )
                for name, alter, diagnostic in attempts:
                    with self.subTest(name=name):
                        candidate = copy.deepcopy(genuine)
                        alter(candidate)
                        catalog_path.write_text(json.dumps(candidate), encoding="utf-8")
                        with self.assertRaisesRegex(MarketTruthError, diagnostic):
                            MarketTruthDataset(
                                root / "snapshot",
                                expected_content_sha256=metadata["content_sha256"],
                            )
                catalog_path.write_text(json.dumps(genuine), encoding="utf-8")
                with (
                    patch.dict(approval.TRUSTED_SIGNERS, {}, clear=True),
                    self.assertRaisesRegex(MarketTruthError, "untrusted source-owner signing key"),
                ):
                    MarketTruthDataset(
                        root / "snapshot",
                        expected_content_sha256=metadata["content_sha256"],
                    )
                with (
                    patch.object(approval, "OPENSSL_BINARY", root / "missing-openssl"),
                    self.assertRaisesRegex(MarketTruthError, "signature verifier unavailable"),
                ):
                    MarketTruthDataset(
                        root / "snapshot",
                        expected_content_sha256=metadata["content_sha256"],
                    )

    def test_owner_signature_format_and_verifier_startup_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = publish_parquet(store(), root / "snapshot")
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                catalog_path = root / "synthetic-approval-catalog.json"
                genuine = json.loads(catalog_path.read_text(encoding="utf-8"))
                for invalid in (None, "", "0" * 2, "g" * 128, "0" * 130):
                    changed = copy.deepcopy(genuine)
                    changed["signature_ed25519"] = invalid
                    catalog_path.write_text(json.dumps(changed), encoding="utf-8")
                    with (
                        self.subTest(signature=repr(invalid)[:24]),
                        patch.object(approval.subprocess, "run",
                                     side_effect=AssertionError("must not invoke OpenSSL")),
                        self.assertRaisesRegex(MarketTruthError, "invalid source-owner signature format"),
                    ):
                        MarketTruthDataset(
                            root / "snapshot",
                            expected_content_sha256=metadata["content_sha256"],
                        )
                catalog_path.write_text(json.dumps(genuine), encoding="utf-8")
                startup = subprocess.CompletedProcess([], 0xC0000142, b"", b"")
                valid = subprocess.CompletedProcess([], 0, b"", b"")
                invalid = subprocess.CompletedProcess([], 1, b"", b"")
                for attempts, expected, calls in (
                    ([startup, startup, valid], None, 3),
                    ([startup, startup, startup], "signature verifier unavailable", 3),
                    ([invalid], "source-owner approval signature invalid", 1),
                    ([subprocess.TimeoutExpired(cmd="openssl", timeout=10)],
                     "signature verifier unavailable", 1),
                ):
                    with (
                        self.subTest(expected=expected, calls=calls),
                        patch.object(approval.subprocess, "run", side_effect=attempts) as run,
                    ):
                        if expected is None:
                            MarketTruthDataset(
                                root / "snapshot",
                                expected_content_sha256=metadata["content_sha256"],
                            )
                        else:
                            with self.assertRaisesRegex(MarketTruthError, expected):
                                MarketTruthDataset(
                                    root / "snapshot",
                                    expected_content_sha256=metadata["content_sha256"],
                                )
                        self.assertEqual(run.call_count, calls)

    def test_signed_catalog_rollback_rejected_by_trusted_release_pin(self):
        # Owner approval is not enough: an older signed catalog must not
        # regain authority after a separately governed release-pin rotation.
        self.assertEqual(approval.TRUSTED_SIGNERS, {})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = publish_parquet(store(), root / "snapshot")
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                self.assertEqual(len(approval.TRUSTED_SIGNERS), 1)
                signer, (pubkey, pinned) = next(iter(approval.TRUSTED_SIGNERS.items()))
                self.assertEqual(len(pinned), 64)
                reader = MarketTruthDataset(
                    root / "snapshot", expected_content_sha256=metadata["content_sha256"]
                )
                reader.snapshot("2022-05-10", QUERY)
                # Restore the same valid signed catalog after deployment has
                # advanced the trusted release identity: both old and new
                # readers must reject it even though Ed25519 still verifies.
                with patch.dict(approval.TRUSTED_SIGNERS, {signer: (pubkey, "0" * 64)}):
                    with self.assertRaisesRegex(
                        MarketTruthError, "untrusted source-owner catalog release"
                    ):
                        reader.snapshot("2022-05-10", QUERY)
                    with self.assertRaisesRegex(
                        MarketTruthError, "untrusted source-owner catalog release"
                    ):
                        MarketTruthDataset(
                            root / "snapshot",
                            expected_content_sha256=metadata["content_sha256"],
                        )
                with (
                    patch.dict(approval.TRUSTED_SIGNERS, {}, clear=True),
                    self.assertRaisesRegex(MarketTruthError, "untrusted source-owner signing key"),
                ):
                    reader.snapshot("2022-05-10", QUERY)
                # Deployment may atomically REPLACE its mapping rather than
                # mutating it: existing readers must resolve the live owner state.
                with (
                    patch.object(approval, "TRUSTED_SIGNERS", {}),
                    self.assertRaisesRegex(MarketTruthError, "untrusted source-owner signing key"),
                ):
                    reader.snapshot("2022-05-10", QUERY)
            approval.TRUSTED_SIGNERS.clear()
            self.assertEqual(approval.TRUSTED_SIGNERS, {})

    def test_reader_rejects_forged_admission_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = publish_parquet(store(), root / "snapshot")
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                approval_path = root / "synthetic-approval-catalog.json"
                original = json.loads(approval_path.read_text(encoding="utf-8"))
                for tampering in (
                    {"source_sha256": {"definitions": "b" * 64}},
                    {"local_evidence_verified": False},
                    {"source_review_id": ""},
                    {"tables_sha256": {"bars": "b" * 64}},
                ):
                    with self.subTest(tampering=tampering):
                        altered = copy.deepcopy(original)
                        altered["datasets"][0].update(tampering)
                        approval_path.write_text(
                            json.dumps(altered), encoding="utf-8"
                        )
                        with self.assertRaisesRegex(
                            MarketTruthError, "source-owner approval signature invalid"
                        ):
                            MarketTruthDataset(
                                root / "snapshot",
                                expected_content_sha256=metadata["content_sha256"],
                            )

    def test_manifest_mutation_blocks_existing_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            metadata = publish_parquet(store(), location)
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                reader = MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )
                manifest_path = location / "manifest.json"
                manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
                with self.assertRaisesRegex(
                    MarketTruthError, "manifest mutated after opening"
                ):
                    reader.snapshot("2022-05-10", QUERY)

    def test_revoked_source_approval_blocks_existing_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = publish_parquet(store(), root / "snapshot")
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                reader = MarketTruthDataset(
                    root / "snapshot",
                    expected_content_sha256=metadata["content_sha256"],
                )
                (root / "synthetic-approval-catalog.json").write_text(
                    json.dumps({
                        "schema_version": 2,
                        "authority": "governed_source_owner_review",
                        "datasets": [],
                    }), encoding="utf-8"
                )
                with self.assertRaisesRegex(
                    MarketTruthError, "no independent source-owner approval"
                ):
                    reader.snapshot("2022-05-10", QUERY)

    def test_duplicate_source_approvals_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = publish_parquet(store(), root / "snapshot")
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
            ):
                path = root / "synthetic-approval-catalog.json"
                approved = json.loads(path.read_text(encoding="utf-8"))
                approved["datasets"].append(copy.deepcopy(approved["datasets"][0]))
                path.write_text(json.dumps(approved), encoding="utf-8")
                with self.assertRaisesRegex(
                    MarketTruthError, "duplicate source-owner approval"
                ):
                    MarketTruthDataset(
                        root / "snapshot",
                        expected_content_sha256=metadata["content_sha256"],
                    )

    def test_unapproved_parquet_root_is_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder) / "snapshot"
            metadata = publish_parquet(store(), location)
            with self.assertRaisesRegex(
                MarketTruthError, "approved development-only root"
            ):
                MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )

    def test_parquet_query_matches_future_revision_and_historical_rank_cutoffs(self):
        definitions, bars, stats = fixtures()
        late_definition = dict(
            definitions[0],
            instrument_id="999",
            raw_symbol="NGK2",
            expiration="2022-05-20T00:00:00Z",
            ts_event="2022-05-11T10:00:00Z",
            ts_recv="2022-05-11T10:00:01Z",
        )
        late_statistic = dict(
            stats[0], price=999,
            ts_event="2022-05-11T09:00:00Z",
            ts_recv="2022-05-11T09:00:01Z",
        )
        source = build_market_truth(
            [*definitions, late_definition], bars, [*stats, late_statistic]
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            metadata = publish_parquet(source, location)
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                reader = MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )
            for cutoff in (
                "2022-05-10T20:00:00Z",
                QUERY,
                "2022-05-11T10:00:00Z",
            ):
                expected = snapshot_asof(
                    source, "2022-05-10", cutoff,
                    session_history=["2022-05-09"],
                )
                actual = reader.snapshot(
                    "2022-05-10", cutoff, session_history=["2022-05-09"]
                )
                for field in ("features", "curve_points", "roll_transition"):
                    self.assertEqual(actual[field], expected[field])

    def test_parquet_rank_query_rejects_alias_conflict_beyond_first_twelve(self):
        definitions, bars, stats = fixtures()
        extra = [
            dict(
                definitions[0],
                instrument_id=str(200 + i),
                raw_symbol=f"NGEX{i:02d}",
                expiration="2022-12-20T00:00:00Z",
            )
            for i in range(12)
        ]
        extra.extend(
            dict(
                definitions[0],
                instrument_id=str(300 + i),
                raw_symbol="NGZZZ",
                expiration="2022-12-25T00:00:00Z",
            )
            for i in range(2)
        )
        source = build_market_truth([*definitions, *extra], bars, stats)
        with self.assertRaisesRegex(MarketTruthError, "ambiguous source contract alias"):
            curve_asof(source, "2022-05-10", QUERY)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            metadata = publish_parquet(source, location)
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                _fixture_approval(root),
                self.assertRaisesRegex(
                    MarketTruthError, "ambiguous source contract alias"
                ),
            ):
                MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                ).snapshot("2022-05-10", QUERY)

    def test_parquet_history_pruning_preserves_all_twenty_session_features(self):
        definitions, bars, stats = fixtures()
        first = date(2022, 4, 15)
        days = [first + timedelta(days=i) for i in range(26)]
        historical_bars = [
            dict(
                bars[0], trade_date=day.isoformat(),
                ts_event=day.isoformat() + "T21:00:00Z",
                available_at=day.isoformat() + "T23:59:00Z",
            )
            for day in days
        ]
        source = build_market_truth(
            definitions,
            [*historical_bars, bars[1]],
            stats,
        )
        history = [day.isoformat() for day in days[:-1]]
        # Caller order is not authority: duplicates and later dates cannot
        # displace the latest 20 eligible historical sessions.
        history = [*reversed(history), history[3], "2022-06-01", "2022-05-10"]
        expected = snapshot_asof(
            source, days[-1], QUERY, session_history=history
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "snapshot"
            metadata = publish_parquet(source, location)
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                reader = MarketTruthDataset(
                    location, expected_content_sha256=metadata["content_sha256"]
                )
            actual = reader.snapshot(days[-1], QUERY, session_history=history)
        for field in ("features", "curve_points", "roll_transition"):
            self.assertEqual(actual[field], expected[field])

    def test_parquet_warmup_and_sparse_official_statistics_match_eager(self):
        # All 20 prior sessions are explicit calendar slots, not a compacted
        # list of days with prices. No undated OI or volume may be invented.
        definitions, bars, statistics = fixtures()
        calendar_days = [date(2022, 4, 11) + timedelta(days=i) for i in range(29)]
        days = [day for day in calendar_days if day.weekday() < 5][-20:]
        self.assertEqual(len(days), 20)
        self.assertEqual(days[-1], date(2022, 5, 9))
        for missing_last_session in (False, True):
            with self.subTest(missing_last_session=missing_last_session):
                history_bars = [
                    dict(
                        bars[0], trade_date=day.isoformat(),
                        ts_event=day.isoformat() + "T21:00:00Z",
                        available_at=day.isoformat() + "T23:59:00Z",
                        close=6.0 + i / 100,
                    )
                    for i, day in enumerate(days)
                    if not (missing_last_session and i == 19)
                ]
                # Remove the only valid official open-interest observation.
                no_oi = [row for row in statistics if row["stat_type"] != 9]
                source = build_market_truth(
                    definitions, [*bars[:2], *history_bars], no_oi
                )
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    location = root / "snapshot"
                    metadata = publish_parquet(source, location)
                    with (
                        patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                        _fixture_approval(root),
                    ):
                        reader = MarketTruthDataset(
                            location, expected_content_sha256=metadata["content_sha256"]
                        )
                    for count in (0, 1, 4, 5, 19, 20):
                        history = [day.isoformat() for day in days[-count:]] if count else []
                        expected = snapshot_asof(
                            source, "2022-05-10", QUERY, session_history=history
                        )
                        actual = reader.snapshot(
                            "2022-05-10", QUERY, session_history=history
                        )
                        with self.subTest(history_count=count):
                            for key, value in expected.items():
                                self.assertEqual(actual[key], value, key)
                            features = actual["features"]
                            self.assertEqual(len(actual["curve_points"]), 12)
                            self.assertEqual(features["front_price"], 7.7)
                            self.assertEqual(features["front_volume"], 100)
                            self.assertIsNone(features["front_open_interest"])
                            self.assertIsNone(features["front_liquidity_volume_oi_ratio"])
                            self.assertIsNone(actual["curve_points"][0]["cleared_volume"])
                            for name, lag in (
                                ("front_momentum_1", 1),
                                ("front_momentum_5", 5),
                                ("front_momentum_20", 20),
                            ):
                                if count < lag or missing_last_session:
                                    self.assertIsNone(features[name])
                                else:
                                    expected_prior = 6.0 + (20 - lag) / 100
                                    self.assertAlmostEqual(
                                        features[name], 7.7 / expected_prior - 1,
                                        places=12,
                                    )
                            if count < 20 or missing_last_session:
                                self.assertIsNone(
                                    features["front_realized_volatility_20_annualized"]
                                )
                                self.assertIsNone(
                                    features["front_max_abs_log_return_20"]
                                )
                            else:
                                closes = [6.0 + i / 100 for i in range(20)] + [7.7]
                                log_returns = [
                                    math.log(closes[i] / closes[i - 1])
                                    for i in range(1, len(closes))
                                ]
                                mean = sum(log_returns) / 20
                                sample_variance = sum(
                                    (value - mean) ** 2 for value in log_returns
                                ) / 19
                                self.assertAlmostEqual(
                                    features["front_realized_volatility_20_annualized"],
                                    math.sqrt(sample_variance) * math.sqrt(252),
                                    places=12,
                                )
                                self.assertAlmostEqual(
                                    features["front_max_abs_log_return_20"],
                                    max(abs(value) for value in log_returns),
                                    places=12,
                                )

    def test_parquet_result_cardinality_fails_closed(self):
        import duckdb

        with (
            duckdb.connect(database=":memory:") as connection,
            self.assertRaisesRegex(MarketTruthError, "exceeds row limit"),
        ):
            MarketTruthDataset._select(
                connection,
                "SELECT value FROM generate_series(0, 200) AS data(value)",
                [], limit=12,
            )

    def test_rebuild_is_bitwise_deterministic_and_audited(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            counts = {"definitions": 3, "bars": 3, "statistics": 3}
            one = publish_parquet(
                store(),
                root / "build1",
                source_counts=counts,
                config_sha256={"platform": "b" * 64},
            )
            two = publish_parquet(
                store(),
                root / "build2",
                source_counts=counts,
                config_sha256={"platform": "b" * 64},
            )
            self.assertEqual(one["content_sha256"], two["content_sha256"])
            self.assertEqual(one["tables"], two["tables"])
            self.assertEqual(one["config_sha256"]["platform"], "b" * 64)
            self.assertEqual(one["source_row_reconciliation"]["bars"]["source_rows"], 3)
            self.assertEqual(
                set(one["transform_sha256"]),
                {"core.py", "ng.py", "query.py", "protected_reads.py", "revision.py", "errors.py"}
            )

    def test_missing_and_explicit_null_revisions_have_same_eager_streaming_rejection(self):
        import sqlite3

        from commodity.market_truth.revision import (
            REVISION_GRAINS,
            canonicalize_versions,
        )
        from commodity.market_truth.streaming import _flush_batch, _staging_record

        earlier = {
            "instrument_id": "110",
            "trade_date": "2022-05-10",
            "stat_type": "settle",
            "available_at": "2022-05-10T21:00:00+00:00",
            "event_at": "2022-05-10T20:00:00+00:00",
            "evidence_id": "a" * 64,
            "source_vintage_id": None,
            "value": 7.7,
        }
        missing = dict(
            earlier,
            event_at="2022-05-10T20:00:01+00:00",
            evidence_id="b" * 64,
        )
        missing.pop("source_vintage_id")
        with self.assertRaisesRegex(MarketTruthError, "ambiguous statistic revision"):
            canonicalize_versions(
                [earlier, missing], REVISION_GRAINS["statistics"], "statistic"
            )
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                "CREATE TABLE statistics (grain TEXT NOT NULL, "
                "available_at TEXT NOT NULL, evidence_id TEXT NOT NULL, "
                "payload TEXT NOT NULL, CHECK(length(evidence_id)=64), "
                "PRIMARY KEY(grain, available_at)) WITHOUT ROWID"
            )
            with self.assertRaisesRegex(MarketTruthError, "ambiguous statistic revision"):
                _flush_batch(
                    connection,
                    "statistics",
                    [_staging_record("statistics", item) for item in (earlier, missing)],
                )

    def test_same_clock_equivalent_statistic_event_retransmissions(self):
        definitions, bars, statistics = fixtures()
        repeated = dict(
            statistics[0], ts_event="2022-05-10T20:00:01Z"
        )
        first = build_market_truth(definitions, bars, [*statistics, repeated])
        second = build_market_truth(definitions, bars, [repeated, *statistics])
        self.assertEqual(first["statistics"], second["statistics"])
        self.assertEqual(len(first["statistics"]), 2)
        self.assertEqual(
            first["statistics"][0]["event_at"],
            "2022-05-10T20:00:00+00:00",
        )
        with self.assertRaisesRegex(MarketTruthError, "ambiguous statistic revision"):
            build_market_truth(
                definitions, bars,
                [*statistics, dict(repeated, price=999.0)],
            )

    def test_retransmissions_deduplicate_exact_bytes(self):
        definitions, bars, stats = fixtures()
        found = build_market_truth(definitions, [*bars, copy.copy(bars[0])], stats)
        self.assertEqual(len(found["bars"]), len(bars))




def _streaming_input_manifest(root: Path, families: dict) -> Path:
    """Small approved synthetic manifest with per-family byte and row identities."""
    from scripts.data import build_ng_market_truth as pipeline

    inputs = {}
    for name, rows in families.items():
        path = root / f"{name}.csv"
        headers = sorted({field for row in rows for field in row})
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        inputs[name] = {
            "schema": pipeline.SCHEMAS[name],
            "relative_path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "row_count": len(rows),
        }
    manifest = root / "source_manifest.json"
    manifest.write_text(
        json.dumps({
            "schema_version": 1,
            "evidence_class": "development",
            "protected_confirmation_accessed": False,
            "dataset": "GLBX.MDP3",
            "product_code": "NG",
            "max_trade_date": "2022-05-10",
            "inputs": inputs,
        }),
        encoding="utf-8",
    )
    return manifest


class StreamingMarketTruthTests(OwnerApprovalTestCase):
    def setUp(self):
        if os.name != "nt":
            guard = patch.object(
                market_truth_query, "protected_table_reads",
                lambda files: nullcontext(),
            )
            guard.start()
            self.addCleanup(guard.stop)

    def test_streaming_matches_eager_snapshots_and_revision_selection(self):
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, stats = fixtures()
        bars.append(dict(bars[0], close=7.9, available_at="2022-05-11T08:00:00Z",
                         ts_event="2022-05-11T07:00:00Z"))
        stats.append(dict(stats[0], price=8.1, ts_event="2022-05-11T08:00:00Z",
                          ts_recv="2022-05-11T08:00:01Z"))
        families = {"definitions": definitions, "bars": bars, "statistics": stats}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(root, families)
            with patch.object(pipeline, "ALLOWED_INPUT_ROOT", root):
                eager = pipeline.build_from_manifest(manifest, root / "eager")
                streamed = pipeline.build_from_manifest(
                    manifest, root / "streamed", streaming=True
                )
            self.assertEqual(
                eager["source_row_reconciliation"], streamed["source_row_reconciliation"]
            )
            self.assertEqual(
                {name: eager["tables"][name]["rows"] for name in families},
                {name: streamed["tables"][name]["rows"] for name in families},
            )
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                eager_reader = MarketTruthDataset(
                    root / "eager", expected_content_sha256=eager["content_sha256"]
                )
                streamed_reader = MarketTruthDataset(
                    root / "streamed", expected_content_sha256=streamed["content_sha256"]
                )
            for cutoff in (QUERY, "2022-05-11T09:00:00Z"):
                baseline = eager_reader.snapshot("2022-05-10", cutoff)
                candidate = streamed_reader.snapshot("2022-05-10", cutoff)
                for key in ("features", "roll_transition", "feature_warmup"):
                    self.assertEqual(candidate[key], baseline[key])
                self.assertEqual(candidate["curve_points"], baseline["curve_points"])
            self.assertEqual(streamed["dataset_scope"], "development_pre2023")
            self.assertFalse(streamed["protected_confirmation_accessed"])
            self.assertEqual(
                json.loads((root / "streamed" / "manifest.json").read_text(
                    encoding="utf-8"
                )),
                streamed,
            )
            self.assertIn("streaming.py", streamed["transform_sha256"])

    def test_streaming_deduplicates_same_clock_equivalent_event_revisions(self):
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, stats = fixtures()
        duplicate = dict(stats[0], ts_event="2022-05-10T20:00:01Z")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(
                root, {
                    "definitions": definitions, "bars": bars,
                    "statistics": [duplicate, *stats],
                }
            )
            with patch.object(pipeline, "ALLOWED_INPUT_ROOT", root):
                eager = pipeline.build_from_manifest(manifest, root / "eager")
                streamed = pipeline.build_from_manifest(
                    manifest, root / "streamed", streaming=True
                )
            self.assertEqual(
                eager["tables"]["statistics"]["rows"],
                streamed["tables"]["statistics"]["rows"],
            )
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                expected = MarketTruthDataset(
                    root / "eager", expected_content_sha256=eager["content_sha256"]
                ).snapshot("2022-05-10", QUERY)
                actual = MarketTruthDataset(
                    root / "streamed",
                    expected_content_sha256=streamed["content_sha256"],
                ).snapshot("2022-05-10", QUERY)
            self.assertEqual(actual["curve_points"], expected["curve_points"])

    def test_streaming_rejects_same_clock_conflicting_revisions_without_output(self):
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, stats = fixtures()
        bars.append(dict(bars[0], close=7.4))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(
                root, {"definitions": definitions, "bars": bars, "statistics": stats}
            )
            with (
                patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                self.assertRaisesRegex(MarketTruthError, "ambiguous bar revision"),
            ):
                pipeline.build_from_manifest(manifest, root / "failed", streaming=True)
            self.assertFalse((root / "failed").exists())
            self.assertFalse(list(root.glob(".market-truth-build-*")))

    def test_streaming_writer_rejects_unattested_governance_before_io(self):
        from commodity.market_truth.attestation import SourceBuildAttestation
        from commodity.market_truth.streaming import build_streaming_parquet

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "must-not-exist"
            manifest = root / "manifest.json"
            manifest.write_bytes(b"independent-source-manifest")
            source_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            for forged in ({}, None, "development_pre2023"):
                with self.subTest(forged=forged), self.assertRaisesRegex(
                    MarketTruthError, "governance attestation required"
                ):
                    build_streaming_parquet(
                        {}, {}, output, source_manifest_path=manifest,
                        config_sha256={}, normalize_row=lambda name, row: row,
                        governance=forged,
                    )
                self.assertFalse(output.exists())
            wrong = SourceBuildAttestation(
                dataset_scope="development_pre2023",
                protected_confirmation_accessed=False,
                source_manifest_sha256="a" * 64,
            )
            with self.assertRaisesRegex(MarketTruthError, "manifest hash mismatch"):
                build_streaming_parquet(
                    {}, {}, output, source_manifest_path=manifest,
                    config_sha256={}, normalize_row=lambda name, row: row,
                    governance=wrong,
                )
            self.assertFalse(output.exists())
            # Only the trusted manifest owner, not the generic writer, decides
            # whether a given evidence scope is permitted for a research dataset.
            other_scope = SourceBuildAttestation(
                dataset_scope="other_scope",
                protected_confirmation_accessed=True,
                source_manifest_sha256=source_digest,
            )
            self.assertEqual(other_scope.dataset_scope, "other_scope")

    def test_generic_streaming_writer_cannot_mint_source_owner_scope(self):
        from commodity.market_truth.attestation import SourceBuildAttestation
        from commodity.market_truth.ng import normalize_ng_databento_record
        from commodity.market_truth.streaming import build_streaming_parquet

        definitions, bars, statistics = fixtures()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(root, {
                "definitions": definitions, "bars": bars, "statistics": statistics,
            })
            declaration = json.loads(manifest.read_text(encoding="utf-8"))
            candidate = build_streaming_parquet(
                {name: root / declaration["inputs"][name]["relative_path"]
                 for name in ("definitions", "bars", "statistics")},
                declaration["inputs"], root / "untrusted-candidate",
                source_manifest_path=manifest, config_sha256={},
                normalize_row=normalize_ng_databento_record,
                governance=SourceBuildAttestation(
                    dataset_scope="protected_confirmation",
                    protected_confirmation_accessed=True,
                    source_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                ),
            )
            # Caller-controlled metadata is structurally valid but cannot
            # publish either development admission or protected-data claims.
            for key in ("dataset_scope", "protected_confirmation_accessed"):
                self.assertNotIn(key, candidate)
                self.assertNotIn(key, json.loads(
                    (root / "untrusted-candidate" / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                ))
            with (
                patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root),
                self.assertRaisesRegex(MarketTruthError, "invalid development dataset manifest"),
            ):
                MarketTruthDataset(
                    root / "untrusted-candidate",
                    expected_content_sha256=candidate["content_sha256"],
                )

    def test_streaming_rejects_unsupported_atomic_publication_before_ingestion(self):
        from commodity.market_truth import streaming as engine
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, statistics = fixtures()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(root, {
                "definitions": definitions, "bars": bars, "statistics": statistics,
            })
            for destination in (root / "never", root / "nested" / "more" / "never"):
                with (
                    self.subTest(destination=destination),
                    patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                    patch.object(pipeline, "_publish_no_replace", side_effect=MarketTruthError(
                        "atomic no-replace dataset publication unavailable"
                    )),
                    patch.object(engine, "build_streaming_parquet",
                                 side_effect=AssertionError("ingestion must not begin")),
                    self.assertRaisesRegex(MarketTruthError, "atomic no-replace"),
                ):
                    pipeline.build_from_manifest(manifest, destination, streaming=True)
                self.assertFalse(destination.exists())
                self.assertFalse((root / "nested").exists())
                self.assertFalse(list(root.glob(".market-truth-atomic-probe-*")))

    def test_private_stage_preserves_retargeted_replacement(self):
        from scripts.data import build_ng_market_truth as pipeline

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with pipeline._private_stage(root, prefix="stage-") as stage:
                (stage / "original").write_text("also preserved", encoding="utf-8")
                relocated = root / "relocated"
                stage.rename(relocated)
                stage.mkdir()
                sentinel = stage / "unrelated"
                sentinel.write_text("must survive", encoding="utf-8")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "must survive")
            self.assertEqual((relocated / "original").read_text(
                encoding="utf-8"), "also preserved")

    def test_private_stage_keeps_empty_replacement(self):
        from scripts.data import build_ng_market_truth as pipeline

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with pipeline._private_stage(root, prefix="stage-") as stage:
                relocated = root / "original-stage"
                stage.rename(relocated)
                stage.mkdir()
            self.assertTrue(stage.is_dir())
            self.assertTrue(relocated.is_dir())

    def test_private_stage_reports_and_preserves_partial_failure(self):
        from scripts.data import build_ng_market_truth as pipeline

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = io.StringIO()
            with (
                redirect_stderr(report),
                self.assertRaisesRegex(MarketTruthError, "interrupted"),
                pipeline._private_stage(root, prefix="stage-") as stage,
            ):
                partial = stage / "candidate"
                partial.mkdir()
                (partial / "incomplete").write_text("recoverable", encoding="utf-8")
                raise MarketTruthError("interrupted")
            self.assertEqual((partial / "incomplete").read_text(
                encoding="utf-8"), "recoverable")
            self.assertIn(f"MARKET_TRUTH_STAGE_RETAINED: {stage}", report.getvalue())

    def test_owner_atomic_publication_never_replaces_existing_directory(self):
        from scripts.data import build_ng_market_truth as pipeline

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "content").write_text("candidate", encoding="utf-8")
            occupied = root / "occupied"
            occupied.mkdir()
            (occupied / "keep").write_text("original", encoding="utf-8")
            if os.name == "nt":
                with self.assertRaises(FileExistsError):
                    pipeline._publish_no_replace(candidate, occupied)
            else:
                with self.assertRaisesRegex(MarketTruthError, "refusing overwrite"):
                    pipeline._publish_no_replace(candidate, occupied)
            self.assertEqual(
                (occupied / "keep").read_text(encoding="utf-8"), "original"
            )
            self.assertTrue(candidate.is_dir())
            destination = root / "available"
            pipeline._publish_no_replace(candidate, destination)
            self.assertFalse(candidate.exists())
            self.assertEqual(
                (destination / "content").read_text(encoding="utf-8"), "candidate"
            )

    def test_linux_publication_rejects_retargeted_parent(self):
        from scripts.data import build_ng_market_truth as pipeline

        if os.name == "nt":
            self.skipTest("Linux kernel directory-descriptor publication only")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_parent = root / "source"
            source_parent.mkdir()
            candidate = source_parent / "candidate"
            candidate.mkdir()
            dest_parent = root / "destination"
            dest_parent.mkdir()
            relocated = root / "relocated"
            native_open = os.open

            def replace_after_open(path, flags):
                descriptor = native_open(path, flags)
                if Path(path) == dest_parent:
                    dest_parent.rename(relocated)
                    dest_parent.mkdir()
                return descriptor

            with (
                patch.object(pipeline.os, "open", replace_after_open),
                self.assertRaisesRegex(MarketTruthError, "publication parent changed"),
            ):
                pipeline._publish_no_replace(candidate, dest_parent / "published")
            self.assertTrue(candidate.is_dir())
            self.assertFalse((dest_parent / "published").exists())
            self.assertFalse((relocated / "published").exists())

    def test_linux_publication_rolls_back_parent_swap_after_rename(self):
        from scripts.data import build_ng_market_truth as pipeline

        if os.name == "nt":
            self.skipTest("Linux kernel directory-descriptor publication only")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_parent = root / "source"
            source_parent.mkdir()
            candidate = source_parent / "candidate"
            candidate.mkdir()
            (candidate / "identity").write_text("preserved", encoding="utf-8")
            dest_parent = root / "destination"
            dest_parent.mkdir()
            relocated = root / "relocated"
            original_stat = os.stat
            destination_checks = [0]

            def swap_after_initial_check(path, *args, **kwargs):
                if Path(path) == dest_parent:
                    destination_checks[0] += 1
                    if destination_checks[0] == 2:
                        dest_parent.rename(relocated)
                        dest_parent.mkdir()
                return original_stat(path, *args, **kwargs)

            with (
                patch.object(pipeline.os, "stat", swap_after_initial_check),
                self.assertRaisesRegex(MarketTruthError, "parent changed; rolled back"),
            ):
                pipeline._publish_no_replace(candidate, dest_parent / "published")
            self.assertEqual(destination_checks[0], 2)
            self.assertEqual((candidate / "identity").read_text(encoding="utf-8"),
                             "preserved")
            self.assertFalse((dest_parent / "published").exists())
            self.assertFalse((relocated / "published").exists())

    def test_linux_publication_rolls_back_source_parent_swap_after_rename(self):
        from scripts.data import build_ng_market_truth as pipeline

        if sys.platform != "linux":
            self.skipTest("Linux kernel directory-descriptor publication only")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_parent = root / "source"
            source_parent.mkdir()
            candidate = source_parent / "candidate"
            candidate.mkdir()
            (candidate / "identity").write_text("preserved", encoding="utf-8")
            destination = root / "published"
            relocated = root / "relocated"
            from types import SimpleNamespace

            native_rename = pipeline.ctypes.CDLL(None, use_errno=True).renameat2
            native_rename.argtypes = (
                pipeline.ctypes.c_int, pipeline.ctypes.c_char_p,
                pipeline.ctypes.c_int, pipeline.ctypes.c_char_p,
                pipeline.ctypes.c_uint,
            )
            native_rename.restype = pipeline.ctypes.c_int
            calls = [0]

            class RenameWithSourceSwap:
                def __call__(self, *args):
                    result = native_rename(*args)
                    calls[0] += 1
                    if calls[0] == 1 and result == 0:
                        source_parent.rename(relocated)
                        source_parent.mkdir()
                        (source_parent / "unrelated").write_text("safe", encoding="utf-8")
                    return result

            with (
                patch.object(pipeline.ctypes, "CDLL", return_value=SimpleNamespace(
                    renameat2=RenameWithSourceSwap())),
                self.assertRaisesRegex(MarketTruthError, "parent changed; rolled back"),
            ):
                pipeline._publish_no_replace(candidate, destination)
            self.assertEqual(calls[0], 2)
            self.assertFalse(destination.exists())
            self.assertEqual((relocated / "candidate" / "identity").read_text(
                encoding="utf-8"), "preserved")
            self.assertEqual((source_parent / "unrelated").read_text(
                encoding="utf-8"), "safe")

    def test_streaming_owner_rejects_forged_candidate_and_manifest_mutation(self):
        from commodity.market_truth import streaming as engine
        from scripts.data import build_ng_market_truth as pipeline

        for scenario, diagnostic in (
            ("forged_scope", "generic transform cannot assert source authority"),
            ("forged_protected", "generic transform cannot assert source authority"),
            ("changed_manifest", "source manifest mutated during build"),
            ("protected_source_manifest", "protected evidence flag must be explicit false"),
        ):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                definitions, bars, statistics = fixtures()
                manifest = _streaming_input_manifest(root, {
                    "definitions": definitions, "bars": bars, "statistics": statistics,
                })
                if scenario == "protected_source_manifest":
                    source = json.loads(manifest.read_text(encoding="utf-8"))
                    source["protected_confirmation_accessed"] = True
                    manifest.write_text(json.dumps(source), encoding="utf-8")
                real_builder = engine.build_streaming_parquet

                def manipulated_builder(*args, _scenario=scenario,
                                        _real_builder=real_builder,
                                        _manifest=manifest, **kwargs):
                    candidate = _real_builder(*args, **kwargs)
                    if _scenario == "forged_scope":
                        candidate["dataset_scope"] = "development_pre2023"
                    elif _scenario == "forged_protected":
                        candidate["protected_confirmation_accessed"] = False
                    else:
                        _manifest.write_bytes(_manifest.read_bytes() + b" ")
                    return candidate

                with (
                    patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                    patch.object(engine, "build_streaming_parquet", manipulated_builder),
                    self.assertRaisesRegex(MarketTruthError, diagnostic),
                ):
                    pipeline.build_from_manifest(manifest, root / "unpublished", streaming=True)
                self.assertFalse((root / "unpublished").exists())
                retained = list(root.glob(".market-truth-owner-*"))
                if scenario == "protected_source_manifest":
                    self.assertEqual(retained, [])
                else:
                    self.assertEqual(len(retained), 1)
                    self.assertTrue((retained[0] / "candidate" / "manifest.json").is_file())

    def test_streaming_rejects_malformed_csv_rows_and_headers_like_eager(self):
        from scripts.data import build_ng_market_truth as pipeline

        families = dict(zip(
            ("definitions", "bars", "statistics"), fixtures(), strict=True
        ))
        expected_messages = {
            "short_row": ("malformed checked CSV record", "CSV row does not match declared columns"),
            "extra_column": ("malformed checked CSV record", "CSV row does not match declared columns"),
            "whitespace_header": ("missing or duplicate checked CSV headers", "missing or duplicate CSV headers"),
            "duplicate_header": ("missing or duplicate checked CSV headers", "missing or duplicate CSV headers"),
            "blank_header": ("missing or duplicate checked CSV headers", "missing or duplicate CSV headers"),
            "unterminated_quote": ("invalid checked source CSV encoding or format", "invalid or oversized CSV field"),
        }
        for case in expected_messages:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                manifest = _streaming_input_manifest(root, families)
                path = root / "bars.csv"
                lines = path.read_bytes().splitlines()
                if case == "short_row":
                    lines[1] = b",".join(lines[1].split(b",")[:-1])
                elif case == "extra_column":
                    lines[1] += b",unexpected"
                elif case == "whitespace_header":
                    lines[0] = b" " + lines[0]
                elif case == "duplicate_header":
                    header = lines[0].split(b",")
                    header[-1] = header[0]
                    lines[0] = b",".join(header)
                elif case == "blank_header":
                    header = lines[0].split(b",")
                    header[0] = b" "
                    lines[0] = b",".join(header)
                else:
                    lines[1] = b'"unterminated'
                path.write_bytes(b"\n".join(lines) + b"\n")
                source_manifest = json.loads(manifest.read_text(encoding="utf-8"))
                source_manifest["inputs"]["bars"]["sha256"] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                manifest.write_text(
                    json.dumps(source_manifest), encoding="utf-8"
                )
                for streaming in (False, True):
                    rejected = root / ("rejected-streaming" if streaming else "rejected-eager")
                    with (
                        self.subTest(streaming=streaming),
                        patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                        self.assertRaisesRegex(
                            MarketTruthError, expected_messages[case][int(streaming)]
                        ),
                    ):
                        pipeline.build_from_manifest(
                            manifest, rejected, streaming=streaming
                        )
                    self.assertFalse(rejected.exists())

    def test_large_csv_automatically_uses_streaming_without_eager_reader(self):
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, stats = fixtures()
        wide_row = dict(bars[0], unused_padding="x" * 9000)
        bars[0] = wide_row
        oversized = [*bars, *[wide_row] * 2100]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(
                root, {
                    "definitions": definitions, "bars": oversized,
                    "statistics": stats,
                }
            )
            self.assertGreater(
                (root / "bars.csv").stat().st_size,
                pipeline.MAX_EAGER_CSV_BYTES,
            )
            with (
                patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                patch.object(
                    pipeline, "_read_checked_csv",
                    side_effect=AssertionError("eager materialization prohibited"),
                ),
            ):
                metadata = pipeline.build_from_manifest(manifest, root / "large")
            self.assertEqual(metadata["tables"]["bars"]["rows"], 3)
            self.assertEqual(
                metadata["source_row_reconciliation"]["bars"]["source_rows"],
                len(oversized),
            )
            self.assertEqual(
                metadata["source_row_reconciliation"]["bars"][
                    "excluded_or_exact_retransmissions"
                ],
                len(oversized) - 3,
            )
            with patch.object(market_truth_query, "DEFAULT_APPROVED_ROOT", root), _fixture_approval(root):
                reader = MarketTruthDataset(
                    root / "large",
                    expected_content_sha256=metadata["content_sha256"],
                )
            self.assertAlmostEqual(
                reader.snapshot("2022-05-10", QUERY)["features"]["front_price"],
                7.7,
            )

    def test_streaming_rejects_post2022_rows_despite_older_source_attestation(self):
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, stats = fixtures()
        bars[0]["trade_date"] = "2023-01-02"
        bars[0]["ts_event"] = "2023-01-02T20:00:00Z"
        bars[0]["available_at"] = "2023-01-02T23:59:00Z"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(
                root, {"definitions": definitions, "bars": bars, "statistics": stats}
            )
            with (
                patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                self.assertRaisesRegex(MarketTruthError, "protected_confirmation"),
            ):
                pipeline.build_from_manifest(manifest, root / "denied", streaming=True)
            self.assertFalse((root / "denied").exists())

    def test_streaming_flushes_large_valid_rows_at_byte_budget(self):
        from commodity.market_truth import streaming as streamed_module
        from scripts.data import build_ng_market_truth as pipeline

        definitions, bars, stats = fixtures()
        width = "v" * 200_000
        for day_index in range(70):
            day = date(2022, 6, 1) + timedelta(days=day_index)
            stamp = day.isoformat()
            bars.append(
                dict(
                    bars[0],
                    trade_date=stamp,
                    ts_event=stamp + "T20:00:00Z",
                    available_at=stamp + "T23:59:00Z",
                    source_vintage_id=width,
                )
            )
        sizes = []
        actual_flush = streamed_module._flush_batch

        def observed_flush(connection, family, batch):
            if batch and family == "bars":
                total = sum(sum(len(part) for part in row) for row in batch)
                sizes.append(total)
                self.assertLessEqual(total, streamed_module.MAX_BATCH_BYTES)
            return actual_flush(connection, family, batch)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = _streaming_input_manifest(
                root, {"definitions": definitions, "bars": bars, "statistics": stats}
            )
            with (
                patch.object(pipeline, "ALLOWED_INPUT_ROOT", root),
                patch.object(streamed_module, "_flush_batch", side_effect=observed_flush),
            ):
                metadata = pipeline.build_from_manifest(
                    manifest, root / "bounded", streaming=True
                )
            self.assertGreaterEqual(len([size for size in sizes if size]), 2)
            self.assertEqual(metadata["tables"]["bars"]["rows"], len(bars))
            self.assertEqual(
                {path.name for path in (root / "bounded").iterdir()},
                {"definitions.parquet", "bars.parquet", "statistics.parquet", "manifest.json"},
            )

if __name__ == "__main__":
    unittest.main()
