# Change Specification: Direct Python Runner

- **Change ID**: `443-direct-python-runner`
- **Status**: Draft
- **Complexity**: use live KIS schema-v4 classification

## Outcome

Add a Commodity-only direct Python execution runner that launches the active worktree .venv interpreter without PowerShell, enforces Projects-local execution/cache/runtime boundaries, supports routine test/lint/research/optimization commands, and records concrete run identity/status while leaving scripts/verify.ps1 unchanged.

## Authority and scope

- Authoritative sources:
- Owned/shared/excluded paths: `scope.json`
- Dependencies/integration ownership: `scope.json`

## Requirements mapping

- Ordinary engineering change: record the bounded software/design requirements that are not owned elsewhere.
- Research-originated change: reference the exact L3 research authority/fingerprint and map it to repository owners/interfaces only. Do not restate, reinterpret, or extend the scientific design.

## Acceptance

1. **Given** the authoritative requirements, **When** the bounded change is implemented, **Then** the mapped acceptance evidence passes.

## Risks and recovery

- Risk:
- Recovery:

## Out of scope

-
