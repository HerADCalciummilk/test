# -*- coding: utf-8 -*-
"""粗时效预报场沿预报时效做时间降尺度。

读取同一起报时间下的多个时效文件，沿 ``dtime`` 插值到更密的时效。
可选先把 U、V 合成风速，或在插值后沿时效做差分。空间网格保持不变。
"""

import numpy as np
import os
from utils.base_plugin import PostProcessingPlugin
from typing import Optional
import meteva_base as meb
import meteva_base.fun.statisticing as _meb_stat

# read_multi_griddata 会调用 os.path.exists，但其模块没有导入 os。
if not hasattr(_meb_stat, "os"):
    _meb_stat.os = os

class TimeSplit(PostProcessingPlugin):
    """把粗时效格点插值成细时效格点。

    输入、输出时效都用 ``[起点, 终点, 步长]`` 表示，终点包含在结果中。
    例如 ``[0, 9, 3]`` 得到时效 ``0, 3, 6, 9``。
    """

    def __init__(self,
                 model_id_attr: Optional[str] = None,
                 input_fh_list: list = None,
                 output_fh_list: list = None,
                 interp_method: Optional[str] = 'slinear',
                 output_fmt: Optional[str] = None,
                 uv_fmt: Optional[str] = None,
                 delta_hour: Optional[str] = None,
                 is_fill0: Optional[bool] = False,
                 io_method = None,
                 ):
        """保存时效列表和可选的风速、差分、输出设置。

        Args:
            model_id_attr: 来源模式标识，本算法不使用。
            input_fh_list: 输入时效 ``[起点, 终点, 步长]``，终点包含在结果中。
            output_fh_list: 输出时效 ``[起点, 终点, 步长]``，终点包含在结果中。
            interp_method: 传给 ``DataArray.interp`` 的插值方法，默认 ``slinear``。
            output_fmt: 输出路径模板。为空时不写文件。
            uv_fmt: V 分量路径模板。为空时不做风速合成，``input_fmt`` 按原要素插值。
            delta_hour: 沿时效做差的间隔。为空时不做差分。
            is_fill0: 为真时，时效 0 不读文件，改用全 0 场。
            io_method: 读网格的函数。为空时使用 ``meteva_base.read_griddata_from_nc``。
        """
        self.model_id_attr = model_id_attr
        # 右边界加 1，使终点进入时效序列，且不会多走出一个步长。
        self.input_fh_list = np.arange(input_fh_list[0],input_fh_list[1]+1,input_fh_list[2])
        self.output_fh_list = np.arange(output_fh_list[0],output_fh_list[1]+1,output_fh_list[2])
        self.interp_method = interp_method
        self.output_fmt = output_fmt
        self.uv_fmt = uv_fmt
        self.delta_hour = delta_hour
        self.is_fill0 = is_fill0
        self.io_method = io_method

    def process(self,input_fmt, time):
        """读取粗时效，插值到输出时效，并按需要合成风速、做差分和写文件。

        Args:
            input_fmt: 输入路径模板，可含 ``YYYY``、``MM``、``DD``、``HH``、``TTT``。
                给出 ``uv_fmt`` 时，这个路径上的场作为 U 分量。
            time: 起报时间，用于解析路径模板，需要具备 ``strftime``。

        Returns:
            ``(细时效场, 插值前的粗时效场)``。读数或插值失败时返回 ``(None, None)``。
            细时效场仍包含全部输出时效；给出输出模板时，每个时效再另存一个 nc。
        """
        fh03_list = self.input_fh_list
        fh01_list = self.output_fh_list
        try:
            # 按时效列表读文件，并沿 dtime 拼成一块。只有一个起报时间时，
            # meteva 的拼接会再补一个 12 小时后的起报时间，其值为缺测 999999。
            grd_all = meb.read_multi_griddata(input_fmt, time, fh03_list, io_method=self.io_method, is_fill0=self.is_fill0)#DataArray
            print(grd_all)
            # 主场为 U，uv_fmt 为 V。只保留风速，风向不参与后续插值。
            if self.uv_fmt is not None:
                grd_0 = meb.read_multi_griddata(self.uv_fmt, time, fh03_list, io_method=self.io_method, is_fill0=self.is_fill0)#读取v分量
                print(grd_0)
                grd_all, _ = meb.u_v_to_speed_angle(grd_all, grd_0)#计算风速
            # 在输出时效上插值。目标时效超出已有范围时按外推填充。
            grd_all_01h = grd_all.interp(dtime=fh01_list, method=self.interp_method, kwargs={"fill_value": "extrapolate"})
            # 用后一时效减去 delta_hour 之前的时效。无法配到起点的时效会被去掉。
            if self.delta_hour is not None:
                grd_all_01h = meb.change(grd_all_01h, delta=self.delta_hour, used_coords="dtime")
        except Exception as err:
            print(err)
            return None,None
        # 每个输出时效单独写一个 nc。文件已存在时跳过。
        if self.output_fmt is not None:#输出拆分结果nc
            for fh01 in fh01_list:
                out_file = meb.get_path(self.output_fmt, time=time, dt=fh01)
                if not os.path.exists(out_file):
                    try:
                        grd_01h = grd_all_01h.sel(dtime=[fh01]).astype(np.float32)
                        # grd_01h = grd_01h.astype(np.float32)
                        grd_01h.values[grd_01h.values<0] = 0#最小为0
                        meb.write_griddata_to_nc(grd_01h, out_file, effectiveNum=2, creat_dir=True)
                        print(out_file)
                    except Exception as err:
                        print(err, time, fh01)
                        continue
        return(grd_all_01h, grd_all)
