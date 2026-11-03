"""cli/io 站点 csv 读写与统一入口冒烟测试。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from probability_reliability_correction.cli import io as cli_io
from probability_reliability_correction.src.utils._station import (
    RELIABILITY_LONG_COLUMNS,
    SPATIAL_KIND_AGGREGATED,
    AGGREGATED_STATION_ID,
)


def test_sta_dataframe_roundtrip_preserves_custom_attrs(tmp_path: Path):
    rows = [
        {
            "level": 283.0,
            "time": "2017-11-10T00:00:00",
            "dtime": 4.0,
            "id": 83001,
            "lon": 116.3,
            "lat": 39.9,
            "data0": 0.8,
        }
    ]
    df = pd.DataFrame(rows)
    df.attrs["relative_to_threshold"] = "above"
    df.attrs["units"] = "1"

    path = tmp_path / "forecast_sta.csv"
    cli_io.write_sta_dataframe(df, path)
    loaded = cli_io.read_forecast_or_truth(path)
    assert isinstance(loaded, pd.DataFrame)
    assert loaded.attrs.get("relative_to_threshold") == "above"
    np.testing.assert_allclose(loaded["data0"].astype(float), [0.8], atol=1e-2)


def test_sta_reliability_roundtrip(tmp_path: Path):
    row = {c: 0.0 for c in RELIABILITY_LONG_COLUMNS}
    row.update(
        {
            "level": 283.0,
            "time": "2017-11-10T00:00:00",
            "dtime": 4.0,
            "id": int(AGGREGATED_STATION_ID),
            "lon": np.nan,
            "lat": np.nan,
            "bin_index": 0,
            "probability_bin": 0.5,
            "probability_bin_bound_lower": 0.0,
            "probability_bin_bound_upper": 1.0,
            "observation_count": 10.0,
            "sum_of_forecast_probabilities": 5.0,
            "forecast_count": 10.0,
        }
    )
    df = pd.DataFrame([row])
    df.attrs["spatial_kind"] = SPATIAL_KIND_AGGREGATED
    df.attrs["relative_to_threshold"] = "above"

    path = tmp_path / "table_sta.csv"
    cli_io.write_result(df, path)
    loaded = cli_io.read_reliability(path)
    assert isinstance(loaded, pd.DataFrame)
    assert loaded.attrs.get("spatial_kind") == SPATIAL_KIND_AGGREGATED
    assert loaded.attrs.get("relative_to_threshold") == "above"
