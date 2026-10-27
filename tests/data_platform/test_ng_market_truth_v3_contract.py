"""Independent synthetic oracle for the Phase 2 V3 snapshot interface.

Only synthetic 2021 data; fixture approval is test-local, not research authority.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from _owner_approval_fixture import sign_fixture_catalog

from commodity.market_truth import (
    MarketTruthDataset,
    MarketTruthError,
    build_market_truth,
    publish_parquet,
    snapshot_asof,
)
from commodity.market_truth import approval as approval_module
from commodity.market_truth import query as market_query

DAY = date(2021, 5, 10)
CUTOFF = "2021-05-10T23:59:30Z"
FEATURE_NAMES = frozenset({
    "front_price", "m1_m2_spread_price_per_unit",
    "m1_m3_slope_per_rank", "m1_m2_m3_curvature",
    "curve_mean_price_per_unit", "available_curve_slots",
    "winter_minus_summer_strip", "winter_strip_contracts",
    "summer_strip_contracts", "m1_m2_annualized_carry_proxy",
    "front_liquidity_volume_oi_ratio",
    "front_realized_volatility_20_annualized",
    "front_max_abs_log_return_20", "session_month",
    "session_weekday", "front_days_to_expiry", "front_volume",
    "front_open_interest", "front_momentum_1", "front_momentum_5",
    "front_momentum_20",
})
WARMUP = {
    "front_momentum_1": 1, "front_momentum_5": 5,
    "front_momentum_20": 20,
    "front_realized_volatility_20_annualized": 20,
    "front_max_abs_log_return_20": 20,
    "winter_minus_summer_strip": "at_least_2_observed_contracts_per_strip",
}
UNITS = {
    "front_price": "quoted_price_per_unit",
    "m1_m2_spread_price_per_unit": "quoted_price_per_unit",
    "m1_m3_slope_per_rank": "quoted_price_per_unit_per_rank",
    "m1_m2_m3_curvature": "quoted_price_per_unit",
    "winter_minus_summer_strip": "quoted_price_per_unit",
    "m1_m2_annualized_carry_proxy": "fraction_per_calendar_year",
    "front_realized_volatility_20_annualized": "annualized_fraction",
}
TOP_LEVEL_KEYS = frozenset({
    "schema_version", "decision_time", "trade_date",
    "protected_confirmation_accessed", "session_history_contract",
    "curve_points", "roll_transition", "features", "feature_warmup",
    "feature_units", "evidence_ids", "source_sha256",
})
PARQUET_ADDITIONAL_KEYS = frozenset({
    "dataset_content_sha256", "dataset_source_sha256",
})
CURVE_POINT_KEYS = frozenset({
    "trade_date", "rank", "instrument_id", "venue", "contract_identity",
    "contract_symbol", "expiration", "last_trade_at", "last_trade_verified",
    "rank_boundary_status", "days_to_expiry", "open", "high", "low",
    "close", "volume", "settle", "open_interest", "cleared_volume",
    "missing_reason", "available_at", "evidence_ids",
})


def _fixture(*, missing_last_prior: bool = False, revisions=None):
    weekdays = [
        DAY - timedelta(days=n)
        for n in range(1, 45)
        if (DAY - timedelta(days=n)).weekday() < 5
    ]
    history = sorted(weekdays[:20])
    assert len(history) == 20
    contracts = []
    expiries = []
    for rank in range(12):
        month_index = 5 + rank
        year = 2021 + month_index // 12
        month = 1 + month_index % 12
        expiry = date(year, month, 25)
        expiries.append(expiry)
        contracts.append({
            "instrument_id": f"NG-{rank:02d}",
            "venue": "NYMEX", "raw_symbol": f"SYN-{rank:02d}",
            "expiration": datetime(year, month, 25, tzinfo=UTC).isoformat(),
            "last_trade_at": (
                datetime.combine(expiry - timedelta(days=1), datetime.min.time(), UTC)
                .replace(hour=20).isoformat() if rank != 2 else None
            ),
            "ts_event": "2021-04-01T12:00:00Z",
            "ts_recv": "2021-04-01T12:00:01Z",
        })
    bars = []
    for rank in range(12):
        price = 3.0 + rank / 10
        bars.append({
            "instrument_id": f"NG-{rank:02d}",
            "trade_date": DAY.isoformat(),
            "ts_event": "2021-05-10T21:00:00Z",
            "available_at": "2021-05-10T23:59:00Z",
            "open": price, "high": price + 0.2,
            "low": price - 0.2, "close": price,
            "volume": 120 + rank,
        })
    for index, day in enumerate(history):
        if missing_last_prior and index == 19:
            continue
        price = 2.4 + index / 50
        bars.append({
            "instrument_id": "NG-00", "trade_date": day.isoformat(),
            "ts_event": day.isoformat() + "T21:00:00Z",
            "available_at": day.isoformat() + "T23:59:00Z",
            "open": price, "high": price + 0.2,
            "low": price - 0.2, "close": price,
            "volume": 90,
        })
    statistics = []
    for rank in range(12):
        statistics.append({
            "instrument_id": f"NG-{rank:02d}",
            "trade_date": DAY.isoformat(), "stat_type": 3,
            "price": 3.1 + rank / 10, "is_final": True,
            "ts_event": "2021-05-10T22:00:00Z",
            "ts_recv": "2021-05-10T22:00:01Z",
        })
    statistics.extend([
        {
            "instrument_id": "NG-00", "trade_date": DAY.isoformat(),
            "stat_type": 9, "quantity": 1000,
            "ts_event": "2021-05-10T22:00:00Z",
            "ts_recv": "2021-05-10T22:00:01Z",
        },
        {
            "instrument_id": "NG-00", "trade_date": DAY.isoformat(),
            "stat_type": 6, "quantity": 0,
            "ts_event": "2021-05-10T22:00:00Z",
            "ts_recv": "2021-05-10T22:00:01Z",
        },
    ])
    statistics.extend(revisions or ())
    store = build_market_truth(
        contracts, bars, statistics,
        source_hashes={part: part[0] * 64 for part in ("definitions", "bars", "statistics")},
    )
    return store, history, expiries


def _read_parquet_snapshot(
    source, history, cutoff=CUTOFF, *, approval_case="approved", isolate_os_guard=True
):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        location = root / "fixture"
        manifest = publish_parquet(source, location)
        approval = {
            "schema_version": 2, "authority": "governed_source_owner_review",
            "datasets": [{
                "content_sha256": manifest["content_sha256"],
                "source_manifest_sha256": manifest.get("source_manifest_sha256"),
                "source_sha256": manifest["source_sha256"],
                "tables_sha256": {
                    part: manifest["tables"][part]["sha256"]
                    for part in ("definitions", "bars", "statistics")
                },
                "source_review_id": "synthetic_fixture_only_not_real_approval",
                "local_evidence_verified": True,
            }],
        }
        catalog = root / "synthetic-only.json"
        assert catalog != market_query.DEFAULT_APPROVAL_CATALOG
        if approval_case == "empty":
            approval["datasets"] = []
        elif approval_case == "wrong_source":
            approval["datasets"][0]["source_sha256"] = {"definitions": "0" * 64}
        elif approval_case == "wrong_table":
            approval["datasets"][0]["tables_sha256"]["bars"] = "0" * 64
        elif approval_case == "wrong_content":
            approval["datasets"][0]["content_sha256"] = "0" * 64
        elif approval_case == "wrong_authority":
            approval["authority"] = "caller_self_approved"
        elif approval_case not in {"approved", "missing_catalog"}:
            raise AssertionError("unexpected synthetic approval test case")
        trusted = {}
        if approval_case != "missing_catalog":
            signed, trusted = sign_fixture_catalog(root, approval)
            catalog.write_text(json.dumps(signed), encoding="utf-8")
        # Non-Windows support remains fail-closed in production. Only this
        # temporary synthetic fixture isolates the OS protection dependency.
        guard = market_query.protected_table_reads
        if os.name != "nt" and isolate_os_guard:
            guard = lambda files: nullcontext()
        with (
            patch.object(market_query, "DEFAULT_APPROVED_ROOT", root),
            patch.object(market_query, "DEFAULT_APPROVAL_CATALOG", catalog),
            patch.dict(approval_module.TRUSTED_SIGNERS, trusted, clear=True),
            patch.object(market_query, "protected_table_reads", guard),
        ):
            reader = MarketTruthDataset(
                location, expected_content_sha256=manifest["content_sha256"]
            )
            return reader.snapshot(DAY, cutoff, session_history=history)
class V3SnapshotContractTest(unittest.TestCase):
    def assert_response_schema(self, result, *, parquet=False):
        expected = TOP_LEVEL_KEYS | (PARQUET_ADDITIONAL_KEYS if parquet else frozenset())
        self.assertEqual(set(result), expected)
        self.assertEqual(set(result["features"]), FEATURE_NAMES)
        self.assertEqual(set(result["feature_units"]), set(UNITS))
        self.assertEqual(set(result["feature_warmup"]), set(WARMUP))
        self.assertEqual(set(result["roll_transition"]), {
            "observed", "previous_session", "previous_contract", "current_contract",
        })
        self.assertEqual(len(result["curve_points"]), 12)
        for point in result["curve_points"]:
            self.assertEqual(set(point), CURVE_POINT_KEYS)

    def test_all_output_fields_independent_numeric_oracle(self):
        store, history, expiries = _fixture()
        result = snapshot_asof(store, DAY, CUTOFF, session_history=history)
        self.assert_response_schema(result)
        self.assertEqual(history[0], date(2021, 4, 12))
        self.assertEqual(history[-1], date(2021, 5, 7))
        self.assertEqual(len(history), 20)
        self.assertEqual(expiries, [
            *[date(2021, month, 25) for month in range(6, 13)],
            *[date(2022, month, 25) for month in range(1, 6)],
        ])
        self.assertEqual(result["trade_date"], DAY.isoformat())
        self.assertEqual(result["decision_time"], "2021-05-10T23:59:30+00:00")
        self.assertFalse(result["protected_confirmation_accessed"])
        self.assertEqual(result["session_history_contract"],
                         "caller_supplied_complete_session_calendar")
        self.assertEqual(len(result["curve_points"]), 12)
        self.assertEqual({row["rank"] for row in result["curve_points"]}, set(range(1, 13)))
        self.assertEqual(set(result["features"]), FEATURE_NAMES)
        self.assertEqual(result["feature_units"], UNITS)
        self.assertEqual(result["feature_warmup"], WARMUP)
        self.assertEqual(result["source_sha256"], store["source_sha256"])
        self.assertEqual(result["evidence_ids"], sorted({
            evidence for point in result["curve_points"]
            for evidence in point["evidence_ids"]
        }))
        self.assertEqual(result["roll_transition"], {
            "observed": False,
            "previous_session": history[-1].isoformat(),
            "previous_contract": "SYN-00",
            "current_contract": "SYN-00",
        })
        points = result["curve_points"]
        self.assertEqual(points[0]["instrument_id"], "NG-00")
        self.assertEqual(points[0]["settle"], 3.1)
        self.assertEqual(points[0]["cleared_volume"], 0.0)
        self.assertEqual(points[0]["open_interest"], 1000.0)
        self.assertTrue(points[0]["last_trade_verified"])
        self.assertFalse(points[2]["last_trade_verified"])
        self.assertEqual(points[2]["rank_boundary_status"], "expiry_fallback_unverified")
        self.assertIsNone(points[1]["open_interest"])
        self.assertIsNone(points[1]["cleared_volume"])
        self.assertEqual(points[1]["missing_reason"], "none")
        for rank, point in enumerate(points, 1):
            self.assertEqual(point["rank"], rank)
            self.assertEqual(point["contract_symbol"], f"SYN-{rank - 1:02d}")
            self.assertIsNotNone(point["available_at"])
            self.assertTrue(point["evidence_ids"])
        prices = [3.1 + rank / 10 for rank in range(12)]
        winter = [price for price, end in zip(prices, expiries, strict=True)
                  if end.month in {11, 12, 1, 2, 3}]
        summer = [price for price, end in zip(prices, expiries, strict=True)
                  if end.month not in {11, 12, 1, 2, 3}]
        self.assertEqual([expiry.month for expiry in expiries[5:10]],
                         [11, 12, 1, 2, 3])
        self.assertEqual(len(winter), 5)
        self.assertEqual(len(summer), 7)
        closes = [2.4 + index / 50 for index in range(20)] + [3.1]
        log_returns = [math.log(closes[index] / closes[index - 1])
                       for index in range(1, 21)]
        mean = sum(log_returns) / len(log_returns)
        features = result["features"]
        numerics = {
            "front_price": 3.1,
            "m1_m2_spread_price_per_unit": -0.1,
            "m1_m3_slope_per_rank": 0.1,
            "m1_m2_m3_curvature": 0.0,
            "curve_mean_price_per_unit": 3.65,
            "winter_minus_summer_strip": 3.8 - 24.8 / 7,
            "m1_m2_annualized_carry_proxy": 0.1 / 3.1 * 365 / 30,
            "front_liquidity_volume_oi_ratio": 0.12,
            "front_realized_volatility_20_annualized":
                math.sqrt(sum((value - mean)**2 for value in log_returns) / 19) * math.sqrt(252),
            "front_max_abs_log_return_20": max(abs(value) for value in log_returns),
            "front_momentum_1": 3.1 / closes[-2] - 1,
            "front_momentum_5": 3.1 / closes[-6] - 1,
            "front_momentum_20": 3.1 / closes[0] - 1,
        }
        for name, expected in numerics.items():
            with self.subTest(feature=name):
                self.assertIsNotNone(features[name])
                self.assertAlmostEqual(features[name], expected, places=11)
        self.assertEqual(features["available_curve_slots"], 12)
        self.assertEqual(features["winter_strip_contracts"], len(winter))
        self.assertEqual(features["summer_strip_contracts"], len(summer))
        self.assertEqual(features["session_month"], DAY.month)
        self.assertEqual(features["session_weekday"], DAY.weekday())
        self.assertEqual(features["front_days_to_expiry"], 46)
        self.assertEqual(features["front_volume"], 120)
        self.assertEqual(features["front_open_interest"], 1000.0)
    def test_complete_parquet_vs_eager_interface_not_only_numeric_features(self):
        source, days, _ = _fixture()
        for count in (0, 1, 4, 5, 19, 20):
            selected = days[-count:] if count else []
            eager = snapshot_asof(source, DAY, CUTOFF, session_history=selected)
            parquet = _read_parquet_snapshot(source, selected)
            self.assert_response_schema(eager)
            self.assert_response_schema(parquet, parquet=True)
            self.assertEqual(set(parquet) - set(eager), PARQUET_ADDITIONAL_KEYS)
            features = parquet["features"]
            for field, lag in (
                ("front_momentum_1", 1),
                ("front_momentum_5", 5),
                ("front_momentum_20", 20),
                ("front_realized_volatility_20_annualized", 20),
                ("front_max_abs_log_return_20", 20),
            ):
                with self.subTest(history_count=count, warmup_field=field):
                    self.assertEqual(features[field] is not None, count >= lag)
            if count >= 1:
                self.assertAlmostEqual(features["front_momentum_1"], 3.1 / 2.78 - 1)
            if count >= 5:
                self.assertAlmostEqual(features["front_momentum_5"], 3.1 / 2.70 - 1)
            if count >= 20:
                self.assertAlmostEqual(features["front_momentum_20"], 3.1 / 2.40 - 1)
                closes = [2.4 + index / 50 for index in range(20)] + [3.1]
                logs = [math.log(closes[i] / closes[i - 1]) for i in range(1, 21)]
                mean = sum(logs) / 20
                expected_vol = math.sqrt(sum((value - mean) ** 2 for value in logs) / 19) * math.sqrt(252)
                self.assertAlmostEqual(
                    features["front_realized_volatility_20_annualized"], expected_vol
                )
                self.assertAlmostEqual(
                    features["front_max_abs_log_return_20"], max(abs(value) for value in logs)
                )
            self.assertEqual(parquet["dataset_source_sha256"], source["source_sha256"])
            self.assertRegex(parquet["dataset_content_sha256"], r"^[a-f0-9]{64}$")
            for key, value in eager.items():
                with self.subTest(history_count=count, field=key):
                    self.assertEqual(parquet[key], value)

    def test_missing_latest_history_preserves_horizon_nulls(self):
        source, days, _ = _fixture(missing_last_prior=True)
        eager = snapshot_asof(source, DAY, CUTOFF, session_history=days)
        parquet = _read_parquet_snapshot(source, days)
        self.assertEqual(parquet["features"], eager["features"])
        for name in (
            "front_momentum_1", "front_momentum_5", "front_momentum_20",
            "front_realized_volatility_20_annualized", "front_max_abs_log_return_20",
        ):
            self.assertIsNone(parquet["features"][name], name)
        self.assertEqual(parquet["features"]["front_price"], 3.1)
        self.assertEqual(parquet["features"]["front_liquidity_volume_oi_ratio"], 0.12)

    def test_same_day_pre_bar_publication_is_sparse_but_settlement_visible(self):
        source, days, _ = _fixture()
        cutoff = "2021-05-10T22:30:00Z"
        eager = snapshot_asof(source, DAY, cutoff, session_history=days)
        parquet = _read_parquet_snapshot(source, days, cutoff)
        for key in eager:
            self.assertEqual(parquet[key], eager[key], key)
        self.assertEqual(parquet["features"]["front_price"], 3.1)
        self.assertIsNone(parquet["features"]["front_volume"])
        self.assertIsNone(parquet["features"]["front_liquidity_volume_oi_ratio"])
        self.assertEqual(parquet["features"]["front_open_interest"], 1000.0)
        self.assertIsNone(parquet["curve_points"][0]["close"])


    def test_microsecond_cutoff_and_postcutoff_revision_fail_closed(self):
        def revision(clock, price):
            return {
                "instrument_id": "NG-00", "trade_date": DAY.isoformat(),
                "stat_type": 3, "price": price, "is_final": True,
                # The source event is earlier than all revisions. Event time
                # must not substitute for availability-time admissibility.
                "ts_event": "2021-05-10T21:00:00Z",
                "ts_recv": "2021-05-10T21:00:01Z",
                "available_at": clock,
            }

        source, days, _ = _fixture(revisions=[
            revision("2021-05-10T22:29:59.999999Z", 4.6),
            revision("2021-05-10T22:30:00Z", 4.7),
            revision("2021-05-10T22:30:00.000001Z", 99.0),
        ])
        for cutoff, price in (
            ("2021-05-10T22:29:59.999999Z", 4.6),
            ("2021-05-10T22:30:00Z", 4.7),
            ("2021-05-10T22:30:00.000001Z", 99.0),
        ):
            with self.subTest(cutoff=cutoff):
                eager = snapshot_asof(source, DAY, cutoff, session_history=days)
                parquet = _read_parquet_snapshot(source, days, cutoff)
                self.assert_response_schema(eager)
                self.assert_response_schema(parquet, parquet=True)
                self.assertEqual(parquet["features"]["front_price"], price)
                self.assertEqual(parquet["curve_points"][0]["settle"], price)
                self.assertEqual(parquet["features"]["front_volume"], None)
                for key in TOP_LEVEL_KEYS:
                    self.assertEqual(parquet[key], eager[key], key)

    def test_fixture_catalog_failure_modes_are_isolated(self):
        source, days, _ = _fixture()
        cases = (
            ("missing_catalog", "catalog missing"),
            ("empty", "no independent source-owner approval"),
            ("wrong_content", "no independent source-owner approval"),
            ("wrong_source", "approval does not match dataset evidence"),
            ("wrong_table", "approval does not match dataset evidence"),
            ("wrong_authority", "invalid source-owner admission policy"),
        )
        for variant, expected in cases:
            with (
                self.subTest(variant=variant),
                self.assertRaisesRegex(MarketTruthError, expected),
            ):
                _read_parquet_snapshot(source, days, approval_case=variant)


    def test_default_governed_catalog_rejects_unapproved_synthetic_content(self):
        source, _, _ = _fixture()
        real_catalog = market_query.DEFAULT_APPROVAL_CATALOG
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            location = root / "fixture"
            manifest = publish_parquet(source, location)
            # Only the path boundary is redirected to a synthetic directory.
            # The *real* governed catalog is never patched or modified.
            with (
                patch.object(market_query, "DEFAULT_APPROVED_ROOT", root),
                self.assertRaisesRegex(
                    MarketTruthError, "no independent source-owner approval"
                ),
            ):
                MarketTruthDataset(
                    location, expected_content_sha256=manifest["content_sha256"]
                )
        self.assertEqual(market_query.DEFAULT_APPROVAL_CATALOG, real_catalog)

    @unittest.skipIf(os.name == "nt", "native non-Windows guard only")
    def test_nonwindows_native_snapshot_guard_remains_fail_closed(self):
        source, history, _ = _fixture()
        with self.assertRaisesRegex(
            MarketTruthError, "non-Windows immutable source protection not implemented"
        ):
            # Synthetic test approval is otherwise valid, but the actual OS
            # protected-read guard is deliberately NOT patched in this test.
            _read_parquet_snapshot(source, history, isolate_os_guard=False)

    def test_real_admission_defaults_reject_synthetic_dataset(self):
        source, _, _ = _fixture()
        default_root = market_query.DEFAULT_APPROVED_ROOT
        default_catalog = market_query.DEFAULT_APPROVAL_CATALOG
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder) / "synthetic-not-approved"
            manifest = publish_parquet(source, location)
            with self.assertRaisesRegex(
                MarketTruthError, "outside approved development-only root"
            ):
                MarketTruthDataset(
                    location, expected_content_sha256=manifest["content_sha256"]
                )
        self.assertEqual(market_query.DEFAULT_APPROVED_ROOT, default_root)
        self.assertEqual(market_query.DEFAULT_APPROVAL_CATALOG, default_catalog)


if __name__ == "__main__":
    unittest.main()
