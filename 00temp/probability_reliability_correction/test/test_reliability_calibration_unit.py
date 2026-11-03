"""probability_reliability_correction 网格路径单元测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from numpy.testing import assert_allclose, assert_array_equal

from probability_reliability_correction import (
    AggregateReliabilityCalibrationTables,
    ApplyReliabilityCalibration,
    ConstructReliabilityCalibrationTables,
    ManipulateReliabilityTable,
)
def _meb_prob(
    data_level_time_lat_lon: np.ndarray,
    *,
    thresholds,
    times,
    dtime=4.0,
    lat=None,
    lon=None,
    relative_to_threshold="above",
) -> xr.DataArray:
    """构建 meb 六维概率场。

    data 形状: (level, time, lat, lon)，dtime/member 长度为 1。
    """
    arr = np.asarray(data_level_time_lat_lon, dtype=np.float32)
    n_lev, n_time, n_lat, n_lon = arr.shape
    if lat is None:
        lat = np.arange(n_lat, dtype=np.float32)
    if lon is None:
        lon = np.arange(n_lon, dtype=np.float32)
    values = arr[:, :, np.newaxis, :, :]  # level, time, dtime, lat, lon
    values = values[np.newaxis, ...]  # member
    return xr.DataArray(
        values,
        coords={
            "member": [0],
            "level": np.asarray(thresholds, dtype=np.float32),
            "time": pd.to_datetime(times),
            "dtime": [float(dtime)],
            "lat": lat,
            "lon": lon,
        },
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        attrs={"units": "1", "relative_to_threshold": relative_to_threshold},
    )


def test_define_probability_bins_default():
    plugin = ConstructReliabilityCalibrationTables()
    bins = plugin._define_probability_bins(5, False, False)
    assert bins.shape == (5, 2)
    assert bins[0, 0] == 0.0
    assert bins[-1, 1] == 1.0


def test_define_probability_bins_both_limits_too_few():
    plugin = ConstructReliabilityCalibrationTables()
    with pytest.raises(ValueError, match="2 or fewer"):
        plugin._define_probability_bins(2, True, True)


def test_construct_and_aggregate_spatial():
    """两时刻相同场累加后，forecast_count 为单时刻的两倍。"""
    thresholds = [283.0, 288.0]
    # 3x3 概率场：0/8 ... 8/8
    field = (np.arange(9, dtype=np.float32).reshape(3, 3) / 8.0)
    fc_stack = np.stack([field, field], axis=0)  # time
    fc_data = np.stack([fc_stack, fc_stack], axis=0)  # level
    truth_raw = np.linspace(281, 285, 9, dtype=np.float32).reshape(3, 3)
    t0 = (truth_raw > thresholds[0]).astype(np.float32)
    t1 = (truth_raw > thresholds[1]).astype(np.float32)
    truth_field = np.stack([t0, t1], axis=0)
    truth_data = np.stack([truth_field, truth_field], axis=1)  # level, time, lat, lon

    times = ["2017-11-10T00:00:00", "2017-11-11T00:00:00"]
    # 实况：time 取有效时间 = FRT+dtime，dtime=0
    forecast = _meb_prob(fc_data, thresholds=thresholds, times=times, dtime=4.0)
    truth_times = ["2017-11-10T04:00:00", "2017-11-11T04:00:00"]
    truth = _meb_prob(truth_data, thresholds=thresholds, times=truth_times, dtime=0.0)

    table = ConstructReliabilityCalibrationTables().process(forecast, truth)
    assert set(table.data_vars) == {
        "observation_count",
        "sum_of_forecast_probabilities",
        "forecast_count",
    }
    assert table["observation_count"].dims == (
        "member",
        "level",
        "time",
        "dtime",
        "lat",
        "lon",
    )
    assert table.sizes["level"] == 2
    assert table.sizes["member"] == 5
    assert table.sizes["lat"] == 3 and table.sizes["lon"] == 3
    assert "time_bound_lower" in table.coords and "time_bound_upper" in table.coords

    # 两时刻相同 → 单时刻 count 的 2 倍
    single = ConstructReliabilityCalibrationTables().process(
        forecast.isel(time=[0]), truth.isel(time=[0])
    )
    assert_allclose(
        table["forecast_count"].values,
        single["forecast_count"].values * 2,
        rtol=0,
        atol=0,
    )

    collapsed = AggregateReliabilityCalibrationTables().process(
        [table], coordinates=["lat", "lon"]
    )
    assert collapsed.sizes["lat"] == 1 and collapsed.sizes["lon"] == 1
    assert_allclose(
        collapsed["forecast_count"].values,
        table["forecast_count"].sum(dim=("lat", "lon")).values.reshape(
            collapsed["forecast_count"].shape
        ),
    )


def test_manipulate_and_apply_smoke():
    thresholds = [283.0]
    # 多概率取值，保证多个箱都有样本
    base = (np.arange(9, dtype=np.float32).reshape(3, 3) / 8.0)
    n_time = 40
    fc_data = np.stack([base] * n_time, axis=0)[np.newaxis, ...]
    truth_field = (base > 0.5).astype(np.float32)
    truth_data = np.stack([truth_field] * n_time, axis=0)[np.newaxis, ...]

    frts = pd.date_range("2017-11-01", periods=n_time, freq="D")
    forecast = _meb_prob(fc_data, thresholds=thresholds, times=frts, dtime=6.0)
    truth_times = frts + pd.to_timedelta(6, unit="h")
    truth = _meb_prob(truth_data, thresholds=thresholds, times=truth_times, dtime=0.0)

    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        forecast, truth, aggregate_coords=["lat", "lon"]
    )
    manipulated = ManipulateReliabilityTable(minimum_forecast_count=1).process(table)
    assert isinstance(manipulated, list) and len(manipulated) == 1
    assert manipulated[0].sizes["member"] >= 2
    assert manipulated[0]["observation_count"].dims == (
        "member",
        "level",
        "time",
        "dtime",
        "lat",
        "lon",
    )

    apply_fc = _meb_prob(
        base[np.newaxis, np.newaxis, ...],
        thresholds=thresholds,
        times=["2017-12-01T00:00:00"],
        dtime=6.0,
    )
    calibrated = ApplyReliabilityCalibration().process(apply_fc, manipulated)
    assert calibrated.shape == apply_fc.shape
    assert np.all((calibrated.values >= 0) & (calibrated.values <= 1))
    # 有足够箱时应发生映射，结果不必处处等于原值
    assert not np.allclose(calibrated.values, apply_fc.values)


def test_apply_none_table_returns_input():
    field = np.zeros((1, 1, 2, 2), dtype=np.float32)
    fc = _meb_prob(field, thresholds=[1.0], times=["2017-01-01"], dtime=0.0)
    out = ApplyReliabilityCalibration().process(fc, None)
    assert out is fc


def test_apply_rejects_unaggregated_spatial_table():
    """非 point_by_point 时，空间未折叠的表应报错（对齐原版，不自动 Aggregate）。"""
    thresholds = [283.0]
    field = np.full((1, 1, 2, 2), 0.5, dtype=np.float32)
    truth_field = np.ones((1, 1, 2, 2), dtype=np.float32)
    fc = _meb_prob(field, thresholds=thresholds, times=["2017-11-10"], dtime=4.0)
    tr = _meb_prob(
        truth_field, thresholds=thresholds, times=["2017-11-10T04:00:00"], dtime=0.0
    )
    table = ConstructReliabilityCalibrationTables().process(fc, tr)
    assert table.sizes["lat"] > 1 or table.sizes["lon"] > 1
    apply_fc = _meb_prob(
        field, thresholds=thresholds, times=["2017-12-01"], dtime=4.0
    )
    with pytest.raises(ValueError, match="spatial dimensions"):
        ApplyReliabilityCalibration().process(apply_fc, table)


def test_apply_relative_to_threshold_aliases_and_required():
    """greater_than 等别名应映射为 above；缺属性应报错。"""
    assert (
        ApplyReliabilityCalibration._probability_is_above_or_below(
            xr.DataArray(0, attrs={"relative_to_threshold": "greater_than"})
        )
        == "above"
    )
    assert (
        ApplyReliabilityCalibration._probability_is_above_or_below(
            xr.DataArray(0, attrs={"relative_to_threshold": "less_than_or_equal_to"})
        )
        == "below"
    )

    thresholds = [283.0, 288.0]
    base = (np.arange(9, dtype=np.float32).reshape(3, 3) / 8.0)
    n_time = 20
    fc_data = np.stack([base] * n_time, axis=0)
    fc_data = np.stack([fc_data, fc_data], axis=0)
    truth_field = (base > 0.5).astype(np.float32)
    truth_data = np.stack([truth_field] * n_time, axis=0)
    truth_data = np.stack([truth_data, truth_data], axis=0)
    frts = pd.date_range("2017-11-01", periods=n_time, freq="D")
    forecast = _meb_prob(
        fc_data,
        thresholds=thresholds,
        times=frts,
        dtime=6.0,
        relative_to_threshold="greater_than",
    )
    truth = _meb_prob(
        truth_data,
        thresholds=thresholds,
        times=frts + pd.to_timedelta(6, unit="h"),
        dtime=0.0,
        relative_to_threshold="greater_than",
    )
    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        forecast, truth, aggregate_coords=["lat", "lon"]
    )
    manipulated = ManipulateReliabilityTable(minimum_forecast_count=1).process(table)
    apply_fc = _meb_prob(
        np.stack([base, base], axis=0)[:, np.newaxis, ...],
        thresholds=thresholds,
        times=["2017-12-01"],
        dtime=6.0,
        relative_to_threshold="greater_than",
    )
    calibrated = ApplyReliabilityCalibration().process(apply_fc, manipulated)
    assert calibrated.shape == apply_fc.shape

    apply_fc_no_attr = apply_fc.copy()
    apply_fc_no_attr.attrs.pop("relative_to_threshold", None)
    with pytest.raises(ValueError, match="above or below"):
        ApplyReliabilityCalibration().process(apply_fc_no_attr, manipulated)


def test_construct_truth_nan_excludes_point():
    """实况 NaN 视为缺测：该点不计入样本；另一时刻有效则可恢复贡献。"""
    thresholds = [283.0]
    field = np.full((3, 3), 0.5, dtype=np.float32)
    fc_data = np.stack([field, field], axis=0)[np.newaxis, ...]

    truth0 = np.ones((3, 3), dtype=np.float32)
    truth0[0, 0] = np.nan  # 第一时刻该点缺测
    truth1 = np.ones((3, 3), dtype=np.float32)
    truth_data = np.stack([truth0, truth1], axis=0)[np.newaxis, ...]

    times = ["2017-11-10T00:00:00", "2017-11-11T00:00:00"]
    forecast = _meb_prob(fc_data, thresholds=thresholds, times=times, dtime=4.0)
    truth = _meb_prob(
        truth_data,
        thresholds=thresholds,
        times=["2017-11-10T04:00:00", "2017-11-11T04:00:00"],
        dtime=0.0,
    )

    table = ConstructReliabilityCalibrationTables().process(forecast, truth)
    # (0,0) 仅第二时刻有效 → forecast_count 在各箱合计应为 1
    # (0,1) 两时刻皆有效 → 合计为 2
    counts = table["forecast_count"].isel(level=0, time=0, dtime=0)
    assert float(counts.isel(lat=0, lon=0).sum()) == 1.0
    assert float(counts.isel(lat=0, lon=1).sum()) == 2.0


def test_aggregate_overlapping_frt_raises():
    thresholds = [283.0]
    field = np.ones((1, 1, 2, 2), dtype=np.float32) * 0.5
    truth_field = np.ones((1, 1, 2, 2), dtype=np.float32)
    fc = _meb_prob(field, thresholds=thresholds, times=["2017-11-10"], dtime=4.0)
    tr = _meb_prob(
        truth_field, thresholds=thresholds, times=["2017-11-10T04:00:00"], dtime=0.0
    )
    table = ConstructReliabilityCalibrationTables().process(fc, tr)
    with pytest.raises(ValueError, match="overlapping"):
        AggregateReliabilityCalibrationTables().process([table, table])
