# -*- coding: utf-8 -*-
"""切变 UV 一例：对照 Lagrangian 与 project_align.extrapolate_like_lagrangian。"""
from __future__ import annotations

import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAIN_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
sys.path.insert(0, RAIN_SRC)
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils")]

from frequency_matching_rain24_plugin import Lagrangian  # noqa: E402
from utils.project_align import extrapolate_like_lagrangian  # noqa: E402
import meteva.base as meb  # noqa: E402

DLON = DLAT = 0.1


def main():
    grid = meb.grid([110.0, 114.0, DLON], [33.0, 37.0, DLAT])
    rain = meb.grid_data(grid)
    lon, lat = np.asarray(rain.lon), np.asarray(rain.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    field = 20.0 * np.exp(-((lon2d - 110.6) ** 2 + (lat2d - 33.6) ** 2) / 0.35 ** 2)
    rain.data = [[[[field]]]]
    w = (lat2d - lat.min()) / (lat.max() - lat.min())
    uu, vv = 0.4 * (0.5 + w), np.full_like(field, 0.1)
    u, v = rain.copy(), rain.copy()
    u.data, v.data = [[[[uu]]]], [[[[vv]]]]
    out_l = np.asarray(
        Lagrangian.simple_semi_lagrangian_in_angle(u, v, rain, 1.0).data
    ).squeeze()
    out_a = extrapolate_like_lagrangian(field, uu, vv, lon, lat, DLON, DLAT)
    print("maxAbs(align-L)=", np.max(np.abs(out_a - out_l)))


if __name__ == "__main__":
    main()
