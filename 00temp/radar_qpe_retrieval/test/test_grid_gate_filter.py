#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""qpe 本地 GridGateFilter 基本行为测试。"""

from __future__ import annotations

import numpy as np
import meteva_base as meb

from radar_qpe_retrieval.utils.grid_gate_filter import GridGateFilter


def _build_grid(data: np.ndarray) -> meb.grid_data:
    nlat, nlon = data.shape
    grid = meb.grid(
        [0, nlon - 1, 1],
        [0, nlat - 1, 1],
        gtime=["2020010100"],
        dtime_list=[0],
        level_list=[0],
        member_list=["radar"],
    )
    return meb.grid_data(grid=grid, data=np.asarray(data, dtype=np.float32))


def test_exclude_below_and_outside_for_cref_qc_style():
    """覆盖 cinrad_meb CREF QC 常用的 exclude 规则。"""
    cref = _build_grid(
        np.array(
            [[np.nan, 10.0, 40.0, 90.0], [20.0, 25.0, 30.0, 35.0]],
            dtype=np.float32,
        )
    )
    gatefilter = GridGateFilter(cref)
    gatefilter.exclude_invalid(cref)
    gatefilter.exclude_below(cref, 15.0)
    gatefilter.exclude_outside(cref, 0.0, 80.0)

    included = gatefilter.gate_included
    assert included.shape == (2, 4)
    # NaN / <15 / >80 应排除；其余保留
    np.testing.assert_array_equal(
        included,
        np.array(
            [[False, False, True, False], [True, True, True, True]],
            dtype=bool,
        ),
    )


def test_exclude_transition_marks_whole_rays():
    """天线过渡旗标为 1 的整条 ray 应被排除。"""
    field = _build_grid(
        np.array([[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]], dtype=np.float32)
    )
    field = field.assign_coords(
        antenna_transition=("lat", np.array([0, 1], dtype=np.int8))
    )
    gatefilter = GridGateFilter(field)
    gatefilter.exclude_transition()
    excluded = gatefilter.gate_excluded
    np.testing.assert_array_equal(excluded[0], [False, False, False, False])
    np.testing.assert_array_equal(excluded[1], [True, True, True, True])


def test_from_mask_and_no_region_dealias_import():
    """from_mask 可用，且本测试不依赖 region_dealias。"""
    field = _build_grid(np.ones((2, 3), dtype=np.float32))
    mask = np.array([[True, False, False], [False, True, False]], dtype=bool)
    gatefilter = GridGateFilter.from_mask(field, mask)
    np.testing.assert_array_equal(gatefilter.gate_excluded, mask)
