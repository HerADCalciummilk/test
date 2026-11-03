"""Module entry point for nimm_g_interp CLI."""
from .orographic_nwp_3d_downscaling_cli import orographic_nwp_3d_downscaling_cli


def main(argv=None):
    return orographic_nwp_3d_downscaling_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
