from __future__ import annotations

from datetime import datetime
from pathlib import Path
import warnings

import numpy as np

from utils.grid import GridConfig


def write_griddata_to_nc(
    path: str | Path,
    initial_time: datetime,
    forecast_hour: int,
    element_name: str,
    grid: GridConfig,
    values: np.ndarray,
    nc_writer: str = "meteva",
) -> None:
    """使用配置的写出方式将二维规则网格场保存为NC文件。"""
    array = np.asarray(values, dtype=np.float32)
    expected_shape = (grid.num_y, grid.num_x)
    if array.shape != expected_shape:
        raise ValueError(f"输出网格形状为 {array.shape}，预期为 {expected_shape}")
    array = array.copy()
    array[~np.isfinite(array)] = np.float32(9999.0)

    output_path = Path(path)
    if nc_writer == "meteva":
        _write_with_meteva(
            output_path,
            initial_time,
            forecast_hour,
            element_name,
            grid,
            array,
        )
        return
    if nc_writer == "xarray":
        _write_with_xarray(
            output_path,
            initial_time,
            forecast_hour,
            element_name,
            grid,
            array,
        )
        return
    raise ValueError(f"不支持的 NC 保存方式：{nc_writer}")


def _write_with_meteva(
    output_path: Path,
    initial_time: datetime,
    forecast_hour: int,
    element_name: str,
    grid: GridConfig,
    array: np.ndarray,
) -> None:
    """使用meteva保存NC文件。"""
    try:
        import meteva.base as meb
    except ImportError as exc:
        raise RuntimeError(
            "保存 NC 文件需要 meteva，请先在当前 Python 环境中安装 meteva"
        ) from exc

    meteva_grid = meb.grid(
        [grid.lon_start, grid.lon_end, grid.dlon],
        [grid.lat_start, grid.lat_end, grid.dlat],
        gtime=[initial_time],
        dtime_list=[forecast_hour],
        level_list=[0],
        member_list=[element_name],
    )
    grid_data = meb.grid_data(meteva_grid, data=array)
    grid_data.name = element_name
    grid_data.attrs["short_name"] = element_name
    grid_data.attrs["units"] = "mm"
    grid_data.attrs["dtime_units"] = "hour"

    from xarray.coding.variables import SerializationWarning

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"saving variable .* without any _FillValue to use for NaNs",
            category=SerializationWarning,
        )
        written = meb.write_griddata_to_nc(
            grid_data,
            save_path=str(output_path),
            creat_dir=True,
            effectiveNum=2,
        )
    if not written:
        raise OSError(f"meteva 写入 NC 文件失败：{output_path}")


def _write_with_xarray(
    output_path: Path,
    initial_time: datetime,
    forecast_hour: int,
    element_name: str,
    grid: GridConfig,
    array: np.ndarray,
) -> None:
    """使用xarray保存与meteva相同结构的NC文件。"""
    try:
        import xarray as xr
    except ImportError as exc:
        raise RuntimeError(
            "使用 xarray 保存 NC 文件时需要安装 xarray"
        ) from exc

    latitudes = np.arange(grid.num_y, dtype=np.float64) * grid.dlat + grid.lat_start
    longitudes = np.arange(grid.num_x, dtype=np.float64) * grid.dlon + grid.lon_start
    grid_data = xr.DataArray(
        array.reshape(1, 1, 1, 1, grid.num_y, grid.num_x),
        coords={
            "member": [element_name],
            "level": [0],
            "time": [initial_time],
            "dtime": [forecast_hour],
            "lat": latitudes,
            "lon": longitudes,
        },
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name=element_name,
        attrs={
            "short_name": element_name,
            "units": "mm",
            "dtime_units": "hour",
        },
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    from xarray.coding.variables import SerializationWarning

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"saving variable .* without any _FillValue to use for NaNs",
            category=SerializationWarning,
        )
        grid_data.to_netcdf(
            output_path,
            encoding={
                element_name: {
                    "dtype": "int32",
                    "scale_factor": 0.01,
                    "zlib": True,
                    "_FillValue": None,
                }
            },
        )
