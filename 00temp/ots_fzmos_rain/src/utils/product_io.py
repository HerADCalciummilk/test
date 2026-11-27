# -*- coding: utf-8 -*-
"""一个时效的 12 小时场读取，以及订正结果的 m4/nc 写出。"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from utils.apcp_reader import read_rain12_from_apcp
from utils.micaps_io import write_micaps4
from utils.netcdf_io import write_griddata_to_nc
from utils.source_reader import read_source_field


def expand_forecast_path(pattern, when, forecast_hour):
    return Path(when.strftime(pattern).replace("FFF", "%03d" % forecast_hour))


def load_rain12(path, fallback_grid, apcp_dir, apcp_initial, forecast_hour, nc_reader):
    """读一个 12 小时场。文件缺失时尝试 APCP 差分，仍失败则用缺测场。"""
    if path.exists():
        print("reading : %s" % path)
        try:
            field = read_source_field(path, nc_reader=nc_reader)
            return field.values, field.grid, False
        except (OSError, RuntimeError, ValueError) as exc:
            print("namelist file read error,file:%s: %s" % (path, exc))
    else:
        print("namelist file does not exist,file:%s" % path)
    if apcp_dir is not None:
        try:
            field = read_rain12_from_apcp(apcp_dir, apcp_initial, forecast_hour, nc_reader)
            print("reading APCP : %s +%03d" % (apcp_initial.strftime("%Y%m%d%H"), forecast_hour))
            return field.values, field.grid, False
        except (OSError, RuntimeError, ValueError) as exc:
            print("APCP read error,forecast_hour=%03d: %s" % (forecast_hour, exc))
    shape = (fallback_grid.num_y, fallback_grid.num_x)
    return np.full(shape, np.float32(9999.0), dtype=np.float32), fallback_grid, True


def write_product(values, initial_time, forecast_hour, element, grid, m4_pattern, nc_pattern, nc_writer):
    written = []
    if m4_pattern is not None:
        path = expand_forecast_path(m4_pattern, initial_time, forecast_hour)
        write_micaps4(path, initial_time, forecast_hour, element, grid, values)
        written.append(path)
    if nc_pattern is not None:
        path = expand_forecast_path(nc_pattern, initial_time, forecast_hour)
        write_griddata_to_nc(
            path, initial_time, forecast_hour, "data0", grid, values, nc_writer=nc_writer
        )
        written.append(path)
    return written
