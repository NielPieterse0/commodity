from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOC_SOURCE = ROOT / "config" / "documentation.json"
REFERENCE_ROOT = ROOT / "docs" / "reference"
REFERENCE_GLOBS = (
    "config/*.json",
    "contracts/*.schema.json",
    "data/acquisition-recipes/*.json",
    "research/**/*.json",
    "artifacts/**/*.json",
)
SKIP_REFERENCE = {"config/documentation.json"}
GENERATED_HEADER = "<!-- GENERATED FILE. DO NOT EDIT. Source: {source} -->\n\n"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value).replace("|", "\\|").replace("\n", " ")
    return ""

def title_for(source: str, payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("title", "methodology_id", "programme_id", "registry_id", "recipe_id", "snapshot_id"):
            if payload.get(key):
                return str(payload[key])
    return Path(source).stem.replace("_", " ").replace("-", " ").title()


def render_summary(source: str, payload: Any) -> str:
    lines = [f"# {title_for(source, payload)}", "", f"Source: `{source}`", ""]
    if not isinstance(payload, dict):
        lines += ["## Value", "", f"`{scalar(payload)}`", ""]
        return "\n".join(lines)
    scalars = [(key, scalar(value)) for key, value in payload.items() if scalar(value)]
    if scalars:
        lines += ["## Overview", "", "| Field | Value |", "| --- | --- |"]
        lines += [f"| `{key}` | {value} |" for key, value in scalars]
        lines.append("")
    lines += ["## Structure", "", "| Field | Shape |", "| --- | --- |"]
    for key, value in payload.items():
        if isinstance(value, dict):
            shape = f"object ({len(value)} keys)"
        elif isinstance(value, list):
            shape = f"array ({len(value)} items)"
        else:
            shape = type(value).__name__
        lines.append(f"| `{key}` | {shape} |")
    lines.append("")
    return "\n".join(lines)

def render_models(source: str, payload: dict[str, Any]) -> str:
    text = render_summary(source, payload)
    models = payload.get("models", {})
    if not isinstance(models, dict):
        return text
    lines = [text.rstrip(), "", "## Models", "", "| Model | Enabled | Kind | Family | Architecture |", "| --- | --- | --- | --- | --- |"]
    for name, spec in models.items():
        if not isinstance(spec, dict):
            continue
        lines.append(
            f"| `{name}` | {scalar(spec.get('enabled'))} | {scalar(spec.get('kind'))} | "
            f"{scalar(spec.get('family'))} | {scalar(spec.get('architecture'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_sources(source: str, payload: dict[str, Any]) -> str:
    text = render_summary(source, payload)
    sources = payload.get("sources", {})
    if not isinstance(sources, dict):
        return text
    lines = [text.rstrip(), "", "## Sources", "", "| Source | Provider | Status | Purpose |", "| --- | --- | --- | --- | --- |"]
    for name, spec in sources.items():
        if not isinstance(spec, dict):
            continue
        lines.append(
            f"| `{name}` | {scalar(spec.get('provider'))} | {scalar(spec.get('status'))} | {scalar(spec.get('purpose'))} |"
        )
    lines.append("")
    return "\n".join(lines)

def render_schema(source: str, payload: dict[str, Any]) -> str:
    text = render_summary(source, payload)
    required = payload.get("required", [])
    properties = payload.get("properties", {})
    lines = [text.rstrip(), "", "## Contract", ""]
    if required:
        lines += ["Required fields: " + ", ".join(f"`{item}`" for item in required), ""]
    if isinstance(properties, dict) and properties:
        lines += ["| Property | Type / constraint |", "| --- | --- |"]
        for name, spec in properties.items():
            if not isinstance(spec, dict):
                lines.append(f"| `{name}` | {type(spec).__name__} |")
                continue
            kind = spec.get("type") or ("enum" if "enum" in spec else "constraint")
            if isinstance(kind, list):
                kind = " / ".join(str(item) for item in kind)
            lines.append(f"| `{name}` | {scalar(kind)} |")
        lines.append("")
    return "\n".join(lines)


def render_programme(source: str, payload: dict[str, Any]) -> str:
    text = render_summary(source, payload)
    research_lines = payload.get("research_lines")
    if not isinstance(research_lines, list):
        return text
    lines = [text.rstrip(), "", "## Research lines", "", "| Research line | Status | Interpretation |", "| --- | --- | --- | --- |"]
    for item in research_lines:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| `{scalar(item.get('research_line_id'))}` | {scalar(item.get('status'))} | "
            f"{scalar(item.get('programme_interpretation'))} |"
        )
    lines.append("")
    return "\n".join(lines)

def render_reference(source: str, payload: Any) -> str:
    if source == "config/models.json" and isinstance(payload, dict):
        body = render_models(source, payload)
    elif source == "config/data_sources.json" and isinstance(payload, dict):
        body = render_sources(source, payload)
    elif source.startswith("contracts/") and isinstance(payload, dict):
        body = render_schema(source, payload)
    elif source == "research/programme/programme_evidence_map.json" and isinstance(payload, dict):
        body = render_programme(source, payload)
    else:
        body = render_summary(source, payload)
    return GENERATED_HEADER.format(source=source) + body.rstrip() + "\n"


def reference_sources() -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in REFERENCE_GLOBS:
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel not in SKIP_REFERENCE:
                found[rel] = path
    return [found[key] for key in sorted(found)]


def reference_output(source: Path) -> Path:
    rel = source.relative_to(ROOT)
    return REFERENCE_ROOT / rel.with_suffix(".md")


def render_rule_verification(source: str, payload: dict[str, Any]) -> str:
    lines = [
        "# Rule Verification",
        "",
        "## Deterministically enforced rules",
        "",
        "| Rule | Authority | Verifier | Enforcement |",
        "| --- | --- | --- | --- |",
    ]
    for rule in payload.get("rules", []):
        verifier = " ".join(rule.get("verifier", []))
        lines.append(
            f"| `{rule.get('id')}` | {rule.get('authority')} (`{rule.get('source')}`) | "
            f"`{verifier}` | {rule.get('enforcement')} |"
        )
    lines += [
        "",
        "## Rules requiring external lifecycle state",
        "",
        "These rules cannot be decided from repository bytes alone and remain under live lifecycle authority.",
        "",
    ]
    for rule in payload.get("non_local_rules", []):
        lines.append(f"- `{rule.get('id')}` (`{rule.get('source')}`): {rule.get('reason')}")
    lines.append("")
    return "\n".join(lines)

def render_page(page: dict[str, Any]) -> str:
    kind = page["kind"]
    if kind == "repository_index":
        body = "# Repository Documentation\n\nAll Markdown under `docs/` is generated. Edit the machine-readable source artifacts, then run `scripts/docs/generate_docs.py`.\n\nGoverned change records remain under `.work/changes/` for their full lifecycle, and retained implementation worktrees belong under `.work/worktrees/`. `.work/historical/` is reserved for pre-governance, non-governed, or otherwise non-authoritative legacy material. `docs/` is a generated projection, not an archive or authority source.\n\n## Human-facing pages\n\n- `big-picture.md` — programme state and direction\n- `data-manifest.md` — data architecture and source state\n- `research-methodology.md` — governed research lifecycle\n- `roadmap.md` — maturity progression\n- `THIRD_PARTY.md` — third-party trust and licensing policy\n- `reference/` — direct artifact reference pages\n"
    elif kind == "programme_big_picture":
        p = load_json(ROOT / "research/programme/programme_evidence_map.json")
        h = p["current_helicopter_view"]
        body = "# Commodity: The Big Picture\n\n" + p["mission"] + "\n\n## Where the work came from\n\nThe programme evidence map preserves the research lines, their historical facts, and why each line was selected.\n\n## What we have learned so far\n\n" + "\n".join(f"- {x}" for x in h["known"]) + "\n\n## Still alive\n\n" + "\n".join(f"- {x}" for x in h["mechanisms_still_alive"]) + "\n\n## Missing, not negative\n\n" + "\n".join(f"- {x}" for x in h["missing_not_negative"]) + f"\n\n## How we zoom in\n\n{h['next_branch_reason']}\n"
    elif kind == "data_architecture":
        d = load_json(ROOT / "config/data_sources.json")
        body = "# Data Architecture\n\nSource: `config/data_sources.json`\n\n## Canonical contract\n\n" + f"Grain: `{d['canonical_contract_schema']['grain']}`\n\nRequired columns: " + ", ".join(f"`{x}`" for x in d["canonical_contract_schema"]["required_columns"]) + "\n\n## Current sources\n\n| Source | Provider | Status | Purpose |\n| --- | --- | --- | --- |\n" + "\n".join(f"| `{k}` | {scalar(v.get('provider'))} | {scalar(v.get('status'))} | {scalar(v.get('purpose'))} |" for k,v in d["sources"].items()) + "\n"
    elif kind == "research_methodology":
        m = load_json(ROOT / "config/research_methodology.json")
        body = "# Research Methodology\n\nSource: `config/research_methodology.json`\n\n## Exploratory research\n\nExploratory work uses the active exploratory schema and may investigate feasibility and mechanisms, but it does not establish a confirmatory claim.\n\n## Confirmatory research\n\nConfirmatory work is bound to the preregistration/results contracts and must satisfy the machine execution gates before protected evidence is used.\n\n## Lifecycle\n\n" + "\n".join(f"{i}. `{stage}`" for i,stage in enumerate(m["lifecycle_stages"],1)) + "\n\n## What is immutable\n\nFrozen preregistration and bound evidence identities are not rewritten after observing protected results.\n\n## Confirmatory execution requires\n\n" + "\n".join(f"- `{x}`" for x in m["new_confirmatory_execution_requires"]) + "\n\n## Human and machine responsibilities\n\nHumans select and interpret research questions; machine contracts verify the encoded commitments and evidence bindings. Research evidence does not grant trading permission.\n"
    elif kind == "research_roadmap":
        s = load_json(ROOT / "config/research_stages.json")
        body = "# Commodity Research Roadmap\n\nSource: `config/research_stages.json`\n\n" + " -> ".join(f"`{x}`" for x in s["stages"]) + "\n\nPromotion scope: `research_evidence_only`. Live trading authority remains false.\n"
    elif kind == "rule_verification":
        body = render_rule_verification("config/rule_verification.json", load_json(ROOT / "config/rule_verification.json"))
    elif kind == "third_party_policy":
        t = load_json(ROOT / "config/third_party.json")
        body = "# Third-party Policy\n\nSource: `config/third_party.json`\n\n## Trust classes\n\n" + "\n".join(f"- **{k}** — {v}" for k,v in t["trust_classes"].items()) + "\n\n## Technical sources\n\n| Source | Class | Use |\n| --- | --- | --- |\n" + "\n".join(f"| `{x['source']}` | `{x['class']}` | {x['use']} |" for x in t["technical_sources"]) + f"\n\n## Licensing\n\n{t['licensing_rule']}\n"
    else:
        raise ValueError(f"unknown documentation page kind: {kind}")
    return GENERATED_HEADER.format(source=", ".join(page["sources"])) + body.rstrip() + "\n"


def expected_documents() -> dict[Path, str]:
    source = load_json(DOC_SOURCE)
    expected: dict[Path, str] = {}
    for page in source.get("pages", []):
        expected[ROOT / page["path"]] = render_page(page)
    for artifact in reference_sources():
        rel = artifact.relative_to(ROOT).as_posix()
        expected[reference_output(artifact)] = render_reference(rel, load_json(artifact))
    index_lines = [
        "# Generated Artifact Reference",
        "",
        "This directory is generated from current machine-readable repository artifacts.",
        "",
    ]
    for artifact in reference_sources():
        source_rel = artifact.relative_to(ROOT).as_posix()
        doc_rel = reference_output(artifact).relative_to(ROOT / "docs").as_posix()
        index_lines.append(f"- [`{source_rel}`]({doc_rel.removeprefix('reference/')})")
    expected[REFERENCE_ROOT / "README.md"] = (
        GENERATED_HEADER.format(source="machine-readable repository artifacts")
        + "\n".join(index_lines)
        + "\n"
    )
    return expected


def write_documents(expected: dict[Path, str]) -> None:
    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def check_documents(expected: dict[Path, str]) -> list[str]:
    failures: list[str] = []
    expected_paths = set(expected)
    actual_paths = set((ROOT / "docs").rglob("*.md"))
    for path, content in expected.items():
        if not path.is_file():
            failures.append(f"missing generated document: {path.relative_to(ROOT).as_posix()}")
        elif path.read_text(encoding="utf-8") != content:
            failures.append(f"stale generated document: {path.relative_to(ROOT).as_posix()}")
    for path in sorted(actual_paths - expected_paths):
        failures.append(f"unmanaged markdown under docs/: {path.relative_to(ROOT).as_posix()}")
    return failures

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = expected_documents()
    if args.check:
        failures = check_documents(expected)
        if failures:
            print("documentation-generation: FAILED")
            for failure in failures:
                print(f"- {failure}")
            return 2
        print("documentation-generation: passed")
        return 0
    write_documents(expected)
    print(f"documentation-generation: wrote {len(expected)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
