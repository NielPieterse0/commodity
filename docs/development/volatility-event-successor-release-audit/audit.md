# #207 — Volatility event successor release audit

**Decision:** pass; nuisance calibration only.

This audit independently reconstructed the frozen #205 every-fifth-row event schedule from the exact #201 2,772-row daily identity and the approved Databento source evidence. It inspected identity, calendar, contract, same-contract history, OHLC coverage and point-in-time availability only. No model performance was calculated.

The #205 contract, power analysis, preregistration, freeze and current source-policy hashes match their frozen identities.

## Event identity

The 972-row development role produces 195 scheduled anchors. Of these, 183 are admissible. Twelve are dropped because the selected prediction contract does not have all five required subsequent target-session bars. There are no history or PIT failures.

The untouched 1,800-row candidate role produces 360 scheduled anchors. Of these, 342 are admissible. Eighteen are dropped for the same fixed same-contract target-coverage reason. There are no history or PIT failures.

The frozen minimum of 300 confirmation events therefore passes without moving or adapting the schedule.

## Frozen roles

The first 80 admissible development events are initial training. The next 80 are nuisance calibration. Twenty-three later admissible development events are unused by the frozen primary design.

The candidate confirmation identity contains exactly 342 admissible events from 28 October 2018 through 7 August 2024. Its performance remains unopened.

The prior #203 result and the #205 freeze both record that the protected daily 1,800-row performance and the separate 504 future-row performance were not inspected before this successor was frozen.

## Authority

This audit releases only the frozen 80-event nuisance calibration. It may emit mean baseline QLIKE, centered paired-loss block SD for 2/4/8-event blocks, and relative MDE at exact confirmation n=342.

Confirmation remains unauthorized. All three nuisance relative MDEs must be at or below 5% before a later release may permit confirmation. Feature/model search, paid acquisition, research promotion and trading remain unauthorized.
