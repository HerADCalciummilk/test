"""在本包目录执行：``python -m cli``。"""
from .grid_grid_fusion_cli import grid_grid_fusion_cli


def main(argv=None):
    return grid_grid_fusion_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
