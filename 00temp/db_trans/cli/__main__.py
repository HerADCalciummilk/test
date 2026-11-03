"""List the command module. Run it from this package directory."""

_COMMANDS = (
    "python -m cli.dB_trans_cli --method db --values 0,0.05,0.1,1,10,100",
    "python cli/dB_trans_cli.py --method db --values 0,0.05,0.1,1,10,100",
)


def main() -> int:
    print("\n".join(_COMMANDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
