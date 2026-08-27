# #212 PIT group-safe as-of join review

## Caller inventory

Production use of `asof_join_point_in_time` is currently bounded to `src/commodity/research_dataset.py::_join_source`.

`PitFeatureSource.group_columns` is now the mandatory explicit source identity contract; construction without it fails closed:

- `group_columns=()` explicitly asserts the source is already single-series or pre-aggregated/pivoted to one logical series for each `available_at`.
- non-empty `group_columns` declares a multi-series source identity and fails closed in `build_pit_dataset` until the dataset supplies matching grouped cutoffs or the source is aggregated/pivoted first.
- direct grouped joins must pass matching `by=` and `source_group_columns=` values.

Current production PIT feature sources are therefore treated as single-series/pre-aggregated at this boundary. No production caller currently supplies grouped cutoffs.

## Semantics preserved

`pd.merge_asof` remains `direction="backward"` with `allow_exact_matches=True`, so rows are eligible only when `available_at <= prediction_time`.

No feature/model tuning, empirical rerun, trading authority, or frozen experiment authority is changed by this slice.

## PR hygiene

PR #237 uses non-closing issue metadata (`Issue: #212`) because repository hygiene rejects GitHub issue-closing keywords in pull-request text.
