#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_derived_solar_fields 单元测试。"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta
import json
import sys

import numpy as np
import pytest
import xarray as xr
from pyproj import CRS, Transformer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generate_derived_solar_fields.src.generate_derived_solar_fields import (
    CLEARSKY_SOLAR_RADIATION_CF_NAME,
    SOLAR_TIME_CF_NAME,
    GenerateClearskySolarRadiation,
    GenerateSolarTime,
)
from generate_derived_solar_fields.src.utils.solar import (
    calc_solar_time,
    get_day_of_year,
    get_hour_of_day,
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
            "lat": xr.DataArray(np.array([30.0, 31.0], dtype=np.float32), dims=("lat",)),
            "lon": xr.DataArray(
                np.array([120.0, 121.0], dtype=np.float32), dims=("lon",)
            ),
        },
        attrs=attrs,
        name=name,
    )


def test_generate_solar_time_process_returns_meb6d_result():
    """测试地方太阳时输出维度、名称和数值范围。"""
    target_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    )

    result = GenerateSolarTime().process(target_grid, datetime(2024, 1, 1, 3, 0))

    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert result.name == SOLAR_TIME_CF_NAME
    assert result.attrs["units"] == "hours"
    values = result.squeeze(drop=True).values
    assert np.all(values >= 0.0)
    assert np.all(values < 24.0)


def test_generate_solar_time_defaults_to_latlon_without_grid_mapping_attrs():
    """缺少 grid_mapping_attrs 时默认按经纬坐标计算，结果与显式 latitude_longitude 一致。"""
    target_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    )
    valid_time = datetime(2024, 1, 1, 3, 0)
    with_attrs = GenerateSolarTime().process(target_grid, valid_time)

    no_attrs_grid = target_grid.copy()
    no_attrs_grid.attrs.pop("grid_mapping_attrs", None)
    without_attrs = GenerateSolarTime().process(no_attrs_grid, valid_time)

    np.testing.assert_allclose(without_attrs.values, with_attrs.values)


def test_generate_clearsky_solar_radiation_defaults_to_latlon_without_grid_mapping_attrs():
    """缺少 grid_mapping_attrs 时默认按经纬坐标计算，结果与显式 latitude_longitude 一致。"""
    target_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    )
    kwargs = dict(
        time=datetime(2024, 1, 1, 3, 0),
        accumulation_period=1,
    )
    with_attrs = GenerateClearskySolarRadiation().process(target_grid=target_grid, **kwargs)

    no_attrs_grid = target_grid.copy()
    no_attrs_grid.attrs.pop("grid_mapping_attrs", None)
    without_attrs = GenerateClearskySolarRadiation().process(
        target_grid=no_attrs_grid, **kwargs
    )

    np.testing.assert_allclose(without_attrs.values, with_attrs.values)


def test_generate_solar_time_supports_projected_coordinates_via_grid_mapping_attrs():
    """当投影属性以 grid_mapping_attrs(JSON) 存储时，也能完成投影转换。"""
    projected_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    ).assign_coords(
        lat=xr.DataArray(np.array([-4.0e6, -3.99e6], dtype=np.float32), dims=("lat",)),
        lon=xr.DataArray(np.array([-1.5e6, -1.49e6], dtype=np.float32), dims=("lon",)),
    )
    mapping_attrs = {
        "grid_mapping_name": "albers_conical_equal_area",
        "longitude_of_prime_meridian": 0.0,
        "semi_major_axis": 6378137.0,
        "semi_minor_axis": 6356752.314140356,
        "longitude_of_central_meridian": 132.0,
        "latitude_of_projection_origin": 0.0,
        "false_easting": 0.0,
        "false_northing": 0.0,
        "standard_parallel": [-18.0, -36.0],
    }
    projected_grid.attrs["grid_mapping_attrs"] = json.dumps(mapping_attrs, ensure_ascii=False)
    valid_time = datetime(2024, 1, 1, 3, 0)

    result = GenerateSolarTime().process(projected_grid, valid_time)

    y2d, x2d = np.meshgrid(
        projected_grid.coords["lat"].values.astype(np.float64),
        projected_grid.coords["lon"].values.astype(np.float64),
        indexing="ij",
    )
    transformer = Transformer.from_crs(
        CRS.from_cf(mapping_attrs),
        CRS.from_epsg(4326),
        always_xy=True,
    )
    lons_2d, _ = transformer.transform(x2d, y2d)
    expected = calc_solar_time(
        lons_2d, get_day_of_year(valid_time), get_hour_of_day(valid_time), normalise=True
    )
    np.testing.assert_allclose(result.squeeze(drop=True).values, expected, atol=1e-5)


def test_generate_solar_time_supports_projected_coordinates_in_km_units():
    """投影坐标若为 km 单位，应先转米再完成转换。"""
    projected_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    ).assign_coords(
        lat=xr.DataArray(
            np.array([-4000.0, -3990.0], dtype=np.float32),
            dims=("lat",),
            attrs={"units": "km"},
        ),
        lon=xr.DataArray(
            np.array([-1500.0, -1490.0], dtype=np.float32),
            dims=("lon",),
            attrs={"units": "km"},
        ),
    )
    mapping_attrs = {
        "grid_mapping_name": "albers_conical_equal_area",
        "longitude_of_prime_meridian": 0.0,
        "semi_major_axis": 6378137.0,
        "semi_minor_axis": 6356752.314140356,
        "longitude_of_central_meridian": 132.0,
        "latitude_of_projection_origin": 0.0,
        "false_easting": 0.0,
        "false_northing": 0.0,
        "standard_parallel": [-18.0, -36.0],
    }
    projected_grid.attrs["grid_mapping_attrs"] = json.dumps(mapping_attrs, ensure_ascii=False)
    valid_time = datetime(2024, 1, 1, 3, 0)

    result = GenerateSolarTime().process(projected_grid, valid_time)

    y2d, x2d = np.meshgrid(
        projected_grid.coords["lat"].values.astype(np.float64) * 1000.0,
        projected_grid.coords["lon"].values.astype(np.float64) * 1000.0,
        indexing="ij",
    )
    transformer = Transformer.from_crs(
        CRS.from_cf(mapping_attrs),
        CRS.from_epsg(4326),
        always_xy=True,
    )
    lons_2d, _ = transformer.transform(x2d, y2d)
    expected = calc_solar_time(
        lons_2d, get_day_of_year(valid_time), get_hour_of_day(valid_time), normalise=True
    )
    np.testing.assert_allclose(result.squeeze(drop=True).values, expected, atol=1e-5)


def test_generate_clearsky_solar_radiation_process_with_defaults():
    """测试晴空辐射在默认输入下可计算并返回正值场。"""
    target_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    )

    valid_time = datetime(2024, 1, 1, 3, 0)
    accumulation_period = 1
    result = GenerateClearskySolarRadiation().process(
        target_grid=target_grid,
        time=valid_time,
        accumulation_period=accumulation_period,
    )

    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert result.name == CLEARSKY_SOLAR_RADIATION_CF_NAME
    assert result.attrs["units"] == "W s m-2"
    assert result.attrs["accumulation_period_hours"] == 1
    assert np.all(result.values >= 0.0)
    assert (
        result.coords["time"].attrs.get("bounds")
        == "time_lower_bound time_upper_bound"
    )
    assert "time_lower_bound" in result.coords
    assert "time_upper_bound" in result.coords
    expected_lower = np.array(
        [np.datetime64(valid_time - timedelta(hours=accumulation_period), "ns")],
        dtype="datetime64[ns]",
    )
    expected_upper = np.array(
        [np.datetime64(valid_time, "ns")],
        dtype="datetime64[ns]",
    )
    np.testing.assert_array_equal(result.coords["time_lower_bound"].values, expected_lower)
    np.testing.assert_array_equal(result.coords["time_upper_bound"].values, expected_upper)


def test_generate_clearsky_solar_radiation_rejects_invalid_temporal_spacing():
    """测试 accumulation_period 与 temporal_spacing 不整除时抛错。"""
    target_grid = _make_meb6d_dataarray(
        np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float32),
        name="target_grid",
        units="1",
    )

    with pytest.raises(ValueError, match="integer multiple of temporal_spacing"):
        GenerateClearskySolarRadiation().process(
            target_grid=target_grid,
            time=datetime(2024, 1, 1, 3, 0),
            accumulation_period=1,
            temporal_spacing=17,
        )


def test_generate_clearsky_solar_radiation_rejects_multi_front_dims():
    """前四维长度大于1时，应拒绝非单场输入。"""
    target_grid = xr.DataArray(
        np.zeros((2, 1, 2, 1, 2, 2), dtype=np.float32),
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": xr.DataArray(np.array([0, 1], dtype=np.int32), dims=("member",)),
            "level": xr.DataArray(np.array([0], dtype=np.int32), dims=("level",)),
            "time": xr.DataArray(
                np.array(["2024-01-01T00:00:00", "2024-01-01T01:00:00"], dtype="datetime64[ns]"),
                dims=("time",),
            ),
            "dtime": xr.DataArray(np.array([0], dtype=np.int32), dims=("dtime",)),
            "lat": xr.DataArray(np.array([30.0, 31.0], dtype=np.float32), dims=("lat",)),
            "lon": xr.DataArray(np.array([120.0, 121.0], dtype=np.float32), dims=("lon",)),
        },
        attrs={
            "model": "test",
            "dtime_units": "hour",
            "level_type": "surface",
            "time_type": "UT",
            "time_bounds": [0, 0],
            "units": "1",
            "grid_mapping_attrs": json.dumps(
                {"grid_mapping_name": "latitude_longitude"}, ensure_ascii=False
            ),
        },
        name="target_grid",
    )
    with pytest.raises(
        ValueError, match=r"more effective coordinates than \(lat, lon\)"
    ):
        GenerateClearskySolarRadiation().process(
            target_grid=target_grid,
            time=datetime(2024, 1, 1, 3, 0),
            accumulation_period=1,
        )
