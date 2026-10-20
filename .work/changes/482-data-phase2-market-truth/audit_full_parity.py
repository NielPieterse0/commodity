"""Read-only pre-2023 parity audit against immutable legacy 356 checkpoint."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dataset', choices=('original', 'rebuild', 'final'), default='original')
choice = parser.parse_args().dataset
pinned_datasets = {
    'original': (
        'market-truth-full-2010-2022-curated',
        '2d172cb67706cc458739bcf26a9711e93b899ee63020031805ee4afdbd6b18b4',
        '08ca7a7cd4905a612d42886d25d27d28075d316bd964eea0ea1951ff22be44ea',
    ),
    'rebuild': (
        'market-truth-full-2010-2022-refactor-v2',
        '853f7da87953407b175e5321d8eed60a1aed9e738c89aaa7824711c036cd989f',
        '40e40302a52579e00a930b659695430508c02dbac691fc3de7e980bac6ba95a7',
    ),
    'final': (
        'market-truth-full-2010-2022-refactor-v3',
        '6d3093305c0ae2c6a313be13151b0810bf208c1cb8f429e1bbf58a17e7d89605',
        '943780ea8eaa7315157385c687e3939777089420c186fd7d8d4b7d781a1f5d94',
    ),
}
dataset_folder, expected_manifest_sha256, expected_content_sha256 = pinned_datasets[choice]
base = Path('/repo/.work/runtime/market_truth_development') / dataset_folder
old=Path('/legacy')
expected_legacy={'features':'b14ae69bd6ec2910f0cf56fe62f481016801308cebc6ef69e536aa7e593d072e','session-path':'0fe87ea79a56f98fb9d445e89e3d65b48ae7bb1175e06ba9b97da68ebe6b01e8'}
for name,digest in expected_legacy.items():
    assert hashlib.sha256((old/(name+'.parquet')).read_bytes()).hexdigest()==digest
assert hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest()==expected_manifest_sha256
manifest=json.loads((base/'manifest.json').read_text())
assert manifest['content_sha256']==expected_content_sha256
for name,details in manifest['tables'].items():
    assert hashlib.sha256((base/(name+'.parquet')).read_bytes()).hexdigest()==details['sha256']
db=duckdb.connect(':memory:')
db.execute("SET memory_limit='1GB'")
db.execute("SET temp_directory='/tmp'")
def scan(folder,name): return str(folder/(name+'.parquet'))
for name,folder,family in [('oldpath',old,'session-path'),('oldfeat',old,'features'),('defs',base,'definitions'),('bars',base,'bars'),('stats',base,'statistics')]:
    db.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{scan(folder,family)}')")
db.execute("""CREATE TEMP VIEW identities AS SELECT instrument_id,symbol,
 CAST(CAST(expiration AS TIMESTAMPTZ) AS DATE) AS expiry_date,
 MIN(CAST(expiration AS TIMESTAMPTZ)) AS expiry_utc,
 MIN(CAST(available_at AS TIMESTAMPTZ)) AS first_known,
 COUNT(*) AS definition_versions FROM defs GROUP BY 1,2,3""")
db.execute("""CREATE TEMP VIEW barlatest AS SELECT * FROM bars
 QUALIFY ROW_NUMBER() OVER (PARTITION BY instrument_id,trade_date
 ORDER BY CAST(available_at AS TIMESTAMPTZ) DESC,evidence_id DESC)=1""")
print('SOURCE_CARDINALITY',db.execute("""SELECT (SELECT COUNT(*) FROM identities),
 (SELECT COUNT(DISTINCT instrument_id) FROM identities),
 (SELECT COUNT(DISTINCT symbol || '/' || CAST(expiry_date AS VARCHAR)) FROM identities),
 (SELECT COUNT(*) FROM oldfeat),(SELECT COUNT(*) FROM oldpath)""").fetchall(),flush=True)
db.execute("""CREATE TEMP VIEW pathmatch AS SELECT
 CAST(lp.trade_date AS DATE) AS day,lp.contract_id,lp.open_price,
 i.instrument_id,i.first_known,CAST(lp.session_open AS TIMESTAMPTZ) AS session_open,
 b.open AS rebuilt_open
 FROM oldpath lp LEFT JOIN identities i
 ON i.symbol=SPLIT_PART(lp.contract_id,'@',1)
 AND i.expiry_date=CAST(SPLIT_PART(lp.contract_id,'@',2) AS DATE)
 LEFT JOIN barlatest b ON b.instrument_id=i.instrument_id
 AND b.trade_date=CAST(CAST(lp.trade_date AS DATE) AS VARCHAR)""")
print('PATH_MATCH',db.execute("""SELECT COUNT(*) joined_rows, COUNT(DISTINCT day) AS day_count,
 COUNT(DISTINCT CASE WHEN instrument_id IS NOT NULL THEN day END) mapped_days,
 COUNT(DISTINCT CASE WHEN rebuilt_open IS NOT NULL THEN day END) priced_days,
 COUNT(DISTINCT CASE WHEN ABS(rebuilt_open-open_price)<1e-9 THEN day END) exact_open_days,
 COUNT(DISTINCT CASE WHEN first_known<session_open THEN day END) known_preopen_days,
 COUNT(DISTINCT CASE WHEN first_known>=session_open THEN day END) late_definition_days
 FROM pathmatch""").fetchall(),flush=True)
print('PATH_MISMATCH_EXAMPLES',db.execute("""SELECT day,contract_id,open_price,rebuilt_open,instrument_id,first_known
 FROM pathmatch WHERE rebuilt_open IS NULL OR ABS(rebuilt_open-open_price)>1e-9
 ORDER BY day LIMIT 20""").fetchall(),flush=True)
print('MULTIPLE_MAPPING',db.execute("""SELECT day, COUNT(*) n
 FROM pathmatch GROUP BY day HAVING COUNT(*)>1 ORDER BY n DESC,day LIMIT 10""").fetchall(),flush=True)
db.execute("""CREATE TEMP VIEW rank4 AS SELECT
 CAST(f.trade_date AS DATE) AS day, CAST(f.available_at AS TIMESTAMPTZ) AS cutoff,
 d.instrument_id,d.symbol,CAST(d.expiration AS TIMESTAMPTZ) AS expiry_utc,
 CAST(d.available_at AS TIMESTAMPTZ) AS first_known,
 ROW_NUMBER() OVER (PARTITION BY f.trade_date
 ORDER BY CAST(d.expiration AS TIMESTAMPTZ),d.symbol,d.instrument_id) AS curve_rank
 FROM oldfeat f CROSS JOIN (SELECT DISTINCT instrument_id FROM defs) ids
 ASOF JOIN defs d ON ids.instrument_id=d.instrument_id
 AND CAST(d.available_at AS TIMESTAMPTZ)<=LEAST(
 CAST(f.available_at AS TIMESTAMPTZ),
 CAST(f.trade_date AS TIMESTAMPTZ)+INTERVAL '1 day'-INTERVAL '1 microsecond')
 WHERE CAST(d.expiration AS TIMESTAMPTZ)>LEAST(
 CAST(f.available_at AS TIMESTAMPTZ),
 CAST(f.trade_date AS TIMESTAMPTZ)+INTERVAL '1 day'-INTERVAL '1 microsecond')
 QUALIFY curve_rank<=4""")
print('RANK4',db.execute("""SELECT COUNT(*) AS row_count,COUNT(DISTINCT day) AS date_count,
 COUNT(DISTINCT CASE WHEN curve_rank=4 THEN day END) full_four,
 MIN(day),MAX(day) FROM rank4""").fetchall(),flush=True)
db.execute("""CREATE TEMP VIEW featurefacts AS SELECT fc.*,
 ss.value AS settle, b.close AS bar_close,b.volume AS bar_volume,
 EXTRACT(EPOCH FROM (fc.expiry_utc-CAST(fc.day AS TIMESTAMPTZ)))/86400 AS dte
 FROM rank4 fc
 LEFT JOIN LATERAL (
 SELECT s.value FROM stats s WHERE s.instrument_id=fc.instrument_id
 AND s.trade_date=CAST(fc.day AS VARCHAR) AND s.stat_type='settle'
 AND CAST(s.available_at AS TIMESTAMPTZ)<=fc.cutoff
 ORDER BY CAST(s.available_at AS TIMESTAMPTZ) DESC,s.evidence_id DESC
 LIMIT 1) ss ON TRUE
 LEFT JOIN LATERAL (
 SELECT b.close,b.volume FROM bars b WHERE b.instrument_id=fc.instrument_id
 AND b.trade_date=CAST(fc.day AS VARCHAR)
 AND CAST(b.available_at AS TIMESTAMPTZ)<=fc.cutoff
 ORDER BY CAST(b.available_at AS TIMESTAMPTZ) DESC,b.evidence_id DESC
 LIMIT 1) b ON TRUE""")
db.execute("""CREATE TEMP VIEW featurecompare AS SELECT x.*,
 CASE x.curve_rank WHEN 1 THEN EXP(f.feature_curve_log_settle_m1)
 WHEN 2 THEN EXP(f.feature_curve_log_settle_m2)
 WHEN 3 THEN EXP(f.feature_curve_log_settle_m3)
 ELSE EXP(f.feature_curve_log_settle_m4) END old_settle,
 CASE x.curve_rank WHEN 1 THEN EXP(f.feature_curve_log_volume_m1)
 WHEN 2 THEN EXP(f.feature_curve_log_volume_m2)
 WHEN 3 THEN EXP(f.feature_curve_log_volume_m3)
 ELSE EXP(f.feature_curve_log_volume_m4) END old_volume_exp,
 CASE x.curve_rank WHEN 1 THEN f.feature_curve_dte_m1
 WHEN 2 THEN f.feature_curve_dte_m2
 WHEN 3 THEN f.feature_curve_dte_m3
 ELSE f.feature_curve_dte_m4 END old_dte
 FROM featurefacts x JOIN oldfeat f ON CAST(f.trade_date AS DATE)=x.day""")
print('FEATURE_PARITY',db.execute("""SELECT curve_rank,
 COUNT(*) total,COUNT(*) FILTER(WHERE settle IS NULL) missing_settle,
 COUNT(*) FILTER(WHERE bar_volume IS NULL) missing_bar_volume,
 COUNT(*) FILTER(WHERE ABS(settle-old_settle)<1e-8) match_settle,
 COUNT(*) FILTER(WHERE ABS(COALESCE(settle,bar_close)-old_settle)<1e-8) match_fallback,
 COUNT(*) FILTER(WHERE ABS(bar_volume-old_volume_exp)<1e-7) volume_exp_match,
 COUNT(*) FILTER(WHERE ABS(bar_volume-(old_volume_exp-1))<1e-7) volume_log1p_match,
 COUNT(*) FILTER(WHERE ABS(dte-old_dte)<1e-8) dte_match,
 ROUND(MAX(ABS(COALESCE(settle,bar_close)-old_settle)),6) max_price_delta,
 ROUND(MAX(ABS(dte-old_dte)),6) max_dte_delta
 FROM featurecompare GROUP BY 1 ORDER BY 1""").fetchall(),flush=True)
print('FEATURE_MISMATCH_EXAMPLES',db.execute("""SELECT day,curve_rank,symbol,
 ROUND(old_settle,5),settle,bar_close,old_dte,dte,
 ROUND(old_volume_exp,1),bar_volume
 FROM featurecompare WHERE settle IS NULL OR ABS(settle-old_settle)>1e-8
 OR ABS(dte-old_dte)>1e-8 ORDER BY day,curve_rank LIMIT 16""").fetchall(),flush=True)
print('EXPIRY_HOUR_DRIFT',db.execute("""SELECT symbol,MIN(day),MAX(day),COUNT(*) n,
 ROUND(MIN(old_dte-dte)*24,3) low_hours, ROUND(MAX(old_dte-dte)*24,3) high_hours
 FROM featurecompare WHERE ABS(dte-old_dte)>1e-8
 GROUP BY symbol ORDER BY n DESC,symbol""").fetchall(),flush=True)
print('SOURCE_DEFINITION_TIME',db.execute("""SELECT symbol,CAST(expiry_utc AS VARCHAR),CAST(first_known AS VARCHAR)
 FROM identities WHERE symbol IN (SELECT DISTINCT symbol FROM featurecompare
 WHERE ABS(dte-old_dte)>1e-8) ORDER BY symbol""").fetchall(),flush=True)
print('NGZ1_VERSIONED_DEFS',db.execute("""SELECT instrument_id,expiration,
 COUNT(*) version_rows,CAST(MIN(CAST(available_at AS TIMESTAMPTZ)) AS VARCHAR),
 CAST(MAX(CAST(available_at AS TIMESTAMPTZ)) AS VARCHAR)
 FROM defs WHERE symbol='NGZ1' GROUP BY 1,2 ORDER BY 1,2""").fetchall(),flush=True)
source_dates=db.execute("""SELECT
 (SELECT MAX(CAST(trade_date AS DATE)) FROM oldfeat),
 (SELECT MAX(CAST(trade_date AS DATE)) FROM oldpath),
 (SELECT MAX(CAST(trade_date AS DATE)) FROM bars),
 (SELECT MAX(CAST(trade_date AS DATE)) FROM stats)""").fetchone()
assert all(x.isoformat()<='2022-12-31' for x in source_dates), 'protected date'
path_pass=db.execute("""SELECT COUNT(*),
 COUNT(DISTINCT CASE WHEN ABS(rebuilt_open-open_price)<1e-9 THEN day END),
 COUNT(DISTINCT CASE WHEN first_known<session_open THEN day END)
 FROM pathmatch""").fetchone()
assert path_pass==(3897,3897,3897), ('path parity failed',path_pass)
feature_pass=db.execute("""SELECT COUNT(*),
 COUNT(*) FILTER(WHERE ABS(settle-old_settle)<1e-8),
 COUNT(*) FILTER(WHERE ABS(bar_volume-(old_volume_exp-1))<1e-7),
 COUNT(*) FILTER(WHERE ABS(dte-old_dte)<1e-8)
 FROM featurecompare""").fetchone()
assert feature_pass==(12352,12352,12352,12352), ('feature parity failed',feature_pass)
print('PASS_FULL_HISTORY',path_pass,feature_pass,flush=True)
