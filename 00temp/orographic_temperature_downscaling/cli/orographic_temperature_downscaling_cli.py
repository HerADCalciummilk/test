# -*- coding: utf-8 -*-
"""估计温度层结递减率。

``@merge_params`` 挂在 ``process`` 上。由 ``python -m orographic_temperature_downscaling``
或 ``python -m cli`` 启动。
"""
import os
import sys

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _ROOT_DIR)
if _PARENT not in sys.path:
    sys.path.insert(1, _PARENT)

import numpy as np
import xarray as xr
import meteva_base as meb

from orographic_temperature_downscaling.src.lapse_rate import DALR, LapseRate
from utils.merge_params import merge_params


def _as_lapse_rate_dataarray(values, template):
    result = xr.DataArray(
        values.astype(np.float32, copy=False),
        dims=template.dims,
        coords=template.coords,
        attrs=dict(template.attrs),
        name="air_temperature_lapse_rate",
    )
    result.attrs["units"] = "K m-1"
    return result


def _need(name, value):
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: %s" % name)
    return value


@merge_params()
def process(
    temperature_path: str = None,
    orography_path: str = None,
    land_sea_mask_path: str = None,
    output_path: str = None,
    max_height_diff: float = 35.0,
    nbhood_radius: int = 7,
    max_lapse_rate: float = -3 * DALR,
    min_lapse_rate: float = DALR,
    dry_adiabatic: bool = False,
    config=None,
):
    """读温度（及地形、海陆掩码），调用 ``LapseRate.process``，按需写出。"""
    _ = config
    temperature_path = _need("temperature_path", temperature_path)
    _unbounded = (-np.inf, np.inf, np.nan)
    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_unbounded
    )

    # 干绝热时直接铺满 DALR，不再做邻域回归
    if dry_adiabatic:
        result = np.full_like(
            np.asarray(temperature.values, dtype=np.float32), DALR, dtype=np.float32
        )
        result = _as_lapse_rate_dataarray(result, temperature)
    else:
        if min_lapse_rate > max_lapse_rate:
            raise ValueError("最小层结递减率不能大于最大层结递减率。")
        if max_height_diff < 0:
            raise ValueError("max_height_diff 必须大于等于 0。")
        if nbhood_radius < 0:
            raise ValueError("nbhood_radius 必须大于等于 0。")
        orography_path = _need("orography_path", orography_path)
        land_sea_mask_path = _need("land_sea_mask_path", land_sea_mask_path)
        orography = meb.checkout_griddata(
            meb.read_griddata_from_nc(orography_path), valid_val=_unbounded
        )
        land_sea_mask = meb.checkout_griddata(meb.read_griddata_from_nc(land_sea_mask_path))
        if not meb.checkout_griddata_same_coords([temperature, orography], is_time_match=False):
            raise ValueError("地形高度场与温度场的坐标不一致")
        if not meb.checkout_griddata_same_coords([temperature, land_sea_mask], is_time_match=True):
            raise ValueError("海陆掩码与温度场的空间/时效坐标不一致")
        result = LapseRate(
            max_height_diff=max_height_diff,
            nbhood_radius=nbhood_radius,
            max_lapse_rate=max_lapse_rate,
            min_lapse_rate=min_lapse_rate,
        ).process(temperature, orography, land_sea_mask)
        if isinstance(result, xr.DataArray):
            result = result.copy()
            result.name = "air_temperature_lapse_rate"
            result.attrs["units"] = "K m-1"
        else:
            result = _as_lapse_rate_dataarray(result, temperature)

    if output_path is not None and str(output_path).strip():
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)
    return result
