---
name: develop-code
description: 'Use when creating, changing, fixing, refactoring, or completing production code where requirements, planning, implementation, review, verification, and closeout must stay aligned. Applies to bounded fixes through cross-component or high-risk delivery; not for read-only explanation, standalone review with no requested changes, or pure research.'
---

# Develop Code

Own the lifecycle and evidence chain:

`Understand -> classify -> specify -> plan -> implement -> review -> verify -> close`

Project instructions and canonical repository documentation override this skill. This skill owns lifecycle state, classification, default artifact locations, traceability, gates, and completion. Referenced sub-skills own specialist methods; return here after each finishes.

## Start

1. Read applicable project instructions and authoritative docs. Inspect current state and preserve unrelated changes.
2. Discover the repository's test, build, lint, security, release, documentation, and Git conventions. Never assume a language or package manager.
3. Define the requested outcome, boundaries, exclusions, constraints, unknowns, recovery needs, and evidence expected.
4. Load [classification](./references/classification.md), state `Development level: Small|Medium|Complex` with reasons, and create lifecycle tasks scaled to that level.
5. Resolve artifact locations using [artifact contracts](./references/artifact-contracts.md). Existing repository locations win; otherwise use the defaults there.

Classify before implementation. Reclassify when scope, uncertainty, reversibility, data impact, or risk changes. Escalate immediately when any higher-level trigger appears; never downgrade only because the diff is small.

## Run The Lifecycle

Load [lifecycle](./references/lifecycle.md) and enforce every applicable gate.

### Small

- Write a compact specification and inline plan.
- Implement one bounded change.
- For a behavior change, **REQUIRED SUB-SKILL:** Use `superpowers:test-driven-development`.
- Review the final diff against the brief, then verify with current evidence.
- **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion` before any completion claim.

### Medium

- Create an explicit specification and implementation plan with traceable reviewable tasks.
- If requirements or design are unclear, **REQUIRED SUB-SKILL:** Use `superpowers:brainstorming`.
- **REQUIRED SUB-SKILL:** Use `superpowers:writing-plans` to produce the plan within this skill's artifact contract.
- For behavior changes, **REQUIRED SUB-SKILL:** Use `superpowers:test-driven-development`.
- At review checkpoints, **REQUIRED SUB-SKILL:** Use `superpowers:requesting-code-review` when available; otherwise perform the review contract directly and disclose the missing specialist.
- **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion` before closeout.

### Complex

- Create the detailed specification and plan defined by the artifact contract. Preserve unresolved decisions; do not invent product or risk decisions.
- If requirements, architecture, or trade-offs are not already approved, **REQUIRED SUB-SKILL:** Use `superpowers:brainstorming`.
- Require human review and approval of the written specification, then **REQUIRED SUB-SKILL:** Use `superpowers:writing-plans`.
- Require human review and approval of the written plan before implementation.
- Select one executor: **REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development` for independently reviewable tasks with subagents, or `superpowers:executing-plans` for inline/separate-session execution.
- For behavior changes, **REQUIRED SUB-SKILL:** Use `superpowers:test-driven-development`.
- At task and whole-change gates, **REQUIRED SUB-SKILL:** Use `superpowers:requesting-code-review` when available; otherwise perform the review contract directly and disclose the missing specialist.
- **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion` before closeout.
- When a branch-based delivery workflow applies and the user has authorized its actions, **REQUIRED SUB-SKILL:** Use `superpowers:finishing-a-development-branch`.

Do not reproduce, approximate, or continue a sub-skill from memory. Invoke it explicitly, follow it within project authority and this skill's artifact contract, record its result, then return to the current lifecycle gate.

## Review Contract

Review the current specification, plan, documentation, implementation diff, tests, and fresh evidence together. Record findings by severity with paths and evidence. Cover:

- specification and acceptance-criteria compliance;
- plan/task compliance and traceability;
- correctness, edge cases, error handling, and regressions;
- security, privacy, secrets, authorization, and data handling;
- test relevance, red/green evidence when TDD applies, and failure-path quality;
- maintainability, readability, and repository conventions;
- unnecessary complexity and opportunities for a smaller correct design;
- scope discipline, exclusions, and unrelated changes;
- freshness and sufficiency of verification evidence;
- rollback, recovery, migration, and operational readiness when applicable.

Use the mapping in [Superpowers integration](./references/superpowers-integration.md). When the planned `security-review`, `code-review`, `simpler-code`, or `smarter-code` skills become available and their trigger applies, invoke them with `REQUIRED SUB-SKILL` and return here. Their absence never converts an unperformed specialist review into a pass.

Fix blocking findings, rerun affected checks, and re-review the changed scope. Do not let an earlier approval or test run cover later edits.

## Close Gate

Close only when applicable requirements are satisfied, spec and plan mappings reconcile, blocking findings are resolved, required checks pass on the current state, evidence is recorded, recovery is understood, and every remaining item is explicitly optional or out of scope.

Report the development level, artifacts, implemented scope, review findings or clean result, exact verification commands and outcomes, recovery/rollback, skipped checks, residual risks, and optional follow-ups. Never describe unverified behavior as complete.
