"""命令行：python -m time_lagging。"""

from __future__ import annotations

import argparse
from pathlib import Path

from time_lagging.src.time_lagging import time_lag
from time_lagging.util.meteva_data import load_meteva, save_meteva

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TESTDATA = PACKAGE_ROOT / "testdata"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m time_lagging",
        description="合并不同起报时次、同一有效时间的集合预报，生成时间滞后集合。",
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=[str(TESTDATA / "cycle_00.nc"), str(TESTDATA / "cycle_06.nc")],
        help="两个或更多格点 nc，或两个或更多站点 csv",
    )
    parser.add_argument("--output", default=None, help="输出路径。缺省时按输入类型自动命名")
    args = parser.parse_args(argv)
    datasets = [load_meteva(path) for path in args.inputs]
    result = time_lag(datasets)
    output = Path(args.output) if args.output else _default_output(args.inputs[0])
    save_meteva(result, output)
    print(f"已写出时间滞后集合 {output}")


def _default_output(path: str) -> Path:
    suffix = Path(path).suffix.lower()
    if suffix in {".nc", ".nc4"}:
        return Path("time_lagging_ensemble.nc")
    return Path("time_lagging_ensemble.csv")


if __name__ == "__main__":
    main()
