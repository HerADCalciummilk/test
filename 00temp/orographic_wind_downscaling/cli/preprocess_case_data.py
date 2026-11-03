#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为 orographic_wind_downscaling 准备个例域 data/（辅料 + 可选风速）。

复用降水个例的空间域（105–122°E / 18–31°N）与 1 km DEM。
`a_over_s` / `sigma` 由 1 km DEM 近似生成（非 Met Office 官方 ancilla 流水线）：
- sigma：邻域地形高度标准差（近似次网格起伏）
- a_over_s：地形坡度模（上坡轮廓粗糙度的可运行近似）

近地面 10 m 风与风速实况若尚未到位，本脚本只写辅料与说明；风速可随后补。
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import xarray as xr
import meteva_base as meb

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG = REPO_ROOT / "orographic_wind_downscaling"
OUT_ROOT = PKG / "resource" / "data"

# 与降水个例对齐
PRECIP_DATA = (
    REPO_ROOT
    / "orographic_precipitation_downscaling"
    / "resource"
)
CASE_DOMAIN = {
    "lon_min": 105.0,
    "lon_max": 122.0,
    "lat_min": 18.0,
    "lat_max": 31.0,
    "label": "SE_China_浙闽赣湘粤桂琼",
}
# EC 气压层约 0.2°；中纬粗算模式分辨率（米），供 CLI model_resolution
EC_MODEL_RESOLUTION_M = 22000.0
SIGMA_WINDOW = 5  # 1 km 网格上 5×5 邻域估 sigma


def _ensure_path() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _read(path: Path) -> xr.DataArray:
    return meb.checkout_griddata(
        meb.read_griddata_from_nc(str(path)),
        valid_val=(-np.inf, np.inf, np.nan),
    )


def _write(da: xr.DataArray, path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = da.copy()
    out.name = name
    out.to_dataset(name=name).to_netcdf(path, mode="w")


def _as_meb2d(
    values: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    *,
    units: str,
    name: str,
    level: float = 0.0,
) -> xr.DataArray:
    arr = np.asarray(values, dtype=np.float32)[None, None, None, None, :, :]
    da = xr.DataArray(
        arr,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": ["EC"],
            "level": [level],
            "time": [np.datetime64("1970-01-01T00:00:00")],
            "dtime": [0],
            "lat": lat,
            "lon": lon,
        },
        name=name,
        attrs={"units": units},
    )
    da.level.attrs["units"] = "m"
    return da


def _crop(da: xr.DataArray) -> xr.DataArray:
    return da.sel(
        lat=slice(CASE_DOMAIN["lat_min"], CASE_DOMAIN["lat_max"]),
        lon=slice(CASE_DOMAIN["lon_min"], CASE_DOMAIN["lon_max"]),
    )


def _field2d(da: xr.DataArray) -> np.ndarray:
    return np.asarray(da.values, dtype=np.float64).reshape(da.lat.size, da.lon.size)


def _moving_std(z: np.ndarray, win: int) -> np.ndarray:
    """简单邻域标准差（忽略 nan）。"""
    from numpy.lib.stride_tricks import sliding_window_view

    pad = win // 2
    zp = np.pad(z, pad, mode="edge")
    windows = sliding_window_view(zp, (win, win))
    # windows: (ny, nx, win, win)
    return np.nanstd(windows, axis=(-1, -2))


def _slope_magnitude(z: np.ndarray, dlat_deg: float, dlon_deg: float, lat: np.ndarray) -> np.ndarray:
    """地形坡度模 |∇h|（无量纲），作 a_over_s 可运行近似。"""
    # 南北：米；东西：按纬度缩放
    dy = dlat_deg * 111000.0
    dx = dlon_deg * 111000.0 * np.cos(np.deg2rad(lat)).reshape(-1, 1)
    dx = np.maximum(dx, 1.0)
    dhz = np.zeros_like(z)
    dhx = np.zeros_like(z)
    dhz[1:-1, :] = (z[2:, :] - z[:-2, :]) / (2.0 * dy)
    dhz[0, :] = (z[1, :] - z[0, :]) / dy
    dhz[-1, :] = (z[-1, :] - z[-2, :]) / dy
    for j in range(z.shape[0]):
        row_dx = float(dx[j, 0])
        dhx[j, 1:-1] = (z[j, 2:] - z[j, :-2]) / (2.0 * row_dx)
        dhx[j, 0] = (z[j, 1] - z[j, 0]) / row_dx
        dhx[j, -1] = (z[j, -1] - z[j, -2]) / row_dx
    slope = np.hypot(dhx, dhz)
    return np.clip(slope, 0.0, 0.5)


def build_ancillaries() -> Dict[str, Path]:
    """生成 pporo / modoro / sigma / a_over_s。"""
    dem_src = PRECIP_DATA / "data" / "ancil" / "HGT_M_1KM_case_domain.nc"
    if not dem_src.exists():
        dem_src = PRECIP_DATA / "ancil" / "HGT_M_1KM_CHINA.nc"
    orog_src = PRECIP_DATA / "ancil" / "ec_source_orography.nc"
    if not orog_src.exists():
        orog_src = PRECIP_DATA / "data" / "ancil" / "ec_orography_on_met_grid.nc"

    dem = _crop(_read(dem_src))
    orog = _crop(_read(orog_src))
    # 模式地形插到 1 km 目标网格
    modoro = meb.interp_gg_linear(orog, meb.get_grid_of_data(dem), outer_value=np.nan)
    modoro = meb.checkout_griddata(
        modoro, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
    )

    z = _field2d(dem)
    lat = dem.lat.values
    lon = dem.lon.values
    dlat = float(lat[1] - lat[0])
    dlon = float(lon[1] - lon[0])
    sigma = _moving_std(z, SIGMA_WINDOW)
    a_over_s = _slope_magnitude(z, dlat, dlon, lat)

    written = {}
    pairs = [
        (dem, "pporo", "m", "surface_altitude", OUT_ROOT / "ancil" / "pporo.nc"),
        (modoro, "modoro", "m", "model_orography", OUT_ROOT / "ancil" / "modoro.nc"),
    ]
    for da, key, units, vname, path in pairs:
        da = da.copy()
        da.attrs["units"] = units
        da.attrs["case_domain"] = CASE_DOMAIN["label"]
        _write(da, path, vname)
        written[key] = path

    sigma_da = _as_meb2d(sigma, lat, lon, units="m", name="standard_deviation_of_height_in_grid_cell")
    sigma_da.attrs["note"] = f"approx from {SIGMA_WINDOW}x{SIGMA_WINDOW} neighborhood of 1km DEM"
    sigma_da.attrs["case_domain"] = CASE_DOMAIN["label"]
    path = OUT_ROOT / "ancil" / "sigma.nc"
    _write(sigma_da, path, sigma_da.name)
    written["sigma"] = path

    aos_da = _as_meb2d(a_over_s, lat, lon, units="1", name="silhouette_roughness")
    aos_da.attrs["note"] = "approx |grad h|; runnable proxy for silhouette roughness"
    aos_da.attrs["case_domain"] = CASE_DOMAIN["label"]
    path = OUT_ROOT / "ancil" / "a_over_s.nc"
    _write(aos_da, path, aos_da.name)
    written["a_over_s"] = path

    # 记录 model_resolution
    (OUT_ROOT / "ancil" / "model_resolution.txt").write_text(
        f"{EC_MODEL_RESOLUTION_M}\n# EC ~0.2 deg, meters near mid-lat\n",
        encoding="utf-8",
    )
    return written


def discover_uv_index(elem: str = "UGRD", level: str = "850") -> Dict[str, List[int]]:
    root = PRECIP_DATA / elem / level
    index: Dict[str, List[int]] = {}
    if not root.exists():
        return index
    for p in root.rglob("*.nc"):
        if "." not in p.stem:
            continue
        init_s, lead_s = p.stem.split(".", 1)
        try:
            lead = int(lead_s)
        except ValueError:
            continue
        index.setdefault(init_s, []).append(lead)
    for k in index:
        index[k] = sorted(set(index[k]))
    return index


def best_forecast(valid: datetime, index: Dict[str, List[int]], lead_step: int = 3):
    best = None
    for init_s, leads in index.items():
        init = datetime.strptime(init_s, "%Y%m%d%H")
        lead = int((valid - init).total_seconds() // 3600)
        if lead < 0 or lead not in leads or lead % lead_step:
            continue
        cand = (init, lead)
        if best is None or lead < best[1]:
            best = cand
    return best


def build_wind_speed_from_uv850(
    *,
    start_bjt: str = "2026083100",
    end_bjt: str = "2026090323",
    target_dem: Optional[xr.DataArray] = None,
) -> int:
    """用现有 850 hPa U/V 合成风速并插到 1 km（过渡产品；level 标为约 1500 m）。

    正式检验近地面风速仍建议补 UGRD_10M/VGRD_10M。
    """
    dem = target_dem
    if dem is None:
        dem = _read(OUT_ROOT / "ancil" / "pporo.nc")
    index = discover_uv_index("UGRD", "850")
    if not index:
        print("未找到 UGRD/850，跳过风速过渡产品")
        return 0

    start = datetime.strptime(start_bjt, "%Y%m%d%H") - timedelta(hours=8)
    end = datetime.strptime(end_bjt, "%Y%m%d%H") - timedelta(hours=8)
    # 对齐 3 h
    cur = start.replace(hour=(start.hour // 3) * 3, minute=0, second=0, microsecond=0)
    n_ok = 0
    rows = []
    while cur <= end:
        hit = best_forecast(cur, index, 3)
        bjt = cur + timedelta(hours=8)
        row = {
            "bjt": bjt.strftime("%Y%m%d%H"),
            "utc_valid": cur.strftime("%Y%m%d%H"),
            "init": "",
            "lead": "",
            "wind_speed": "",
            "source": "UGRD/VGRD 850 -> speed -> 1km",
            "note": "",
        }
        if hit is None:
            row["note"] = "no_uv"
            rows.append(row)
            cur += timedelta(hours=3)
            continue
        init, lead = hit
        init_s = init.strftime("%Y%m%d%H")
        day = init.strftime("%Y%m%d")
        year = init.strftime("%Y")
        stem = f"{init_s}.{lead:03d}"
        up = PRECIP_DATA / "UGRD" / "850" / year / day / f"{stem}.nc"
        vp = PRECIP_DATA / "VGRD" / "850" / year / day / f"{stem}.nc"
        if not up.exists() or not vp.exists():
            row["note"] = "missing_uv_file"
            rows.append(row)
            cur += timedelta(hours=3)
            continue
        u = _read(up)
        v = _read(vp)
        # 合成后再插到 1 km（在模式网格上合成，避免两次插值相位差）
        spd = u.copy(deep=True)
        spd.values = np.hypot(
            np.asarray(u.values, dtype=np.float64),
            np.asarray(v.values, dtype=np.float64),
        ).astype(np.float32)
        spd.attrs["units"] = "m s-1"
        spd.name = "wind_speed"
        spd_f = meb.interp_gg_linear(spd, meb.get_grid_of_data(dem), outer_value=np.nan)
        spd_f = meb.checkout_griddata(
            spd_f, valid_val=(-np.inf, np.inf, np.nan)
        )
        # level：850 层几何高度粗标 1500 m（米），供插件高度逻辑使用
        spd_f = spd_f.assign_coords(level=("level", [1500.0]))
        spd_f.level.attrs["units"] = "m"
        spd_f.attrs["units"] = "m s-1"
        spd_f.attrs["source_stem"] = stem
        spd_f.attrs["source_level"] = "850hPa"
        spd_f.attrs["note"] = "interim product; prefer UGRD_10M for surface verification"
        out = OUT_ROOT / "wind_speed" / f"{cur.strftime('%Y%m%d%H')}.nc"
        _write(spd_f, out, "wind_speed")
        row["init"] = init_s
        row["lead"] = str(lead)
        row["wind_speed"] = str(out.relative_to(OUT_ROOT))
        rows.append(row)
        n_ok += 1
        print(f"[OK wind] {cur.strftime('%Y%m%d%H')} <- {stem}")
        cur += timedelta(hours=3)

    meta = OUT_ROOT / "meta" / "time_alignment.csv"
    meta.parent.mkdir(parents=True, exist_ok=True)
    with meta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["utc_valid"])
        if rows:
            w.writeheader()
            w.writerows(rows)
    return n_ok


def write_readme(*, n_wind: int) -> None:
    path = OUT_ROOT / "meta" / "README.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"""# orographic_wind_downscaling 个例数据

## 空间域
- 与降水个例一致：`{CASE_DOMAIN['lon_min']}–{CASE_DOMAIN['lon_max']}°E` / `{CASE_DOMAIN['lat_min']}–{CASE_DOMAIN['lat_max']}°N`
- 目标网格：1 km DEM（`ancil/pporo.nc`）

## 已就绪（辅料）
| 文件 | 用途 | CLI 参数 |
| --- | --- | --- |
| `ancil/pporo.nc` | 目标细地形 | `target_orography_path` |
| `ancil/modoro.nc` | 模式地形→目标网格 | `standard_orography_path` |
| `ancil/sigma.nc` | 高度标准差（邻域近似） | `sigma_path` |
| `ancil/a_over_s.nc` | 轮廓粗糙度（坡度近似） | `silhouette_roughness_path` |
| `ancil/model_resolution.txt` | ≈{EC_MODEL_RESOLUTION_M} m | `model_resolution` |

`sigma` / `a_over_s` 为可运行近似，非 Met Office 官方 ancilla 产品。

## 风速（过渡）
- 已从降水包同个例的 **850 hPa U/V** 合成并插到 1 km：`wind_speed/`（{n_wind} 个 3 h 时次）
- `level` 暂标 **1500 m**；**不适合当作 10 m 风速做近地面检验**

## 仍需补充（批量调度 + 检验）
1. **近地面风速**：`UGRD_10M` / `VGRD_10M`（或业务 10 m 风速），对齐个例窗口后合成写入 `wind_speed/`，`level=10`
2. **风速实况**：如 HRCLDAS 10 m 风速（BJT），写入 `obs_wind/`，供订正前/后 RMSE
3. （可选）植被粗糙度 `z0` / `veg.nc`

## 时次
- 温湿风/现用 850 风：3 h（UTC 有效时文件名）
- 若 10 m 风为逐时，调度可逐时；检验对齐实况 BJT=+8
"""
    path.write_text(text, encoding="utf-8")
    dom = OUT_ROOT / "meta" / "case_domain.csv"
    with dom.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["label", "lon_min", "lon_max", "lat_min", "lat_max", "note"]
        )
        w.writeheader()
        w.writerow({**CASE_DOMAIN, "note": "same_as_precip_case; wind_ancil_ready"})


def main() -> None:
    _ensure_path()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    print("生成辅料…")
    written = build_ancillaries()
    for k, p in written.items():
        da = _read(p)
        print(f"  {k}: {p.name} shape={dict(da.sizes)}")
    print("生成过渡风速（850→1km）…")
    n_wind = build_wind_speed_from_uv850()
    write_readme(n_wind=n_wind)
    print(f"完成：辅料 OK；过渡风速 {n_wind}；见 {OUT_ROOT}")


if __name__ == "__main__":
    main()
