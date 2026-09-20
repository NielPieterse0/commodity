# Change Specification: Direct Python Runner

- **Change ID**: `443-direct-python-runner`
- **Status**: Active; implementation complete, delivery pending
- **Complexity**: Medium (`scope.json`)
- **Authority**: GitHub issue #443, `AGENTS.md`, and `scope.json`

## Outcome

Provide a Commodity-owned launcher that invokes the active worktree `.venv\Scripts\python.exe` directly without PowerShell for routine Python execution.

## Requirements

1. Resolve only the active checkout/worktree interpreter and fail closed on any other interpreter or repository root.
2. Keep launcher-managed cache, temp, run records, and runtime state beneath the configured Commodity repository root.
3. Force child Python resolution to the active worktree via `VIRTUAL_ENV`, `PYTHONPATH`, `PYTHONNOUSERSITE`, and PATH while removing inherited `PYTHONHOME`.
4. Support pytest, Ruff, modules, repository scripts, and arbitrary Python arguments while preserving child exit codes.
5. Record concrete child/launcher process identity and classify vanished running processes as interrupted without signalling live processes.
6. Keep `scripts\verify.ps1` unchanged.

## Acceptance evidence

- `tests/test_run_python.py` covers interpreter/root boundaries, environment containment, command/argument forwarding, relative script resolution, run state, and non-destructive PID reconciliation.
- `scripts\run.cmd` directly launches the worktree venv Python and forwards the child exit code.
- Canonical `scripts\verify.ps1` must pass on the final exact review head before publication.

## Out of scope

No kis-mcp, Defender, host shell-policy, global Python, or canonical verification-orchestration changes.