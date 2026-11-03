# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""apply_additive_correction / ApplyBiasCorrection 合成单测。"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
import xarray as xr

from simple_bias_correction.src.simple_bias_correction import (
    ApplyBiasCorrection,
    apply_additive_correction,
)

VALID_TIME = datetime(2022, 12, 6, 3, 0)
DTIME_HOURS = 3.0

ATTRIBUTES = {
    "title": "Test forecast dataset",
    "source": "IMPROVER",
    "institution": "Australian Bureau of Meteorology",
}

RNG = np.random.default_rng(0)

TEST_FCST_DATA = np.array(
    [[1.0, 2.0, 2.0], [2.0, 1.0, 3.0], [1.0, 3.0, 3.0]], dtype=np.float32
) + RNG.normal(0.0, 1, (4, 3, 3)).astype(np.float32)

MEAN_BIAS_DATA = np.array(
    [[0.0, 0.0, 0.0], [-1.0, 1.0, 0.0], [-2.0, 0.0, 1.0]], dtype=np.float32
)

MASK = np.array(
    [[False, False, False], [True, False, False], [True, False, True]], dtype=bool
)


def _meb6d_field(
    data: np.ndarray,
    *,
    name: str,
    time: datetime,
    dtime_hours: float = DTIME_HOURS,
    attrs: dict | None = None,
    n_member: int = 1,
) -> xr.DataArray:
    """构造标准 meb 六维场；``data`` 为 (lat, lon) 或 (member, lat, lon)。"""
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]
    if arr.shape[0] != n_member:
        raise ValueError("data 的 member 维与 n_member 不一致。")
    # (member, lat, lon) → (member, 1, 1, 1, lat, lon)
    values = arr[:, np.newaxis, np.newaxis, np.newaxis, :, :]
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.arange(n_member, dtype=np.int32),
            "level": [0.0],
            "time": [np.datetime64(time)],
            "dtime": [np.float32(dtime_hours)],
            "lat": np.arange(arr.shape[-2], dtype=np.float32),
            "lon": np.arange(arr.shape[-1], dtype=np.float32),
        },
        name=name,
        attrs=dict(attrs or ATTRIBUTES),
    )


@pytest.fixture
def forecast_da() -> xr.DataArray:
    return _meb6d_field(
        TEST_FCST_DATA,
        name="wind_speed",
        time=VALID_TIME + timedelta(days=1) - timedelta(hours=3),
        n_member=4,
    )


def generate_bias_list(
    num_frts: int,
    *,
    single_frt_with_bounds: bool = False,
    last_frt: datetime | None = None,
    masked_data: bool = False,
) -> list[xr.DataArray]:
    """生成偏差 DataArray 列表（meb 六维，``time``=起报）。"""
    attributes = ATTRIBUTES.copy()
    attributes["title"] = "Forecast bias data"
    rng = np.random.default_rng(0)
    items: list[xr.DataArray] = []
    if last_frt is None:
        last_frt = VALID_TIME + timedelta(days=1) - timedelta(hours=3)

    for i in range(num_frts):
        if num_frts > 1:
            noise = rng.normal(0.0, 0.1, (3, 3)).astype(np.float32)
            data_slice = MEAN_BIAS_DATA + noise
        else:
            data_slice = MEAN_BIAS_DATA.copy()
        if masked_data:
            data_slice = data_slice.astype(np.float32).copy()
            data_slice[MASK] = np.nan

        items.append(
            _meb6d_field(
                data_slice,
                name="forecast_error_of_wind_speed",
                time=last_frt - timedelta(days=i),
                attrs=attributes,
                n_member=1,
            )
        )

    if single_frt_with_bounds and num_frts > 1:
        stacked = []
        times = []
        for da in items:
            t = np.asarray(da["time"].values).ravel()[0]
            times.append(np.datetime64(t))
            stacked.append(da)
        # 沿 time 维拼接（各场 time 长度已为 1）
        merged = xr.concat(stacked, dim="time", coords="different", compat="equals")
        mean_bias = merged.mean(dim="time", keep_attrs=True)
        if "time" in mean_bias.dims:
            mean_bias = mean_bias.isel(time=0, drop=True)
        mean_bias = mean_bias.expand_dims(time=[max(times)])
        mean_bias = mean_bias.astype(np.float32, copy=False)
        mean_bias.name = "forecast_error_of_wind_speed"
        mean_bias.attrs = dict(attributes)
        mean_bias.attrs["time_bounds"] = [
            np.datetime_as_string(min(times)),
            np.datetime_as_string(max(times)),
        ]
        mean_bias = mean_bias.transpose(
            "member", "level", "time", "dtime", "lat", "lon"
        )
        return [mean_bias]
    return items


@pytest.mark.parametrize("num_bias_inputs", (1, 30))
@pytest.mark.parametrize("masked_bias_data", (True, False))
@pytest.mark.parametrize("fill_masked_bias_data", (True, False))
def test_apply_additive_correction(
    forecast_da, num_bias_inputs, masked_bias_data, fill_masked_bias_data
):
    """加性订正数值应接近 forecast - mean_bias。"""
    bias = generate_bias_list(
        num_bias_inputs,
        single_frt_with_bounds=True,
        masked_data=masked_bias_data,
    )[0]

    expected = TEST_FCST_DATA - MEAN_BIAS_DATA
    if fill_masked_bias_data and masked_bias_data:
        expected = np.where(MASK, TEST_FCST_DATA, expected)

    result = np.squeeze(
        apply_additive_correction(forecast_da, bias, fill_masked_bias_data)
    )

    if masked_bias_data and not fill_masked_bias_data:
        assert np.all(np.isnan(result) == np.broadcast_to(MASK, result.shape))
        valid = ~np.isnan(result)
        assert np.allclose(result[valid], expected[valid], atol=0.05)
    else:
        assert np.allclose(result, expected, atol=0.05)


def test_apply_additive_correction_converts_bias_units():
    """偏差单位与预报不同时，应按预报单位换算后订正。"""
    fc = _meb6d_field(
        np.full((3, 3), 283.15, dtype=np.float32),
        name="air_temperature",
        time=VALID_TIME + timedelta(days=1) - timedelta(hours=3),
        n_member=1,
    )
    fc.attrs["units"] = "K"
    bias = _meb6d_field(
        np.full((3, 3), 10.0, dtype=np.float32),
        name="forecast_error_of_air_temperature",
        time=VALID_TIME + timedelta(days=1) - timedelta(hours=3),
    )
    bias.attrs["units"] = "celsius"
    result = np.squeeze(apply_additive_correction(fc, bias, fill_masked_bias_values=True))
    np.testing.assert_allclose(result, 0.0, atol=1e-4)


def test_init_sets_correction_method():
    """默认订正方法应为 apply_additive_correction。"""
    plugin = ApplyBiasCorrection()
    assert plugin._correction_method is apply_additive_correction


@pytest.mark.parametrize("single_input_frt", (False, True))
def test_get_mean_bias(single_input_frt):
    """多偏差平均后空间场接近 MEAN_BIAS_DATA。"""
    bias_list = generate_bias_list(30, single_frt_with_bounds=single_input_frt)
    result = ApplyBiasCorrection()._get_mean_bias(bias_list)
    assert result.sizes.get("time", 1) == 1 or "time" not in result.dims
    assert np.allclose(np.squeeze(result.values), MEAN_BIAS_DATA, atol=0.05)
    assert result.dtype == bias_list[0].dtype


@pytest.mark.parametrize("single_input_frt", (True, False))
def test_get_mean_bias_fails_on_inconsistent_bounds(single_input_frt):
    """混入带 bounds 的偏差后求平均应失败。"""
    input_list = []
    input_list.extend(generate_bias_list(2, single_frt_with_bounds=single_input_frt))
    input_list.extend(
        generate_bias_list(
            2,
            single_frt_with_bounds=True,
            last_frt=VALID_TIME
            + timedelta(days=1)
            - timedelta(hours=3)
            - timedelta(days=2),
        )
    )
    with pytest.raises(ValueError):
        ApplyBiasCorrection()._get_mean_bias(input_list)


@pytest.mark.parametrize("num_bias_inputs", (1, 5))
def test_inconsistent_bias_forecast_inputs(forecast_da, num_bias_inputs):
    """起报小时 / dtime 不一致应报错。"""
    plugin = ApplyBiasCorrection()
    base_frt = VALID_TIME + timedelta(days=1) - timedelta(hours=3)

    bias_list = generate_bias_list(
        num_bias_inputs,
        last_frt=base_frt + timedelta(hours=3),
        single_frt_with_bounds=True,
    )
    with pytest.raises(ValueError, match="valid-hour differ"):
        plugin._check_forecast_bias_consistent(forecast_da, bias_list)

    bias_list = generate_bias_list(
        num_bias_inputs, last_frt=base_frt, single_frt_with_bounds=False
    )
    bias_list.extend(
        generate_bias_list(
            num_bias_inputs,
            last_frt=base_frt - timedelta(hours=12),
            single_frt_with_bounds=False,
        )
    )
    with pytest.raises(ValueError, match="Multiple forecast_reference_time valid-hour"):
        plugin._check_forecast_bias_consistent(forecast_da, bias_list)

    bias_list = generate_bias_list(
        num_bias_inputs, last_frt=base_frt, single_frt_with_bounds=True
    )
    for i, da in enumerate(bias_list):
        dt0 = float(np.asarray(da["dtime"].values).ravel()[0])
        bias_list[i] = da.assign_coords(dtime=[np.float32(dt0 + 3.0)])
    with pytest.raises(ValueError, match="Forecast period differ"):
        plugin._check_forecast_bias_consistent(forecast_da, bias_list)

    bias_list = generate_bias_list(
        num_bias_inputs, last_frt=base_frt, single_frt_with_bounds=False
    )
    other = generate_bias_list(
        1,
        last_frt=base_frt - timedelta(days=6),
        single_frt_with_bounds=False,
    )[0]
    dt0 = float(np.asarray(other["dtime"].values).ravel()[0])
    other = other.assign_coords(dtime=[np.float32(dt0 + 3.0)])
    bias_list.append(other)
    with pytest.raises(ValueError, match="Multiple forecast period"):
        plugin._check_forecast_bias_consistent(forecast_da, bias_list)


@pytest.mark.parametrize("num_bias_inputs", (1, 30))
@pytest.mark.parametrize("single_input_frt", (False, True))
@pytest.mark.parametrize("lower_bound", (None, 1))
@pytest.mark.parametrize("upper_bound", (None, 4))
@pytest.mark.parametrize("masked_input_data", (True, False))
@pytest.mark.parametrize("masked_bias_data", (True, False))
@pytest.mark.parametrize("fill_masked_bias_data", (True, False))
def test_process(
    forecast_da,
    num_bias_inputs,
    single_input_frt,
    lower_bound,
    upper_bound,
    masked_input_data,
    masked_bias_data,
    fill_masked_bias_data,
):
    """process 在多种组合下数值与裁剪行为符合预期。"""
    bias_list = generate_bias_list(
        num_bias_inputs,
        single_frt_with_bounds=single_input_frt,
        masked_data=masked_bias_data,
    )
    forecast = forecast_da
    if masked_input_data:
        values = np.asarray(forecast.values, dtype=np.float32).copy()
        values[..., MASK] = np.nan
        forecast = forecast.copy(data=values)

    result = ApplyBiasCorrection(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        fill_masked_bias_values=fill_masked_bias_data,
    ).process(forecast, bias_list)

    expected = TEST_FCST_DATA - MEAN_BIAS_DATA
    if fill_masked_bias_data and masked_bias_data:
        expected = np.where(MASK, TEST_FCST_DATA, expected)
    if masked_input_data:
        expected = expected.copy()
        expected[:, MASK] = np.nan
    if lower_bound is not None:
        expected = np.maximum(lower_bound, expected)
    if upper_bound is not None:
        expected = np.minimum(upper_bound, expected)

    result_vals = np.squeeze(result.values)
    # 多 member：与 expected (member, lat, lon) 对齐
    if result_vals.ndim == 2:
        result_vals = result_vals[np.newaxis, ...]
    valid = ~np.isnan(result_vals)
    assert np.allclose(result_vals[valid], expected[valid], atol=0.05)
    assert result.dtype == forecast.dtype
    assert result.name == forecast.name


def test_no_bias_file(forecast_da):
    """无偏差输入时应告警并返回带 comment 的原预报。"""
    with pytest.warns(UserWarning, match=".*no forecast_error.*"):
        result = ApplyBiasCorrection()(forecast_da)
    assert "Warning: Calibration of this forecast has been attempted" in result.attrs[
        "comment"
    ]
    np.testing.assert_array_equal(result.values, forecast_da.values)


def test_missing_fcst_file():
    """仅有偏差、无预报时应报错。"""
    bias_list = generate_bias_list(3, single_frt_with_bounds=False)
    with pytest.raises(ValueError, match="No forecast"):
        ApplyBiasCorrection()(*bias_list)


def test_multiple_fcst_files(forecast_da):
    """多个预报输入应报错。"""
    bias_list = generate_bias_list(3, single_frt_with_bounds=False)
    with pytest.raises(ValueError, match="Multiple forecast"):
        ApplyBiasCorrection()(forecast_da, forecast_da, bias_list)


def test_has_time_bounds_ignores_meb_placeholder():
    """meb 占位 time_bounds=[0,0] 不应视为有效多日起报范围。"""
    from simple_bias_correction.src.utils._calibration_utilities import (
        has_time_bounds,
        strip_placeholder_time_bounds,
    )

    placeholder = xr.DataArray(
        np.zeros((1, 1, 1, 1, 2, 2), dtype=np.float32),
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        attrs={"time_bounds": [0, 0]},
    )
    assert has_time_bounds(placeholder) is False
    strip_placeholder_time_bounds(placeholder)
    assert "time_bounds" not in placeholder.attrs

    real = placeholder.copy(deep=True)
    real.attrs["time_bounds"] = [
        "2022-08-11T00:00:00.000000000",
        "2022-08-13T00:00:00.000000000",
    ]
    assert has_time_bounds(real) is True
