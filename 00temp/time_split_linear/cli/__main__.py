"""List the command modules. Run one module from this package directory."""

_COMMANDS = (
    "python -m cli.cal_griddata_TimeSplit_plugin_cli --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100",
    "python cli/cal_griddata_TimeSplit_plugin_cli.py --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100",
    "python -m cli.timesplit_hourtomin_plugin_cli --ntime 10",
    "python cli/timesplit_hourtomin_plugin_cli.py --ntime 10",
    "python -m cli.readdata_fromtime_plugin_cli --file-path <template> --file-time 2023070100,2023070101 --glon 70,140,0.05 --glat 0,60,0.05",
    "python cli/readdata_fromtime_plugin_cli.py --file-path <template> --file-time 2023070100,2023070101 --glon 70,140,0.05 --glat 0,60,0.05",
)


def main() -> int:
    print("\n".join(_COMMANDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
