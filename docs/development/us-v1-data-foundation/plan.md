# U.S. V1 Data Foundation Plan

1. Add immutable raw snapshot primitives with hashes and tamper verification.
2. Harden Massive discovery/capture for account pacing, 429/5xx retries, bounded schedule windows, checkpoints, and M1-M12 preservation.
3. Add EIA bulk and API snapshot adapters; preserve Natural Gas bulk and targeted Lower-48 EIA-930 series.
4. Add Open-Meteo Single Runs capture with explicit issue/valid/availability semantics.
5. Expose capture commands and update authoritative source configuration.
6. Record verified local capture evidence, reconcile the data manifest/README, run review/verification, and raise a PR.

## Exit gates

- Raw provider values remain under ignored `data/raw/snapshots/`.
- Committed evidence contains hashes/coverage only, never licensed Massive values or credentials.
- Point-in-time readiness and Massive licensing remain fail-closed.
- Full test/lint/diff checks must pass before merge.
