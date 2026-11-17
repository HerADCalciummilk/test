"""构造时间滞后示例数据。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from time_lagging.util.meteva_data import save_grid, save_station

HERE = Path(__file__).resolve().parents[1]
TESTDATA = HERE / "testdata"


def make_grid_cycles() -> tuple[xr.DataArray, xr.DataArray]:
    """00 时起报、时效 12 小时，与 06 时起报、时效 6 小时，有效时间都是 12 时。

    空间场有经纬度结构，但每个成员的空间平均值仍为 1/2 与 3/4，便于测试断言。
    """
    lats = np.linspace(28.0, 34.0, 12)
    lons = np.linspace(108.0, 114.0, 12)
    early = _grid(
        values=np.array([1.0, 2.0], dtype=np.float32),
        members=["0", "1"],
        cycle="2024-01-01 00:00",
        dtime=12,
        lats=lats,
        lons=lons,
        pattern_scale=0.6,
    )
    late = _grid(
        values=np.array([3.0, 4.0], dtype=np.float32),
        members=["0", "1"],
        cycle="2024-01-01 06:00",
        dtime=6,
        lats=lats,
        lons=lons,
        pattern_scale=0.8,
    )
    return early, late


def make_station_cycles() -> tuple[pd.DataFrame, pd.DataFrame]:
    early = _station("2024-01-01 00:00", 12, [1.0, 2.0])
    late = _station("2024-01-01 06:00", 6, [3.0, 4.0])
    return early, late


def write_testdata(directory: Path | None = None) -> Path:
    target = Path(directory) if directory is not None else TESTDATA
    target.mkdir(parents=True, exist_ok=True)
    early, late = make_grid_cycles()
    save_grid(early, target / "cycle_00.nc")
    save_grid(late, target / "cycle_06.nc")
    early_station, late_station = make_station_cycles()
    save_station(early_station, target / "cycle_00.csv")
    save_station(late_station, target / "cycle_06.csv")
    return target


def _grid(values, members, cycle, dtime, lats, lons, pattern_scale: float = 0.0) -> xr.DataArray:
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    lon2d, lat2d = np.meshgrid(lons, lats)
    anomaly = np.sin((lat2d - lats.min()) / max(float(np.ptp(lats)), 1e-6) * np.pi) * np.cos(
        (lon2d - lons.min()) / max(float(np.ptp(lons)), 1e-6) * np.pi
    )
    anomaly = anomaly - anomaly.mean()
    field = np.zeros((len(members), 1, 1, 1, len(lats), len(lons)), dtype=np.float32)
    for index, value in enumerate(values):
        field[index, 0, 0, 0] = value + pattern_scale * anomaly
    grid = xr.DataArray(
        field,
        coords={
            "member": list(members),
            "level": [0.0],
            "time": pd.to_datetime([cycle]),
            "dtime": [dtime],
            "lat": np.asarray(lats, dtype=np.float64),
            "lon": np.asarray(lons, dtype=np.float64),
        },
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name="air_temperature",
    )
    grid.attrs.update(
        {
            "dtime_units": "hour",
            "units": "degC",
            "level_type": "surface",
            "time_type": "UT",
            "model_var": "air_temperature",
            "time_bounds": [0, 0],
        }
    )
    return grid


def _station(cycle, dtime, member_values) -> pd.DataFrame:
    rows = []
    for station_id, lon, lat in ((54511, 116.28, 39.93), (54527, 117.20, 39.08)):
        for member, value in enumerate(member_values):
            rows.append(
                {
                    "level": 0,
                    "time": pd.Timestamp(cycle),
                    "dtime": dtime,
                    "id": station_id,
                    "lon": lon,
                    "lat": lat,
                    "member": member,
                    "air_temperature": value + (0 if station_id == 54511 else 10),
                }
            )
    frame = pd.DataFrame(rows)
    frame.attrs.update(
        {
            "dtime_units": "hour",
            "units": "degC",
            "level_type": "surface",
            "time_type": "UT",
            "model_var": "air_temperature",
            "time_bounds": [0, 0],
        }
    )
    return frame


if __name__ == "__main__":
    print(write_testdata())
