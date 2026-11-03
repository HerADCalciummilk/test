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
from meteva_base.basicdata.grid import grid


class InterpSgIdw(PostProcessingPlugin):
    def __init__(self, 
                 model_id_attr: Optional[str] = None,
                 effectR : Optional[int] = 1000,
                 nearNum : Optional[int] = 8,
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
        
    def process(self,sta0, grid):
        ## sta0:  站点数据
        ## grid:  格点信息类，无背景场
        ## effectR: 反距离权重最大距离范围

        sta1 = meb.sele_by_para(sta0,drop_IV=True)
        sta_list = meb.split(sta1,["member","level","time","dtime"])
        grd_list = []
        for sta in sta_list:
            data_name = meb.get_stadata_names(sta)
            index0 = sta.index[0]
            dtime = sta.loc[index0, 'dtime'].astype(int)
            level = sta.loc[index0, 'level'].astype(int)
            grid2 = meb.basicdata.grid(grid.glon, grid.glat, [sta.loc[index0, 'time']],
                                                               [dtime],
                                                               [level], data_name)
            xyz_sta = meb.tool.math_tools.lon_lat_to_cartesian(sta['lon'].values,
                                                                                        sta['lat'].values,
                                                                                        R=meb.basicdata.const.ER)
            lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
            lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
            grid_lon, grid_lat = np.meshgrid(lon, lat)
            xyz_grid = meb.tool.math_tools.lon_lat_to_cartesian(grid_lon.flatten(),
                                                                                         grid_lat.flatten(),
                                                                                         R=meb.basicdata.const.ER)
            tree = cKDTree(xyz_sta)
            # d,inds 分别是站点到格点的距离和id
            if self.nearNum > len(sta.index):
                nearNum = len(sta.index)
            d, inds = tree.query(xyz_grid, k=self.nearNum)
            if self.nearNum >1:
                d += 1e-6
                w = 1.0 / d ** self.decrease
                input_dat = sta.values[:,-1]
                dat = np.sum(w * input_dat[inds], axis=1) / np.sum(w, axis=1)
                bg = meb.basicdata.grid_data(grid2)
                bg_dat = bg.values.flatten()
                dat = np.where(d[:, 0] > self.effectR, bg_dat, dat)
            else:
                input_dat = sta.iloc[:,-1].values
                dat = input_dat[inds]
                bg = meb.basicdata.grid_data(grid2)
                bg_dat = bg.values.flatten()
                dat = np.where(d[:] > self.effectR, bg_dat, dat)
            dat = dat.astype(np.float32)
            grd = meb.basicdata.grid_data(grid2, dat)
            grd.name = data_name[0]
            grd_list.append(grd)

        grd_all = meb.concat(grd_list)
        return grd_all
    
if __name__ == "__main__":
    
    sta=meb.read_stadata_from_csv(r'D:\Desktop\Meteva_base\f.csv')
    grid=meb.read_griddata_from_nc(r'D:\Desktop\input_demo.nc')
    print(grid)
    grid_info=meb.get_grid_of_data(grid)
    result=InterpSgIdw().process(sta,grid_info)