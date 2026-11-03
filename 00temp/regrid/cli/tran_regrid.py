#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""海陆感知重网格 CLI 示例。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import meteva_base as meb
import numpy as np
import xarray as xr


def process(
    input_path: str,
    target_grid_path: str,
    land_sea_mask_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    regrid_mode: str = "bilinear",
    extrapolation_mode: str = "nanmask",
    land_sea_mask_vicinity: float = 25000.0,
    regridded_title: Optional[str] = None,
) -> xr.DataArray:
    """将源场重网格到目标网格，可选海陆感知。

    考虑海陆掩码时，地表类型不匹配的源点不参与目标点插值。例如在最近邻
    海陆感知模式下，重网格后的陆点总是取自源网格陆点，海点总是取自源网格
    海点。

    参数
    ----------
    input_path :
        源场 nc 路径。
    target_grid_path :
        目标网格 nc 路径；掩码模式下应为目标海陆掩码场。
    land_sea_mask_path :
        源网格海陆掩码 nc；``*-with-mask*`` 模式必需。
    output_path :
        输出 nc 路径；为 None 时不写文件。
    regrid_mode :
        插值模式，如 ``bilinear`` / ``nearest`` / ``nearest-with-mask`` /
        ``bilinear-2`` / ``nearest-2`` / ``*-with-mask-2``。
    extrapolation_mode :
        源域外填充方式：``extrapolate``、``error``，以及
        ``nan`` / ``mask`` / ``nanmask``（三者等效，均填 NaN；默认 ``nanmask``）。
    land_sea_mask_vicinity :
        海岸线搜索半径，单位米。
    regridded_title :
        输出 ``title`` 属性；未指定时由插件使用默认值。

    返回
    -------
    xr.DataArray
        重网格后的六维场。
    """
    from regrid.src.landsea import RegridLandSea
    
    _unbounded = (-np.inf, np.inf, np.nan)

    input_field = meb.checkout_griddata(
        meb.read_griddata_from_nc(input_path), valid_val=_unbounded
    )
    target_grid = meb.checkout_griddata(
        meb.read_griddata_from_nc(target_grid_path), valid_val=_unbounded
    )

    land_sea_mask = None
    if land_sea_mask_path is not None:
        # 与上游 improver/cli/regrid.py 一致：提供掩码文件时须匹配掩码模式
        if regrid_mode not in (
            "nearest-with-mask",
            "nearest-with-mask-2",
            "bilinear-with-mask-2",
        ):
            raise ValueError(
                "Land-mask file supplied without appropriate regrid-mode. "
                "Use --regrid-mode nearest-with-mask."
            )
        land_sea_mask = meb.checkout_griddata(
            meb.read_griddata_from_nc(land_sea_mask_path), valid_val=_unbounded
        )

    result = RegridLandSea(
        regrid_mode=regrid_mode,
        extrapolation_mode=extrapolation_mode,
        landmask=land_sea_mask,
        landmask_vicinity=land_sea_mask_vicinity,
    )(input_field, target_grid, regridded_title=regridded_title)

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
        str(input_dir / "global_cutout.nc"),
        str(input_dir / "ukvx_grid.nc"),
        land_sea_mask_path=None,
        output_path=str(output_dir / "cli_bilinear_result.nc"),
        regrid_mode="bilinear",
        extrapolation_mode="nanmask",
        land_sea_mask_vicinity=25000.0,
        regridded_title="Global Model Forecast on UK 2 km Standard Grid",
    )


if __name__ == "__main__":
    main()
