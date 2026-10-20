"""Fail-closed, read-only post-publisher audit of pre-2023 market table bytes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from commodity.market_truth.protected_reads import protected_table_reads

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / ".work" / "runtime" / "market_truth_development"
BASE = DATA / "market-truth-full-2010-2022-refactor-v3"
CURRENT = DATA / "rebuild-postpublisher" / "dataset"
SOURCE = DATA / "source-manifest-full-2010-2022-curated.json"
BASE_SHA = "6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605"
SOURCE_SHA = "8a86789673c8458c5745f14b550f3c16b6e4885cac026578cb2989cbc80e5240"
COUNTS = {"definitions": 525810, "bars": 103793, "statistics": 1177700}
SOURCE_INPUTS = {
    "definitions": ("definitions-full-2010-2022.csv", "definition", 525810),
    "bars": ("bars-full-2010-2022.csv", "ohlcv-1d", 103793),
    "statistics": ("statistics-full-2010-2022-curated.csv", "statistics", 2282697),
}
TABLE_HASHES = {
    "definitions": "b803deb0b88d7c0f57625fd46cfa4537e902dd3951cf04aeeba84f95f5dbf4d8",
    "bars": "d7b72c4295e67a2c60f64cc1e23c9904885724b096d59d949ea6729e18f9a5ec",
    "statistics": "08238152f29f5e6c2296e098671448b0cb36470626faa421c6a461140f034e8b",
}
CONFIG_FILES = frozenset({"config/data_platform.json", "config/data_sources.json"})
# The baseline predates ec82d10, which added independent-cadence source-time
# policy without changing the historical Parquet observations. Both sides
# are immutable SHA-256 pins; any other configuration transition fails closed.
BASELINE_CONFIG_HASHES = {
    "config/data_platform.json": "b91a67ce4d0d993245c70117575e17d8b30818be6dea0ed065189cfce2c35549",
    "config/data_sources.json": "d62d087ad412f7f4af910f05a399ccb3badfe8ad0e0a5dac34e29986514354c8",
}
CURRENT_CONFIG_HASHES = {
    "config/data_platform.json": "d9e05a7ff5c57875e00572fefdc2abae883dfa40ac65c92fa00bf95f666bd7b0",
    "config/data_sources.json": "d62d087ad412f7f4af910f05a399ccb3badfe8ad0e0a5dac34e29986514354c8",
}
CONFIG_TRANSITION_COMMIT = "ec82d10dc71697c87e7db7f2548e6bb0a25b3ce6"
# The transition commit also includes change-specific temporal code/tests. Do
# not misdescribe it as a one-file commit or as independently signed authority.
TRANSITION_CHANGED_PATHS = frozenset({
    ".work/changes/482-data-phase2-market-truth/closeout.md",
    ".work/changes/482-data-phase2-market-truth/implementation-evidence.json",
    ".work/changes/482-data-phase2-market-truth/tasks.md",
    ".work/changes/482-data-phase2-market-truth/temporal-source-resolution.json",
    "config/data_platform.json",
    "contracts/data_platform.schema.json",
    "scripts/data/recover_ng_unreferenced_statistics.py",
    "src/commodity/temporal_alignment.py",
    "tests/data_platform/test_temporal_alignment.py",
    "tests/data_platform/test_unreferenced_statistics_recovery.py",
})
TRANSFORM_HASHES = {
    "core.py": "06a6c1a8e41e74509c4baf003eb51ba63c0c20c4b8b133c93322fb5d5bfd33a7",
    "ng.py": "f7bda28aabf4d0fbad0d1ba8b99f5aa0bc95c7ae7eb2afa8d9d1f9c33d36bc19",
    "query.py": "9817bd50df6b3286bf83afb2fb92656d32945e6da002e7bae6cc124fdac64cd6",
    "protected_reads.py": "c05095d1f8ffa5f46f09d17c943a94f654896d7a87f41c461cb43ff32f18f19f",
    "streaming.py": "8d2b8921b7a040391fd53e94a4bf158c1172b264c9f553378091785fd08b0951",
    "revision.py": "c05c3a70af511bcd8f842b34f36a0db62228601f922934cd674aa304ccef979b",
    "errors.py": "5a49014d4135eef20122b19b906cb944490362cdbdfa07e1b3e5b03be593fdf8",
    "attestation.py": "7ab7efcf4b62cefd879bbc20f7d0ceceb5d612a3771ff3b2fae0a05958298a8d",
}


class AuditFailure(RuntimeError):
    """A required immutable identity or expected output did not match."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AuditFailure(message)


def sha(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), "source file unavailable")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_inputs() -> dict[str, tuple[Path, str]]:
    """Only interpret the already-locked and byte-pinned source manifest."""
    with SOURCE.open("rb") as reader:
        raw = reader.read(1024 * 1024 + 1)
    require(len(raw) <= 1024 * 1024, "source manifest oversized")
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA, "source manifest changed")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditFailure("invalid pinned source manifest") from exc
    require(isinstance(payload, dict) and set(payload) == {
        "schema_version", "dataset", "product_code", "evidence_class",
        "protected_confirmation_accessed", "max_trade_date", "inputs",
    }, "source manifest schema changed")
    require(
        payload["schema_version"] == 1
        and payload["dataset"] == "GLBX.MDP3"
        and payload["product_code"] == "NG"
        and payload["evidence_class"] == "development"
        and payload["protected_confirmation_accessed"] is False
        and payload["max_trade_date"] == "2022-12-31",
        "source manifest provenance/boundary changed",
    )
    records = payload["inputs"]
    require(isinstance(records, dict) and set(records) == set(SOURCE_INPUTS),
            "unexpected source input family")
    paths = {}
    for family, (filename, schema, rows) in SOURCE_INPUTS.items():
        item = records[family]
        require(isinstance(item, dict) and set(item) == {
            "relative_path", "row_count", "schema", "sha256"
        }, "source record schema changed")
        require(item["relative_path"] == filename
                and re.fullmatch(r"[A-Za-z0-9_.-]+[.]csv", filename)
                and item["schema"] == schema
                and type(item["row_count"]) is int
                and item["row_count"] == rows,
                "source input identity changed")
        digest = item["sha256"]
        require(isinstance(digest, str) and re.fullmatch("[0-9a-f]{64}", digest),
                "source input digest invalid")
        paths[family] = (DATA / filename, digest)
    return paths


def verify_source_artifacts(
    inputs: dict[str, tuple[Path, str]],
    source_hashes: dict,
    reconciliation: dict,
) -> None:
    """Rehash original CSV bytes while source and ancestor handles are retained."""
    require(source_hashes == {family: digest for family, (_, digest) in inputs.items()},
            "source manifest and table source digests disagree")
    require(isinstance(reconciliation, dict) and set(reconciliation) == set(SOURCE_INPUTS),
            "source reconciliation families changed")
    for family, (path, digest) in inputs.items():
        require(isinstance(reconciliation[family], dict)
                and reconciliation[family].get("source_rows") == SOURCE_INPUTS[family][2],
                "source row count declaration changed")
        require(sha(path) == digest, "source artifact SHA-256 mismatch: " + family)


def git_checked(*args: str) -> bytes:
    """Read local Git objects with replacement refs and inherited Git overrides off."""
    environment = {
        key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }
    environment.update({"GIT_NO_REPLACE_OBJECTS": "1", "GIT_CONFIG_NOSYSTEM": "1"})
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), *args],
            stderr=subprocess.DEVNULL, env=environment, timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AuditFailure("configuration transition Git object unavailable") from exc


def verify_transition_commit() -> None:
    """Pin exact local Git object ancestry, paths and both config blob pairs."""
    for filename in sorted(CONFIG_FILES):
        for revision, expected in (
            (CONFIG_TRANSITION_COMMIT + "^", BASELINE_CONFIG_HASHES[filename]),
            (CONFIG_TRANSITION_COMMIT, CURRENT_CONFIG_HASHES[filename]),
        ):
            data = git_checked("show", revision + ":" + filename)
            require(hashlib.sha256(data).hexdigest() == expected,
                    "configuration transition commit does not match pinned blobs")
    changed = git_checked(
        "diff-tree", "--no-commit-id", "--name-only", "-r", CONFIG_TRANSITION_COMMIT
    ).decode("utf-8").splitlines()
    require(set(changed) == TRANSITION_CHANGED_PATHS and len(changed) == len(TRANSITION_CHANGED_PATHS),
            "configuration transition commit changed-path set differs")
    git_checked("merge-base", "--is-ancestor", CONFIG_TRANSITION_COMMIT, "HEAD")


def audit() -> dict:
    """Hold protected Windows file and ancestor handles for the whole audit."""
    files = [
        BASE / "manifest.json", SOURCE, CURRENT / "manifest.json",
        *(CURRENT / (family + ".parquet") for family in COUNTS),
        *(ROOT / "src" / "commodity" / "market_truth" / name
          for name in TRANSFORM_HASHES),
        *(ROOT / name for name in CONFIG_FILES),
    ]
    # This guard excludes writers, file replacement, and reparse ancestors
    # throughout all pathname opens. Other platforms deliberately fail closed.
    with protected_table_reads(files):
        inputs = source_inputs()
        # Keep the manifest and every ancestor protected while adding checked
        # source CSV handles: no gap for a path replacement during the audit.
        with protected_table_reads([path for path, _ in inputs.values()]):
            return _audit_locked(inputs)


def _audit_locked(inputs: dict[str, tuple[Path, str]]) -> dict:
    # A compromised or re-targeted ancestor may not redirect us into a
    # protected archive before the manifest's metadata can be checked.
    for directory in (DATA, BASE, CURRENT.parent, CURRENT):
        require(directory.is_dir() and not directory.is_symlink(), "dataset root redirected")
    base_path = BASE / "manifest.json"
    current_path = CURRENT / "manifest.json"
    for path, parent in ((base_path, BASE), (current_path, CURRENT)):
        require(path.is_file() and not path.is_symlink(), "manifest redirected")
        require(path.resolve(strict=True).parent == parent.resolve(strict=True), "manifest escaped")
    base_bytes = base_path.read_bytes()
    require(hashlib.sha256(base_bytes).hexdigest() == BASE_SHA, "baseline manifest changed")
    require(sha(SOURCE) == SOURCE_SHA, "approved source manifest changed")
    old = json.loads(base_bytes.decode("utf-8"))
    raw = current_path.read_bytes()
    new = json.loads(raw.decode("utf-8"))
    require(new.get("schema_version") == 1, "schema mismatch")
    require(new.get("dataset_scope") == "development_pre2023", "wrong scope")
    require(new.get("protected_confirmation_accessed") is False, "protected access")
    require(new.get("source_manifest_sha256") == SOURCE_SHA, "source mismatch")
    require(new.get("source_sha256") == old["source_sha256"], "input hashes changed")
    require(new.get("source_row_reconciliation") == old["source_row_reconciliation"], "source counts changed")
    verify_source_artifacts(inputs, new["source_sha256"], new["source_row_reconciliation"])
    require(new.get("tables") == old["tables"], "table manifest changed")
    declared = {key: value for key, value in new.items() if key != "content_sha256"}
    digest = hashlib.sha256(
        json.dumps(declared, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    require(digest == new.get("content_sha256"), "content identity changed")
    require(set(new["tables"]) == set(COUNTS), "missing or additional tables")
    for family, expected in TABLE_HASHES.items():
        details = new["tables"][family]
        location = CURRENT / (family + ".parquet")
        require(details["relative_path"] == location.name, "table path changed")
        require(details["rows"] == COUNTS[family], "table row count changed")
        require(details["bytes"] == location.stat().st_size, "table size changed")
        require(sha(location) == expected == details["sha256"], "table byte mismatch")
    require(new.get("transform_sha256") == TRANSFORM_HASHES, "transform source pin changed")
    for filename, expected in sorted(TRANSFORM_HASHES.items()):
        location = ROOT / "src" / "commodity" / "market_truth" / filename
        require(sha(location) == expected, "transform file bytes changed")
    require(set(new.get("config_sha256", {})) == CONFIG_FILES, "config set changed")
    require(old.get("config_sha256") == BASELINE_CONFIG_HASHES, "unexpected baseline config identity")
    require(new["config_sha256"] == CURRENT_CONFIG_HASHES, "unexpected current config identity")
    for filename in sorted(CONFIG_FILES):
        require(sha(ROOT / filename) == CURRENT_CONFIG_HASHES[filename], "config bytes changed")
    verify_transition_commit()
    return {
        "schema_version": 1,
        "issue": 482,
        "state": "PASS_PRIVATE_DEVELOPMENT_REBUILD_NOT_RESEARCH_ADMISSION",
        "source_manifest_sha256": SOURCE_SHA,
        "new_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "new_content_sha256": new["content_sha256"],
        "previous_content_sha256": old["content_sha256"],
        "parquet_sha256": TABLE_HASHES,
        "parquet_rows": COUNTS,
        "same_three_table_bytes": True,
        "source_artifact_sha256": {family: digest for family, (_, digest) in inputs.items()},
        "source_artifacts_independently_hashed_under_protection": True,
        "configuration_identity": {
            "baseline": BASELINE_CONFIG_HASHES,
            "current": CURRENT_CONFIG_HASHES,
            "git_blob_verified_transition_commit": CONFIG_TRANSITION_COMMIT,
            "reason": "independent_cadence_alignment_policy_added_without_parquet_value_changes",
        },
        "protected_confirmation_accessed": False,
        "official_reference_dates_promoted": 0,
        "research_fitness_approved": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True, indent=2))
