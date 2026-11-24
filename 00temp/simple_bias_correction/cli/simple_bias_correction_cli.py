#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI：调用 ApplyBiasCorrection 施加简单加性偏差订正。

输入为预处理后的 meb 六维 ``.nc``：一个当前预报，以及零个或多个偏差场
（变量名含 ``forecast_error``）。

在本包目录执行::

    python -m cli.prb_bias_correction --forecast-path fcst.nc --bias-paths bias.nc --output-path corrected.nc
    python cli/prb_bias_correction.py --forecast-path fcst.nc --bias-paths bias.nc --output-path corrected.nc

Python::

    from cli.prb_bias_correction import PrbBiasCorrectionCli
    PrbBiasCorrectionCli.call(
        forecast_path="fcst.nc",
        bias_paths=["bias.nc"],
        output_path="corrected.nc",
    )
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence, Union

import meteva_base as meb
import numpy as np
import xarray as xr


def _bootstrap_paths() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


_bootstrap_paths()

from utils.merge_params import merge_params


@merge_params()
def process(
    forecast_path: Union[str, Path],
    bias_paths: Optional[Union[str, Path, Sequence[Union[str, Path]]]] = None,
    *,
    lower_bound: Optional[float] = None,
    upper_bound: Optional[float] = None,
    fill_masked_bias_values: bool = False,
    output_path: Optional[Union[str, Path]] = None,
    config=None,
) -> xr.DataArray:
    """读取预报与偏差场，输出订正结果并可选写出。

    参数
    ----------
    forecast_path :
        待订正预报网格数据。
    bias_paths :
        一个或多个偏差场网格数据；``None`` 或空列表时不订正（告警后返回原预报）。
    lower_bound / upper_bound :
        订正后物理上下界；``None`` 表示该侧不裁剪。
    fill_masked_bias_values :
        偏差缺测是否在相减前填 0。
    output_path :
        若给出则写出结果；``None`` 只返回。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        订正后的预报。
    """
    from simple_bias_correction.src.simple_bias_correction import ApplyBiasCorrection

    # 避免 meb 默认合理值范围误伤风速等诊断量
    valid_val = (-np.inf, np.inf, np.nan)

    forecast = meb.read_griddata_from_nc(str(forecast_path))
    if forecast is None:
        raise ValueError(f"读取网格数据失败: {forecast_path}")
    # 统一维序 member,level,time,dtime,lat,lon 并校验六维格式
    forecast = meb.checkout_griddata(forecast, valid_val=valid_val)

    # 第一个场为待订正预报；后续为偏差场（变量名含 forecast_error，由插件拆分）
    inputs: list[xr.DataArray] = [forecast]
    if bias_paths:
        if isinstance(bias_paths, (str, Path)):
            bias_path_list = [Path(bias_paths)]
        else:
            bias_path_list = [Path(p) for p in bias_paths]
        for path in bias_path_list:
            bias = meb.read_griddata_from_nc(str(path))
            if bias is None:
                raise ValueError(f"读取网格数据失败: {path}")
            inputs.append(meb.checkout_griddata(bias, valid_val=valid_val))

    # 多份偏差时插件沿 time 求平均；无偏差时告警并返回原预报
    result = ApplyBiasCorrection(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        fill_masked_bias_values=fill_masked_bias_values,
    ).process(*inputs)

    if output_path is not None:
        # meb.write_griddata_to_nc 的 effectiveNum 量化会损失精度，改用 xarray 直写。
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "bias_corrected"
        result.to_dataset(name=var_name).to_netcdf(
            out_path,
            mode="w",
            encoding={
                var_name: {
                    "dtype": "float32",
                    "_FillValue": np.float32(np.nan),
                }
            },
        )

    return result
