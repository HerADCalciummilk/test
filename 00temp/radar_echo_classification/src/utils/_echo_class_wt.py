#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""
雷达数据中的降水回波分类。

创建时间：Thu Oct 12 23:12:19 2017
作者：Bhupendra Raut
修改时间：11/19/2023
参考文献：10.1109/TGRS.2020.2965649

.. autosummary::
    wavelet_reclass
    label_classes
    calc_scale_break
    atwt2d
"""

import numpy as np


def wavelet_reclass(
    dbz_data,
    zr_a,
    zr_b,
    core_wt_threshold,
    conv_wt_threshold,
    scale_break,
    min_reflectivity,
    conv_min_refl,
    conv_core_threshold,
):
    """
    计算 Raut et al. (2008) 描述的 ATWT，
    并按 Raut et al. (2020) 方案进行回波分类。
    首先将 dBZ 按 Z-R 关系转换为雨强，用于把近似正态分布的 dBZ
    转为更接近 gamma 分布的量，从而增强场结构特征。

    Parameters
    ----------
    dbz_data : ndarray
        雷达数据二维数组，最后一维应为高度层。
    res_km : float
        雷达数据分辨率（km）。
    scale_break : int
        对流与层状尺度的分界（像素，二进尺度）。

    Returns
    -------
    wt_class : ndarray
        降水类型分类：
        0. 无效 / 未分类
        1. 层状 / 非对流
        2. 对流核心
        3. 中等或过渡（混合）对流区域
    """

    # 提取网格数据并保留原始掩膜。
    # 统一转为 masked array，确保缺测值掩码在全流程保持一致。
    dbz_data = np.ma.masked_invalid(np.asanyarray(dbz_data))

    # 保存原始缺测掩膜。
    radar_mask = np.ma.getmask(dbz_data)

    wt_sum = conv_wavelet_sum(dbz_data, zr_a, zr_b, scale_break)

    wt_class = label_classes(
        wt_sum,
        dbz_data,
        core_wt_threshold,
        conv_wt_threshold,
        min_reflectivity,
        conv_min_refl,
        conv_core_threshold,
    )

    wt_class_ma = np.ma.masked_where(radar_mask, wt_class)  # 恢复原始掩膜
    wt_class_ma = wt_class_ma.squeeze()

    return wt_class_ma


def conv_wavelet_sum(dbz_data, zr_a, zr_b, scale_break):
    """
    基于 dBZ 数据计算对流尺度小波分量之和。

    Parameters
    ------------
    dbz_data : ndarray
        雷达 dBZ 二维数组。
    zr_a, zr_b : float
        Z-R 关系系数。
    res_km : float
        雷达分辨率（km）。
    scale_break : int
        对流与层状尺度分界（像素）。

    Returns
    ---------
    wt_sum : ndarray
        对流尺度小波分量累加结果。
    """
    try:
        dbz_data = dbz_data.filled(0)
    except Exception:
        pass

    dbz_data[np.isnan(dbz_data)] = 0
    rr_data = ((10.0 ** (dbz_data / 10.0)) / zr_a) ** (1.0 / zr_b)

    wt, _ = atwt2d(rr_data, max_scale=scale_break)
    wt_sum = np.sum(wt, axis=(0))

    return wt_sum


def label_classes(
    wt_sum,
    dbz_data,
    core_wt_threshold,
    conv_wt_threshold,
    min_reflectivity,
    conv_min_refl,
    conv_core_threshold,
):
    """
    按阈值规则标注回波类别：
        - 0：无降水或未分类
        - 1：层状 / 非对流区域
        - 2：过渡与混合对流区域
        - 3：对流核心

    下列默认阈值基于 Raut et al. (2020) 在 C 波段数据上的
    优化与验证（Darwin, Australia 2.5 km；Solapur, India 1 km）。
    core_wt_threshold = 5  # WT value more than this is strong convection
    conv_wt_threshold = 2  # WT value for moderate convection
    min_reflectivity = 10  # pixels below this value are not classified.
     conv_min_refl = 30  # 低于该阈值的像素不判为对流，通常适用于多数场景。

    Parameters
    -----------
    wt_sum : ndarray
        小波积分结果。
    vol_data : ndarray
        数据数组。

    Returns
    ---------
    wt_class : ndarray
        降水类型分类结果。
    """

    # 先用负号编码分类，再整体乘 -1 转为正号编号。
    wt_class = np.where(
        (wt_sum >= conv_wt_threshold) & (dbz_data >= conv_core_threshold), -3, 0
    )
    wt_class = np.where(
        (wt_sum >= core_wt_threshold) & (dbz_data >= conv_min_refl), -3, 0
    )
    wt_class = np.where(
        (wt_sum < core_wt_threshold)
        & (wt_sum >= conv_wt_threshold)
        & (dbz_data >= conv_min_refl),
        -2,
        wt_class,
    )
    wt_class = np.where((wt_class == 0) & (dbz_data >= min_reflectivity), -1, wt_class)

    wt_class = -1 * wt_class
    wt_class = np.ma.masked_where(wt_class == 0, wt_class)

    return wt_class.astype(np.int32)


def calc_scale_break(res_meters, conv_scale_km):
    """
    计算对流与层状尺度的分界。
    小波分解计算到该尺度时，特征会被归为对流。

    Parameters
    -----------
    res_meters : float
        图像分辨率（m）。
    conv_scale_km : float
        预期对流空间变化尺度（km）。

    Returns
    --------
    dyadic scale break : int
        二进尺度下的整数分界。
    """
    res_km = res_meters / 1000
    scale_break = np.log(conv_scale_km / res_km) / np.log(2) + 1

    return int(round(scale_break))


def atwt2d(data2d, max_scale=-1):
    """
    计算二维 a trous 小波变换（ATWT）。
    对输入二维数组分解到 max_scale；若 max_scale 超出可用范围，
    会自动缩减到可计算尺度。

    边界采用镜像处理；未针对非方形数据做完整验证。

    作者：Bhupendra A. Raut、Dileep M. Puranik
    参考：Press et al. (1992) Numerical Recipes in C.

    Parameters
    -----------
    data2d : ndarray
        二维图像数组。
    max_scale :
        小波分解最大尺度。缺省时使用可计算的最大尺度。

    Returns
    ---------
    tuple of ndarray
        输入图像的 ATWT 分量与最终平滑（背景）图像。
    """

    if not isinstance(data2d, np.ndarray):
        raise TypeError("The input data2d must be a numpy array.")

    data2d = data2d.squeeze()

    dims = data2d.shape
    min_dims = np.min(dims)
    max_possible_scales = int(np.floor(np.log(min_dims) / np.log(2)))

    if max_scale < 0 or max_possible_scales <= max_scale:
        max_scale = max_possible_scales - 1

    ny = dims[0]
    nx = dims[1]

    # 用于存储各尺度小波分量。
    wt = np.zeros((max_scale, ny, nx))

    temp1 = np.zeros(dims)
    temp2 = np.zeros(dims)

    sf = (0.0625, 0.25, 0.375)  # scaling function

    # 小波分解主循环。
    for scale in range(1, max_scale + 1):
        x1 = 2 ** (scale - 1)
        x2 = 2 * x1

        # 行方向平滑。
        for i in range(0, nx):
            # 计算当前列对应的前后采样索引。
            prev2 = abs(i - x2)
            prev1 = abs(i - x1)
            next1 = i + x1
            next2 = i + x2

            # 若索引越界则做镜像映射。
            # 在高尺度下该处理有时会引入边界误差。
            if next1 > nx - 1:
                next1 = 2 * (nx - 1) - next1

            if next2 > nx - 1:
                next2 = 2 * (nx - 1) - next2

            if prev1 < 0 or prev2 < 0:
                prev1 = next1
                prev2 = next2

            for j in range(0, ny):
                left2 = data2d[j, prev2]
                left1 = data2d[j, prev1]
                right1 = data2d[j, next1]
                right2 = data2d[j, next2]
                temp1[j, i] = (
                    sf[0] * (left2 + right2)
                    + sf[1] * (left1 + right1)
                    + sf[2] * data2d[j, i]
                )

        # 列方向平滑。
        for i in range(0, ny):
            prev2 = abs(i - x2)
            prev1 = abs(i - x1)
            next1 = i + x1
            next2 = i + x2

            # 若索引越界则做镜像映射。
            if next1 > ny - 1:
                next1 = 2 * (ny - 1) - next1
            if next2 > ny - 1:
                next2 = 2 * (ny - 1) - next2
            if prev1 < 0 or prev2 < 0:
                prev1 = next1
                prev2 = next2

            for j in range(0, nx):
                top2 = temp1[prev2, j]
                top1 = temp1[prev1, j]
                bottom1 = temp1[next1, j]
                bottom2 = temp1[next2, j]
                temp2[i, j] = (
                    sf[0] * (top2 + bottom2)
                    + sf[1] * (top1 + bottom1)
                    + sf[2] * temp1[i, j]
                )

        wt[scale - 1, :, :] = data2d - temp2
        data2d[:] = temp2

    return wt, data2d
