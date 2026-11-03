"""在本包目录执行：``python -m cli``。"""
from .station_grid_fusion_cli import station_grid_fusion_cli


def main(argv=None):
    return station_grid_fusion_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
