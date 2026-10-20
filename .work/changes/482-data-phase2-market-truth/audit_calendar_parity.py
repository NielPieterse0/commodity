"""Hash-pinned, pre-2023 calendar and roll feature parity, read-only."""
import json
import runpy
import sys

source = "/repo/.work/changes/482-data-phase2-market-truth/audit_full_parity.py"
sys.argv = [source, "--dataset", "final"]
db = runpy.run_path(source)["db"]
db.execute("""
CREATE TEMP VIEW calendar_check AS
SELECT CAST(f.trade_date AS DATE) AS day,
 f.feature_season_sin old_sin,
 SIN(2.0*PI()*EXTRACT(DOY FROM CAST(f.trade_date AS DATE))/365.25) new_sin,
 f.feature_season_cos old_cos,
 COS(2.0*PI()*EXTRACT(DOY FROM CAST(f.trade_date AS DATE))/365.25) new_cos,
 f.feature_roll_event old_roll,
 CASE WHEN lp.roll_reason IN ('hold','initial') THEN 0 ELSE 1 END new_roll,
 f.feature_selected_dte old_dte,
 DATEDIFF('day', CAST(f.trade_date AS DATE), CAST(i.expiry_utc AS DATE)) new_dte
FROM oldfeat f
JOIN oldpath lp ON CAST(f.trade_date AS DATE)=CAST(lp.trade_date AS DATE)
JOIN pathmatch pm ON pm.day=CAST(f.trade_date AS DATE)
JOIN identities i ON i.instrument_id=pm.instrument_id
""")
fields = {
    "season_sin": ("old_sin", "new_sin"),
    "season_cos": ("old_cos", "new_cos"),
    "roll_event": ("old_roll", "new_roll"),
    "selected_dte": ("old_dte", "new_dte"),
}
results = {}
for name, (left, right) in fields.items():
    count, matches, max_delta = db.execute(f"""
    SELECT COUNT(*),
      COUNT(*) FILTER (WHERE {left} IS NOT NULL AND {right} IS NOT NULL
                      AND ABS({left}-{right}) <= 1e-10),
      MAX(ABS({left}-{right}))
    FROM calendar_check
    """).fetchone()
    results[name] = {"tested": count, "matched": matches, "max_delta": max_delta}
    if count != matches:
        print("MISMATCH", name, db.execute(f"""
        SELECT day, {left}, {right} FROM calendar_check
        WHERE {left} IS NULL OR {right} IS NULL OR ABS({left}-{right})>1e-10
        ORDER BY day LIMIT 10
        """).fetchall(), flush=True)
assert all(x["matched"] == x["tested"] == 3088 for x in results.values()), results
print("PASS_CALENDAR_ROLL_PARITY", json.dumps(results, sort_keys=True), flush=True)
