#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""输出 attrs：仅透传 grid_mapping_attrs，其余用 set_griddata_attrs 默认。"""

from pathlib import Path
import sys

import meteva_base as meb
import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generate_ancillary.src.generate_ancillary import (  # noqa: E402
    CorrectLandSeaMask,
    GenerateOrographyBandAncils,
)
from generate_ancillary.src.generate_topographic_zone_weights import (  # noqa: E402
    GenerateTopographicZoneWeights,
)


def _meb6d(values2d: np.ndarray, *, name: str, units: str) -> xr.DataArray:
    data = np.asarray(values2d, dtype=np.float32)[
        np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :
    ]
    ny, nx = values2d.shape
    da = xr.DataArray(
        data,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": np.array([0], dtype=np.int32),
            "time": np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
            "dtime": np.array([0], dtype=np.int32),
            "lat": np.arange(ny, dtype=np.float32),
            "lon": np.arange(nx, dtype=np.float32),
        },
        name=name,
        attrs={"units": units},
    )
    meb.set_griddata_attrs(
        da,
        units=units,
        model_var="probe_model",
        dtime_units="hour",
        level_type="isobaric",
        time_type="UT",
        time_bounds=[0, 0],
        is_default=False,
    )
    da.attrs["title"] = f"title-{name}"
    da.attrs["grid_mapping_attrs"] = '{"grid_mapping_name": "latitude_longitude"}'
    return da


def test_correct_land_sea_mask_meb_defaults_and_grid_mapping():
    land = _meb6d(
        np.array([[0.2, 0.8], [0.6, 0.1]], dtype=np.float32),
        name="land_fraction",
        units="1",
    )
    land.attrs["units"] = "fraction"
    out = CorrectLandSeaMask().process(land)
    assert out.attrs["units"] == "1"
    assert out.attrs["model_var"] == ""
    assert out.attrs["dtime_units"] == "hour"
    assert out.attrs["level_type"] == "isobaric"
    assert out.attrs["grid_mapping_attrs"] == land.attrs["grid_mapping_attrs"]
    assert "title" not in out.attrs
    assert out.name == "land_binary_mask"


def test_bands_and_weights_hardcode_units_and_level_type():
    orog = _meb6d(
        np.array([[10.0, 25.0], [75.0, 100.0]], dtype=np.float32),
        name="orography",
        units="m",
    )
    land = _meb6d(
        np.array([[0.0, 1.0], [1.0, 1.0]], dtype=np.float32),
        name="land_binary_mask",
        units="1",
    )
    thresholds = {"bounds": [[0, 50], [50, 200]], "units": "m"}

    bands = GenerateOrographyBandAncils().process(orog, thresholds, landmask=land)
    assert bands.attrs["units"] == "1"
    assert bands.attrs["level_type"] == "altitude"
    assert bands.coords["level"].dtype == np.float32
    assert bands.attrs["model_var"] == ""
    assert bands.attrs["grid_mapping_attrs"] == orog.attrs["grid_mapping_attrs"]
    assert "title" not in bands.attrs
    assert bands.attrs["topographic_zones_include_seapoints"] == "False"
    assert bands.name == "topography_mask"

    weights = GenerateTopographicZoneWeights().process(
        orog, thresholds, landmask=land
    )
    assert weights.attrs["units"] == "1"
    assert weights.attrs["level_type"] == "altitude"
    assert weights.coords["level"].dtype == np.float32
    assert weights.attrs["model_var"] == ""
    assert weights.attrs["dtime_units"] == "hour"
    assert weights.attrs["grid_mapping_attrs"] == orog.attrs["grid_mapping_attrs"]
    assert weights.attrs["topographic_zones_include_seapoints"] == "False"
    assert weights.name == "topographic_zone_weights"


def test_output_fills_meb_defaults_when_input_lacks_them():
    """输入无 meb 字段时，set_griddata_attrs(is_default=True) 仍补齐缺省。"""
    data = np.array([[10.0, 25.0], [75.0, 100.0]], dtype=np.float32)
    orog = xr.DataArray(
        data[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :],
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": [0],
            "time": np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
            "dtime": [0],
            "lat": [0.0, 1.0],
            "lon": [0.0, 1.0],
        },
        attrs={"units": "m"},
        name="orography",
    )
    result = GenerateTopographicZoneWeights().process(
        orog, {"bounds": [[0, 50], [50, 200]], "units": "m"}
    )
    assert result.attrs["units"] == "1"
    assert result.attrs["level_type"] == "altitude"
    assert result.attrs["dtime_units"] == "hour"
    assert result.attrs["time_type"] == "UT"
    assert result.attrs["model_var"] == ""
    assert "time_bounds" in result.attrs
    assert "grid_mapping_attrs" not in result.attrs
    assert result.coords["level"].dtype == np.float32
