import pandas as pd
import pytest

from commodity.config import data_config
from commodity.rolls import build_derived_contract_path, within_contract_log_returns


def _contracts() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2026-01-05", periods=4, freq="D", tz="UTC")
    liquidity = [
        ((100, 100), (50, 50)),
        ((90, 90), (120, 110)),
        ((80, 80), (130, 120)),
        ((70, 70), (140, 130)),
    ]
    for date, pair in zip(dates, liquidity, strict=True):
        rows.extend([
            {"trade_date": date, "contract_id": "NGF26", "expiration": "2026-01-20", "settle": 3.0, "volume": pair[0][0], "open_interest": pair[0][1]},
            {"trade_date": date, "contract_id": "NGG26", "expiration": "2026-02-20", "settle": 3.2 + 0.01 * len(rows), "volume": pair[1][0], "open_interest": pair[1][1]},
        ])
    return pd.DataFrame(rows)


def _policy() -> dict:
    return {"method": "dual_liquidity_crossover", "confirmation_sessions": 1, "forced_roll_days_before_expiry": 0}


def test_roll_policy_has_no_hidden_defaults() -> None:
    with pytest.raises(ValueError, match="missing explicit fields"):
        build_derived_contract_path(_contracts(), data_config()["canonical_contract_schema"], {"method": "dual_liquidity_crossover"})


def test_roll_uses_prior_session_volume_and_open_interest() -> None:
    path = build_derived_contract_path(
        _contracts(), data_config()["canonical_contract_schema"], _policy()
    )
    assert list(path["contract_id"]) == ["NGF26", "NGF26", "NGG26", "NGG26"]
    assert path.iloc[2]["roll_reason"] == "prior_session_dual_liquidity"


def test_returns_are_blank_across_roll_boundary() -> None:
    path = build_derived_contract_path(
        _contracts(), data_config()["canonical_contract_schema"], _policy()
    )
    returns = within_contract_log_returns(path)
    assert pd.isna(returns.iloc[0])
    assert pd.notna(returns.iloc[1])
    assert pd.isna(returns.iloc[2])
    assert pd.notna(returns.iloc[3])
