# -*- coding: utf-8 -*-
"""Transform cube's map projection from equal distance to lon/lat."""

from typing import Optional, Tuple

import iris
from iris.cube import Cube

import sys as _bp_sys
from pathlib import Path as _BpPath

_bp_root = str(_BpPath(__file__).resolve().parents[1])
if _bp_root not in _bp_sys.path:
    _bp_sys.path.insert(0, _bp_root)
from utils.base_plugin import BasePlugin
from improver.utilities.cube_checker import check_for_x_and_y_axes

from utils.cpt_utils import build_target_cube_shell, make_lonlat_coords


class CubeEqualToLonlat(BasePlugin):
    """Regrid equal-distance (Lambert) cube onto a regular lon/lat grid."""

    def __init__(
        self,
        lonlat_extent: Optional[Tuple[float, float, float, float]] = None,
        grid_spacing: float = 0.1,
        regrid_mode: str = "bilinear",
        extrapolation_mode: str = "nanmask",
    ):
        """
        Args:
            lonlat_extent:
                Target lon/lat extent ``(lonmin, lonmax, latmin, latmax)``.
            grid_spacing:
                Lon/lat grid spacing in degrees.
            regrid_mode:
                ``bilinear`` or ``nearest``.
            extrapolation_mode:
                Fill mode outside source domain.
        """
        regrid_modes = {
            "bilinear": iris.analysis.Linear(extrapolation_mode=extrapolation_mode),
            "nearest": iris.analysis.Nearest(extrapolation_mode=extrapolation_mode),
        }
        if regrid_mode not in regrid_modes:
            raise ValueError("Unrecognised regrid mode {}".format(regrid_mode))

        if lonlat_extent is None:
            lonlat_extent = (83.0, 138.0, 12.0, 53.0)

        self.xpoints, self.ypoints, self.coord_x, self.coord_y = make_lonlat_coords(
            lonlat_extent, grid_spacing
        )
        self.lonlat_extent = lonlat_extent
        self.regrid_analysis = regrid_modes[regrid_mode]
        self.regridder = None

    def _create_target_cube(self, source_cube: Cube) -> Cube:
        check_for_x_and_y_axes(source_cube)
        return build_target_cube_shell(source_cube, self.coord_x, self.coord_y)

    def process(self, source_cube: Cube) -> Cube:
        """Regrid equal-distance cube to lon/lat."""
        check_for_x_and_y_axes(source_cube)
        if self.regridder is not None:
            return self.regridder(source_cube)
        new_cube = self._create_target_cube(source_cube)
        self.regridder = self.regrid_analysis.regridder(source_cube, new_cube)
        return self.regridder(source_cube)
