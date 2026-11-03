#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""风速降尺度 CLI 示例。"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr
from cf_units import Unit
import meteva_base as meb

def process(
    wind_speed_path: str,
    sigma_path: str,
    target_orography_path: str,
    standard_orography_path: str,
    silhouette_roughness_path: str,
    model_resolution: float,
    vegetative_roughness_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    output_height_level: Optional[float] = None,
    output_height_level_units: str = "m",
) -> xr.DataArray:
    """风速降尺度处理流程。

    参数
    ----------
    wind_speed_path : str
        待订正风速场 nc 文件路径。
    sigma_path : str
        网格高度标准差场 nc 文件路径。
    target_orography_path : str
        目标网格地形高度场 nc 文件路径。
    standard_orography_path : str
        标准网格地形高度场 nc 文件路径。
    silhouette_roughness_path : str
        地形轮廓粗糙度场 nc 文件路径。
    model_resolution : float
        原始模式分辨率（米）。
    vegetative_roughness_path : str, optional
        植被粗糙度长度场 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    output_height_level : float, optional
        若指定，则从结果中提取该高度层。
    output_height_level_units : str, default="m"
        ``output_height_level`` 的单位。

    返回
    -------
    xr.DataArray
        订正后的风速场。
    """
    from orographic_wind_downscaling.src.wind_downscaling import RoughnessCorrection
        
    _unbounded = (-np.inf, np.inf, np.nan)

    if output_height_level_units and output_height_level is None:
        warnings.warn(
            "output_height_level_units 已设置，但未提供 output_height_level；该参数不会生效。"
        )

    wind_speed = meb.checkout_griddata(
        meb.read_griddata_from_nc(wind_speed_path), valid_val=_unbounded
    )
    sigma = meb.checkout_griddata(
        meb.read_griddata_from_nc(sigma_path), is_single=True, valid_val=_unbounded
    )
    target_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(target_orography_path),
        is_single=True,
        valid_val=_unbounded,
    )
    standard_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(standard_orography_path),
        is_single=True,
        valid_val=_unbounded,
    )
    silhouette_roughness = meb.checkout_griddata(
        meb.read_griddata_from_nc(silhouette_roughness_path), is_single=True
    )
    vegetative_roughness = (
        None
        if vegetative_roughness_path is None
        else meb.checkout_griddata(
            meb.read_griddata_from_nc(vegetative_roughness_path), is_single=True
        )
    )

    plugin = RoughnessCorrection(
        silhouette_roughness,
        sigma,
        target_orography,
        standard_orography,
        model_resolution,
        z0=vegetative_roughness,
    )
    result = plugin.process(wind_speed)

    result = result.astype(np.float32, copy=False)
    result.name = wind_speed.name or result.name or "wind_speed"

    if output_height_level is not None:
        result = _extract_height_level(
            result,
            output_height_level=output_height_level,
            output_height_level_units=output_height_level_units,
        )

    if output_path is not None:
        _write_result_netcdf_float32(result, output_path)

    return result


def _extract_height_level(
    data: xr.DataArray,
    output_height_level: float,
    output_height_level_units: str,
) -> xr.DataArray:
    """按指定高度提取单层结果。"""
    level_name = "level"
    if level_name not in data.coords:
        raise ValueError("结果中不存在 level 坐标。")

    levels = np.asarray(data.coords[level_name].values, dtype=np.float64)
    coord_units = data.coords[level_name].attrs.get("units", "m")
    target_level = float(output_height_level)

    if output_height_level_units and output_height_level_units != coord_units:
        target_level = float(
            Unit(output_height_level_units).convert(target_level, Unit(coord_units))
        )

    idx = np.where(np.isclose(levels, target_level, rtol=0.0, atol=1e-6))[0]
    if idx.size == 0:
        raise ValueError(
            "Requested height level not found. "
            f"Available levels: {levels.tolist()} (units: {coord_units})"
        )
    return data.isel({level_name: int(idx[0])})


def _write_result_netcdf_float32(data: xr.DataArray, output_path: str) -> None:
    """以 float32 直写 NetCDF，避免 scale_factor 量化误差。"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    output = data.astype(np.float32, copy=False)
    var_name = output.name or "wind_speed"
    output.name = var_name
    dataset = output.to_dataset(name=var_name)
    dataset.to_netcdf(
        target,
        engine="netcdf4",
        encoding={
            var_name: {
                "dtype": "float32",
                "zlib": False,
                "_FillValue": np.float32(np.nan),
            }
        },
    )


if __name__ == "__main__":
    import sys

    #添加项目根目录到系统路径,可直接运行示例脚本
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    #测试数据路径
    data_dir = (
        Path(__file__).resolve().parent.parent
        / "test_data"
        / "wind_calculations_data"
        / "cli_input"
    )
    cli_output_dir = (
        Path(__file__).resolve().parent.parent
        / "test_data"
        / "wind_calculations_data"
        / "cli_output"
    )

    #各输入文件的路径映射
    wind_speed_path = str(data_dir / "input.nc")   #待订正风速场nc文件路径
    sigma_path = str(data_dir / "sigma.nc")   #网格高度标准差场nc文件路径
    target_orography_path = str(data_dir / "highres_orog.nc")   #目标网格地形高度场nc文件路径
    standard_orography_path = str(data_dir / "standard_orog.nc")   #标准网格地形高度场nc文件路径
    silhouette_roughness_path = str(data_dir / "a_over_s.nc")   #地形轮廓粗糙度场nc文件路径
    vegetative_roughness_path = str(data_dir / "veg.nc")   #植被粗糙度长度场nc文件路径
    output_path = str(cli_output_dir / "cli_result.nc")   #输出nc文件路径

    model_resolution = 1500.0   #模式原始分辨率（米）
    output_height_level = None   #若指定，则从结果中提取该高度层
    output_height_level_units = "m"   #output_height_level的单位

    required_inputs = [
        Path(wind_speed_path),
        Path(sigma_path),
        Path(target_orography_path),
        Path(standard_orography_path),
        Path(silhouette_roughness_path),
        Path(vegetative_roughness_path),
    ]
    missing = [str(path) for path in required_inputs if not path.is_file()]
    if missing:
        print(
            "示例输入不存在：\n  "
            + "\n  ".join(missing)
            + "\n请补齐 test_data 或先运行 cli/preprocess_test_data.py，"
            "也可在此处改为自己的输入/输出路径。"
        )
    else:
        result = process(
            wind_speed_path,
            sigma_path,
            target_orography_path,
            standard_orography_path,
            silhouette_roughness_path,
            model_resolution,
            vegetative_roughness_path=vegetative_roughness_path,
            output_path=output_path,
            output_height_level=output_height_level,
            output_height_level_units=output_height_level_units,
        )
