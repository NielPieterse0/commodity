from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from commodity.cftc import (
    CftcCotClient,
    capture_cftc_v1_window,
    cftc_research_availability,
    load_cftc_v1_window,
    normalize_disaggregated_futures_only_archive,
)


def _archive_bytes(
    report_dates: list[str],
    *,
    report_date_column: str = "As_of_Date_Form_YYYY-MM-DD",
) -> bytes:
    frame = pd.DataFrame(
        {
            "Market_and_Exchange_Names": ["NATURAL GAS - NEW YORK MERCANTILE EXCHANGE"] * len(report_dates),
            report_date_column: report_dates,
            "CFTC_Contract_Market_Code": ["023651"] * len(report_dates),
            "Open_Interest_All": [1000] * len(report_dates),
            "Prod_Merc_Positions_Long_All": [100] * len(report_dates),
            "Prod_Merc_Positions_Short_All": [200] * len(report_dates),
            "Swap_Positions_Long_All": [300] * len(report_dates),
            "Swap__Positions_Short_All": [250] * len(report_dates),
            "M_Money_Positions_Long_All": [400] * len(report_dates),
            "M_Money_Positions_Short_All": [350] * len(report_dates),
            "M_Money_Positions_Spread_All": [50] * len(report_dates),
            "Other_Rept_Positions_Long_All": [120] * len(report_dates),
            "Other_Rept_Positions_Short_All": [110] * len(report_dates),
            "Pct_of_OI_M_Money_Long_All": [40.0] * len(report_dates),
            "Pct_of_OI_M_Money_Short_All": [35.0] * len(report_dates),
            "FutOnly_or_Combined": ["FutOnly"] * len(report_dates),
        }
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("f_year.txt", frame.to_csv(index=False))
    return buffer.getvalue()


def test_cftc_client_uses_official_annual_futures_only_archive() -> None:
    class Response:
        content = b"zip"

        def raise_for_status(self) -> None:
            pass

    class Session:
        def __init__(self) -> None:
            self.url = ""

        def get(self, url: str, timeout: int) -> Response:
            self.url = url
            assert timeout == 60
            return Response()

    session = Session()
    payload, url = CftcCotClient(session=session).fetch_year(2025)
    assert payload == b"zip"
    assert url.endswith("/fut_disagg_txt_2025.zip")
    assert session.url == url


def test_cftc_availability_uses_special_schedule_and_conservative_bounds() -> None:
    special = cftc_research_availability("2025-10-07")
    assert special["available_at"] == pd.Timestamp("2025-11-22T04:59:00Z")
    assert special["availability_basis"] == "cftc_special_announcement_end_of_day"

    ordinary = cftc_research_availability("2024-08-13")
    assert ordinary["available_at"] == pd.Timestamp("2024-08-21T03:59:00Z")
    assert ordinary["availability_basis"] == "cftc_ordinary_next_tuesday_end_of_day"

    scheduled = cftc_research_availability("2026-08-11")
    assert scheduled["available_at"] == pd.Timestamp("2026-08-15T03:59:00Z")
    assert scheduled["availability_basis"] == "cftc_2026_release_schedule_end_of_day"
    assert scheduled["availability_status"] == "reconstructed_conservative"


def test_cftc_normalization_preserves_variant_raw_hash_and_position_features() -> None:
    content = _archive_bytes(["2025-10-07", "2025-10-14"])
    frame = normalize_disaggregated_futures_only_archive(content, year=2025)
    assert len(frame) == 2
    assert frame["source_id"].eq("cftc_disaggregated_futures_only_023651").all()
    assert frame["source_variant"].eq("disaggregated_futures_only").all()
    assert frame["source_raw_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert frame.iloc[0]["observed_for"] == pd.Timestamp("2025-10-07T00:00:00Z")
    assert frame.iloc[0]["available_at"] == pd.Timestamp("2025-11-22T04:59:00Z")
    assert frame.iloc[0]["managed_money_net"] == 50
    assert frame.iloc[0]["producer_merchant_net"] == -100
    assert frame.iloc[0]["swap_dealer_net"] == 50
    assert frame.iloc[0]["revision_status"] == "point_in_time"


def test_cftc_normalization_accepts_current_report_date_header() -> None:
    content = _archive_bytes(
        ["2025-10-07", "2025-10-14"],
        report_date_column="Report_Date_as_YYYY-MM-DD",
    )
    frame = normalize_disaggregated_futures_only_archive(content, year=2025)
    assert list(frame["observed_for"]) == [
        pd.Timestamp("2025-10-07T00:00:00Z"),
        pd.Timestamp("2025-10-14T00:00:00Z"),
    ]


def test_cftc_window_capture_is_bounded_resumable_and_loadable(tmp_path: Path) -> None:
    class Client:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def fetch_year(self, year: int) -> tuple[bytes, str]:
            self.calls.append(year)
            return _archive_bytes([f"{year}-08-13", f"{year}-08-20"]), f"https://example/{year}.zip"

    client = Client()
    first = capture_cftc_v1_window(
        client, "2024-08-13", "2026-08-12", tmp_path, "2026-08-14T02:00:00Z"
    )
    assert client.calls == [2024, 2025, 2026]
    second = capture_cftc_v1_window(
        client, "2024-08-13", "2026-08-12", tmp_path, "2026-08-14T03:00:00Z"
    )
    assert client.calls == [2024, 2025, 2026]
    assert first == second
    frame = load_cftc_v1_window(tmp_path, "2024-08-13", "2026-08-12")
    assert len(frame) == 6
    assert frame["source_id"].eq("cftc_disaggregated_futures_only_023651").all()


def test_cftc_loader_fails_closed_when_required_year_snapshot_is_missing(tmp_path: Path) -> None:
    class Client:
        def fetch_year(self, year: int) -> tuple[bytes, str]:
            return _archive_bytes([f"{year}-08-13"]), f"https://example/{year}.zip"

    capture_cftc_v1_window(
        Client(), "2024-08-13", "2024-12-31", tmp_path, "2026-08-14T02:00:00Z"
    )
    try:
        load_cftc_v1_window(tmp_path, "2024-08-13", "2026-08-12")
    except ValueError as exc:
        assert "missing annual snapshot" in str(exc)
    else:
        raise AssertionError("CFTC V1 loader must fail closed when an annual snapshot is missing")
