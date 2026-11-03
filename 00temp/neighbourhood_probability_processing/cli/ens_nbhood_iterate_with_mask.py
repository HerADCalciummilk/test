#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""按掩码分层迭代的邻域处理 CLI 示例。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
import xarray as xr
import meteva_base as meb


def _read_band_field(path: str) -> xr.DataArray:
    """读取地形带 mask/weights：优先 meb 六维，失败则退回 xarray。"""
    try:
        return meb.read_griddata_from_nc(path)
    except Exception:
        return xr.open_dataarray(path, decode_timedelta=False)


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
    area_sum: bool = False,
) -> xr.DataArray:
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


if __name__ == "__main__":
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    scenario_dir = (
        Path(__file__).resolve().parent.parent
        / "test_data"
        / "official_test_use_nbhood"
        / "iterate_with_mask"
    )
    input_dir = scenario_dir / "cli_input"
    output_dir = scenario_dir / "cli_output"

    input_data_path = input_dir / "thresholded_input.nc"
    mask_path = str(input_dir / "orographic_bands_mask.nc")
    weights_path = str(input_dir / "orographic_bands_weights.nc")
    output_path = str(output_dir / "cli_iterated_result.nc")

    # 与 GenerateOrographyBandAncils / GenerateTopographicZoneWeights 一致
    coord_for_masking = "level"
    neighbourhood_shape = "square"
    radii: List[float] = [10000.0]
    lead_times = None
    area_sum = False

    if not input_data_path.is_file():
        print(
            f"示例输入不存在：{input_data_path}\n"
            "请补充 test_data 后重试，或在此处配置自己的输入与输出路径。"
        )
    else:
        process(
            str(input_data_path),
            mask_path,
            coord_for_masking,
            radii,
            weights_path=weights_path,
            output_path=output_path,
            neighbourhood_shape=neighbourhood_shape,
            lead_times=lead_times,
            area_sum=area_sum,
        )
