# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CalculateForecastBias / evaluate_additive_error 合成单测。"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import numpy.ma as ma
import pytest
import xarray as xr

from simple_bias_correction.src.simple_bias_correction import (
    CalculateForecastBias,
    evaluate_additive_error,
)

ATTRIBUTES = {
    "title": "Test forecast dataset",
    "source": "IMPROVER",
    "institution": "Australian Bureau of Meteorology",
}

# 有效时刻锚点；预报 dtime=3h 时起报 = VALID_TIME - 3h
VALID_TIME = datetime(2022, 12, 6, 3, 0)


def generate_dataset(
    num_frts: int = 1,
    *,
    truth_dataset: bool = False,
    data: np.ndarray | None = None,
    masked: bool = False,
) -> tuple[xr.DataArray, np.ndarray | bool]:
    """生成合成历史预报或实况（标准 meb 六维）。"""
    attributes = ATTRIBUTES.copy()
    if truth_dataset:
        period_h = 0.0
        attributes["title"] = "Test truth dataset"
        time_vals = [
            np.datetime64(VALID_TIME - i * timedelta(days=1)) for i in range(num_frts)
        ]
    else:
        period_h = 3.0
        time_vals = [
            np.datetime64(
                VALID_TIME - timedelta(hours=int(period_h)) - i * timedelta(days=1)
            )
            for i in range(num_frts)
        ]

    if data is None:
        data = np.ones((4, 3), dtype=np.float32)
    data = np.asarray(data, dtype=np.float32)
    data_mask: np.ndarray | bool = False
    if masked:
        masked_data = ma.masked_array(data.copy())
        masked_data.mask = np.zeros(data.shape, dtype=bool)
        if truth_dataset:
            masked_data.mask[:, -1] = True
        else:
            masked_data.mask[0, :] = True
        data_mask = np.array(masked_data.mask, copy=True)
        data = masked_data

    rng = np.random.default_rng(0)
    ny, nx = np.asarray(data).shape[-2:]
    stack = []
    for _ in time_vals:
        if (num_frts > 1) and (not truth_dataset):
            noise = rng.normal(0.0, 0.1, np.asarray(data).shape).astype(np.float32)
            data_slice = np.asarray(data) + noise
            if masked:
                data_slice = ma.masked_array(data_slice, mask=data.mask)
        else:
            data_slice = data

        values = np.asarray(data_slice, dtype=np.float32).copy()
        if isinstance(data_slice, ma.MaskedArray):
            values[ma.getmaskarray(data_slice)] = np.nan
        stack.append(values)

    # (time, lat, lon) → (member, level, time, dtime, lat, lon)
    arr = np.stack(stack, axis=0)[np.newaxis, np.newaxis, :, np.newaxis, :, :]
    merged = xr.DataArray(
        arr.astype(np.float32),
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": [0.0],
            "time": np.array(time_vals),
            "dtime": [np.float32(period_h)],
            "lat": np.arange(ny, dtype=np.float32),
            "lon": np.arange(nx, dtype=np.float32),
        },
        name="air_temperature",
        attrs=dict(attributes),
    )
    merged.attrs.setdefault("units", "K")
    return merged, data_mask


@pytest.mark.parametrize("num_frt", (1, 30))
@pytest.mark.parametrize("mask_truth", (False, True))
@pytest.mark.parametrize("mask_forecast", (False, True))
def test_evaluate_additive_error(num_frt, mask_truth, mask_forecast):
    """加性误差应接近给定 diff（允许历史噪声容差）。"""
    data = 273.0 + np.array(
        [[1.0, 2.0, 2.0], [2.0, 1.0, 3.0], [3.0, 3.0, 3.0]], dtype=np.float32
    )
    diff = np.array(
        [[0.0, 0.0, 0.0], [-1.0, 1.0, 0.0], [-2.0, 0.0, 1.0]], dtype=np.float32
    )
    truth_data = data - diff

    historic_forecasts, forecasts_mask = generate_dataset(
        num_frt, data=data, masked=mask_forecast
    )
    truths, truths_mask = generate_dataset(
        num_frt, truth_dataset=True, data=truth_data, masked=mask_truth
    )

    result = evaluate_additive_error(historic_forecasts, truths, collapse_dim="time")
    # 去掉长度为 1 的 leading 维便于与二维 diff 比较
    result_2d = np.squeeze(result)
    if mask_forecast or mask_truth:
        expected_mask = np.ma.mask_or(
            np.asarray(forecasts_mask, dtype=bool),
            np.asarray(truths_mask, dtype=bool),
        )
        assert np.all(np.isnan(result_2d) == expected_mask)
        valid = ~np.isnan(result_2d)
        assert np.allclose(result_2d[valid], diff[valid], atol=0.05)
    else:
        assert np.allclose(result_2d, diff, atol=0.05)


def test_evaluate_additive_error_numpy():
    """ndarray 路径：leading 维视为 time 并求平均。"""
    fc = np.arange(12, dtype=np.float32).reshape(2, 2, 3)
    tr = fc - 1.0
    result = evaluate_additive_error(fc, tr, collapse_dim="time")
    np.testing.assert_allclose(result, np.ones((2, 3), dtype=np.float32))


def test_evaluate_additive_error_converts_truth_units():
    """实况与预报单位不同时，应按预报单位换算后求差。"""
    historic_forecasts, _ = generate_dataset(1)
    truths, _ = generate_dataset(1, truth_dataset=True)
    fc = historic_forecasts.copy(deep=True)
    fc.values[...] = 283.15
    fc.attrs["units"] = "K"
    tr = truths.copy(deep=True)
    tr.values[...] = 10.0
    tr.attrs["units"] = "celsius"
    result = evaluate_additive_error(fc, tr, collapse_dim="time")
    np.testing.assert_allclose(np.squeeze(result), 0.0, atol=1e-4)


def test_evaluate_additive_error_incompatible_units_raises():
    """不可换算单位应报错。"""
    historic_forecasts, _ = generate_dataset(1)
    truths, _ = generate_dataset(1, truth_dataset=True)
    fc = historic_forecasts.copy(deep=True)
    fc.attrs["units"] = "K"
    tr = truths.copy(deep=True)
    tr.attrs["units"] = "m s-1"
    with pytest.raises(ValueError, match="单位不兼容"):
        evaluate_additive_error(fc, tr, collapse_dim="time")


@pytest.mark.parametrize("num_frt", (1, 4))
def test_define_metadata(num_frt):
    """偏差场 title 应为 Forecast bias data，并保留强制属性。"""
    reference_forecast, _ = generate_dataset(num_frt)
    expected = {
        "title": "Forecast bias data",
        "source": "IMPROVER",
        "institution": "Australian Bureau of Meteorology",
    }
    actual = CalculateForecastBias()._define_metadata(reference_forecast)
    assert actual == expected


@pytest.mark.parametrize("num_frt", (1, 4))
def test_create_bias_template(num_frt):
    """偏差壳应为 meb 前四维长度 1，并按多/单起报设置 time_bounds。"""
    reference_forecast, _ = generate_dataset(num_frt)
    # 模板路径与 process 一致：先 squeeze 长度 1 的 member/level
    squeezed = CalculateForecastBias()._ensure_single_valued_forecast(
        reference_forecast
    )
    result = CalculateForecastBias()._create_bias_template(squeezed)

    assert result.dims[:4] == ("member", "level", "time", "dtime")
    assert all(result.sizes[d] == 1 for d in ("member", "level", "time", "dtime"))
    assert result.name == f"forecast_error_of_{reference_forecast.name}"
    assert result.dtype == reference_forecast.dtype

    time_vals = reference_forecast["time"].values
    expected_point = max(np.datetime64(v) for v in time_vals)
    assert np.datetime64(result["time"].values.ravel()[0]) == expected_point

    if num_frt > 1:
        bounds = result.attrs["time_bounds"]
        assert np.datetime64(bounds[0]) == min(np.datetime64(v) for v in time_vals)
        assert np.datetime64(bounds[1]) == expected_point
    else:
        assert "time_bounds" not in result.attrs


@pytest.mark.parametrize("num_fcst_frt", (1, 50))
@pytest.mark.parametrize("num_truth_frt", (1, 48, 50))
@pytest.mark.parametrize("mask_truth", (False, True))
@pytest.mark.parametrize("mask_forecast", (False, True))
def test_process(num_fcst_frt, num_truth_frt, mask_truth, mask_forecast):
    """process 在不同历史长度下应给出近零偏差（合成数据期望）。"""
    reference_forecast, forecasts_mask = generate_dataset(
        num_fcst_frt, masked=mask_forecast
    )
    truth, truth_mask = generate_dataset(
        num_truth_frt, truth_dataset=True, masked=mask_truth
    )

    result = CalculateForecastBias().process(reference_forecast, truth)

    matched_n = min(num_fcst_frt, num_truth_frt)
    expected_times = reference_forecast["time"].values[:matched_n]
    expected_point = max(np.datetime64(v) for v in expected_times)
    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert all(result.sizes[d] == 1 for d in ("member", "level", "time", "dtime"))
    assert np.datetime64(result["time"].values.ravel()[0]) == expected_point

    if matched_n == 1:
        assert "time_bounds" not in result.attrs
    else:
        bounds = result.attrs["time_bounds"]
        assert np.datetime64(bounds[0]) == min(np.datetime64(v) for v in expected_times)
        assert np.datetime64(bounds[1]) == expected_point

    expected_tol = 0.2 if (num_truth_frt == 1 and num_fcst_frt > 1) else 0.05
    result_2d = np.squeeze(result.values)
    valid = ~np.isnan(result_2d)
    assert np.allclose(result_2d[valid], 0.0, atol=expected_tol)

    if mask_forecast or mask_truth:
        expected_mask = np.ma.mask_or(
            np.asarray(forecasts_mask, dtype=bool),
            np.asarray(truth_mask, dtype=bool),
        )
        assert np.all(np.isnan(result_2d) == expected_mask)


def test_ensure_single_valued_forecast_rejects_multi_member():
    """多 member 应报错（对应原版 realization）。"""
    base, _ = generate_dataset(1)
    multi = xr.concat([base.isel(member=0), base.isel(member=0) + 1], dim="member")
    multi = multi.assign_coords(member=[0, 1])
    with pytest.raises(ValueError, match="Multiple member values"):
        CalculateForecastBias()._ensure_single_valued_forecast(multi)


def test_ensure_single_valued_forecast_rejects_probability_name():
    """单阈值概率（level=1）按变量名 probability_of_* 拒绝。"""
    base, _ = generate_dataset(1)
    prob = base.rename("probability_of_air_temperature_above_threshold")
    with pytest.raises(ValueError, match="probability data"):
        CalculateForecastBias()._ensure_single_valued_forecast(prob)


def test_ensure_single_valued_forecast_rejects_multi_level():
    """多 level（含 meb 下多阈值）应报错：非时间层次须单值。"""
    base, _ = generate_dataset(1)
    multi = xr.concat([base.isel(level=0), base.isel(level=0) + 1], dim="level")
    multi = multi.assign_coords(level=[0.0, 1000.0])
    with pytest.raises(ValueError, match="Multiple level values"):
        CalculateForecastBias()._ensure_single_valued_forecast(multi)


def test_ensure_single_valued_forecast_squeezes_unit_member_and_level():
    """长度为 1 的 member / level 维应被 squeeze。"""
    base, _ = generate_dataset(1)
    result = CalculateForecastBias()._ensure_single_valued_forecast(base)
    assert "member" not in result.dims
    assert "level" not in result.dims


def test_filter_constrains_time_and_dtime_together():
    """匹配成功后单样本截取，拼接后多日起报且锁定同一时效。"""
    from simple_bias_correction.src.utils._calibration_utilities import (
        filter_non_matching_by_valid_time,
    )

    frts = [
        np.datetime64(VALID_TIME - timedelta(hours=3) - timedelta(days=i))
        for i in range(2)
    ]
    # member, level, time, dtime, lat, lon
    data = np.ones((1, 1, 2, 2, 2, 2), dtype=np.float32)
    forecast = xr.DataArray(
        data,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": [0.0],
            "time": frts,
            "dtime": np.array([1.0, 3.0], dtype=np.float32),
            "lat": [0.0, 1.0],
            "lon": [0.0, 1.0],
        },
        name="air_temperature",
        attrs=ATTRIBUTES,
    )
    truth_times = [np.datetime64(VALID_TIME - timedelta(days=i)) for i in range(2)]
    truth = xr.DataArray(
        np.ones((1, 1, 2, 1, 2, 2), dtype=np.float32),
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": [0.0],
            "time": truth_times,
            "dtime": [np.float32(0.0)],
            "lat": [0.0, 1.0],
            "lon": [0.0, 1.0],
        },
        name="air_temperature",
        attrs=ATTRIBUTES,
    )

    hf, tr = filter_non_matching_by_valid_time(forecast, truth)
    assert hf.sizes["time"] == 2
    assert hf.sizes["dtime"] == 1
    assert float(hf["dtime"].values.ravel()[0]) == 3.0
    assert tr.sizes["dtime"] == 1
    for t in np.atleast_1d(hf["time"].values):
        assert str(np.datetime_as_string(np.datetime64(t), unit="h")).endswith("T00")
