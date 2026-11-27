# -*- coding: utf-8 -*-
"""福建 OTS 降水。

``process`` 按四步走：读入，阈值表插件，格点订正插件，写出。
第二步对应 autofjyz，只出 20×10 阈值表。第三步对应 autofcast，用读入的
12 小时场和第二步的表做插值订正，并合成 24 小时降水。多进程在插件内部。
``config`` 与 ``ini_path`` 都可指定本次 ini，``config`` 优先。
四级优先级由 ``@merge_params`` 处理：调用参数 > 指定 ini > 默认 ``resource/conf.ini`` > 函数预设。

在 ``00temp``::

    python -m ots_fzmos_rain task=forecast initial_time=2026090108
    python -m utils.nimm_cli ots_fzmos_rain ini_path=resource/conf.ini pro_count=4

在本包目录::

    python -m cli
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _util_plugin import LEAD_HOURS
from ots_fzmos_rain_plugin import OtsForecastPlugin, OtsThresholdPlugin
from utils.merge_params import merge_params
from utils.ots_io import read_input_data, read_thresholds, write_thresholds
from utils.product_io import expand_forecast_path, load_rain12, write_product
from utils.task_args import resolve_forecast_args, resolve_threshold_args

_ROOT = Path(_ROOT_DIR)


@merge_params()
def process(
    task: str = "forecast",
    pro_count: int = 1,
    now: str = None,
    initial_time: str = None,
    input_time_zone: str = "CST",
    output_time_zone: str = "CST",
    input_rain12_dir: str = None,
    input_apcp_dir: str = None,
    input_apcp_time_zone: str = "CST",
    nc_reader: str = "meteva",
    nc_writer: str = "meteva",
    threshold_file: str = None,
    output_rain12_m4_dir: str = None,
    output_rain24_m4_dir: str = None,
    output_rain12_nc_dir: str = None,
    output_rain24_nc_dir: str = None,
    source_lat_start: float = 55.0,
    source_lon_start: float = 70.0,
    source_lat_end: float = 15.0,
    source_lon_end: float = 140.0,
    source_dlat: float = -0.125,
    source_dlon: float = 0.125,
    source_num_x: int = 561,
    source_num_y: int = 321,
    output_lat_start: float = 21.0,
    output_lon_start: float = 114.0,
    output_lat_end: float = 29.0,
    output_lon_end: float = 127.0,
    output_dlat: float = 0.025,
    output_dlon: float = 0.025,
    output_num_x: int = 521,
    output_num_y: int = 321,
    interpolation_radius: float = 0.7,
    obs_dir: str = None,
    ec_dir: str = None,
    station_file: str = None,
    station_count: int = 70,
    output_file: str = None,
    config=None,
    ini_path=None,
):
    """四步：读入，阈值表插件，订正插件，写出。``pro_count`` 大于 1 时插件内部并行。"""
    _ = config, ini_path
    name = (task or "forecast").strip().lower()
    if name not in {"threshold", "forecast", "both"}:
        raise ValueError("task 只能是 threshold、forecast 或 both")
    count = int(pro_count or 1)

    # 第一步：读出这一次要用的数据。阈值任务读历史站点样本；订正任务读 12 小时场。
    # task=both 时订正直接使用第二步算出的表，不读旧表。
    threshold_prepared = None
    ec_by_year = None
    obs_by_year = None
    forecast_prepared = None
    fields = None
    grids = None
    thresholds = None
    if name in {"threshold", "both"}:
        threshold_prepared = resolve_threshold_args(
            _ROOT,
            now=now,
            initial_time=initial_time,
            input_time_zone=input_time_zone,
            obs_dir=obs_dir,
            ec_dir=ec_dir,
            station_file=station_file,
            station_count=station_count,
            output_file=output_file,
        )
        target = threshold_prepared["target"]
        _, ec_by_year, obs_by_year = read_input_data(
            threshold_prepared["obs_dir"],
            threshold_prepared["ec_dir"],
            threshold_prepared["station_file"],
            threshold_prepared["station_count"],
            target.this_year,
        )
        threshold_file = str(threshold_prepared["output_file"])
    if name in {"forecast", "both"}:
        forecast_prepared = resolve_forecast_args(
            _ROOT,
            now=now,
            initial_time=initial_time,
            input_time_zone=input_time_zone,
            output_time_zone=output_time_zone,
            input_rain12_dir=input_rain12_dir,
            input_apcp_dir=input_apcp_dir,
            input_apcp_time_zone=input_apcp_time_zone,
            nc_reader=nc_reader,
            nc_writer=nc_writer,
            threshold_file=threshold_file,
            output_rain12_m4_dir=output_rain12_m4_dir,
            output_rain24_m4_dir=output_rain24_m4_dir,
            output_rain12_nc_dir=output_rain12_nc_dir,
            output_rain24_nc_dir=output_rain24_nc_dir,
            source_lat_start=source_lat_start,
            source_lon_start=source_lon_start,
            source_lat_end=source_lat_end,
            source_lon_end=source_lon_end,
            source_dlat=source_dlat,
            source_dlon=source_dlon,
            source_num_x=source_num_x,
            source_num_y=source_num_y,
            output_lat_start=output_lat_start,
            output_lon_start=output_lon_start,
            output_lat_end=output_lat_end,
            output_lon_end=output_lon_end,
            output_dlat=output_dlat,
            output_dlon=output_dlon,
            output_num_x=output_num_x,
            output_num_y=output_num_y,
            interpolation_radius=interpolation_radius,
        )
        if name == "forecast":
            thresholds = read_thresholds(forecast_prepared["threshold_file"])
        fields = []
        grids = []
        for forecast_hour in LEAD_HOURS:
            input_path = expand_forecast_path(
                forecast_prepared["input_rain12"],
                forecast_prepared["input_initial"],
                forecast_hour,
            )
            values, grid, _absent = load_rain12(
                input_path,
                forecast_prepared["source_grid"],
                forecast_prepared["apcp_dir"],
                forecast_prepared["apcp_initial"],
                forecast_hour,
                forecast_prepared["nc_reader"],
            )
            fields.append(values)
            grids.append(grid)

    # 第二步：用历史样本做阈值表。
    table = None
    if threshold_prepared is not None:
        target = threshold_prepared["target"]
        table = OtsThresholdPlugin().process(
            iday=40,
            start_day=target.start_day,
            station_count=threshold_prepared["station_count"],
            ec_by_year=ec_by_year,
            obs_by_year=obs_by_year,
            begin_year=target.this_year - 2,
            end_year=target.this_year,
            pro_count=count,
        )
        thresholds = table

    # 第三步：用读入的 12 小时场和阈值表做插值订正，并合成 24 小时降水。
    products = None
    if fields is not None:
        products = OtsForecastPlugin().process(
            fields,
            grids,
            forecast_prepared["output_grid"],
            forecast_prepared["interpolation_radius"],
            thresholds,
            pro_count=count,
        )

    # 第四步：写出阈值表、12 小时场和 24 小时场。
    output = None
    if table is not None:
        output = threshold_prepared["output_file"]
        write_thresholds(output, table)
        print(
            "input_time_zone=%s this_year=%s start_day=%s output=%s"
            % (
                threshold_prepared["zone"],
                threshold_prepared["target"].this_year,
                threshold_prepared["target"].start_day,
                output,
            )
        )
    if products is not None:
        rain12, rain24 = products
        written24 = []
        for forecast_hour, corrected, rain24_field in zip(LEAD_HOURS, rain12, rain24):
            if corrected is not None:
                write_product(
                    corrected,
                    forecast_prepared["output_initial"],
                    forecast_hour,
                    "rain12",
                    forecast_prepared["output_grid"],
                    forecast_prepared["rain12_m4"],
                    forecast_prepared["rain12_nc"],
                    forecast_prepared["nc_writer"],
                )
            if rain24_field is not None:
                written24.extend(
                    write_product(
                        rain24_field,
                        forecast_prepared["output_initial"],
                        forecast_hour,
                        "rain24",
                        forecast_prepared["output_grid"],
                        forecast_prepared["rain24_m4"],
                        forecast_prepared["rain24_nc"],
                        forecast_prepared["nc_writer"],
                    )
                )
        print(
            "input_initial=%s output_initial=%s rain24_files=%s"
            % (
                forecast_prepared["input_initial"].strftime("%Y%m%d%H"),
                forecast_prepared["output_initial"].strftime("%Y%m%d%H"),
                len(written24),
            )
        )
        return rain12
    return output
