from __future__ import annotations

import json
from pathlib import Path

from commodity.v2_indicator_contract import build_implementation_source_manifest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest = build_implementation_source_manifest(root)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
