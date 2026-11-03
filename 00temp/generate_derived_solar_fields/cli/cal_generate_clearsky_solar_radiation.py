#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""晴空太阳辐射累计计算 CLI 示例。

约定（无 Improver ``cli`` 装饰器）::

    - ``process`` 接收文件路径，在函数内完成读入、计算与可选写出；
    - ``main`` 中定义路径等参数，再直接调用 ``process``。

包根目录执行::

    python -m cli clearsky
    python cli/cal_generate_clearsky_solar_radiation.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import meteva_base as meb
import xarray as xr

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def process(
    target_grid_path: str,
    time: datetime,
    accumulation_period: int,
    surface_altitude_path: Optional[str] = None,
    linke_turbidity_path: Optional[str] = None,
    temporal_spacing: int = 30,
    new_title: Optional[str] = None,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """读取输入并计算指定时段内的累计晴空太阳辐射。

    参数
    ----------
    target_grid_path :
        目标网格 meb 六维 nc；通常与 ``surface_altitude_path`` 同网。
    time :
        累积结束时刻（``datetime``）。
    accumulation_period :
        累积时长（小时），如 ``24`` 表示过去 24 小时积分。
    surface_altitude_path :
        可选，地表海拔 meb nc（米）；不传则插件内使用默认海拔场。
    linke_turbidity_path :
        可选，Linke 浑浊度 meb nc；不传则插件内使用默认浑浊度场。
    temporal_spacing :
        时间积分步长（分钟），默认 ``30``。
    new_title :
        可选，写出前覆盖 ``attrs["title"]``。
    output_path :
        可选输出 nc 路径；为 ``None`` 时不写文件。

    返回
    -------
    xr.DataArray
        累计晴空短波辐射（单位 ``W s m-2``），并附带时间窗与积分参数属性。
    """
    from generate_derived_solar_fields.src.generate_derived_solar_fields import (
        GenerateClearskySolarRadiation,
    )

    if not isinstance(time, datetime):
        raise TypeError("time 必须是 datetime。")

    target_grid = meb.read_griddata_from_nc(target_grid_path)
    surface_altitude = (
        meb.read_griddata_from_nc(surface_altitude_path)
        if surface_altitude_path is not None
        else None
    )
    linke_turbidity = (
        meb.read_griddata_from_nc(linke_turbidity_path)
        if linke_turbidity_path is not None
        else None
    )

    result = GenerateClearskySolarRadiation().process(
        target_grid=target_grid,
        time=time,
        accumulation_period=accumulation_period,
        surface_altitude=surface_altitude,
        linke_turbidity=linke_turbidity,
        temporal_spacing=temporal_spacing,
        new_title=new_title,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


def main() -> None:
    """定义输入/输出路径并调用 ``process``。

    默认使用 ``resource/cli_input`` 下经纬 meb 六维样例；业务使用时在此修改路径即可。
    """
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    input_dir = _PACKAGE_ROOT / "resource" / "cli_input"
    output_dir = _PACKAGE_ROOT / "resource" / "cli_output"

    surface_altitude_path = str(input_dir / "input_surface_altitude_meb.nc")
    target_grid_path = surface_altitude_path
    linke_turbidity_path = str(input_dir / "input_linke_turbidity_meb.nc")
    output_path = str(output_dir / "cal_clearsky_solar_radiation_result.nc")

    process(
        target_grid_path=target_grid_path,
        time=datetime(2022, 5, 6, 0, 0),
        accumulation_period=24,
        surface_altitude_path=surface_altitude_path,
        linke_turbidity_path=linke_turbidity_path,
        output_path=output_path,
    )


if __name__ == "__main__":
    main()
