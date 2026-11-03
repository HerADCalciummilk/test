"""在本包目录执行：``python -m cli``。"""
from .coordinate_projection_transform_cli import coordinate_projection_transform_cli


def main(argv=None):
    return coordinate_projection_transform_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
