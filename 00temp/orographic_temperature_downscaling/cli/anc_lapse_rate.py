#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""应用层结递减率进行温度地形订正的 CLI 示例。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np
import xarray as xr
import meteva_base as meb

def process(
    temperature_path: str,
    lapse_rate_path: str,
    source_orography_path: str,
    target_orography_path: str,
    output_path: Optional[str] = None,
) -> Union[xr.DataArray, np.ndarray]:
    """将已计算的层结递减率应用到温度场。

    参数
    ----------
    temperature_path : str
        输入温度场 nc 文件路径。
    lapse_rate_path : str
        层结递减率场 nc 文件路径，单位通常为 ``K m-1``。
    source_orography_path : str
        温度原始网格对应的源地形高度场 nc 文件路径。
    target_orography_path : str
        目标地形高度场 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件，仅返回结果。

    返回
    -------
    xr.DataArray or np.ndarray
        地形订正后的温度场。
    """
    from orographic_temperature_downscaling.src.lapse_rate import ApplyGriddedLapseRate
        
    _unbounded = (-np.inf, np.inf, np.nan)

    temperature = meb.read_griddata_from_nc(temperature_path)
    lapse_rate = meb.read_griddata_from_nc(lapse_rate_path)
    source_orography = meb.read_griddata_from_nc(source_orography_path)
    target_orography = meb.read_griddata_from_nc(target_orography_path)

    temperature = meb.checkout_griddata(temperature, valid_val=_unbounded)
    lapse_rate = meb.checkout_griddata(lapse_rate)
    source_orography = meb.checkout_griddata(source_orography, valid_val=_unbounded)
    target_orography = meb.checkout_griddata(target_orography, valid_val=_unbounded)

    if not meb.checkout_griddata_same_coords([temperature, lapse_rate], is_time_match=True):
        raise ValueError("层结递减率场与温度场的空间/时效坐标不一致")
    if not meb.checkout_griddata_same_coords([temperature, source_orography], is_time_match=False):
        raise ValueError("源地形高度场与温度场的坐标不一致")
    if not meb.checkout_griddata_same_coords([temperature, target_orography], is_time_match=False):
        raise ValueError("目标地形高度场与温度场的坐标不一致")

    result = ApplyGriddedLapseRate()(
        temperature,
        lapse_rate,
        source_orography,
        target_orography,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)

    return result


def main() -> None:
    """定义输入/输出路径并调用 ``process``（默认 ``resource/`` 样例）。"""
    import sys

    _PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    input_dir = _PACKAGE_ROOT / "resource" / "cli_input"
    output_dir = _PACKAGE_ROOT / "resource" / "cli_output"
    process(
        str(input_dir / "ukvx_temperature.nc"),
        str(input_dir / "ukvx_lapse_rate.nc"),
        str(input_dir / "anc_ukvx_orography.nc"),
        str(input_dir / "highres_orog.nc"),
        output_path=str(output_dir / "cli_apply_lapse_rate_result.nc"),
    )


if __name__ == "__main__":
    main()