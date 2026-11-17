"""在本包目录执行：``python -m cli``。"""
from .interpolation_grid_station_cli import interpolation_grid_station_cli


def main(argv=None):
    return interpolation_grid_station_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
