#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""把地形增强场叠加或扣除到降水预报上的 CLI。

降水预报须已经在地形增强场同一张网格上。本入口不做重采样。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr
import meteva_base as meb


def process(
    precip_path: str,
    orographic_enhancement_path: str,
    output_path: Optional[str] = None,
    *,
    operation: str = "add",
    allowed_time_diff: int = 1800,
) -> xr.DataArray:
    """对降水预报叠加或扣除地形增强。

    参数
    ----------
    precip_path : str
        降水预报 nc 文件路径。网格须与地形增强场一致。
    orographic_enhancement_path : str
        地形增强场 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    operation : str, default="add"
        ``add`` 为叠加，``subtract`` 为扣除。
    allowed_time_diff : int, default=1800
        多时次增强场与降水时次匹配的容差，单位秒。

    返回
    -------
    xr.DataArray
        订正后的降水场。
    """
    from orographic_precipitation_downscaling.src.apply_orographic_enhancement import (
        ApplyOrographicEnhancement,
    )

    _unbounded = (-np.inf, np.inf, np.nan)
    precip = meb.checkout_griddata(
        meb.read_griddata_from_nc(precip_path), valid_val=_unbounded
    )
    orographic_enhancement = meb.checkout_griddata(
        meb.read_griddata_from_nc(orographic_enhancement_path), valid_val=_unbounded
    )

    result = ApplyOrographicEnhancement(operation)(
        precip,
        orographic_enhancement,
        allowed_time_diff=allowed_time_diff,
    )

    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "precipitation"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")

    return result


if __name__ == "__main__":
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    resource = Path(__file__).resolve().parents[1] / "resource"
    init_s = "2026083100"
    lead = "003"
    stamp = f"{init_s}.{lead}"
    day_dir = Path(init_s[:4]) / init_s[:8]

    precip_path = str(
        resource / "EC" / "APCP01" / day_dir / "NC" / f"{stamp}.nc"
    )
    orographic_enhancement_path = str(
        resource / "data" / "orographic_enhancement" / day_dir / f"{stamp}.nc"
    )
    output_path = str(
        resource / "data" / "APCP_corrected" / day_dir / f"{stamp}.nc"
    )

    result = process(
        precip_path,
        orographic_enhancement_path,
        output_path=output_path,
        operation="add",
        allowed_time_diff=1800,
    )
