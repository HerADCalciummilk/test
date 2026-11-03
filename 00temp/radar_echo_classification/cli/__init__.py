#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""echo_class 模块 CLI 入口。"""

from __future__ import annotations

import gc
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import xarray as xr


_CLI_SCRIPTS = (
    "radar_echo_classification/cli/steiner_conv_strat_main.py",
    "radar_echo_classification/cli/feature_detection_main.py",
    "radar_echo_classification/cli/conv_strat_raut_main.py",
    "radar_echo_classification/cli/hydroclass_semisupervised_main.py",
)

# netCDF 库对 float32 的默认填充值（NC_FILL_FLOAT），与 netCDF4.default_fillvals['f4'] 相同。
# CF/NUG 推荐用 ``_FillValue`` 显式声明缺测；该数值本身来自 netCDF 库而非 CF 另行规定。
_CF_NETCDF_FILL = np.float32(9.969209968386869e36)


def _sanitize_attr_value(value):
    """将属性值转换为 NetCDF 可序列化类型。"""
    # xarray/netCDF 属性只接受 str、数值、ndarray、list/tuple 等；
    # bool / numpy 标量 / dict 需先转换，否则 to_netcdf 会 TypeError。
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        # 例如 conv_strat_raut 的 parameters 字典
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        # 纯数值序列可直接写入；含混合类型时改为 JSON 字符串
        if all(
            isinstance(v, (int, float, np.integer, np.floating, bool, np.bool_))
            for v in value
        ):
            return [
                int(v)
                if isinstance(v, (bool, np.bool_))
                else (v.item() if isinstance(v, np.generic) else v)
                for v in value
            ]
        return json.dumps(value, ensure_ascii=False)
    return value


def _sanitize_grid_values_for_nc(values: np.ndarray) -> np.ndarray:
    """将 NaN/异常极值统一为 NetCDF 缺测填充值（float32）。

    分类标签 ``0`` 是有效值，不会被当作缺测。
    """
    arr = np.asarray(values, dtype=np.float32).copy()
    # NaN / Inf
    invalid = ~np.isfinite(arr)
    # 过大数值（含未识别的填充哨兵）
    invalid |= np.abs(arr) >= np.float32(1e19)
    # 常见异常下界（不含分类标签 0）
    invalid |= arr <= np.float32(-1e6)
    # meteva int32 缩放路径可能留下的伪填充（约 -2147483.6）
    invalid |= np.abs(arr + 2147483.648) < np.float32(1.0)
    arr[invalid] = _CF_NETCDF_FILL
    return arr


def save_echo_class_grid_to_netcdf(
    data: xr.DataArray | xr.Dataset,
    output_path: str | Path,
    *,
    compression: bool = True,
) -> Path:
    """保存 echo_class 网格结果为 NetCDF（float32 + CF 缺测值）。

    不使用 ``meteva_base.write_griddata_to_nc``：其默认 ``dtype=int32`` 与
    ``scale_factor=0.001`` 会把分类标签 ``0/1/2`` 存成 ``0/1000/2000``，
    且无法正确表达 NaN。

    与 ``qpe.cli.cinrad_meb.save_meteva_grid_to_netcdf`` 策略对齐，但额外：
    - 支持 ``Dataset``（多字段输出）
    - 序列化嵌套 attrs（如 ``parameters`` dict）
    - Windows/Jupyter 下先写临时文件再替换，减轻句柄占用导致的覆盖失败
    """
    if not isinstance(data, (xr.DataArray, xr.Dataset)):
        raise TypeError(
            "save_echo_class_grid_to_netcdf only supports xarray.DataArray or xarray.Dataset"
        )

    path_obj = Path(output_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    # 统一成 Dataset：单字段 DataArray 转一变量；多字段结果（如 hydro）直接深拷贝
    if isinstance(data, xr.DataArray):
        var_name = data.name if data.name else "data"
        dataset = data.to_dataset(name=var_name)
    else:
        dataset = data.copy(deep=True)

    # 全局与变量属性清洗，保证可写入 NetCDF
    dataset.attrs = {k: _sanitize_attr_value(v) for k, v in dict(dataset.attrs).items()}
    encoding: dict = {}
    for data_var in dataset.data_vars:
        # 缺测/极值 → NC_FILL_FLOAT；保留分类标签 0/1/2/...
        values = _sanitize_grid_values_for_nc(dataset[data_var].values)
        dataset[data_var] = dataset[data_var].copy(data=values)
        dataset[data_var].attrs = {
            k: _sanitize_attr_value(v)
            for k, v in dict(dataset[data_var].attrs).items()
        }
        # 填充值只放在 encoding，避免与 attrs 重复冲突
        dataset[data_var].attrs.pop("_FillValue", None)
        dataset[data_var].attrs.pop("missing_value", None)
        enc = {
            "dtype": "float32",  # 不用 int32，避免缩放与 NaN 问题
            "_FillValue": _CF_NETCDF_FILL,
            "missing_value": _CF_NETCDF_FILL,
        }
        if compression:
            enc["zlib"] = True
            enc["complevel"] = 4
        encoding[data_var] = enc

    # Windows + Jupyter 下 xarray/netCDF4 常会缓存句柄，直接覆盖同名文件会 PermissionError。
    try:
        from xarray.backends.file_manager import FILE_CACHE

        FILE_CACHE.clear()
    except Exception:
        FILE_CACHE = None
    gc.collect()

    # 先写同目录临时文件，成功后再替换目标路径，降低覆盖失败与半写入风险
    fd, tmp_name = tempfile.mkstemp(suffix=".nc", dir=str(path_obj.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        dataset.to_netcdf(tmp_path, mode="w", encoding=encoding)
        if FILE_CACHE is not None:
            FILE_CACHE.clear()
        gc.collect()
        if path_obj.exists():
            path_obj.unlink()
        tmp_path.replace(path_obj)
    except PermissionError as exc:
        tmp_path.unlink(missing_ok=True)
        raise PermissionError(
            f"Cannot write output file: {path_obj}. "
            "The file may be open in another process (for example, Jupyter). "
            "Please close dataset handles or use a different output path."
        ) from exc
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return path_obj


def main(argv: Optional[Sequence[str]] = None):
    """列出可直接运行的 CLI 示例脚本。"""
    lines = [
        "echo_class 模块 CLI 已改为示例脚本，请直接运行：",
        *(f"  python {script}" for script in _CLI_SCRIPTS),
        "",
        "在脚本底部的 if __name__ == '__main__' 中修改路径与参数后执行。",
    ]
    raise SystemExit("\n".join(lines))
