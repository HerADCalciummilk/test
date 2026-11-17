"""构造 QRF 示例数据。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from quantile_regression_random_forest.util.meteva_data import save_grid, save_station

HERE = Path(__file__).resolve().parents[1]
TESTDATA = HERE / "testdata"

STATIONS = (
    (54511, 116.28, 39.93, 50.0),
    (54527, 117.20, 39.08, 10.0),
    (54662, 117.72, 39.02, 5.0),
)
CYCLES = pd.to_datetime(
    ["2024-01-01 00:00", "2024-01-01 12:00", "2024-01-02 00:00", "2024-01-02 12:00"]
)
LEADS = (6, 12)
MEMBER_OFFSETS = (-1.5, -0.5, 0.5, 1.5)


def station_base(station_index: int, cycle_index: int, lead: int) -> float:
    return 10.0 + station_index * 5.0 + cycle_index * 2.0 + lead / 6.0


def make_station_case() -> tuple[pd.DataFrame, pd.DataFrame]:
    """集合预报相对实况有 +2 的系统偏差。"""
    forecast_rows = []
    truth_rows = []
    for station_index, (station_id, lon, lat, altitude) in enumerate(STATIONS):
        for cycle_index, cycle in enumerate(CYCLES):
            for lead in LEADS:
                base = station_base(station_index, cycle_index, lead)
                for member, offset in enumerate(MEMBER_OFFSETS):
                    forecast_rows.append(
                        {
                            "level": 0,
                            "time": cycle,
                            "dtime": lead,
                            "id": station_id,
                            "lon": lon,
                            "lat": lat,
                            "member": member,
                            "altitude": altitude,
                            "air_temperature": base + offset,
                        }
                    )
                truth_rows.append(
                    {
                        "level": 0,
                        "time": cycle + pd.to_timedelta(lead, unit="h"),
                        "dtime": 0,
                        "id": station_id,
                        "lon": lon,
                        "lat": lat,
                        "ob_value": base - 2.0,
                    }
                )
    forecast = _as_station(pd.DataFrame(forecast_rows), "degC")
    truth = _as_station(pd.DataFrame(truth_rows), "degC")
    return forecast, truth


def make_grid_case() -> tuple[xr.DataArray, xr.DataArray]:
    """12x12 格点、2 个起报时间、1 个时效、4 个成员，便于示例绘图。"""
    lats = np.linspace(28.0, 34.0, 12)
    lons = np.linspace(108.0, 114.0, 12)
    cycles = CYCLES[:2]
    lead = 6
    members = np.arange(4)
    n_lat, n_lon = len(lats), len(lons)
    forecast_data = np.zeros((4, 1, 2, 1, n_lat, n_lon), dtype=np.float32)
    truth_data = np.zeros((1, 1, 2, 1, n_lat, n_lon), dtype=np.float32)
    lon2d, lat2d = np.meshgrid(lons, lats)
    for cycle_index, _cycle in enumerate(cycles):
        base = (
            18.0
            + (lat2d - 30.0) * 3.5
            + (lon2d - 110.0) * 1.8
            + 1.2 * np.sin((lat2d - 28.0) / 2.0)
            + 0.8 * np.cos((lon2d - 108.0) / 1.5)
            + cycle_index * 3.0
        )
        for member, offset in enumerate(MEMBER_OFFSETS):
            forecast_data[member, 0, cycle_index, 0] = base + offset
        truth_data[0, 0, cycle_index, 0] = base - 2.0
    forecast = _as_grid(
        forecast_data,
        members=[str(item) for item in members],
        times=cycles,
        dtimes=[lead],
        lats=lats,
        lons=lons,
        name="air_temperature",
    )
    truth = _as_grid(
        truth_data,
        members=["0"],
        times=cycles + pd.to_timedelta(lead, unit="h"),
        dtimes=[0],
        lats=lats,
        lons=lons,
        name="air_temperature",
    )
    return forecast, truth


def write_testdata(directory: Path | None = None) -> Path:
    target = Path(directory) if directory is not None else TESTDATA
    target.mkdir(parents=True, exist_ok=True)
    forecast, truth = make_station_case()
    save_station(forecast, target / "forecast_sta.csv")
    save_station(truth, target / "truth_sta.csv")
    grid_forecast, grid_truth = make_grid_case()
    save_grid(grid_forecast, target / "forecast_grid.nc")
    save_grid(grid_truth, target / "truth_grid.nc")
    config = {
        "air_temperature": ["mean", "std", "hour_of_day_sin", "day_of_year_cos"],
        "altitude": ["static"],
    }
    (target / "feature_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    grid_config = {"air_temperature": ["mean", "std"]}
    (target / "feature_config_grid.json").write_text(
        json.dumps(grid_config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def _as_station(frame: pd.DataFrame, units: str) -> pd.DataFrame:
    frame = frame.copy()
    frame.attrs["dtime_units"] = "hour"
    frame.attrs["units"] = units
    frame.attrs["level_type"] = "surface"
    frame.attrs["time_type"] = "UT"
    frame.attrs["model_var"] = "air_temperature"
    frame.attrs["time_bounds"] = [0, 0]
    return frame


def _as_grid(data, members, times, dtimes, lats, lons, name: str) -> xr.DataArray:
    grid = xr.DataArray(
        np.asarray(data, dtype=np.float32),
        coords={
            "member": list(members),
            "level": [0.0],
            "time": pd.to_datetime(times),
            "dtime": list(dtimes),
            "lat": np.asarray(lats, dtype=np.float64),
            "lon": np.asarray(lons, dtype=np.float64),
        },
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name=name,
    )
    grid.attrs["dtime_units"] = "hour"
    grid.attrs["units"] = "degC"
    grid.attrs["level_type"] = "surface"
    grid.attrs["time_type"] = "UT"
    grid.attrs["model_var"] = name
    grid.attrs["time_bounds"] = [0, 0]
    return grid


if __name__ == "__main__":
    print(write_testdata())
