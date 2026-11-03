# -*- coding: utf-8 -*-
"""手工对照：构造源场后用本包 ``interp_gg_linear`` 插到更细网格并出图。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for p in (str(_ROOT), str(_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import meteva.base as meb
import numpy as np

from interp_gg_linear import interp_gg_linear

grid0 = meb.grid([70, 140, 1.0], [15, 55, 1.0])
grd = meb.grid_data(grid0)
lon = np.arange(grid0.nlon) * grid0.dlon + grid0.slon
lat = np.arange(grid0.nlat) * grid0.dlat + grid0.slat
xx, yy = np.meshgrid(lon, lat)
grd.values[0, 0, 0, 0, :, :] = xx + 0.5 * yy

grid1 = meb.grid([70, 140, 0.25], [15, 55, 0.25])
grd1 = interp_gg_linear(grd, grid1, used_coords="xy", outer_value=0.0)
print(grd1)
meb.plot_tools.contourf_2d_grid(grd1)
