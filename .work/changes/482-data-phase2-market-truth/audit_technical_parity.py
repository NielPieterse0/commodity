"""Source-rebuilt V2/V3 per-contract technical-feature parity; pre-2023 only."""
import json
import runpy
import sys

source = "/repo/.work/changes/482-data-phase2-market-truth/audit_full_parity.py"
sys.argv = [source, "--dataset", "final"]
db = runpy.run_path(source)["db"]
db.execute("""
CREATE TEMP VIEW settle_latest AS SELECT * FROM stats WHERE stat_type='settle'
 QUALIFY ROW_NUMBER() OVER (PARTITION BY instrument_id,trade_date
  ORDER BY CAST(available_at AS TIMESTAMPTZ) DESC,evidence_id DESC)=1
""")
db.execute("""
CREATE TEMP VIEW tech_base AS SELECT
 b.instrument_id,CAST(b.trade_date AS DATE) AS day,
 CAST(s.value AS DOUBLE) settle,
 b.high,b.low,b.close
 FROM barlatest b JOIN settle_latest s USING (instrument_id,trade_date)
 WHERE s.value>0 AND b.close>0
""")
db.execute("""
CREATE TEMP VIEW tech_returns AS SELECT *,
 LN(settle) - LAG(LN(settle),1) OVER w AS ret1,
 LN(settle) - LAG(LN(settle),5) OVER w AS ret5,
 LN(settle) - LAG(LN(settle),20) OVER w AS ret20
 FROM tech_base WINDOW w AS (PARTITION BY instrument_id ORDER BY day)
""")
db.execute("""
CREATE TEMP VIEW tech_metrics AS SELECT *,
 ret1 AS feature_ret_1,
 ret5 AS feature_ret_5,
 ret20 AS feature_ret_20,
 CASE WHEN COUNT(ret1) OVER w5=5 THEN STDDEV_SAMP(ret1) OVER w5 END feature_vol_5,
 CASE WHEN COUNT(ret1) OVER w20=20 THEN STDDEV_SAMP(ret1) OVER w20 END feature_vol_20,
 CASE WHEN COUNT(settle) OVER w5=5 THEN settle/AVG(settle) OVER w5-1 END feature_ma_gap_5,
 CASE WHEN COUNT(settle) OVER w20=20 THEN settle/AVG(settle) OVER w20-1 END feature_ma_gap_20,
 (high-low)/close AS feature_range_pct
 FROM tech_returns
 WINDOW w5 AS (PARTITION BY instrument_id ORDER BY day ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
        w20 AS (PARTITION BY instrument_id ORDER BY day ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
""")
db.execute("""
CREATE TEMP VIEW tech_comparison AS
SELECT CAST(f.trade_date AS DATE) AS day, f.*, t.feature_ret_1 AS new_ret_1,
 t.feature_ret_5 new_ret_5,t.feature_ret_20 new_ret_20,
 t.feature_vol_5 new_vol_5,t.feature_vol_20 new_vol_20,
 t.feature_ma_gap_5 new_ma_gap_5,t.feature_ma_gap_20 new_ma_gap_20,
 t.feature_range_pct new_range_pct
 FROM oldfeat f
 JOIN pathmatch p ON p.day=CAST(f.trade_date AS DATE)
 LEFT JOIN tech_metrics t ON t.instrument_id=p.instrument_id AND t.day=p.day
""")
fields = {
 "ret_1": ("feature_ret_1","new_ret_1"),
 "ret_5": ("feature_ret_5","new_ret_5"),
 "ret_20": ("feature_ret_20","new_ret_20"),
 "vol_5": ("feature_vol_5","new_vol_5"),
 "vol_20": ("feature_vol_20","new_vol_20"),
 "ma_gap_5": ("feature_ma_gap_5","new_ma_gap_5"),
 "ma_gap_20": ("feature_ma_gap_20","new_ma_gap_20"),
 "range_pct": ("feature_range_pct","new_range_pct")
}
results = {}
for name,(old,new) in fields.items():
    count,matched,null_count,max_delta = db.execute(f"""
    SELECT COUNT(*),
       COUNT(*) FILTER(WHERE {old} IS NOT NULL AND {new} IS NOT NULL
         AND ABS({old}-{new})<=1e-8*GREATEST(1,ABS({old}))),
       COUNT(*) FILTER(WHERE {old} IS NULL OR {new} IS NULL),
       MAX(ABS({old}-{new}))
    FROM tech_comparison
    """).fetchone()
    results[name]={"tested":count,"matched":matched,"null_rows":null_count,
                   "max_abs_error":max_delta}
    if matched!=count:
        print("TECH_MISMATCH",name,db.execute(f"""
        SELECT day,{old},{new} FROM tech_comparison
        WHERE {old} IS NULL OR {new} IS NULL OR
        ABS({old}-{new})>1e-8*GREATEST(1,ABS({old}))
        ORDER BY day LIMIT 8
        """).fetchall(),flush=True)
print("TECH_PARITY_RESULT",json.dumps(results,sort_keys=True),flush=True)
assert all(item["tested"]==3088 and item["matched"]==3088
           for item in results.values()),"technical parity incomplete"
