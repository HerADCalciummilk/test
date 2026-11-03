#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""合成真经纬网格：RoughnessCorrection 端到端用例。

构造规则经纬 meb 六维场，不传 ``ppres``（由度→米推断），结果应与
显式传入正确米制 ``ppres`` 的参考结果一致；并与固化的预期场对照，
防止算法回归。
"""
from __future__ import annotations

import json

import numpy as np
import pytest
import xarray as xr

from orographic_wind_downscaling.src.wind_downscaling import EARTH_RADIUS_M, RoughnessCorrection

MODRES_M = 4000.0
COMPARE_ATOL = 1.0e-5


def _ppres_meters_from_latlon(lat: np.ndarray, lon: np.ndarray) -> float:
    dlat = float(np.median(np.abs(np.diff(lat))))
    dlon = float(np.median(np.abs(np.diff(lon))))
    lat0 = float(np.median(lat))
    dy_m = np.deg2rad(dlat) * EARTH_RADIUS_M
    dx_m = np.deg2rad(dlon) * EARTH_RADIUS_M * np.cos(np.deg2rad(lat0))
    return float(np.mean([abs(dy_m), abs(dx_m)]))


def _as_meb6d(
    values2d: np.ndarray,
    *,
    lat: np.ndarray,
    lon: np.ndarray,
    name: str,
    units: str,
    levels: np.ndarray | None = None,
) -> xr.DataArray:
    """二维或 (level, lat, lon) 场 → 六维 meb DataArray（真经纬）。"""
    arr = np.asarray(values2d, dtype=np.float32)
    if arr.ndim == 2:
        level_values = np.array([0.0], dtype=np.float32)
        data = arr[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    elif arr.ndim == 3:
        level_values = np.asarray(levels, dtype=np.float32)
        data = arr[np.newaxis, :, np.newaxis, np.newaxis, :, :]
    else:
        raise ValueError(f"不支持的数组维数: {arr.ndim}")

    return xr.DataArray(
        data,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.array(["data0"], dtype=object),
            "level": level_values,
            "time": np.array(
                [np.datetime64("1970-01-01T00:00:00")], dtype="datetime64[ns]"
            ),
            "dtime": np.array([0], dtype=np.int32),
            "lat": ("lat", np.asarray(lat, dtype=np.float64), {"units": "degrees_north"}),
            "lon": ("lon", np.asarray(lon, dtype=np.float64), {"units": "degrees_east"}),
        },
        name=name,
        attrs={
            "units": units,
            "dtime_units": "hour",
            "level_type": "height",
            "time_type": "UT",
            "grid_mapping_attrs": json.dumps(
                {"grid_mapping_name": "latitude_longitude"},
                ensure_ascii=False,
            ),
        },
    )


def _synthetic_latlon_case() -> dict:
    """构造确定性合成经纬输入（小网格，含海点）。"""
    rng = np.random.default_rng(20260812)
    n_lat, n_lon, n_levels = 6, 7, 4
    # ~0.05° ≈ 数公里，度→米后应明显大于 1
    lat = np.linspace(50.0, 50.25, n_lat, dtype=np.float64)
    lon = np.linspace(10.0, 10.3, n_lon, dtype=np.float64)
    levels = np.array([10.0, 50.0, 100.0, 200.0], dtype=np.float32)

    yy, xx = np.meshgrid(
        np.linspace(0.0, 1.0, n_lat),
        np.linspace(0.0, 1.0, n_lon),
        indexing="ij",
    )
    a_over_s = (0.05 + 0.1 * yy).astype(np.float32)
    sigma = (20.0 + 80.0 * xx).astype(np.float32)
    pporo = (100.0 + 200.0 * yy).astype(np.float32)
    modoro = (80.0 + 150.0 * xx).astype(np.float32)
    z0 = (0.05 + 0.2 * yy * xx).astype(np.float32)
    # 海点：关闭 HC/RC
    a_over_s[0, 0] = 0.0
    sigma[0, 0] = 0.0
    a_over_s[-1, -1] = 0.0
    sigma[-1, -1] = 0.0

    wind = np.zeros((n_levels, n_lat, n_lon), dtype=np.float32)
    for k, h in enumerate(levels):
        wind[k] = 5.0 + 0.02 * h + 1.5 * yy + 0.8 * xx
    wind += rng.normal(0.0, 0.05, size=wind.shape).astype(np.float32)
    wind = np.maximum(wind, 0.1).astype(np.float32)

    ppres_m = _ppres_meters_from_latlon(lat, lon)

    return {
        "lat": lat,
        "lon": lon,
        "levels": levels,
        "ppres_m": ppres_m,
        "a_over_s": _as_meb6d(a_over_s, lat=lat, lon=lon, name="a_over_s", units="1"),
        "sigma": _as_meb6d(sigma, lat=lat, lon=lon, name="sigma", units="m"),
        "pporo": _as_meb6d(pporo, lat=lat, lon=lon, name="pporo", units="m"),
        "modoro": _as_meb6d(modoro, lat=lat, lon=lon, name="modoro", units="m"),
        "z0": _as_meb6d(z0, lat=lat, lon=lon, name="z0", units="m"),
        "wind": _as_meb6d(
            wind, lat=lat, lon=lon, name="wind_speed", units="m s-1", levels=levels
        ),
    }


def test_synthetic_latlon_inferred_ppres_matches_explicit_reference() -> None:
    """不传 ppres 的经纬路径，应与显式米制 ppres 参考结果一致。"""
    case = _synthetic_latlon_case()
    assert case["ppres_m"] > 1000.0

    ref = RoughnessCorrection(
        case["a_over_s"],
        case["sigma"],
        case["pporo"],
        case["modoro"],
        MODRES_M,
        ppres=case["ppres_m"],
        z0=case["z0"],
    )
    expected = ref.process(case["wind"])

    auto = RoughnessCorrection(
        case["a_over_s"],
        case["sigma"],
        case["pporo"],
        case["modoro"],
        MODRES_M,
        z0=case["z0"],
    )
    result = auto.process(case["wind"])

    assert auto.ppres == pytest.approx(case["ppres_m"], rel=1e-10, abs=1e-6)
    assert isinstance(result, xr.DataArray)
    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    np.testing.assert_allclose(
        np.asarray(result.values, dtype=np.float64),
        np.asarray(expected.values, dtype=np.float64),
        atol=COMPARE_ATOL,
        rtol=0.0,
    )


def test_synthetic_latlon_matches_frozen_expected_field() -> None:
    """与固化预期场对照（显式正确米制 ppres 生成的参考）。"""
    case = _synthetic_latlon_case()
    plugin = RoughnessCorrection(
        case["a_over_s"],
        case["sigma"],
        case["pporo"],
        case["modoro"],
        MODRES_M,
        z0=case["z0"],
    )
    result = plugin.process(case["wind"])
    values = np.asarray(result.values, dtype=np.float64).reshape(-1)

    # 由同种子合成数据 + 显式 ppres 路径固化；若算法或推断改变应失败。
    expected_head = np.array(
        [
            5.1575675,
            4.77163029,
            4.50431538,
            4.236691,
            3.98065186,
            3.77464843,
            3.63234735,
            7.13934803,
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(values[: expected_head.size], expected_head, atol=2.0e-5)

    expected_stats = {
        "mean": 9.46074268363771,
        "max": 15.295589447021484,
        "min": 3.632347345352173,
    }
    assert float(np.nanmean(values)) == pytest.approx(expected_stats["mean"], abs=2.0e-5)
    assert float(np.nanmax(values)) == pytest.approx(expected_stats["max"], abs=2.0e-5)
    assert float(np.nanmin(values)) == pytest.approx(expected_stats["min"], abs=2.0e-5)


def test_synthetic_latlon_wrong_degree_ppres_differs() -> None:
    """若误把经纬度差分当米传入，结果应与正确米制路径明显不同。"""
    case = _synthetic_latlon_case()
    dlat = float(np.median(np.abs(np.diff(case["lat"]))))
    dlon = float(np.median(np.abs(np.diff(case["lon"]))))
    wrong_ppres = float(np.mean([dlat, dlon]))  # 约 0.05，量纲错误
    assert wrong_ppres < 1.0

    good = RoughnessCorrection(
        case["a_over_s"],
        case["sigma"],
        case["pporo"],
        case["modoro"],
        MODRES_M,
        z0=case["z0"],
    ).process(case["wind"])
    bad = RoughnessCorrection(
        case["a_over_s"],
        case["sigma"],
        case["pporo"],
        case["modoro"],
        MODRES_M,
        ppres=wrong_ppres,
        z0=case["z0"],
    ).process(case["wind"])

    diff = np.abs(
        np.asarray(good.values, dtype=np.float64) - np.asarray(bad.values, dtype=np.float64)
    )
    assert float(np.nanmax(diff)) > 1.0e-3
