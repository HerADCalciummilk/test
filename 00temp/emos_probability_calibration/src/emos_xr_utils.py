"""xarray DataArray 辅助工具（维度常量、坐标、概率/ECC 相关）。"""

from __future__ import annotations

from collections import namedtuple
from copy import deepcopy
from datetime import datetime
import re
import warnings
from typing import Any, Dict, List, Match, Optional, Sequence, Union

import numpy as np
import xarray as xr
from numpy import ndarray
from numpy.ma.core import MaskedArray

# --- constants ---

ABSOLUTE_ZERO = -273.15

# bounds_for_ecdf 字典使用的 namedtuple
Bounds = namedtuple("bounds", "value units")

# 构建 ECDF 时，各诊断量的分布端点（气候学上下界的近似值）。
# 除降水率使用 mm/h 外，其余均采用 SI 单位。
BOUNDS_FOR_ECDF = {
    # 云
    "cloud_area_fraction": Bounds((0, 1.0), "1"),
    "cloud_area_fraction_assuming_only_consider_surface_to_1000_feet_asl": Bounds(
        (0, 1.0), "1"
    ),
    "cloud_base_height_assuming_only_consider_cloud_area_fraction_greater_than_2p5_oktas": Bounds(
        (-4000, 20000), "m"
    ),
    "cloud_base_height_assuming_only_consider_cloud_area_fraction_greater_than_4p5_oktas": Bounds(
        (-4000, 20000), "m"
    ),
    "high_type_cloud_area_fraction": Bounds((0, 1.0), "1"),
    "low_and_medium_type_cloud_area_fraction": Bounds((0, 1.0), "1"),
    "low_type_cloud_area_fraction": Bounds((0, 1.0), "1"),
    "medium_type_cloud_area_fraction": Bounds((0, 1.0), "1"),
    # 降水量
    "lwe_thickness_of_freezing_rainfall_amount": Bounds((0, 0.5), "m"),
    "lwe_thickness_of_graupel_and_hail_fall_amount": Bounds((0, 0.5), "m"),
    "lwe_thickness_of_precipitation_amount": Bounds((0, 0.5), "m"),
    "lwe_thickness_of_precipitation_amount_in_vicinity": Bounds((0, 0.5), "m"),
    "lwe_thickness_of_precipitation_amount_in_variable_vicinity": Bounds((0, 0.5), "m"),
    "lwe_thickness_of_sleetfall_amount": Bounds((0, 0.5), "m"),
    "lwe_thickness_of_snowfall_amount": Bounds((0, 0.5), "m"),
    "thickness_of_rainfall_amount": Bounds((0, 0.5), "m"),
    # 降水率
    "lwe_precipitation_rate": Bounds((0, 400.0), "mm h-1"),
    "lwe_precipitation_rate_in_vicinity": Bounds((0, 400.0), "mm h-1"),
    "lwe_precipitation_rate_max": Bounds((0, 400.0), "mm h-1"),
    "lwe_sleetfall_rate": Bounds((0, 400.0), "mm h-1"),
    "lwe_snowfall_rate": Bounds((0, 400.0), "mm h-1"),
    "lwe_snowfall_rate_in_vicinity": Bounds((0, 400.0), "mm h-1"),
    "rainfall_rate": Bounds((0, 400.0), "mm h-1"),
    "rainfall_rate_in_vicinity": Bounds((0, 400.0), "mm h-1"),
    # 降水时间占比
    "fraction_of_time_classified_as_wet": Bounds((0, 1.0), "1"),
    # 温度
    "air_temperature": (Bounds((-100 - ABSOLUTE_ZERO, 60 - ABSOLUTE_ZERO), "Kelvin")),
    "feels_like_temperature": (
        Bounds((-100 - ABSOLUTE_ZERO, 60 - ABSOLUTE_ZERO), "Kelvin")
    ),
    "temperature_at_screen_level_daytime_max": (
        Bounds((-100 - ABSOLUTE_ZERO, 60 - ABSOLUTE_ZERO), "Kelvin")
    ),
    "temperature_at_screen_level_nighttime_min": Bounds(
        (-100 - ABSOLUTE_ZERO, 60 - ABSOLUTE_ZERO), "Kelvin"
    ),
    # 风
    "wind_speed": Bounds((0, 50), "m s^-1"),
    "wind_speed_of_gust": Bounds((0, 200), "m s^-1"),
    # 其他
    "air_pressure_at_sea_level": Bounds((79600, 108000), "Pa"),
    "dew_point_temperature": Bounds(
        (-100 - ABSOLUTE_ZERO, 60 - ABSOLUTE_ZERO), "Kelvin"
    ),
    "relative_humidity": Bounds((0, 1.2), "1"),
    "visibility_in_air": Bounds((0, 100000), "m"),
    "visibility_in_air_in_vicinity": Bounds((0, 100000), "m"),
    "ultraviolet_index": Bounds((0, 25.0), "1"),
    "ultraviolet_index_daytime_max": Bounds((0, 25.0), "1"),
}
# --- xarray_core ---

import numpy as np
import xarray as xr
from numpy import ndarray
from numpy.ma.core import MaskedArray

MANDATORY_ATTRIBUTE_DEFAULTS = {
    "title": "unknown",
    "source": "IMPROVER",
    "institution": "unknown",
}

MANDATORY_ATTRIBUTES = [x for x in MANDATORY_ATTRIBUTE_DEFAULTS.keys()]

SPOT_DIM = "spot_index"
LAT_DIM = "lat"
LON_DIM = "lon"
REALIZATION_DIM = "realization"
TIME_DIM = "time"


class CoordinateNotFoundError(KeyError):
    """当缺少预期坐标时抛出。"""


def as_dataarray(
    obj: Union[xr.DataArray, xr.Dataset],
    var_name: Optional[str] = None,
) -> xr.DataArray:
    """从 Dataset 中提取单个诊断 DataArray，或直接返回 DataArray。"""
    if isinstance(obj, xr.DataArray):
        return obj
    if not isinstance(obj, xr.Dataset):
        raise TypeError(f"Expected DataArray or Dataset, got {type(obj)}")
    if var_name is not None:
        if var_name not in obj.data_vars:
            raise KeyError(f"Variable {var_name!r} not in dataset")
        return obj[var_name]
    if len(obj.data_vars) == 1:
        return next(iter(obj.data_vars.values()))
    for name, da in obj.data_vars.items():
        if da.attrs.get("standard_name"):
            return da
    raise ValueError(
        "Dataset has multiple data variables; specify var_name or use a "
        f"single-variable dataset. Variables: {list(obj.data_vars)}"
    )


def as_dataset(obj: Union[xr.DataArray, xr.Dataset]) -> xr.Dataset:
    """将 DataArray 包装为单变量 Dataset，或原样返回 Dataset。"""
    if isinstance(obj, xr.Dataset):
        return obj
    if isinstance(obj, xr.DataArray):
        if obj.name is None:
            name = obj.attrs.get("standard_name", "unknown")
            return obj.to_dataset(name=name)
        return obj.to_dataset()
    raise TypeError(f"Expected DataArray or Dataset, got {type(obj)}")


def get_diagnostic_name(da: xr.DataArray) -> str:
    """返回 standard_name、long_name 或变量名。"""
    if da.attrs.get("standard_name"):
        return da.attrs["standard_name"]
    if da.attrs.get("long_name"):
        return da.attrs["long_name"]
    if da.name:
        return da.name
    return "unknown"


def is_spot_data(da: xr.DataArray) -> bool:
    """若数据以 spot_index 作为维度坐标则为 True。"""
    return SPOT_DIM in da.dims


def is_gridded_data(da: xr.DataArray) -> bool:
    """若数据以 lat/lon 作为维度坐标（IMPROVER 格点风格）则为 True。"""
    return LAT_DIM in da.dims and LON_DIM in da.dims


def has_spatial_points(da: xr.DataArray) -> bool:
    """若数据定义在离散空间点（单点或 lat/lon 格点）上则为 True。"""
    return is_spot_data(da) or is_gridded_data(da)


def stack_lat_lon_to_spot(
    da: xr.DataArray,
    lat_dim: str = LAT_DIM,
    lon_dim: str = LON_DIM,
) -> xr.DataArray:
    """将 (lat, lon) 替换为整数 spot_index，并保留辅助 lat/lon 坐标。"""
    if SPOT_DIM in da.dims:
        return da
    if lat_dim not in da.dims or lon_dim not in da.dims:
        raise ValueError(f"Expected dimensions {lat_dim!r} and {lon_dim!r}")
    lat = da[lat_dim].values
    lon = da[lon_dim].values
    n_lat, n_lon = len(lat), len(lon)
    other_dims = [d for d in da.dims if d not in (lat_dim, lon_dim)]
    da_ordered = da.transpose(*other_dims, lat_dim, lon_dim)
    shape = [da_ordered.sizes[d] for d in other_dims] + [n_lat * n_lon]
    data = da_ordered.values.reshape(shape)
    spot_index = np.arange(n_lat * n_lon, dtype=np.int32)
    lat_on_spot = np.repeat(lat, n_lon)
    lon_on_spot = np.tile(lon, n_lat)
    coords = {d: da.coords[d] for d in other_dims}
    coords[SPOT_DIM] = (SPOT_DIM, spot_index)
    coords[lat_dim] = (SPOT_DIM, lat_on_spot.astype(np.float32))
    coords[lon_dim] = (SPOT_DIM, lon_on_spot.astype(np.float32))
    return xr.DataArray(
        data,
        dims=other_dims + [SPOT_DIM],
        coords=coords,
        attrs=da.attrs.copy(),
        name=da.name,
    )


def unstack_spot_to_lat_lon(
    da: xr.DataArray,
    lat: np.ndarray,
    lon: np.ndarray,
    lat_dim: str = LAT_DIM,
    lon_dim: str = LON_DIM,
) -> xr.DataArray:
    """从 spot_index 恢复 (lat, lon) 维度。"""
    if SPOT_DIM not in da.dims:
        return da
    n_lat, n_lon = len(lat), len(lon)
    other_dims = [d for d in da.dims if d != SPOT_DIM]
    shape = [da.sizes[d] for d in other_dims] + [n_lat, n_lon]
    data = da.values.reshape(shape)
    coords = {
        d: da.coords[d]
        for d in other_dims
        if d not in (lat_dim, lon_dim)
    }
    coords[lat_dim] = lat.astype(np.float32)
    coords[lon_dim] = lon.astype(np.float32)
    drop_coords = [
        c for c in (lat_dim, lon_dim) if c in da.coords and c not in coords
    ]
    out = xr.DataArray(
        data,
        dims=other_dims + [lat_dim, lon_dim],
        coords=coords,
        attrs=da.attrs.copy(),
        name=da.name,
    )
    return out.drop_vars(drop_coords, errors="ignore")


def ensure_spatial_spot_index(da: xr.DataArray) -> xr.DataArray:
    """将单点数据规范为使用 spot_index（格点 lat/lon 保持不变）。"""
    if is_spot_data(da) or is_gridded_data(da):
        return da
    return da


def spatial_point_count(da: xr.DataArray) -> int:
    """spot_index 或 lat/lon 格点顺序下的空间点数量。"""
    if SPOT_DIM in da.dims:
        return da.sizes[SPOT_DIM]
    if is_gridded_data(da):
        return da.sizes[LAT_DIM] * da.sizes[LON_DIM]
    return 0


def iter_spatial_selections(da: xr.DataArray):
    """
    按 IMPROVER 顺序为每个空间点生成选择字典。

    格点数据按纬度 (y) 再经度 (x) 迭代，与 Iris ``slices_over([y, x])`` 一致。
    """
    if SPOT_DIM in da.dims:
        for spot in da[SPOT_DIM].values:
            yield {SPOT_DIM: spot}
    elif is_gridded_data(da):
        for lat in da[LAT_DIM].values:
            for lon in da[LON_DIM].values:
                yield {LAT_DIM: lat, LON_DIM: lon}


def reshape_pointwise_coefficients(
    optimised_coeffs: list,
    template: xr.DataArray,
) -> np.ndarray:
    """将逐点系数重塑为与 IMPROVER 空间布局一致。"""
    transposed = np.transpose(np.array(optimised_coeffs))
    n_coeff = transposed.shape[0]
    if SPOT_DIM in template.dims:
        return transposed.reshape(n_coeff, template.sizes[SPOT_DIM])
    if is_gridded_data(template):
        return transposed.reshape(
            n_coeff, template.sizes[LAT_DIM], template.sizes[LON_DIM]
        )
    return transposed


def ensure_spatial_coefficients(ds: xr.Dataset) -> xr.Dataset:
    """原样返回系数（IMPROVER 使用原生空间维度）。"""
    return ds


def has_coord(da: xr.DataArray, name: str) -> bool:
    """检查坐标或维度名是否存在于 DataArray 中。"""
    return name in da.coords or name in da.dims


def dim_names(da: xr.DataArray) -> List[str]:
    """返回 DataArray 的维度名列表。"""
    return list(da.dims)


def enforce_coordinate_ordering(
    da: xr.DataArray,
    coord_names: Union[List[str], str],
    anchor_start: bool = True,
) -> xr.DataArray:
    """重排维度，使指定坐标出现在最前（或最后）。"""
    if isinstance(coord_names, str):
        coord_names = [coord_names]
    present = [c for c in coord_names if c in da.dims]
    if not present:
        return da
    other = [d for d in da.dims if d not in present]
    new_order = present + other if anchor_start else other + present
    return da.transpose(*new_order)


def collapsed(
    da: xr.DataArray,
    dim: Union[str, Sequence[str]],
    how: str,
) -> xr.DataArray:
    """沿维度求均值或方差（仅用于单点 EMOS）。"""
    if isinstance(dim, str):
        dim = [dim]
    if how == "mean":
        return da.mean(dim=dim, keep_attrs=True)
    if how == "var":
        # Iris iris.analysis.VARIANCE 默认使用 ddof=1。
        return da.var(dim=dim, ddof=1, keep_attrs=True)
    raise ValueError(f"Unsupported collapse method: {how}")


def convert_data_to_2d(
    da: xr.DataArray,
    coord: str = REALIZATION_DIM,
    transpose: bool = True,
) -> ndarray:
    """重塑数据，使 *coord* 为第二维（transpose=False 时为第一维）。"""
    data = da.values
    if np.ma.is_masked(data):
        data = np.ma.filled(data, np.nan)
    if coord not in da.dims:
        flat = data.flatten()
        result = flat.reshape(-1, 1) if transpose else flat.reshape(1, -1)
        return np.array(result)

    da_ord = enforce_coordinate_ordering(da, coord)
    other_dims = [d for d in da_ord.dims if d != coord]
    stacked = da_ord.transpose(coord, *other_dims)
    forecast_data = stacked.values.reshape(stacked.sizes[coord], -1)
    if transpose:
        forecast_data = forecast_data.T
    return np.array(forecast_data)


def time_coord_to_datetime(
    da: xr.DataArray,
    coord_name: str = TIME_DIM,
    point_or_bound: str = "point",
) -> List:
    """将 xarray 时间坐标转换为 Python datetime。"""
    if coord_name not in da.coords:
        raise CoordinateNotFoundError(coord_name)
    coord = da[coord_name]
    values = coord.values
    if point_or_bound == "point":
        return [np.datetime_as_string(v, unit="s").astype("datetime64[s]").astype(object)
                if not isinstance(v, datetime) else v
                for v in np.atleast_1d(values)]
    # 当前样例数据未使用 bounds；需要时可扩展
    raise NotImplementedError("time bounds matching not implemented for xarray path")


def _numpy_datetime_to_py(dt) -> datetime:
    """将 numpy 时间类型转换为 Python datetime。"""
    if isinstance(dt, datetime):
        return dt
    return pd_timestamp_to_datetime(dt)


def pd_timestamp_to_datetime(dt) -> datetime:
    """将 pandas Timestamp 或兼容值转换为 Python datetime。"""
    import pandas as pd

    return pd.Timestamp(dt).to_pydatetime()


def time_value_to_datetime(value, units: Optional[str] = None) -> datetime:
    """
    将标量时间坐标值转换为 ``datetime``。

    与 Iris/IMPROVER 对数值历元坐标（自 1970-01-01 起的秒数）的行为一致，
    避免将小整数误当作纳秒处理。
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, np.datetime64):
        return pd_timestamp_to_datetime(value)
    if isinstance(value, (int, np.integer, float, np.floating)):
        numeric = int(value)
        if units:
            unit_lower = units.lower()
            if "second" in unit_lower:
                import pandas as pd

                return pd.Timestamp(numeric, unit="s").to_pydatetime()
            if "minute" in unit_lower:
                import pandas as pd

                return pd.Timestamp(numeric, unit="m").to_pydatetime()
            if "hour" in unit_lower:
                import pandas as pd

                return pd.Timestamp(numeric, unit="h").to_pydatetime()
            if "day" in unit_lower:
                import pandas as pd

                return pd.Timestamp(numeric, unit="D").to_pydatetime()
        if 0 <= numeric < 10**10:
            import pandas as pd

            return pd.Timestamp(numeric, unit="s").to_pydatetime()
    return pd_timestamp_to_datetime(value)


def get_frt_hours(da: xr.DataArray) -> set:
    """返回 forecast_reference_time 坐标的小时分量集合。"""
    if "forecast_reference_time" not in da.coords:
        raise CoordinateNotFoundError("forecast_reference_time")
    frt = da["forecast_reference_time"]
    hours = set()
    for v in np.atleast_1d(frt.values):
        t = time_value_to_datetime(v, frt.attrs.get("units"))
        hours.add(int(t.hour))
    return hours


def create_unified_frt_coord(da: xr.DataArray) -> Dict[str, Any]:
    """为系数输出构建标量 forecast_reference_time 元数据。"""
    frt = da["forecast_reference_time"]
    points = np.atleast_1d(frt.values)
    frt_point = np.max(points)
    frt_bounds_min = np.min(points)
    frt_bounds_max = frt_point
    return {
        "forecast_reference_time": frt_point,
        "forecast_reference_time_bounds": (frt_bounds_min, frt_bounds_max),
    }


def generate_mandatory_attributes(
    diagnostic_arrays: List[xr.DataArray],
    model_id_attr: Optional[str] = None,
) -> Dict[str, str]:
    """从输入诊断数据合并必选属性。"""
    missing_value = object()
    attr_dicts = [da.attrs for da in diagnostic_arrays]
    required_attributes = [model_id_attr] if model_id_attr else []
    attributes = MANDATORY_ATTRIBUTE_DEFAULTS.copy()
    for attr in MANDATORY_ATTRIBUTES + required_attributes:
        unique_values = {d.get(attr, missing_value) for d in attr_dicts}
        if len(unique_values) == 1 and missing_value not in unique_values:
            (attributes[attr],) = unique_values
        elif attr in required_attributes:
            raise ValueError(
                f'Required attribute "{attr}" is missing or not the same on all inputs'
            )
    return attributes


def create_new_diagnostic_dataarray(
    name: str,
    units: str,
    template: xr.DataArray,
    mandatory_attributes: Dict[str, str],
    optional_attributes: Optional[Dict[str, Any]] = None,
    data: Optional[Union[MaskedArray, ndarray]] = None,
    dtype: type = np.float32,
) -> xr.DataArray:
    """从模板复制坐标/属性以创建输出 DataArray。"""
    attributes = dict(mandatory_attributes)
    if optional_attributes:
        attributes.update(optional_attributes)
    for attr in MANDATORY_ATTRIBUTES:
        if attr not in attributes:
            raise ValueError(f"{attr} attribute is required")

    drop = [REALIZATION_DIM, "percentile"]
    coords = {
        k: v
        for k, v in template.coords.items()
        if k not in drop and (k in template.dims or k not in template.dims)
    }
    # 保留其维度仍存在的非维度坐标
    dims = list(template.dims)
    for d in drop:
        if d in dims:
            dims.remove(d)

    if data is None:
        shape = tuple(template.sizes[d] for d in dims) if dims else ()
        data = np.zeros(shape, dtype=dtype)
    else:
        data = np.asarray(data, dtype=dtype)

    da = xr.DataArray(
        data,
        dims=dims,
        coords={k: v for k, v in coords.items() if k in dims or k not in dims},
        attrs={**template.attrs, **attributes, "units": units},
        name=name,
    )
    if "standard_name" in attributes:
        da.attrs["standard_name"] = attributes["standard_name"]
    elif name not in ("location_parameter", "scale_parameter") and not name.startswith(
        "emos_coefficient"
    ):
        da.attrs["standard_name"] = name
    return da


def extract_coefficient(ds: xr.Dataset, coeff_name: str) -> xr.DataArray:
    """从系数 Dataset 中获取单个 EMOS 系数变量。"""
    if coeff_name in ds.data_vars:
        return ds[coeff_name]
    prefixed = f"emos_coefficient_{coeff_name.replace('emos_coefficient_', '')}"
    if prefixed in ds.data_vars:
        return ds[prefixed]
    raise KeyError(f"Coefficient {coeff_name!r} not found in dataset")


def get_dataset_attribute(ds: xr.Dataset, name: str, optional: bool = False) -> Any:
    """从 Dataset 或系数变量一致地读取属性。"""
    values = []
    for var in ds.data_vars:
        if name in ds[var].attrs:
            values.append(str(ds[var].attrs[name]))
    if name in ds.attrs:
        values.append(str(ds.attrs[name]))
    if not values and optional:
        return None
    if not values:
        raise AttributeError(f"The {name} attribute must be specified on coefficients.")
    if len(set(values)) == 1:
        raw = values[0]
        if name == "shape_parameters":
            return np.array(eval(raw)) if raw.startswith("[") else ds[list(ds.data_vars)[0]].attrs[name]
        return ds[list(ds.data_vars)[0]].attrs.get(name, raw)
    raise AttributeError(f"Coefficients must share the same {name} attribute: {values}")


def mask_dataarray(da: xr.DataArray, landsea_mask: xr.DataArray) -> xr.DataArray:
    """用 NaN 掩膜海洋点（陆地=1，海洋=0）。"""
    mask_da = as_dataarray(landsea_mask)
    land = mask_da.values.astype(bool)
    data = da.values.copy()
    try:
        data[..., ~land] = np.nan
    except IndexError as err:
        raise IndexError(
            f"DataArray and landsea_mask shapes are not compatible. {err}"
        ) from err
    return da.copy(data=np.ma.masked_invalid(data))


def merge_land_and_sea(
    calibrated_land_only: xr.DataArray,
    uncalibrated: xr.DataArray,
) -> None:
    """从非校准数据填充校准输出中被掩膜的海洋点（原地修改）。"""
    cal = as_dataarray(calibrated_land_only)
    unc = as_dataarray(uncalibrated)
    if cal.dims != unc.dims:
        raise ValueError("Input arrays do not have the same dimension names")
    if np.ma.is_masked(cal.values):
        new_data = cal.values.data.copy()
        mask = cal.values.mask
        new_data[mask] = unc.values[mask]
        calibrated_land_only.values[:] = new_data


def merge_coords_from_template(
    result: xr.DataArray, template: xr.DataArray, prob_dim: Optional[str] = None
) -> xr.DataArray:
    """将模板中的非概率坐标复制到结果上。"""
    drop = {REALIZATION_DIM, "percentile", prob_dim} - {None}
    for c in template.coords:
        if c in drop or c in result.coords:
            continue
        if c in template.dims and c not in result.dims:
            continue
        result = result.assign_coords({c: template[c]})
    result.attrs = {**template.attrs, **result.attrs}
    return result


def to_output_dataset(da: xr.DataArray) -> xr.Dataset:
    """将单变量结果返回为 Dataset。"""
    return as_dataset(da)


def copy_dataset_attrs(source: xr.Dataset, target: xr.Dataset) -> xr.Dataset:
    """将源 Dataset 的全局属性深拷贝到目标 Dataset。"""
    target.attrs = deepcopy(source.attrs)
    return target
# --- xarray_utilities ---

import numpy as np
import xarray as xr
from numpy import ndarray


ABSOLUTE_ZERO = -273.15


def concatenate_2d_array_with_2d_array_endpoints(
    array_2d: ndarray, low_endpoint: float, high_endpoint: float
) -> ndarray:
    """在二维数组两端各追加一列低/高端点值。"""
    if array_2d.ndim != 2:
        raise ValueError(f"Expected 2D input, got {array_2d.ndim}D input")
    lower_array = np.full((array_2d.shape[0], 1), low_endpoint, dtype=array_2d.dtype)
    upper_array = np.full((array_2d.shape[0], 1), high_endpoint, dtype=array_2d.dtype)
    return np.concatenate((lower_array, array_2d, upper_array), axis=1)


def choose_set_of_percentiles(no_of_percentiles: int, sampling: str = "quantile") -> List[float]:
    """选取指定数量的百分位值（0–100 尺度）。"""
    if sampling in ["quantile"]:
        percentiles = np.linspace(
            1 / float(1 + no_of_percentiles),
            no_of_percentiles / float(1 + no_of_percentiles),
            no_of_percentiles,
        ).tolist()
    elif sampling in ["random"]:
        percentiles = sorted(
            list(
                np.random.uniform(
                    1 / float(1 + no_of_percentiles),
                    no_of_percentiles / float(1 + no_of_percentiles),
                    no_of_percentiles,
                )
            )
        )
    else:
        raise ValueError(f"Unrecognised sampling option '{sampling}'")
    return [item * 100 for item in percentiles]


def create_dataarray_with_percentiles(
    percentiles: Union[List[float], ndarray],
    template: xr.DataArray,
    cube_data: ndarray,
    units: Optional[str] = None,
) -> xr.DataArray:
    """构建以百分位为前导维度的 DataArray。"""
    template = template.drop_vars(
        [v for v in (template.name,) if v and v in template.coords],
        errors="ignore",
    )
    for d in ("realization", "percentile"):
        if d in template.dims:
            template = template.isel({d: 0}, drop=True)

    coords = dict(template.coords)
    dims = ["percentile"] + list(template.dims)
    coords["percentile"] = ("percentile", np.asarray(percentiles, dtype=np.float32))
    # print(percentiles)
    attrs = dict(template.attrs)
    if units:
        attrs["units"] = units
    da = xr.DataArray(
        cube_data.astype(np.float32),
        dims=dims,
        coords={k: v for k, v in coords.items() if k in dims},
        attrs=attrs,
        name=template.name or template.attrs.get("standard_name"),
    )
    for k, v in coords.items():
        if (k not in dims) and (getattr(v, "ndim", 0) == 0):
            da.coords[k] = v
    return da


def get_bounds_of_distribution(bounds_pairing_key: str, desired_units: str) -> ndarray:
    """返回指定诊断在 ECDF 中使用的分布上下界。"""
    try:
        bounds_pairing = BOUNDS_FOR_ECDF[bounds_pairing_key].value
    except KeyError as err:
        raise KeyError(
            f"The bounds_pairing_key: {bounds_pairing_key} is not recognised "
            f"within BOUNDS_FOR_ECDF."
        ) from err
    # 无 cf_units/pint 时：假定边界已在目标诊断单位中。
    return np.array(bounds_pairing, dtype=np.float32)


def insert_lower_and_upper_endpoint_to_1d_array(
    array_1d: ndarray, low_endpoint: float, high_endpoint: float
) -> ndarray:
    """在一维数组首尾插入低/高端点。"""
    if array_1d.ndim != 1:
        raise ValueError(f"Expected 1D input, got {array_1d.ndim}D input")
    array_1d = np.concatenate(([low_endpoint], array_1d, [high_endpoint]))
    if array_1d.dtype == np.float64:
        array_1d = array_1d.astype(np.float32)
    return array_1d


def restore_non_percentile_dimensions(
    array_to_reshape: ndarray, template: xr.DataArray, n_percentiles: int
) -> ndarray:
    """将插值结果重塑为含百分位维度的数组形状。"""
    shape = [n_percentiles] + [template.sizes[d] for d in template.dims] if n_percentiles > 1 else list(template.sizes[d] for d in template.dims)
    if n_percentiles <= 1:
        shape = list(template.sizes[d] for d in template.dims)
    else:
        shape = [n_percentiles] + [template.sizes[d] for d in template.dims]
    return array_to_reshape.reshape(shape)


def slow_interp_same_x(x: np.ndarray, xp: np.ndarray, fp: np.ndarray) -> np.ndarray:
    result = np.empty((fp.shape[0], len(x)), np.float32)
    for i in range(fp.shape[0]):
        result[i, :] = np.interp(x, xp, fp[i, :])
    return result


def interpolate_multiple_rows_same_x(*args):
    """沿固定 x 对多行数据插值（优先使用 numba 加速）。"""
    try:
        import numba  # noqa: F401
        from ensemble_copula_coupling.numba_utilities import fast_interp_same_x

        return fast_interp_same_x(*args)
    except ImportError:
        warnings.warn("Module numba unavailable. ResamplePercentiles will be slower.")
        return slow_interp_same_x(*args)


def slow_interp_same_y(x: np.ndarray, xp: np.ndarray, fp: np.ndarray) -> np.ndarray:
    result = np.empty((xp.shape[0], len(x)), dtype=np.float32)
    for i in range(xp.shape[0]):
        result[i] = np.interp(x, xp[i, :], fp)
    return result


def interpolate_multiple_rows_same_y(*args):
    """沿固定 y 对多行数据插值（优先使用 numba 加速）。"""
    try:
        import numba  # noqa: F401
        from ensemble_copula_coupling.numba_utilities import fast_interp_same_x as _  # noqa
        from ensemble_copula_coupling.numba_utilities import fast_interp_same_y

        return fast_interp_same_y(*args)
    except ImportError:
        warnings.warn(
            "Module numba unavailable. ConvertProbabilitiesToPercentiles will be slower."
        )
        return slow_interp_same_y(*args)


def choose(index_array: ndarray, array_set: ndarray) -> ndarray:
    """沿前导维度重排（来自 indexing_operations.choose）。"""
    if index_array.shape != array_set.shape:
        raise ValueError(
            f"index_array shape {index_array.shape} != array_set shape {array_set.shape}"
        )
    if index_array.max() > array_set.shape[0] - 1:
        raise IndexError(
            f"index max {index_array.max()} exceeds sub-array count {array_set.shape[0]}"
        )
    result = np.array(
        [array_set[index_array[i]][i[1:]] for i in np.ndindex(index_array.shape)]
    ).reshape(index_array.shape)
    return result


def manipulate_n_realizations(da: xr.DataArray, n_realizations: int) -> xr.DataArray:
    """将 realization 维扩展或截断到指定成员数（循环复用）。"""
    if "realization" not in da.dims:
        raise ValueError("Input must contain a realization dimension")
    mpoints = da["realization"].values
    if len(mpoints) == n_realizations:
        return da.copy()
    realization_list = [mpoints[i % len(mpoints)] for i in range(n_realizations)]
    new_numbers = realization_list[0] + np.arange(n_realizations)
    slices = [da.sel(realization=r) for r in realization_list]
    out = xr.concat(slices, dim="realization")
    return out.assign_coords(realization=new_numbers.astype(np.int32))
# --- xarray_probabilistic ---

import xarray as xr



def probability_cube_name_regex(cube_name: str) -> Optional[Match]:
    """匹配概率立方体 standard_name 的正则表达式。"""
    regex = re.compile(
        "(probability_of_)"
        "(?P<diag>.*?)"
        "(?P<vicinity>_in_vicinity|_in_variable_vicinity)?"
        "(?P<thresh>_above_threshold|_below_threshold|_between_thresholds|$)"
    )
    return regex.match(cube_name)


def find_percentile_coordinate(da: xr.DataArray) -> str:
    """返回百分位坐标名称。"""
    da = as_dataarray(da)
    name = get_diagnostic_name(da)
    found = []
    for c in da.coords:
        if "percentile" in c:
            found.append(c)
    if not found:
        raise CoordinateNotFoundError(f"No percentile coord found on {name} data")
    if len(found) > 1:
        raise ValueError(f"Too many percentile coords found on {name} data")
    return found[0]


def find_threshold_coordinate(da: xr.DataArray) -> str:
    """返回阈值坐标名称。"""
    da = as_dataarray(da)
    name = get_diagnostic_name(da)
    if "threshold" in da.coords:
        return "threshold"
    for c in da.coords:
        if da[c].attrs.get("var_name") == "threshold":
            return c
    raise CoordinateNotFoundError(f"No threshold coord found on {name} data")


def get_threshold_coord_name_from_probability_name(cube_name: str) -> str:
    """从概率立方体名称解析底层诊断（阈值）变量名。"""
    regex = probability_cube_name_regex(cube_name)
    return regex.groupdict()["diag"]


def get_diagnostic_cube_name_from_probability_name(cube_name: str) -> str:
    """从概率立方体名称解析对应诊断立方体名称。"""
    regex = probability_cube_name_regex(cube_name)
    gd = regex.groupdict()
    diag = gd["diag"]
    if gd.get("vicinity"):
        diag += gd["vicinity"]
    return diag


def probability_is_above_or_below(da: xr.DataArray) -> str:
    """判断概率相对于阈值为 above 还是 below。"""
    da = as_dataarray(da)
    thresh = find_threshold_coordinate(da)
    relation = da[thresh].attrs.get("spp__relative_to_threshold")
    if relation in ("above", "below"):
        return relation
    name = get_diagnostic_name(da)
    if "_above_threshold" in name:
        return "above"
    if "_below_threshold" in name:
        return "below"
    raise NotImplementedError(
        f"Cannot determine threshold relation for {name}"
    )


def get_forecast_type(forecast: Union[xr.DataArray, xr.Dataset]) -> str:
    """返回 'probabilities'、'percentiles' 或 'realizations'。"""
    da = as_dataarray(forecast)
    if "threshold" in da.dims:
        return "probabilities"
    try:
        find_percentile_coordinate(da)
    except CoordinateNotFoundError:
        name = get_diagnostic_name(da)
        if name.startswith("probability_of"):
            return "probabilities"
        return "realizations"
    else:
        return "percentiles"
