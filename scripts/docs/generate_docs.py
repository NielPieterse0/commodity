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
    elif source.endswith("/evidence-map.json") and source.startswith("research/programmes/") and isinstance(payload, dict):
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
            if rel.startswith("research/.temp/"):
                continue
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

def render_governed_research_workflow_details(methodology: dict[str, Any]) -> str:
    sections: list[str] = []
    labels = {
        "required_inputs": "Required inputs",
        "required_questions": "Questions this step must answer",
        "scope_when_relevant": "Scope when relevant",
        "refresh_rules": "Refresh rules",
        "evidence_inputs": "Evidence inputs",
        "history_synthesis_sources": "Accumulated programme-history sources",
        "programme_synthesis_lenses": "Programme-level interpretation lenses",
        "history_reasoning_rules": "History reasoning rules",
        "governing_principles": "Governing principles",
        "evidence_exposure_hierarchy": "Evidence-exposure hierarchy",
        "legacy_evidence_rules": "Legacy evidence and migration rules",
        "gap_rules": "Gap rules",
        "mechanism_rules": "Mechanism rules",
        "hypothesis_rules": "Hypothesis rules",
        "expectation_rules": "Expected/disconfirming observation rules",
        "gate_sequence": "Gate sequence",
        "mepi_rules": "MEPI rules",
        "detectability_rules": "Power and detectability rules",
        "required_dimensions": "Required dimensions",
        "stability_rules": "Stability and boundary rules",
        "selection_inputs": "Selection inputs",
        "selection_rules": "Selection rules",
        "slice_rules": "Slice rules",
        "review_scope": "Detailed review scope",
        "rules": "Rules",
        "design_elements": "Design elements",
        "gate_inputs": "Gate inputs",
        "dependence_rules": "Dependence and effective-information rules",
        "confirmation_capacity_rules": "Confirmation-capacity and split rules",
        "failure_actions": "Failure actions",
        "governed_change_requirements": "Governed repository-change requirements",
        "implementation_quality_gate": "Implementation quality gate",
        "freeze_gate": "Freeze gate",
        "preregistration_freeze_requirements": "What preregistration must freeze",
        "benchmark_rules": "Benchmark rules",
        "confirmation_data_rules": "Reserved-confirmation rules",
        "binding_semantics": "Preregistration binding semantics",
        "scientific_artifact_model": "Scientific artifact and projection model",
        "automation_and_enforcement": "Automation and enforcement",
        "execution_rules": "Execution rules",
        "truth_classes": "Verification truth classes",
        "verification_requirements": "Verification requirements",
        "leakage_controls": "Domain-specific leakage controls",
        "result_preservation_rules": "Result preservation and lineage rules",
        "interpretation_inputs": "Interpretation inputs",
        "coherence_trigger_classes": "Symmetric coherence/anomaly trigger classes",
        "coherence_rules": "Coherence rules",
        "triangulation_rules": "External triangulation rules",
        "hierarchy_retrace": "Hierarchy retrace: L4 back to L0",
        "truth_class_rules": "Truth-class rules",
        "evidence_level_definitions": "E0–E6 evidence definitions",
        "evidence_rules": "Evidence-level rules",
        "orthogonal_status": "Orthogonal experiment status",
        "programme_inference_rules": "Programme-level inference rules",
        "programme_conclusion_questions": "Programme conclusion questions",
        "update_rules": "Programme evidence update rules",
        "disposition_rules": "Disposition and stopping rules",
        "documentation_model": "Confirmatory and exploratory documentation model",
        "record_rules": "Compact durable record rules",
        "executive_summary_requirements": "Mandatory operator executive summary",
    }
    for detail in methodology.get("governed_research_workflow_details", []):
        lines = [
            f"## Step {detail['step']}: {detail['title']}",
            "",
            f"**Zoom level:** `{detail['zoom_level']}`",
            "",
            f"**Purpose:** {detail['purpose']}",
        ]
        if detail.get("north_star_source"):
            lines += ["", f"**L0 authority:** `{detail['north_star_source']}`"]
        if detail.get("core_question"):
            lines += ["", f"**Core question:** {detail['core_question']}"]
        if detail.get("repo_transition"):
            lines += ["", f"**Repository transition:** {detail['repo_transition']}"]
        if detail.get("redesign_rule"):
            lines += ["", f"**Redesign rule:** {detail['redesign_rule']}"]
        for key, label in labels.items():
            values = detail.get(key)
            if values:
                lines += ["", f"### {label}", "", *(f"- {item}" for item in values)]
        if detail.get("required_output"):
            output = detail["required_output"]
            lines += ["", "### Required output", "", f"Artifact: `{output['artifact_ref']}`", "", *(f"- `{item}`" for item in output["fields"])]
        if detail.get("methodological_canon_rule"):
            lines += ["", "### Methodological canon", "", detail["methodological_canon_rule"]]
            if detail.get("methodological_canon_source"):
                lines += ["", f"Source: `{detail['methodological_canon_source']}`"]
        if detail.get("programme_reasoning_output"):
            lines += ["", "### Programme reasoning output", "", detail["programme_reasoning_output"]]
        if detail.get("environment_reproduction"):
            reproduction = detail["environment_reproduction"]
            lines += [
                "",
                "### Environment identity and reproduction semantics",
                "",
                f"- **Logical reproduction:** {reproduction['logical_reproduction']}",
                f"- **Byte reproduction:** {reproduction['byte_reproduction']}",
                "",
                "Required identity:",
                "",
                *(f"- {item}" for item in reproduction["required_identity"]),
                "",
                reproduction["rule"],
            ]
        if detail.get("mepi_definition"):
            lines += ["", "### MEPI — Minimum Effect of Practical Importance", "", detail["mepi_definition"]]
        if detail.get("mepi_types"):
            lines += ["", *(f"- `{key}`: {value}" for key, value in detail["mepi_types"].items())]
        if detail.get("step") == 8:
            dataset_policy = load_json(ROOT / "config" / "research_dataset.json")["evaluation_evidence_policy"]
            reserved = dataset_policy["reserved_confirmation"]
            fraction_pct = reserved["planning_fraction"] * 100
            lines += [
                "",
                "### Canonical evaluation-data policy",
                "",
                "- Sequence: " + " → ".join(dataset_policy["sequence"]) + ".",
                f"- Reserved confirmation planning default: {fraction_pct:g}% of the usable chronological sample, using the latest usable block; this is a planning default, not a universal rule.",
                "- The actual share must be justified by the experiment's horizon, dependence, power, regime coverage, usable history and remaining confirmation capacity.",
                "- Reserved-confirmation identity may be known; its outcomes must not influence pre-freeze design, fitting or selection.",
            ]
        if detail.get("refresh_trigger_source"):
            lines += ["", f"**Refresh triggers:** `{detail['refresh_trigger_source']}`"]
        lines += ["", f"**Completion condition:** {detail['completion_condition']}"]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def render_page(page: dict[str, Any]) -> str:
    kind = page["kind"]
    if kind == "repository_index":
        body = "# Repository Documentation\n\nAll Markdown under `docs/` is generated. Edit the machine-readable source artifacts, then run `scripts/docs/generate_docs.py`.\n\nGoverned change records remain under `.work/changes/` for their full lifecycle, and retained implementation worktrees belong under `.work/worktrees/`. `.work/historical/` is reserved for pre-governance, non-governed, or otherwise non-authoritative legacy material. `docs/` is a generated projection, not an archive or authority source.\n\n## Human-facing pages\n\n- `big-picture.md` — programme state and direction\n- `data-manifest.md` — data architecture and source state\n- `research-methodology.md` — governed research lifecycle\n- `roadmap.md` — maturity progression\n- `THIRD_PARTY.md` — third-party trust and licensing policy\n- `reference/` — direct artifact reference pages\n"
    elif kind == "repository_big_picture":
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        commodity_start = agents.index("# Commodity")
        repository_start = agents.index("## Repository")
        objective_start = agents.index("## Primary objective")
        authority_start = agents.index("## Authority and ownership")
        body = (
            agents[commodity_start:repository_start].rstrip()
            + "\n\n"
            + agents[objective_start:authority_start].rstrip()
            + "\n"
        )
    elif kind == "data_architecture":
        d = load_json(ROOT / "config/data_sources.json")
        body = "# Data Architecture\n\nSource: `config/data_sources.json`\n\n## Canonical contract\n\n" + f"Grain: `{d['canonical_contract_schema']['grain']}`\n\nRequired columns: " + ", ".join(f"`{x}`" for x in d["canonical_contract_schema"]["required_columns"]) + "\n\n## Current sources\n\n| Source | Provider | Status | Purpose |\n| --- | --- | --- | --- |\n" + "\n".join(f"| `{k}` | {scalar(v.get('provider'))} | {scalar(v.get('status'))} | {scalar(v.get('purpose'))} |" for k,v in d["sources"].items()) + "\n"
    elif kind == "research_methodology":
        m = load_json(ROOT / "config/research_methodology.json")
        hierarchy = m["research_hierarchy"]
        hierarchy_rows = "\n".join(
            f"- **{item['level']} — {item['name']}:** {item['definition']}"
            for item in hierarchy["levels"]
        )
        flow_rows = "\n".join(
            f"| {item['step']} | **{item['zoom_level']}** | {item['stage']} | {item['required_outcome']} |"
            for item in m["governed_research_workflow"]
        )
        details = render_governed_research_workflow_details(m)
        body = "# Research Methodology\n\nSource: `config/research_methodology.json`\n\n## Big-picture research hierarchy\n\nEvery governed research artifact declares a zoom level.\n\n" + hierarchy_rows + "\n\n**North Star rule:** " + hierarchy["north_star_rule"] + "\n\n**Promotion rule:** " + hierarchy["promotion_rule"] + "\n\n## Governed research workflow\n\nThis is the one authoritative end-to-end research workflow. Every governed experiment/run enters this 15-step workflow and may stop early only through the governed disposition/revisit rules.\n\n| Step | Zoom level | Workflow stage | Required outcome |\n| ---: | --- | --- | --- |\n" + flow_rows + "\n\n# Detailed governed research workflow\n\n" + details + "\n\n## Exploratory research\n\nExploratory work uses the active exploratory schema and may investigate feasibility and mechanisms, but it does not establish a confirmatory claim.\n\n## Confirmatory research\n\nConfirmatory work is bound to the preregistration/results contracts and must satisfy the machine execution gates before protected evidence is used.\n\n## What is immutable\n\nFrozen preregistration and bound evidence identities are not rewritten after observing protected results.\n\n## Confirmatory execution requires\n\n" + "\n".join(f"- `{x}`" for x in m["new_confirmatory_execution_requires"]) + "\n\n## Human and machine responsibilities\n\nHumans select and interpret research questions; machine contracts verify the encoded commitments and evidence bindings. Research evidence does not grant trading permission.\n"
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
    actual_paths = {
        path
        for path in (ROOT / "docs").rglob("*.md")
        if not path.relative_to(ROOT / "docs").as_posix().startswith(("niel/", ".temp/"))
    }
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
