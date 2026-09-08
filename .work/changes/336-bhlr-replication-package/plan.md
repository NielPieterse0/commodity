# BHLR Replication Package Implementation Plan

**Goal:** Preserve and identity-bind the complete operator-supplied BHLR package for rep-014 without adding acquisition infrastructure or touching forecast outcomes.

## Implementation

1. Rebase the governed #336 worktree to current `main` and keep scope limited to the raw BHLR snapshot plus change evidence.
2. Copy the three operator-supplied files unchanged into the durable raw snapshot.
3. Extract the five JAE resource-archive members unchanged for direct research use.
4. Generate `manifest.json` for source/provenance/top-level identities.
5. Generate `nested-archive-members.json` with per-member size/SHA-256 for the code and nowcast ZIPs.
6. Verify source-to-durable byte identity, outer archive extraction identity, and standalone-versus-archive database identity.
7. Record the exact manifest identities in tracked `package-evidence.json`.
8. Run focused governance/compile checks, publish exact-head PR, require provider-native CI, merge, and return the landed identity to rep-014.

## Boundaries

- Existing `config/data_sources.json` already records `LIT-BHLR-RTDB`; do not duplicate it.
- Do not add an acquisition recipe or KIS acquisition plumbing.
- Do not execute MATLAB, Python forecast scoring, or sealed confirmation data in this change.
