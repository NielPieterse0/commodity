from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from commodity.wngsr import (
    WngsrEvidenceClient,
    build_wngsr_feature_events,
    capture_wngsr_v1_window,
    load_wngsr_v1_window,
    normalize_wngsr_history_table,
    normalize_wngsr_revisions_table,
    parse_wngsr_workbooks,
    resolve_wngsr_release_availability,
)


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Week ending": ["2024-09-20", "2024-09-27"],
            "Lower 48 States": [300.0, 305.0],
        }
    )


def _revisions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Week ending": ["2024-09-20"],
            "Original Estimate": [290.0],
            "Revision Date": ["2024-11-18"],
        }
    )


def test_wngsr_tables_normalize_to_lower48_vintage_contract() -> None:
    history = normalize_wngsr_history_table(_history())
    revisions = normalize_wngsr_revisions_table(_revisions())

    assert list(history["observed_for"].dt.date.astype(str)) == [
        "2024-09-20",
        "2024-09-27",
    ]
    assert list(history["storage_lower48_bcf"]) == [300.0, 305.0]
    assert revisions.iloc[0]["observed_for"] == pd.Timestamp("2024-09-20T00:00:00Z")
    assert revisions.iloc[0]["original_storage_lower48_bcf"] == 290.0
    assert pd.isna(revisions.iloc[0]["revised_storage_lower48_bcf"])
    assert revisions.iloc[0]["revision_date"] == pd.Timestamp("2024-11-18T00:00:00Z")


def test_wngsr_release_availability_includes_2024_holidays() -> None:
    regular = resolve_wngsr_release_availability("2024-09-20")
    thanksgiving = resolve_wngsr_release_availability("2024-11-22")
    christmas = resolve_wngsr_release_availability("2024-12-20")

    assert regular == pd.Timestamp("2024-09-26T14:30:00Z")
    assert thanksgiving == pd.Timestamp("2024-11-27T17:00:00Z")
    assert christmas == pd.Timestamp("2024-12-27T15:30:00Z")


def test_wngsr_revisions_are_later_state_events_not_backfilled() -> None:
    events = build_wngsr_feature_events(
        normalize_wngsr_history_table(_history()),
        normalize_wngsr_revisions_table(_revisions()),
        history_raw_sha256="a" * 64,
        revisions_raw_sha256="b" * 64,
    )

    sep26 = events.loc[events["available_at"].eq(pd.Timestamp("2024-09-26T14:30Z"))].iloc[0]
    oct03 = events.loc[events["available_at"].eq(pd.Timestamp("2024-10-03T14:30Z"))].iloc[0]
    nov18 = events.loc[events["available_at"].eq(pd.Timestamp("2024-11-18T20:00Z"))].iloc[0]

    assert sep26["storage_lower48_bcf"] == 290.0
    assert oct03["storage_lower48_bcf"] == 305.0
    assert oct03["storage_weekly_change_bcf"] == 15.0
    assert nov18["storage_lower48_bcf"] == 305.0
    assert nov18["storage_weekly_change_bcf"] == 5.0
    assert nov18["source_event_type"] == "revision"
    assert nov18["revision_target_count"] == 1
    assert nov18["revision_targets"] == "2024-09-20"
    assert events["revision_status"].eq("point_in_time").all()


def test_wngsr_sample_reselection_uses_exact_november_18_publication_time() -> None:
    revisions = normalize_wngsr_revisions_table(_revisions())
    events = build_wngsr_feature_events(
        normalize_wngsr_history_table(_history()),
        revisions,
        history_raw_sha256="a" * 64,
        revisions_raw_sha256="b" * 64,
    )
    revision = events.loc[events["source_event_type"].eq("revision")].iloc[0]
    assert revision["available_at"] == pd.Timestamp("2024-11-18T20:00:00Z")
    assert revision["availability_basis"] == "wngsr_2024_sample_reselection"


def test_wngsr_client_owns_official_history_and_revision_urls() -> None:
    class Response:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            pass

    class Session:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, timeout: int) -> Response:
            assert timeout == 60
            self.urls.append(url)
            return Response(b"history" if url.endswith("ngshistory.xls") else b"revisions")

    session = Session()
    history, revisions, urls = WngsrEvidenceClient(session=session).fetch_bundle()
    assert history == b"history"
    assert revisions == b"revisions"
    assert urls["history_url"].endswith("/ngshistory.xls")
    assert urls["revisions_url"].endswith("/revisions.xls")
    assert session.urls == [urls["history_url"], urls["revisions_url"]]


def test_wngsr_capture_is_resumable_and_loadable(tmp_path: Path, monkeypatch) -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = 0

        def fetch_bundle(self) -> tuple[bytes, bytes, dict[str, str]]:
            self.calls += 1
            return b"history-xls", b"revisions-xls", {
                "history_url": "https://ir.eia.gov/ngs/ngshistory.xls",
                "revisions_url": "https://ir.eia.gov/ngs/revisions.xls",
            }

    monkeypatch.setattr(
        "commodity.wngsr.parse_wngsr_workbooks",
        lambda history, revisions: (
            normalize_wngsr_history_table(_history()),
            normalize_wngsr_revisions_table(_revisions()),
        ),
    )
    client = Client()
    manifest = capture_wngsr_v1_window(
        client, "2024-09-27", "2024-11-20", tmp_path, "2026-08-14T02:00:00Z"
    )
    second = capture_wngsr_v1_window(
        client, "2024-09-27", "2024-11-20", tmp_path, "2026-08-14T03:00:00Z"
    )
    assert manifest == second
    assert client.calls == 1

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_id"] == "eia_wngsr_vintage_reconstruction"
    assert payload["point_in_time_backtest_ready"] is True
    assert {item["path"] for item in payload["artifacts"]} == {
        "ngshistory.xls",
        "revisions.xls",
        "storage_feature_events.csv",
    }

    frame = load_wngsr_v1_window(tmp_path, "2024-09-27", "2024-11-20")
    assert not frame.empty
    assert frame["source_id"].eq("eia_wngsr_vintage_reconstruction").all()
    assert frame["history_raw_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert frame["revisions_raw_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()



def test_wngsr_workbook_parser_promotes_semantic_header_rows(monkeypatch) -> None:
    history_sheet = pd.DataFrame(
        [
            ["Weekly Natural Gas Storage Report", None],
            ["Week ending", "Lower 48 States (Bcf)"],
            ["2024-09-20", 300.0],
        ]
    )
    revisions_sheet = pd.DataFrame(
        [
            ["Published revisions", None, None, None],
            ["Week ending date", "Original Estimate (Bcf)", "Revision Date"],
            ["2024-09-20", 290.0, "2024-11-18"],
        ]
    )

    def fake_read_excel(content: io.BytesIO, **kwargs):
        assert kwargs["engine"] == "xlrd"
        return {"Sheet1": history_sheet if content.getvalue() == b"history" else revisions_sheet}

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    history, revisions = parse_wngsr_workbooks(b"history", b"revisions")
    assert history.iloc[0]["storage_lower48_bcf"] == 300.0
    assert revisions.iloc[0]["original_storage_lower48_bcf"] == 290.0


def test_wngsr_revision_chain_infers_each_revised_value_from_source_history() -> None:
    history = normalize_wngsr_history_table(
        pd.DataFrame({"Week ending": ["2025-01-03"], "Lower 48 States": [310.0]})
    )
    revisions = normalize_wngsr_revisions_table(
        pd.DataFrame(
            {
                "Week ending": ["2025-01-03", "2025-01-03"],
                "Original Estimate": [290.0, 300.0],
                "Revision Date": ["2025-01-20", "2025-02-03"],
            }
        )
    )
    events = build_wngsr_feature_events(
        history,
        revisions,
        history_raw_sha256="a" * 64,
        revisions_raw_sha256="b" * 64,
    )
    revision_values = list(
        events.loc[events["source_event_type"].eq("revision"), "storage_lower48_bcf"]
    )
    assert revision_values == [300.0, 310.0]
