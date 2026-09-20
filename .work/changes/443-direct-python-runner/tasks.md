# Tasks: Direct Python Runner

- [x] Confirm issue #443 authority, schema-v4 scope, medium complexity, owned paths, and unchanged `verify.ps1` boundary.
- [x] Implement the direct worktree-local Python runner and CMD entry point.
- [x] Add boundary, environment, argument, cache, process-state, and wrapper tests.
- [x] Fix JSON newline handling caught by canonical verification.
- [x] Replace destructive Windows PID probing with a non-signalling wait-handle query.
- [x] Harden child Python environment isolation and repository-relative script execution.
- [x] Pass focused runner tests/Ruff and a real direct-launch smoke test.
- [ ] Pass canonical verification and final review on the exact final head.
- [ ] Publish PR, pass exact-head CI, merge, reconcile Work/documentation state, and clean the worktree through KIS.