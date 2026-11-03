"""Command line entry points for linear_scd_multi_time_fusion."""

from __future__ import annotations


_COMMANDS = (
    "linear_scd_multi_time_fusion 命令行入口：",
    "  python -m cli.split_qpf [--config PATH] [START_UTC END_UTC]",
    "  python cli/split_qpf.py [--config PATH] [START_UTC END_UTC]",
    "  python -m cli.run_scd_fusion [--config PATH] [START_UTC END_UTC]",
    "  python cli/run_scd_fusion.py [--config PATH] [START_UTC END_UTC]",
    "  python -m cli.pad_fusion_output [--config PATH] [START_UTC END_UTC]",
    "  python cli/pad_fusion_output.py [--config PATH] [START_UTC END_UTC]",
)


def main(argv=None) -> int:
    """List available SCD commands. Run from this package directory."""
    print("\n".join(_COMMANDS))
    return 0
