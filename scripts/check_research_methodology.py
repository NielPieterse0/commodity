from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commodity.research_methodology import (
    MethodologyError,
    canonical_prereg_sha256,
    parse_interpretation_markdown,
    validate_inference_ledger,
    validate_programme_context,
    verify_interpretation_metadata,
    verify_results,
)

GATES = (
    "experiment-schema",
    "experiment-freeze-integrity",
    "experiment-verification",
    "programme-inference-integrity",
)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def validate_document_value(schema_path: Path, value: dict) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"value violates {schema_path.name}: {details}")


def validate_document(schema_path: Path, document_path: Path) -> None:
    try:
        validate_document_value(schema_path, load_json(document_path))
    except ValueError as exc:
        raise ValueError(f"{document_path.relative_to(ROOT)}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk.replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def load_json_at_commit(commit_sha: str, path: str) -> tuple[dict, str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit_sha}:{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"cannot resolve {path} at bound commit {commit_sha}")
    return json.loads(result.stdout.decode("utf-8")), hashlib.sha256(result.stdout).hexdigest()


def check_schema() -> None:
    schema_names = (
        "prereg.schema.json", "results.schema.json", "programme_evidence.schema.json",
        "programme_inference.schema.json", "sealed_windows.schema.json",
        "exploratory_run.schema.json", "interpretation_metadata.schema.json",
    )
    for name in schema_names:
        Draft202012Validator.check_schema(load_json(ROOT / "contracts" / name))
    validate_document(ROOT / "contracts/programme_evidence.schema.json", ROOT / "config/programme_evidence_map.json")
    validate_document(ROOT / "contracts/programme_inference.schema.json", ROOT / "config/programme_inference_ledger.json")
    validate_document(ROOT / "contracts/sealed_windows.schema.json", ROOT / "config/sealed_windows.json")
    methodology = load_json(ROOT / "config/research_methodology.json")
    if methodology.get("issue") != 249 or methodology.get("execution_authority") is not False:
        raise ValueError("research_methodology.json must retain #249 identity and no trading authority")
    migration = load_json(ROOT / "docs/development/249-hypothesis-experiment-methodology/legacy-migration.json")
    for item in migration.get("legacy_authority", []):
        path = ROOT / item["path"]
        if sha256_file(path) != item["sha256"]:
            raise ValueError(f"legacy V1/V2 authority changed after #249 adoption: {item['path']}")
    exploratory_root = ROOT / "research" / "exploratory"
    if exploratory_root.exists():
        for record_path in sorted(exploratory_root.glob("*.json")):
            validate_document(ROOT / "contracts/exploratory_run.schema.json", record_path)
            record = load_json(record_path)
            serialized = json.dumps(record, sort_keys=True).lower()
            if "sealed_window" in serialized or "sealed confirmation" in serialized:
                raise ValueError(f"exploratory record references sealed confirmation: {record_path.relative_to(ROOT)}")


def experiment_dirs() -> list[Path]:
    root = ROOT / "research" / "experiments"
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def check_freeze_integrity() -> None:
    for directory in experiment_dirs():
        prereg = directory / "prereg.json"
        freeze = directory / "freeze.json"
        if freeze.exists() and not prereg.exists():
            raise ValueError(f"freeze exists without preregistration: {freeze.relative_to(ROOT)}")
        if prereg.exists():
            validate_document(ROOT / "contracts/prereg.schema.json", prereg)
        if not freeze.exists():
            continue
        record = load_json(freeze)
        if record.get("frozen") is not True:
            raise ValueError(f"freeze record is not frozen: {freeze.relative_to(ROOT)}")
        binding = record.get("binding") or {}
        if binding.get("preregistration_remote_bound") != "verified":
            raise ValueError(f"freeze lacks verified remote binding: {freeze.relative_to(ROOT)}")
        prereg_sha = record.get("prereg_sha256")
        if prereg_sha != canonical_prereg_sha256(load_json(prereg)):
            raise ValueError(f"freeze preregistration identity mismatch: {freeze.relative_to(ROOT)}")
        if binding.get("prereg_sha256") != prereg_sha:
            raise ValueError(f"remote binding preregistration identity mismatch: {freeze.relative_to(ROOT)}")
        context = record.get("programme_context") or {}
        if context.get("status") != "selected_and_feasible":
            raise ValueError(f"freeze lacks selected programme context: {freeze.relative_to(ROOT)}")
        commit_sha = binding.get("commit_sha")
        context_path = context.get("path")
        if not isinstance(commit_sha, str) or not isinstance(context_path, str):
            raise TypeError(f"freeze lacks bound programme context identity: {freeze.relative_to(ROOT)}")
        programme_at_freeze, programme_sha = load_json_at_commit(commit_sha, context_path)
        if programme_sha != context.get("sha256"):
            raise ValueError(f"freeze programme-context hash mismatch: {freeze.relative_to(ROOT)}")
        validate_programme_context(load_json(prereg), programme_at_freeze)


def check_verification() -> None:
    for directory in experiment_dirs():
        prereg_path = directory / "prereg.json"
        results_path = directory / "results.json"
        interpretation_path = directory / "interpretation.md"
        summary_path = directory / "executive-summary.md"
        if results_path.exists() and not prereg_path.exists():
            raise ValueError(f"results exist without preregistration: {results_path.relative_to(ROOT)}")
        if not results_path.exists():
            if interpretation_path.exists() or summary_path.exists():
                raise ValueError(f"interpretation/summary exists without results: {directory.relative_to(ROOT)}")
            continue
        validate_document(ROOT / "contracts/results.schema.json", results_path)
        prereg = load_json(prereg_path)
        results = load_json(results_path)
        verify_results(prereg, results)
        if interpretation_path.exists():
            text = interpretation_path.read_text(encoding="utf-8")
            metadata, _ = parse_interpretation_markdown(text)
            validate_document_value(ROOT / "contracts/interpretation_metadata.schema.json", metadata)
            verify_interpretation_metadata(metadata, prereg, results)
        if summary_path.exists() and not interpretation_path.exists():
            raise ValueError(f"executive summary exists without interpretation: {summary_path.relative_to(ROOT)}")


def check_programme_inference() -> None:
    ledger = load_json(ROOT / "config/programme_inference_ledger.json")
    validate_inference_ledger(ledger)
    sealed = load_json(ROOT / "config/sealed_windows.json")
    ids: set[str] = set()
    for window in sealed.get("windows", []):
        window_id = window.get("sealed_window_id")
        if window_id in ids:
            raise ValueError(f"duplicate sealed_window_id: {window_id}")
        ids.add(window_id)
        openings = window.get("openings", [])
        if len(openings) > int(window.get("permitted_openings", 0)):
            raise ValueError(f"sealed window over-opened: {window_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=GATES, required=True)
    args = parser.parse_args()
    checks = {
        "experiment-schema": check_schema,
        "experiment-freeze-integrity": check_freeze_integrity,
        "experiment-verification": check_verification,
        "programme-inference-integrity": check_programme_inference,
    }
    try:
        checks[args.check]()
    except (OSError, TypeError, ValueError, MethodologyError, json.JSONDecodeError) as exc:
        print(f"{args.check}: FAILED: {exc}")
        return 2
    print(f"{args.check}: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
