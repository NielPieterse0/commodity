from __future__ import annotations

import os


def pytest_runtest_logreport(report) -> None:
    if not report.failed or not os.environ.get("GITHUB_ACTIONS"):
        return
    message = str(report.longrepr).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title=pytest {report.nodeid}::{message[:12000]}")
