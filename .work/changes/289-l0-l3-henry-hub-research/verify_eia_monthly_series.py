from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
archive = ROOT / "data" / "raw" / "snapshots" / "eia" / "20260813-v1-ng-bulk" / "NG.zip"
wanted = {
    "NG.N9070US2.M", "NG.N9140US2.M", "NG.N9100US2.M",
    "NG.N9130US2.M", "NG.NGM_EPG0_SAO_R48_MMCF.M", "NG.RNGWHHD.M",
}
found: dict[str, dict[str, object]] = {}
with zipfile.ZipFile(archive) as zf, zf.open("NG.txt") as handle:
    for raw in handle:
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        series_id = str(item.get("series_id", ""))
        if series_id in wanted:
            found[series_id] = {key: item.get(key) for key in ("series_id", "name", "units", "f", "start", "end")}
print(json.dumps({"found": found, "missing": sorted(wanted - set(found))}, indent=2))
raise SystemExit(0 if set(found) == wanted else 2)
