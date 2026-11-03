#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""echo_class 插件类测试。"""

from __future__ import annotations

import numpy as np
import xarray as xr

from radar_echo_classification.src.echo_class import (
    ConvStratRautPlugin,
    FeatureDetectionPlugin,
    HydroclassSemisupervisedPlugin,
    SteinerConvStratPlugin,
)


def _make_refl_grid():
    levels = np.array([0.0, 3000.0], dtype=np.float32)
    lat = np.linspace(30.0, 30.09, 10, dtype=np.float32)
    lon = np.linspace(100.0, 100.09, 10, dtype=np.float32)
    data = np.full((1, 2, 1, 1, 10, 10), 20.0, dtype=np.float32)
    data[0, 1, 0, 0, 4:7, 4:7] = 45.0

    return xr.DataArray(
        data,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": ["m0"],
            "level": levels,
            "time": [np.datetime64("2024-01-01T00:00:00")],
            "dtime": [0],
            "lat": lat,
            "lon": lon,
        },
        name="reflectivity",
    )


def test_steiner_conv_strat_plugin_returns_grid():
    refl = _make_refl_grid()
    plugin = SteinerConvStratPlugin(dx=1000.0, dy=1000.0, work_level=3000.0)

    result = plugin(refl)

    assert result.name == "echo_classification"
    assert result.shape[-2:] == refl.shape[-2:]


def test_feature_detection_plugin_returns_result_dict():
    refl = _make_refl_grid()
    plugin = FeatureDetectionPlugin(dx=1000.0, dy=1000.0, level_m=3000.0)

    result = plugin(refl)

    assert set(result) == {"feature_detection", "feature_under", "feature_over"}
    assert result["feature_detection"].shape[-2:] == refl.shape[-2:]


def test_hydroclass_semisupervised_plugin_returns_result_dict_without_relh():
    refl = _make_refl_grid()
    zdr = xr.full_like(refl, 0.5)
    rhv = xr.full_like(refl, 0.98)
    kdp = xr.full_like(refl, 0.3)
    mass_centers = np.array(
        [[25.0, 0.1, 0.1, 0.95], [35.0, 1.0, 0.5, 0.90]],
        dtype=np.float32,
    )
    weights = np.array([1.0, 1.0, 1.0, 0.75], dtype=np.float32)
    plugin = HydroclassSemisupervisedPlugin(
        var_names=("Zh", "ZDR", "KDP", "RhoHV"),
        mass_centers=mass_centers,
        weights=weights,
    )

    result = plugin(refl=refl, zdr=zdr, rhv=rhv, kdp=kdp)

    assert set(result) == {"hydro"}
    assert result["hydro"].shape == refl.shape


def test_conv_strat_raut_plugin_returns_grid():
    refl = _make_refl_grid()
    plugin = ConvStratRautPlugin(cappi_level=0)

    result = plugin(refl)

    assert result.name == "wt_reclass"
    assert result.shape[-2:] == refl.shape[-2:]
