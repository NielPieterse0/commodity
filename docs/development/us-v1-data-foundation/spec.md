# U.S. V1 Data Foundation Specification

**Development level:** Complex
**Status:** implemented for acquisition/preservation; point-in-time and Massive licensing gates remain explicit

## Outcome

Make the U.S./Henry Hub V1 manifest executable without starting serious model training. Preserve reproducible source snapshots while upstream access exists, and never promote a current-state historical snapshot to point-in-time backtest evidence by implication.

## Scope

The seven remaining V1 families after canonical futures are:

1. issued weather forecasts;
2. underground storage;
3. gas production and balance;
4. gas demand and power burn;
5. LNG and pipeline trade;
6. Henry Hub spot/reference price;
7. calendar and seasonality.

Massive futures preservation is included because the account-accessible history is a prerequisite for the curve/calendar layer.

## Requirements

- Raw snapshots are immutable, hashed, ignored by Git, and recoverable from manifests.
- Credentials never appear in snapshot metadata or request URLs stored by the repo.
- Massive acquisition is rate-limit aware, transient-error aware, bounded, and resumable.
- Massive V1 market-value capture is bounded to the M1-M12 curve horizon; full discovered contract metadata may be retained.
- EIA Natural Gas bulk history is preserved as a current-state snapshot; Lower-48 EIA-930 demand/forecast and gas generation are captured separately rather than downloading the full EIA-930 bulk archive.
- Archived weather uses actually-issued model runs. Model initialization is not silently equated with actual availability.
- All historical `available_at`/revision gaps remain fail-closed for point-in-time backtests.
- Massive non-display/backtesting rights and redistribution restrictions remain unchanged.
- No LIVE-trading authority changes and no serious model training is introduced.
