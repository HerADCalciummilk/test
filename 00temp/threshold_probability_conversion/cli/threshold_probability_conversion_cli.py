#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阈值概率转换命令行。

在本包目录执行::

    python -m cli threshold --input-path resource/cli_input/input_meb.nc
    python cli/prb_threshold.py --input-path resource/cli_input/input_meb.nc

Python::

    from cli.prb_threshold import PrbThresholdCli
    PrbThresholdCli.call(
        input_path="resource/cli_input/input_meb.nc",
        threshold_values=280.0,
    )
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Union


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    parent = root.parent
    root_s = str(root)
    parent_s = str(parent)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if parent_s not in sys.path:
        sys.path.append(parent_s)


_bootstrap_paths()

import meteva_base as meb
import xarray as xr

from utils.merge_params import merge_params


@merge_params()
def process(
    input_path: str,
    *,
    threshold_values: Optional[Union[float, List[float]]] = None,
    threshold_config_path: Optional[str] = None,
    threshold_units: Optional[str] = None,
    comparison_operator: str = ">",
    fuzzy_factor: Optional[float] = None,
    fill_masked: Optional[float] = None,
    vicinity: Optional[Union[float, List[float]]] = None,
    landmask_path: Optional[str] = None,
    collapse_coord: Optional[Union[str, List[str]]] = None,
    output_path: Optional[str] = None, config=None) -> xr.DataArray | xr.Dataset:
    """读取诊断场并生成相对阈值的概率场。

    参数
    ----------
    input_path :
        meb 六维诊断场 nc。
    threshold_values :
        阈值列表；与 ``threshold_config_path`` 互斥。
    threshold_config_path :
        JSON 阈值配置路径。
    threshold_units :
        阈值单位（如 ``celsius``）。
    comparison_operator :
        比较符，默认 ``>``。
    fuzzy_factor :
        可选模糊因子 (0, 1)。
    fill_masked :
        可选，比较前填充掩码/缺测。
    vicinity :
        邻域半径（米），可多个。
    landmask_path :
        海陆掩码 nc（与 vicinity 联用）。
    collapse_coord :
        压维坐标，``member`` / ``time``。
    output_path :
        可选写出路径。
    config :
        保留给调用方传入。本函数按已给出的参数执行。
    """
    from threshold_probability_conversion.src.threshold import Threshold

    data = meb.read_griddata_from_nc(input_path)
    threshold_config = None
    if threshold_config_path is not None:
        with open(threshold_config_path, encoding="utf-8") as fh:
            threshold_config = json.load(fh)

    landmask = None
    if landmask_path is not None:
        landmask = xr.open_dataset(landmask_path)
        landmask = landmask[list(landmask.data_vars)[0]]

    result = Threshold(
        threshold_values=threshold_values,
        threshold_config=threshold_config,
        fuzzy_factor=fuzzy_factor,
        threshold_units=threshold_units,
        comparison_operator=comparison_operator,
        fill_masked=fill_masked,
        vicinity=vicinity,
        collapse_coord=collapse_coord,
    ).process(data, landmask=landmask)

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(result, xr.Dataset):
            encoding = {
                name: {"dtype": "float32", "zlib": True, "complevel": 4}
                for name in result.data_vars
            }
            result.to_netcdf(output_path, encoding=encoding)
        else:
            # 概率场写 float32，避免 meb 默认 scale_factor 打包
            name = result.name or "probability"
            result.astype("float32").to_dataset(name=name).to_netcdf(
                output_path,
                encoding={name: {"dtype": "float32", "zlib": True, "complevel": 4}},
            )
    return result


