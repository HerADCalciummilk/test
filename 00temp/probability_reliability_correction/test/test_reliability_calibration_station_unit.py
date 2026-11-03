"""probability_reliability_correction 站点 DataFrame 路径单元测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

from probability_reliability_correction import (
    AggregateReliabilityCalibrationTables,
    ApplyReliabilityCalibration,
    ConstructReliabilityCalibrationTables,
    ManipulateReliabilityTable,
)
from probability_reliability_correction.src.utils._station import (
    AGGREGATED_STATION_ID,
    RELIABILITY_LONG_COLUMNS,
    SPATIAL_KIND_AGGREGATED,
    SPATIAL_KIND_STATION,
)


def _sta_table(
    rows,
    *,
    data_name: str = "data0",
    relative_to_threshold: str = "above",
) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.attrs["relative_to_threshold"] = relative_to_threshold
    assert data_name in df.columns
    return df


def _toy_forecast_truth():
    """两站、四起报、单阈值、dtime=4h（保证 Manipulate 后仍 ≥2 箱）。"""
    thresholds = [283.0]
    stations = [
        (83001, 116.3, 39.9),
        (83002, 117.1, 40.2),
    ]
    frts = [
        "2017-11-10T00:00:00",
        "2017-11-11T00:00:00",
        "2017-11-12T00:00:00",
        "2017-11-13T00:00:00",
    ]
    dtime = 4.0
    # 站1：偏高概率；站2：偏低；覆盖多个概率箱
    probs = {
        (83001, frts[0]): 0.9,
        (83001, frts[1]): 0.75,
        (83001, frts[2]): 0.55,
        (83001, frts[3]): 0.85,
        (83002, frts[0]): 0.1,
        (83002, frts[1]): 0.25,
        (83002, frts[2]): 0.45,
        (83002, frts[3]): 0.15,
    }
    events = {
        (83001, frts[0]): 1.0,
        (83001, frts[1]): 1.0,
        (83001, frts[2]): 0.0,
        (83001, frts[3]): 1.0,
        (83002, frts[0]): 0.0,
        (83002, frts[1]): 0.0,
        (83002, frts[2]): 1.0,
        (83002, frts[3]): 0.0,
    }
    fc_rows = []
    tr_rows = []
    for sid, lon, lat in stations:
        for frt in frts:
            fc_rows.append(
                {
                    "level": thresholds[0],
                    "time": frt,
                    "dtime": dtime,
                    "id": sid,
                    "lon": lon,
                    "lat": lat,
                    "data0": probs[(sid, frt)],
                }
            )
            valid = pd.Timestamp(frt) + pd.Timedelta(hours=dtime)
            tr_rows.append(
                {
                    "level": thresholds[0],
                    "time": valid,
                    "dtime": 0.0,
                    "id": sid,
                    "lon": lon,
                    "lat": lat,
                    "data0": events[(sid, frt)],
                }
            )
    return _sta_table(fc_rows), _sta_table(tr_rows)


def test_construct_station_long_table():
    fc, tr = _toy_forecast_truth()
    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        fc, tr
    )
    assert isinstance(table, pd.DataFrame)
    assert list(table.columns) == list(RELIABILITY_LONG_COLUMNS)
    assert table.attrs["spatial_kind"] == SPATIAL_KIND_STATION
    assert set(table["id"].tolist()) == {83001, 83002}
    # 2 站 × 1 阈值 × 5 箱
    assert len(table) == 10
    # 每站四时刻均落入某箱 → forecast_count 按站求和为 4
    assert_allclose(table.groupby("id")["forecast_count"].sum(), [4.0, 4.0])


def test_construct_then_aggregate_id():
    fc, tr = _toy_forecast_truth()
    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        fc, tr, aggregate_coords=["id"]
    )
    assert table.attrs["spatial_kind"] == SPATIAL_KIND_AGGREGATED
    assert set(table["id"].tolist()) == {int(AGGREGATED_STATION_ID)}
    assert len(table) == 5
    assert_allclose(table["forecast_count"].sum(), 8.0)


def test_aggregate_two_tables_no_overlap():
    fc, tr = _toy_forecast_truth()
    plugin = ConstructReliabilityCalibrationTables(n_probability_bins=5)
    # 拆成两个非重叠 FRT 表再聚合
    t_mid = pd.Timestamp("2017-11-11T12:00:00")
    fc1 = fc.loc[pd.to_datetime(fc["time"]) <= t_mid].copy()
    fc1.attrs = dict(fc.attrs)
    tr1 = tr.loc[
        pd.to_datetime(tr["time"]) <= t_mid + pd.Timedelta(hours=4)
    ].copy()
    tr1.attrs = dict(tr.attrs)
    fc2 = fc.loc[pd.to_datetime(fc["time"]) > t_mid].copy()
    fc2.attrs = dict(fc.attrs)
    tr2 = tr.loc[
        pd.to_datetime(tr["time"]) > t_mid + pd.Timedelta(hours=4)
    ].copy()
    tr2.attrs = dict(tr.attrs)
    t1 = plugin.process(fc1, tr1, aggregate_coords=["id"])
    t2 = plugin.process(fc2, tr2, aggregate_coords=["id"])
    merged = AggregateReliabilityCalibrationTables().process([t1, t2])
    assert_allclose(merged["forecast_count"].sum(), 8.0)


def test_manipulate_requires_aggregated_by_default():
    fc, tr = _toy_forecast_truth()
    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        fc, tr
    )
    with pytest.raises(ValueError, match="已聚合"):
        ManipulateReliabilityTable(minimum_forecast_count=1).process(table)


def test_manipulate_and_apply_aggregated():
    fc, tr = _toy_forecast_truth()
    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        fc, tr, aggregate_coords=["id"]
    )
    manipulated = ManipulateReliabilityTable(minimum_forecast_count=1).process(table)
    assert isinstance(manipulated, pd.DataFrame)
    assert manipulated.attrs["spatial_kind"] == SPATIAL_KIND_AGGREGATED

    # 待订正：同一站新起报
    apply_fc = _sta_table(
        [
            {
                "level": 283.0,
                "time": "2017-11-12T00:00:00",
                "dtime": 4.0,
                "id": 83001,
                "lon": 116.3,
                "lat": 39.9,
                "data0": 0.7,
            },
            {
                "level": 283.0,
                "time": "2017-11-12T00:00:00",
                "dtime": 4.0,
                "id": 83002,
                "lon": 117.1,
                "lat": 40.2,
                "data0": 0.3,
            },
        ]
    )
    out = ApplyReliabilityCalibration().process(apply_fc, manipulated)
    assert isinstance(out, pd.DataFrame)
    assert out["data0"].between(0.0, 1.0).all()
    # 订正后应有变化（或至少仍为有效概率）
    assert len(out) == 2


def test_apply_point_by_point_station():
    fc, tr = _toy_forecast_truth()
    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        fc, tr
    )
    manipulated = ManipulateReliabilityTable(
        minimum_forecast_count=1, point_by_point=True
    ).process(table)
    apply_fc = fc.loc[fc["time"] == fc["time"].iloc[-1]].copy()
    apply_fc.attrs = dict(fc.attrs)
    out = ApplyReliabilityCalibration(point_by_point=True).process(
        apply_fc, manipulated
    )
    assert len(out) == len(apply_fc)
    assert out["data0"].between(0.0, 1.0).all()


def test_apply_station_without_point_by_point_raises():
    fc, tr = _toy_forecast_truth()
    table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
        fc, tr
    )
    with pytest.raises(ValueError, match="point_by_point"):
        ApplyReliabilityCalibration().process(fc, table)
