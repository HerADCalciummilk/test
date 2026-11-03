"""Command line entry points for steps_multi_time_fusion."""


def main() -> None:
    """List available commands."""
    raise SystemExit(
        "\n".join(
            [
                "steps_multi_time_fusion 命令行入口：",
                "  python -m steps_multi_time_fusion.cli.noise --help",
                "  python -m steps_multi_time_fusion.cli.climatological_skill --help",
                "  python -m steps_multi_time_fusion.cli.blending --help",
            ]
        )
    )
