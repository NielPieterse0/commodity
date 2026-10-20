"""NG-specific acceptance tests for previously unguarded expiry decisions."""
from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from commodity.market_truth import MarketTruthError, ng_expiry
from commodity.market_truth.ng import ng_curve_asof, ng_snapshot_asof
from commodity.market_truth.query import MarketTruthDataset

AFFECTED = {
    "venue": "NYMEX", "symbol": "NGM2", "instrument_id": "a",
    "expiration": "2022-05-26T18:30:00+00:00",
    "last_trade_at": None,
    "available_at": "2022-04-01T00:00:00+00:00",
    "evidence_id": "source-a",
}
SAFE = {
    **AFFECTED, "symbol": "NGN2", "instrument_id": "b",
    "expiration": "2022-06-27T18:30:00+00:00",
    "last_trade_at": "2022-06-27T18:30:00+00:00",
    "evidence_id": "source-b",
}
BAR = {
    "instrument_id": "a", "trade_date": "2022-05-10",
    "available_at": "2022-05-10T18:00:00+00:00",
    "evidence_id": "bar-a", "open": 7.0, "high": 8.0,
    "low": 6.0, "close": 7.5, "volume": 100,
}

class NGExpiryFenceTests(unittest.TestCase):
    def test_hash_pinned_cohort_fences_all_14_terminal_windows(self):
        ng_expiry.verify_ng_expiry_policy()
        self.assertEqual(len(ng_expiry.UNQUALIFIED_NG_EXPIRIES), 14)
        for symbol, expiration in sorted(ng_expiry.UNQUALIFIED_NG_EXPIRIES):
            expiry = datetime.fromisoformat(expiration)
            row = {
                **AFFECTED, "symbol": symbol, "expiration": expiration,
                "available_at": (expiry - timedelta(days=30)).isoformat(),
            }
            for offset in (-7, 0, 7):
                cutoff = expiry + timedelta(days=offset)
                with self.subTest(symbol=symbol, expiration=expiration,
                                  offset=offset), self.assertRaisesRegex(
                    MarketTruthError, "unverified CME historical expiry"
                ):
                    ng_expiry.fence_ng_expiry_definitions([row], cutoff)

    def test_absent_or_mutated_release_policy_fails_closed(self):
        for replaced in (frozenset(), frozenset({("NGM2", AFFECTED["expiration"])}), None):
            with self.subTest(replaced=replaced), patch.object(
                ng_expiry, "UNQUALIFIED_NG_EXPIRIES", replaced
            ), self.assertRaisesRegex(
                MarketTruthError, "exclusion policy missing or modified"
            ):
                # No input contract can bypass release policy integrity.
                ng_expiry.fence_ng_expiry_definitions([], datetime(2022, 5, 26, tzinfo=UTC))

    def test_block_both_sides_of_unqualified_expiry(self):
        store = {"definitions": [AFFECTED, SAFE], "bars": [], "statistics": []}
        for moment in (
            "2022-05-19T16:00:00+00:00",
            "2022-05-26T16:00:00+00:00",
            "2022-05-30T16:00:00+00:00",
        ):
            with self.subTest(moment=moment), self.assertRaisesRegex(
                MarketTruthError, "unverified CME historical expiry"
            ):
                ng_curve_asof(store, moment[:10], moment)

    def test_outside_window_preserves_price_but_nulls_expiry_features(self):
        store = {"definitions": [AFFECTED, SAFE], "bars": [BAR], "statistics": []}
        curve = ng_curve_asof(store, "2022-05-10", "2022-05-10T20:00:00Z")
        self.assertEqual(BAR["close"], 7.5)
        self.assertEqual(BAR["volume"], 100)
        self.assertIsNone(curve[0]["close"])
        self.assertIsNone(curve[0]["volume"])
        self.assertEqual(curve[0]["rank_boundary_status"],
                         "unverified_exchange_expiry_rank")
        self.assertIsNone(curve[0]["days_to_expiry"])
        result = ng_snapshot_asof(store, "2022-05-10", "2022-05-10T20:00:00Z")
        self.assertIsNone(result["features"]["front_price"])
        self.assertIsNone(result["features"]["front_volume"])
        self.assertIsNone(result["features"]["front_days_to_expiry"])
        self.assertIsNone(result["features"]["m1_m2_annualized_carry_proxy"])
        self.assertIsNone(result["features"]["winter_minus_summer_strip"])
        self.assertIsNone(result["roll_transition"]["observed"])
        self.assertEqual(result["curve_points"][0]["rank_boundary_status"],
                         "unverified_exchange_expiry_rank")
        self.assertIsNone(result["curve_points"][0]["contract_identity"])
        self.assertIsNone(result["curve_points"][0]["close"])
        self.assertEqual(result["curve_points"][0]["evidence_ids"], [])

    def test_only_rank_prefix_is_model_visible_outside_terminal_fence(self):
        cutoff = "2019-11-15T20:00:00+00:00"
        early = {
            **SAFE, "symbol": "NGX9", "instrument_id": "earlier",
            "expiration": "2019-11-20T19:30:00+00:00",
            "last_trade_at": "2019-11-20T19:30:00+00:00",
            "available_at": "2019-10-01T00:00:00+00:00",
        }
        disputed = {
            **AFFECTED, "symbol": "NGZ9", "instrument_id": "disputed",
            "expiration": "2019-11-26T19:30:00+00:00",
            "available_at": "2019-10-01T00:00:00+00:00",
        }
        later = {
            **SAFE, "symbol": "NGF0", "instrument_id": "later",
            "expiration": "2019-12-27T19:30:00+00:00",
            "last_trade_at": "2019-12-27T19:30:00+00:00",
            "available_at": "2019-10-01T00:00:00+00:00",
        }
        bars = [
            {**BAR, "instrument_id": instrument, "trade_date": "2019-11-15",
             "available_at": "2019-11-15T18:00:00+00:00", "close": price}
            for instrument, price in (
                ("earlier", 2.0), ("disputed", 2.5), ("later", 3.0)
            )
        ]
        store = {"definitions": [early, disputed, later],
                 "bars": bars, "statistics": []}
        self.assertEqual([p["close"] for p in store["bars"]], [2.0, 2.5, 3.0])
        safe_curve = ng_curve_asof(store, "2019-11-15", cutoff)
        self.assertEqual([p["close"] for p in safe_curve[:3]], [2.0, None, None])
        snapshot = ng_snapshot_asof(store, "2019-11-15", cutoff)
        points = snapshot["curve_points"]
        self.assertEqual(points[0]["close"], 2.0)
        self.assertEqual(points[0]["contract_symbol"], "NGX9")
        for point in points[1:3]:
            self.assertIsNone(point["close"])
            self.assertIsNone(point["contract_identity"])
            self.assertIsNone(point["expiration"])
            self.assertEqual(point["missing_reason"],
                             "unverified_exchange_expiry_rank")
        self.assertEqual(snapshot["features"]["front_price"], 2.0)
        self.assertIsNone(snapshot["features"]["m1_m2_spread_price_per_unit"])
        self.assertIsNone(snapshot["features"]["curve_mean_price_per_unit"])
        self.assertIsNone(snapshot["features"]["winter_minus_summer_strip"])
        self.assertIsNone(snapshot["features"]["winter_strip_contracts"])
        self.assertIsNone(snapshot["features"]["summer_strip_contracts"])
        self.assertEqual(snapshot["features"]["available_curve_slots"], 1)

    def test_every_rank_position_masks_entire_suffix_without_raw_mutation(self):
        """All twelve M1..M12 taint positions share the same model boundary."""
        for tainted_rank in range(1, 13):
            raw = [
                {
                    "rank": rank,
                    "rank_boundary_status": (
                        "unverified_exchange_expiry"
                        if rank == tainted_rank else "verified_last_trade"
                    ),
                    "instrument_id": f"id-{rank}",
                    "venue": "NYMEX",
                    "contract_identity": f"NYMEX:NG{rank}:expiry",
                    "contract_symbol": f"NG{rank}",
                    "expiration": "2022-12-01T00:00:00+00:00",
                    "last_trade_at": "2022-12-01T00:00:00+00:00",
                    "days_to_expiry": 30,
                    "open": 2.0, "high": 3.0, "low": 1.0, "close": 2.5,
                    "volume": 100, "settle": 2.5,
                    "open_interest": 1000, "cleared_volume": 200,
                    "available_at": "2022-05-10T00:00:00+00:00",
                    "evidence_ids": [f"e-{rank}"],
                    "last_trade_verified": True,
                    "missing_reason": "none",
                }
                for rank in range(1, 13)
            ]
            protected = ng_expiry.model_safe_ng_curve(raw)
            with self.subTest(tainted_rank=tainted_rank):
                self.assertEqual(len(protected), 12)
                for rank, point in enumerate(protected, 1):
                    if rank < tainted_rank:
                        self.assertEqual(point, raw[rank - 1])
                    else:
                        for name in ("instrument_id", "contract_identity",
                                     "expiration", "close", "volume",
                                     "settle", "open_interest"):
                            self.assertIsNone(point[name])
                        self.assertEqual(point["evidence_ids"], [])
                        self.assertEqual(point["rank_boundary_status"],
                                         "unverified_exchange_expiry_rank")
                self.assertEqual(raw[tainted_rank - 1]["close"], 2.5)

    def test_all_14_delivery_months_bound_source_pruning(self):
        """Rule 220102.F upper bound excludes any surviving expired candidate."""
        ng_expiry.verify_ng_expiry_policy()
        distances = []
        for symbol, expiration in sorted(ng_expiry.UNQUALIFIED_NG_EXPIRIES):
            expiry = datetime.fromisoformat(expiration)
            delivery = ng_expiry.ng_delivery_month_start(symbol, expiration)
            distance = (delivery - expiry.date()).days
            distances.append(distance)
            self.assertLessEqual(distance, 7)
            self.assertGreater(distance, 0)
            row = {
                **AFFECTED, "symbol": symbol, "expiration": expiration,
                "available_at": (expiry - timedelta(days=30)).isoformat(),
            }
            # All dates from recorded termination until delivery start are
            # guarded, including candidates SQL would otherwise prune.
            for offset in range(distance):
                cutoff = expiry + timedelta(days=offset)
                with self.subTest(symbol=symbol, day=offset), self.assertRaisesRegex(
                    MarketTruthError, "unverified CME historical expiry"
                ):
                    ng_expiry.fence_ng_expiry_definitions([row], cutoff)
            # Beyond the existing conservative terminal fence, official
            # NYMEX rule already prohibits any further trading eligibility.
            late = expiry + timedelta(days=8)
            self.assertGreater(late.date(), delivery)
            observed = ng_expiry.fence_ng_expiry_definitions([row], late)
            self.assertTrue(observed[0]["_expiry_unverified"])
        self.assertEqual(len(distances), 14)

    def test_delivery_bound_or_contract_symbol_corruption_denied(self):
        expiration = AFFECTED["expiration"]
        for invalid in ("NGZ2", "NGM1", "NGM22"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                MarketTruthError, "delivery-month bound"
            ):
                ng_expiry.ng_delivery_month_start(invalid, expiration)
        with (
            patch.object(ng_expiry, "NG_DELIVERY_MONTH_CODES", "Z" * 12),
            self.assertRaisesRegex(
                MarketTruthError, "exclusion policy missing or modified"
            ),
        ):
            ng_expiry.verify_ng_expiry_policy()

    def test_parquet_prefilter_checks_full_cohort_after_prior_expiry(self):
        """SQL inspects pinned source identities outside the old +/-8-day range."""
        try:
            import duckdb
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("requires pinned Parquet runtime")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pq.write_table(
                pa.Table.from_pylist([AFFECTED, SAFE]),
                root / "definitions.parquet",
            )
            reader = object.__new__(MarketTruthDataset)
            reader.files = {"definitions": root / "definitions.parquet"}
            observed = []
            class StopAfterSourceBoundary(Exception):
                pass

            def inspect(connection, statement, params, *, limit):
                if "SELECT DISTINCT venue, symbol, expiration" in statement:
                    observed.append((statement, params))
                    raise StopAfterSourceBoundary
                raise AssertionError("SQL pruned ranks before inspecting source")

            with (
                duckdb.connect(":memory:") as connection,
                patch.object(reader, "_select", side_effect=inspect),
                self.assertRaises(StopAfterSourceBoundary),
            ):
                # The affected May contract has been pruned by source expiry,
                # but its source identity must be checked before rank SQL.
                reader._curve_from_parquet(
                    connection, date(2022, 6, 5),
                    datetime(2022, 6, 5, 20, tzinfo=UTC), 12,
                )
            self.assertEqual(len(observed), 1)
            statement, params = observed[0]
            self.assertIn("symbol IN", statement)
            self.assertNotIn("INTERVAL '8 days'", statement)
            self.assertIn("NGM2", params)

    def test_source_unavailable_at_decision_clock_cannot_poison_rank(self):
        future = {**AFFECTED, "available_at": "2022-06-01T00:00:00Z"}
        store = {"definitions": [future, SAFE], "bars": [], "statistics": []}
        curve = ng_curve_asof(store, "2022-05-26", "2022-05-26T16:00:00Z")
        self.assertEqual(curve[0]["instrument_id"], "b")

    def test_parquet_snapshot_also_masks_unqualified_rank_outputs(self):
        """Exercise the real Parquet V3 snapshot path with test-local admission isolated."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("requires pinned Parquet runtime")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for family, rows in (
                ("definitions", [AFFECTED, SAFE]),
                ("bars", [BAR]),
                ("statistics", [{
                    "instrument_id": "a", "trade_date": "2022-05-10",
                    "stat_type": "open_interest", "value": 1500.0,
                    "available_at": "2022-05-10T18:00:00+00:00",
                    "evidence_id": "oi-a",
                }]),
            ):
                pq.write_table(pa.Table.from_pylist(rows), root / f"{family}.parquet")
            reader = object.__new__(MarketTruthDataset)
            reader.location = root
            reader._approval_catalog_path = root / "synthetic-only.json"
            reader.files = {
                name: root / f"{name}.parquet"
                for name in ("definitions", "bars", "statistics")
            }
            reader.manifest = {"source_sha256": {}, "content_sha256": "f" * 64}
            from commodity.market_truth import query as market_query

            # Isolate admission checks only for this synthetic contract test;
            # no real dataset or owner signature is admitted.
            with (
                patch.object(market_query, "protected_table_reads",
                             lambda files: nullcontext()),
                patch.object(MarketTruthDataset, "_assert_sources_unchanged",
                             lambda self: None),
            ):
                result = reader.snapshot("2022-05-10", "2022-05-10T20:00:00Z")
            eager = ng_snapshot_asof(
                {"definitions": [AFFECTED, SAFE], "bars": [BAR],
                 "statistics": []},
                "2022-05-10", "2022-05-10T20:00:00Z",
            )
            for name in ("front_price", "front_volume",
                         "m1_m2_spread_price_per_unit",
                         "curve_mean_price_per_unit"):
                self.assertIsNone(result["features"][name])
                self.assertEqual(result["features"][name], eager["features"][name])
            self.assertEqual(result["curve_points"][0]["rank_boundary_status"],
                             "unverified_exchange_expiry_rank")
            self.assertIsNone(result["curve_points"][0]["instrument_id"])
            self.assertEqual(result["curve_points"][0]["evidence_ids"], [])

    def test_parquet_guard_catches_contract_pruned_by_expiry_sql(self):
        """A source-expired NG contract must not disappear before the fence."""
        try:
            import duckdb
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("requires pinned Parquet runtime")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pq.write_table(pa.Table.from_pylist([AFFECTED, SAFE]), root / "definitions.parquet")
            reader = object.__new__(MarketTruthDataset)
            reader.files = {"definitions": root / "definitions.parquet"}
            with (
                duckdb.connect(":memory:") as connection,
                self.assertRaisesRegex(
                    MarketTruthError, "unverified CME historical expiry"
                ),
            ):
                reader._curve_from_parquet(
                    connection, date(2022, 5, 30),
                    datetime(2022, 5, 30, 18, tzinfo=UTC), 12,
                )


if __name__ == "__main__":
    unittest.main()
