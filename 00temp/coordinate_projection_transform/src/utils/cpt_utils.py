# -*- coding: utf-8 -*-
"""本包公共工具：网格元数据、Cube 维坐标组装、cartopy 重采样、目标坐标构造。

合并原 ``grid_meta`` / ``cube_setup`` / ``cartopy_cube_regrid``，避免分散导入与重复实现。
无 ``nimm`` 依赖。导入：``from utils.cpt_utils import ...``（经包级 ``utils`` 合并 ``src/utils``）。
"""
from __future__ import annotations

from collections import namedtuple
from copy import deepcopy
from typing import Any, List, Optional, Tuple, Union

import iris.std_names
import numpy as np
from cartopy import crs as ccrs
from iris.coord_systems import GeogCS, LambertConformal
from iris.coords import DimCoord
from iris.cube import Cube
from numpy import ndarray
from numpy.ma.core import MaskedArray
from scipy.interpolate import RegularGridInterpolator

# ---------------------------------------------------------------------------
# 网格 / dtype / 时间约定（原 grid_meta）
# ---------------------------------------------------------------------------

FLOAT_DTYPE = np.float32
FLOAT_TYPES = [np.float32, np.float64]

CHINA_SECANT_LATITUDES = (25.0, 47.0)
ELLIPSOID = GeogCS(semi_major_axis=6378137.0, semi_minor_axis=6356752.314140356)
GLOBAL_GRID_CCRS = GeogCS(6371229.0)
STANDARD_GRID_CCRS = LambertConformal(
    central_lat=34.0,
    central_lon=105.0,
    secant_latitudes=CHINA_SECANT_LATITUDES,
    ellipsoid=ELLIPSOID,
)

GRID_COORD_ATTRIBUTES = {
    "latlon": {
        "xname": "longitude",
        "yname": "latitude",
        "units": "degrees",
        "coord_system": GLOBAL_GRID_CCRS,
        "default_grid_spacing": 1,
    },
    "equalarea": {
        "xname": "projection_x_coordinate",
        "yname": "projection_y_coordinate",
        "units": "metres",
        "coord_system": STANDARD_GRID_CCRS,
        "default_grid_spacing": 1000,
    },
}

DIM_COORD_ATTRIBUTES = {
    "realization": {"units": "1"},
    "height": {"units": "m", "attributes": {"positive": "up"}},
    "pressure": {"units": "Pa", "attributes": {"positive": "down"}},
}

TimeSpec = namedtuple("TimeSpec", ("calendar", "dtype", "units"))
_TIME_REFERENCE_SPEC = TimeSpec(
    calendar="standard", dtype=np.int64, units="seconds since 1970-01-01 00:00:00"
)
_TIME_INTERVAL_SPEC = TimeSpec(calendar=None, dtype=np.int32, units="seconds")

TIME_COORDS = {
    "time": _TIME_REFERENCE_SPEC,
    "time_in_local_timezone": _TIME_REFERENCE_SPEC,
    "forecast_reference_time": _TIME_REFERENCE_SPEC,
    "forecast_period": _TIME_INTERVAL_SPEC,
    "UTC_offset": _TIME_INTERVAL_SPEC,
}

# ---------------------------------------------------------------------------
# Cube 维坐标组装（原 cube_setup）
# ---------------------------------------------------------------------------


def _create_dimension_coord(
    coord_array: Optional[List[float]],
    data_length: int,
    coord_name: str,
    **kwargs: Any,
) -> DimCoord:
    if coord_array is not None:
        if len(coord_array) != data_length:
            raise ValueError(
                "Cannot generate {} {}s with data of length "
                "{}".format(len(coord_array), coord_name, data_length)
            )
        coord_array = np.array(coord_array)
        if issubclass(coord_array.dtype.type, float):
            coord_array = coord_array.astype(np.float32)
    else:
        coord_array = np.arange(data_length).astype(np.int32)

    if coord_name in iris.std_names.STD_NAMES:
        return DimCoord(coord_array, standard_name=coord_name, **kwargs)
    return DimCoord(coord_array, long_name=coord_name, **kwargs)


def construct_dimension_coords(
    data: Union[MaskedArray, ndarray],
    y_coord: DimCoord,
    x_coord: DimCoord,
    realizations: Union[List[float], ndarray],
    height_levels: Union[List[float], ndarray],
    pressure: bool,
):
    """组装 realization / height / y / x 维坐标列表。"""
    data_shape = data.shape
    ndims = len(data_shape)

    if ndims not in (2, 3, 4):
        raise ValueError(
            "Expected 2 to 4 dimensions on input data: got {}".format(ndims)
        )
    if realizations is not None and height_levels is not None and ndims != 4:
        raise ValueError(
            "Input data must have 4 dimensions to add both realization "
            "and height coordinates: got {}".format(ndims)
        )
    if height_levels is None and ndims == 4:
        raise ValueError("Height levels must be provided if data has 4 dimensions.")

    dim_coords = []
    if ndims == 4 or (height_levels is None and ndims == 3):
        realization_coord = _create_dimension_coord(
            realizations,
            data_shape[0],
            "realization",
            units=DIM_COORD_ATTRIBUTES["realization"]["units"],
        )
        dim_coords.append((realization_coord, 0))

    if height_levels is not None and ndims in (3, 4):
        i = len(dim_coords)
        coord_name = "pressure" if pressure else "height"
        height_coord = _create_dimension_coord(
            height_levels,
            data_shape[i],
            coord_name,
            units=DIM_COORD_ATTRIBUTES[coord_name]["units"],
            attributes=DIM_COORD_ATTRIBUTES[coord_name]["attributes"],
        )
        dim_coords.append((height_coord, i))

    dim_coords.append((y_coord, len(dim_coords)))
    dim_coords.append((x_coord, len(dim_coords)))
    return dim_coords


def check_mandatory_standards(cube: Cube) -> None:
    """原 nimm/improver 强制 dtype/units 检查；本包改为空操作。"""
    _ = cube


# ---------------------------------------------------------------------------
# 目标网格坐标构造（iris / cartopy 插件共用）
# ---------------------------------------------------------------------------


def make_lonlat_coords(
    lonlat_extent: Tuple[float, float, float, float] = (83.0, 138.0, 12.0, 53.0),
    grid_spacing: float = 0.1,
) -> Tuple[np.ndarray, np.ndarray, DimCoord, DimCoord]:
    """构造等经纬度 ``(xpoints, ypoints, coord_x, coord_y)``。"""
    lonmin, lonmax, latmin, latmax = lonlat_extent
    spacing = float(grid_spacing)
    xpoints = np.arange(lonmin, lonmax + spacing * 0.5, spacing, dtype=FLOAT_DTYPE)
    ypoints = np.arange(latmin, latmax + spacing * 0.5, spacing, dtype=FLOAT_DTYPE)
    attrs = GRID_COORD_ATTRIBUTES["latlon"]
    coord_system = attrs["coord_system"]
    coord_x = DimCoord(
        xpoints,
        standard_name=attrs["xname"],
        units=attrs["units"],
        coord_system=coord_system,
    )
    coord_x.guess_bounds()
    coord_y = DimCoord(
        ypoints,
        standard_name=attrs["yname"],
        units=attrs["units"],
        coord_system=coord_system,
    )
    coord_y.guess_bounds()
    return xpoints, ypoints, coord_x, coord_y


def make_equalarea_coords(
    projection_extent: Tuple[float, float, float, float] = (83, 138, 12, 53),
    secant_latitudes: Optional[Tuple[float, float]] = None,
    grid_distance: float = 1000,
) -> Tuple[np.ndarray, np.ndarray, DimCoord, DimCoord]:
    """构造 Lambert 等距 ``(xpoints, ypoints, coord_x, coord_y)``。"""
    if secant_latitudes is None:
        secant_latitudes = CHINA_SECANT_LATITUDES
    xy_coord = LambertConformal(
        central_lon=(projection_extent[0] + projection_extent[1]) / 2.0,
        central_lat=(projection_extent[2] + projection_extent[3]) / 2.0,
        secant_latitudes=secant_latitudes,
        ellipsoid=ELLIPSOID,
    )
    xy_proj = xy_coord.as_cartopy_crs()
    xmin, ymin = xy_proj.transform_point(
        projection_extent[0], projection_extent[2], src_crs=ccrs.PlateCarree()
    )
    xmax, ymax = xy_proj.transform_point(
        projection_extent[1], projection_extent[3], src_crs=ccrs.PlateCarree()
    )
    xpoints = np.arange(xmin, xmax + 1, grid_distance, dtype=FLOAT_DTYPE)
    ypoints = np.arange(ymin, ymax + 1, grid_distance, dtype=FLOAT_DTYPE)
    attrs = GRID_COORD_ATTRIBUTES["equalarea"]
    coord_x = DimCoord(
        xpoints,
        standard_name=attrs["xname"],
        units=attrs["units"],
        coord_system=xy_coord,
    )
    coord_x.guess_bounds()
    coord_y = DimCoord(
        ypoints,
        standard_name=attrs["yname"],
        units=attrs["units"],
        coord_system=xy_coord,
    )
    coord_y.guess_bounds()
    return xpoints, ypoints, coord_x, coord_y


def source_xy_sig(source_cube: Cube, include_coord_system: bool = False) -> tuple:
    """源 Cube 空间轴签名，用于缓存 regridder / query 点。"""
    sx = source_cube.coord(axis="x")
    sy = source_cube.coord(axis="y")
    sig = (
        sx.name(),
        sy.name(),
        float(sx.points[0]),
        float(sx.points[-1]),
        int(sx.shape[0]),
        float(sy.points[0]),
        float(sy.points[-1]),
        int(sy.shape[0]),
    )
    if include_coord_system:
        return sig + (repr(sx.coord_system),)
    return sig


# ---------------------------------------------------------------------------
# cartopy CRS 变换 + 规则网格插值（原 cartopy_cube_regrid）
# ---------------------------------------------------------------------------


def fill_value_for_extrapolation(extrapolation_mode: str):
    mode = (extrapolation_mode or "nanmask").strip().lower()
    if mode in ("nanmask", "mask", "nan"):
        return np.nan
    return np.nan


def _ensure_increasing(points: np.ndarray, field: np.ndarray, axis: int):
    pts = np.asarray(points, dtype=np.float64)
    if pts.size < 2 or pts[0] <= pts[-1]:
        return pts, field
    return pts[::-1].copy(), np.flip(field, axis=axis)


def interp_regular_2d(
    field_yx: np.ndarray,
    src_y: np.ndarray,
    src_x: np.ndarray,
    query_y: np.ndarray,
    query_x: np.ndarray,
    regrid_mode: str = "bilinear",
    fill_value=np.nan,
) -> np.ndarray:
    """在规则源网格 (y, x) 上插值到查询点。"""
    data = np.ma.filled(np.ma.asarray(field_yx), np.nan).astype(np.float64, copy=False)
    sy, data = _ensure_increasing(src_y, data, axis=0)
    sx, data = _ensure_increasing(src_x, data, axis=1)
    method = "linear" if regrid_mode == "bilinear" else "nearest"
    if method not in ("linear", "nearest"):
        raise ValueError("Unrecognised regrid mode {}".format(regrid_mode))
    interpolator = RegularGridInterpolator(
        (sy, sx),
        data,
        method=method,
        bounds_error=False,
        fill_value=fill_value,
    )
    pts = np.column_stack(
        [
            np.asarray(query_y, dtype=np.float64).ravel(),
            np.asarray(query_x, dtype=np.float64).ravel(),
        ]
    )
    out = interpolator(pts).reshape(np.asarray(query_y).shape)
    return out.astype(FLOAT_DTYPE, copy=False)


def target_query_in_source_crs(
    source_cube: Cube,
    target_x: DimCoord,
    target_y: DimCoord,
) -> Tuple[np.ndarray, np.ndarray]:
    """将目标格点变换到源 Cube CRS，返回与目标网格同形的 ``(qy, qx)``。"""
    src_x = source_cube.coord(axis="x")
    src_y = source_cube.coord(axis="y")
    if src_x.coord_system is None or target_x.coord_system is None:
        raise ValueError("source/target 空间坐标均需带 coord_system，以便 cartopy 投影变换")
    src_crs = src_x.coord_system.as_cartopy_crs()
    tgt_crs = target_x.coord_system.as_cartopy_crs()

    tx, ty = np.meshgrid(
        np.asarray(target_x.points, dtype=np.float64),
        np.asarray(target_y.points, dtype=np.float64),
    )
    transformed = src_crs.transform_points(tgt_crs, tx.ravel(), ty.ravel())
    qx = transformed[:, 0].reshape(tx.shape)
    qy = transformed[:, 1].reshape(ty.shape)
    return qy, qx


def build_target_cube_shell(
    source_cube: Cube,
    target_x: DimCoord,
    target_y: DimCoord,
) -> Cube:
    """按源 Cube 元数据搭目标壳（空间维换成 target_x/y）。"""
    yname = source_cube.coord(axis="y").name()
    xname = source_cube.coord(axis="x").name()
    y_dim = source_cube.coord_dims(yname)
    x_dim = source_cube.coord_dims(xname)

    shape = list(source_cube.data.shape)
    if x_dim:
        shape[x_dim[0]] = target_x.shape[0]
    if y_dim:
        shape[y_dim[0]] = target_y.shape[0]
    data = np.zeros(shape, dtype=FLOAT_DTYPE)

    metadata_dict = deepcopy(source_cube.metadata._asdict())
    new_cube = Cube(data, **metadata_dict)

    for coord in source_cube.coords():
        if coord.name() in (yname, xname):
            continue
        if source_cube.coords(coord, dim_coords=True):
            new_cube.add_dim_coord(coord, source_cube.coord_dims(coord))
        else:
            new_cube.add_aux_coord(coord, source_cube.coord_dims(coord) or None)

    if x_dim:
        new_cube.add_dim_coord(target_x, x_dim)
    else:
        new_cube.add_aux_coord(target_x)
    if y_dim:
        new_cube.add_dim_coord(target_y, y_dim)
    else:
        new_cube.add_aux_coord(target_y)
    return new_cube


def regrid_cube_cartopy(
    source_cube: Cube,
    target_x: DimCoord,
    target_y: DimCoord,
    regrid_mode: str = "bilinear",
    extrapolation_mode: str = "nanmask",
    query_yx: Optional[Tuple[np.ndarray, np.ndarray]] = None,
) -> Cube:
    """
    cartopy 投影变换 + 规则网格插值，把 ``source_cube`` 重采样到 ``target_x/y``。

    Args:
        query_yx: 可选缓存的 ``(qy, qx)``；省略则现场计算。
    """
    if regrid_mode not in ("bilinear", "nearest"):
        raise ValueError("Unrecognised regrid mode {}".format(regrid_mode))

    src_x = source_cube.coord(axis="x")
    src_y = source_cube.coord(axis="y")
    y_dim = source_cube.coord_dims(src_y)[0]
    x_dim = source_cube.coord_dims(src_x)[0]

    if query_yx is None:
        qy, qx = target_query_in_source_crs(source_cube, target_x, target_y)
    else:
        qy, qx = query_yx

    fill = fill_value_for_extrapolation(extrapolation_mode)
    new_cube = build_target_cube_shell(source_cube, target_x, target_y)

    src_data = np.ma.filled(np.ma.asarray(source_cube.data), np.nan)
    data_yx = np.moveaxis(src_data, (y_dim, x_dim), (-2, -1))
    flat = data_yx.reshape(-1, data_yx.shape[-2], data_yx.shape[-1])
    out_flat = np.empty((flat.shape[0], qy.shape[0], qy.shape[1]), dtype=FLOAT_DTYPE)
    for i in range(flat.shape[0]):
        out_flat[i] = interp_regular_2d(
            flat[i],
            src_y.points,
            src_x.points,
            qy,
            qx,
            regrid_mode=regrid_mode,
            fill_value=fill,
        )
    out_yx = out_flat.reshape(data_yx.shape[:-2] + qy.shape)
    out = np.moveaxis(out_yx, (-2, -1), (y_dim, x_dim))
    new_cube.data = out.astype(FLOAT_DTYPE, copy=False)
    return new_cube
