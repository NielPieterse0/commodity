"""Independent-source cadence, revision and missing-reference PIT regressions."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

from commodity.temporal_alignment import SourceCadence, SourceFact, align_asof


def clock(day: int, hour: int = 0) -> datetime:
    return datetime(2022, 6, day, hour, tzinfo=UTC)


def observation(
    source: str,
    series: str,
    day: int,
    published_day: int,
    value: float,
    vintage: str,
    *,
    hour: int = 0,
) -> SourceFact:
    return SourceFact(
        source_id=source, series_id=series, value=value,
        observed_for=clock(day), available_at=clock(published_day, hour),
        source_vintage_id=vintage, published_at=clock(published_day, hour),
        ingested_at=clock(15),  # later archive acquisition is not market availability
    )


class TemporalAlignmentTests(unittest.TestCase):
    def test_mixed_frequency_one_decision_no_same_timestamp_requirement(self):
        items = [
            observation("market", "ng_close", 7, 7, 8.2, "p1", hour=0),
            observation("eia", "storage", 2, 2, 91, "s1", hour=14),
            observation("cftc", "managed_money", 1, 4, 35, "c1", hour=20),
            observation("weather", "temperature", 7, 7, 28, "w1", hour=4),
        ]
        policies = [
            SourceCadence("market", "ng_close", "daily", timedelta(days=2)),
            SourceCadence("eia", "storage", "weekly", timedelta(days=8)),
            SourceCadence("cftc", "managed_money", "weekly", timedelta(days=7)),
            SourceCadence("weather", "temperature", "hourly", timedelta(hours=8)),
        ]
        result = align_asof(clock(7, 9), items, policies)
        self.assertEqual({key: item.value for key, item in result.items()}, {
            ("market", "ng_close"): 8.2,
            ("eia", "storage"): 91,
            ("cftc", "managed_money"): 35,
            ("weather", "temperature"): 28,
        })
        self.assertEqual(result[("cftc", "managed_money")].age_seconds, 2 * 86400 + 13 * 3600)

    def test_future_publication_is_not_available_at_observation(self):
        record = observation("cme", "oi", 6, 7, 130, "v1", hour=8)
        policy = [SourceCadence("cme", "oi", "daily", timedelta(days=3))]
        early = align_asof(clock(7, 7), [record], policy)[("cme", "oi")]
        self.assertEqual(early.state, "not_yet_published")
        self.assertIsNone(early.value)
        late = align_asof(clock(7, 9), [record], policy)[("cme", "oi")]
        self.assertEqual(late.value, 130)

    def test_newer_observation_beats_later_revision_of_older_day(self):
        items = [
            observation("a", "x", 5, 6, 10, "a"),
            observation("a", "x", 6, 7, 20, "a"),
            observation("a", "x", 5, 8, 11, "revision"),
        ]
        policy = [SourceCadence("a", "x", "daily", timedelta(days=5))]
        self.assertEqual(align_asof(clock(9), items, policy)[("a", "x")].value, 20)
        original_only = [item for item in items if item.observed_for == clock(5)]
        self.assertEqual(align_asof(clock(9), original_only, policy)[("a", "x")].value, 11)

    def test_stale_is_visible_but_value_not_silently_forward_filled(self):
        record = observation("s", "weekly", 1, 1, 100, "v1")
        policy = [SourceCadence("s", "weekly", "weekly", timedelta(days=5))]
        result = align_asof(clock(9), [record], policy)[("s", "weekly")]
        self.assertEqual(result.state, "stale")
        self.assertIsNone(result.value)
        self.assertEqual(result.age_seconds, 8 * 86400)
        self.assertEqual(result.fact.value, 100)

    def test_undefined_reference_is_never_inferred_from_publication_date(self):
        valid = observation("cme", "oi", 5, 6, 10, "v1")
        orphan = SourceFact("cme", "oi", 999, None, clock(7), "legacy",
                            reference_state="unresolved")
        policy = [SourceCadence("cme", "oi", "daily", timedelta(days=3))]
        result = align_asof(clock(7, 12), [valid, orphan], policy)[("cme", "oi")]
        self.assertEqual(result.value, 10)
        self.assertEqual(result.unresolved_reference_rows, 1)
        result = align_asof(clock(7, 12), [orphan], policy)[("cme", "oi")]
        self.assertEqual(result.state, "reference_unresolved")
        self.assertIsNone(result.value)
        self.assertIsNone(result.fact)

    def test_availability_change_cannot_affect_past(self):
        base = observation("eia", "storage", 3, 4, 100, "v1")
        future = observation("eia", "storage", 3, 10, 200, "v2")
        policy = [SourceCadence("eia", "storage", "weekly", None)]
        before = align_asof(clock(9), [base], policy)
        after = align_asof(clock(9), [future, base], policy)
        self.assertEqual(before, after)

    def test_forecasts_use_issue_time_not_future_target(self):
        forecast = SourceFact(
            "wx", "forecast_2022_06_09", 26, clock(9), clock(7, 6), "fx1",
            issued_at=clock(7, 5), forecast_valid_at=clock(9),
        )
        p = [SourceCadence("wx", "forecast_2022_06_09", "6-hourly", timedelta(hours=10), forecast=True)]
        self.assertEqual(align_asof(clock(7, 7), [forecast], p)[("wx", "forecast_2022_06_09")].value, 26)
        self.assertEqual(align_asof(clock(7, 5), [forecast], p)[("wx", "forecast_2022_06_09")].state, "not_yet_published")

    def test_conflicting_same_version_fails_closed(self):
        fact = observation("a", "x", 5, 6, 1, "one")
        with self.assertRaisesRegex(ValueError, "conflicting"):
            align_asof(clock(8), [fact, replace(fact, value=2)],
                       [SourceCadence("a", "x", "daily", None)])

    def test_naive_timestamp_and_fabricated_reference_rejected(self):
        base = observation("a", "x", 5, 6, 1, "v")
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            replace(base, available_at=clock(6).replace(tzinfo=None))
        with self.assertRaisesRegex(ValueError, "reference"):
            replace(base, observed_for=None)
        with self.assertRaisesRegex(ValueError, "invent"):
            replace(base, reference_state="unresolved")

    def test_maximum_rows_and_unknown_series_fail_closed(self):
        fact = observation("a", "x", 5, 6, 1, "v")
        with self.assertRaisesRegex(ValueError, "budget"):
            align_asof(clock(8), [fact], [SourceCadence("a", "x", "daily", None)],
                       max_fact_rows=0)
        with self.assertRaisesRegex(ValueError, "undeclared"):
            align_asof(clock(8), [fact], [])

    def test_future_undated_records_do_not_leak_missingness_into_past(self):
        record = SourceFact("cme", "oi", 123, None, clock(10), "legacy",
                            reference_state="unresolved")
        policy = [SourceCadence("cme", "oi", "daily", timedelta(days=2))]
        result = align_asof(clock(7), [record], policy)[("cme", "oi")]
        self.assertEqual(result.state, "not_yet_published")
        self.assertEqual(result.unresolved_reference_rows, 0)

    def test_source_value_missing_is_not_reported_available(self):
        fact = replace(observation("a", "x", 5, 6, 1, "v"), value=None)
        selection = align_asof(
            clock(7), [fact], [SourceCadence("a", "x", "daily", None)]
        )[("a", "x")]
        self.assertEqual(selection.state, "source_value_missing")
        self.assertIsNone(selection.value)
        self.assertIs(selection.fact, fact)

    def test_archive_ingestion_time_not_backdated_to_market_availability(self):
        old = observation("eia", "storage", 5, 6, 100, "historical")
        newer = replace(old, value=101, source_vintage_id="late", available_at=clock(7),
                        published_at=clock(7), ingested_at=clock(20))
        policy = [SourceCadence("eia", "storage", "weekly", None)]
        historical = align_asof(clock(8), [old, newer], policy)
        self.assertEqual(historical[("eia", "storage")].value, 101)
        bounded = align_asof(clock(8), [old, newer], policy, knowledge_asof=clock(16))
        self.assertEqual(bounded[("eia", "storage")].value, 100)
        with self.assertRaisesRegex(ValueError, "ingestion timestamp"):
            align_asof(clock(8), [replace(old, ingested_at=None)], policy,
                       knowledge_asof=clock(16))

    def test_equal_availability_uses_publication_before_lexical_vintage(self):
        old = observation("cme", "oi", 5, 7, 10, "z-vintage", hour=20)
        early = replace(old, published_at=clock(7, 9), value=10)
        revised = replace(old, published_at=clock(7, 15), value=11,
                          source_vintage_id="a-vintage")
        policy = [SourceCadence("cme", "oi", "daily", timedelta(days=3))]
        result = align_asof(clock(8), [early, revised], policy)[("cme", "oi")]
        self.assertEqual(result.value, 11)
        self.assertEqual(result.fact.source_vintage_id, "a-vintage")
        self.assertEqual(align_asof(clock(8), [revised, early], policy), {
            ("cme", "oi"): result
        })

    def test_equal_publication_uses_issued_and_ingested_before_vintage(self):
        first = observation("cme", "oi", 5, 7, 10, "z-first", hour=20)
        first = replace(first, published_at=clock(7, 8), issued_at=clock(7, 8),
                        ingested_at=clock(12))
        second = replace(first, value=12, source_vintage_id="a-second",
                         issued_at=clock(7, 9), ingested_at=clock(11))
        policy = [SourceCadence("cme", "oi", "daily", None)]
        self.assertEqual(
            align_asof(clock(8), [first, second], policy)[("cme", "oi")].value, 12
        )

    def test_same_clock_conflicting_values_remain_rejected(self):
        first = observation("cme", "oi", 5, 7, 10, "z-first", hour=20)
        second = replace(first, value=12, source_vintage_id="a-second")
        policy = [SourceCadence("cme", "oi", "daily", None)]
        with self.assertRaisesRegex(ValueError, "conflicting"):
            align_asof(clock(8), [first, second], policy)

    def test_same_clock_conflict_rejects_equivalent_utc_offsets(self):
        first = observation("cme", "oi", 5, 7, 10, "utc-version", hour=20)
        first = replace(first, issued_at=clock(7, 8))
        local = timezone(timedelta(hours=3))
        second = replace(
            first, value=12, source_vintage_id="local-offset-version",
            published_at=first.published_at.astimezone(local),
            issued_at=first.issued_at.astimezone(local),
            ingested_at=first.ingested_at.astimezone(local),
        )
        policy = [SourceCadence("cme", "oi", "daily", None)]
        for records in ([first, second], [second, first]):
            with self.assertRaisesRegex(ValueError, "same-clock"):
                align_asof(clock(8), records, policy)

    def test_forecast_target_must_have_distinct_series_key(self):
        one = SourceFact("wx", "forecast", 25, clock(9), clock(7, 6), "v1",
                         issued_at=clock(7, 5), forecast_valid_at=clock(9))
        two = SourceFact("wx", "forecast", 26, clock(10), clock(7, 8), "v2",
                         issued_at=clock(7, 7), forecast_valid_at=clock(10))
        policy = [SourceCadence("wx", "forecast", "six_hourly", timedelta(days=2), forecast=True)]
        with self.assertRaisesRegex(ValueError, "mixed forecast targets"):
            align_asof(clock(7, 9), [one, two], policy)


if __name__ == "__main__":
    unittest.main()
