#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_derived_solar_fields CLI 冒烟测试。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys

import meteva_base as meb
import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generate_derived_solar_fields.cli.cal_generate_clearsky_solar_radiation import (
    process as cal_clearsky_process,
)
from generate_derived_solar_fields.cli.cal_generate_solar_time import (
    process as cal_solar_time_process,
)


def _make_meb6d_dataarray(
    values_2d: np.ndarray, *, name: str, units: str | None = None
) -> xr.DataArray:
    """构造最小可用的 meteva_base 六维网格 DataArray。"""
    values = values_2d[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    attrs = {
        "model": "test",
        "dtime_units": "hour",
        "level_type": "surface",
        "time_type": "UT",
        "time_bounds": [0, 0],
        "grid_mapping_attrs": json.dumps(
            {"grid_mapping_name": "latitude_longitude"}, ensure_ascii=False
        ),
    }
    if units is not None:
        attrs["units"] = units

    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": xr.DataArray(np.array([0], dtype=np.int32), dims=("member",)),
            "level": xr.DataArray(np.array([0], dtype=np.int32), dims=("level",)),
            "time": xr.DataArray(
                np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
                dims=("time",),
            ),
            "dtime": xr.DataArray(np.array([0], dtype=np.int32), dims=("dtime",)),
            "lat": xr.DataArray(
                np.array([30.0, 31.0], dtype=np.float32), dims=("lat",)
            ),
            "lon": xr.DataArray(
                np.array([120.0, 121.0], dtype=np.float32), dims=("lon",)
            ),
        },
        attrs=attrs,
        name=name,
    )


def test_cal_generate_solar_time_process_smoke(tmp_path: Path):
    """测试 solar time CLI process 入口可跑通并写出结果。"""
    target_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    )
    target_grid_path = tmp_path / "target_grid.nc"
    output_path = tmp_path / "cal_solar_time_result.nc"
    target_grid.to_netcdf(target_grid_path)

    result = cal_solar_time_process(
        target_grid_path=str(target_grid_path),
        time=datetime(2024, 1, 1, 3, 0),
        output_path=str(output_path),
    )

    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert result.name == "local_solar_time"
    assert output_path.exists()

    disk_result = meb.read_griddata_from_nc(str(output_path))
    assert disk_result is not None
    assert disk_result.dims == ("member", "level", "time", "dtime", "lat", "lon")


def test_cal_generate_clearsky_solar_radiation_process_smoke(tmp_path: Path):
    """测试 clearsky solar radiation CLI process 入口可跑通并写出结果。"""
    target_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    )
    surface_altitude = _make_meb6d_dataarray(
        np.array([[100.0, 200.0], [50.0, 20.0]], dtype=np.float32),
        name="surface_altitude",
        units="m",
    )
    target_grid_path = tmp_path / "target_grid.nc"
    surface_altitude_path = tmp_path / "surface_altitude.nc"
    output_path = tmp_path / "cal_clearsky_solar_radiation_result.nc"
    target_grid.to_netcdf(target_grid_path)
    surface_altitude.to_netcdf(surface_altitude_path)

    result = cal_clearsky_process(
        target_grid_path=str(target_grid_path),
        time=datetime(2024, 1, 1, 3, 0),
        accumulation_period=1,
        surface_altitude_path=str(surface_altitude_path),
        output_path=str(output_path),
    )

    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert (
        result.name
        == "integral_of_surface_downwelling_shortwave_flux_in_air_assuming_clear_sky_wrt_time"
    )
    assert output_path.exists()

    disk_result = meb.read_griddata_from_nc(str(output_path))
    assert disk_result is not None
    assert disk_result.dims == ("member", "level", "time", "dtime", "lat", "lon")
