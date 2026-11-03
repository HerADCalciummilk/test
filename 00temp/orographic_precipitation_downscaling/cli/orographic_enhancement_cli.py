#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""直接用 U/V 计算地形增强的 CLI。

输入须已是边界层代表高度上的单层场。温度、湿度、气压、U、V
由 ``OrographicEnhancement`` 重采样到传入的地形网格。
本入口不解析风速风向，也不做风矢量旋转。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr
import meteva_base as meb


def process(
    temperature_path: str,
    humidity_path: str,
    pressure_path: str,
    uwind_path: str,
    vwind_path: str,
    orography_path: str,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """用已有 U/V 计算地形增强。

    参数
    ----------
    temperature_path : str
        温度输入场 nc 文件路径。
    humidity_path : str
        相对湿度输入场 nc 文件路径。
    pressure_path : str
        气压输入场 nc 文件路径。
    uwind_path : str
        东西风分量 nc 文件路径。
    vwind_path : str
        南北风分量 nc 文件路径。
    orography_path : str
        目标地形网格场 nc 文件路径。增强场落在这张网格上。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。

    返回
    -------
    xr.DataArray
        地形增强结果，单位 ``m s-1``。
    """
    from orographic_precipitation_downscaling.src.orographic_enhancement import (
        OrographicEnhancement,
    )

    _unbounded = (-np.inf, np.inf, np.nan)

    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_unbounded
    )
    humidity = meb.checkout_griddata(
        meb.read_griddata_from_nc(humidity_path), valid_val=_unbounded
    )
    pressure = meb.checkout_griddata(
        meb.read_griddata_from_nc(pressure_path), valid_val=_unbounded
    )
    uwind = meb.checkout_griddata(
        meb.read_griddata_from_nc(uwind_path), valid_val=_unbounded
    )
    vwind = meb.checkout_griddata(
        meb.read_griddata_from_nc(vwind_path), valid_val=_unbounded
    )
    orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(orography_path),
        is_single=True,
        valid_val=_unbounded,
    )

    for label, field in (
        ("相对湿度场", humidity),
        ("气压场", pressure),
        ("东西风场", uwind),
        ("南北风场", vwind),
    ):
        if not meb.checkout_griddata_same_coords([temperature, field], is_time_match=True):
            raise ValueError(f"{label}与温度场的空间/时效坐标不一致")

    result = OrographicEnhancement()(
        temperature,
        humidity,
        pressure,
        uwind,
        vwind,
        orography,
    )

    if output_path is not None:
        # meb.write_griddata_to_nc 对 ~1e-6 m/s 量级结果会量化成 0，改用 xarray 直写。
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "orographic_enhancement"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")

    return result


if __name__ == "__main__":
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    resource = Path(__file__).resolve().parents[1] / "resource"
    init_s = "2026083100"
    lead = "000"
    data_dir = resource / "data"
    stamp = f"{init_s}.{lead}"
    day_dir = Path(init_s[:4]) / init_s[:8]

    temperature_path = str(data_dir / "TMP" / day_dir / f"{stamp}.nc")
    humidity_path = str(data_dir / "RH" / day_dir / f"{stamp}.nc")
    pressure_path = str(data_dir / "PRES" / day_dir / f"{stamp}.nc")
    uwind_path = str(data_dir / "UGRD" / day_dir / f"{stamp}.nc")
    vwind_path = str(data_dir / "VGRD" / day_dir / f"{stamp}.nc")
    orography_path = str(resource / "ancil" / "HGT_M_1KM_CHINA.nc")
    output_path = str(data_dir / "orographic_enhancement" / day_dir / f"{stamp}.nc")

    result = process(
        temperature_path,
        humidity_path,
        pressure_path,
        uwind_path,
        vwind_path,
        orography_path,
        output_path=output_path,
    )
