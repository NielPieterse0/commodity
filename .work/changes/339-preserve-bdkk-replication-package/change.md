# Change: Preserve Bdkk Replication Package

- **Change ID**: `339-preserve-bdkk-replication-package`
- **Risk Profile**: lean

## Outcome

Preserve the operator-supplied Bernard et al. Journal of Applied Econometrics replication archive as an immutable durable raw snapshot with byte identity, provenance, and archive-member manifest linked to future research issue #338, without altering current rep-014 or sealed confirmation data.

## Scope and acceptance

- Implement only the paths declared in `scope.json`.
- Preserve the operator-supplied ZIP bytes unchanged in the durable raw-data layer.
- Bind DOI `10.15456/jae.2022320.0725024505`, original filename, byte size, SHA-256, and archive-member identities.
- Record source scope: annual U.S. real natural-gas prices, 1919-2006; not Henry Hub-specific real-time forecast data.
- Link future research issue #338 and preservation task #339; do not touch rep-014 or sealed confirmation data.

## Implementation and verification

- Implementation notes: copied the immutable source bytes to the main repository's ignored durable raw layer at `data/raw/snapshots/jae/bernard-et-al-2012-tvp/replication-data.zip`; the dataset-local `manifest.json` records provenance, source scope, archive identity, and every member identity. `acquisition-evidence.json` preserves the safe tracked summary and binds the dataset-local manifest hash.
- Focused checks: source/durable archive SHA-256 and byte size match; every archive member exists and matches the dataset-local manifest SHA-256; JSON parses successfully. Durable raw snapshot verification passed on 2026-09-08.
- Review findings: no scientific result or executable archive content was used; this change is preservation-only.
- Residual risk: dataset license has not been independently verified; manifest records `license_status=not_verified` rather than inferring a license.
- Closeout state: implementation complete; repository/KIS verification and publication pending.
