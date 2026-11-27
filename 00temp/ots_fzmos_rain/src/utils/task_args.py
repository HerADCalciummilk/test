# -*- coding: utf-8 -*-
"""把 process 收到的参数整理成读文件要用的路径、网格和起报时间。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from utils.forecast_time import convert_initial_time, determine_initial_time, validate_initial_time
from utils.grid import GridConfig
from utils.threshold_time import determine_target_run


def blank(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_path(root, value):
    text = blank(value)
    if text is None:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = Path(root) / path
    return path


def parse_clock(value):
    text = blank(value)
    if text is None:
        return None
    if len(text) != 10 or not text.isdigit():
        raise ValueError("时间必须是 10 位 YYYYMMDDHH，例如 2026090108")
    return datetime(int(text[0:4]), int(text[4:6]), int(text[6:8]), int(text[8:10]))


def time_zone(value, key):
    zone = str(value or "CST").strip().upper()
    if zone not in {"UTC", "CST"}:
        raise ValueError("%s 只能是 UTC 或 CST" % key)
    return zone


def reader_name(value, key):
    name = str(value or "meteva").strip().lower()
    if name not in {"meteva", "xarray"}:
        raise ValueError("%s 只能是 meteva 或 xarray" % key)
    return name


def forecast_pattern(value, key):
    path = blank(value)
    if path is None:
        return None
    if "FFF" not in path:
        raise ValueError("%s 必须包含三位预报时效占位符 FFF" % key)
    return path


def require_pair(left, right, left_key, right_key):
    if (left is None) != (right is None):
        raise ValueError("%s 和 %s 必须同时配置或同时留空" % (left_key, right_key))
    return left, right


def grid_config(prefix, values):
    grid = GridConfig(
        lat_start=float(values["%s_lat_start" % prefix]),
        lon_start=float(values["%s_lon_start" % prefix]),
        lat_end=float(values["%s_lat_end" % prefix]),
        lon_end=float(values["%s_lon_end" % prefix]),
        dlat=float(values["%s_dlat" % prefix]),
        dlon=float(values["%s_dlon" % prefix]),
        num_x=int(values["%s_num_x" % prefix]),
        num_y=int(values["%s_num_y" % prefix]),
    )
    if grid.num_x <= 0 or grid.num_y <= 0:
        raise ValueError("%s 网格的 num_x 和 num_y 必须大于 0" % prefix)
    if grid.dlon == 0.0 or grid.dlat == 0.0:
        raise ValueError("%s 网格的 dlon 和 dlat 不能为 0" % prefix)
    return grid


def resolve_threshold_args(root, now, initial_time, input_time_zone, obs_dir, ec_dir, station_file, station_count, output_file):
    """阈值任务开算前要有的站点样本路径和目标起报。"""
    obs = resolve_path(root, obs_dir)
    ec = resolve_path(root, ec_dir)
    stations = resolve_path(root, station_file)
    output = resolve_path(root, output_file)
    missing = [
        key
        for key, path in (
            ("obs_dir", obs),
            ("ec_dir", ec),
            ("station_file", stations),
            ("output_file", output),
        )
        if path is None
    ]
    if missing:
        raise ValueError("做阈值表缺少参数: " + ", ".join(missing))
    zone = time_zone(input_time_zone, "input_time_zone")
    target = determine_target_run(
        parse_clock(now),
        initial_time=parse_clock(initial_time),
        input_time_zone=zone,
    )
    return {
        "obs_dir": obs,
        "ec_dir": ec,
        "station_file": stations,
        "output_file": output,
        "station_count": int(station_count or 70),
        "zone": zone,
        "target": target,
    }


def resolve_forecast_args(root, **values):
    """订正任务开算前要有的路径、网格、起报时间和阈值表。"""
    input_rain12 = forecast_pattern(values["input_rain12_dir"], "input_rain12_dir")
    threshold_file = resolve_path(root, values["threshold_file"])
    if not input_rain12 or threshold_file is None:
        raise ValueError("做格点订正缺少参数: input_rain12_dir, threshold_file")
    radius = float(values["interpolation_radius"] or 0.7)
    if radius <= 0.0:
        raise ValueError("interpolation_radius 必须大于 0")
    input_zone = time_zone(values["input_time_zone"], "input_time_zone")
    output_zone = time_zone(values["output_time_zone"], "output_time_zone")
    apcp_zone = time_zone(
        values["input_apcp_time_zone"] or input_zone, "input_apcp_time_zone"
    )
    rain12_m4, rain24_m4 = require_pair(
        forecast_pattern(values["output_rain12_m4_dir"], "output_rain12_m4_dir"),
        forecast_pattern(values["output_rain24_m4_dir"], "output_rain24_m4_dir"),
        "output_rain12_m4_dir",
        "output_rain24_m4_dir",
    )
    rain12_nc, rain24_nc = require_pair(
        forecast_pattern(values["output_rain12_nc_dir"], "output_rain12_nc_dir"),
        forecast_pattern(values["output_rain24_nc_dir"], "output_rain24_nc_dir"),
        "output_rain12_nc_dir",
        "output_rain24_nc_dir",
    )
    if rain12_m4 is None and rain12_nc is None:
        raise ValueError("至少配置一组 12/24 小时输出，M4 或 NC")

    given = parse_clock(values["initial_time"])
    input_initial = (
        validate_initial_time(given, input_zone)
        if given is not None
        else determine_initial_time(parse_clock(values["now"]), input_zone)
    )
    return {
        "input_rain12": input_rain12,
        "input_initial": input_initial,
        "output_initial": convert_initial_time(input_initial, input_zone, output_zone),
        "apcp_initial": convert_initial_time(input_initial, input_zone, apcp_zone),
        "apcp_dir": forecast_pattern(values["input_apcp_dir"], "input_apcp_dir"),
        "source_grid": grid_config("source", values),
        "output_grid": grid_config("output", values),
        "interpolation_radius": radius,
        "nc_reader": reader_name(values["nc_reader"], "nc_reader"),
        "nc_writer": reader_name(values["nc_writer"], "nc_writer"),
        "threshold_file": threshold_file,
        "rain12_m4": rain12_m4,
        "rain12_nc": rain12_nc,
        "rain24_m4": rain24_m4,
        "rain24_nc": rain24_nc,
    }
