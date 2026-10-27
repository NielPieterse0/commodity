"""Source-free negatives for the change-local CME counterfactual, not CME approval."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import duckdb
from audit_cme_exclusion_impact import (
    LEGACY,
    audit,
    count_expiry_value_differences,
    count_rank_differences,
    uncertain_expiry,
    verify_source_pins,
)


class CmeImpactClassificationTests(unittest.TestCase):
    def test_receipt_bound_to_audited_script_and_source_identity(self):
        root = Path(__file__).parent
        boundary = json.loads((root / "cme-expiry-closeout-boundary.json").read_bytes())
        self.assertEqual(boundary["audit_receipt"], "cme-expiry-exposure-receipt.json")
        receipt = json.loads((root / boundary["audit_receipt"]).read_bytes())
        script_sha = hashlib.sha256(
            (root / "audit_cme_exclusion_impact.py").read_bytes()
        ).hexdigest()
        self.assertEqual(receipt["audit_script_sha256"], script_sha)
        self.assertEqual(
            receipt["source_sha256"],
            {
                "manifest": "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605",
                "definitions": "b803deb0b88d7c0f57625fd46cfa4537e902dd3951cf04aeeba84f95f5dbf4d8",
                "features": "b14ae69bd6ec2910f0cf56fe62f481016801308cebc6ef69e536aa7e593d072e",
                "session-path": "0fe87ea79a56f98fb9d445e89e3d65b48ae7bb1175e06ba9b97da68ebe6b01e8",
            },
        )
        self.assertEqual(
            receipt["uncertain_contract_identities_sha256"],
            "a6c11d1fc824bca35745f2cfb4cd7d87849da4310ffc661a0d0fbe568cb26ffd",
        )
        self.assertEqual(
            receipt["counterfactual_changed_sessions_sha256"],
            "dac98d806a34ae8b23b35f488dfb45975509680bf6af53de0305dec1de18364c",
        )
        impact = boundary["impact"]
        self.assertEqual(
            impact["rank_order_changed_sessions_using_weekday_only_counterfactual"],
            receipt["counterfactual_changed_sessions_any_rank"],
        )
        self.assertEqual(
            impact["changed_rank12_slots_using_weekday_only_counterfactual"],
            receipt["counterfactual_changed_rank_slots"],
        )
        self.assertEqual(
            impact["sessions_selecting_any_of_14_unverified_expiries_among_12_ranks"],
            receipt["uncertain_rank12_selected_sessions"],
        )
        self.assertEqual(
            impact["affected_contract_rank_selections"],
            receipt["uncertain_rank12_selected_rows"],
        )
        self.assertEqual(
            impact["selected_front_trading_path_sessions_referencing_anomalies"],
            receipt["frozen_trading_path_sessions_referencing_uncertain_expiries"],
        )
        self.assertEqual(
            impact["frozen_feature_sessions"], receipt["frozen_feature_sessions"]
        )
        for field, source in {
            "same_rank_expiry_value_changed_sessions": "counterfactual_same_rank_expiry_changed_sessions",
            "same_rank_expiry_value_changed_slots": "counterfactual_same_rank_expiry_changed_slots",
            "same_rank_expiry_value_changed_m1to4_sessions": "counterfactual_same_rank_expiry_changed_front4_sessions",
            "same_rank_expiry_value_changed_m1to4_slots": "counterfactual_same_rank_expiry_changed_front4_slots",
        }.items():
            self.assertEqual(impact[field], receipt[source])
        self.assertTrue(impact["counterfactual_is_not_independent_exchange_evidence"])
        self.assertTrue(
            impact["date_dependent_features_outside_rank_boundary_unverified"]
        )
        self.assertEqual(
            boundary["status"],
            "open_all_14_date_only_corrob_externally_unpinned_unqualified",
        )
        self.assertEqual(receipt["historical_contracts"], 152)
        self.assertEqual(receipt["historical_weekday_comparator_differences"], 14)
        self.assertEqual(receipt["frozen_feature_sessions"], 3088)
        self.assertEqual(receipt["frozen_rank12_rows"], 37056)
        self.assertEqual(receipt["uncertain_rank12_selected_rows"], 3156)
        self.assertEqual(receipt["uncertain_rank12_selected_sessions"], 2564)
        self.assertEqual(receipt["uncertain_rank12_selected_symbols"], 12)
        self.assertEqual(
            receipt["frozen_trading_path_records_referencing_uncertain_expiries"], 344
        )
        self.assertEqual(
            sum(item["rows"] for item in receipt["uncertain_selected_by_rank"]), 3156
        )
        self.assertEqual(
            [item["rank"] for item in receipt["uncertain_selected_by_rank"]],
            list(range(1, 13)),
        )
        self.assertEqual(receipt["official_date_promotions"], 0)
        self.assertFalse(receipt["immutable_storage_verified"])
        self.assertFalse(receipt["safe_for_unqualified_expiry_dependent_V3_research"])
        self.assertEqual(receipt["counterfactual_changed_sessions_any_rank"], 10)
        self.assertEqual(receipt["counterfactual_changed_rank_slots"], 120)
        self.assertEqual(receipt["counterfactual_changed_rank1to4_slots"], 40)
        self.assertEqual(receipt["counterfactual_changed_sessions_rank1to4"], 10)
        self.assertEqual(receipt["counterfactual_changed_front_rank_slots"], 10)
        self.assertEqual(receipt["counterfactual_changed_front_rank_sessions"], 10)
        self.assertEqual(receipt["counterfactual_same_rank_expiry_changed_slots"], 3147)
        self.assertEqual(
            receipt["counterfactual_same_rank_expiry_changed_sessions"], 2556
        )
        self.assertEqual(
            receipt["counterfactual_same_rank_expiry_changed_front4_slots"], 1143
        )
        self.assertEqual(
            receipt["counterfactual_same_rank_expiry_changed_front4_sessions"], 1082
        )
        self.assertFalse(receipt["independent_CME_expiration_verification"])
        self.assertFalse(receipt["exclusion_policy_implemented"])
        self.assertFalse(receipt["research_owner_approval"])

    def test_exact_pinned_replay_matches_complete_receipt(self):
        if not (LEGACY / "features.parquet").is_file():
            self.skipTest("Frozen source not mounted; offline Docker replay required")
        actual = audit()
        receipt = json.loads(
            (Path(__file__).parent / "cme-expiry-exposure-receipt.json").read_bytes()
        )
        self.assertEqual(actual, receipt)

    def test_checked_source_pins_and_development_scope_fail_closed(self):
        runtime = Path(__file__).resolve().parents[3] / ".work/runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as directory:
            root = Path(directory)
            sources = {
                name: root / name
                for name in ("manifest", "definitions", "features", "session-path")
            }
            for name, path in sources.items():
                if name != "manifest":
                    path.write_bytes(name.encode())
            expected = {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in sources.items()
                if name != "manifest"
            }
            manifest = {
                "dataset_scope": "development_pre2023",
                "protected_confirmation_accessed": False,
                "tables": {"definitions": {"sha256": expected["definitions"]}},
            }

            def publish_manifest():
                sources["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
                expected["manifest"] = hashlib.sha256(
                    sources["manifest"].read_bytes()
                ).hexdigest()

            publish_manifest()
            verify_source_pins(sources, expected)
            sources["definitions"].write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "definitions"):
                verify_source_pins(sources, expected)
            sources["definitions"].write_bytes(b"definitions")
            sources["features"].rename(root / "held")
            with self.assertRaisesRegex(RuntimeError, "features"):
                verify_source_pins(sources, expected)
            (root / "held").rename(sources["features"])
            link = root / "symlink-fixture"
            try:
                link.symlink_to(sources["features"])
            except (OSError, NotImplementedError):
                pass  # Windows symlink privilege may be unavailable.
            else:
                actual = sources["features"]
                sources["features"] = link
                with self.assertRaisesRegex(RuntimeError, "features"):
                    verify_source_pins(sources, expected)
                sources["features"] = actual
            for key, value in (
                ("dataset_scope", "protected_confirmation"),
                ("protected_confirmation_accessed", True),
            ):
                prior = manifest[key]
                manifest[key] = value
                publish_manifest()
                with (
                    self.subTest(key=key),
                    self.assertRaisesRegex(RuntimeError, "admission/scope"),
                ):
                    verify_source_pins(sources, expected)
                manifest[key] = prior
            manifest["tables"]["definitions"]["sha256"] = "0" * 64
            publish_manifest()
            with self.assertRaisesRegex(RuntimeError, "admission/scope"):
                verify_source_pins(sources, expected)

    def test_independent_three_day_rank_oracle(self):
        # A unchanged, B changes all 12, C swaps two front ranks, D expiry only.
        with duckdb.connect(":memory:") as db:
            db.execute(
                "CREATE TEMP TABLE rank12(day DATE, rank INTEGER, instrument_id VARCHAR,"
                " expiration VARCHAR)"
            )
            db.execute(
                "CREATE TEMP TABLE proxy_rank12(day DATE, rank INTEGER,"
                " instrument_id VARCHAR, expiration VARCHAR, counterfactual_expiration VARCHAR)"
            )
            original = []
            alternate = []
            for day in ("2022-01-03", "2022-01-04", "2022-01-05", "2022-01-06"):
                for rank in range(1, 13):
                    original.append((day, rank, f"CONTRACT-{rank}", "2022-02-28"))
                    proxy_rank = (
                        (rank % 12) + 1
                        if day == "2022-01-04"
                        else (3 - rank if rank in (1, 2) else rank)
                        if day == "2022-01-05"
                        else rank
                    )
                    alternate.append(
                        (
                            day,
                            rank,
                            f"CONTRACT-{proxy_rank}",
                            "2022-02-28",
                            "2022-02-27"
                            if day == "2022-01-06" and rank == 9
                            else "2022-02-28",
                        )
                    )
            db.executemany("INSERT INTO rank12 VALUES (?,?,?,?)", original)
            db.executemany("INSERT INTO proxy_rank12 VALUES (?,?,?,?,?)", alternate)
            changed, days = count_rank_differences(db)
            expiry_values = count_expiry_value_differences(db)
            self.assertEqual(changed, (14, 2, 6, 2, 2, 2))
            self.assertEqual(days, ["2022-01-04", "2022-01-05"])
            self.assertEqual(expiry_values, (1, 1, 0, 0))
            db.execute("DELETE FROM proxy_rank12 WHERE day='2022-01-03' AND rank=12")
            with self.assertRaisesRegex(RuntimeError, "rank comparison"):
                count_rank_differences(db)
            db.execute(
                "INSERT INTO proxy_rank12 VALUES "
                "('2022-01-03',12,'CONTRACT-12','2022-02-28','2022-02-28')"
            )
            db.execute(
                "INSERT INTO proxy_rank12 VALUES "
                "('2022-01-03',13,'EXTRA','2022-02-28','2022-02-28')"
            )
            with self.assertRaisesRegex(RuntimeError, "rank comparison"):
                count_rank_differences(db)

    def test_eastern_cutoff_and_suffix_boundaries(self):
        cases = [
            ("NGF23", "2023-01-01T00:30:00+00:00", True),
            ("NGG23", "2023-01-01T05:30:00+00:00", False),
            ("NGF0", "2019-12-27T19:30:00+00:00", True),
            ("NGF2022", "2021-12-28T19:30:00+00:00", True),
        ]
        for symbol, expiration, historical in cases:
            with self.subTest(symbol=symbol, expiration=expiration):
                self.assertIs(
                    uncertain_expiry("NYMEX", symbol, expiration)[0], historical
                )

    def test_normal_historical_expiration_is_not_a_discrepancy(self):
        self.assertEqual(
            uncertain_expiry("NYMEX", "NGQ2", "2022-07-27T18:30:00+00:00"),
            (True, False),
        )

    def test_memorial_day_holiday_candidate_is_not_assumed_official(self):
        self.assertEqual(
            uncertain_expiry("NYMEX", "NGM22", "2022-05-26T18:30:00+00:00"),
            (True, True),
        )

    def test_2023_forward_expiry_is_outside_historical_cohort(self):
        self.assertEqual(
            uncertain_expiry("NYMEX", "NGG23", "2023-01-27T19:30:00+00:00"),
            (False, False),
        )

    def test_source_identity_and_time_fail_closed(self):
        cases = [
            ("OTHER", "NGM22", "2022-05-26T18:30:00+00:00"),
            ("NYMEX", "NOT-NG", "2022-05-26T18:30:00+00:00"),
            ("NYMEX", "NGM21", "2022-05-26T18:30:00+00:00"),
            ("NYMEX", "NGM22", "2022-05-26T18:30:00"),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                uncertain_expiry(*args)


if __name__ == "__main__":
    unittest.main()
