"""Definition field-level original-to-final audit regressions (synthetic only)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from commodity.market_truth.ng import normalize_ng_databento_record
from commodity.market_truth.review_site import reconcile_definition_fields


class DefinitionFieldAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = [
            {
                "instrument_id": str(id_), "ts_event": event, "ts_recv": received,
                "asset": "NG", "instrument_class": "F", "raw_symbol": symbol,
                "expiration": expiry, "exchange": "XNYM",
            }
            for id_, event, received, symbol, expiry in [
                (101, "2022-01-03 12:00:00+00:00", "2022-01-03 12:05:00+00:00",
                 "NGG22", "2022-02-01 19:30:00+00:00"),
                (102, "2022-01-04 12:00:00+00:00", "2022-01-04 12:00:00+00:00",
                 "NGH22", "2022-03-01 19:30:00+00:00"),
            ]
        ]

    def compare(self, source_rows, final_rows):
        source = self.root / "definitions.csv"
        source.write_text(
            "instrument_id,ts_event,ts_recv,asset,instrument_class,"
            "raw_symbol,expiration,exchange\n"
            + "".join(",".join(row[name] for name in (
                "instrument_id", "ts_event", "ts_recv", "asset",
                "instrument_class", "raw_symbol", "expiration", "exchange"
            )) + "\n" for row in source_rows),
            encoding="utf-8",
        )
        document = self.root / "final.jsonl"
        document.write_text(
            "\n".join(json.dumps(row) for row in final_rows), encoding="utf-8"
        )
        final = self.root / f"final-{len(list(self.root.glob('*.parquet')))}.parquet"
        with duckdb.connect(":memory:") as db:
            fields = ", ".join(
                f"strftime(CAST({name} AS TIMESTAMP), "
                f"'%Y-%m-%dT%H:%M:%S+00:00') AS {name}"
                for name in ("expiration", "available_at", "event_at", "last_trade_at")
            )
            db.execute(
                f"COPY (SELECT * REPLACE ({fields}) FROM read_json_auto(?)) "
                f"TO '{final.as_posix()}' (FORMAT PARQUET)",
                [str(document)],
            )
            return reconcile_definition_fields(db, source, final)

    def normalized(self):
        return [normalize_ng_databento_record("definitions", row) for row in self.original]

    def test_matches_all_mapped_fields_including_availability_clock(self):
        matched = self.compare(self.original, self.normalized())
        self.assertTrue(matched["exact"], matched)
        self.assertEqual(matched["source_rows"], 2)
        self.assertEqual(matched["final_rows"], 2)
        self.assertFalse(matched["research_admitted"])
        self.assertFalse(matched["exchange_expiry_independently_verified"])

    def test_detects_same_count_symbol_expiry_and_clock_tampering(self):
        for field, forged in (
            ("symbol", "OTHER"),
            ("expiration", "2022-02-02T19:30:00+00:00"),
            ("available_at", "2022-01-03T11:59:00+00:00"),
            ("contract_size", 999),
        ):
            rows = self.normalized()
            rows[0][field] = forged
            with self.subTest(field=field):
                result = self.compare(self.original, rows)
                self.assertFalse(result["exact"])
                self.assertEqual(result["source_only_field_tuples"], 1)
                self.assertEqual(result["final_only_field_tuples"], 1)

    def test_duplicate_final_revision_is_visible(self):
        rows = self.normalized()
        duplicate = self.compare(self.original, rows + [dict(rows[0])])
        self.assertFalse(duplicate["exact"])
        self.assertEqual(duplicate["final_only_field_tuples"], 1)
        self.assertEqual(duplicate["duplicate_final_revision_grains"], 1)

    def test_other_product_is_not_counted_as_ng(self):
        original = [dict(row) for row in self.original]
        original[1]["asset"] = "CL"
        result = self.compare(original, self.normalized())
        self.assertFalse(result["exact"])
        self.assertEqual(result["source_rows"], 1)
        self.assertEqual(result["final_only_field_tuples"], 1)


if __name__ == "__main__":
    unittest.main()
