# -*- coding: utf-8 -*-
"""Lambert 等距 → 等经纬度（cartopy CRS + 规则网格插值）。

与 ``cube_equal_to_lonlat.CubeEqualToLonlat``（iris regridder）并行的新实现，
不改动原模块。用法相同：

    from cube_equal_to_lonlat_cartopy import CubeEqualToLonlatCartopy
    out = CubeEqualToLonlatCartopy(...).process(cube)
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
    make_lonlat_coords,
    regrid_cube_cartopy,
    source_xy_sig,
    target_query_in_source_crs,
)


class CubeEqualToLonlatCartopy(BasePlugin):
    """Lambert 等距 Cube → 等经纬度 Cube（cartopy 变换 + RegularGridInterpolator）。"""

    def __init__(
        self,
        lonlat_extent: Optional[Tuple[float, float, float, float]] = None,
        grid_spacing: float = 0.1,
        regrid_mode: str = "bilinear",
        extrapolation_mode: str = "nanmask",
    ):
        if regrid_mode not in ("bilinear", "nearest"):
            raise ValueError("Unrecognised regrid mode {}".format(regrid_mode))

        if lonlat_extent is None:
            lonlat_extent = (83.0, 138.0, 12.0, 53.0)

        self.xpoints, self.ypoints, self.coord_x, self.coord_y = make_lonlat_coords(
            lonlat_extent, grid_spacing
        )
        self.lonlat_extent = lonlat_extent
        self.regrid_mode = regrid_mode
        self.extrapolation_mode = extrapolation_mode
        self._query_yx = None
        self._src_xy_sig = None

    def process(self, source_cube: Cube) -> Cube:
        check_for_x_and_y_axes(source_cube)
        sig = source_xy_sig(source_cube, include_coord_system=True)
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
