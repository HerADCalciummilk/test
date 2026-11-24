#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""邻域概率处理命令行。

在本包目录执行::

    python cli/ens_nbhood.py --input-data-path PATH --neighbourhood-output probabilities --radii 20000
    python -m cli.ens_nbhood --input-data-path PATH --neighbourhood-output probabilities --radii 20000

Python::

    from cli.ens_nbhood import EnsNbhoodCli
    EnsNbhoodCli.call(input_data_path="PATH", neighbourhood_output="probabilities", radii=[20000])
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


@merge_params()
def process(
    input_data_path: str,
    neighbourhood_output: str,
    radii: Sequence[float],
    mask_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    neighbourhood_shape: str = "square",
    lead_times: Optional[Sequence[int]] = None,
    degrees_as_complex: bool = False,
    weighted_mode: bool = False,
    area_sum: bool = False,
    percentiles: Optional[Sequence[float]] = None,
    halo_radius: Optional[float] = None, config=None) -> xr.DataArray:
    """执行邻域处理。

    参数
    ----------
    input_data_path : str
        输入网格数据 nc 文件路径。
    neighbourhood_output : str
        邻域输出类型：``probabilities`` 或 ``percentiles``。
    radii : sequence of float
        邻域半径（米），可传单值或多值。
    mask_path : str, optional
        外部掩码 nc 文件路径，仅 ``probabilities`` 模式可用。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    neighbourhood_shape : str, default="square"
        邻域形状，``square`` 或 ``circular``。
    lead_times : sequence of int, optional
        与 ``radii`` 配套的时效（小时）。
    degrees_as_complex : bool, default=False
        是否将输入角度场转为复数后再计算。
    weighted_mode : bool, default=False
        圆形邻域加权模式。
    area_sum : bool, default=False
        是否返回邻域和而非邻域平均。
    percentiles : sequence of float, default=DEFAULT_PERCENTILES
        百分位列表（单位 %），仅 ``percentiles`` 模式使用。
    halo_radius : float, optional
        结果外圈裁剪半径（米）。

    返回
    -------
    xr.DataArray
        邻域处理结果。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "mask_path": (mask_path, "str"),
        "output_path": (output_path, "str"),
        "lead_times": (lead_times, "int_list"),
        "percentiles": (percentiles, "float_list"),
        "halo_radius": (halo_radius, "float"),
    })
    mask_path = _over['mask_path']
    output_path = _over['output_path']
    lead_times = _over['lead_times']
    percentiles = _over['percentiles']
    halo_radius = _over['halo_radius']
    from neighbourhood_probability_processing.src.utils._helpers import (
        complex_to_deg,
        deg_to_complex,
        radius_by_lead_time,
        remove_dataarray_halo,
    )
    from neighbourhood_probability_processing.src.nbhood import (
        DEFAULT_PERCENTILES,
        GeneratePercentilesFromANeighbourhood,
        NeighbourhoodProcessing,
    )

    if percentiles is None:
        percentiles = DEFAULT_PERCENTILES
    else:
        percentiles = _as_number_list(percentiles, float)
    radii = _as_number_list(radii, float)
    if lead_times is not None:
        lead_times = _as_number_list(lead_times, int)

    mode = str(neighbourhood_output).strip().lower()
    shape = str(neighbourhood_shape).strip().lower()
    if mode not in ("probabilities", "percentiles"):
        raise ValueError('neighbourhood_output 仅支持 "probabilities" 或 "percentiles"。')
    if shape not in ("square", "circular"):
        raise ValueError('neighbourhood_shape 仅支持 "square" 或 "circular"。')
    if mode == "percentiles" and mask_path is not None:
        raise RuntimeError('neighbourhood_output="percentiles" 时不支持 mask。')
    if mode == "percentiles" and weighted_mode:
        raise RuntimeError('weighted_mode 不能与 neighbourhood_output="percentiles" 同时使用。')
    if degrees_as_complex and mode == "percentiles":
        raise RuntimeError("complex 角度模式不支持 percentiles 输出。")
    if degrees_as_complex and shape == "circular":
        raise RuntimeError("complex 角度模式不支持 circular 邻域。")

    
    input_data = meb.checkout_griddata(meb.read_griddata_from_nc(input_data_path), valid_val=(-np.inf, np.inf, np.nan))
    # 掩码不一定是六维 meb，按单变量 nc 读取。
    mask = (
        None
        if mask_path is None
        else xr.open_dataarray(mask_path, decode_timedelta=False)
    )

    radius_or_radii, parsed_lead_times = radius_by_lead_time(list(radii), lead_times)

    work_input_data = input_data.copy()
    if degrees_as_complex:
        work_input_data = work_input_data.copy(
            data=deg_to_complex(np.asarray(work_input_data.values))
        )

    if mode == "probabilities":
        nbhood = NeighbourhoodProcessing(
            shape,
            radius_or_radii,
            lead_times=parsed_lead_times,
            weighted_mode=bool(weighted_mode),
            sum_only=bool(area_sum),
            re_mask=True,
        )
        # CLI 经 meb 读盘得到普通 DataArray，仅支持外部 mask；内部掩码需 MaskedArray
        # 输入（见 docs/nbhood.md），不在 CLI 场景内。
        result = nbhood.process(work_input_data, mask=mask)
    else:
        result = GeneratePercentilesFromANeighbourhood(
            radius_or_radii,
            lead_times=parsed_lead_times,
            percentiles=list(percentiles),
        ).process(work_input_data)

    if not isinstance(result, xr.DataArray):
        raise TypeError("算法结果不是 xarray.DataArray。")

    if degrees_as_complex:
        result = result.copy(data=complex_to_deg(np.asarray(result.values)))

    if halo_radius is not None:
        result = remove_dataarray_halo(result, halo_radius=float(halo_radius))

    result = result.astype(np.float32, copy=False)

    if output_path is not None:
        # meb.write_griddata_to_nc 会把 NaN 量化成 int32 哨兵，改用 xarray 直写。
        # 先写临时文件再替换，减轻 Windows 上目标文件被占用时的直接覆盖失败。
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "neighbourhood_result"
        tmp = output_file.with_suffix(output_file.suffix + ".tmp")
        if tmp.exists():
            tmp.unlink()
        result.to_dataset(name=var_name).to_netcdf(
            tmp,
            mode="w",
            encoding={
                var_name: {
                    "dtype": "float32",
                    "_FillValue": np.float32(np.nan),
                }
            },
        )
        try:
            tmp.replace(output_file)
        except PermissionError as err:
            raise PermissionError(
                f"无法覆盖 {output_file}（可能被 Jupyter 或其他进程占用）。"
                f"临时文件已写至 {tmp}，请关闭占用后重试。"
            ) from err

    return result
