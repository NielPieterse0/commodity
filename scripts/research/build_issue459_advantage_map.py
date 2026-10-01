from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

EVIDENCE_CLASSES = {
    "positive_clue",
    "empirical_negative",
    "null_or_inconclusive",
    "underpowered",
    "source_or_data_hold",
    "role_unidentifiable",
    "untested_mechanism",
    "governance_only",
}

_STATUS_KEYS = {
    "status",
    "programme_status",
    "development_disposition",
    "disposition",
    "promotion_disposition",
    "candidate_status",
}
_IDENTIFIER_KEYS = {
    "finding_id", "design_id", "candidate_id", "config_id", "id", "family",
    "role", "outer_block_id", "block_id", "specialist", "model_id",
}


def classify_evidence(status: str, reason: str) -> str:
    text = f"{status} {reason}".lower()
    if "external_literature" in text or "not_yet_reproduced" in text:
        return "untested_mechanism"
    if "unidentifiable" in text or "cannot identify" in text:
        return "role_unidentifiable"
    if any(token in text for token in ("source_not_proven", "source not proven", "source gate", "publication", "availability", "timing ambiguity")):
        return "source_or_data_hold"
    if any(token in text for token in ("insufficient", "underpowered", "undersized", "minimum_history", "minimum training")):
        return "underpowered"
    if any(token in text for token in ("no_matched_marginal", "no matched marginal", "no_robust", "no robust", "rejected_by_evidence", "not retained", "complete_not_promoted", "complete not promoted")):
        return "empirical_negative"
    if any(token in text for token in ("retained_for_investigation_not_approved", "retained for investigation not approved", "inconclusive", "null", "no new deployable")):
        return "null_or_inconclusive"
    if any(token in text for token in ("retain", "advantage", "promot")) and not any(
        token in text for token in ("not_approved", "not approved", "not_promoted", "not promoted")
    ):
        return "positive_clue"
    return "governance_only"


def _economic_metrics(obj: dict[str, Any]) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    for key, value in obj.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        name = key.lower()
        if any(token in name for token in ("pnl", "return", "delta", "trade", "month", "drawdown", "turnover", "coverage", "accuracy")):
            metrics[key] = value
    return dict(sorted(metrics.items()))


def _status_reason(obj: dict[str, Any]) -> tuple[str, str]:
    statuses = [str(obj[key]) for key in sorted(_STATUS_KEYS & obj.keys()) if isinstance(obj[key], str)]
    reason = str(obj.get("reason", "")) if isinstance(obj.get("reason", ""), str) else ""
    return " | ".join(statuses), reason


def _walk_json(obj: Any, source_path: str, trail: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        status, reason = _status_reason(obj)
        finding_id = obj.get("finding_id")
        literature = isinstance(finding_id, str) and "programme_status" in obj
        if status or reason or literature:
            effective_status = status or ("external_literature_finding_not_yet_reproduced" if literature else "")
            rows.append(
                {
                    "source_kind": "research_json",
                    "source_path": source_path,
                    "object_path": "/".join(trail) or "$",
                    "status": effective_status,
                    "reason": reason,
                    "classification": classify_evidence(effective_status, reason),
                    "identifiers": {
                        key: obj[key]
                        for key in sorted(_IDENTIFIER_KEYS & obj.keys())
                        if isinstance(obj[key], (str, int, float)) and not isinstance(obj[key], bool)
                    },
                    "economic_metrics": _economic_metrics(obj),
                }
            )
        for key in sorted(obj):
            _walk_json(obj[key], source_path, trail + (str(key),), rows)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _walk_json(value, source_path, trail + (str(index),), rows)


def _is_protected_search_artifact(path: Path) -> bool:
    name = path.name.lower()
    return any(token in name for token in ("confirmation", "true-forward", "paper", "sim", "live"))


def _load_json(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    return json.loads(path.read_text(encoding="utf-8"))


def _foundation_clues(root: Path) -> list[dict[str, Any]]:
    relative = "research/programmes/003-natural-gas-trading-decision-system/phase4-foundation-specialists-v1.json"
    payload = _load_json(root, relative)
    candidates = payload["phase5_handoff"]["ordered_candidates"]
    wanted = {"timesfm-baseline-short-modifier", "kronos-baseline-long-modifier"}
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if candidate.get("candidate_id") not in wanted:
            continue
        row = {
            "clue_id": candidate["candidate_id"],
            "classification": "positive_clue",
            "source_path": relative,
            "object_path": f"phase5_handoff/ordered_candidates/{index}",
            "role": candidate["role"],
            **candidate["evidence"],
        }
        rows.append(row)
    return rows


def _issue426_clues(root: Path) -> list[dict[str, Any]]:
    relative = "research/programmes/004-v2-maximum-reproducible-one-month-return/issue426-result-v1.json"
    payload = _load_json(root, relative)
    return [
        {
            "clue_id": "issue426-storage",
            "classification": "positive_clue",
            "source_path": relative,
            "object_path": "family_results/storage",
            "mean_monthly_net_return_delta": float(payload["family_results"]["storage"]["mean_monthly_net_return_delta"]),
        },
        {
            "clue_id": "issue426-positioning",
            "classification": "positive_clue",
            "source_path": relative,
            "object_path": "family_results/positioning",
            "mean_monthly_net_return_delta": float(payload["family_results"]["positioning"]["mean_monthly_net_return_delta"]),
        },
        {
            "clue_id": "issue426-storage-weather-interaction",
            "classification": "positive_clue",
            "source_path": relative,
            "object_path": "combined_interaction",
            "mean_monthly_net_return_delta": float(payload["combined_interaction"]["mean_monthly_net_return_delta"]),
        },
    ]


def _issue427_clue(root: Path) -> dict[str, Any]:
    relative = "research/programmes/004-v2-maximum-reproducible-one-month-return/issue427-result-v1.json"
    payload = _load_json(root, relative)
    core = payload["core"]["development_advantages"]
    ids = {str(row["id"]): float(row["gate"]["mean_outer_monthly_net_return_delta"]) for row in core}
    return {
        "clue_id": "issue427-retained-signals",
        "classification": "positive_clue",
        "source_path": relative,
        "object_path": "core/development_advantages + specialist development advantages",
        "signals": [
            "range_breakout", "volume_confirmation", "trend_strength", "positioning",
            "jump_intensity", "volatility_of_volatility",
        ],
        "core_mean_outer_monthly_net_return_deltas": ids,
    }


def _find_dict(obj: Any, predicate) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        if predicate(obj):
            return obj
        for key in sorted(obj):
            found = _find_dict(obj[key], predicate)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_dict(value, predicate)
            if found is not None:
                return found
    return None


def _issue448_clue(root: Path) -> dict[str, Any]:
    relative = "research/programmes/004-v2-maximum-reproducible-one-month-return/issue448-result-v1.json"
    payload = _load_json(root, relative)
    item = payload["family_results"]["market_structure.open_interest"]
    return {
        "clue_id": "issue448-open-interest",
        "classification": "positive_clue",
        "source_path": relative,
        "object_path": "family_results/market_structure.open_interest",
        "mean_monthly_net_return_delta": float(item["mean_monthly_net_return_delta"]),
    }


def _issue428_clue(root: Path) -> dict[str, Any]:
    relative = "research/programmes/004-v2-maximum-reproducible-one-month-return/issue428-result-v1.json"
    payload = _load_json(root, relative)
    outer = _find_dict(
        payload,
        lambda row: row.get("outer_block_id") == "outer-2021-2022"
        and row.get("selected_config_id") == "meta-interactions-p60",
    )
    if outer is None:
        outer = _find_dict(
            payload,
            lambda row: row.get("selected_config", {}).get("config_id") == "meta-interactions-p60"
            if isinstance(row.get("selected_config"), dict) else False,
        )
    if outer is None:
        raise RuntimeError("issue459 cannot locate the final #428 meta-interactions-p60 outer result")
    effective = outer.get("selected_effective_sample") or outer.get("effective_sample") or {}
    delta = outer.get("delta_vs_baseline") or outer.get("selected_delta_vs_baseline") or {}
    return {
        "clue_id": "issue428-meta-interactions-p60",
        "classification": "underpowered",
        "source_path": relative,
        "object_path": "outer_results/outer-2021-2022",
        "risk_executed_selected_trades": int(effective["selected_trades"]),
        "nonempty_months": int(effective["nonempty_months"]),
        "mean_monthly_net_return_delta": float(
            delta.get("mean_monthly_net_return_delta", outer.get("mean_monthly_net_return_delta", 0.0))
        ),
        "reason": "positive conditional development effect but insufficient risk-executed sample",
    }


def build_advantage_map(root: Path) -> dict[str, Any]:
    root = root.resolve()
    raw: list[dict[str, Any]] = []
    excluded: list[str] = []
    research_root = root / "research" / "programmes"
    for path in sorted(research_root.rglob("*.json"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.name.lower().startswith("issue459-"):
            continue
        if _is_protected_search_artifact(path) or "phase7-" in path.name.lower():
            excluded.append(relative)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        _walk_json(payload, relative, (), raw)
    change_rows, governed_change_files_scanned = _change_record_rows(root)
    raw.extend(change_rows)
    raw.sort(key=lambda row: (row["source_path"], row["object_path"], row["status"], row["reason"]))

    priority = _foundation_clues(root)
    priority.extend(_issue426_clues(root))
    priority.append(_issue427_clue(root))
    priority.append(_issue448_clue(root))
    issue428_path = root / "research/programmes/004-v2-maximum-reproducible-one-month-return/issue428-result-v1.json"
    if issue428_path.exists():
        priority.append(_issue428_clue(root))
    priority.sort(key=lambda row: row["clue_id"])
    counts = Counter(row["classification"] for row in raw)
    return {
        "schema_version": 1,
        "issue": 459,
        "evidence_window_end": "2022-12-31",
        "protected_confirmation_accessed": False,
        "raw_evidence_count": len(raw),
        "classification_counts": {key: counts.get(key, 0) for key in sorted(EVIDENCE_CLASSES)},
        "source_summary": {
            "governed_change_files_scanned": governed_change_files_scanned,
            "governed_change_rows": len(change_rows),
        },
        "excluded_artifacts": excluded,
        "raw_evidence": raw,
        "priority_clues": priority,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_advantage_map(args.root)
    output = args.output or args.root / "research/programmes/004-v2-maximum-reproducible-one-month-return/issue459-advantage-map-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"output": str(output), "raw_evidence_count": payload["raw_evidence_count"], "classification_counts": payload["classification_counts"], "priority_clue_count": len(payload["priority_clues"])}, indent=2, sort_keys=True))


def _change_record_rows(root: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    files_scanned = 0
    changes_root = root / ".work" / "changes"
    keywords = (
        "hold",
        "retain",
        "disposition",
        "advantage",
        "marginal",
        "promotion",
        "failed",
        "passed",
        "result",
    )
    for path in sorted(changes_root.rglob("*.md"), key=lambda item: item.as_posix()):
        if path.name not in {"closeout.md", "spec.md", "plan.md", "tasks.md"}:
            continue
        if path.parent.name == "459-historical-evidence-recombination-joint-advantage-discovery":
            continue
        files_scanned += 1
        relative = path.relative_to(root).as_posix()
        change_id = path.parent.name
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or not any(keyword in line.lower() for keyword in keywords):
                continue
            rows.append(
                {
                    "source_kind": "governed_change_record",
                    "source_path": relative,
                    "object_path": f"line:{line_number}",
                    "status": line,
                    "reason": "",
                    "classification": classify_evidence(line, ""),
                    "identifiers": {"change_id": change_id},
                    "economic_metrics": {},
                }
            )
    return rows, files_scanned


if __name__ == "__main__":
    main()
