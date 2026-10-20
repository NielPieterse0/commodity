"""Bounded regression tests for the independent pre-2023 archive audit."""

import hashlib
import runpy
import tempfile
import unittest
from pathlib import Path

TOOLS = runpy.run_path(
    str(Path(__file__).with_name("audit_original_cohort.py"))
)
validate_job_id = TOOLS["validate_job_id"]
validate_archive_filename = TOOLS["validate_archive_filename"]
bounded_archive_path = TOOLS["bounded_archive_path"]
verify_curated_inputs = TOOLS["verify_curated_inputs"]
require_pinned_curated_manifest = TOOLS["require_pinned_curated_manifest"]
EXPECTED_MANIFEST_SHA256 = TOOLS["EXPECTED_CURATED_MANIFEST_SHA256"]


class OriginalSourceCohortTests(unittest.TestCase):
    def test_exact_historical_acquisition_id_required(self):
        self.assertEqual(
            validate_job_id("GLBX-20260813-4LWDSMFX5T"),
            "GLBX-20260813-4LWDSMFX5T",
        )
        for invalid in (
            "../../protected",
            "GLBX-20260913-4LWDSMFX5T",
            "GLBX-20260813-4LWDSMFX5T/../protected",
            "not-an-acquisition-job-id",
            "GLBX-20260813-../../BAD",
            "",
            None,
        ):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                validate_job_id(invalid)

    def test_filename_enforces_exact_original_annual_date_ranges(self):
        for year in range(2010, 2023):
            start = "20100606" if year == 2010 else f"{year}0101"
            for family in ("definition", "ohlcv-1d", "statistics"):
                with self.subTest(year=year, family=family):
                    self.assertEqual(
                        validate_archive_filename(
                            f"glbx-mdp3-{start}-{year}1231.{family}.dbn.zst",
                            family,
                        ),
                        year,
                    )
        for filename, family in (
            ("glbx-mdp3-20100101-20101231.definition.dbn.zst", "definition"),
            ("glbx-mdp3-20100607-20101231.definition.dbn.zst", "definition"),
            ("glbx-mdp3-20110102-20111231.statistics.dbn.zst", "statistics"),
            ("glbx-mdp3-20110101-20111230.ohlcv-1d.dbn.zst", "ohlcv-1d"),
            ("glbx-mdp3-20110101-20121231.definition.dbn.zst", "definition"),
            ("glbx-mdp3-20230101-20231231.statistics.dbn.zst", "statistics"),
            ("glbx-mdp3-20110101-20111231.statistics.dbn.zst", "bad-family"),
        ):
            with self.subTest(filename=filename, family=family), self.assertRaises(
                ValueError
            ):
                validate_archive_filename(filename, family)

    def test_source_guard_accepts_only_file_in_declared_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent = root / "definition" / "GLBX-20260813-4LWDSMFX5T"
            parent.mkdir(parents=True)
            expected = parent / "pre2023.dbn.zst"
            expected.write_bytes(b"pinned")
            self.assertEqual(
                bounded_archive_path(expected, parent=parent, root=root), expected
            )
            with self.assertRaises(ValueError):
                bounded_archive_path(expected, parent=root, root=root)
            with self.assertRaises(ValueError):
                bounded_archive_path(expected, parent=parent, root=root / "wrong")

    def test_curated_manifest_fails_on_coordinated_input_change(self):
        require_pinned_curated_manifest(EXPECTED_MANIFEST_SHA256)
        for altered_digest in ("a" * 64, "0" * 64):
            with self.subTest(digest=altered_digest), self.assertRaisesRegex(
                ValueError, "curated manifest independently pinned hash mismatch"
            ):
                require_pinned_curated_manifest(altered_digest)

    def test_curated_csv_requires_three_inputs_and_exact_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder)
            inputs = {}
            for name in ("definitions", "bars", "statistics"):
                csv_path = stage / f"{name}.csv"
                csv_path.write_text("field\nvalue\n", encoding="utf-8")
                inputs[name] = {
                    "relative_path": csv_path.name,
                    "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                    "row_count": 1,
                }
            manifest = {"inputs": inputs}
            sizes, counts = verify_curated_inputs(manifest, stage)
            self.assertEqual(set(sizes), set(inputs))
            self.assertEqual(counts, dict.fromkeys(inputs, 1))
            for invalid in (
                {"inputs": {k: v for k, v in inputs.items() if k != "bars"}},
                {"inputs": {**inputs, "bars": {**inputs["bars"], "row_count": 2}}},
                {"inputs": {**inputs, "bars": {**inputs["bars"], "relative_path": "statistics.csv"}}},
            ):
                with self.subTest(case=invalid), self.assertRaises(ValueError):
                    verify_curated_inputs(invalid, stage)
            for bad in (b",field\nvalue,1\n", b"   ,field\nvalue,1\n", b"field ,other\nvalue,1\n", b"field, other\nvalue,1\n", b"field, field\nvalue,1\n"):
                (stage / "bars.csv").write_bytes(bad)
                inputs["bars"]["sha256"] = hashlib.sha256(bad).hexdigest()
                with self.subTest(bad=bad), self.assertRaisesRegex(
                    ValueError, "missing or duplicate curated CSV header"
                ):
                    verify_curated_inputs(manifest, stage)

    def test_archive_symlink_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "target"
            target.mkdir()
            (target / "pre2023.dbn.zst").write_bytes(b"pinned")
            alias = root / "alias"
            try:
                alias.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("Windows symlink privilege unavailable")
            with self.assertRaises(ValueError):
                bounded_archive_path(
                    alias / "pre2023.dbn.zst", parent=alias, root=root
                )

    def test_archive_symlink_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.dbn.zst"
            source.write_bytes(b"pinned")
            alias = root / "alias.dbn.zst"
            try:
                alias.symlink_to(source)
            except OSError:
                self.skipTest("Windows symlink privilege unavailable")
            with self.assertRaises(ValueError):
                bounded_archive_path(alias, parent=root, root=root)


if __name__ == "__main__":
    unittest.main()
