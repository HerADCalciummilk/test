#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""按掩码分层迭代的邻域处理命令行。

在本包目录执行::

    python cli/ens_nbhood_iterate_with_mask.py --input-data-path PATH --mask-path PATH --coord-for-masking level --radii 10000
    python -m cli.ens_nbhood_iterate_with_mask --input-data-path PATH --mask-path PATH --coord-for-masking level --radii 10000

Python::

    from cli.ens_nbhood_iterate_with_mask import EnsNbhoodIterateWithMaskCli
    EnsNbhoodIterateWithMaskCli.call(input_data_path="PATH", mask_path="PATH", coord_for_masking="level", radii=[10000])
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import xarray as xr
import meteva_base as meb


def _bootstrap_paths() -> None:
    """沿用原脚本：把 00temp 放进 sys.path，并让包根上的 utils 优先。"""
    root = Path(__file__).resolve().parent.parent
    temp_root = root.parent
    temp_s = str(temp_root)
    if temp_s not in sys.path:
        sys.path.insert(0, temp_s)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.merge_params import merge_params
from utils.conf_ini import overlay_none


def _as_number_list(value, kind):
    """命令行逗号串或单个数收成列表；已是序列则逐项转换。"""
    if value is None:
        return None
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",") if item.strip()]
        return [kind(item) for item in parts]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [kind(value)]
    return [kind(item) for item in value]


def _read_band_field(path: str) -> xr.DataArray:
    """读取地形带 mask/weights：优先 meb 六维，失败则退回 xarray。"""
    try:
        return meb.read_griddata_from_nc(path)
    except Exception:
        return xr.open_dataarray(path, decode_timedelta=False)


@merge_params()
def process(
    input_data_path: str,
    mask_path: str,
    coord_for_masking: str,
    radii: Sequence[float],
    weights_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    neighbourhood_shape: str = "square",
    lead_times: Optional[Sequence[int]] = None,
    area_sum: bool = False, config=None) -> xr.DataArray:
    """执行“按掩码层迭代”的邻域处理。

    参数
    ----------
    input_data_path : str
        待处理输入场 nc 文件路径。
    mask_path : str
        掩码分层数据 nc 文件路径，需包含 ``coord_for_masking`` 维。
        推荐为 Generate* 六维 meb（带维 ``level``）。
    coord_for_masking : str
        掩码分层维名称；与 generate_ancillary 对齐时为 ``level``。
    radii : sequence of float
        邻域半径（米），可单值或多值。
    weights_path : str, optional
        掩码维折叠权重 nc 文件路径（同样推荐六维 meb）。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    neighbourhood_shape : str, default="square"
        邻域形状，``square`` / ``circular``。
    lead_times : sequence of int, optional
        与 ``radii`` 对应的时效（小时）。
    area_sum : bool, default=False
        是否输出邻域和（True）而非邻域平均（False）。

    返回
    -------
    xr.DataArray
        邻域处理结果。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "weights_path": (weights_path, "str"),
        "output_path": (output_path, "str"),
        "lead_times": (lead_times, "int_list"),
    })
    weights_path = _over['weights_path']
    output_path = _over['output_path']
    lead_times = _over['lead_times']
    from neighbourhood_probability_processing.src.utils._helpers import radius_by_lead_time
    from neighbourhood_probability_processing.src.use_nbhood import ApplyNeighbourhoodProcessingWithAMask

    input_data = meb.checkout_griddata(
        meb.read_griddata_from_nc(input_data_path),
        valid_val=(-np.inf, np.inf, np.nan),
    )
    mask = _read_band_field(mask_path)
    if coord_for_masking not in mask.dims:
        raise ValueError(f"mask 中缺少分层维 {coord_for_masking}")
    weights = None if weights_path is None else _read_band_field(weights_path)

    radii = _as_number_list(radii, float)
    if lead_times is not None:
        lead_times = _as_number_list(lead_times, int)
    radius_or_radii, parsed_lead_times = radius_by_lead_time(list(radii), lead_times)
    result = ApplyNeighbourhoodProcessingWithAMask(
        coord_for_masking=coord_for_masking,
        neighbourhood_method=neighbourhood_shape,
        radii=radius_or_radii,
        lead_times=parsed_lead_times,
        collapse_weights=weights,
        sum_only=area_sum,
    ).process(input_data, mask)

    result = result.astype(np.float32, copy=False)
    if output_path is not None:
        # meb.write_griddata_to_nc 会把 NaN 量化成 int32 哨兵，改用 xarray 直写。
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "neighbourhood_result"
        if result.name is None:
            result = result.copy()
            result.name = var_name
        tmp = output_file.with_suffix(output_file.suffix + ".tmp")
        if tmp.exists():
            tmp.unlink()
        result.to_dataset(name=var_name).to_netcdf(
            tmp,
            mode="w",
            encoding={var_name: {"dtype": "float32", "_FillValue": None}},
        )
        try:
            tmp.replace(output_file)
        except PermissionError:
            fallback = output_file.with_name(
                f"{output_file.stem}_new{output_file.suffix}"
            )
            if fallback.exists():
                fallback.unlink()
            tmp.replace(fallback)
    return result
