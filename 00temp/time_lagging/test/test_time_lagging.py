"""时间滞后集合测试。"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from time_lagging.src.time_lagging import time_lag  # noqa: E402
from time_lagging.util.demo_data import make_grid_cycles, make_station_cycles  # noqa: E402
from time_lagging.util.meteva_data import load_grid, load_station  # noqa: E402

PYTHON = sys.executable


def _grid(values, cycle, dtime, units="hour", members=None, lats=None, lons=None):
    members = ["0", "1"] if members is None else members
    lats = [30.0, 31.0] if lats is None else lats
    lons = [110.0, 111.0] if lons is None else lons
    field = np.zeros((len(members), 1, 1, 1, len(lats), len(lons)), dtype=np.float32)
    for index, value in enumerate(values):
        field[index] = value
    grid = xr.DataArray(
        field,
        coords={
            "member": members,
            "level": [0.0],
            "time": pd.to_datetime([cycle]),
            "dtime": [dtime],
            "lat": lats,
            "lon": lons,
        },
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name="air_temperature",
    )
    grid.attrs["dtime_units"] = units
    grid.attrs["units"] = "degC"
    return grid


class TimeLagTests(unittest.TestCase):
    def test_grid_rebadges_to_latest_cycle_and_renumbers_members(self):
        early, late = make_grid_cycles()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            lagged = time_lag(early, late)
        self.assertEqual(caught, [])
        self.assertEqual(pd.Timestamp(lagged.time.values[0]), pd.Timestamp("2024-01-01 06:00"))
        self.assertEqual(int(lagged.dtime.values[0]), 6)
        self.assertEqual(list(lagged.member.values), ["0", "1", "2", "3"])
        self.assertEqual(lagged.attrs["dtime_units"], "hour")
        means = lagged.mean(dim=("lat", "lon")).values.reshape(-1)
        self.assertTrue(np.allclose(means, [1, 2, 3, 4]))

    def test_station_keeps_validity_and_station_identity(self):
        early, late = make_station_cycles()
        lagged = time_lag(early, late)
        self.assertTrue((pd.to_datetime(lagged["time"]) == pd.Timestamp("2024-01-01 06:00")).all())
        self.assertTrue((lagged["dtime"] == 6).all())
        self.assertEqual(set(lagged["member"]), {0, 1, 2, 3})
        station = lagged[(lagged["id"] == 54511) & (lagged["member"] == 0)]
        self.assertAlmostEqual(float(station["air_temperature"].iloc[0]), 1.0)
        self.assertEqual(lagged.attrs["dtime_units"], "hour")

    def test_single_cycle_warns_and_returns_input(self):
        early, _late = make_grid_cycles()
        with self.assertWarns(UserWarning):
            lagged = time_lag(early)
        self.assertEqual(list(lagged.member.values), ["0", "1"])
        self.assertEqual(int(lagged.dtime.values[0]), 12)

    def test_mismatched_validity_raises(self):
        early, _late = make_grid_cycles()
        other = _grid([8, 9], "2024-01-01 06:00", 3)
        with self.assertRaises(ValueError):
            time_lag(early, other)

    def test_mismatched_grid_raises(self):
        early, late = make_grid_cycles()
        late = late.assign_coords(lat=late.lat.values + 2.0)
        with self.assertRaises(ValueError):
            time_lag(early, late)

    def test_minute_unit_shifts_by_minutes(self):
        early = _grid([5], "2024-01-01 00:00", 90, units="minute", members=["0"])
        late = _grid([7], "2024-01-01 01:00", 30, units="minute", members=["0"])
        lagged = time_lag(early, late)
        self.assertEqual(pd.Timestamp(lagged.time.values[0]), pd.Timestamp("2024-01-01 01:00"))
        self.assertEqual(int(lagged.dtime.values[0]), 30)
        self.assertEqual(lagged.attrs["dtime_units"], "minute")
        means = lagged.mean(dim=("lat", "lon")).values.reshape(-1)
        self.assertTrue(np.allclose(means, [5, 7]))

    def test_reorders_leads_before_merging(self):
        early_values = np.zeros((1, 1, 1, 2, 1, 1), dtype=np.float32)
        early_values[0, 0, 0, 0, 0, 0] = 2.0
        early_values[0, 0, 0, 1, 0, 0] = 1.0
        late_values = np.zeros((1, 1, 1, 2, 1, 1), dtype=np.float32)
        late_values[0, 0, 0, 0, 0, 0] = 8.0
        late_values[0, 0, 0, 1, 0, 0] = 9.0
        early = xr.DataArray(
            early_values,
            coords={
                "member": ["0"],
                "level": [0.0],
                "time": pd.to_datetime(["2024-01-01 00:00"]),
                "dtime": [12, 6],
                "lat": [30.0],
                "lon": [110.0],
            },
            dims=("member", "level", "time", "dtime", "lat", "lon"),
            name="air_temperature",
        )
        late = xr.DataArray(
            late_values,
            coords={
                "member": ["1"],
                "level": [0.0],
                "time": pd.to_datetime(["2024-01-01 06:00"]),
                "dtime": [0, 6],
                "lat": [30.0],
                "lon": [110.0],
            },
            dims=("member", "level", "time", "dtime", "lat", "lon"),
            name="air_temperature",
        )
        for grid in (early, late):
            grid.attrs["dtime_units"] = "hour"
        lagged = time_lag(early, late)
        self.assertTrue(np.array_equal(lagged.dtime.values, np.array([0, 6], dtype=np.int32)))
        # 有效时间 06 时的值是 early 的时效 6（数值 1）和 late 的时效 0（数值 8）。
        self.assertAlmostEqual(float(lagged.sel(member="0", dtime=0)), 1.0)
        self.assertAlmostEqual(float(lagged.sel(member="1", dtime=0)), 8.0)
        self.assertAlmostEqual(float(lagged.sel(member="0", dtime=6)), 2.0)
        self.assertAlmostEqual(float(lagged.sel(member="1", dtime=6)), 9.0)

    def test_cli_and_meteva_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "lagged.nc"
            grid_inputs = ",".join(
                [
                    str(REPO / "time_lagging" / "testdata" / "cycle_00.nc"),
                    str(REPO / "time_lagging" / "testdata" / "cycle_06.nc"),
                ]
            )
            completed = subprocess.run(
                [
                    PYTHON,
                    "-m",
                    "time_lagging",
                    f"inputs={grid_inputs}",
                    f"output={output}",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            loaded = load_grid(output)
            station_output = Path(temporary) / "lagged.csv"
            station_inputs = ",".join(
                [
                    str(REPO / "time_lagging" / "testdata" / "cycle_00.csv"),
                    str(REPO / "time_lagging" / "testdata" / "cycle_06.csv"),
                ]
            )
            station_run = subprocess.run(
                [
                    PYTHON,
                    "-m",
                    "time_lagging",
                    f"inputs={station_inputs}",
                    f"output={station_output}",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(station_run.returncode, 0, station_run.stderr)
            station = load_station(station_output)
        self.assertEqual(loaded.sizes["member"], 4)
        self.assertEqual(loaded.attrs["dtime_units"], "hour")
        self.assertEqual(set(station["member"].astype(int)), {0, 1, 2, 3})
        self.assertTrue((station["dtime"] == 6).all())


if __name__ == "__main__":
    unittest.main()
