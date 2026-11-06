# -*- coding: utf-8 -*-
"""把已在内存中的小时预报插值到更细的分钟或小时间隔。

可沿预报时效 ``dtime`` 或起报时间 ``time`` 插值。空间网格保持不变。
``dtime`` 路径会在最前面补一个时效为 0 的场。
"""

from utils.base_plugin import PostProcessingPlugin
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import xarray as xr
import meteva_base as meb


class Timesplit_hourtomin(PostProcessingPlugin):
    """小时时效到分钟时效的线性时间降尺度。

    默认间隔 10 分钟，插值方法 ``slinear``。``interp_method`` 会原样传给
    ``DataArray.interp``，因此也可以换成该接口支持的其他方法。
    """

    def __init__(self,
                 model_id_attr: Optional[str] = None,
                 ntime: Optional[int] = 10,
                 is_Min: Optional[bool] = True,
                 index: Optional[str] = 'dtime',
                 interp_method: Optional[str] = 'slinear'):
        """保存插值间隔、时间单位、插值轴和插值方法。

        Args:
            model_id_attr: 来源模式标识，本算法不使用。
            ntime: 插值后的时间间隔。``is_Min`` 为真时单位是分钟，否则是小时。
            is_Min: 为真时输出时间单位为分钟，为假时保持小时。
            index: 插值轴，``dtime`` 为预报时效，``time`` 为起报时间。
            interp_method: 传给 ``DataArray.interp`` 的方法名，默认 ``slinear``。
        """
        self.model_id_attr = model_id_attr
        self.ntime = ntime
        self.is_Min = is_Min
        self.index = index
        self.interp_method = interp_method

    def process(self,fcst, fcst0=None):
        """把小时场插值到更细的时间轴。

        Args:
            fcst: 已读入内存的格点场。``index="dtime"`` 时其 ``dtime`` 单位为小时。
            fcst0: 时效为 0 的场。为空时按第一帧形状造全 0 场。
                只在 ``index="dtime"`` 时使用，并要求与第一帧形状一致。

        Returns:
            插值后的 ``DataArray``。``index`` 不是 ``dtime`` 或 ``time`` 时返回 ``None``。
            零场与第一帧形状不一致时也返回 ``None``。
        """

        if self.index == "dtime":
            data1 = fcst
            dtime = data1.dtime
            # 时效插值从 0 开始。没有零场时，用第一帧的形状造一个全 0 场。
            if fcst0 is None:
                data0 = np.zeros(data1.sel(dtime=slice(dtime[0], dtime[0])).shape)
            else:
                data0 = fcst0

            if np.array_equal(data0.shape, data1.sel(dtime=slice(dtime[0], dtime[0])).shape):
                # 零场复用原场的经纬度、起报时间和层次，时效固定为 0。
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

                # 零场在前、原场在后，沿 dtime 拼成一条从 0 开始的时效序列。
                data_all = []
                data_all.append(data0)
                data_all.append(data1)
                data_all0 = [i.astype(np.float32) for i in data_all]
                data_all = meb.concat(data_all0)
                data_all_new = xr.DataArray(data_all)

                dtimelist = data_all_new.dtime.values
                # 用首尾和项数检查是否为等差数列。不是等差数列时只警告，仍继续插值。
                nndtime = 2 * np.sum(dtimelist) / [(dtimelist[-1] + dtimelist[0]) * len(dtimelist)]
                if (dtimelist[1] - dtimelist[0]) != nndtime:
                    print("Warning: The dtime of input data is not an arithmetic sequence")

                # 分钟输出时，先把小时坐标乘 60，再按 ntime 分钟生成目标轴。
                if self.is_Min:
                    data_all_new = data_all_new.assign_coords(
                        dtime=np.asarray(dtimelist, dtype=float) * 60
                    )
                    dtimelist_new = np.arange(0, dtimelist[-1] * 60 + 1, self.ntime)
                else:
                    # 小时输出保持原单位，目标轴从 0 覆盖到最后一帧。
                    dtimelist_new = np.arange(0, dtimelist[-1] + 0.01, self.ntime)
                data_all_inter = data_all_new.interp(dtime=dtimelist_new, method=self.interp_method)
                return data_all_inter
            else:
                print("WRONG: Input data has different shapes")

        elif self.index == "time":
            # 起报时间轴不补零场，直接在首尾时间之间生成细时间序列。
            if not isinstance(fcst, xr.DataArray):
                data_all_new = xr.DataArray(fcst)
            else:
                data_all_new = fcst
            time = data_all_new.time.values
            stime = time[0]
            etime = time[-1]
            if self.is_Min:
                timelist_new = pd.date_range(stime, etime, freq=str(self.ntime) + "min")
            else:
                timelist_new = pd.date_range(stime, etime, freq=str(self.ntime) + "h")

            data_all_inter = data_all_new.interp(time=timelist_new, method=self.interp_method)
            return data_all_inter
        else:
            print("index must be dtime or time")
