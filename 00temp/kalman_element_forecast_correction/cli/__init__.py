"""Command line entry points for kalman_element_forecast_correction."""

from __future__ import annotations

from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> None:
    """List available CLI entry points."""
    lines = [
        "kalman_element_forecast_correction 命令行入口：",
        "  python -m kalman_element_forecast_correction.cli.kalman_data [START_YYYYMMDD END_YYYYMMDD]",
        "  python -m kalman_element_forecast_correction.cli.trans_data [YYYYMMDD]",
    ]
    raise SystemExit("\n".join(lines))
