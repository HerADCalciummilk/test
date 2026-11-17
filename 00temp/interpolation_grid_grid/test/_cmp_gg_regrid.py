# -*- coding: utf-8 -*-
"""Compare InterpGg* vs regrid InterpGgLandSea on resource/data (in-domain)."""
from __future__ import annotations

import sys
from pathlib import Path

import meteva_base as meb
import numpy as np

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "interpolation_grid_grid" / "src"))
sys.path.insert(0, str(root / "interpolation_grid_grid"))
sys.path.insert(0, str(root))

from interp_gg_linear_plugin import InterpGgLinear  # noqa: E402
from interp_gg_nearest_plugin import InterpGgNearest  # noqa: E402
from interp_gg_landsea_plugin import InterpGgLandSea  # noqa: E402


def stats(a, b, name: str) -> None:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() == 0:
        print(name, "no finite overlap")
        return
    d = a[m] - b[m]
    print(
        f"{name}: n={int(m.sum())} max|d|={np.max(np.abs(d)):.6g} "
        f"mean|d|={np.mean(np.abs(d)):.6g} rmse={np.sqrt(np.mean(d * d)):.6g} "
        f"corr={np.corrcoef(a[m], b[m])[0, 1]:.8f}"
    )


def make_tmpl(src, glon, glat):
    g0 = meb.get_grid_of_data(src)
    tgt_full = meb.grid(glon, glat, g0.gtime, g0.dtimes, g0.levels, g0.members)
    tmpl = meb.grid_data(tgt_full)
    tmpl[:] = 0
    return meb.basicdata.grid(glon, glat), tmpl


def run_case(src, glon, glat, label: str) -> None:
    print(f"=== {label} ===")
    tgt_grid, tmpl = make_tmpl(src, glon, glat)
    print("tgt nlon/nlat", tgt_grid.nlon, tgt_grid.nlat)

    gg_lin = InterpGgLinear(outer_value=0.0).process(src, tgt_grid)
    gg_near = InterpGgNearest(outer_value=0.0).process(src, tgt_grid)
    rg_lin = InterpGgLandSea(regrid_mode="bilinear", extrapolation_mode="nan").process(
        src, tmpl
    )
    rg_near = InterpGgLandSea(regrid_mode="nearest", extrapolation_mode="nan").process(
        src, tmpl
    )
    rg_lin2 = InterpGgLandSea(regrid_mode="bilinear-2", extrapolation_mode="nan").process(
        src, tmpl
    )
    rg_near2 = InterpGgLandSea(regrid_mode="nearest-2", extrapolation_mode="nan").process(
        src, tmpl
    )

    stats(gg_lin.values, rg_lin.values, "GgLinear vs RGI bilinear")
    stats(gg_lin.values, rg_lin2.values, "GgLinear vs bilinear-2")
    stats(rg_lin.values, rg_lin2.values, "RGI bilinear vs bilinear-2")
    stats(gg_near.values, rg_near.values, "GgNearest vs RGI nearest")
    stats(gg_near.values, rg_near2.values, "GgNearest vs nearest-2")
    stats(rg_near.values, rg_near2.values, "RGI nearest vs nearest-2")


def main() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "resource" / "data"
    src = meb.read_griddata_from_nc(str(data_dir / "2026100900.024.nc"))
    print("src", dict(src.sizes), "lon", float(src.lon.min()), float(src.lon.max()),
          "lat", float(src.lat.min()), float(src.lat.max()))

    # half-cell offset: stresses bilinear weights
    run_case(src, [70.05, 130.05, 0.1], [15.05, 55.05, 0.1], "half-cell offset 0.1")
    # coincident nodes
    run_case(src, [70.0, 130.0, 0.1], [15.0, 55.0, 0.1], "aligned 0.1")
    # finer target inside domain
    run_case(src, [80.0, 100.0, 0.05], [30.0, 40.0, 0.05], "finer 0.05 subset")


if __name__ == "__main__":
    main()
