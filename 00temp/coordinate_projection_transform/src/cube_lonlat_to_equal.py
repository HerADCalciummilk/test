# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2022， CMA National Meteorological Centre.
# All rights reserved.
#
# Distributed under the terms of the GPL v2 License.
#
"""Transform cube's map projection from lon/lat to equal distance."""

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

from utils.cpt_utils import build_target_cube_shell, make_equalarea_coords


class CubeLonlatToEqual(BasePlugin):
    """
    Regridding cube with lat/lon coordinates to
    Lambert Conformal Conic projection with equal
    meter units.
    """

    def __init__(
        self,
        projection_extent: Optional[Tuple[float]] = None,
        secant_latitudes: Optional[Tuple[float]] = None,
        grid_distance: float = 1000,
        regrid_mode: str = "bilinear",
        extrapolation_mode: str = "nanmask",
    ):
        """
        Initialise projection transform parameters.

        Args:
            projection_extent (Optional[Tuple[float]], optional):
                Set the extent of target map projection. (lonmin, lonmax, latmin, latmax).
                Note the extent should be inclued the extent of source cube projection.
            secant_latitudes (Optional[Tuple[float]], optional):
                Secant intersection latitudes of Lambert Conformal projection.
            grid_distance (float, optional):
                Equal grid distance in meters. Defaults to 1000.
            regrid_mode (str, optional):
                Mode of interpolation in regridding. Valid options are
                "bilinear", "nearest". Defaults to "bilinear".
            extrapolation_mode (str, optional):
                Mode to fill regions outside the domain in regridding.
                Defaults to "nanmask".
        """
        regrid_modes = {
            "bilinear": iris.analysis.Linear(extrapolation_mode=extrapolation_mode),
            "nearest": iris.analysis.Nearest(extrapolation_mode=extrapolation_mode),
        }
        if regrid_mode not in regrid_modes.keys():
            msg = "Unrecognised regrid mode {}"
            raise ValueError(msg.format(regrid_mode))

        if projection_extent is None:
            projection_extent = (83, 138, 12, 53)

        self.xpoints, self.ypoints, self.coord_x, self.coord_y = make_equalarea_coords(
            projection_extent, secant_latitudes, grid_distance
        )
        self.projection_extent = projection_extent
        self.regrid_analysis = regrid_modes.get(regrid_mode)
        self.regridder = None

    def _create_target_cube(self, source_cube: Cube) -> Cube:
        """
        Create the target cube with equal distance projection.

        Args:
            source_cube (Cube):
                Source cube with lon/lat used for projection transform.

        Returns:
            Cube with equal distance projection and copy metedata from source cube.
        """
        check_for_x_and_y_axes(source_cube)
        return build_target_cube_shell(source_cube, self.coord_x, self.coord_y)

    def process(self, source_cube: Cube) -> Cube:
        """
        Transform source_cube lon/lat projection to equal distance projection.

        Args:
            source_cube (Cube):
                Source cube with lon/lat used for projection transform.

        Returns:
            Cube with equal distance projection.
        """
        check_for_x_and_y_axes(source_cube)

        if self.regridder is not None:
            return self.regridder(source_cube)

        new_cube = self._create_target_cube(source_cube)
        self.regridder = self.regrid_analysis.regridder(source_cube, new_cube)
        return self.regridder(source_cube)
