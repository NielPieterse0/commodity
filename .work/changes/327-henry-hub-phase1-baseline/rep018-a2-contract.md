# rep-018 A2 public source-era reconstruction

This fallback is fixed before reading its reconstructed 2003-2018 announcement-return outcome.

- Use official EIA daily Contract 1 and Contract 2 Henry Hub futures histories only.
- Reconstruct the paper's first investable series from rank identity, not announcement outcomes.
- Within each calendar month, use EIA Contract 2 through the expiry of the exchange front contract and Contract 1 after that expiry through month-end.
- Compute front expiry as the third CME business day before the first calendar day of the delivery month using the 2003-2018 CME holiday set.
- Validate the rank-switch rule against exact Databento contract identities for every overlapping 2010-2018 month before using 2003-2010 returns.
- Permit only EIA rounding differences when validating prices; do not tune switch dates against return signs, announcement labels, or statistical significance.
- Use the same conservative release-calendar rule already fixed for Stage A; unresolved holiday-shift weeks remain excluded rather than guessed.
- Report the exact-contract 2010-2018 overlap and the public 2003-2018 reconstruction separately.
- Bloomberg surprise controls remain a separate fidelity boundary and cannot be synthesized from fitted expectations.
