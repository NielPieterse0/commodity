# Change Specification: BHLR Replication Package

- **Change ID**: `336-bhlr-replication-package`
- **Status**: Active
- **Complexity**: medium
- **Authority**: issue #336, Programme 002 rep-014, and source registry `LIT-BHLR-RTDB`

## Outcome

Preserve the operator-supplied Baumeister-Huber-Lee-Ravazzolo JAE replication package as an immutable raw snapshot for rep-014 and bind every retained artifact to durable provenance and SHA-256 identities.

## Acceptance

1. Preserve all three supplied files byte-for-byte under `data/raw/snapshots/bhlr/bhlr-2025-real-time-forecasting`.
2. Retain the JAE readme, real-time database, codes, nowcasts, citation, and separately supplied online appendix.
3. Bind DOI `10.15456/jae.2025266.1900967125`, canonical source URLs, filenames, byte sizes, SHA-256s, and package contents.
4. Verify the standalone database against the database embedded in the JAE resource archive.
5. Inventory every non-directory member of the nested code and nowcast ZIPs with byte size and SHA-256.
6. Return the exact snapshot manifest identity to the Phase-1 rep-014 lineage.

## Constraints

- No new downloading or KIS acquisition plumbing; the source registry already identifies `LIT-BHLR-RTDB`.
- No forecast scoring, model selection, or scientific interpretation in this import change.
- Do not touch sealed confirmation data.
- Raw source bytes are immutable; manifests/evidence may describe but never rewrite them.
