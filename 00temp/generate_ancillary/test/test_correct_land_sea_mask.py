#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CorrectLandSeaMask 单元测试。"""

from pathlib import Path
import sys

import iris
import numpy as np
import pytest
import xarray as xr

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "improver-1.18.7"))

from generate_ancillary.src.generate_ancillary import CorrectLandSeaMask  # noqa: E402

RESOURCE_ROOT = (
    Path(__file__).resolve().parents[1] / "test_data" / "generate-landmask"
)

_requires_official_data = pytest.mark.skipif(
    not (RESOURCE_ROOT / "basic" / "input.nc").is_file(),
    reason="未同步 test_data/generate-landmask",
)


def _improver_available() -> bool:
    try:
        import improver  # noqa: F401

        return True
    except ImportError:
        return False


_requires_improver = pytest.mark.skipif(
    not _improver_available(),
    reason="未提供 improver-1.18.7（包旁路径）",
)


def make_landmask_dataarray() -> xr.DataArray:
    """构造 meteva_base 六维格式测试海陆掩码。"""
    base = np.array(
        [[0.2, 0.0, 0.0], [0.7, 0.5, 0.05], [1.0, 0.95, 0.7]], dtype=np.float32
    )
    values = base[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
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
            "lat": xr.DataArray(np.array([0.0, 1.0, 2.0], dtype=np.float32), dims=("lat",)),
            "lon": xr.DataArray(np.array([100.0, 101.0, 102.0], dtype=np.float32), dims=("lon",)),
        },
        name="landmask",
    )


def test_process_binary_landmask_for_numpy():
    """测试 numpy 输入会被阈值化为 int8 二值掩码。"""
    plugin = CorrectLandSeaMask()
    landmask = np.array(
        [[0.2, 0.0, 0.0], [0.7, 0.5, 0.05], [1.0, 0.95, 0.7]],
        dtype=np.float32,
    )

    result = plugin.process(landmask)

    expected = np.array([[0, 0, 0], [1, 1, 0], [1, 1, 1]], dtype=np.int8)
    np.testing.assert_array_equal(result, expected)
    assert result.dtype == np.int8


def test_process_binary_landmask_for_xarray():
    """测试 xarray 输入会保留坐标并统一输出名称。"""
    plugin = CorrectLandSeaMask()
    landmask = make_landmask_dataarray()

    result = plugin.process(landmask)

    expected = np.array([[0, 0, 0], [1, 1, 0], [1, 1, 1]], dtype=np.int8)
    np.testing.assert_array_equal(result.squeeze(drop=True).values, expected)
    assert result.dtype == np.int8
    assert result.name == "land_binary_mask"
    assert result.dims == landmask.dims


def test_call_matches_process_for_landmask():
    """测试 __call__ 与 process 的返回完全一致。"""
    plugin = CorrectLandSeaMask()
    landmask = make_landmask_dataarray()

    result_process = plugin.process(landmask)
    result_call = plugin(landmask)

    xr.testing.assert_identical(result_call, result_process)


def test_process_rejects_non_meb6d_xarray_landmask():
    """测试非六维 xarray 输入会抛出格式异常。"""
    plugin = CorrectLandSeaMask()
    invalid_landmask = xr.DataArray(
        np.array([[0.2, 0.6], [0.4, 1.0]], dtype=np.float32),
        dims=("y", "x"),
    )
    with pytest.raises(ValueError, match="griddata dims must be"):
        plugin.process(invalid_landmask)


def to_meb6d_grid(data: xr.DataArray) -> xr.DataArray:
    """将二维网格场包装为 meteva_base 六维格式。"""
    if data.dims[-2:] == ("projection_y_coordinate", "projection_x_coordinate"):
        data = data.rename(
            {
                "projection_y_coordinate": "lat",
                "projection_x_coordinate": "lon",
            }
        )
    elif data.dims[-2:] != ("lat", "lon"):
        data = data.rename({data.dims[-2]: "lat", data.dims[-1]: "lon"})

    expanded = data.expand_dims(
        member=np.array([0], dtype=np.int32),
        level=np.array([0], dtype=np.int32),
        time=np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
        dtime=np.array([0], dtype=np.int32),
    )
    return expanded.transpose("member", "level", "time", "dtime", "lat", "lon")


def load_primary_dataarray(path: Path) -> xr.DataArray:
    """读取 NetCDF 文件中的主变量。"""
    dataset = xr.open_dataset(path, decode_timedelta=False)
    for name, data_array in dataset.data_vars.items():
        if "bnds" not in name and name != "lambert_azimuthal_equal_area":
            return data_array
    raise ValueError(f"未在 {path} 中找到主数据变量。")


# 官方数据回归测试

@_requires_improver
@_requires_official_data
def test_official_basic_matches_kgo_and_original():
    """官方样例：迁移版与 KGO、原算法二值化结果一致。"""
    from improver.generate_ancillaries.generate_ancillary import (  # noqa: E402
        CorrectLandSeaMask as OrigLandSeaMask,
    )

    landmask = to_meb6d_grid(
        load_primary_dataarray(RESOURCE_ROOT / "basic" / "input.nc")
    )
    kgo = load_primary_dataarray(RESOURCE_ROOT / "basic" / "kgo.nc")
    original = OrigLandSeaMask().process(
        iris.load_cube(str(RESOURCE_ROOT / "basic" / "input.nc")).copy()
    )

    result = CorrectLandSeaMask().process(landmask)
    result_2d = np.asarray(result.squeeze(drop=True).values)

    np.testing.assert_array_equal(result_2d, np.asarray(kgo.values))
    np.testing.assert_array_equal(result_2d, np.asarray(original.data))
    assert result.name == "land_binary_mask"
    assert result.dtype == np.int8
