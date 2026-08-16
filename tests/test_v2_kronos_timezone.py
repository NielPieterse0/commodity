import pandas as pd
import pytest

from commodity.v2_kronos import KronosContractError, build_pit_context


def _market() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-08-10T23:59:00Z"],
            "contract_id": ["NGU6"],
            "expiration": ["2026-08-27T00:00:00Z"],
            "available_at": ["2026-08-10T23:59:00Z"],
            "open": [3.0],
            "high": [3.2],
            "low": [2.9],
            "close": [3.1],
            "volume": [1000.0],
        }
    )


@pytest.mark.parametrize("column", ["trade_date", "expiration", "available_at"])
def test_market_identity_timestamp_requires_explicit_timezone(column: str) -> None:
    frame = _market()
    frame.loc[0, column] = "2026-08-10 23:59:00"
    with pytest.raises(KronosContractError, match="timezone-aware"):
        build_pit_context(frame, "2026-08-10T23:59:00Z")
