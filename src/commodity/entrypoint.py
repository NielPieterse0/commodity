# ruff: noqa: I001
from __future__ import annotations

from commodity import research_methodology
from commodity.methodology_extensions import (
    compute_effective_information,
    freeze_with_registration,
)


research_methodology.compute_effective_information = compute_effective_information

from commodity import cli


cli._experiment_freeze = lambda args: freeze_with_registration(args, cli)


def main() -> None:
    cli.main()
