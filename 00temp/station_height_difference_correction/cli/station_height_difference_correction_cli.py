# -*- coding: utf-8 -*-
"""估计站点高差订正因子。

``@merge_params`` 挂在 ``process`` 上。读三份站点表，调用插件，按需写出。
"""
import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _ROOT_DIR)
if _PARENT not in sys.path:
    sys.path.insert(1, _PARENT)

from utils.merge_params import merge_params


def _need(name, value):
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: %s" % name)
    return value


@merge_params()
def process(
    forecast_path: str = None,
    truth_path: str = None,
    neighbour_path: str = None,
    forecast_period: float = None,
    forecast_data_name: str = None,
    truth_data_name: str = None,
    output_path: str = None,
    dz_lower_bound: float = None,
    dz_upper_bound: float = None,
    land_constraint: bool = False,
    similar_altitude: bool = False,
    config=None,
):
    """读预报、实况和邻近站表，调用 ``EstimateDzRescaling.process``，按需写出。"""
    _ = config
    forecast_path = _need("forecast_path", forecast_path)
    truth_path = _need("truth_path", truth_path)
    neighbour_path = _need("neighbour_path", neighbour_path)
    if forecast_period is None:
        raise ValueError("缺少参数: forecast_period")
    forecast_data_name = _need("forecast_data_name", forecast_data_name)
    from meteva_base import read_stadata_from_csv, write_stadata_to_csv

    from station_height_difference_correction.src.dz_rescaling import EstimateDzRescaling

    forecast = read_stadata_from_csv(str(forecast_path), drop_same_id=False)
    truth = read_stadata_from_csv(str(truth_path), drop_same_id=False)
    neighbour = read_stadata_from_csv(str(neighbour_path), drop_same_id=False)
    if forecast is None or truth is None or neighbour is None:
        raise ValueError("站点 CSV 读取失败，请检查路径与格式")
    result = EstimateDzRescaling(
        forecast_period=forecast_period,
        forecast_data_name=forecast_data_name,
        truth_data_name=truth_data_name,
        dz_lower_bound=dz_lower_bound,
        dz_upper_bound=dz_upper_bound,
        land_constraint=land_constraint,
        similar_altitude=similar_altitude,
    ).process(forecast, truth, neighbour)
    if output_path is not None and str(output_path).strip():
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        ok = write_stadata_to_csv(
            result, str(output_path), effective_num=8, creat_dir=True
        )
        if not ok:
            raise RuntimeError("写出站点表失败: %s" % output_path)
    return result
