#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI 示例：调用 CalculateForecastBias 计算历史平均偏差。

用法（仓库根目录，先改脚本底部路径）::

    python simple_bias_correction/cli/cal_calculate_forecast_bias.py

输入为预处理后的 meb 六维 ``.nc``；历史预报与实况可各传多个文件，沿 ``time`` 拼接。
预报与实况须已对齐到同一水平网格。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Union

import meteva_base as meb
import numpy as np
import xarray as xr


def process(
    historic_forecast_paths: Union[str, Path, Sequence[Union[str, Path]]],
    truth_paths: Union[str, Path, Sequence[Union[str, Path]]],
    *,
    output_path: Optional[Union[str, Path]] = None,
) -> xr.DataArray:
    """读取历史预报与实况，输出空间偏差场并可选写出。

    参数
    ----------
    historic_forecast_paths :
        一个或多个历史单值预报网格数据；多文件时沿 ``time``  维度拼接。
    truth_paths :
        对应实况网格数据；须能与预报按有效时刻配对。
    output_path :
        若给出则写出偏差场；``None`` 只返回结果。

    返回
    -------
    xr.DataArray
        偏差场，输出变量名为 ``forecast_error_of_<name>``。
    """
    from simple_bias_correction.src.simple_bias_correction import (
        CalculateForecastBias,
    )

    # 风速等诊断量可能超出 meb 默认 [-1000, 1000]；超界格点 checkout 会置 NaN
    valid_val = (-np.inf, np.inf, np.nan)

    def _concat_along_time(
        paths: Union[str, Path, Sequence[Union[str, Path]]],
    ) -> xr.DataArray:
        """将多个单日 meb 文件拼成带历史 ``time`` 维的六维场。"""
        if isinstance(paths, (str, Path)):
            path_list = [Path(paths)]
        else:
            path_list = [Path(p) for p in paths]
        if not path_list:
            raise ValueError("至少需要一个输入文件路径。")

        pieces: list[xr.DataArray] = []
        for path in path_list:
            da = meb.read_griddata_from_nc(str(path))
            if da is None:
                raise ValueError(f"读取网格数据失败: {path}")
            # 统一维序 member,level,time,dtime,lat,lon 并校验六维格式
            pieces.append(meb.checkout_griddata(da, valid_val=valid_val))

        if len(pieces) == 1:
            return pieces[0]
        # 各文件 time 仅含一个起报点；拼接后 time 维即多日历史样本
        return xr.concat(pieces, dim="time", coords="different", compat="equals")

    # 预报与实况分别拼接，再由 CalculateForecastBias 按有效时刻配对
    historic_forecasts = _concat_along_time(historic_forecast_paths)
    truths = _concat_along_time(truth_paths)
    result = CalculateForecastBias().process(historic_forecasts, truths)

    if output_path is not None:
        # meb.write_griddata_to_nc 的 effectiveNum 量化会损失精度，改用 xarray 直写。
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name
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


def main() -> None:
    """定义输入/输出路径并调用 ``process``（默认 ``resource/`` 样例）。"""
    import sys

    _PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    cli_input = _PACKAGE_ROOT / "resource" / "cli_input"
    cli_output = _PACKAGE_ROOT / "resource" / "cli_output"
    cli_output.mkdir(parents=True, exist_ok=True)

    multi_days = ("20220811", "20220812", "20220813")
    forecast_paths = sorted(
        p
        for p in cli_input.glob("*PT0003H00M*.nc")
        if any(day in p.name for day in multi_days)
        and not p.name.startswith(("apply_", "bias_"))
    )
    truth_paths = sorted(
        p
        for p in cli_input.glob("*PT0000H00M*.nc")
        if any(day in p.name for day in multi_days)
    )

    process(
        forecast_paths,
        truth_paths,
        output_path=cli_output / "mig_calculate_forecast_bias.nc",
    )


if __name__ == "__main__":
    main()
