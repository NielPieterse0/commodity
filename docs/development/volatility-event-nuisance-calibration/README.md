# #209 — Volatility event nuisance calibration

The frozen 80-event nuisance calibration was executed under the #207 release authority. It used the exact #207 training and calibration identities and did not inspect the 342-event confirmation sample or the separate 504 future rows.

The power gate failed. Relative detectable QLIKE improvement at the exact 342-event confirmation count was 17.71% for 2-event blocks, 17.83% for the primary 4-event block, and 17.33% for 8-event blocks. The frozen gate requires every value to be at or below 5%.

Therefore confirmation execution remains unauthorized. This result does not establish that the challenger lacks forecasting value; it establishes that this frozen confirmation design cannot reliably detect a 5% relative QLIKE improvement at the observed nuisance-loss variability.

Only the outputs permitted by #207 are recorded in `result.json`. Mean challenger loss, paired mean improvement, p-values, confidence intervals, period/regime results, and secondary performance remain unreported.

<!-- temporary ci-trigger marker; reverted in next commit -->
