#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地方太阳时计算 CLI 示例。

约定（无 Improver ``cli`` 装饰器）::

    - ``process`` 接收文件路径，在函数内完成读入、计算与可选写出；
    - ``main`` 中定义路径等参数，再直接调用 ``process``。

包根目录执行::

    python -m cli solar-time
    python cli/cal_generate_solar_time.py
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
    new_title: Optional[str] = None,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """读取目标网格并计算地方太阳时。

    参数
    ----------
    target_grid_path :
        目标网格 meb 六维 nc（``member, level, time, dtime, lat, lon``）。
        投影输入须含 ``grid_mapping_attrs``；亦可使用预处理后的经纬 meb。
    time :
        计算时刻（``datetime``），用于推算地方太阳时。
    new_title :
        可选，写出前覆盖 ``attrs["title"]``。
    output_path :
        可选输出 nc 路径；为 ``None`` 时不写文件。

    返回
    -------
    xr.DataArray
        地方太阳时场（``local_solar_time``，单位 hours，范围 0–24）。
    """
    from generate_derived_solar_fields.src.generate_derived_solar_fields import GenerateSolarTime

    if not isinstance(time, datetime):
        raise TypeError("time 必须是 datetime。")

    target_grid = meb.read_griddata_from_nc(target_grid_path)
    result = GenerateSolarTime().process(
        target_grid=target_grid,
        time=time,
        new_title=new_title,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


def main() -> None:
    """定义输入/输出路径并调用 ``process``。

    默认复用 ``resource/cli_input/input_surface_altitude_meb.nc`` 作为目标网格
    （与 clearsky 示例共用同一份经纬 meb 样例）；业务使用时在此修改路径即可。
    """
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    input_dir = _PACKAGE_ROOT / "resource" / "cli_input"
    output_dir = _PACKAGE_ROOT / "resource" / "cli_output"

    # 仅需网格几何；与 clearsky 共用 surface_altitude 样例即可
    target_grid_path = str(input_dir / "input_surface_altitude_meb.nc")
    output_path = str(output_dir / "cal_solar_time_result.nc")

    process(
        target_grid_path=target_grid_path,
        time=datetime(2022, 6, 7, 0, 0),
        output_path=output_path,
    )


if __name__ == "__main__":
    main()
