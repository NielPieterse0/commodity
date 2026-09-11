from __future__ import annotations

import json
from pathlib import Path

from commodity.market_only_phase2 import (
    _build_segmented_decision_origins,
    _canonicalize_one_origin_per_fill,
    build_phase2_inputs,
    reconstruct_market_history,
)
from commodity.phase2_runtime import Phase2CheckpointStore, Phase2Telemetry

repo = Path(__file__).resolve().parents[2]
cfg = json.loads((repo / "config/phase2_market_only.json").read_text(encoding="utf-8"))
raw_root = Path(r"C:\Projects\commodity\data\raw\snapshots\databento\ng-full-history-v1")
runtime_repo = repo.parents[2] if repo.parent.name == "worktrees" else repo
out = runtime_repo / ".work/runtime/359-stacking-policy/phase5-inputs"
out.mkdir(parents=True, exist_ok=True)
telemetry = Phase2Telemetry(out / "telemetry.jsonl", heartbeat_seconds=15, echo=True)
checkpoint_store = Phase2CheckpointStore(out / "checkpoints", telemetry)

with checkpoint_store.run_lock():
    canonical, market, bars, provenance = reconstruct_market_history(
        raw_root,
        cfg,
        checkpoint_store=checkpoint_store,
        telemetry=telemetry,
    )
session, features = build_phase2_inputs(canonical, market, bars, cfg, telemetry=telemetry)
origins, feature_columns = _build_segmented_decision_origins(
    session,
    features,
    horizon_sessions=int(cfg["execution_contract"]["horizon_sessions"]),
)
origins, origin_canonicalization = _canonicalize_one_origin_per_fill(origins)

session.to_csv(out / "session-path.csv", index=False, lineterminator="\n")
features.to_csv(out / "features.csv", index=False, lineterminator="\n")
origins.to_csv(out / "origins.csv", index=False, lineterminator="\n")
(out / "metadata.json").write_text(
    json.dumps(
        {
            "provenance": provenance,
            "session_rows": len(session),
            "feature_rows": len(features),
            "origin_rows": len(origins),
            "origin_canonicalization": origin_canonicalization,
            "feature_columns": feature_columns,
        },
        indent=2,
        default=str,
    )
    + "\n",
    encoding="utf-8",
    newline="\n",
)
print(
    "READY",
    len(session),
    len(features),
    len(origins),
    provenance["provenance_sha256"],
)
