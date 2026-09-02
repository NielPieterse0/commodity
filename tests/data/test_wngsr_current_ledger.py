from __future__ import annotations

import pandas as pd

from commodity import wngsr


def test_current_original_data_ledger_is_pit_safe(monkeypatch) -> None:
    history_sheet = pd.DataFrame(
        {
            "Week ending": ["2024-09-20", "2025-01-03"],
            "Lower 48 States": [300.0, 310.0],
        }
    )
    revisions_sheet = pd.DataFrame(
        {
            "Week ending": ["2024-09-20", "2025-01-03"],
            "Source": ["EIA-912", "EIA-912"],
            "Total Lower 48": [290.0, 300.0],
            "Explanation": ["sample reselection", None],
        }
    )

    monkeypatch.setattr(
        wngsr,
        "_read_xls_candidates",
        lambda content: [history_sheet] if content == b"history" else [revisions_sheet],
    )
    history, revisions = wngsr.parse_wngsr_workbooks(
        b"history",
        b"revisions",
        retrieved_at="2026-08-14T12:00:00Z",
    )

    assert list(revisions["original_storage_lower48_bcf"]) == [290.0, 300.0]
    assert list(revisions["revised_storage_lower48_bcf"]) == [300.0, 310.0]
    assert revisions["revision_date_basis"].eq("snapshot_retrieval_date").all()

    events = wngsr.build_wngsr_feature_events(
        history,
        revisions,
        history_raw_sha256="a" * 64,
        revisions_raw_sha256="b" * 64,
    )
    special = events.loc[
        events["availability_basis"].eq("wngsr_2024_sample_reselection")
    ].iloc[0]
    fallback = events.loc[
        events["availability_basis"].eq(
            "wngsr_revision_snapshot_retrieval_end_of_day"
        )
    ].iloc[0]

    assert special["available_at"] == pd.Timestamp("2024-11-18T20:00:00Z")
    assert fallback["available_at"] == pd.Timestamp("2026-08-15T03:59:00Z")
