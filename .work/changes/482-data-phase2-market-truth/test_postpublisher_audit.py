"""Synthetic fail-closed tests for the change-local post-publisher evidence audit."""

import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import audit_postpublisher_rebuild as audit

from commodity.market_truth.protected_reads import protected_table_reads


class PostpublisherAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.payload = {
            "schema_version": 1, "dataset": "GLBX.MDP3",
            "product_code": "NG", "evidence_class": "development",
            "max_trade_date": "2022-12-31", "protected_confirmation_accessed": False,
            "inputs": {},
        }
        for family, (filename, schema, count) in audit.SOURCE_INPUTS.items():
            raw = (family + " original bytes\n").encode()
            (self.root / filename).write_bytes(raw)
            self.payload["inputs"][family] = {
                "relative_path": filename, "row_count": count,
                "schema": schema, "sha256": hashlib.sha256(raw).hexdigest(),
            }
        self.manifest = self.root / "source-manifest.json"
        self.patch_data = patch.object(audit, "DATA", self.root)
        self.patch_source = patch.object(audit, "SOURCE", self.manifest)
        self.patch_digest = patch.object(audit, "SOURCE_SHA", "")
        for operation in (self.patch_data, self.patch_source, self.patch_digest):
            operation.start()
            self.addCleanup(operation.stop)
        self.save_manifest()

    def save_manifest(self):
        raw = json.dumps(self.payload, sort_keys=True).encode()
        self.manifest.write_bytes(raw)
        audit.SOURCE_SHA = hashlib.sha256(raw).hexdigest()

    def checked(self):
        inputs = audit.source_inputs()
        rec = {k: {"source_rows": info[2]} for k, info in audit.SOURCE_INPUTS.items()}
        sha = {k: digest for k, (_, digest) in inputs.items()}
        audit.verify_source_artifacts(inputs, sha, rec)
        return inputs, sha, rec

    def test_known_artifacts_pass(self):
        self.checked()

    def test_source_handles_cover_entire_audit(self):
        levels = []
        expected = {family: (self.root / item[0], "0" * 64)
                    for family, item in audit.SOURCE_INPUTS.items()}

        @contextmanager
        def protected(paths):
            levels.append(set(paths))
            try:
                yield
            finally:
                levels.pop()

        def source():
            self.assertEqual(len(levels), 1)
            self.assertIn(audit.SOURCE, levels[0])
            return expected

        def locked(inputs):
            self.assertEqual(len(levels), 2)
            self.assertEqual({path for path, _ in inputs.values()}, levels[1])
            return {"audit": "guarded"}

        with (
            patch.object(audit, "protected_table_reads", protected),
            patch.object(audit, "source_inputs", source),
            patch.object(audit, "_audit_locked", locked),
        ):
            self.assertEqual(audit.audit(), {"audit": "guarded"})
        self.assertEqual(levels, [])

    @unittest.skipUnless(os.name == "nt", "Win32 retained sharing handles required")
    def test_real_windows_nested_source_and_ancestor_guards(self):
        """Validate actual Windows exclusive-read handles, not mocked contexts."""
        source_file = self.root / audit.SOURCE_INPUTS["statistics"][0]
        ancestor = self.root
        original_manifest = self.manifest.read_bytes()
        with protected_table_reads([self.manifest]):
            with self.assertRaises(OSError):
                self.manifest.open("ab")
            with protected_table_reads([source_file]):
                with self.assertRaises(OSError):
                    source_file.open("ab")
                with self.assertRaises(OSError):
                    source_file.rename(source_file.with_suffix(".moved"))
                with self.assertRaises(OSError):
                    ancestor.rename(ancestor.with_name(ancestor.name + "-retarget"))
            with self.assertRaises(OSError):
                self.manifest.open("ab")
        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        # All retained handles have now closed, and ordinary writes work.
        with self.manifest.open("ab") as output:
            output.write(b" ")
        self.assertEqual(self.manifest.read_bytes(), original_manifest + b" ")

    def test_source_byte_mutation_fails(self):
        inputs, sha, rec = self.checked()
        inputs["statistics"][0].write_bytes(b"changed underlying source bytes")
        with self.assertRaisesRegex(audit.AuditFailure, "source artifact SHA-256 mismatch"):
            audit.verify_source_artifacts(inputs, sha, rec)

    def test_manifest_mutation_after_pin_fails(self):
        self.payload["max_trade_date"] = "2023-01-01"
        self.manifest.write_text(json.dumps(self.payload), encoding="utf-8")
        with self.assertRaisesRegex(audit.AuditFailure, "source manifest changed"):
            audit.source_inputs()

    def test_forged_manifest_source_path_fails(self):
        self.payload["inputs"]["statistics"]["relative_path"] = "../protected/2024.csv"
        self.save_manifest()
        with self.assertRaisesRegex(audit.AuditFailure, "source input identity changed"):
            audit.source_inputs()

    def test_changed_source_count_fails(self):
        inputs, sha, rec = self.checked()
        rec["statistics"]["source_rows"] -= 1
        with self.assertRaisesRegex(audit.AuditFailure, "source row count"):
            audit.verify_source_artifacts(inputs, sha, rec)

    def test_git_environment_disables_replace_refs(self):
        with patch.object(audit.subprocess, "check_output", return_value=b"blob") as execute:
            self.assertEqual(audit.git_checked("show", "HEAD:config/data_platform.json"), b"blob")
        environment = execute.call_args.kwargs["env"]
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertNotIn("GIT_DIR", environment)

    def test_unbound_transition_commit_fails(self):
        with (
            patch.object(audit, "CONFIG_TRANSITION_COMMIT", "0" * 40),
            self.assertRaisesRegex(audit.AuditFailure, "Git object unavailable"),
        ):
            audit.verify_transition_commit()


if __name__ == "__main__":
    unittest.main()
