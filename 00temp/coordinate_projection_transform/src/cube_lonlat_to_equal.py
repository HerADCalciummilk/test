# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2022， CMA National Meteorological Centre.
# All rights reserved.
#
# Distributed under the terms of the GPL v2 License.
#
"""Transform cube's map projection from lon/lat to equal distance."""

from copy import deepcopy
from typing import Tuple, Optional

import numpy as np
import iris
from iris.coords import DimCoord
from iris.cube import Cube
from cartopy import crs as ccrs

from improver import PostProcessingPlugin
from improver.utilities.cube_checker import check_for_x_and_y_axes

from nimm.metadata.grid_info import (
    CHINA_SECANT_LATITUDES, 
    GRID_COORD_ATTRIBUTES,
    ELLIPSOID,
)
from nimm.metadata.dtype_info import FLOAT_DTYPE


class CubeLonlatToEqual(PostProcessingPlugin):
    """
    Regridding cube with lat/lon coordinates to 
    Lambert Conformal Conic projection with equal 
    meter units.
    """
    
    def __init__(
        self,
        projection_extent: Optional[Tuple[float]]=None,
        secant_latitudes: Optional[Tuple[float]]=None,
        grid_distance: float=1000,
        regrid_mode: str="bilinear",
        extrapolation_mode: str="nanmask",
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
            
        if secant_latitudes is None:
            secant_latitudes = CHINA_SECANT_LATITUDES
        
        # Initial lambert conformal projection
        xy_coord = iris.coord_systems.LambertConformal(
            central_lon=(projection_extent[0]+projection_extent[1])/2.0,
            central_lat=(projection_extent[2]+projection_extent[3])/2.0,
            secant_latitudes = secant_latitudes,
            ellipsoid=ELLIPSOID)
        xy_proj = xy_coord.as_cartopy_crs()
        
         # construct equal distance coodinate points
        xmin, ymin = xy_proj.transform_point(
            projection_extent[0], projection_extent[2], src_crs=ccrs.PlateCarree())
        xmax, ymax = xy_proj.transform_point(
            projection_extent[1], projection_extent[3], src_crs=ccrs.PlateCarree())
        self.xpoints = np.arange(xmin, xmax+1, grid_distance, dtype=FLOAT_DTYPE)
        self.ypoints = np.arange(ymin, ymax+1, grid_distance, dtype=FLOAT_DTYPE)
        
        # create x/y coordinates
        self.coord_x = DimCoord(
            self.xpoints, 
            standard_name=GRID_COORD_ATTRIBUTES['equalarea']['xname'], 
            units=GRID_COORD_ATTRIBUTES['equalarea']['units'], 
            coord_system=xy_coord)
        self.coord_x.guess_bounds()
        self.coord_y = DimCoord(
            self.ypoints, 
            standard_name=GRID_COORD_ATTRIBUTES['equalarea']['yname'], 
            units=GRID_COORD_ATTRIBUTES['equalarea']['units'], 
            coord_system=xy_coord)
        self.coord_y.guess_bounds()
        
        self.projection_extent = projection_extent
        self.regrid_analysis = regrid_modes.get(regrid_mode)
        
        # used for caching regridder
        self.regridder = None
        
        
    def _create_target_cube(self, source_cube: Cube)->Cube:
        """
        Create the target cube with equal distance projection.

        Args:
            source_cube (Cube): 
                Source cube with lon/lat used for projection transform.

        Returns:
            Cube with equal distance projection and copy metedata from source cube.
        """
        check_for_x_and_y_axes(source_cube)
        
        yname = source_cube.coord(axis="y").name()
        xname = source_cube.coord(axis="x").name()
        ycoord_dim = source_cube.coord_dims(yname)
        xcoord_dim = source_cube.coord_dims(xname)
        
        # create target cube data
        source_cube_shape = [*source_cube.data.shape]
        source_cube_shape[xcoord_dim[0]] = len(self.xpoints)
        source_cube_shape[ycoord_dim[0]] = len(self.ypoints)
        data = np.zeros(source_cube_shape, dtype=FLOAT_DTYPE)
        
        # inherit metadata (cube name, units, attributes etc)
        metadata_dict = deepcopy(source_cube.metadata._asdict())
        new_cube = iris.cube.Cube(data, **metadata_dict)
        
        # inherit non-spatial coordinates
        for coord in source_cube.coords():
            if coord.name() not in [yname, xname]:
                if source_cube.coords(coord, dim_coords=True):
                    coord_dim = source_cube.coord_dims(coord)
                    new_cube.add_dim_coord(coord, coord_dim)
                else:
                    new_cube.add_aux_coord(coord)
                    
         # update spatial coordinates
        if len(xcoord_dim) > 0:
            new_cube.add_dim_coord(self.coord_x, xcoord_dim)
        else:
            new_cube.add_aux_coord(self.coord_x)

        if len(ycoord_dim) > 0:
            new_cube.add_dim_coord(self.coord_y, ycoord_dim)
        else:
            new_cube.add_aux_coord(self.coord_y)

        return new_cube


    def process(self, source_cube: Cube)->Cube:
        """
        Transform source_cube lon/lat projection to equal distance projection.

        Args:
            source_cube (Cube): 
                Source cube with lon/lat used for projection transform.

        Returns:
            _type_: _description_
        """
        check_for_x_and_y_axes(source_cube)
        
        # check cached regridder
        if self.regridder is not None:
            return self.regridder(source_cube)
        
        # create regridder
        new_cube = self._create_target_cube(source_cube)
        self.regridder = self.regrid_analysis.regridder(source_cube, new_cube)
        return self.regridder(source_cube)

