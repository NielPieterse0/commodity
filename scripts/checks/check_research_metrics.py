from __future__ import annotations

from pathlib import Path

from commodity.research_metrics import load_ledger

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "artifacts" / "research-metrics" / "longitudinal-ledger.json"


def main() -> int:
    if not LEDGER.is_file():
        print("research-metrics: FAILED: canonical ledger is missing")
        return 1
    try:
        load_ledger(LEDGER)
    except (OSError, ValueError) as exc:
        print(f"research-metrics: FAILED: {exc}")
        return 1
    print("research-metrics: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
