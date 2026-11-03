# -*- coding: utf-8 -*-
"""裁剪真实样例并生成模板页用图（仅本地构建，不改 Skill）。"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import meteva_base as meb
from meteva_base.tool.plot_tools import pcolormesh_2d_grid

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from interp_gg_linear.src.interp_gg_linear import InterpGGLinearPlugin
from orographic_temperature_downscaling.src.lapse_rate import (
    ApplyGriddedLapseRate,
    LapseRate,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "resource" / "data" / "common_domain"
OUT = Path(__file__).resolve().parent
FIG = OUT / "figs"
FIG.mkdir(parents=True, exist_ok=True)

# 川西高原东缘：地形对比强，网格可控
LON0, LON1, LAT0, LAT1 = 103.0, 108.0, 28.0, 33.0
FILL_ABS = 1.0e5


def crop(g):
    lat_sel = (g.lat.values >= LAT0) & (g.lat.values <= LAT1)
    lon_sel = (g.lon.values >= LON0) & (g.lon.values <= LON1)
    out = g.isel(lat=lat_sel, lon=lon_sel).copy()
    v = np.asarray(out.values, dtype=np.float32)
    v = np.where(np.abs(v) > FILL_ABS, np.nan, v)
    return out.copy(data=v)


def write(grd, path, name=None, units=None):
    g = grd.copy()
    if name:
        g.name = name
    if units is not None:
        g.attrs["units"] = units
    meb.write_griddata_to_nc(g, str(path), creat_dir=True)


def to_C(da):
    u = str(da.attrs.get("units", "")).lower().replace("°", "")
    if u in ("k", "kelvin"):
        out = da - 273.15
        out.attrs["units"] = "℃"
        return out
    return da


def main() -> None:
    t = crop(
        meb.read_griddata_from_nc(
            str(SRC / "ec_tmp2m/2026/20261010/2026101000.000.nc")
        )
    )
    z = crop(meb.read_griddata_from_nc(str(SRC / "ancil/ec_source_orography.nc")))
    m = crop(meb.read_griddata_from_nc(str(SRC / "ancil/ec_land_sea_mask.nc")))
    m = m.copy(data=(np.asarray(m.values) >= 0.5).astype(np.float32))
    h = crop(meb.read_griddata_from_nc(str(SRC / "ancil/HGT_M_1KM_CHINA.nc")))

    write(t, OUT / "t_coarse.nc", name="air_temperature", units="℃")
    write(z, OUT / "z_coarse.nc", name="surface_altitude", units="m")
    write(m, OUT / "landmask.nc", name="land_binary_mask", units="1")
    write(h, OUT / "z_dest_fine.nc", name="surface_altitude", units="m")

    meta = {
        "lon_min": LON0,
        "lon_max": LON1,
        "lat_min": LAT0,
        "lat_max": LAT1,
        "time": "2026-10-10 00UTC +0h",
        "source": "common_domain EC tmp2m / EC orography / landmask / HGT 1km",
        "shapes": {
            "t": list(t.shape),
            "z": list(z.shape),
            "mask": list(m.shape),
            "hgt": list(h.shape),
        },
    }
    (OUT / "domain.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote demo", meta)

    temperature = meb.read_griddata_from_nc(str(OUT / "t_coarse.nc"))
    orography = meb.read_griddata_from_nc(str(OUT / "z_coarse.nc"))
    land_sea_mask = meb.read_griddata_from_nc(str(OUT / "landmask.nc")).astype(bool)
    dest_orog = meb.read_griddata_from_nc(str(OUT / "z_dest_fine.nc"))
    temperature.attrs["units"] = "℃"
    orography.attrs["units"] = "m"
    dest_orog.attrs["units"] = "m"

    print("=== temperature ===")
    print(temperature)
    t_c_vals = np.asarray(temperature.values, dtype=np.float64)
    t_clevs = list(
        np.linspace(np.nanpercentile(t_c_vals, 2), np.nanpercentile(t_c_vals, 98), 12)
    )
    pcolormesh_2d_grid(
        temperature,
        save_path=str(FIG / "t_coarse.png"),
        title="粗网格气温（℃，EC 0.1°）",
        clevs=t_clevs,
        cmap="RdYlBu_r",
        show=False,
    )
    z_clevs = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
    pcolormesh_2d_grid(
        orography,
        save_path=str(FIG / "z_coarse.png"),
        title="粗网格源地形（m，EC 0.1°）",
        clevs=z_clevs,
        cmap="terrain",
        show=False,
    )

    gamma = LapseRate(max_height_diff=1200.0, nbhood_radius=2).process(
        temperature, orography, land_sea_mask
    )
    print("=== gamma ===")
    print(gamma)
    g_clevs = [-10.0, -9.0, -8.0, -7.5, -7.0, -6.5, -6.0, -5.5, -5.0, -4.0, -3.0]
    pcolormesh_2d_grid(
        gamma * 1000.0,
        save_path=str(FIG / "gamma.png"),
        title="粗网格 Γ（K/km，EC 0.1°）",
        clevs=g_clevs,
        cmap="coolwarm",
        show=False,
    )

    dlon = float(np.diff(dest_orog.lon.values[:2])[0])
    dlat = float(np.diff(dest_orog.lat.values[:2])[0])
    g_f = meb.grid(
        [float(dest_orog.lon.min()), float(dest_orog.lon.max()), dlon],
        [float(dest_orog.lat.min()), float(dest_orog.lat.max()), dlat],
    )
    interp = InterpGGLinearPlugin(used_coords="xy", outer_value=0.0)
    t_fine = interp.process(temperature, g_f)
    g_fine = interp.process(gamma, g_f)
    src_fine = interp.process(orography, g_f)
    t_fine.attrs["units"] = "℃"
    g_fine.attrs["units"] = "K m-1"
    src_fine.attrs["units"] = "m"

    assert t_fine.shape[-2:] == dest_orog.shape[-2:], (t_fine.shape, dest_orog.shape)
    t_corr = ApplyGriddedLapseRate().process(t_fine, g_fine, src_fine, dest_orog)
    print("=== t_corr ===")
    print(t_corr)

    t_before_C = to_C(t_fine)
    t_after_C = to_C(t_corr)
    t_fine_K = (
        t_fine + 273.15
        if str(t_fine.attrs.get("units")) in ("℃", "C", "celsius")
        else t_fine
    )
    delta = t_corr - t_fine_K

    t_f_vals = np.asarray(t_before_C.values, dtype=np.float64)
    t_clevs_f = list(
        np.linspace(np.nanpercentile(t_f_vals, 2), np.nanpercentile(t_f_vals, 98), 12)
    )
    pcolormesh_2d_grid(
        dest_orog,
        save_path=str(FIG / "z_fine.png"),
        title="细网格目标地形（m，1 km DEM）",
        clevs=z_clevs,
        cmap="terrain",
        show=False,
    )
    pcolormesh_2d_grid(
        t_before_C,
        save_path=str(FIG / "t_before.png"),
        title="插到细网格后的气温（订正前，℃，1 km）",
        clevs=t_clevs_f,
        cmap="RdYlBu_r",
        show=False,
    )
    pcolormesh_2d_grid(
        t_after_C,
        save_path=str(FIG / "t_after.png"),
        title="地形订正后气温（℃，1 km）",
        clevs=t_clevs_f,
        cmap="RdYlBu_r",
        show=False,
    )
    pcolormesh_2d_grid(
        delta,
        save_path=str(FIG / "t_delta.png"),
        title="订正增量（K，1 km）",
        cmap="bwr",
        show=False,
    )

    (OUT / "stdout_temperature.txt").write_text(str(temperature), encoding="utf-8")
    (OUT / "stdout_gamma.txt").write_text(str(gamma), encoding="utf-8")
    (OUT / "stdout_t_corr.txt").write_text(str(t_corr), encoding="utf-8")
    (OUT / "t_clevs.json").write_text(json.dumps(t_clevs), encoding="utf-8")
    (OUT / "t_clevs_fine.json").write_text(json.dumps(t_clevs_f), encoding="utf-8")
    print("figs", sorted(p.name for p in FIG.glob("*.png")))
    print(
        "delta range",
        float(np.nanmin(delta.values)),
        float(np.nanmax(delta.values)),
    )


if __name__ == "__main__":
    main()
