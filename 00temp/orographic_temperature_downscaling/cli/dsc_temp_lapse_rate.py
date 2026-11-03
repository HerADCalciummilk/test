#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""计算层结递减率的 CLI 示例。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr
import meteva_base as meb

DALR = -0.0098  # # 干绝热递减率


def _as_lapse_rate_dataarray(
    values: np.ndarray,
    template: xr.DataArray,
    name: str = "air_temperature_lapse_rate",
    units: str = "K m-1",
) -> xr.DataArray:
    """用模板网格将结果数组封装为 DataArray。"""
    result = xr.DataArray(
        values.astype(np.float32, copy=False),
        dims=template.dims,
        coords=template.coords,
        attrs=dict(template.attrs),
        name=name,
    )
    result.attrs["units"] = units
    return result


def process(
    temperature_path: str,
    orography_path: Optional[str] = None,
    land_sea_mask_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    max_height_diff: float = 35.0,
    nbhood_radius: int = 7,
    max_lapse_rate: float = -3 * DALR,
    min_lapse_rate: float = DALR,
    dry_adiabatic: bool = False,
) -> xr.DataArray:
    """计算温度层结递减率（K m-1）。

    参数
    ----------
    temperature_path : str
        气温输入场 nc 文件路径。
    orography_path : str, optional
        地形高度场 nc 文件路径，单位通常为 m。
    land_sea_mask_path : str, optional
        海陆掩码 nc 文件路径，陆地为真值，海洋为假值。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    max_height_diff : float, default=35.0
        计算邻域回归时允许的最大高度差（m）。
    nbhood_radius : int, default=7
        邻域半径（格点数）。
    max_lapse_rate : float, default=-3*DALR
        层结递减率上限（K m-1）。
    min_lapse_rate : float, default=DALR
        层结递减率下限（K m-1）。
    dry_adiabatic : bool, default=False
        若为真，直接返回干绝热递减率场，不执行真实递减率估计。

    返回
    -------
    xr.DataArray
        层结递减率场，单位 ``K m-1``。
    """
    from orographic_temperature_downscaling.src.lapse_rate import LapseRate
        
    _unbounded = (-np.inf, np.inf, np.nan)

    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_unbounded
    )

    if dry_adiabatic:
        result = np.full_like(
            np.asarray(temperature.values, dtype=np.float32), DALR, dtype=np.float32
        )
        result = _as_lapse_rate_dataarray(result, temperature)
    else:
        if min_lapse_rate > max_lapse_rate:
            raise ValueError("最小层结递减率不能大于最大层结递减率。")
        if max_height_diff < 0:
            raise ValueError("max_height_diff 必须大于等于 0。")
        if nbhood_radius < 0:
            raise ValueError("nbhood_radius 必须大于等于 0。")

        if orography_path is None or land_sea_mask_path is None:
            raise RuntimeError("计算真实层结递减率时，必须同时提供 orography_path 和 land_sea_mask_path。")

        orography = meb.checkout_griddata(
            meb.read_griddata_from_nc(orography_path), valid_val=_unbounded
        )
        land_sea_mask = meb.checkout_griddata(meb.read_griddata_from_nc(land_sea_mask_path))

        if not meb.checkout_griddata_same_coords([temperature, orography], is_time_match=False):
            raise ValueError("地形高度场与温度场的坐标不一致")
        # 海陆掩码为静态场，只校验空间坐标（不要求 time/dtime 与气温一致）
        if not meb.checkout_griddata_same_coords([temperature, land_sea_mask], is_time_match=False):
            raise ValueError("海陆掩码与温度场的空间坐标不一致")

        plugin = LapseRate(
            max_height_diff=max_height_diff,
            nbhood_radius=nbhood_radius,
            max_lapse_rate=max_lapse_rate,
            min_lapse_rate=min_lapse_rate,
        )
        result = plugin(temperature, orography, land_sea_mask)
        if isinstance(result, xr.DataArray):
            result = result.copy()
            result.name = "air_temperature_lapse_rate"
            result.attrs["units"] = "K m-1"
        else:
            result = _as_lapse_rate_dataarray(result, temperature)

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
        str(input_dir / "temperature_at_screen_level.nc"),
        orography_path=str(input_dir / "ukvx_orography.nc"),
        land_sea_mask_path=str(input_dir / "ukvx_landmask.nc"),
        output_path=str(output_dir / "cli_lapse_rate_result.nc"),
    )


if __name__ == "__main__":
    main()
