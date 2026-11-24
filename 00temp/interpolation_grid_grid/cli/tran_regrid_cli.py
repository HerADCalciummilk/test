# -*- coding: utf-8 -*-
"""海陆感知重网格。

``regrid_mode`` 仍是原来的选择（bilinear / nearest / nearest-with-mask 等）。
本命令没有自己的 ini 节，省略的项用函数预设。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    parent = root.parent
    for path in (str(parent), str(root / "src"), str(root)):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


_bootstrap_paths()

import meteva_base as meb

from utils.merge_params import merge_params


@merge_params()
def process(
    input_path: str = None,
    target_grid_path: str = None,
    land_sea_mask_path: Optional[str] = None,
    output_path: Optional[str] = None,
    regrid_mode: str = "bilinear",
    extrapolation_mode: str = "nan",
    land_sea_mask_vicinity: float = 25000.0,
    regridded_title: Optional[str] = None,
    config=None,
) -> xr.DataArray:
    """将源场重网格到目标网格，可选海陆感知。

    考虑海陆掩码时，地表类型不匹配的源点不参与目标点插值。
    ``config`` 只占位：本命令不另读 ini。
    """
    from interp_gg_landsea_plugin import InterpGgLandSea

    _ = config
    if not input_path or not target_grid_path:
        raise ValueError("缺少 input_path 或 target_grid_path")

    _unbounded = (-np.inf, np.inf, np.nan)
    # 读源场与目标网格
    input_field = meb.checkout_griddata(
        meb.read_griddata_from_nc(input_path), valid_val=_unbounded
    )
    target_grid = meb.checkout_griddata(
        meb.read_griddata_from_nc(target_grid_path), valid_val=_unbounded
    )

    land_sea_mask = None
    if land_sea_mask_path is not None:
        if regrid_mode not in (
            "nearest-with-mask",
            "nearest-with-mask-2",
            "bilinear-with-mask-2",
        ):
            raise ValueError(
                "Land-mask file supplied without appropriate regrid-mode. "
                "Use regrid_mode=nearest-with-mask."
            )
        land_sea_mask = meb.checkout_griddata(
            meb.read_griddata_from_nc(land_sea_mask_path), valid_val=_unbounded
        )

    # 海陆插件沿用可调用入口，以便保留 PostProcessingPlugin 的标题后处理
    result = InterpGgLandSea(
        regrid_mode=regrid_mode,
        extrapolation_mode=extrapolation_mode,
        landmask=land_sea_mask,
        landmask_vicinity=land_sea_mask_vicinity,
    )(input_field, target_grid, regridded_title=regridded_title)

    if output_path is not None:
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)
    return result
