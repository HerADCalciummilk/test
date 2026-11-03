#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_ancillary CLI 冒烟测试。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import meteva_base as meb
import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generate_ancillary.cli.anc_generate_landmask_ancillary import process as anc_process
from generate_ancillary.cli.dsc_generate_topography_bands_mask import process as dsc_process
from generate_ancillary.cli.dsc_generate_topographic_zone_weights import (
    process as weights_process,
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


def test_dsc_generate_topography_bands_mask_process_smoke(tmp_path: Path):
    """测试地形带 CLI process 入口可跑通并写出结果。"""
    orography = _make_meb6d_dataarray(
        np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
        name="orography",
        units="m",
    )
    landmask = _make_meb6d_dataarray(
        np.array([[1.0, 0.0], [1.0, 1.0]], dtype=np.float32),
        name="land_binary_mask",
    )

    input_orog_path = tmp_path / "input_orog_meb.nc"
    input_land_path = tmp_path / "input_land_meb.nc"
    thresholds_path = tmp_path / "bounds.json"
    output_path = tmp_path / "cli_topography_bands_mask_result.nc"

    orography.to_netcdf(input_orog_path)
    landmask.to_netcdf(input_land_path)
    thresholds = {"bounds": [[0.0, 25.0], [25.0, 50.0]], "units": "m"}
    with open(thresholds_path, "w", encoding="utf-8") as outfile:
        json.dump(thresholds, outfile)

    result = dsc_process(
        orography_path=str(input_orog_path),
        landmask_path=str(input_land_path),
        thresholds_path=str(thresholds_path),
        output_path=str(output_path),
    )

    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert result.sizes["level"] == 2
    assert output_path.exists()

    disk_result = meb.read_griddata_from_nc(str(output_path))
    assert disk_result is not None
    assert disk_result.dims == ("member", "level", "time", "dtime", "lat", "lon")


def test_anc_generate_landmask_ancillary_process_smoke(tmp_path: Path):
    """测试海陆掩码 CLI process 入口可跑通并写出结果。"""
    landmask = _make_meb6d_dataarray(
        np.array([[0.2, 0.8], [0.6, 0.4]], dtype=np.float32),
        name="landmask",
    )

    input_land_path = tmp_path / "input_land_meb.nc"
    output_path = tmp_path / "cli_landmask_result.nc"
    landmask.to_netcdf(input_land_path)

    result = anc_process(landmask_path=str(input_land_path), output_path=str(output_path))

    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert np.issubdtype(result.dtype, np.integer)
    assert output_path.exists()

    disk_result = meb.read_griddata_from_nc(str(output_path))
    assert disk_result is not None
    assert disk_result.dims == ("member", "level", "time", "dtime", "lat", "lon")


def test_dsc_generate_topographic_zone_weights_process_smoke(tmp_path: Path):
    """测试地形带权重 CLI process 入口可跑通并写出结果。"""
    orography = _make_meb6d_dataarray(
        np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
        name="orography",
        units="m",
    )
    landmask = _make_meb6d_dataarray(
        np.array([[1.0, 0.0], [1.0, 1.0]], dtype=np.float32),
        name="land_binary_mask",
    )

    input_orog_path = tmp_path / "input_orog_meb.nc"
    input_land_path = tmp_path / "input_land_meb.nc"
    thresholds_path = tmp_path / "bounds.json"
    output_path = tmp_path / "cli_topographic_zone_weights_result.nc"

    orography.to_netcdf(input_orog_path)
    landmask.to_netcdf(input_land_path)
    thresholds = {"bounds": [[0.0, 25.0], [25.0, 50.0]], "units": "m"}
    with open(thresholds_path, "w", encoding="utf-8") as outfile:
        json.dump(thresholds, outfile)

    result = weights_process(
        orography_path=str(input_orog_path),
        landmask_path=str(input_land_path),
        thresholds_path=str(thresholds_path),
        output_path=str(output_path),
    )

    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert result.sizes["level"] == 2
    assert result.name == "topographic_zone_weights"
    assert output_path.exists()

    disk_result = meb.read_griddata_from_nc(str(output_path))
    assert disk_result is not None
    assert disk_result.dims == ("member", "level", "time", "dtime", "lat", "lon")
