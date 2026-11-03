# -*- coding: utf-8 -*-
"""
Created on Mon Apr 15 15:54:20 2024

@author: cheny
"""

from nimm import PostProcessingPlugin
from typing import Optional, Tuple
import meteva_base as meb
import numpy as np
from scipy.spatial import cKDTree


class InterpSgIdwDelta(PostProcessingPlugin):
    def __init__(self,
                 model_id_attr: Optional[str] = None,
                 effectR: Optional[int] = 1000,
                 nearNum: Optional[int] = 8,
                 decrease: Optional[int] = 2):
        """
        Initialise the class

        Args:
            model_id_attr:
                Name of the attribute used to identify the source model for
                blending.
        """
        self.model_id_attr = model_id_attr
        self.effectR = effectR
        self.nearNum = nearNum
        self.decrease = decrease

    def process(self, sta0, grid0,):
        # sta0:  站点数据
        # grid0:  格点数据，有背景场
        # effectR: 高斯半径(站点偏差影响附近网格的范围)
        sta = meb.sele_by_para(sta0, drop_IV=True)
        grid2 = meb.get_grid_of_data(grid0)  # 格点信息
        sta.iloc[:, -1] = sta.iloc[:, -1] - meb.interp_gs_linear(grid0, sta).iloc[:, -1]  # 站点与对应网格偏差
        # 偏差扩散至周围网格
        data_name = meb.get_stadata_names(sta)
        index0 = sta.index[0]
        xyz_sta = meb.tool.math_tools.lon_lat_to_cartesian(sta['lon'].values,
                                                           sta['lat'].values,
                                                           R=meb.basicdata.const.ER)  # 站点
        lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
        lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
        grid_lon, grid_lat = np.meshgrid(lon, lat)
        xyz_grid = meb.tool.math_tools.lon_lat_to_cartesian(grid_lon.flatten(),
                                                            grid_lat.flatten(),
                                                            R=meb.basicdata.const.ER)  # 网格点
        tree = cKDTree(xyz_sta)  # 站点索引树，找离站点最近的格点
        # d,inds 分别是站点到格点的距离和id
        if self.nearNum > len(sta.index):
            self.nearNum = len(sta.index)
        d, inds = tree.query(xyz_grid, k=self.nearNum)  # 返回每个格点最近的nearNum个站点
        if self.nearNum > 1:
            d += 1e-6
            w1 = 1.0 / d ** self.decrease
            w2 = np.exp(-(d / self.effectR)**2)
            input_dat = sta.values[:, -1]
            dat = np.sum(w1 * w2 * input_dat[inds], axis=1) / np.sum(w1, axis=1)
        else:
            input_dat = sta.iloc[:, -1].values
            w2 = np.exp(-(d / self.effectR)**2)
            dat = w2 * input_dat[inds]
            dat[d > self.effectR] = 0
        dat = dat.astype(np.float32)
        grd_delta = meb.basicdata.grid_data(grid2, dat)  # 网格偏差
        grd_final = grid0.copy()
        grd_final.values = grd_final.values + grd_delta.values
        grd_final.name = "data0"
        return grd_final
