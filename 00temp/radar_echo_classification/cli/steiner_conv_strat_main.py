#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""Steiner 对流/层状分类 CLI 示例脚本。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import meteva_base as meb
import xarray as xr


def process(
    refl_path: str,
    *,
    dx: float = None,
    dy: float = None,
    intense: float = 42.0,
    work_level: float = 3000.0,
    peak_relation: str = "default",
    area_relation: str = "medium",
    bkg_rad: float = 11000.0,
    use_intense: bool = True,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """读取反射率网格，执行 Steiner 层状/对流分类，并可写出 NetCDF。

    参数
    ----
    refl_path : str
        输入反射率网格 NetCDF 文件路径。
    dx, dy : float, optional
        水平分辨率，单位米；为空时根据网格经纬度坐标估算。
    intense : float, optional
        强对流反射率阈值，单位 dBZ。
    work_level : float, optional
        分类工作高度，单位米；选择最接近该高度的层。
    peak_relation : str, optional
        峰值阈值关系，可选 ``default`` 或 ``sgp``。
    area_relation : str, optional
        对流影响半径关系，可选 ``small``、``medium``、``large`` 或 ``sgp``。
    bkg_rad : float, optional
        背景半径，单位米。当前底层 Steiner 实现固定使用 11000 m，
        该参数暂不改变实际计算，详见算法文档的已知限制。
    use_intense : bool, optional
        是否启用强回波快速判别。当前底层 Steiner 实现固定启用，
        该参数暂不改变实际计算。
    output_path : str, optional
        结果 NetCDF 输出路径；为空时仅返回内存结果。

    返回
    ----
    xr.DataArray
        单层分类网格：0=未定义，1=层状，2=对流。
    """
    from radar_echo_classification.src.echo_class import SteinerConvStratPlugin

    refl = meb.read_griddata_from_nc(refl_path)
    plugin = SteinerConvStratPlugin(
        dx=dx,
        dy=dy,
        intense=intense,
        work_level=work_level,
        peak_relation=peak_relation,
        area_relation=area_relation,
        bkg_rad=bkg_rad,
        use_intense=use_intense,
    )
    result = plugin(refl)
    if output_path is not None:
        from radar_echo_classification.cli import save_echo_class_grid_to_netcdf

        save_echo_class_grid_to_netcdf(result, output_path)
    return result


if __name__ == "__main__":
    import sys

    # 添加项目根目录到 Python 路径
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    data_dir = Path(__file__).resolve().parents[1] / "test_data" / "echo_class" / "cli_input"
    output_dir = Path(__file__).resolve().parents[1] / "test_data" / "echo_class" / "cli_output"

    process(
        str(data_dir / "ACHN_CREF000_20240612_070000_small.nc"),
        work_level=0.0,
        output_path=str(output_dir / "achn_steiner_cli.nc"),
    )
