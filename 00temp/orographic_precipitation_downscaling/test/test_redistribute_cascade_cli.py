"""分档订正 CLI 的档参数展开，以及一条小网格上的串联。"""

from pathlib import Path
import sys

import numpy as np
import pytest
import xarray as xr

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = Path(__file__).resolve().parents[2]
if str(TEMP_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMP_ROOT))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from cli.dsc_redistribute_cascade import build_cascade_stages, process

MEB_DIMS = ("member", "level", "time", "dtime", "lat", "lon")


def test_product_stage_overrides():
    specs = build_cascade_stages(
        "20,5,1",
        precip_spacing_km=10,
        zero_below=0.2,
    )
    assert len(specs) == 2
    assert specs[0]["from_km"] == 20
    assert specs[0]["to_km"] == 5
    assert specs[0]["smooth_radius"] == 2
    assert specs[0]["block_cells"] == 4
    assert specs[0]["zero_below_mmh"] == 0.2
    assert specs[1]["zero_below_mmh"] == 0.0
    assert specs[1]["smooth_radius"] == 5
    assert specs[1]["block_cells"] == 5
    assert "passes" not in specs[0]
    assert "sigma_km" not in specs[1]


def test_four_level_defaults():
    specs = build_cascade_stages("25,10,5,1", precip_spacing_km=10, zero_below=0.2)
    assert [item["from_km"] for item in specs] == [25, 10, 5]
    assert [item["to_km"] for item in specs] == [10, 5, 1]
    assert [item["smooth_radius"] for item in specs] == [1, 2, 5]
    assert [item["block_cells"] for item in specs] == [2, 2, 5]
    assert specs[0]["zero_below_mmh"] == 0.2
    assert specs[1]["zero_below_mmh"] == 0.0
    assert specs[2]["zero_below_mmh"] == 0.0


def test_omitted_zero_below_is_off():
    specs = build_cascade_stages("20,5,1", precip_spacing_km=10)
    assert specs[0]["zero_below_mmh"] == 0.0
    assert specs[0]["smooth_radius"] == 2
    assert specs[1]["smooth_radius"] == 5
    assert specs[0]["block_cells"] == 4


def test_doe_smooth_radius_is_grid_cells():
    from orographic_precipitation_downscaling.src.redistribute_orographic_enhancement import (
        RedistributeOrographicEnhancement,
    )

    field = np.zeros((5, 5), dtype=np.float64)
    field[2, 2] = 9.0
    out = RedistributeOrographicEnhancement._masked_local_mean(
        field, np.isfinite(field), 1
    )
    assert out[2, 2] == pytest.approx(1.0)
    assert out[0, 0] == 0.0
    assert out[1, 1] == pytest.approx(1.0)


def test_block_id_uses_grid_cells():
    from orographic_precipitation_downscaling.src.redistribute_orographic_enhancement import (
        RedistributeOrographicEnhancement,
    )

    ids = RedistributeOrographicEnhancement._coarse_block_id((4, 4), 2)
    assert ids[0, 0] == ids[1, 1]
    assert ids[0, 0] != ids[0, 2]
    assert ids[0, 0] != ids[2, 0]


def test_rejects_bad_stage_lists():
    with pytest.raises(ValueError):
        build_cascade_stages("5,20,1", precip_spacing_km=10)
    with pytest.raises(ValueError):
        build_cascade_stages("20,7,2", precip_spacing_km=10)
    with pytest.raises(ValueError):
        build_cascade_stages("20,5,1", precip_spacing_km=0)


def _meb6d(values: np.ndarray, lat: np.ndarray, lon: np.ndarray, units: str, name: str) -> xr.DataArray:
    data = xr.DataArray(
        np.asarray(values, dtype=np.float32)[None, None, None, None, :, :],
        dims=MEB_DIMS,
        coords={
            "member": ["data0"],
            "level": [1000.0],
            "time": [np.datetime64("1970-01-01T00:00:00")],
            "dtime": [0],
            "lat": np.asarray(lat, dtype=np.float64),
            "lon": np.asarray(lon, dtype=np.float64),
        },
        attrs={"units": units},
        name=name,
    )
    data.coords["level"].attrs["units"] = "m"
    return data


def test_cascade_on_small_grid_changes_wet_field(tmp_path):
    n_lat, n_lon = 8, 8
    lat = np.linspace(30.0, 30.07, n_lat)
    lon = np.linspace(100.0, 100.07, n_lon)
    coarse_lat = np.linspace(30.0, 30.07, 4)
    coarse_lon = np.linspace(100.0, 100.07, 4)
    topo = np.zeros((n_lat, n_lon), dtype=np.float32)
    topo[4:, :] = 80.0
    model_topo = np.zeros((4, 4), dtype=np.float32)
    model_topo[2:, :] = 40.0
    precip = np.full((4, 4), 3.0, dtype=np.float32)

    def _write(values, lat_axis, lon_axis, units, name):
        path = tmp_path / f"{name}.nc"
        _meb6d(values, lat_axis, lon_axis, units, name).to_dataset(name=name).to_netcdf(path)
        return str(path)

    result = process(
        precip_path=_write(precip, coarse_lat, coarse_lon, "mm h-1", "precipitation_rate"),
        temperature_path=_write(np.full((4, 4), 20.0, dtype=np.float32), coarse_lat, coarse_lon, "degC", "temperature"),
        humidity_path=_write(np.full((4, 4), 90.0, dtype=np.float32), coarse_lat, coarse_lon, "%", "humidity"),
        pressure_path=_write(np.full((4, 4), 85000.0, dtype=np.float32), coarse_lat, coarse_lon, "Pa", "pressure"),
        uwind_path=_write(np.full((4, 4), 8.0, dtype=np.float32), coarse_lat, coarse_lon, "m s-1", "u"),
        vwind_path=_write(np.full((4, 4), 2.0, dtype=np.float32), coarse_lat, coarse_lon, "m s-1", "v"),
        orography_model_path=_write(model_topo, coarse_lat, coarse_lon, "m", "orography_model"),
        orography_target_path=_write(topo, lat, lon, "m", "orography_target"),
        stages="4,2,1",
        zero_below=0.2,
    )
    assert result.sizes["lat"] == n_lat
    assert result.sizes["lon"] == n_lon
    values = np.asarray(result.values, dtype=np.float64)
    assert np.isfinite(values).any()
    assert float(np.nanmax(values)) >= 0.0
