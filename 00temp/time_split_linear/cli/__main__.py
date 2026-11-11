"""List the command modules. Run one module from this package directory."""

_COMMANDS = (
    "python -m cli.cal_griddata_TimeSplit_plugin_cli --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100",
    "python cli/cal_griddata_TimeSplit_plugin_cli.py --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100",
)


def main() -> int:
    print("\n".join(_COMMANDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
