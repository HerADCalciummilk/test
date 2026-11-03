"""Command line entry points for linear_scd_multi_time_fusion."""

from __future__ import annotations


def main() -> None:
    """List available SCD commands."""
    raise SystemExit(
        "\n".join(
            [
                "linear_scd_multi_time_fusion 命令行入口：",
                "  python -m linear_scd_multi_time_fusion.cli.split_qpf [START_UTC END_UTC]",
                "  python -m linear_scd_multi_time_fusion.cli.run_scd_fusion [START_UTC END_UTC]",
                "  python -m linear_scd_multi_time_fusion.cli.pad_fusion_output [START_UTC END_UTC]",
            ]
        )
    )
