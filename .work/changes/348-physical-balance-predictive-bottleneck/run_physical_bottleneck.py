from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from commodity.research_forecasting import (
    build_bhlr_physical_bottleneck_panel,
    predict_c_from_frozen_b_models,
    score_bottleneck_pair,
    walk_forward_ab,
)

MEMBERS = {
    "ng_henry": "BHLR_codes/Table3/baseline_logs/NG_HENRY.txt",
    "production": "BHLR_codes/Table3/baseline_logs/PROD_DRY.txt",
    "storage": "BHLR_codes/Table3/baseline_logs/STORE_WORK.txt",
    "consumption": "BHLR_codes/Table4/small_model_4/CONS_TOT.txt",
}


def _load_member(archive: zipfile.ZipFile, member: str) -> tuple[np.ndarray, str]:
    payload = archive.read(member)
    values = np.loadtxt(io.BytesIO(payload))
    return values, hashlib.sha256(payload).hexdigest()


def _classify_ab(result: dict[str, object]) -> str:
    if bool(result["survives_primary_rule"]):
        return "PASS_REALIZED_PHYSICAL_SIGNAL"
    relative = float(result["relative_rmse_improvement"])
    primary = result["primary"]
    assert isinstance(primary, dict)
    thirds = result["chronological_thirds_rmse_improvement"]
    assert isinstance(thirds, dict)
    negative_thirds = sum(float(value) < 0.0 for value in thirds.values())
    if relative <= 0.0 and float(primary["ci_upper"]) <= 0.0:
        return "RULES_OUT_MATERIAL_PREDICTIVE_BENEFIT"
    if negative_thirds >= 2:
        return "RULES_OUT_MATERIAL_PREDICTIVE_BENEFIT"
    return "INCONCLUSIVE_REALIZED_PHYSICAL_SIGNAL"


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    with zipfile.ZipFile(args.source_zip) as archive:
        loaded = {name: _load_member(archive, member) for name, member in MEMBERS.items()}
    matrices = {name: value for name, (value, _) in loaded.items()}
    member_sha256 = {name: digest for name, (_, digest) in loaded.items()}

    origins = pd.period_range("1997-01", "2020-08", freq="M")
    panel = build_bhlr_physical_bottleneck_panel(
        ng_henry=matrices["ng_henry"],
        production=matrices["production"],
        storage=matrices["storage"],
        consumption=matrices["consumption"],
        origin_periods=origins,
        start_row=288,
        start_column=72,
        final_column=397,
    )
    if len(panel) != 284 or panel.index[-1] >= pd.Period("2020-09", freq="M"):
        raise RuntimeError("Frozen chronology or protected-window exclusion changed")

    rows = np.arange(288, 288 + len(origins))
    columns = np.arange(72, 72 + len(origins))
    next_vintage_target = matrices["ng_henry"][rows + 1, columns + 1]
    final_target = matrices["ng_henry"][rows + 1, 397]
    target_revision_max_abs = float(np.max(np.abs(next_vintage_target - final_target)))
    if not np.allclose(next_vintage_target, final_target, rtol=0.0, atol=1e-12):
        raise RuntimeError("Henry Hub target failed the frozen non-revision audit")

    a_predictions, b_predictions, frozen_b = walk_forward_ab(
        panel,
        development_rows=72,
        alpha=10.0,
    )
    if len(a_predictions) != 212 or not a_predictions.index.equals(b_predictions.index):
        raise RuntimeError("Frozen A/B OOS month identity changed")
    ab = score_bottleneck_pair(
        b_predictions,
        a_predictions,
        primary_block_size=3,
        sensitivity_block_sizes=(1, 6),
        resamples=2000,
        confidence=0.95,
        seed=348,
    )
    ab_disposition = _classify_ab(ab)

    c_predictions: pd.DataFrame | None = None
    c_vs_b: dict[str, object] | None = None
    c_vs_a: dict[str, object] | None = None
    pit_disposition = "NOT_RUN_A_TO_B_DID_NOT_SURVIVE"
    retention_fraction: float | None = None
    if bool(ab["survives_primary_rule"]):
        c_predictions = predict_c_from_frozen_b_models(panel, frozen_b)
        c_vs_b = score_bottleneck_pair(
            c_predictions, b_predictions, primary_block_size=3,
            sensitivity_block_sizes=(1, 6), resamples=2000, confidence=0.95, seed=349,
        )
        c_vs_a = score_bottleneck_pair(
            c_predictions, a_predictions, primary_block_size=3,
            sensitivity_block_sizes=(1, 6), resamples=2000, confidence=0.95, seed=350,
        )
        ab_improvement = float(ab["relative_rmse_improvement"])
        c_improvement = float(c_vs_a["relative_rmse_improvement"])
        retention_fraction = c_improvement / ab_improvement if ab_improvement > 0.0 else None
        if retention_fraction is not None and retention_fraction >= 0.5 and bool(c_vs_a["survives_primary_rule"]):
            pit_disposition = "PASS_PIT_SIGNAL_PRESERVED"
        elif retention_fraction is not None and (retention_fraction < 0.5 or not bool(c_vs_a["survives_primary_rule"])):
            pit_disposition = "INFORMATION_TIMING_BOTTLENECK_SUPPORTED"
        else:
            pit_disposition = "INCONCLUSIVE_PIT_DEGRADATION"

    result = {
        "schema_version": 1,
        "design_id": "rep-021-physical-balance-predictive-bottleneck",
        "issue": 348,
        "source_zip_sha256": hashlib.sha256(args.source_zip.read_bytes()).hexdigest(),
        "source_member_sha256": member_sha256,
        "chronology": {"development_rows": 72, "research_oos_rows": 212, "research_oos_end": "2020-08"},
        "target_nonrevision_audit": {"passed": True, "max_abs_difference": target_revision_max_abs},
        "A_to_B": ab,
        "A_to_B_disposition": ab_disposition,
        "B_to_C": c_vs_b,
        "C_to_A": c_vs_a,
        "pit_retention_fraction": retention_fraction,
        "pit_disposition": pit_disposition,
        "c_scored": c_predictions is not None,
        "protected_confirmation_accessed": False,
        "confirmation_eligibility": "ineligible_no_fresh_historical_block",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(
        json.dumps(_jsonable(result), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    predictions = pd.DataFrame(
        {
            "actual_log_hh": a_predictions["actual"],
            "A_prediction": a_predictions["prediction"],
            "B_prediction": b_predictions["prediction"],
        }
    )
    if c_predictions is not None:
        predictions["C_prediction"] = c_predictions["prediction"]
    predictions.index = predictions.index.astype(str)
    predictions.index.name = "origin_month"
    predictions.to_csv(args.output_dir / "predictions.csv", lineterminator="\n")
    print(json.dumps({
        "A_to_B_disposition": ab_disposition,
        "A_to_B_relative_rmse_improvement": ab["relative_rmse_improvement"],
        "A_to_B_primary_ci": [ab["primary"]["ci_lower"], ab["primary"]["ci_upper"]],
        "A_to_B_nonnegative_thirds": ab["nonnegative_chronological_thirds"],
        "c_scored": c_predictions is not None,
        "pit_disposition": pit_disposition,
        "pit_retention_fraction": retention_fraction,
    }, indent=2))


if __name__ == "__main__":
    main()
