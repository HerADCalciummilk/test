"""List the command module. Run it from this package directory."""

_COMMANDS = (
    "python -m cli.weight_blending_cli --weight-power -2",
    "python cli/weight_blending_cli.py --weight-power -2",
)


def main() -> int:
    print("\n".join(_COMMANDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
