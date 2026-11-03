# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI 写出-读回保真度测试。

核心回归点：两个 CLI 脚本经 ``xarray.to_netcdf()`` 直写（编码
``dtype="float32"``、``_FillValue=NaN``），写出结果应与插件内存值
**逐位一致**。历史上曾用 ``meb.write_griddata_to_nc`` 写出，其
``effectiveNum`` 量化会把浮点值截断到少量有效数字，导致与
KGO/原方法产生 1e-1 量级误差；本组测试防止该写法回归。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import meteva_base as meb
import numpy as np
import xarray as xr

from simple_bias_correction.cli.cal_calculate_forecast_bias import (
    process as calc_bias_cli_process,
)
from simple_bias_correction.cli.prb_bias_correction import (
    process as apply_bias_cli_process,
)
from simple_bias_correction.src.simple_bias_correction import (
    ApplyBiasCorrection,
    CalculateForecastBias,
)

VALID_TIME = datetime(2022, 12, 6, 3, 0)
# 与 CLI 内部一致：避免 meb 默认真实值范围误置空诊断量
VALID_VAL = (-np.inf, np.inf, np.nan)

FCST_PATTERN = np.array(
    [[11.653186, 5.40012, 7.82345], [2.10093, 9.99876, 14.33210]],
    dtype=np.float32,
)


def _meb6d(
    values: np.ndarray,
    *,
    name: str,
    time: datetime,
    dtime_hours: float = 0.0,
    units: str = "m s-1",
) -> xr.DataArray:
    """构造标准 meb 六维单日场；``values`` 为 ``(lat, lon)``。"""
    values = np.asarray(values, dtype=np.float32)
    ny, nx = values.shape
    return xr.DataArray(
        values[np.newaxis, np.newaxis, np.newaxis, np.newaxis],
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": [0.0],
            "time": [np.datetime64(time)],
            "dtime": [np.float32(dtime_hours)],
            "lat": np.arange(ny, dtype=np.float32),
            "lon": np.arange(nx, dtype=np.float32),
        },
        name=name,
        attrs={
            "units": units,
            "dtime_units": "hour",
            "time_type": "UT",
            "title": "Test dataset",
            "source": "IMPROVER",
            "institution": "Test",
        },
    )


def _write_input(da: xr.DataArray, path) -> None:
    """合成输入以 xarray 直写（与预处理脚本同一写出方式）。"""
    da.to_dataset(name=da.name).to_netcdf(path)


def _read_back(path) -> xr.DataArray:
    """按业务读法读回：meb 读入 + 六维校验。"""
    da = meb.read_griddata_from_nc(str(path))
    assert da is not None
    return meb.checkout_griddata(da, valid_val=VALID_VAL)


def test_calc_cli_write_read_is_bit_exact(tmp_path):
    """算偏差 CLI 写回后读回，应与插件内存结果逐位一致（无量化损失）。"""
    num_days = 3
    fcst_paths, truth_paths = [], []
    for i in range(num_days):
        frt = VALID_TIME - timedelta(hours=3) - timedelta(days=i)
        truth_time = VALID_TIME - timedelta(days=i)
        # 逐日加入不同的小数级扰动，保证数值不是整数（量化敏感）
        noise = np.float32(0.117 * (i + 1))
        fcst = _meb6d(
            FCST_PATTERN + noise, name="wind_speed_at_10m", time=frt, dtime_hours=3.0
        )
        truth = _meb6d(
            FCST_PATTERN - 0.5 + noise,
            name="wind_speed_at_10m",
            time=truth_time,
            dtime_hours=0.0,
        )
        fp = tmp_path / f"fcst_{i}.nc"
        tp = tmp_path / f"truth_{i}.nc"
        _write_input(fcst, fp)
        _write_input(truth, tp)
        fcst_paths.append(fp)
        truth_paths.append(tp)

    out_path = tmp_path / "bias.nc"
    in_memory = calc_bias_cli_process(fcst_paths, truth_paths, output_path=out_path)

    readback = _read_back(out_path)
    # 数值逐位一致（float32 写-读回无损）；历史 effectiveNum 量化下此处会差 1e-1
    np.testing.assert_allclose(
        readback.values, in_memory.values, rtol=0, atol=0, equal_nan=True
    )
    assert readback.dtype == np.float32

    # 与插件内存计算结果一致（偏差 = 0.5，非整数，量化敏感）
    expected = CalculateForecastBias().process(
        xr.concat(
            [_read_back(p) for p in fcst_paths], dim="time", coords="different"
        ),
        xr.concat(
            [_read_back(p) for p in truth_paths], dim="time", coords="different"
        ),
    )
    np.testing.assert_allclose(
        readback.values, expected.values, rtol=0, atol=0, equal_nan=True
    )


def test_apply_cli_write_read_preserves_values_and_nan(tmp_path):
    """订正 CLI 写回后：数值逐位一致，且预报/偏差 NaN 并集保留。"""
    frt = VALID_TIME - timedelta(hours=3)
    fcst_vals = FCST_PATTERN.copy()
    fcst_vals[0, 0] = np.nan  # 预报缺测格点
    bias_vals = np.full(FCST_PATTERN.shape, 0.3125, dtype=np.float32)
    bias_vals[1, 1] = np.nan  # 偏差缺测格点（与预报缺测位置不同）

    fcst = _meb6d(fcst_vals, name="wind_speed_at_10m", time=frt, dtime_hours=3.0)
    bias = _meb6d(
        bias_vals,
        name="forecast_error_of_wind_speed_at_10m",
        time=frt,
        dtime_hours=3.0,
    )
    fcst_path = tmp_path / "fcst.nc"
    bias_path = tmp_path / "bias.nc"
    _write_input(fcst, fcst_path)
    _write_input(bias, bias_path)

    out_path = tmp_path / "corrected.nc"
    in_memory = apply_bias_cli_process(
        fcst_path, [bias_path], lower_bound=0.0, output_path=out_path
    )

    readback = _read_back(out_path)
    np.testing.assert_allclose(
        readback.values, in_memory.values, rtol=0, atol=0, equal_nan=True
    )
    assert readback.dtype == np.float32

    rb = np.squeeze(readback.values)
    # NaN 取预报与偏差缺测的并集
    expected_nan = np.isnan(np.squeeze(fcst_vals)) | np.isnan(np.squeeze(bias_vals))
    np.testing.assert_array_equal(np.isnan(rb), expected_nan)
    # 有效格点：订正值 = 预报 - 偏差，且不低于下界
    valid = ~expected_nan
    np.testing.assert_allclose(
        rb[valid],
        np.clip(np.squeeze(fcst_vals)[valid] - np.squeeze(bias_vals)[valid], 0.0, None),
        rtol=0,
        atol=0,
    )


def test_apply_cli_without_output_path_returns_only(tmp_path):
    """output_path=None 时只返回结果，不落盘。"""
    frt = VALID_TIME - timedelta(hours=3)
    fcst = _meb6d(FCST_PATTERN, name="wind_speed_at_10m", time=frt, dtime_hours=3.0)
    bias = _meb6d(
        np.full(FCST_PATTERN.shape, 0.25, dtype=np.float32),
        name="forecast_error_of_wind_speed_at_10m",
        time=frt,
        dtime_hours=3.0,
    )
    fcst_path = tmp_path / "fcst.nc"
    bias_path = tmp_path / "bias.nc"
    _write_input(fcst, fcst_path)
    _write_input(bias, bias_path)

    result = apply_bias_cli_process(fcst_path, [bias_path], lower_bound=0.0)
    assert isinstance(result, xr.DataArray)
    # 未指定输出路径时不应产生额外文件
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bias.nc", "fcst.nc"]
