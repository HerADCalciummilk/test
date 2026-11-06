# -*- coding: utf-8 -*-
"""按时间列表读取多个格点文件，并沿起报时间拼接。

每个文件使用同一路径模板。读入后按给定经纬度范围裁剪，再堆成
``member, time, dtime, level, lat, lon``。这里只拼接，不做时间插值。
"""

from utils.base_plugin import PostProcessingPlugin
from typing import Optional, Tuple
import meteva_base as meb
import numpy as np
import xarray as xr
import sys



class Readdata_fromtime(PostProcessingPlugin):
    """把同一路径模板下的多个时次拼成一块六维格点。"""

    def __init__(self, model_id_attr: Optional[str] = None):
        """保存来源模式标识。

        Args:
            model_id_attr: 来源模式标识，本算法不使用。
        """
        self.model_id_attr = model_id_attr

    def process(file_path, file_time, glon, glat):
        """读取多个时次并沿时间维拼接。

        当前定义没有 ``self``，因此应按函数方式调用，不能作为实例方法调用。

        Args:
            file_path: 路径模板，由 ``meteva_base.get_path`` 按时间展开。
            file_time: 需要读取的时间列表。元素需能被 ``get_path`` 解析。
            glon: 经度范围 ``[起点, 终点, 分辨率]``。
            glat: 纬度范围 ``[起点, 终点, 分辨率]``。

        Returns:
            六维 ``DataArray``，维度顺序为
            ``member, time, dtime, level, lat, lon``。
            ``time`` 使用 ``file_time``，其余坐标来自第一个文件和经纬度范围。
        """
        # 裁剪范围同时提供给外部经纬度展开函数和 xarray 的 sel。
        dylonlat_data = {"begin_lon": glon[0],
                         "end_lon": glon[1],
                         "begin_lat": glat[0],
                         "end_lat": glat[1],
                         "lon_res": glon[2],
                         "lat_res": glat[2]}
        # dylon,dylat = _dlonlat_info(dylonlat_data,1)
        dylon, dylat = dlonlat_info(dylonlat_data, 1)
        # 用第一个时次确定成员、时效和层次，后续文件按这个形状填入。
        file_test = meb.get_path(file_path, file_time[0])
        data_test = meb.read_griddata_from_nc(file_test).sel(lat=slice(glat[0], glat[1]), lon=slice(glon[0], glon[1]))
        member = data_test.member.values
        dtime = data_test.dtime.values
        level = data_test.level.values
        # 时间维长度等于时次个数，空间维使用裁剪后的经纬度。
        data_all = np.empty((1, len(file_time), len(dtime), len(level), len(dylat), len(dylon)))
        for i, itime in enumerate(file_time):
            file = meb.get_path(file_path, itime)
            data = meb.read_griddata_from_nc(file).sel(lat=slice(glat[0], glat[1]), lon=slice(glon[0], glon[1]))
            data_all[:, i, :, :, :, :] = data.values
        data_list = xr.DataArray(data_all, dims=["member", "time", "dtime", "level", "lat", "lon"],
                                 coords=[member, file_time, dtime, level, dylat, dylon])
        return data_list
