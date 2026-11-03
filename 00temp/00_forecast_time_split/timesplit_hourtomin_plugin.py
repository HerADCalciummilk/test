# -*- coding: utf-8 -*-
"""
Created on Mon Apr 15 15:54:20 2024

@author: cheny
"""

from nimm import PostProcessingPlugin
from typing import Optional, Tuple
import numpy as np
import meteva_base as meb


class Timesplit_hourtomin(PostProcessingPlugin):
    def __init__(self, 
                 model_id_attr: Optional[str] = None,
                 ntime: Optional[int] = 10,
                 is_Min: Optional[bool] = True,
                 index: Optional[str] = 'dtime'):
        """
        Initialise the class

        Args:
            model_id_attr:
                Name of the attribute used to identify the source model for
                blending.
        """
        self.model_id_attr = model_id_attr
        self.ntime = ntime
        self.is_Min = is_Min
        self.index = index
        
    def process(self,fcst, fcst0=None):
        """
        将时报时效或预报时间单位为小时的数据fcst进行时间插值
        fcst0 为预报零场,若为None则默认为零。若存在预报零场，则fcst0需要与fcst分辨率一致
        ntime 为插值后的时间间隔,默认为10分钟
        is_Min True则插值后单位为分钟 若is_Min=True则插值后单位为分钟
        index 为需要插值的索引名称，可选择dtime（预报时效）、time（时间）
        """

        if self.index == "dtime":
            data1 = fcst
            # 若对预报时效dtime进行插值，则需要零场
            dtime = data1.dtime
            if fcst0 is None:
                data0 = np.zeros(data1.sel(dtime=slice(dtime[0], dtime[0])).shape)
            else:
                data0 = fcst0

            if np.array_equal(data0.shape, data1.sel(dtime=slice(dtime[0], dtime[0])).shape):
                # 将预报数据data1的除了dtime之外的各维度信息赋给零场data0
                glon = [min(data1.lon.values), max(data1.lon.values),
                        round(abs(data1.lon.values[0] - data1.lon.values[1]), 2)]
                glat = [min(data1.lat.values), max(data1.lat.values),
                        round(abs(data1.lat.values[0] - data1.lat.values[1]), 2)]
                time = data1.time.values
                time_data = pd.to_datetime(time).strftime("%Y%m%d%H").values
                level = data1.level.values
                grid_info = meb.grid(glon, glat, gtime=time_data, dtime_list=[0], level_list=level)
                if fcst0 is None:
                    data0 = meb.grid_data(grid_info, data0)
                else:
                    data0 = meb.grid_data(grid_info, data0.values)

                # 用于存放零场数据data0和data1
                data_all = []
                data_all.append(data0)
                data_all.append(data1)
                # 将data_all list进行dtime维度上拼接
                data_all0 = [i.astype(np.float32) for i in data_all]
                data_all = meb.concat(data_all0)
                data_all_new = xr.DataArray(data_all)

                # 对拼接好的数据进行dtime时间插值
                dtimelist = data_all_new.dtime.values
                # 判断dtimelist是否为等差数列若不是则提醒
                nndtime = 2 * np.sum(dtimelist) / [(dtimelist[-1] + dtimelist[0]) * len(dtimelist)]
                if (dtimelist[1] - dtimelist[0]) != nndtime:
                    print("Warning: The dtime of input data is not an arithmetic sequence")

                # 对dtime进行以分钟或者小时为单位拆分
                if self.is_Min:
                    dtimelist_new = np.arange(0, dtimelist[-1] * 60 + 1, self.ntime)
                else:
                    dtimelist_new = np.arange(0, dtimelist[-1] + 0.01, self.ntime)
                data_all_inter = data_all_new.interp(dtime=dtimelist_new, method="slinear")
                return data_all_inter
            else:
                print("WRONG: Input data has different shapes")

        elif self.index == "time":
            if not isinstance(fcst, xr.DataArray):
                data_all_new = xr.DataArray(fcst)
            else:
                data_all_new = fcst
            # 对拼接好的数据进行dtime时间插值
            time = data_all_new.time.values
            stime = time[0]
            etime = time[-1]
            if self.is_Min:
                timelist_new = pd.date_range(stime, etime, freq=str(self.ntime) + "min")
            else:
                timelist_new = pd.date_range(stime, etime, freq=str(self.ntime) + "h")

            data_all_inter = data_all_new.interp(time=timelist_new, method="slinear")
            return data_all_inter
        else:
            print("index must be dtime or time")