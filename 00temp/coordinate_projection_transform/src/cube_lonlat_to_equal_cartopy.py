# -*- coding: utf-8 -*-
"""等经纬度 → Lambert 等距（cartopy CRS + 规则网格插值）。

与 ``cube_lonlat_to_equal.CubeLonlatToEqual``（iris regridder）并行的新实现，
不改动原模块。用法相同：

    from cube_lonlat_to_equal_cartopy import CubeLonlatToEqualCartopy
    out = CubeLonlatToEqualCartopy(...).process(cube)
"""

from typing import Optional, Tuple

from iris.cube import Cube

import sys as _bp_sys
from pathlib import Path as _BpPath

_bp_root = str(_BpPath(__file__).resolve().parents[1])
if _bp_root not in _bp_sys.path:
    _bp_sys.path.insert(0, _bp_root)
from utils.base_plugin import BasePlugin
from improver.utilities.cube_checker import check_for_x_and_y_axes

from utils.cpt_utils import (
    make_equalarea_coords,
    regrid_cube_cartopy,
    source_xy_sig,
    target_query_in_source_crs,
)


class CubeLonlatToEqualCartopy(BasePlugin):
    """等经纬度 Cube → Lambert 等距 Cube（cartopy 变换 + RegularGridInterpolator）。"""

    def __init__(
        self,
        projection_extent: Optional[Tuple[float]] = None,
        secant_latitudes: Optional[Tuple[float]] = None,
        grid_distance: float = 1000,
        regrid_mode: str = "bilinear",
        extrapolation_mode: str = "nanmask",
    ):
        if regrid_mode not in ("bilinear", "nearest"):
            raise ValueError("Unrecognised regrid mode {}".format(regrid_mode))

        if projection_extent is None:
            projection_extent = (83, 138, 12, 53)

        self.xpoints, self.ypoints, self.coord_x, self.coord_y = make_equalarea_coords(
            projection_extent, secant_latitudes, grid_distance
        )
        self.projection_extent = projection_extent
        self.regrid_mode = regrid_mode
        self.extrapolation_mode = extrapolation_mode
        self._query_yx = None
        self._src_xy_sig = None

    def process(self, source_cube: Cube) -> Cube:
        check_for_x_and_y_axes(source_cube)
        sig = source_xy_sig(source_cube)
        if self._query_yx is None or self._src_xy_sig != sig:
            self._query_yx = target_query_in_source_crs(
                source_cube, self.coord_x, self.coord_y
            )
            self._src_xy_sig = sig
        return regrid_cube_cartopy(
            source_cube,
            self.coord_x,
            self.coord_y,
            regrid_mode=self.regrid_mode,
            extrapolation_mode=self.extrapolation_mode,
            query_yx=self._query_yx,
        )
