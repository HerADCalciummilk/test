#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_mask_griddata：对齐原库 _make_mask_cube 的构造行为。"""

from pathlib import Path
import sys

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generate_ancillary.src.utils._make_mask_griddata import (  # noqa: E402
    make_mask_griddata,
)


def _template(ny: int = 3, nx: int = 3) -> xr.DataArray:
    data = np.zeros((1, 1, 1, 1, ny, nx), dtype=np.float32)
    return xr.DataArray(
        data,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": np.array([0], dtype=np.float32),
            "time": np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
            "dtime": [0],
            "lat": np.arange(ny, dtype=np.float32),
            "lon": np.arange(nx, dtype=np.float32),
        },
        name="orography",
        attrs={
            "units": "m",
            "model_var": "probe",
            "title": "src-title",
            "grid_mapping_attrs": '{"grid_mapping_name": "latitude_longitude"}',
        },
    )


def test_make_mask_griddata_rejects_bad_bounds():
    """非法 bounds（长度非 2、含 None）应抛 TypeError。"""
    tmpl = _template()
    mask = np.zeros((3, 3), dtype=np.int32)
    with pytest.raises(TypeError):
        make_mask_griddata(mask, tmpl, [0], "m")
    with pytest.raises(TypeError):
        make_mask_griddata(mask, tmpl, [0, 2, 4], "m")
    with pytest.raises(TypeError):
        make_mask_griddata(mask, tmpl, [None, 100.0], "m")


def test_make_mask_griddata_single_band_coords_and_attrs():
    """单带：六维结构、level 中点/上下界、meb attrs 与数值透传。"""
    tmpl = _template()
    mask = np.array([[1, 0, 0], [0, 0, 0], [0, 0, 0]], dtype=np.int32)
    out = make_mask_griddata(
        mask, tmpl, [0.0, 100.0], "m", sea_points_included=False
    )
    assert out.name == "topography_mask"
    assert out.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert out.sizes["level"] == 1
    np.testing.assert_allclose(out.coords["level"].values, [50.0])
    np.testing.assert_allclose(out.coords["level_lower_bound"].values, [0.0])
    np.testing.assert_allclose(out.coords["level_upper_bound"].values, [100.0])
    assert out.coords["level"].dtype == np.float32
    assert out.coords["level"].attrs["units"] == "m"
    assert out.attrs["units"] == "1"
    assert out.attrs["level_type"] == "altitude"
    assert out.attrs["topographic_zones_include_seapoints"] == "False"
    assert out.attrs["model_var"] == ""
    assert "title" not in out.attrs
    assert out.attrs["grid_mapping_attrs"] == tmpl.attrs["grid_mapping_attrs"]
    np.testing.assert_array_equal(out.values[0, 0, 0, 0], mask)


def test_make_mask_griddata_multiband():
    """多带 (n_band,y,x)：level 维长度与各带中点坐标正确。"""
    tmpl = _template()
    weights = np.zeros((2, 3, 3), dtype=np.float32)
    weights[0, 0, 0] = 1.0
    stacked = make_mask_griddata(
        weights,
        tmpl,
        [[0.0, 50.0], [50.0, 200.0]],
        "m",
        name="topographic_zone_weights",
        dtype=np.float32,
    )
    assert stacked.sizes["level"] == 2
    np.testing.assert_allclose(stacked.coords["level"].values, [25.0, 125.0])
    assert stacked.name == "topographic_zone_weights"
