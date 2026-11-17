# -*- coding: utf-8 -*-
"""格点→站点插值辅助（对齐 ``utils.interpolating`` 中的经度预处理）。"""
from __future__ import annotations

import meteva_base as meb
import numpy as np


def reset_global_griddata(grd):
    """全球经度网展成平面时扩展一列，使末经度与首经度衔接。"""
    grid = meb.get_grid_of_data(grd)
    if grid.glon[1] + grid.glon[2] - grid.glon[0] - 360 > -0.001:
        glon1 = [grid.glon[0], grid.glon[1] + grid.glon[2], grid.glon[2]]
        grid1 = meb.grid(
            glon1, grid.glat, grid.gtime, grid.dtimes, grid.levels, grid.members
        )
        grd1 = meb.grid_data(grid1)
        grd1.values[:, :, :, :, :, :-1] = grd.values[:, :, :, :, :, :]
        grd1.values[:, :, :, :, :, -1] = grd.values[:, :, :, :, :, 0]
        return grd1
    return grd


def reset_lon_range(grd, sta):
    """将格点经度取值范围向站点对齐（-180～180 与 0～360）。"""
    grid = meb.get_grid_of_data(grd)
    slon0 = np.min(sta.loc[:, "lon"].values)
    if slon0 < 0 and grid.glon[1] > 180:
        lons0 = grd["lon"].values
        nlon = lons0.size
        index = np.argmax(lons0 > 180)
        lons1 = np.zeros(nlon)
        lons1[0 : nlon - index] = lons0[index:nlon] - 360
        lons1[nlon - index :] = lons0[0:index]
        glon1 = [lons1[0], lons1[-1], lons1[1] - lons1[0]]
        grid1 = meb.grid(
            glon1, grid.glat, grid.gtime, grid.dtimes, grid.levels, grid.members
        )
        grd1 = meb.grid_data(grid1)
        grd1.values[:, :, :, :, :, 0 : nlon - index] = grd.values[
            :, :, :, :, :, index:nlon
        ]
        grd1.values[:, :, :, :, :, nlon - index :] = grd.values[
            :, :, :, :, :, 0:index
        ]
        return grd1

    elon0 = np.max(sta.loc[:, "lon"].values)
    if elon0 > 180 and grid.glon[0] < 0:
        lons0 = grd["lon"].values
        nlon = lons0.size
        index = np.argmax(lons0 >= 0)
        lons1 = np.zeros(nlon)
        lons1[0 : nlon - index] = lons0[index:nlon]
        lons1[nlon - index :] = lons0[0:index] + 360
        grid1 = meb.grid(
            lons1, grid.glat, grid.gtime, grid.dtimes, grid.levels, grid.members
        )
        grd1 = meb.grid_data(grid1)
        grd1.values[:, :, :, :, :, 0 : nlon - index] = grd.values[
            :, :, :, :, :, index:nlon
        ]
        grd1.values[:, :, :, :, :, nlon - index :] = grd.values[
            :, :, :, :, :, 0:index
        ]
        return grd1
    return grd
