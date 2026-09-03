from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha256(commit: str, path: str) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"cannot resolve legacy source {path} at {commit}")
    return hashlib.sha256(result.stdout).hexdigest()


def validate(schema_rel: str, path: Path) -> dict:
    schema = load_json(ROOT / schema_rel)
    Draft202012Validator.check_schema(schema)
    value = load_json(path)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"{path.relative_to(ROOT)} violates {schema_rel}: {errors[0].message}")
    return value


def programme_dirs() -> list[Path]:
    root = ROOT / "research" / "programmes"
    if not root.is_dir():
        raise ValueError("research/programmes is missing")
    programmes = sorted(path for path in root.iterdir() if path.is_dir())
    if not programmes:
        raise ValueError("at least one numbered research programme is required")
    return programmes


def experiment_records(programme_dir: Path) -> list[Path]:
    programme = validate("contracts/programme.schema.json", programme_dir / "programme.json")
    if programme["programme_id"] != programme_dir.name:
        raise ValueError(f"programme_id does not match directory: {programme_dir.name}")
    records: list[Path] = []
    for line_ref in programme["line_refs"]:
        line_path = ROOT / line_ref["path"]
        line = validate("contracts/research_line.schema.json", line_path)
        if line["programme_id"] != programme["programme_id"]:
            raise ValueError(f"research line parent mismatch: {line_ref['path']}")
        if line["research_line_id"] != line_ref["research_line_id"] or line_path.parent.name != line["research_line_id"]:
            raise ValueError(f"research line identity mismatch: {line_ref['path']}")
        experiments_root = line_path.parent / "experiments"
        for experiment_ref in line["experiment_refs"]:
            directory = ROOT / experiment_ref["path"]
            if directory.parent != experiments_root or directory.name != experiment_ref["experiment_id"]:
                raise ValueError(f"experiment parent/identity mismatch: {experiment_ref['path']}")
            prereg = directory / "prereg.json"
            legacy = directory / "legacy-record.json"
            if prereg.is_file() == legacy.is_file():
                raise ValueError(f"registered experiment must contain exactly one of prereg.json or legacy-record.json: {experiment_ref['path']}")
            if legacy.is_file():
                legacy_record = validate("contracts/legacy_experiment_record.schema.json", legacy)
                for source in legacy_record["source_artifacts"]:
                    if git_blob_sha256(source["commit"], source["path"]) != source["sha256"]:
                        raise ValueError(f"legacy source hash mismatch: {source['path']}")
                    if source.get("preserved_as"):
                        preserved = directory / source["preserved_as"]
                        if not preserved.is_file() or sha256(preserved) != source["sha256"]:
                            raise ValueError(f"preserved legacy source is not byte-identical: {preserved.relative_to(ROOT)}")
                records.append(legacy)
                continue
            if (directory / "results.json").exists():
                if not (directory / "record.json").is_file():
                    raise ValueError(f"completed experiment lacks durable record.json: {experiment_ref['experiment_id']}")
                if not (directory / "executive-summary.md").is_file():
                    raise ValueError(f"completed experiment lacks required executive-summary.md: {experiment_ref['experiment_id']}")
                records.append(directory / "record.json")
    return records


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
        rel = path.relative_to(ROOT).as_posix()
        record_dir = path.parent
        if path.name == "legacy-record.json":
            record = validate("contracts/legacy_experiment_record.schema.json", path)
            programme = load_json(ROOT / "research/programmes" / record["programme_id"] / "programme.json")
            line = load_json(ROOT / "research/programmes" / record["programme_id"] / "lines" / record["research_line_id"] / "line.json")
        else:
            record = validate("contracts/experiment_record.schema.json", path)
            programme = load_json(ROOT / record["lineage"]["programme_ref"])
            line = load_json(ROOT / record["lineage"]["research_line_ref"])
        if record["experiment_id"] != record_dir.name:
            raise ValueError(f"record experiment_id does not match directory: {rel}")
        if record["programme_id"] != programme["programme_id"]:
            raise ValueError(f"record programme lineage mismatch: {rel}")
        if record["research_line_id"] != line["research_line_id"] or line["programme_id"] != record["programme_id"]:
            raise ValueError(f"record research-line lineage mismatch: {rel}")
        if path.name != "legacy-record.json":
            methodology = load_json(ROOT / "config/research_methodology.json")
            expected_stages = methodology["lifecycle_stages"]
            observed_stages = [item["stage_id"] for item in record["workflow"]]
            if observed_stages != expected_stages:
                raise ValueError(f"record workflow does not mirror authoritative 15-step methodology: {rel}")
            if [item["step"] for item in record["workflow"]] != list(range(1, 16)):
                raise ValueError(f"record workflow steps must be exactly 1..15: {rel}")
            for stage in record["workflow"]:
                if stage["status"] == "complete" and not stage["evidence_refs"]:
                    raise ValueError(f"completed record stage lacks evidence refs: {rel} step {stage['step']}")
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
        for programme_dir in programme_dirs():
            programme = validate("contracts/programme.schema.json", programme_dir / "programme.json")
            evidence = validate("contracts/programme_evidence.schema.json", programme_dir / "evidence-map.json")
            if evidence["programme_id"] != programme["programme_id"] or evidence["research_line_refs"] != programme["line_refs"]:
                raise ValueError(f"programme evidence lineage drifted: {programme_dir.name}")
            records = experiment_records(programme_dir)
            expected_decisions, expected_backlog = expected_projections(records)
            decisions = validate("contracts/programme_decisions.schema.json", programme_dir / "decisions.json")
            backlog = validate("contracts/research_backlog.schema.json", programme_dir / "backlog.json")
            if decisions["programme_id"] != programme["programme_id"] or backlog["programme_id"] != programme["programme_id"]:
                raise ValueError(f"programme projection parent mismatch: {programme_dir.name}")
            missing_decisions = [item for item in expected_decisions if item not in decisions["decisions"]]
            missing_backlog = [item for item in expected_backlog if item not in backlog["items"]]
            if missing_decisions:
                raise ValueError(f"decisions.json omitted authoritative experiment decisions: {programme_dir.name}")
            if missing_backlog:
                raise ValueError(f"backlog.json omitted authoritative experiment follow-ups: {programme_dir.name}")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"research-memory: FAILED: {exc}")
        return 2
    print("research-memory: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
