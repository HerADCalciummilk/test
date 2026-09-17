"""命令行入口：读取 u、v 网格文件，输出风速与风向。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import netCDF4
import meteva_base as meb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wind_composite import ComputeWindDirection, ComputeWindSpeed  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="风速风向合成")
    parser.add_argument("--u", required=True, help="u 分量 nc 文件路径")
    parser.add_argument("--v", required=True, help="v 分量 nc 文件路径")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--member", default="ec", help="模式成员名")
    return parser


def read_uv(u_path: str, v_path: str, member: str):
    """读取 u、v 两个分量的网格数据。"""
    u_grid = meb.read_griddata_from_nc(u_path, data_name=member)
    v_grid = meb.read_griddata_from_nc(v_path, data_name=member)
    if u_grid is None or v_grid is None:
        raise SystemExit("读取 u/v 网格失败，请检查文件路径与变量名")
    return u_grid, v_grid
 

def main(argv: list[str] | None = None) -> int:
    """读取数据、执行两个插件、写出结果。"""
    args = build_parser().parse_args(argv)
    print(f"netCDF4 版本: {netCDF4.__version__}")

    u_grid, v_grid = read_uv(args.u, args.v, args.member)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ## 风速与风向分别由两个插件计算
    speed = ComputeWindSpeed().process(u_grid, v_grid)
    direction = ComputeWindDirection().process(u_grid, v_grid)

    ## 输出文件名按诊断量命名
    speed.to_netcdf(out_dir / "wind_speed.nc")
    direction.to_netcdf(out_dir / "wind_direction.nc")

    print(f"风速范围: {float(np.nanmin(speed)):.2f} ~ {float(np.nanmax(speed)):.2f} m/s")  ## 概览
    print(f"结果已写入: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
