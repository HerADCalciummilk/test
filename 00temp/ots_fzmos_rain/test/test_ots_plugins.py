# -*- coding: utf-8 -*-
"""两个插件的形状和订正关系。用小网格，不读业务文件。"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from _util_plugin import THRESHOLD_IN, build_threshold_bounds
from ots_fzmos_rain_plugin import OtsForecastPlugin, OtsThresholdPlugin
from utils.grid import GridConfig
from utils.ots_io import read_station_codes, read_thresholds, write_thresholds


def _grid():
    return GridConfig(
        lat_start=21.0,
        lon_start=114.0,
        lat_end=21.2,
        lon_end=114.2,
        dlat=0.1,
        dlon=0.1,
        num_x=3,
        num_y=3,
    )


def test_station_file_lists_seventy_codes():
    codes = read_station_codes(ROOT / "resource" / "fjstation70-2021.txt", 70)
    assert len(codes) == 70
    assert len(set(codes)) == 70


def test_threshold_table_roundtrip(tmp_path):
    table = np.linspace(0.1, 20.0, 200, dtype=np.float32).reshape(20, 10)
    path = tmp_path / "fjyz.txt"
    write_thresholds(path, table)
    loaded = read_thresholds(path)
    assert loaded.shape == (20, 10)
    assert np.allclose(loaded, np.round(table, 1), atol=0.051)


def test_threshold_plugin_stays_inside_search_bounds():
    years = range(2022, 2027)
    generator = np.random.default_rng(1)
    ec_by_year = {
        year: generator.uniform(0.0, 40.0, size=(20, 732, 2)).astype(np.float32)
        for year in years
    }
    obs_by_year = {
        year: generator.uniform(0.0, 40.0, size=(732, 2)).astype(np.float32)
        for year in years
    }
    table = OtsThresholdPlugin().process(
        iday=1,
        start_day=80,
        station_count=2,
        ec_by_year=ec_by_year,
        obs_by_year=obs_by_year,
        begin_year=2024,
        end_year=2024,
        pro_count=1,
    )
    bounds = build_threshold_bounds()
    assert table.shape == (20, 10)
    assert np.all(np.isfinite(table))
    assert np.all(table >= bounds[:, 0, :] - 1e-4)
    assert np.all(table <= bounds[:, 1, :] + 1e-4)


def test_forecast_plugin_corrects_and_sums_adjacent_leads():
    grid = _grid()
    missing = np.full((grid.num_y, grid.num_x), np.float32(9999.0))
    fields = [missing.copy() for _ in range(20)]
    fields[0] = np.full_like(missing, np.float32(10.0))
    fields[1] = np.full_like(missing, np.float32(4.0))
    thresholds = np.tile(THRESHOLD_IN, (20, 1))
    rain12, rain24 = OtsForecastPlugin().process(
        fields,
        [grid] * 20,
        grid,
        0.7,
        thresholds,
        pro_count=1,
    )
    assert len(rain12) == 20
    assert rain24[0] is None
    assert np.allclose(rain12[0], 10.0)
    assert np.allclose(rain12[1], 4.0)
    assert np.allclose(rain24[1], 14.0)
    assert np.all(rain24[2] == np.float32(9999.0))
