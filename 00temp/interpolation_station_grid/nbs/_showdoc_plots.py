# -*- coding: utf-8 -*-
"""Generate ShowDoc example plots from package real data."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import meteva_base as meb
import numpy as np
import pandas as pd
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from meteva_base.tool.plot_tools import pcolormesh_2d_grid

PACKAGE_ROOT = Path(r"d:\workspace\test\00temp\interpolation_station_grid")
DATA_DIR = PACKAGE_ROOT / "resource"
OUT_DIR = DATA_DIR / "showdoc_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path[:0] = [str(PACKAGE_ROOT / "src"), str(PACKAGE_ROOT)]

from interp_sg_cressman_plugin import InterpSgCressman
from interp_sg_gaussian_plugin import InterpSgGaussian
from interp_sg_idw_plugin import InterpSgIdw
from interp_sg_kriging import InterpSgKriging
from cli.interpolation_station_grid_cli import InterpolationStationGridCli

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# --- load real data ---
sta_raw = meb.read_stadata_from_csv(str(DATA_DIR / "20260602000000.csv")).copy()
sta_raw["time"] = pd.to_datetime("2026-06-02")
sta_raw = meb.sele_by_para(sta_raw, dtime=24)
obs = sta_raw[["level", "time", "dtime", "id", "lon", "lat", "obs_gust"]].copy()
fcst = sta_raw[["level", "time", "dtime", "id", "lon", "lat", "fcst_wind"]].copy()

lon0, lon1 = float(obs.lon.min()) - 0.5, float(obs.lon.max()) + 0.5
lat0, lat1 = float(obs.lat.min()) - 0.5, float(obs.lat.max()) + 0.5
tgt_grid = meb.basicdata.grid([lon0, lon1, 0.1], [lat0, lat1, 0.1])

# ensure CLI inputs
obs.to_csv(DATA_DIR / "obs_gust_d24.csv", index=False)
meb.write_griddata_to_nc(meb.grid_data(tgt_grid), str(DATA_DIR / "target_grid.nc"), creat_dir=True)

cmap, clevs = get_cmap_and_clevs_by_element_name("wind_speed")
print("wind_speed clevs n=", len(clevs), clevs)

# background from fcst_wind
bg = InterpSgIdw(effectR=150000, nearNum=8, decrease=2).process(fcst, tgt_grid)
meb.write_griddata_to_nc(bg, str(OUT_DIR / "bg_fcst_idw.nc"), creat_dir=True)

# methods with background
idw_bg = InterpSgIdw(
    effectR=150000, nearNum=8, decrease=2, outer_value=0.0
).process(obs, tgt_grid, background=bg)
gauss_bg = InterpSgGaussian(halfR=80000, outer_value=0.0).process(
    obs, tgt_grid, background=bg
)
cress_bg = InterpSgCressman(
    r_list=[200000, 100000, 50000], nearNum=40, outer_value=0.0
).process(obs, tgt_grid, background=bg)

# no-bg for kriging + idw pure
idw_nobg = InterpSgIdw(effectR=150000, nearNum=8, decrease=2).process(obs, tgt_grid)
krig_nobg = InterpSgKriging(model="spherical", nearNum=12).process(obs, tgt_grid)

# save prints
buf = io.StringIO()
with redirect_stdout(buf):
    print(idw_bg)
idw_print = buf.getvalue()
(OUT_DIR / "print_idw_bg.txt").write_text(idw_print, encoding="utf-8")

buf = io.StringIO()
with redirect_stdout(buf):
    print(krig_nobg)
(OUT_DIR / "print_krig.txt").write_text(buf.getvalue(), encoding="utf-8")

# plots — shared cmap/clevs
pairs = [
    (bg, "sg_before_bg.png", "订正前-背景场 (fcst_wind IDW)"),
    (idw_bg, "sg_idw_after.png", "订正后-InterpSgIdw + 背景"),
    (gauss_bg, "sg_gauss_after.png", "订正后-InterpSgGaussian + 背景"),
    (cress_bg, "sg_cress_after.png", "订正后-InterpSgCressman + 背景"),
    (idw_nobg, "sg_idw_nobg.png", "InterpSgIdw 无背景插值结果"),
    (krig_nobg, "sg_krig_nobg.png", "InterpSgKriging 无背景插值结果"),
]
for grd, name, title in pairs:
    pcolormesh_2d_grid(
        grd,
        save_path=str(OUT_DIR / name),
        title=title,
        cmap=cmap,
        clevs=clevs,
        show=False,
        dpi=120,
    )
    plt.close("all")
    print("wrote", name)

# CLI
out_nc = str(OUT_DIR / "cli_idw_bg_out.nc")
# write bg for CLI background
bg_path = str(OUT_DIR / "bg_fcst_idw.nc")
rc = InterpolationStationGridCli.call(
    module="idw",
    sta=str(DATA_DIR / "obs_gust_d24.csv"),
    grid=str(DATA_DIR / "target_grid.nc"),
    background=bg_path,
    output=out_nc,
    effect_r=150000,
    near_num=8,
    decrease=2,
    sta_type="csv",
    grid_type="nc",
    background_type="nc",
    output_type="nc",
)
print("cli rc", rc)
grd_cli = meb.read_griddata_from_nc(out_nc)
buf = io.StringIO()
with redirect_stdout(buf):
    print(grd_cli)
(OUT_DIR / "print_cli.txt").write_text(buf.getvalue(), encoding="utf-8")
pcolormesh_2d_grid(
    bg,
    save_path=str(OUT_DIR / "cli_before.png"),
    title="订正前-背景场",
    cmap=cmap,
    clevs=clevs,
    show=False,
    dpi=120,
)
plt.close("all")
pcolormesh_2d_grid(
    grd_cli,
    save_path=str(OUT_DIR / "cli_after.png"),
    title="订正后-CLI InterpSgIdw",
    cmap=cmap,
    clevs=clevs,
    show=False,
    dpi=120,
)
plt.close("all")
print("done", OUT_DIR)
