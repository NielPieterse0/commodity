---
name: develop-docs
description: 'Use when creating, revising, restructuring, or completing technical, operational, product, architecture, policy, planning, specification, or repository documentation where authority, sources, writing quality, review, verification, and closeout must stay aligned. Not for casual chat answers, simple translation, or code-only implementation.'
---

# Develop Docs

Own the documentation lifecycle and evidence chain:

`Understand -> classify -> plan -> implement -> review -> verify -> close`

There is no specification phase. The documentation plan records outcome, audience, authority, sources, boundaries, structure, acceptance evidence, and implementation tasks at level-appropriate depth.

Project instructions and canonical documentation override this skill. This skill owns lifecycle state, classification, default artifact locations, traceability, phase gates, Markdown defaults, and completion. Referenced sub-skills own specialist methods; return here after each finishes.

## Start

1. Read applicable project instructions, document owners, templates, source material, related documents, and current files. Preserve unrelated changes and existing authority.
2. Identify the audience, decision or task the document must support, authoritative claims, source freshness, target location, requested format, boundaries, exclusions, and evidence expected.
3. Discover repository-specific documentation, link, spelling, formatting, schema, example, build, security, release, and Git checks. Never assume tooling.
4. Load [classification](./references/classification.md), state `Documentation level: Small|Medium|Complex` with reasons, and create lifecycle tasks scaled to that level.
5. Resolve the plan and output paths using [artifact contracts](./references/artifact-contracts.md). Existing project locations win.
6. Load [style guide](./references/style-guide.md). Produce `.md` files unless the user or authoritative project convention requests another format.

Classify before editing. Reclassify when authority, audience, source conflicts, document dependencies, operational impact, format, or review needs change. Escalate immediately when any higher-level trigger appears; never downgrade only because the textual diff is short.

## Run The Lifecycle

Load [lifecycle](./references/lifecycle.md) and enforce every applicable gate.

### Small

- Record a compact documentation brief and inline plan.
- Make one bounded Markdown change using existing structure and style.
- Review the final diff against the brief, sources, style rules, and current document context.
- **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion` before any completion claim.

### Medium

- Create an explicit documentation plan with source-to-section traceability and reviewable tasks.
- If audience, structure, scope, or content decisions are unclear, **REQUIRED SUB-SKILL:** Use `superpowers:brainstorming`.
- **REQUIRED SUB-SKILL:** Use `superpowers:writing-plans` for task decomposition, adapting its output to this skill's documentation artifact contract and omitting code-only steps.
- Review completed sections and the whole document set at meaningful checkpoints.
- **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion` before closeout.

### Complex

- Create the detailed documentation plan defined by the artifact contract. Preserve source conflicts and open decisions; do not invent authority or facts.
- If audience, authority, architecture, structure, or trade-offs are not already approved, **REQUIRED SUB-SKILL:** Use `superpowers:brainstorming`.
- **REQUIRED SUB-SKILL:** Use `superpowers:writing-plans` to create independently reviewable document tasks.
- Require human review and approval of the written plan before implementation.
- Select one executor: **REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development` for independent document tasks with subagents, or `superpowers:executing-plans` for inline/separate-session execution.
- Review each authoritative or high-risk boundary and the final document set.
- **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion` before closeout.
- When a branch-based delivery workflow applies and its actions are authorized, **REQUIRED SUB-SKILL:** Use `superpowers:finishing-a-development-branch`.

Pure documentation does not invoke test-driven-development or code review. If the scope changes generators, schemas, executable examples, configuration, or product code, classify that slice separately and **REQUIRED SUB-SKILL:** Use `develop-code`; return here with its current evidence before closing the documentation lifecycle.

Do not reproduce or approximate a sub-skill from memory. Invoke it explicitly, follow it within project authority and this skill's artifact contract, record its result, then return to the current lifecycle gate.

## Style Contract

Write for fast human review and reliable machine extraction:

- default to Markdown (`.md`), one H1 title, logical heading levels, fenced code with language tags, and resolvable links;
- put operative content first; remove introductions that only repeat headings;
- use one claim per sentence or structured block, active voice, named actors, explicit conditions, units, defaults, and exceptions;
- prefer tables for uniform comparisons, numbered lists for ordered actions, bullets for non-sequential items, and fenced YAML/JSON only when structured data improves extraction;
- physically separate binding requirements from rationale or examples; use controlled `MUST`, `MUST NOT`, `SHOULD`, and `MAY` only when the document establishes normative meaning;
- keep identifiers and anchors stable, enumerate completely or mark the set incomplete, and update dependent indexes or references together;
- remove filler, hedge chains, vague qualifiers, ambiguous pronouns, duplicated authority, and unsupported claims;
- keep a sentence only when removing it would change machine extraction or a reader's decision.

The detailed rules and conditional controlled-document conventions are in [style guide](./references/style-guide.md).

## Review Contract

Review the current plan, source material, document diff, related documents, examples, and fresh evidence together. Record findings by severity with paths and evidence. Cover:

- plan/task compliance and source-to-section traceability;
- factual accuracy, source support, provenance, freshness, and authority boundaries;
- audience fit, declared outcome, completeness, exclusions, and decision usefulness;
- information architecture, Markdown correctness, machine readability, and accessibility;
- normative/informative separation, atomic claims, explicit actors/conditions/defaults, and terminology consistency;
- metadata, identifiers, headings, indexes, cross-references, links, anchors, examples, and commands;
- security, privacy, secrets, unsafe operational guidance, and sensitive-data handling;
- duplication, contradictions, stale statements, unnecessary complexity, and scope discipline;
- freshness and sufficiency of verification evidence;
- publication, rollback, recovery, versioning, and downstream impact when applicable.

When available and applicable, **REQUIRED SUB-SKILL:** Use `security-review` for sensitive documentation. Use `code-review`, `simpler-code`, or `smarter-code` only for embedded code, executable examples, or docs-as-code implementation covered by `develop-code`. Their absence never converts an unperformed specialist review into a pass.

Fix blocking findings, rerun affected checks, and re-review the changed scope. An edit after review invalidates the affected review. An edit after verification invalidates the affected evidence.

## Close Gate

Close only when the plan and implemented document set reconcile, authoritative claims remain supported, blocking findings are resolved, required checks pass on the current state, output format matches the request, recovery is understood, and every remaining item is explicitly optional or out of scope.

Report the documentation level, plan/output paths, sources used, implemented scope, review findings or clean result, exact verification commands and outcomes, skipped checks, publication/recovery notes, residual risks, and optional follow-ups. Never describe unverified or unsupported documentation as complete or authoritative.
