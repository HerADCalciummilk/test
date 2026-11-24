# -*- coding: utf-8 -*-
"""把高差订正因子乘到站点预报上。"""
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
    scaled_dz_path: str = None,
    forecast_data_name: str = None,
    output_path: str = None,
    frt_hour_leniency: int = 1,
    config=None,
):
    """读预报和订正因子，调用 ``ApplyDzRescaling.process``，按需写出。"""
    _ = config
    forecast_path = _need("forecast_path", forecast_path)
    scaled_dz_path = _need("scaled_dz_path", scaled_dz_path)
    forecast_data_name = _need("forecast_data_name", forecast_data_name)
    if frt_hour_leniency is None:
        frt_hour_leniency = 1
    from meteva_base import read_stadata_from_csv, write_stadata_to_csv

    from station_height_difference_correction.src.dz_rescaling import ApplyDzRescaling

    forecast = read_stadata_from_csv(str(forecast_path), drop_same_id=False)
    scaled_dz = read_stadata_from_csv(str(scaled_dz_path), drop_same_id=False)
    if forecast is None or scaled_dz is None:
        raise ValueError("站点 CSV 读取失败，请检查路径与格式")
    result = ApplyDzRescaling(
        forecast_data_name=forecast_data_name,
        frt_hour_leniency=frt_hour_leniency,
    ).process(forecast, scaled_dz)
    if output_path is not None and str(output_path).strip():
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        ok = write_stadata_to_csv(
            result, str(output_path), effective_num=8, creat_dir=True
        )
        if not ok:
            raise RuntimeError("写出站点表失败: %s" % output_path)
    return result
