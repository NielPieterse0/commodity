# Contributing

Commodity is an experimental research repository. Repository authority, change boundaries, and development governance are defined in `AGENTS.md`; research and execution policy remain owned by the configuration files identified there.

## Change workflow

- Use an isolated non-default branch/worktree for non-trivial changes.
- Keep each change bounded to one tracked issue or approved scope.
- Use the live KIS capability/workflow contract for verification, publication, review, landing, and cleanup.
- GitHub Actions evidence must correspond to the exact pull-request head before merge.
- Do not bypass failed, missing, stale, or mismatched required verification.

## Issue completion authority

Do not use GitHub auto-closing keywords such as `Fixes #123`, `Closes #123`, or `Resolves #123` in pull-request bodies or commit messages. Work Management and the governed closeout workflow retain completion authority.

## Sensitive and generated material

Follow `SECURITY.md`. Do not commit credentials, licensed raw market values, machine-local paths/state, caches, generated run output, quarantine payloads, or provider installations.
