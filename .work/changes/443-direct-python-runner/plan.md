# Direct Python Runner Implementation Plan

**Goal:** Satisfy issue #443 with a repository-only direct Python runner while preserving the existing canonical verification contract.

## Implementation

- Add `scripts/environment/run_python.py` as the bounded execution authority.
- Add `scripts/run.cmd` as the non-PowerShell Windows entry point.
- Enforce exact active-worktree `.venv\Scripts\python.exe` identity.
- Redirect launcher-managed cache/temp/runtime state beneath Commodity.
- Sanitize child Python environment so inherited host Python variables cannot override the active worktree.
- Support pytest, Ruff, module, script, and raw Python modes with exact argument/exit-code forwarding.
- Track child PID, launcher PID, run state, timestamps, and command hash without persisting raw command arguments.
- Reconcile vanished processes as interrupted with a non-destructive Windows process query.

## Verification and delivery

- Run focused runner tests and Ruff after each behavioral correction.
- Prove a real direct launch from outside the worktree uses the exact worktree interpreter/environment and preserves a non-zero exit code.
- Run `scripts\verify.ps1` on the final exact head.
- Complete KIS review/promotion, exact-head PR, provider-native CI, merge, Work reconciliation, and safe worktree cleanup.

## Recovery

All changes are isolated on `change/443-direct-python-runner`; rollback is branch/PR scoped and does not alter host configuration.