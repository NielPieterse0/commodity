# Norway source and PIT readiness — issue #115

**Decision date:** 2026-08-20

## Decision

Defer historical activation of every Norway-specific feature family under #86. None of the four reviewed source families currently satisfies the repository's strict point-in-time evidence standard end to end.

The strongest future candidate is **Gassco outage/event revisions**, because the publication contract includes an event ID, revision, publication time, affected asset and unavailable capacity. That mechanism can represent an unexpected Norwegian supply shock before it is fully absorbed into TTF, European storage and broader balance variables. Historical event-vintage depth and approved machine acquisition are not yet verified, so this remains a capture-forward / archive-verification candidate rather than backtest evidence.

ENTSOG Norway-interface operational data is useful as a machine-readable cross-check and possible flow control. Its API exposes period fields and `lastUpdateDateTime`, but the reviewed documentation does not establish preservation of every superseded value. It therefore cannot yet prove historical-vintage reconstruction. Norway-interface flow is also economically close to the existing European-flow family and should not be counted as a separate geographic signal without an incremental ablation.

## Source dispositions

Norwegian Offshore Directorate monthly production is public and deep, and dated monthly news releases provide exact publication dates for preliminary NCS totals. FactPages, however, is a synchronized current-state history and no field-level historical-vintage archive was verified. Field production is therefore deferred for strict PIT backtests; dated aggregate releases may later support a separately reconstructed slow-moving regime control.

SSB tables `08864` and `08799` are public, API-accessible and CC BY 4.0. They explicitly revise prior months, revise annual histories again in later years, and have also made exceptional historical revisions. The current Statbank API is not a vintage archive. Current extracts must not be used as if they were the values known at the historical prediction date.

Gassco publishes current/next-gasday aggregated nominations every five minutes and only final daily aggregated nominations for up to two years historically. Final daily history is useful for physical context but does not reconstruct what a trader knew intraday. Public outage messages are more promising because revisions are timestamped, but the public historical archive and machine-access terms must be closed before use.

## Incremental-information test

A Norway variable is eligible for future preregistration only if its mechanism is incremental to the Global/Interconnect controls already planned in `docs/data-manifest.md`:

- unexpected Gassco event **publication/revision deltas** may qualify as upstream supply-shock information;
- corridor flow may qualify only after conditioning on the existing ENTSOG European-flow family and TTF controls;
- monthly NCS production and SSB exports are primarily slow-moving balance/regime information and are unlikely to justify a short-horizon standalone family;
- the same physical flow observed through both Gassco and ENTSOG is one economic signal, not two features merely because it has two publishers.

## Activation requirements

Before #86 can activate a Norway family, a separate preregistration must freeze source identity, historical coverage, timestamp semantics, revision/vintage handling, units and point mapping, cutoff rules, missing-data rules and the exact incremental control set. Any paid or restricted acquisition requires separate approval.

This slice performs no acquisition spend, feature generation, model execution or geographic activation. Machine-readable evidence is in `evidence.json`. `config/data_sources.json` remains unchanged because it is still part of the frozen #83 source-policy identity; any future operational adoption of these Norway dispositions must occur through a successor/refreeze change rather than silently mutating that empirical authority.
