"""在本包目录执行：``python -m cli``。"""
from .interpolation_station_grid_cli import interpolation_station_grid_cli


def main(argv=None):
    return interpolation_station_grid_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
