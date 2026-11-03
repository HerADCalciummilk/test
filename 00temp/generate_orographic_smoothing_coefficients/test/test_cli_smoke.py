#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_orographic_smoothing_coefficients CLI 冒烟测试。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generate_orographic_smoothing_coefficients.cli.dsc_generate_orographic_smoothing_coefficients import (  # noqa: E402
    process,
)


def _make_meb6d(
    values_2d: np.ndarray,
    *,
    name: str,
    lat: np.ndarray | None = None,
    lon: np.ndarray | None = None,
    units: str = "m",
) -> xr.DataArray:
    """构造最小可用的投影米制六维 DataArray。"""
    values = values_2d[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    ny, nx = values_2d.shape
    if lat is None:
        lat = np.arange(ny, dtype=np.float32) * 1000.0
    if lon is None:
        lon = np.arange(nx, dtype=np.float32) * 1000.0
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
                np.asarray(lat, dtype=np.float32),
                dims=("lat",),
                attrs={"units": "m"},
            ),
            "lon": xr.DataArray(
                np.asarray(lon, dtype=np.float32),
                dims=("lon",),
                attrs={"units": "m"},
            ),
        },
        attrs={
            "units": units,
            "grid_mapping_attrs": json.dumps(
                {"grid_mapping_name": "lambert_azimuthal_equal_area"},
                ensure_ascii=False,
            ),
        },
        name=name,
    )


_CLI_DEFAULT_OROG = (
    Path(__file__).resolve().parents[1]
    / "test_data"
    / "cli_inputs"
    / "input_orography_meb.nc"
)
_requires_cli_default_inputs = pytest.mark.skipif(
    not _CLI_DEFAULT_OROG.is_file(),
    reason="未同步 test_data/cli_inputs",
)


def test_dsc_generate_orographic_smoothing_coefficients_process_smoke(
    tmp_path: Path,
):
    """测试 CLI process 入口可跑通并写出 x/y 系数。"""
    orography = _make_meb6d(
        np.array(
            [[10.0, 20.0, 40.0], [15.0, 25.0, 45.0], [18.0, 30.0, 50.0]],
            dtype=np.float32,
        ),
        name="orography",
    )
    mask = _make_meb6d(
        np.array(
            [[1.0, 1.0, 0.0], [1.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
            dtype=np.float32,
        ),
        name="land_binary_mask",
        units="1",
    )

    orog_path = tmp_path / "input_orography_meb.nc"
    mask_path = tmp_path / "input_landmask_meb.nc"
    output_path = tmp_path / "cli_result.nc"
    orography.to_netcdf(orog_path)
    mask.to_netcdf(mask_path)

    coeff_x, coeff_y = process(
        orography_path=str(orog_path),
        mask_path=str(mask_path),
        use_mask_boundary=True,
        output_path=str(output_path),
    )

    assert coeff_x.name == "smoothing_coefficient_x"
    assert coeff_y.name == "smoothing_coefficient_y"
    assert coeff_x.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert coeff_y.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert coeff_x.sizes["lat"] == 3 and coeff_x.sizes["lon"] == 2
    assert coeff_y.sizes["lat"] == 2 and coeff_y.sizes["lon"] == 3
    assert output_path.exists()

    disk = xr.open_dataset(output_path)
    assert "smoothing_coefficient_x" in disk
    assert "smoothing_coefficient_y" in disk
    disk.close()


@_requires_cli_default_inputs
def test_cli_default_inputs_exist_and_runnable():
    """若已导出默认 meb 输入，则 CLI 默认路径可直接跑通。"""
    test_data = (
        Path(__file__).resolve().parents[1] / "test_data" / "cli_inputs"
    )
    orog_path = test_data / "input_orography_meb.nc"
    if not orog_path.exists():
        return

    output_path = (
        Path(__file__).resolve().parents[1]
        / "test_data"
        / "cli_outputs"
        / "cli_smoke_from_default_inputs.nc"
    )
    coeff_x, coeff_y = process(
        orography_path=str(orog_path),
        output_path=str(output_path),
    )
    assert coeff_x.sizes["lat"] == 100 and coeff_x.sizes["lon"] == 99
    assert coeff_y.sizes["lat"] == 99 and coeff_y.sizes["lon"] == 100
    assert output_path.exists()
