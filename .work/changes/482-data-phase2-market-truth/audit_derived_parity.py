"""Read-only, hash-pinned V2/V3 derived-curve parity against frozen pre-2023 evidence."""

import json
import runpy
import sys
from pathlib import Path

source = Path("/repo/.work/changes/482-data-phase2-market-truth/audit_full_parity.py")
sys.argv = [str(source), "--dataset", "final"]
audit = runpy.run_path(str(source))
db = audit["db"]

# Reconstruct independent curve math from the normalized versioned facts at
# the frozen feature availability cutoff. Full base-field audit already asserts
# exact 12,352 settlement/bar volume/expiry matches without promoting OI.
db.execute("""
CREATE TEMP VIEW derived_wide AS
SELECT day,
 MAX(settle) FILTER (WHERE curve_rank=1) AS s1,
 MAX(settle) FILTER (WHERE curve_rank=2) AS s2,
 MAX(settle) FILTER (WHERE curve_rank=3) AS s3,
 MAX(settle) FILTER (WHERE curve_rank=4) AS s4,
 MAX(dte) FILTER (WHERE curve_rank=1) AS d1,
 MAX(dte) FILTER (WHERE curve_rank=4) AS d4,
 MAX(bar_volume) FILTER (WHERE curve_rank=1) AS v1,
 MAX(bar_volume) FILTER (WHERE curve_rank=2) AS v2
FROM featurefacts GROUP BY day
""")
db.execute("""
CREATE TEMP VIEW derived_check AS
SELECT w.day,
  f.feature_curve_spread_m1_m2 AS old12, w.s1-w.s2 AS new12,
  f.feature_curve_spread_m2_m3 AS old23, w.s2-w.s3 AS new23,
  f.feature_curve_spread_m3_m4 AS old34, w.s3-w.s4 AS new34,
  f.feature_curve_slope_m1_m4 AS old_slope,
  CASE WHEN w.d4 > w.d1 THEN (w.s4-w.s1)/(w.d4-w.d1) ELSE NULL END AS new_slope,
  f.feature_curve_volume_ratio_m1_m2 AS old_ratio,
  CASE WHEN w.v2 > 0 THEN w.v1/w.v2 ELSE NULL END AS new_ratio
FROM derived_wide w JOIN oldfeat f
ON CAST(f.trade_date AS DATE)=w.day
""")
fields = {
    "spread_m1_m2": ("old12", "new12"),
    "spread_m2_m3": ("old23", "new23"),
    "spread_m3_m4": ("old34", "new34"),
    "slope_m1_m4": ("old_slope", "new_slope"),
    "volume_ratio_m1_m2": ("old_ratio", "new_ratio"),
}
rows = db.execute("SELECT COUNT(*) FROM derived_check").fetchone()[0]
assert rows == 3088, ("derived feature date count mismatch", rows)
results = {}
for name, (old, new) in fields.items():
    tested, matched, missing, max_abs = db.execute(f"""
    SELECT COUNT(*),
      COUNT(*) FILTER (WHERE {old} IS NOT NULL AND {new} IS NOT NULL
         AND ABS({old}-{new}) <= 1e-8 * GREATEST(1.0, ABS({old}))),
      COUNT(*) FILTER (WHERE {old} IS NULL OR {new} IS NULL),
      MAX(ABS({old}-{new}))
    FROM derived_check
    """).fetchone()
    results[name] = {
        "tested": tested, "matched": matched, "missing": missing,
        "max_abs_error": max_abs
    }
    if tested != matched:
        print("MISMATCH_EXAMPLES", name, db.execute(f"""
            SELECT day, {old} AS frozen, {new} AS rebuilt FROM derived_check
            WHERE {old} IS NULL OR {new} IS NULL OR
              ABS({old}-{new}) > 1e-8 * GREATEST(1.0, ABS({old}))
            ORDER BY day LIMIT 12
        """).fetchall(), flush=True)
assert all(v["matched"] == rows and v["missing"] == 0 for v in results.values()), results
print("PASS_DERIVED_FEATURE_PARITY", json.dumps(results, sort_keys=True), flush=True)
