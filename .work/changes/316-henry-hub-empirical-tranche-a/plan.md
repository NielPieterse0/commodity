# 316 recovery and execution plan

1. Re-establish one exact GitHub branch/PR identity from current `main` and preserve this change record there.
2. Repair Databento contract identity so each market observation joins only to the definition valid at that observation time; fail closed on missing, overlapping, or ambiguous validity.
3. Complete rep-001 pre-outcome rules: fixed DTE buckets, liquidity rule, numeric MEPI, and clustered/dependence-aware power.
4. Complete rep-002 pre-outcome rules: exact standardized M1-M6 seasonal curve statistic, numeric MEPI, and year-block/bootstrap power.
5. Add synthetic/adversarial regressions, including instrument-ID reuse across eras resolving to different contracts.
6. Run definition/identity/coverage-only dry runs without reading protected market outcomes.
7. Update Programme 002 authorities and create/freeze the two governed preregistrations only when every pre-outcome gate passes.
8. Only after freeze, execute the maximum eligible canonical samples and record results without post-outcome tuning.
9. Keep the GitHub PR head exact, observe provider-native Actions for that head, review, and merge only when scientific and repository gates both pass.
