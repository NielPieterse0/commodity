from __future__ import annotations

import hashlib
import json
from pathlib import Path

from commodity.config import assumptions_config, data_config
from commodity.market_data import canonical_market_readiness

ROOT = Path(__file__).resolve().parents[2]
DATABENTO_ROOT = ROOT / "data/raw/snapshots/databento/ng-full-history-v1"
EXPECTED_CANONICAL = "databento_henry_hub"
EXPECTED_EVALUATION = "massive_henry_hub_evaluation"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fail(message: str) -> None:
    raise ValueError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_local_batch(schema: str, job_id: str) -> None:
    directory = DATABENTO_ROOT / schema / job_id
    manifest = _load(directory / "manifest.json")
    if manifest.get("job_id") != job_id:
        _fail(f"Databento {schema} manifest job identity mismatch")
    for item in manifest.get("files", []):
        path = directory / str(item["filename"])
        if not path.is_file() or path.stat().st_size != int(item["size"]):
            _fail(f"Databento {schema} retained file missing or size-mismatched: {path.name}")
        expected = str(item["hash"]).removeprefix("sha256:")
        if _sha256(path) != expected:
            _fail(f"Databento {schema} retained file hash mismatch: {path.name}")


def main() -> int:
    try:
        cfg = data_config()
        sources = cfg["sources"]
        configured = cfg.get("canonical_market_source_id")
        if configured != EXPECTED_CANONICAL:
            _fail(f"canonical market source must be {EXPECTED_CANONICAL!r}")
        marked = [key for key, value in sources.items() if value.get("canonical_market_source") is True]
        if marked != [configured]:
            _fail(f"exactly the configured canonical source must be marked canonical: {marked}")

        canonical = canonical_market_readiness(cfg, assumptions_config(), configured)
        if not canonical["canonical_evidence_allowed"]:
            _fail(f"configured canonical source is not research-ready: {canonical['reasons']}")

        evaluation = canonical_market_readiness(cfg, assumptions_config(), EXPECTED_EVALUATION)
        if not evaluation["evaluation_evidence_allowed"]:
            _fail(f"Massive evaluation source is not evaluation-ready: {evaluation['evaluation_reasons']}")
        if evaluation["canonical_evidence_allowed"]:
            _fail("Massive evaluation source must not be canonical promotion evidence")

        canonical_source = sources[configured]
        if canonical_source.get("integrity_status") != "complete":
            _fail("configured Databento source is not marked integrity-complete")
        if canonical_source.get("licensing_rights_verified") is not True:
            _fail("configured Databento source lacks verified licensing rights")
        if not canonical_source.get("quarantine_evidence") or not canonical_source.get("repair_evidence"):
            _fail("configured Databento source lacks durable acquisition/repair evidence refs")

        if DATABENTO_ROOT.exists():
            acquisition = _load(DATABENTO_ROOT / "acquisition-state.json")
            request = acquisition.get("request", {})
            if request.get("dataset") != "GLBX.MDP3" or request.get("symbol") != "NG.FUT":
                _fail("retained Databento acquisition identity does not match configured Henry Hub source")
            if request.get("start") != "2010-06-06T00:00:00Z":
                _fail("retained Databento acquisition does not preserve the verified history start")
            for schema in ("definition", "ohlcv-1d", "statistics"):
                job = acquisition.get("jobs", {}).get(schema, {})
                if job.get("state") != "done" or int(job.get("record_count", 0)) <= 0:
                    _fail(f"retained Databento {schema} acquisition is incomplete")
                _verify_local_batch(schema, str(job["id"]))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"market-source-authority: FAILED: {exc}")
        return 2
    print("market-source-authority: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
