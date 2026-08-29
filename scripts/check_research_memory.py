from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(schema_rel: str, path: Path) -> dict:
    schema = load_json(ROOT / schema_rel)
    Draft202012Validator.check_schema(schema)
    value = load_json(path)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"{path.relative_to(ROOT)} violates {schema_rel}: {errors[0].message}")
    return value


def experiment_records() -> list[Path]:
    root = ROOT / "research" / "experiments"
    if not root.exists():
        return []
    completed = sorted(path for path in root.iterdir() if path.is_dir() and (path / "results.json").exists())
    missing_records = [path.name for path in completed if not (path / "record.json").exists()]
    if missing_records:
        raise ValueError(f"completed experiments lack durable record.json: {missing_records}")
    missing_summaries = [path.name for path in completed if not (path / "executive-summary.md").exists()]
    if missing_summaries:
        raise ValueError(f"completed experiments lack required executive-summary.md: {missing_summaries}")
    return [path / "record.json" for path in completed]


def verify_artifact_ref(record_dir: Path, ref: dict, label: str) -> None:
    path = ROOT / ref["path"]
    if not path.is_file():
        raise ValueError(f"{label} target missing: {ref['path']}")
    if path.parent != record_dir:
        raise ValueError(f"{label} must stay inside experiment directory: {ref['path']}")
    if sha256(path) != ref["sha256"]:
        raise ValueError(f"{label} sha256 mismatch: {ref['path']}")


def expected_projections(records: list[Path]) -> tuple[list[dict], list[dict]]:
    decisions: list[dict] = []
    backlog: list[dict] = []
    ids: set[str] = set()
    for path in records:
        record = validate("contracts/experiment_record.schema.json", path)
        rel = path.relative_to(ROOT).as_posix()
        record_dir = path.parent
        if record["experiment_id"] != record_dir.name:
            raise ValueError(f"record experiment_id does not match directory: {rel}")
        verify_artifact_ref(record_dir, record["frozen_setup"], "frozen_setup")
        verify_artifact_ref(record_dir, record["outcome"]["results"], "results")
        verify_artifact_ref(record_dir, record["outcome"]["interpretation"], "interpretation")
        for decision in record["decisions"]:
            if decision["id"] in ids:
                raise ValueError(f"duplicate durable research item id: {decision['id']}")
            ids.add(decision["id"])
            decisions.append({**decision, "source_record": rel})
        for kind in ("recommendations", "open_questions"):
            for item in record[kind]:
                if item["id"] in ids:
                    raise ValueError(f"duplicate durable research item id: {item['id']}")
                ids.add(item["id"])
                if item["status"] == "open":
                    backlog.append({"id": item["id"], "item": item["item"], "kind": "recommendation" if kind == "recommendations" else "open_question", "status": "open", "source_record": rel, "work_ref": item.get("work_ref")})
                elif not item.get("resolution_ref"):
                    raise ValueError(f"closed follow-up lacks resolution_ref: {item['id']}")
    return decisions, backlog


def main() -> int:
    try:
        records = experiment_records()
        expected_decisions, expected_backlog = expected_projections(records)
        decisions = validate("contracts/programme_decisions.schema.json", ROOT / "research/programme-decisions.json")
        backlog = validate("contracts/research_backlog.schema.json", ROOT / "research/research-backlog.json")
        if decisions["decisions"] != expected_decisions:
            raise ValueError("programme-decisions.json drifted from authoritative experiment records")
        if backlog["items"] != expected_backlog:
            raise ValueError("research-backlog.json drifted from authoritative experiment records")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"research-memory: FAILED: {exc}")
        return 2
    print("research-memory: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
