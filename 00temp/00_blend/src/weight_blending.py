#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''
@FILE      : weight_blending.py
@TIME      : 2023/07/17 16:18:09
@AUTHOR    : wangyu / NMC
@VERSION   : 1.0
@DESC      : 本程序实现基于权重的多预报融合
'''

from iris.cube import Cube
from types import FunctionType as function
from typing import Tuple, Optional

import cv2
import numpy as np

from nimm import PostProcessingPlugin

from utils.cube_checker import (
    check_for_x_and_y_axes, 
    spatial_coords_match
)

from nimm.utils.set_up_cubes import construct_scalar_frt_coords
from nimm.metadata.utils import (
    create_new_diagnostic_cube,
    generate_mandatory_attributes,
)

class WeightBlending(PostProcessingPlugin): 
    """
    实现网格加权融合的类
    当出现数据缺测或评分缺测时，可以在对应位置填充None，这样缺测的数据不会参与融合
    """

    def __init__(self, 
                 wfunc: function=lambda x: np.power(x, -2), 
                 tolerate_period_mismatch: Optional[bool]=False,
                 ) -> None: 
        """
        实现网格加权融合的类
        
        data_list 的长度，必须与 factor_list 的长度一致
        当出现数据缺测或评分缺测时, 可以在对应位置填充None, 这样缺测的数据不会参与融合

        Args: 
        wfunc:  
                函数指针，负责将 factor_list 中的 评分矩阵，转换为 融合权重矩阵
                如果使用默认值None, 则实际会使用 w = np.power(score, -2)
        tolerate_period_mismatch (Optional[bool], optional): 
                If True, tolerate a mismatch in forecast period.
                Use with caution!. Defaults to False.

        --------------------------
        Returns:        
        --------------------------
        None
        """
        if wfunc is None: 
            self.wfunc = lambda x: np.power(x, -2)
        else: 
            self.wfunc = wfunc 
        self.tolerate_period_mismatch=tolerate_period_mismatch

    def process(self,                  
                fcst_cubes : list[Cube], 
                factor_cubes:   list[Cube], 
        )-> Cube:
        """
        融合多个预报，并生成融合预报
        
        Args:
            fcst_cubes:     由 cube 组成的list, 里面存放的是待融合的矩阵  
                            = [data1, data2, ..., datan]
                            如果缺测, 设置为 None

                                 
            factor_cubes:   由 cube 组成的list, 里面存放的是 MAE、RMSE 等决定融合权重的 factor matrix
                            = [factor1, factor2, ..., factorn]
                            如果缺测, 设置为 None

        Returns:        
            融合预报场        cube
                            如果没有可以融合的预报场，则返回 None
        """
        if len(fcst_cubes) != len(factor_cubes): 
            raise ValueError("len of fcst_cubes and factor_cubes should be the same!")
        
        # ws: the weights cube list
        ws = self._calculate_weights(factor_cubes, self.wfunc)

        return self._blending(fcst_cubes, ws)
    
    def _calculate_weights(
            self, factors: list[Cube], 
            wfunc=lambda x: np.power(x, -2)
        ) -> list[Cube]:
        """
        根据输入的 factors, 计算权重
        权重的计算公式，由 lambda_func 提供

        Args:
            factors:        需要基于该要素计算融合权重, list
                            like: [f1, f2, ..., fn]
                            fi = Cube

            wfunc:          计算权重的函数指针
                            默认为lambda函数，factors^-2 

        Returns
            ws:             经由 factors 计算获得的权重矩阵

        """
        ws = []
        for ifactor in factors:
            if ifactor is None:  
                continue 
            
            if type(ifactor) is not Cube: 
                raise ValueError("the data type of ifactor should be Cube, please check the data")
            
            # 考虑到有些区域模式只在某部分区域有预报
            # 需要对融合权重进行额外的平滑
            raw_shape = ifactor.data.shape 
            if len(raw_shape) == 1:
                # 更大的可能是站点数据，此时无需平滑 
                iw = wfunc(ifactor)
            elif len(raw_shape) == 2:
                iw = cv2.blur(wfunc(ifactor.data), (51, 51), cv2.BORDER_REPLICATE)
            else:
                # len(raw_shape) > 2: 
                nrows, ncols = raw_shape[-2], raw_shape[-1]
                tmp_factor = ifactor.data.reshape(-1, nrows, ncols)
                iw = np.zeros(tmp_factor.shape)
                for i in range(tmp_factor.shape[0]): 
                    iw[i, :, :] = cv2.blur(wfunc(tmp_factor[i, :, :]), (51, 51), cv2.BORDER_REPLICATE)
                iw = iw.reshape(raw_shape) 

                # create iw cube
                MAE_cube = create_new_diagnostic_cube(
                    ifactor.name(),
                    'w',
                    template_cube=ifactor,
                    mandatory_attributes=generate_mandatory_attributes([ifactor]),
                    optional_attributes=ifactor.attributes,
                    data=iw,
                )
            ws.append(iw)

        return ws 
    
    def _blending(self, 
                  fcsts: list[Cube], 
                  weights: list[Cube]
        ) -> Cube: 
        """
        给出预报场(fcsts)和相应预报场的权重(同样为网格场), 进行预报的融合

        Args:
            fcsts:      list 格式的多个预报场, like [fcst1, fcst2, ..., fcstn]
                        fcsti = Cube
                        如果某个预报缺失，则设置为 None

            weights:    list 格式的融合权重, like [w1, w2, ..., wn]
                        wi = Cube
                        如果某个预报的权重缺失，则设置为 None
        
        Return:
            dmat:       融合后预报场, = Cube
                        如果没有任何能够融合的矩阵，则返回 None
        """
        dmat, wmat, total_vld = None, None, None 
        fcst_unit = None 
        blend_infor = ''

        for ifcst, iw in zip(fcsts, weights): 
            if (ifcst is None) or (iw is None): 
                continue
            
            # 为了保险，检测一下 ifcst 和 iw 的数据类型
            if type(ifcst) is not Cube:
                raise ValueError('the data type of fcst should be Cube, please check the forecast data type')

            if type(iw) is not Cube:
                raise ValueError('the data type of weight should be Cube, please check the forecast data type')
            
            check_for_x_and_y_axes(ifcst)
            check_for_x_and_y_axes(iw)

            if not spatial_coords_match([ifcst, iw]): 
                msg = "The x/y coordinate of Fcst and Weight cube do not match."
                raise ValueError(msg)
            
            # 确保所有参与融合的预报场，使用同一个 单位
            if fcst_unit is None: 
                fcst_unit = ifcst.units
            else: 
                # check 不同融合场的 unit 是否一致
                if not ifcst.units == fcst_unit: 
                    ifcst.convert_units(fcst_unit)

            # 初始化融合矩阵和权重矩阵
            if (dmat is None) and (ifcst.data is not None) and (iw.data is not None): 
                dmat = np.zeros(ifcst.data.shape)
                wmat = np.zeros(ifcst.data.shape)
                total_vld = np.zeros(ifcst.data.shape, dtype=bool)

            # ifcst 预报提供的 有效网格点
            vld_idx = ((~np.isnan(ifcst.data)) & (~np.isnan(iw.data)))
            # 融合预报总的有效网格点
            total_vld |= vld_idx

            dmat[vld_idx] += ifcst.data[vld_idx] * iw.data[vld_idx]
            wmat[vld_idx] += iw.data[vld_idx]
            blend_infor += ifcst.name()+","

        # float 无法直接使用 == 0.0比较
        wmat[np.abs(wmat) < 1e-8] = 1.0
        dmat /= wmat 
        dmat[~total_vld] = np.nan

        # creat a new cube 
        blend_cube = create_new_diagnostic_cube(
            blend_infor+" Blending",
            fcst_unit,
            template_cube=ifcst,
            mandatory_attributes=generate_mandatory_attributes([ifcst]),
            optional_attributes=ifcst.attributes,
            data=dmat,
        )
        return dmat