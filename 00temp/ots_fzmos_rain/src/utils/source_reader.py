from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from utils.grid import GridConfig
from utils.micaps_io import read_micaps4


_NETCDF_SUFFIXES = {".nc", ".nc4", ".netcdf"}


@dataclass(frozen=True)
class SourceField:
    """保存一个输入降水场及其规则经纬度网格。"""

    values: np.ndarray
    grid: GridConfig


def _read_regular_axis(grid_data: object, name: str) -> tuple[np.ndarray, float]:
    """读取并校验规则网格的一维经度或纬度坐标。"""
    try:
        coordinates = np.asarray(grid_data.coords[name].values, dtype=np.float64)
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"NC 数据缺少 {name} 坐标") from exc

    if coordinates.ndim != 1 or coordinates.size < 2:
        raise ValueError(f"NC 数据的 {name} 坐标必须是一维且至少包含两个格点")
    if not np.all(np.isfinite(coordinates)):
        raise ValueError(f"NC 数据的 {name} 坐标包含非有限值")

    differences = np.diff(coordinates)
    spacing = float(differences[0])
    tolerance = max(abs(spacing) * 1.0e-5, 1.0e-7)
    if spacing == 0.0 or not np.allclose(
        differences,
        spacing,
        rtol=1.0e-5,
        atol=tolerance,
    ):
        raise ValueError(f"NC 数据的 {name} 坐标不是规则等间距网格")
    return coordinates, spacing


def _convert_netcdf_grid(grid_data: object, path: Path) -> SourceField:
    """将NC读取结果转换为程序使用的二维规则网格。"""
    try:
        dimensions = tuple(grid_data.dims)
        sizes = grid_data.sizes
    except AttributeError as exc:
        raise ValueError(f"NC 数据结构无效：{path}") from exc

    if "lat" not in dimensions or "lon" not in dimensions:
        raise ValueError(f"NC 数据必须包含 lat 和 lon 维度：{path}")

    extra_dimensions = [name for name in dimensions if name not in {"lat", "lon"}]
    non_singleton = [name for name in extra_dimensions if int(sizes[name]) != 1]
    if non_singleton:
        names = ", ".join(non_singleton)
        raise ValueError(f"NC 文件包含多个待选择的数据场（维度：{names}）：{path}")

    # 每个输入文件应只包含一个预报场，去掉读取器补齐的单元素维度。
    field = grid_data.isel({name: 0 for name in extra_dimensions}, drop=True)
    field = field.transpose("lat", "lon")
    latitudes, dlat = _read_regular_axis(field, "lat")
    longitudes, dlon = _read_regular_axis(field, "lon")

    values = np.asarray(field.values, dtype=np.float32)
    expected_shape = (latitudes.size, longitudes.size)
    if values.shape != expected_shape:
        raise ValueError(f"NC 数据形状为 {values.shape}，预期为 {expected_shape}")

    # 与原程序保持一致，将 NaN 和无穷值统一作为 9999 缺测值处理。
    values = values.copy()
    values[~np.isfinite(values)] = np.float32(9999.0)
    grid = GridConfig(
        lat_start=float(latitudes[0]),
        lon_start=float(longitudes[0]),
        lat_end=float(latitudes[-1]),
        lon_end=float(longitudes[-1]),
        dlat=dlat,
        dlon=dlon,
        num_x=int(longitudes.size),
        num_y=int(latitudes.size),
    )
    return SourceField(values=values, grid=grid)


def _read_netcdf_with_meteva(path: Path) -> SourceField:
    """使用meteva读取NC文件。"""
    try:
        import meteva.base as meb
    except ImportError as exc:
        raise RuntimeError(
            "读取 NC 文件需要 meteva，请先在当前 Python 环境中安装 meteva"
        ) from exc

    grid_data = meb.read_griddata_from_nc(str(path))
    if grid_data is None:
        raise ValueError(f"meteva 无法读取 NC 文件：{path}")
    return _convert_netcdf_grid(grid_data, path)


def _read_netcdf_with_xarray(path: Path) -> SourceField:
    """使用xarray读取NC文件。"""
    try:
        import xarray as xr
    except ImportError as exc:
        raise RuntimeError(
            "使用 xarray 读取 NC 文件时需要安装 xarray"
        ) from exc

    with xr.open_dataset(path) as dataset:
        variable_names = list(dataset.data_vars)
        if len(variable_names) != 1:
            names = ", ".join(variable_names) if variable_names else "无"
            raise ValueError(f"NC 文件必须只包含一个数据变量，当前为：{names}：{path}")
        grid_data = dataset[variable_names[0]].load()
    return _convert_netcdf_grid(grid_data, path)


def read_source_field(path: str | Path, nc_reader: str = "meteva") -> SourceField:
    """根据扩展名读取 MICAPS4 或 NetCDF 输入文件。"""
    file_path = Path(path)
    if file_path.suffix.lower() in _NETCDF_SUFFIXES:
        if nc_reader == "meteva":
            return _read_netcdf_with_meteva(file_path)
        if nc_reader == "xarray":
            return _read_netcdf_with_xarray(file_path)
        raise ValueError(f"不支持的 NC 读取方式：{nc_reader}")

    micaps = read_micaps4(file_path)
    return SourceField(values=micaps.values, grid=micaps.grid)
