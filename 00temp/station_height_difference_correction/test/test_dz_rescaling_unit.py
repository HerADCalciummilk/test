"""station_height_difference_correction 单元测试（对照原版公式与匹配逻辑）。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from numpy.polynomial.polynomial import polyfit

from station_height_difference_correction import ApplyDzRescaling, EstimateDzRescaling
from station_height_difference_correction.src.utils._sta import (
    filter_matching_stations,
    get_neighbour_finding_method_name,
    require_columns,
)
from station_height_difference_correction.utils.base_plugin import PostProcessingPlugin

EST_CLI_INPUT = (
    Path(__file__).resolve().parents[1]
    / "test_data"
    / "estimate-dz-rescaling"
    / "cli_input"
)


def _sta(ids, values, *, dtime=6, hour=0, day=1, data_name="data", percentile=50.0):
    n = len(ids)
    df = pd.DataFrame(
        {
            "level": [0] * n,
            "time": pd.to_datetime([f"2017-01-{day:02d} {hour:02d}:00:00"] * n),
            "dtime": [dtime] * n,
            "id": ids,
            "lon": list(range(n)),
            "lat": [0.0] * n,
            data_name: values,
        }
    )
    if percentile is not None:
        df["percentile"] = percentile
    return df


def test_require_columns_raises():
    df = pd.DataFrame({"id": [1]})
    with pytest.raises(ValueError, match="缺少列"):
        require_columns(df, ("id", "vertical_displacement"))


def test_filter_matching_stations():
    left = _sta([1, 2, 3], [1.0, 2.0, 3.0])
    right = _sta([2, 3, 4], [10.0, 20.0, 30.0])
    a, b = filter_matching_stations(left, right)
    assert set(a["id"]) == {2, 3}
    assert set(b["id"]) == {2, 3}


@pytest.mark.parametrize("truth_adj", [0.0, -1.0, 1.0])
def test_estimate_scaled_dz_math(truth_adj):
    """用可控 dz 验证 ln(fc/tr)≈s*dz 与 exp(-s*dz)。"""
    ids = [1, 2, 3, 4]
    dz_lower, dz_upper = -200.0, 200.0
    forecast = _sta(ids, [0.0, 20.0, 10.0, 15.0], data_name="wind")
    truth_vals = np.clip(np.array([0.0, 20.0, 10.2, 15.1]) + truth_adj, 0, None)
    truth = _sta(ids, truth_vals.tolist(), data_name="wind")
    dz = np.array([0.0, -30.0, 80.0, 30.0], dtype=np.float32)
    neighbour = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
            "id": ids,
            "lon": [0, 1, 2, 3],
            "lat": 0.0,
            "vertical_displacement": dz,
        }
    )

    result = EstimateDzRescaling(
        forecast_period=6,
        forecast_data_name="wind",
        dz_lower_bound=dz_lower,
        dz_upper_bound=dz_upper,
    ).process(forecast, truth, neighbour)

    fc = np.array([0.0, 20.0, 10.0, 15.0])
    tr = truth_vals
    mask = (fc != 0) & (tr != 0) & (dz >= dz_lower) & (dz <= dz_upper)
    s = polyfit(dz[mask], np.log(fc[mask] / tr[mask]), 1)[1]
    expected_scaled = np.exp(-s * dz)
    a = np.exp(-s * dz_lower)
    b = np.exp(-s * dz_upper)
    expected_scaled = np.clip(expected_scaled, min(a, b), max(a, b))

    np.testing.assert_allclose(
        result["scaled_vertical_displacement"].to_numpy(), expected_scaled, atol=1e-4, rtol=1e-4
    )
    assert float(result["dtime"].iloc[0]) == 6.0
    assert int(result["forecast_reference_time_hour"].iloc[0]) == 0


def test_estimate_dz_bounds_exclude_all_nonzero_raises_or_filters():
    """过紧的 dz 界导致有效训练点不足时应报错。"""
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 12.0], data_name="wind")
    truth = _sta(ids, [9.0, 11.0], data_name="wind")
    neighbour = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
            "id": ids,
            "lon": [0.0, 1.0],
            "lat": 0.0,
            "vertical_displacement": [100.0, -100.0],
        }
    )
    with pytest.raises(ValueError, match="拟合样本为空"):
        EstimateDzRescaling(
            forecast_period=6,
            forecast_data_name="wind",
            dz_lower_bound=-10,
            dz_upper_bound=10,
        ).process(forecast, truth, neighbour)


def test_estimate_percentile_filter():
    ids = [1, 2]
    rows = []
    for perc, vals in [(10, [5.0, 6.0]), (50, [10.0, 12.0]), (90, [20.0, 24.0])]:
        rows.append(_sta(ids, vals, data_name="wind", percentile=perc))
    forecast = pd.concat(rows, ignore_index=True)
    truth = _sta(ids, [9.0, 11.0], data_name="wind", percentile=None)
    neighbour = pd.DataFrame(
        {
            "id": ids,
            "vertical_displacement": [10.0, -10.0],
            "lon": [0.0, 1.0],
            "lat": [0.0, 0.0],
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
        }
    )
    result = EstimateDzRescaling(
        forecast_period=6, forecast_data_name="wind"
    ).process(forecast, truth, neighbour)
    assert len(result) == 2
    assert "scaled_vertical_displacement" in result.columns


def test_estimate_requires_percentile_column():
    """与原版一致：预报必须含 percentile 列。"""
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 12.0], data_name="wind", percentile=None)
    truth = _sta(ids, [9.0, 11.0], data_name="wind", percentile=None)
    neighbour = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
            "id": ids,
            "lon": [0.0, 1.0],
            "lat": 0.0,
            "vertical_displacement": [10.0, -10.0],
        }
    )
    with pytest.raises(ValueError, match="缺少列"):
        EstimateDzRescaling(
            forecast_period=6, forecast_data_name="wind"
        ).process(forecast, truth, neighbour)


def test_estimate_output_dtypes_follow_meb_spec():
    """Estimate 输出坐标与要素列 dtype 符合 meb 规范。"""
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 12.0], data_name="wind")
    truth = _sta(ids, [9.0, 11.0], data_name="wind", percentile=None)
    neighbour = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
            "id": ids,
            "lon": [0.0, 1.0],
            "lat": [0.0, 0.0],
            "vertical_displacement": [10.0, -10.0],
        }
    )
    result = EstimateDzRescaling(
        forecast_period=6, forecast_data_name="wind"
    ).process(forecast, truth, neighbour)
    assert result["level"].dtype == np.float32
    assert np.issubdtype(result["time"].dtype, np.datetime64)
    assert result["dtime"].dtype == np.int32
    assert result["id"].dtype == np.int32
    assert result["lon"].dtype == np.float32
    assert result["lat"].dtype == np.float32
    assert result["scaled_vertical_displacement"].dtype == np.float32
    assert result["forecast_reference_time_hour"].dtype == np.float32


def test_apply_multiplies_and_selects_period():
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 20.0], dtime=7, hour=3, data_name="wind")
    rows = []
    for fp, factors in [(6, [0.5, 0.5]), (12, [1.1, 1.0])]:
        rows.append(
            pd.DataFrame(
                {
                    "level": 0,
                    "time": forecast["time"].iloc[0],
                    "dtime": fp,
                    "id": ids,
                    "lon": [0.0, 1.0],
                    "lat": [0.0, 0.0],
                    "forecast_reference_time_hour": 3,
                    "scaled_vertical_displacement": factors,
                }
            )
        )
    scaled = pd.concat(rows, ignore_index=True)
    out = ApplyDzRescaling(frt_hour_leniency=0, forecast_data_name="wind").process(
        forecast, scaled
    )
    np.testing.assert_allclose(out["wind"].to_numpy(), [11.0, 20.0], atol=1e-6)


def test_apply_frt_hour_leniency():
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 20.0], dtime=6, hour=2, data_name="wind")
    scaled = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 6,
            "id": ids,
            "lon": [0.0, 1.0],
            "lat": [0.0, 0.0],
            "forecast_reference_time_hour": 3,
            "scaled_vertical_displacement": [1.2, 1.0],
        }
    )
    out = ApplyDzRescaling(frt_hour_leniency=1, forecast_data_name="wind").process(
        forecast, scaled
    )
    np.testing.assert_allclose(out["wind"].to_numpy(), [12.0, 20.0])


def test_apply_mismatch_sites():
    forecast = _sta([1, 2], [10.0, 20.0], data_name="wind")
    scaled = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 6,
            "id": [1],
            "lon": [0.0],
            "lat": [0.0],
            "forecast_reference_time_hour": 0,
            "scaled_vertical_displacement": [1.0],
        }
    )
    with pytest.raises(ValueError, match="站点不一致"):
        ApplyDzRescaling(forecast_data_name="wind").process(forecast, scaled)


def test_apply_uses_max_period_when_exceeded():
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 20.0], dtime=30, hour=3, data_name="wind")
    scaled = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": [6, 6, 24, 24],
            "id": [1, 2, 1, 2],
            "lon": [0.0, 1.0, 0.0, 1.0],
            "lat": 0.0,
            "forecast_reference_time_hour": 3,
            "scaled_vertical_displacement": [0.5, 0.5, 1.05, 1.0],
        }
    )
    out = ApplyDzRescaling(frt_hour_leniency=0, forecast_data_name="wind").process(
        forecast, scaled
    )
    np.testing.assert_allclose(out["wind"].to_numpy(), [10.5, 20.0])


@pytest.mark.parametrize(
    "land_constraint,similar_altitude,expected",
    [
        (False, False, "nearest"),
        (True, False, "nearest_land"),
        (False, True, "nearest_minimum_dz"),
        (True, True, "nearest_land_minimum_dz"),
    ],
)
def test_neighbour_finding_method_name(land_constraint, similar_altitude, expected):
    assert (
        get_neighbour_finding_method_name(land_constraint, similar_altitude)
        == expected
    )


def _neighbour_multi_method(ids, method_to_dz, *, time):
    """构造含多种 neighbour_selection_method 的 neighbour 表。"""
    rows = []
    for method, dz_by_id in method_to_dz.items():
        for site_id, dz in zip(ids, dz_by_id):
            rows.append(
                {
                    "level": 0,
                    "time": time,
                    "dtime": 0,
                    "id": site_id,
                    "lon": float(site_id),
                    "lat": 0.0,
                    "neighbour_selection_method": method,
                    "vertical_displacement": float(dz),
                }
            )
    return pd.DataFrame(rows)


def test_estimate_land_constraint_uses_nearest_land_dz():
    """land_constraint=True 时只用 nearest_land 的高差拟合与输出。"""
    ids = [1, 2, 3]
    train_ids = [1, 2]
    forecast = _sta(train_ids, [10.0, 12.0], data_name="wind")
    truth = _sta(train_ids, [9.0, 11.0], data_name="wind")
    nearest_dz = [100.0, -100.0, 50.0]
    land_dz = [10.0, -10.0, 5.0]
    neighbour = _neighbour_multi_method(
        ids,
        {"nearest": nearest_dz, "nearest_land": land_dz},
        time=forecast["time"].iloc[0],
    )

    result = EstimateDzRescaling(
        forecast_period=6,
        forecast_data_name="wind",
        land_constraint=True,
    ).process(forecast, truth, neighbour)

    fc = np.array([10.0, 12.0])
    tr = np.array([9.0, 11.0])
    dz_train = np.array(land_dz[:2])
    s = polyfit(dz_train, np.log(fc / tr), 1)[1]
    expected = np.exp(-s * np.array(land_dz))

    assert set(result["id"]) == set(ids)
    np.testing.assert_allclose(
        result.set_index("id").loc[ids, "scaled_vertical_displacement"].to_numpy(),
        expected,
        atol=1e-4,
        rtol=1e-4,
    )


def test_estimate_missing_method_raises():
    """neighbour 无对应选取方法时应明确报错。"""
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 12.0], data_name="wind")
    truth = _sta(ids, [9.0, 11.0], data_name="wind")
    neighbour = _neighbour_multi_method(
        ids,
        {"nearest": [10.0, -10.0]},
        time=forecast["time"].iloc[0],
    )
    with pytest.raises(ValueError, match="neighbour 中无方法"):
        EstimateDzRescaling(
            forecast_period=6,
            forecast_data_name="wind",
            land_constraint=True,
        ).process(forecast, truth, neighbour)


def test_estimate_missing_truth_uses_log_one():
    """非有限实况按原版掩码路径以 log=1.0 参与 polyfit。"""
    ids = [1, 2, 3]
    forecast = _sta(ids, [10.0, 12.0, 14.0], data_name="wind")
    truth = _sta(ids, [9.0, np.nan, 13.0], data_name="wind")
    dz = np.array([20.0, -20.0, 40.0], dtype=float)
    neighbour = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
            "id": ids,
            "lon": [0.0, 1.0, 2.0],
            "lat": 0.0,
            "vertical_displacement": dz,
        }
    )

    result = EstimateDzRescaling(
        forecast_period=6, forecast_data_name="wind"
    ).process(forecast, truth, neighbour)

    fc = np.array([10.0, 12.0, 14.0])
    tr = np.array([9.0, np.nan, 13.0])
    log_err = np.array(
        [np.log(fc[0] / tr[0]), 1.0, np.log(fc[2] / tr[2])], dtype=float
    )
    s = polyfit(dz, log_err, 1)[1]
    expected = np.exp(-s * dz)

    np.testing.assert_allclose(
        result["scaled_vertical_displacement"].to_numpy(),
        expected,
        atol=1e-4,
        rtol=1e-4,
    )


def test_estimate_output_covers_all_neighbour_sites():
    """输出站点集合与筛选后的 neighbour 对齐，可多于训练交集。"""
    train_ids = [1, 2]
    all_ids = [1, 2, 3, 4]
    forecast = _sta(train_ids, [10.0, 12.0], data_name="wind")
    truth = _sta(train_ids, [9.0, 11.0], data_name="wind")
    neighbour = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
            "id": all_ids,
            "lon": [0.0, 1.0, 2.0, 3.0],
            "lat": 0.0,
            "vertical_displacement": [10.0, -10.0, 30.0, -30.0],
        }
    )
    result = EstimateDzRescaling(
        forecast_period=6, forecast_data_name="wind"
    ).process(forecast, truth, neighbour)
    assert list(result["id"]) == all_ids
    assert len(result) == len(all_ids)


@pytest.mark.skipif(
    not (EST_CLI_INPUT / "T1200Z_forecast.csv").exists(),
    reason="缺少 estimate CLI 样例输入",
)
def test_cli_estimate_process_smoke():
    """CLI process 对官方样例输入可跑通（含 land_constraint）。"""
    from station_height_difference_correction.cli.dsc_estimate_dz_rescaling import process

    result = process(
        EST_CLI_INPUT / "T1200Z_forecast.csv",
        EST_CLI_INPUT / "T1200Z_truth.csv",
        EST_CLI_INPUT / "neighbour.csv",
        forecast_period=6,
        forecast_data_name="wind_speed",
        dz_lower_bound=-550,
        dz_upper_bound=550,
        land_constraint=True,
        output_path=None,
    )
    assert "scaled_vertical_displacement" in result.columns
    assert len(result) > 0
    assert float(result["dtime"].iloc[0]) == 6.0


class _ReturnFramePlugin(PostProcessingPlugin):
    """测试用：process 原样返回构造时传入的 DataFrame。"""

    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def process(self, *args, **kwargs):
        return self._frame


def test_post_processing_plugin_station_title_prefix():
    """站点 DataFrame.attrs['title'] 经 __call__ 加上 Post-Processed 前缀。"""
    df = pd.DataFrame({"id": [1]})
    df.attrs["title"] = "Foo"
    out = _ReturnFramePlugin(df)()
    assert out.attrs["title"] == "Post-Processed Foo"


@pytest.mark.parametrize(
    "title,expected",
    [
        (None, None),
        ("unknown", "unknown"),
        ("Post-Processed Already", "Post-Processed Already"),
    ],
)
def test_post_processing_plugin_station_title_unchanged(title, expected):
    """无 title / 默认 unknown / 已含前缀时不修改。"""
    df = pd.DataFrame({"id": [1]})
    if title is not None:
        df.attrs["title"] = title
    out = _ReturnFramePlugin(df)()
    if expected is None:
        assert "title" not in out.attrs
    else:
        assert out.attrs["title"] == expected


def test_estimate_via_call_preserves_absent_title():
    """EstimateDzRescaling 经 __call__ 调用时，无 title 的输出保持不变。"""
    ids = [1, 2]
    forecast = _sta(ids, [10.0, 20.0], data_name="wind")
    truth = _sta(ids, [10.0, 19.0], data_name="wind")
    neighbour = pd.DataFrame(
        {
            "level": 0,
            "time": forecast["time"].iloc[0],
            "dtime": 0,
            "id": ids,
            "lon": [0, 1],
            "lat": 0.0,
            "vertical_displacement": [10.0, -10.0],
        }
    )
    result = EstimateDzRescaling(
        forecast_period=6, forecast_data_name="wind"
    )(forecast, truth, neighbour)
    assert "title" not in result.attrs
    assert "scaled_vertical_displacement" in result.columns
