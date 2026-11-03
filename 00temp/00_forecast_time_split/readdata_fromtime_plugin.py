# -*- coding: utf-8 -*-
"""
Created on Mon Apr 15 15:54:20 2024

@author: cheny
"""

from nimm import PostProcessingPlugin
from typing import Optional, Tuple
import meteva_base as meb
import numpy as np
import xarray as xr
import sys



class Readdata_fromtime(PostProcessingPlugin):
    def __init__(self, model_id_attr: Optional[str] = None):
        """
        Initialise the class

        Args:
            model_id_attr:
                Name of the attribute used to identify the source model for
                blending.
        """
        self.model_id_attr = model_id_attr
        
    def process(file_path, file_time, glon, glat):
        """
        对file_path路径下的数据在时间维度上进行拼接
        file_path:读取数据的路径
        file_time:读取数据的时间[list]
        输出 member,time,dtime,level,lat,lon的六维数据
        """
        dylonlat_data = {"begin_lon": glon[0],
                         "end_lon": glon[1],
                         "begin_lat": glat[0],
                         "end_lat": glat[1],
                         "lon_res": glon[2],
                         "lat_res": glat[2]}
        # dylon,dylat = _dlonlat_info(dylonlat_data,1)
        dylon, dylat = dlonlat_info(dylonlat_data, 1)
        file_test = meb.get_path(file_path, file_time[0])
        data_test = meb.read_griddata_from_nc(file_test).sel(lat=slice(glat[0], glat[1]), lon=slice(glon[0], glon[1]))
        member = data_test.member.values
        dtime = data_test.dtime.values
        level = data_test.level.values
        data_all = np.empty((1, len(file_time), len(dtime), len(level), len(dylat), len(dylon)))
        for i, itime in enumerate(file_time):
            file = meb.get_path(file_path, itime)
            data = meb.read_griddata_from_nc(file).sel(lat=slice(glat[0], glat[1]), lon=slice(glon[0], glon[1]))
            data_all[:, i, :, :, :, :] = data.values
        data_list = xr.DataArray(data_all, dims=["member", "time", "dtime", "level", "lat", "lon"],
                                 coords=[member, file_time, dtime, level, dylat, dylon])
        return data_list