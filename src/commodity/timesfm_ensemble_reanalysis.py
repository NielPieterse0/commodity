from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from commodity.evaluation_protocol import benjamini_hochberg_adjust
from commodity.timesfm_zero_shot import (
    _dm_squared_error,
    _file_sha256,
    _return_metrics,
    _rmse_improvement,
    prepare_inputs,
)

CONTRACT_PATH = Path("docs/development/timesfm-ensemble-successor-preregistration/contract.json")
AUTHORITY_PATH = Path("docs/development/timesfm-ensemble-reanalysis/execution-authority.json")
SOURCE_PREDICTIONS = Path("artifacts/timesfm/timesfm-198-zero-shot-v1/predictions.csv")
SOURCE_RESULT = Path("artifacts/timesfm/timesfm-198-zero-shot-v1/result.json")
EXPECTED_CONTRACT_SHA256 = "c814dac9c7e8433909f820d7df636cc7a009fba8789970132a2a59ae220687f0"
EXPECTED_PREDICTIONS_SHA256 = "ad5a8794c363043780a661aac8619a342cf4cba0ad393394627f4bd927abb574"
EXPECTED_RESULT_SHA256 = "050b3023a08d9ffb57958a8ee361344dbce6df2216d0f760b6240d747de7da03"
EXPECTED_ROWS = 204


class TimesFMEnsembleReanalysisError(RuntimeError):
    """Raised when frozen #226/#228 reanalysis authority is violated."""


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TimesFMEnsembleReanalysisError(f"JSON authority must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_reanalysis_authority(repo_root: Path) -> dict[str, Any]:
    contract_path = repo_root / CONTRACT_PATH
    authority_path = repo_root / AUTHORITY_PATH
    if _sha256(contract_path) != EXPECTED_CONTRACT_SHA256:
        raise TimesFMEnsembleReanalysisError("#226 frozen contract hash drifted")
    contract = _json(contract_path)
    authority = _json(authority_path)
    if contract.get("contract_id") != "timesfm-226-ensemble-reanalysis-v1":
        raise TimesFMEnsembleReanalysisError("unexpected #226 contract id")
    if authority.get("execution_authorized") is not True:
        raise TimesFMEnsembleReanalysisError("#228 execution authority is not enabled")
    if authority.get("frozen_contract_sha256") != EXPECTED_CONTRACT_SHA256:
        raise TimesFMEnsembleReanalysisError("#228 binds the wrong frozen contract")
    forbidden_true = (
        "new_timesfm_forecasts_permitted",
        "weight_fitting_permitted",
        "candidate_dropping_permitted",
        "xreg_permitted",
        "fine_tuning_permitted",
        "lora_or_peft_permitted",
        "promotion_authorized",
        "trading_authority",
    )
    if any(authority.get(key) is not False for key in forbidden_true):
        raise TimesFMEnsembleReanalysisError("#228 authority permits a prohibited action")
    return {"contract": contract, "authority": authority}


def prepare_reanalysis(
    repo_root: Path,
    dataset_dir: Path,
    canonical_market_csv: Path,
) -> dict[str, Any]:
    authority = validate_reanalysis_authority(repo_root)
    predictions_path = repo_root / SOURCE_PREDICTIONS
    result_path = repo_root / SOURCE_RESULT
    if _file_sha256(predictions_path) != EXPECTED_PREDICTIONS_SHA256:
        raise TimesFMEnsembleReanalysisError("#224 prediction artifact hash mismatch")
    if _file_sha256(result_path) != EXPECTED_RESULT_SHA256:
        raise TimesFMEnsembleReanalysisError("#224 result artifact hash mismatch")
    prepared = prepare_inputs(repo_root, dataset_dir, canonical_market_csv)
    predictions = pd.read_csv(predictions_path)
    prior_result = _json(result_path)
    if len(predictions) != 3264:
        raise TimesFMEnsembleReanalysisError("#224 prediction row count drifted")
    candidates = authority["contract"]["candidates"]["members"]
    prior_family = prior_result.get("complementarity_family")
    if not isinstance(prior_family, list) or len(prior_family) != len(candidates):
        raise TimesFMEnsembleReanalysisError("F198 complementarity family shape drifted")
    return {
        **prepared,
        "successor_contract": authority["contract"],
        "execution_authority": authority["authority"],
        "predictions": predictions,
        "prior_result": prior_result,
    }


def _prior_family_map(prior_result: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    family = prior_result["complementarity_family"]
    mapped: dict[tuple[str, int], dict[str, Any]] = {}
    for item in family:
        key = (str(item["representation"]), int(item["context"]))
        if key in mapped:
            raise TimesFMEnsembleReanalysisError("duplicate F198 complementarity candidate")
        mapped[key] = item
    return mapped


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temp.replace(path)


def evaluate_reanalysis(prepared: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    contract = prepared["successor_contract"]
    predictions: pd.DataFrame = prepared["predictions"]
    cases = prepared["cases"]
    actual = np.asarray([case.actual_return for case in cases], dtype=float)
    if len(actual) != EXPECTED_ROWS:
        raise TimesFMEnsembleReanalysisError(
            f"reanalysis requires exactly {EXPECTED_ROWS} frozen OOS rows"
        )
    histgb = prepared["histgb"]["prediction"].to_numpy(dtype=float)
    if len(histgb) != EXPECTED_ROWS:
        raise TimesFMEnsembleReanalysisError("HistGB baseline does not cover 204 rows")
    zero = np.zeros(EXPECTED_ROWS, dtype=float)
    zero_mae = float(np.mean(np.abs(actual)))
    prior = _prior_family_map(prepared["prior_result"])
    rows: list[dict[str, Any]] = []
    for candidate in contract["candidates"]["members"]:
        representation = str(candidate["representation"])
        context = int(candidate["context"])
        subset = predictions.loc[
            (predictions["representation"] == representation)
            & (predictions["context"] == context)
        ]
        if len(subset) != len(actual):
            raise TimesFMEnsembleReanalysisError("candidate does not have 204-row coverage")
        if not np.allclose(subset["actual"].to_numpy(float), actual, rtol=0.0, atol=2e-15):
            raise TimesFMEnsembleReanalysisError("candidate actual values drifted")
        point = subset["point"].to_numpy(dtype=float)
        blend = 0.5 * point + 0.5 * histgb
        inference = _rmse_improvement(actual, blend, zero)
        metrics = _return_metrics(actual, blend, zero_mae)
        prior_item = prior.get((representation, context))
        if prior_item is None:
            raise TimesFMEnsembleReanalysisError("candidate missing from F198 family")
        rows.append({
            "representation": representation,
            "context": context,
            "rmse": metrics["rmse"],
            "mae": metrics["mae"],
            "mase": metrics["mase"],
            "direction_accuracy": metrics["direction_accuracy"],
            "prediction_actual_correlation": metrics["prediction_actual_correlation"],
            "zero_rmse_improvement": inference["rmse_improvement"],
            "zero_relative_rmse_improvement": inference["rmse_improvement"]
            / float(contract["baselines"]["primary_rmse"]),
            "p_value": inference["p_value_one_sided_improvement"],
            "bootstrap": inference,
            "diebold_mariano": _dm_squared_error(actual, blend, zero),
            "f198_histgb_rmse_improvement": float(prior_item["rmse_improvement"]),
            "f198_histgb_adjusted_p_value": float(prior_item["adjusted_p_value"]),
        })
    adjusted = benjamini_hochberg_adjust([item["p_value"] for item in rows])
    alpha = float(contract["evaluation"]["multiple_testing"]["max_adjusted_p_value"])
    for item, adjusted_p in zip(rows, adjusted, strict=True):
        item["adjusted_p_value"] = float(adjusted_p)
        item["passes_zero_gate"] = bool(
            item["zero_rmse_improvement"] > 0.0 and adjusted_p <= alpha
        )
        item["passes_histgb_gate"] = bool(
            item["f198_histgb_rmse_improvement"] > 0.0
            and item["f198_histgb_adjusted_p_value"] <= alpha
        )
        item["passes_joint_gate"] = bool(
            item["passes_zero_gate"] and item["passes_histgb_gate"]
        )
    return {
        "schema_version": 1,
        "execution_id": "timesfm-228-ensemble-reanalysis-v1",
        "rows": len(actual),
        "family": "F226_TIMESFM_BLEND_VS_ZERO_12",
        "candidates": rows,
        "benchmarks": {
            "zero_return_rmse": float(contract["baselines"]["primary_rmse"]),
            "phase_d_histgb_rmse": float(contract["baselines"]["secondary_rmse"]),
        },
        "decision": {
            "reanalysis_pass": any(item["passes_joint_gate"] for item in rows),
            "fresh_confirmation_required_after_pass": True,
            "trading_edge_established": False,
            "consumed_204_rows_are_fresh_confirmation": False,
        },
        "source_evidence": {
            "predictions_sha256": EXPECTED_PREDICTIONS_SHA256,
            "result_sha256": EXPECTED_RESULT_SHA256,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
        },
    }


def run_reanalysis(prepared: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    result = evaluate_reanalysis(prepared, output_dir)
    result_path = output_dir / "result.json"
    _atomic_json(result_path, result)
    manifest = {
        "schema_version": 1,
        "execution_id": result["execution_id"],
        "result_sha256": _file_sha256(result_path),
        "source_predictions_sha256": EXPECTED_PREDICTIONS_SHA256,
        "source_result_sha256": EXPECTED_RESULT_SHA256,
        "frozen_contract_sha256": EXPECTED_CONTRACT_SHA256,
    }
    _atomic_json(output_dir / "run-manifest.json", manifest)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute frozen #226 TimesFM ensemble reanalysis")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--canonical-market-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    prepared = prepare_reanalysis(args.repo_root, args.dataset_dir, args.canonical_market_csv)
    if args.preflight_only:
        print(json.dumps({"rows": len(prepared["cases"]), "authority": "ok"}, indent=2))
        return
    result = run_reanalysis(prepared, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
