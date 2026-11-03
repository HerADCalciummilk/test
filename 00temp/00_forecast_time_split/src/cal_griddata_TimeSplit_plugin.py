# -*- coding: utf-8 -*-
"""
Created on Mon Apr 15 15:54:20 2024

@author: cheny
"""

import numpy as np
import os
from nimm import PostProcessingPlugin
from typing import Optional, Tuple
import meteva_base as meb


class TimeSplit(PostProcessingPlugin):
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
        """
        Initialise the class

        Args:
            model_id_attr:
                Name of the attribute used to identify the source model for
                blending.
        """
        self.model_id_attr = model_id_attr
        self.input_fh_list = np.arange(input_fh_list[0],input_fh_list[1],input_fh_list[2])
        self.output_fh_list = np.arrage(output_fh_list[0],output_fh_list[1],output_fh_list[2])
        self.interp_method=interp_method
        self.io_method=io_method
        
    def process(self,input_fmt, time):
        """
        时间拆分预处理，包括uv生成风速、delta变量等
        """
        ## read data
        fh03_list = self.input_fh_list
        fh01_list = self.output_fh_list
        try:
            ## 组合数据 
            grd_all = read_multi_griddata(input_fmt, time, fh03_list, io_method=self.io_method, is_fill0=self.is_fill0)#DataArray
            print(grd_all)
            ## 预处理, UV风读取并合成风速
            if self.uv_fmt is not None:
                grd_0 = read_multi_griddata(self.uv_fmt, time, fh03_list, io_method=self.io_method, is_fill0=self.is_fill0)#读取v分量
                print(grd_0)
                grd_all, _ = cal_wswd_from_meteva_uvgrid(grd_all, grd_0)#计算风速
            ## 拆分数据
            grd_all_01h = grd_all.interp(dtime=fh01_list, method=self.interp_method, kwargs={"fill_value": "extrapolate"})    
            ## 后处理，计算时间变量(delta)
            if self.delta_hour is not None:
                grd_all_01h = meb.change(grd_all_01h, delta=self.delta_hour, used_coords="dtime")
        except Exception as err:
            print(err)
            return None,None
        # 输出
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