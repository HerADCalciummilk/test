#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""迁移版 echo_class 函数测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radar_echo_classification.src.utils._echo_class import _feature_detection, steiner_class_buff
from radar_echo_classification.src.utils._echo_class_wt import (
    calc_scale_break,
    conv_wavelet_sum,
    label_classes,
)
from radar_echo_classification.src.utils._hydro_utils import (
    _assign_to_class,
    _compute_coeff_transform,
    _get_mass_centers,
    _standardize,
)

from radar_echo_classification.src.echo_class import (
    conv_strat_raut,
    feature_detection,
    hydroclass_semisupervised,
    steiner_conv_strat,
)


def _make_refl_grid():
    levels = np.array([1000.0, 3000.0, 5000.0], dtype=np.float32)
    lat = np.array([30.00, 30.01, 30.02, 30.03, 30.04], dtype=np.float32)
    lon = np.array([100.00, 100.01, 100.02, 100.03, 100.04], dtype=np.float32)

    data = np.full((1, 3, 1, 1, 5, 5), 18.0, dtype=np.float32)
    data[0, 1, 0, 0, 2, 2] = 45.0
    data[0, 1, 0, 0, 1:4, 1:4] += 10.0
    data[0, 2, 0, 0, 2, 2] = 35.0

    return xr.DataArray(
        data,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": levels,
            "time": [np.datetime64("2024-01-01T00:00:00")],
            "dtime": [0],
            "lat": lat,
            "lon": lon,
        },
        name="reflectivity",
    )


def _make_hydro_inputs():
    refl = _make_refl_grid()
    zdr = xr.full_like(refl, 0.5)
    rhv = xr.full_like(refl, 0.98)
    kdp = xr.full_like(refl, 0.3)
    temp = xr.full_like(refl, -5.0)

    zdr.values[0, 1, 0, 0, 2, 2] = 2.0
    kdp.values[0, 1, 0, 0, 2, 2] = 1.5
    temp.values[0, 0, 0, 0, :, :] = 2.0
    temp.values[0, 1, 0, 0, :, :] = -2.0
    temp.values[0, 2, 0, 0, :, :] = -10.0

    return refl, zdr, rhv, kdp, temp


def _get_xy_and_resolutions(grid):
    lon = grid.lon.values.astype(np.float64)
    lat = grid.lat.values.astype(np.float64)
    lat_mean = float(np.nanmean(lat))
    x = (lon - lon[0]) * 111000.0 * np.cos(np.deg2rad(lat_mean))
    y = (lat - lat[0]) * 111000.0
    dx = float(np.mean(np.abs(np.diff(x))))
    dy = float(np.mean(np.abs(np.diff(y))))
    return x.astype(np.float32), y.astype(np.float32), dx, dy


def test_steiner_conv_strat_matches_pyart_core():
    """Steiner 分类结果应与底层 Py-ART 实现一致。"""
    refl = _make_refl_grid()
    x, y, dx, dy = _get_xy_and_resolutions(refl)
    z = refl.level.values.astype(np.float32)
    volume = refl.values[0, :, 0, 0, :, :]

    result = steiner_conv_strat(refl, dx=dx, dy=dy, work_level=3000.0)
    expected = steiner_class_buff(
        volume,
        x,
        y,
        z,
        dx=dx,
        dy=dy,
        bkg_rad=11000.0,
        work_level=3000.0,
        intense=42.0,
        peak_relation="default",
        area_relation="medium",
        use_intense=True,
    )

    assert result.shape[-2:] == expected.shape
    assert result.name == "echo_classification"
    np.testing.assert_array_equal(result.values[0, 0, 0, 0, :, :], expected.astype(np.float32))


def test_steiner_conv_strat_inherits_provenance_not_frequency():
    """分类输出应继承站点溯源属性，补齐 meb 默认属性，但不继承 frequency。"""
    refl = _make_refl_grid()
    _, _, dx, dy = _get_xy_and_resolutions(refl)
    refl.attrs["site_code"] = "Z9010"
    refl.attrs["scan_time"] = "2025-07-24 19:24:00"
    refl.attrs["frequency"] = 2.87e9
    refl.attrs["units"] = "dBZ"

    result = steiner_conv_strat(refl, dx=dx, dy=dy, work_level=3000.0)

    assert result.attrs["site_code"] == "Z9010"
    assert result.attrs["scan_time"] == "2025-07-24 19:24:00"
    assert "frequency" not in result.attrs
    assert result.attrs["units"] == ""
    assert result.attrs["dtime_units"] == "hour"
    assert "time_type" in result.attrs
    assert result.attrs["long_name"] == "Steiner echo classification"
    assert result.attrs["standard_name"] == "echo_classification"


def test_hydroclass_semisupervised_inherits_provenance_not_frequency():
    """水凝物分类输出可从输入读 frequency 选质心，但结果 attrs 不继承 frequency。"""
    refl, zdr, rhv, kdp, temp = _make_hydro_inputs()
    for grid in (refl, zdr, rhv, kdp, temp):
        grid.attrs["site_code"] = "Z9010"
        grid.attrs["frequency"] = 5.6e9
        grid.attrs["units"] = "dBZ"

    result = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        radar_freq=None,
        compute_entropy=False,
        vectorize=False,
    )
    hydro = result["hydro"]

    assert hydro.attrs["site_code"] == "Z9010"
    assert "frequency" not in hydro.attrs
    assert hydro.attrs["units"] == ""
    assert hydro.attrs["dtime_units"] == "hour"
    assert hydro.attrs["long_name"] == "Hydrometeor classification"


def test_feature_detection_returns_expected_keys_and_values():
    """feature_detection 应返回主结果及高估低估结果。"""
    refl = _make_refl_grid()
    _, _, dx, dy = _get_xy_and_resolutions(refl)
    field_2d = refl.values[0, 1, 0, 0, :, :]

    result = feature_detection(refl, dx=dx, dy=dy, level_m=3000.0, estimate_flag=True)
    _, _, expected = _feature_detection(field_2d, dx, dy)

    assert set(result.keys()) == {"feature_detection", "feature_under", "feature_over"}
    assert result["feature_detection"].name == "feature_detection"
    np.testing.assert_array_equal(
        result["feature_detection"].values[0, 0, 0, 0, :, :],
        expected.astype(np.float32),
    )


def test_hydroclass_semisupervised_returns_hydro_grid():
    """水凝物分类应返回与输入同形状的分类网格。"""
    refl, zdr, rhv, kdp, temp = _make_hydro_inputs()

    result = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        radar_freq=5.6e9,
        compute_entropy=False,
        vectorize=False,
    )

    assert set(result.keys()) == {"hydro"}
    assert result["hydro"].shape == refl.shape
    assert result["hydro"].name == "radar_echo_classification"
    assert np.nanmax(result["hydro"].values) <= 9
    assert np.nanmin(result["hydro"].values) >= 0


def test_hydroclass_semisupervised_reads_frequency_from_attrs():
    """未传 radar_freq 时应从输入网格 attrs['frequency'] 选择质心频段。"""
    refl, zdr, rhv, kdp, temp = _make_hydro_inputs()
    # X 波段频率（与默认 C 波段质心不同）
    x_freq = 9.5e9
    refl_attr = refl.copy(deep=True)
    zdr_attr = zdr.copy(deep=True)
    rhv_attr = rhv.copy(deep=True)
    kdp_attr = kdp.copy(deep=True)
    temp_attr = temp.copy(deep=True)
    for grid in (refl_attr, zdr_attr, rhv_attr, kdp_attr, temp_attr):
        grid.attrs["frequency"] = x_freq

    from_attrs = hydroclass_semisupervised(
        refl_attr,
        zdr_attr,
        rhv_attr,
        kdp_attr,
        temp=temp_attr,
        radar_freq=None,
        compute_entropy=False,
        vectorize=False,
    )
    from_param = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        radar_freq=x_freq,
        compute_entropy=False,
        vectorize=False,
    )

    np.testing.assert_array_equal(
        from_attrs["hydro"].values,
        from_param["hydro"].values,
    )


def test_hydroclass_semisupervised_attrs_frequency_overrides_radar_freq():
    """输入 attrs['frequency'] 优先于显式 radar_freq。"""
    refl, zdr, rhv, kdp, temp = _make_hydro_inputs()
    x_freq = 9.5e9
    c_freq = 5.6e9
    for grid in (refl, zdr, rhv, kdp, temp):
        grid.attrs["frequency"] = x_freq

    # attrs 为 X，参数故意传 C：应仍按 X 质心分类
    mixed = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        radar_freq=c_freq,
        compute_entropy=False,
        vectorize=False,
    )
    expected_x = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        mass_centers=_get_mass_centers(x_freq),
        compute_entropy=False,
        vectorize=False,
    )
    expected_c = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        mass_centers=_get_mass_centers(c_freq),
        compute_entropy=False,
        vectorize=False,
    )

    np.testing.assert_array_equal(mixed["hydro"].values, expected_x["hydro"].values)
    assert not np.array_equal(mixed["hydro"].values, expected_c["hydro"].values)


def test_hydroclass_semisupervised_defaults_to_c_band_without_frequency():
    """无 frequency 属性且未传 radar_freq 时回退 C 波段默认质心。"""
    refl, zdr, rhv, kdp, temp = _make_hydro_inputs()

    with pytest.warns(UserWarning, match="Radar frequency is unknown"):
        result = hydroclass_semisupervised(
            refl,
            zdr,
            rhv,
            kdp,
            temp=temp,
            radar_freq=None,
            compute_entropy=False,
            vectorize=False,
        )
    expected = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        radar_freq=5.6e9,
        compute_entropy=False,
        vectorize=False,
    )

    np.testing.assert_array_equal(result["hydro"].values, expected["hydro"].values)


def test_hydroclass_semisupervised_four_variable_mode_runs():
    """4变量模式（无 relH）应可正常运行并返回 hydro 字段。"""
    refl, zdr, rhv, kdp, _ = _make_hydro_inputs()
    mass_centers = _get_mass_centers(5.6e9)[:, :4]
    weights = np.array([1.0, 1.0, 1.0, 0.75], dtype=np.float32)

    result = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        var_names=("Zh", "ZDR", "KDP", "RhoHV"),
        mass_centers=mass_centers,
        weights=weights,
        radar_freq=5.6e9,
        compute_entropy=False,
        vectorize=True,
    )

    assert set(result.keys()) == {"hydro"}
    assert result["hydro"].shape == refl.shape


def test_hydroclass_semisupervised_entropy_matches_internal_logic():
    """水凝物分类熵结果应与内部分类逻辑一致。"""
    refl, zdr, rhv, kdp, temp = _make_hydro_inputs()

    result = hydroclass_semisupervised(
        refl,
        zdr,
        rhv,
        kdp,
        temp=temp,
        radar_freq=5.6e9,
        compute_entropy=True,
        output_distances=False,
        vectorize=False,
    )

    scan_refl = np.ma.masked_invalid(refl.values.astype(np.float32).reshape(-1, refl.shape[-1]))
    scan_zdr = np.ma.masked_invalid(zdr.values.astype(np.float32).reshape(-1, zdr.shape[-1]))
    scan_rhv = np.ma.masked_invalid(rhv.values.astype(np.float32).reshape(-1, rhv.shape[-1]))
    scan_kdp = np.ma.masked_invalid(kdp.values.astype(np.float32).reshape(-1, kdp.shape[-1]))
    scan_temp = np.ma.masked_invalid(temp.values.astype(np.float32).reshape(-1, temp.shape[-1]))

    mass_centers = _get_mass_centers(5.6e9)
    fields_dict = {
        "Zh": _standardize(scan_refl.copy(), "Zh"),
        "ZDR": _standardize(scan_zdr.copy(), "ZDR"),
        "KDP": _standardize(scan_kdp.copy(), "KDP"),
        "RhoHV": _standardize(scan_rhv.copy(), "RhoHV"),
        "relH": _standardize((scan_temp * (1000.0 / -6.5)).copy(), "relH"),
    }
    mc_std = np.empty_like(mass_centers, dtype=np.float32)
    for i, name in enumerate(("Zh", "ZDR", "KDP", "RhoHV", "relH")):
        mc_std[:, i] = _standardize(mass_centers[:, i].copy(), name)
    t_vals = _compute_coeff_transform(mc_std, weights=np.array([1.0, 1.0, 1.0, 0.75, 0.5]), value=50.0)
    _, entropy_expected, _ = _assign_to_class(fields_dict, mc_std, weights=np.array([1.0, 1.0, 1.0, 0.75, 0.5]), t_vals=t_vals)

    np.testing.assert_allclose(
        result["entropy"].values,
        np.ma.filled(entropy_expected, np.nan).reshape(refl.shape).astype(np.float32),
        equal_nan=True,
    )


def test_conv_strat_raut_matches_wavelet_components():
    """Raut 小波分类应与底层小波分类逻辑一致。"""
    refl = _make_refl_grid()
    _, _, dx, _ = _get_xy_and_resolutions(refl)
    field_2d = refl.values[0, 0, 0, 0, :, :]

    result = conv_strat_raut(refl, cappi_level=0)

    scale_break = calc_scale_break(res_meters=dx, conv_scale_km=25)
    wt_sum = conv_wavelet_sum(field_2d.copy(), 200, 1.6, scale_break)
    expected = label_classes(wt_sum, field_2d, 5, 1.5, 5, 25, 42)

    np.testing.assert_allclose(
        result.values[0, 0, 0, 0, :, :],
        np.asarray(expected, dtype=np.float32),
        equal_nan=True,
    )
