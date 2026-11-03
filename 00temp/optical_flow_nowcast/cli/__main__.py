"""List the command modules. Run one module from this package directory."""

_COMMANDS = (
    "python -m cli.lk_plugin_cli --precip obs1.nc,obs2.nc",
    "python cli/lk_plugin_cli.py --precip obs1.nc,obs2.nc",
    "python -m cli.extrapolation_plugin_cli --precip obs.nc --velocity uv.nc --timesteps 6",
    "python cli/extrapolation_plugin_cli.py --precip obs.nc --velocity uv.nc --timesteps 6",
    "python -m cli.sprog_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6",
    "python cli/sprog_plugin_cli.py --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6",
    "python -m cli.linda_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6",
    "python cli/linda_plugin_cli.py --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6",
    "python -m cli.steps_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6",
    "python cli/steps_plugin_cli.py --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6",
)


def main() -> int:
    print("\n".join(_COMMANDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
