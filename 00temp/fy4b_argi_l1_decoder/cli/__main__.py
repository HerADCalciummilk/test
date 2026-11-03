"""在本包目录执行：``python -m cli``。"""
from .fy4b_argi_l1_decoder_cli import fy4b_argi_l1_decoder_cli


def main(argv=None):
    return fy4b_argi_l1_decoder_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
