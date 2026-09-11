from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
PHASE2_CONFIG = REPO_ROOT / "config" / "phase2_market_only.json"
SAMPLE_KEYS = Path(__file__).with_name("second-line-sample-keys.csv")
KRONOS_DIAGNOSTIC = Path(__file__).with_name("phase4_kronos_path_diagnostic.py")
TARGET_COLUMNS = ["open", "high", "low", "close", "volume"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_kronos_helpers():
    spec = importlib.util.spec_from_file_location("phase4_kronos_path_diagnostic", KRONOS_DIAGNOSTIC)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load frozen path diagnostic helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Export exact frozen Phase-4 Moirai context bundle")
    parser.add_argument("--phase2-checkpoint-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cfg = json.loads(PHASE2_CONFIG.read_text(encoding="utf-8"))
    helper = _load_kronos_helpers()
    eligible, excluded = helper._cases(args.phase2_checkpoint_root, cfg, 512)
    keys = pd.read_csv(SAMPLE_KEYS)
    wanted = {
        (pd.Timestamp(row.prediction_time).isoformat(), str(row.contract_id))
        for row in keys.itertuples(index=False)
    }
    selected = [
        case for case in eligible
        if (case["prediction_time"].isoformat(), case["contract_id"]) in wanted
    ]
    if len(selected) != 96:
        found = {(c["prediction_time"].isoformat(), c["contract_id"]) for c in selected}
        missing = sorted(wanted - found)
        raise RuntimeError(f"frozen sample mismatch: selected={len(selected)} missing={missing[:3]}")

    rows = []
    for case in sorted(selected, key=lambda c: (c["prediction_time"], c["contract_id"])):
        rows.append({
            "outer_block_id": str(case["outer_block_id"]),
            "prediction_time": case["prediction_time"].isoformat(),
            "contract_id": str(case["contract_id"]),
            "current_close": float(case["current_close"]),
            "history": case["history"][TARGET_COLUMNS].astype(float).values.tolist(),
            "actual": case["actual"][TARGET_COLUMNS].astype(float).values.tolist(),
        })

    payload = {
        "schema_version": 1,
        "authority": "github-issue-358-comment-5634786235",
        "sample_keys_sha256": _sha256(SAMPLE_KEYS),
        "protected_confirmation_accessed": False,
        "max_context": 512,
        "pred_len": 5,
        "target_columns": TARGET_COLUMNS,
        "excluded_before_frozen_sample": excluded,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "rows": len(rows),
        "output": str(args.output),
        "output_sha256": _sha256(args.output),
        "protected_confirmation_accessed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
