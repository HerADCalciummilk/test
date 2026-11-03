#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RegridWithLandSeaMask / *-2 合成单元测试（对齐上游 test_RegridWithLandSeaMask）。"""

from __future__ import annotations

import numpy as np
import pytest

from regrid import RegridLandSea
from regrid.src.utils.bilinear import basic_indexes
from regrid.src.utils.grid import (
    calculate_input_grid_spacing,
    latlon_from_dataarray,
)
from regrid.test.helpers import make_meb6d, to_compare_array


def _define_source_target_grid_data():
    """上游 define_source_target_grid_data 的 meb 版本。"""
    in_lats = np.linspace(0, 15, 4, dtype=np.float32)
    in_lons = np.linspace(0, 40, 5, dtype=np.float32)
    out_lats = np.linspace(0, 14, 8, dtype=np.float32)
    out_lons = np.linspace(5, 35, 11, dtype=np.float32)

    data = np.arange(20, dtype=np.float32).reshape(4, 5)

    in_mask = np.ones((4, 5), dtype=np.float32)
    in_mask[0, 2] = 0
    in_mask[2, 2:4] = 0
    in_mask[3, 2:4] = 0

    out_mask = np.ones((8, 11), dtype=np.float32)
    out_mask[0, 4:7] = 0
    out_mask[1, 5] = 0
    out_mask[5:9, 4:10] = 0
    out_mask[6, 6] = 1
    out_mask[7, 6] = 1
    out_mask[1, 0] = 0

    cube_in = make_meb6d(data, lats=in_lats, lons=in_lons, name="air_temperature", units="C")
    cube_in_mask = make_meb6d(
        in_mask, lats=in_lats, lons=in_lons, name="land_binary_mask", units="1"
    )
    cube_out_mask = make_meb6d(
        out_mask, lats=out_lats, lons=out_lons, name="land_binary_mask", units="1"
    )
    return cube_in, cube_out_mask, cube_in_mask


def _define_source_target_grid_data_same_domain():
    """上游同域版本。"""
    in_lats = np.linspace(0, 15, 4, dtype=np.float32)
    in_lons = np.linspace(0, 40, 5, dtype=np.float32)
    out_lats = np.linspace(0, 15, 7, dtype=np.float32)
    out_lons = np.linspace(0, 40, 9, dtype=np.float32)

    data = np.arange(20, dtype=np.float32).reshape(4, 5)

    in_mask = np.ones((4, 5), dtype=np.float32)
    in_mask[0, 2] = 0
    in_mask[2, 2:4] = 0
    in_mask[3, 2:4] = 0

    out_mask = np.ones((7, 9), dtype=np.float32)
    out_mask[0, 3:6] = 0
    out_mask[1, 4] = 0
    out_mask[4:9, 4:8] = 0
    out_mask[6, 6] = 1
    out_mask[1, 0] = 0

    cube_in = make_meb6d(data, lats=in_lats, lons=in_lons, name="air_temperature", units="C")
    cube_in_mask = make_meb6d(
        in_mask, lats=in_lats, lons=in_lons, name="land_binary_mask", units="1"
    )
    cube_out_mask = make_meb6d(
        out_mask, lats=out_lats, lons=out_lons, name="land_binary_mask", units="1"
    )
    return cube_in, cube_out_mask, cube_in_mask


def test_basic_indexes():
    cube_in, cube_out_mask, _ = _define_source_target_grid_data_same_domain()
    in_latlons = latlon_from_dataarray(cube_in)
    out_latlons = latlon_from_dataarray(cube_out_mask)
    in_lons_size = int(cube_in.sizes["lon"])
    lat_spacing, lon_spacing = calculate_input_grid_spacing(cube_in)
    indexes = basic_indexes(
        out_latlons, in_latlons, in_lons_size, lat_spacing, lon_spacing
    )
    expected = np.array(
        [
            [12, 17, 18, 13],
            [12, 17, 18, 13],
            [13, 18, 19, 14],
            [13, 18, 19, 14],
            [13, 18, 19, 14],
        ]
    )
    np.testing.assert_array_equal(indexes[58:63, :], expected)


def test_regrid_nearest_2():
    cube_in, cube_out_mask, _ = _define_source_target_grid_data()
    result = RegridLandSea(regrid_mode="nearest-2")(cube_in, cube_out_mask)
    expected = np.array(
        [
            [0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3],
            [0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3],
            [5, 6, 6, 6, 7, 7, 7, 8, 8, 8, 8],
            [5, 6, 6, 6, 7, 7, 7, 8, 8, 8, 8],
            [10, 11, 11, 11, 12, 12, 12, 13, 13, 13, 13],
            [10, 11, 11, 11, 12, 12, 12, 13, 13, 13, 13],
            [10, 11, 11, 11, 12, 12, 12, 13, 13, 13, 13],
            [15, 16, 16, 16, 17, 17, 17, 18, 18, 18, 18],
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(to_compare_array(result), expected, atol=1e-3)


def test_regrid_bilinear_2():
    cube_in, cube_out_mask, _ = _define_source_target_grid_data()
    result = RegridLandSea(regrid_mode="bilinear-2")(cube_in, cube_out_mask)
    expected = np.array(
        [
            [0.5, 0.8, 1.1, 1.4, 1.7, 2.0, 2.3, 2.6, 2.9, 3.2, 3.5],
            [2.5, 2.8, 3.1, 3.4, 3.7, 4.0, 4.3, 4.6, 4.9, 5.2, 5.5],
            [4.5, 4.8, 5.1, 5.4, 5.7, 6.0, 6.3, 6.6, 6.9, 7.2, 7.5],
            [6.5, 6.8, 7.1, 7.4, 7.7, 8.0, 8.3, 8.6, 8.9, 9.2, 9.5],
            [8.5, 8.8, 9.1, 9.4, 9.7, 10.0, 10.3, 10.6, 10.9, 11.2, 11.5],
            [10.5, 10.8, 11.1, 11.4, 11.7, 12.0, 12.3, 12.6, 12.9, 13.2, 13.5],
            [12.5, 12.8, 13.1, 13.4, 13.7, 14.0, 14.3, 14.6, 14.9, 15.2, 15.5],
            [14.5, 14.8, 15.1, 15.4, 15.7, 16.0, 16.3, 16.6, 16.9, 17.2, 17.5],
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(to_compare_array(result), expected, atol=1e-3)


def test_regrid_nearest_with_mask_2():
    cube_in, cube_out_mask, cube_in_mask = _define_source_target_grid_data()
    result = RegridLandSea(
        regrid_mode="nearest-with-mask-2",
        landmask=cube_in_mask,
        landmask_vicinity=250000000,
    )(cube_in, cube_out_mask)
    expected = np.array(
        [
            [0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3],
            [0, 1, 1, 1, 7, 2, 7, 3, 3, 3, 3],
            [5, 6, 6, 6, 7, 7, 7, 8, 8, 8, 8],
            [5, 6, 6, 6, 7, 7, 7, 8, 8, 8, 9],
            [10, 11, 11, 11, 7, 7, 7, 8, 8, 8, 14],
            [10, 11, 11, 11, 12, 12, 12, 13, 13, 13, 14],
            [10, 11, 11, 11, 12, 12, 7, 13, 13, 13, 14],
            [15, 16, 16, 16, 17, 17, 7, 18, 18, 18, 19],
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(to_compare_array(result), expected, atol=1e-3)

    # 常数场
    const_in = make_meb6d(
        np.ones((4, 5), dtype=np.float32),
        lats=cube_in.coords["lat"].values,
        lons=cube_in.coords["lon"].values,
        name="air_temperature",
        units="C",
    )
    result_const = RegridLandSea(
        regrid_mode="nearest-with-mask-2",
        landmask=cube_in_mask,
        landmask_vicinity=250000000,
    )(const_in, cube_out_mask)
    np.testing.assert_allclose(to_compare_array(result_const), 1.0, atol=1e-3)


def test_regrid_bilinear_with_mask_2():
    cube_in, cube_out_mask, cube_in_mask = _define_source_target_grid_data()
    result = RegridLandSea(
        regrid_mode="bilinear-with-mask-2",
        landmask=cube_in_mask,
        landmask_vicinity=250000000,
    )(cube_in, cube_out_mask)
    expected = np.array(
        [
            [0.5, 0.8, 1.401, 3.292, 2.0, 2.0, 2.0, 4.943, 3.256, 3.2, 3.5],
            [2.5, 2.8, 3.1, 3.4, 5.489, 2.763, 6.329, 4.6, 4.9, 5.2, 5.5],
            [4.5, 4.8, 5.1, 5.4, 5.7, 7.015, 6.3, 6.6, 6.9, 7.2, 7.5],
            [6.5, 6.8, 7.1, 7.4, 7.7, 7.0, 7.19, 7.668, 7.662, 9.2, 9.5],
            [8.5, 8.8, 9.1, 9.4, 8.106, 7.0, 7.0, 7.629, 7.217, 9.114, 10.524],
            [10.5, 10.8, 11.0, 11.012, 13.154, 12.0, 12.3, 12.6, 12.9, 13.713, 15.745],
            [
                12.5,
                12.8,
                12.234,
                13.259,
                14.142,
                14.0,
                8.073,
                14.6,
                14.9,
                14.963,
                16.333,
            ],
            [14.5, 14.8, 15.1, 14.227, 15.509, 16.0, 9.873, 16.6, 16.9, 16.911, 17.038],
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(to_compare_array(result), expected, atol=1e-3)

    const_in = make_meb6d(
        np.ones((4, 5), dtype=np.float32),
        lats=cube_in.coords["lat"].values,
        lons=cube_in.coords["lon"].values,
        name="air_temperature",
        units="C",
    )
    result_const = RegridLandSea(
        regrid_mode="bilinear-with-mask-2",
        landmask=cube_in_mask,
        landmask_vicinity=250000000,
    )(const_in, cube_out_mask)
    np.testing.assert_allclose(to_compare_array(result_const), 1.0, atol=1e-3)


@pytest.mark.parametrize("regridder", ("nearest", "bilinear"))
@pytest.mark.parametrize("landmask", (True, False))
def test_target_domain_bigger_than_source_domain(regridder, landmask):
    """目标域大于源域时，域外应为 NaN；内域与未扩展结果一致。"""
    cube_in, cube_out_mask, cube_in_mask = _define_source_target_grid_data_same_domain()

    # 四周各扩 2/4 个格点，模拟更大目标域
    width_x, width_y = 2, 4
    out_lats = cube_out_mask.coords["lat"].values
    out_lons = cube_out_mask.coords["lon"].values
    dlat = float(out_lats[1] - out_lats[0])
    dlon = float(out_lons[1] - out_lons[0])
    pad_lats = np.concatenate(
        [
            out_lats[0] - dlat * np.arange(width_y, 0, -1),
            out_lats,
            out_lats[-1] + dlat * np.arange(1, width_y + 1),
        ]
    ).astype(np.float32)
    pad_lons = np.concatenate(
        [
            out_lons[0] - dlon * np.arange(width_x, 0, -1),
            out_lons,
            out_lons[-1] + dlon * np.arange(1, width_x + 1),
        ]
    ).astype(np.float32)
    pad_mask = np.zeros((len(pad_lats), len(pad_lons)), dtype=np.float32)
    pad_mask[width_y:-width_y, width_x:-width_x] = to_compare_array(cube_out_mask)
    cube_out_mask_pad = make_meb6d(
        pad_mask, lats=pad_lats, lons=pad_lons, name="land_binary_mask", units="1"
    )

    with_mask = "-with-mask" if landmask else ""
    mask_arg = cube_in_mask if landmask else None
    mode = f"{regridder}{with_mask}-2"
    plugin = RegridLandSea(
        regrid_mode=mode, landmask=mask_arg, landmask_vicinity=250000000
    )
    regrid_out = plugin(cube_in, cube_out_mask)
    regrid_out_pad = plugin(cube_in, cube_out_mask_pad)

    inner = to_compare_array(regrid_out_pad)[width_y:-width_y, width_x:-width_x]
    np.testing.assert_allclose(to_compare_array(regrid_out), inner)

    padded = to_compare_array(regrid_out_pad).copy()
    padded[width_y:-width_y, width_x:-width_x] = np.nan
    assert np.isnan(padded).all()
