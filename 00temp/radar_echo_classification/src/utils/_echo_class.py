#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
import numpy as np
import scipy.ndimage


def _steiner_conv_strat(
    refl,
    x,
    y,
    dx,
    dy,
    intense=42,
    peak_relation=0,
    area_relation=1,
    bkg_rad=11000,
    use_intense=True,
):
    """
    使用 Steiner et al. (1995) 回波分类算法，仅基于反射率场，
    将每个网格点划分为对流、层状或未定义。

    分类编号如下：
    0 = 未定义
    1 = 层状
    2 = 对流
    """

    def convective_radius(ze_bkg, area_relation):
        """
        根据背景平均反射率通过分段函数确定对应的对流影响半径。

        背景反射率越高，通常表示对周边区域的对流影响越强，
        因而对应的影响半径也会更大。
        """
        if area_relation == 0:
            if ze_bkg < 30:
                conv_rad = 1000.0
            elif (ze_bkg >= 30) & (ze_bkg < 35.0):
                conv_rad = 2000.0
            elif (ze_bkg >= 35.0) & (ze_bkg < 40.0):
                conv_rad = 3000.0
            elif (ze_bkg >= 40.0) & (ze_bkg < 45.0):
                conv_rad = 4000.0
            else:
                conv_rad = 5000.0

        if area_relation == 1:
            if ze_bkg < 25:
                conv_rad = 1000.0
            elif (ze_bkg >= 25) & (ze_bkg < 30.0):
                conv_rad = 2000.0
            elif (ze_bkg >= 30.0) & (ze_bkg < 35.0):
                conv_rad = 3000.0
            elif (ze_bkg >= 35.0) & (ze_bkg < 40.0):
                conv_rad = 4000.0
            else:
                conv_rad = 5000.0

        if area_relation == 2:
            if ze_bkg < 20:
                conv_rad = 1000.0
            elif (ze_bkg >= 20) & (ze_bkg < 25.0):
                conv_rad = 2000.0
            elif (ze_bkg >= 25.0) & (ze_bkg < 30.0):
                conv_rad = 3000.0
            elif (ze_bkg >= 30.0) & (ze_bkg < 35.0):
                conv_rad = 4000.0
            else:
                conv_rad = 5000.0

        if area_relation == 3:
            if ze_bkg < 40:
                conv_rad = 0.0
            elif (ze_bkg >= 40) & (ze_bkg < 45.0):
                conv_rad = 1000.0
            elif (ze_bkg >= 45.0) & (ze_bkg < 50.0):
                conv_rad = 2000.0
            elif (ze_bkg >= 50.0) & (ze_bkg < 55.0):
                conv_rad = 6000.0
            else:
                conv_rad = 8000.0

        return conv_rad

    def peakedness(ze_bkg, peak_relation):
        """
        根据背景反射率确定“峰值判据”（差值阈值），
        即当前格点反射率相对背景反射率至少需要超过多少，
        才能被判定为对流。
        """
        if peak_relation == 0:
            if ze_bkg < 0.0:
                peak = 10.0
            elif (ze_bkg >= 0.0) and (ze_bkg < 42.43):
                peak = 10.0 - ze_bkg**2 / 180.0
            else:
                peak = 0.0

        elif peak_relation == 1:
            if ze_bkg < 0.0:
                peak = 14.0
            elif (ze_bkg >= 0.0) and (ze_bkg < 42.43):
                peak = 14.0 - ze_bkg**2 / 180.0
            else:
                peak = 4.0

        return peak

    sclass = np.zeros(refl.shape, dtype=int)
    ny, nx = refl.shape

    for i in range(0, nx):
        # 获取背景半径范围内 x 方向的格点窗口。
        imin = np.max(np.array([1, (i - bkg_rad / dx)], dtype=int))
        imax = np.min(np.array([nx, (i + bkg_rad / dx)], dtype=int))

        for j in range(0, ny):
            # 先确认当前格点尚未被分类。
            # 前序格点在扩张其对流影响半径时，可能已经覆盖到此格点。
            if ~np.isnan(refl[j, i]) & (sclass[j, i] == 0):
                # 获取背景半径范围内 y 方向的格点窗口。
                jmin = np.max(np.array([1, (j - bkg_rad / dy)], dtype=int))
                jmax = np.min(np.array([ny, (j + bkg_rad / dy)], dtype=int))

                n = 0
                sum_ze = 0

                # 计算当前格点的背景平均反射率，
                # 用于后续确定对流半径和峰值阈值。

                for r in range(imin, imax):
                    for m in range(jmin, jmax):
                        if not np.isnan(refl[m, r]):
                            rad = np.sqrt((x[r] - x[i]) ** 2 + (y[m] - y[j]) ** 2)

                            # 背景平均反射率先在线性单位（mm^6/m^3）下求均值，
                            # 再转换到 dBZ。
                            if rad <= bkg_rad:
                                n += 1
                                sum_ze += 10.0 ** (refl[m, r] / 10.0)

                if n == 0:
                    ze_bkg = np.inf
                else:
                    ze_bkg = 10.0 * np.log10(sum_ze / n)

                # 根据背景平均反射率计算对应对流影响半径。
                conv_rad = convective_radius(ze_bkg, area_relation)

                # 检查当前格点周边、位于对流半径内的格点，
                # 决定它们是否归为对流、层状或未定义。

                # 获取对流半径范围内 x/y 方向的格点窗口。
                lmin = np.max(np.array([1, int(i - conv_rad / dx)], dtype=int))
                lmax = np.min(np.array([nx, int(i + conv_rad / dx)], dtype=int))
                mmin = np.max(np.array([1, int(j - conv_rad / dy)], dtype=int))
                mmax = np.min(np.array([ny, int(j + conv_rad / dy)], dtype=int))

                if use_intense and (refl[j, i] >= intense):
                    sclass[j, i] = 2

                    for r in range(lmin, lmax):
                        for m in range(mmin, mmax):
                            if not np.isnan(refl[m, r]):
                                rad = np.sqrt((x[r] - x[i]) ** 2 + (y[m] - y[j]) ** 2)

                                if rad <= conv_rad:
                                    sclass[m, r] = 2

                else:
                    peak = peakedness(ze_bkg, peak_relation)

                    if refl[j, i] - ze_bkg >= peak:
                        sclass[j, i] = 2

                        for r in range(imin, imax):
                            for m in range(jmin, jmax):
                                if not np.isnan(refl[m, r]):
                                    rad = np.sqrt(
                                        (x[r] - x[i]) ** 2 + (y[m] - y[j]) ** 2
                                    )

                                    if rad <= conv_rad:
                                        sclass[m, r] = 2

                    else:
                        # 若既不满足强回波判据，也不满足峰值判据，
                        # 则归为层状回波。
                        sclass[j, i] = 1

    return sclass


def steiner_class_buff(
    ze,
    x,
    y,
    z,
    dx,
    dy,
    bkg_rad,
    work_level,
    intense,
    peak_relation,
    area_relation,
    use_intense,
):
    zslice = np.argmin(np.abs(z - work_level))
    refl = ze[zslice, :, :]

    area_rel = {"small": 0, "medium": 1, "large": 2, "sgp": 3}
    peak_rel = {"default": 0, "sgp": 1}

    sclass = _steiner_conv_strat(
        refl,
        x,
        y,
        dx,
        dy,
        intense=intense,
        peak_relation=peak_rel[peak_relation],
        area_relation=area_rel[area_relation],
        bkg_rad=11000,
        use_intense=True,
    )

    return sclass


def _feature_detection(
    field,
    dx,
    dy,
    always_core_thres=42,
    bkg_rad_km=11,
    use_cosine=True,
    max_diff=5,
    zero_diff_cos_val=55,
    scalar_diff=1.5,
    use_addition=True,
    calc_thres=0.75,
    weak_echo_thres=5.0,
    min_val_used=5.0,
    dB_averaging=True,
    remove_small_objects=True,
    min_km2_size=10,
    binary_close=False,
    val_for_max_rad=30,
    max_rad_km=5.0,
    core_val=3,
    nosfcecho=0,
    weakecho=3,
    bkgd_val=1,
    feat_val=2,
):
    """
    基于相对背景场的差异识别特征回波。
    方法描述见 Tomkins et al. (2023)，其思想来源于
    Steiner et al. (1995)、Yuter and Houze (1997)、
    Yuter et al. (2005) 的层状-对流分类方法。

    分类编号如下：
    nosfcecho = 无地面回波 / 未定义
    bkgd_val = 背景回波（如层状）
    feat_val = 特征回波（如对流）
    weakecho = 弱回波

    field : array
        待识别特征的二维场。
    x, y : array
        场的 x/y 坐标。
    dx, dy : float
        x/y 方向分辨率，单位米。
    always_core_thres : float, optional
        始终判定为特征回波的阈值。高于该阈值的格点直接判为特征。
    bkg_rad_km : float, optional
        背景平均半径（km），默认 11 km，建议不小于约 3 倍网格间距。
    use_cosine : bool, optional
        是否使用余弦判据（True，见 Yuter and Houze 1997）识别核心，
        否则使用标量差值判据（False）。
    max_diff : float, optional
        判为特征所需的最大差值参数，
        对应 Yuter and Houze (1997) 式 B1 的参数 a。
    zero_diff_cos_val : float, optional
        余弦函数中差值为 0 时对应的场值，
        对应 Yuter and Houze (1997) 式 B1 的参数 b。
    scalar_diff : float, optional
        标量差值判据中的增量或倍率参数。
    use_addition : bool, optional
        标量差值判据中使用加法（True）或乘法（False）。
    calc_thres : float, optional
        背景平均时所需有效样本占比阈值。
    weak_echo_thres : float, optional
        弱回波阈值，低于该值的格点判为弱回波。
    min_val_used : float, optional
        分类最小值阈值。低于该值的格点判为无地面回波。
        详细讨论可见 Yuter and Houze (1997) 与 Yuter et al. (2005)。
    dB_averaging : bool, optional
        是否在求背景平均前把 dBZ 转为线性 Z。非 dBZ 变量通常设为 False。
    remove_small_objects : bool, optional
        是否移除核心数组中的小连通体，默认 True。
    min_km2_size : float, optional
        核心最小面积阈值（km^2），小于该值的核心将被移除。
    binary_close : bool, optional
        是否对核心执行二值闭运算，默认 False。
    val_for_max_rad : float, optional
        达到最大扩张半径所需的背景场阈值。
    max_rad_km : float, optional
        核心向外扩张判为特征回波的最大半径（km）。
    core_val : int, optional
        核心回波类别编号。
    nosfcecho : int, optional
        无地面回波类别编号（由 min_val_used 判定）。
    weakecho : int, optional
        弱回波类别编号（由 weak_echo_thres 判定）。
    bkgd_val : int, optional
        背景回波类别编号。
    feat_val : int, optional
        特征回波类别编号。

    Returns
    -------
    field_bkg : array
        背景场数组。
    core_array : array
        初始核心数组（未执行半径扩张）。
    feature_array : array
        执行半径扩张后的特征识别结果。
    """

    # 构造背景平均和半径扩张所需掩膜。
    # 根据最大半径计算最大直径（像素）。
    max_diameter = int(np.floor((max_rad_km / (dx / 1000)) * 2))
    # 若直径为偶数，调整为奇数。
    if max_diameter % 2 == 0:
        max_diameter = max_diameter + 1
    # 计算掩膜中心索引。
    center_mask_x = int(np.floor(max_diameter / 2))

    # 准备背景平均掩膜。
    # 根据背景半径和网格间距估算背景窗口像素直径。
    bkg_diameter_pix = int(np.floor((bkg_rad_km / (dx / 1000)) * 2))
    # 若窗口直径为偶数，调整为奇数。
    if bkg_diameter_pix % 2 == 0:
        bkg_diameter_pix = bkg_diameter_pix + 1
    # 计算背景窗口中心索引。
    bkg_center = int(np.floor(bkg_diameter_pix / 2))
    # 创建背景掩膜数组。
    bkg_mask_array = np.ones((bkg_diameter_pix, bkg_diameter_pix), dtype=float)
    # 掩蔽圆形半径外区域。
    bkg_mask_array = create_radial_mask(
        bkg_mask_array,
        min_rad_km=0,
        max_rad_km=bkg_rad_km,
        x_pixsize=dx / 1000,
        y_pixsize=dy / 1000,
        center_x=bkg_center,
        center_y=bkg_center,
        circular=True,
    )

    # 特征识别：先把输入场转为 masked array。
    field = np.ma.masked_invalid(field)
    # 计算背景场。
    field_bkg = calc_bkg_intensity(field, bkg_mask_array, dB_averaging, calc_thres)

    # 根据余弦判据或标量判据识别核心。
    if use_cosine:
        core_array = core_cos_scheme(
            field, field_bkg, max_diff, zero_diff_cos_val, always_core_thres, core_val
        )
    else:
        core_array = core_scalar_scheme(
            field,
            field_bkg,
            scalar_diff,
            always_core_thres,
            core_val,
            use_addition=use_addition,
        )

    # 根据背景场给核心分配扩张半径。
    radius_array_km = assign_feature_radius_km(
        field_bkg, val_for_max_rad=val_for_max_rad, max_rad=max_rad_km
    )

    # 移除过小核心对象。
    if remove_small_objects:
        # 根据网格分辨率计算最小像素面积阈值。
        min_pix_size = min_km2_size / ((dx / 1000) * (dy / 1000))
        # 对核心连通体做标记。
        cc_labels, _ = scipy.ndimage.label(core_array)
        # 在原掩膜区域屏蔽标签。
        cc_labels = np.ma.masked_where(core_array.mask, cc_labels)

        # 逐个连通体检查面积阈值。
        for lab in np.unique(cc_labels):
            # 统计该连通体像素数。
            size_lab = np.count_nonzero(cc_labels == lab)
            # 像素数小于阈值则移除。
            if size_lab < min_pix_size:
                core_array[cc_labels == lab] = 0

    # 执行二值闭运算（可选）。
    if binary_close:
        # 闭运算后得到二值数组。
        close_core = scipy.ndimage.binary_closing(core_array).astype(int)
        # 把二值结果映射回核心类别值。
        core_array = close_core * core_val

    # 使用二值膨胀执行核心半径扩张。
    # 创建临时赋值数组。
    temp_assignment = np.zeros_like(core_array)

    # 按半径逐级扩张。
    for radius in np.arange(1, max_rad_km + 1):
        # 构造当前半径对应的掩膜。
        radius_mask_array = create_radius_mask(
            max_diameter, radius, dx / 1000, dy / 1000, center_mask_x
        )
        # 找到当前半径对应位置。
        temp = radius_array_km == radius
        # 提取该半径对应的核心。
        temp_core = np.ma.masked_where(~temp, core_array)
        # 执行膨胀。
        temp_dilated = scipy.ndimage.binary_dilation(
            temp_core.filled(0), radius_mask_array
        )
        # 累加到赋值数组。
        temp_assignment = temp_assignment + temp_dilated

    # 将扩张结果写回核心数组。
    core_copy = np.ma.copy(core_array)
    core_copy[temp_assignment >= 1] = core_val

    # 生成最终特征分类结果。
    feature_array = np.zeros_like(field)
    feature_array = classify_feature_array(
        field,
        feature_array,
        core_copy,
        nosfcecho,
        feat_val,
        bkgd_val,
        weakecho,
        core_val,
        min_val_used,
        weak_echo_thres,
    )
    # 在输入掩膜区域保持掩蔽。
    feature_array = np.ma.masked_where(field.mask, feature_array)

    return field_bkg, core_array, feature_array


# 辅助函数


def create_radial_mask(
    mask_array,
    min_rad_km,
    max_rad_km,
    x_pixsize,
    y_pixsize,
    center_x,
    center_y,
    circular=True,
):
    """
    计算径向距离掩膜。
    距离在 [min_rad_km, max_rad_km] 内的像素赋值为 1，其余赋值为 0。
    该实现同时支持矩形数组和非等距像素。

    Parameters
    ----------
    mask_array : array
        待掩膜数组。
    min_rad_km, max_rad_km : float
        非掩膜区域的最小和最大半径（km）。
    x_pixsize, y_pixsize : float
        x/y 方向像素尺寸（km）。
    center_x, center_y : int
        x/y 方向中心像素索引。
    circular : bool
        True 返回圆形掩膜，False 返回方形掩膜。

    Returns
    -------
    mask_array : array
        应用径向距离后的掩膜数组。
    """

    xsize, ysize = mask_array.shape

    for j in np.arange(0, ysize, 1):
        for i in np.arange(0, xsize, 1):
            # 计算当前像素到中心的距离。
            if circular:
                x_range_sq = ((center_x - i) * x_pixsize) ** 2
                y_range_sq = ((center_y - j) * y_pixsize) ** 2
                circ_range = np.sqrt(x_range_sq + y_range_sq)
            # circular=False 时使用方形距离定义。
            else:
                x_range = abs(int(np.floor(center_x - i) * x_pixsize))
                y_range = abs(int(np.floor(center_y - j) * y_pixsize))

                if x_range > y_range:
                    circ_range = x_range
                else:
                    circ_range = y_range
            # 在半径范围内赋值为 1，否则为 0。
            if (circ_range <= max_rad_km) and (circ_range >= min_rad_km):
                mask_array[j, i] = 1
            else:
                mask_array[j, i] = 0

    return mask_array


def calc_bkg_intensity(field, bkg_mask_array, dB_averaging, calc_thres=None):
    """
    计算输入场的背景平均值。
    每个像素的平均窗口由 bkg_mask_array 指定。

    Parameters
    ----------
    field : array
        待计算背景平均的输入场。
    bkg_mask_array : array
        用于背景平均的径向掩膜。
    dB_averaging : bool
        为 True 时先将 dBZ 转为线性 Z 再平均。
    calc_thres : float
        背景平均的最小有效样本占比阈值。

    Returns
    -------
    field_bkg : array
        背景平均数组。
    """

    # dBZ 平均前先转为线性 Z。
    if dB_averaging:
        field = 10 ** (field / 10)

    # 使用圆形窗口计算背景场。
    field_bkg = scipy.ndimage.generic_filter(
        field.filled(np.nan),
        function=np.nanmean,
        mode="constant",
        footprint=bkg_mask_array.astype(bool),
        cval=np.nan,
    )

    # 若给定 calc_thres，则按有效样本比例进行筛选。
    if calc_thres is not None:
        # 统计有效样本数。
        field_count = scipy.ndimage.generic_filter(
            field.filled(0),
            function=np.count_nonzero,
            mode="constant",
            footprint=bkg_mask_array.astype(bool),
            cval=0,
        )
        # 计算有效样本阈值。
        val = calc_thres * np.count_nonzero(bkg_mask_array)
        # 有效样本不足的位置设为掩蔽。
        field_bkg = np.ma.masked_where(field_count < val, field_bkg)

    # 保持原始掩膜区域。
    field_bkg = np.ma.masked_where(field.mask, field_bkg)

    # 若使用 dBZ 平均流程，最后再转回 dBZ。
    if dB_averaging:
        field_bkg = 10 * np.log10(field_bkg)
        # 保持原始掩膜区域。
        field_bkg = np.ma.masked_where(field.mask, field_bkg)

    return field_bkg


def core_cos_scheme(
    field, field_bkg, max_diff, zero_diff_cos_val, always_core_thres, CS_CORE
):
    """
    使用余弦判据识别核心回波。

    Parameters
    ----------
    field : array
        输入场值。
    field_bkg : array
        背景平均场。
    max_diff : float
        判为核心所需最大差值参数。
    zero_diff_cos_val : float
        余弦函数返回零差值对应的场值。
    always_core_thres : float
        高于该阈值直接判为特征。
    CS_CORE : int
        核心类别赋值。

    Returns
    -------
    core_array : array
        核心识别结果数组。
    """

    # 初始化：默认均非核心。
    core_array = np.zeros_like(field)

    # 计算整场差值阈值。
    zDiff = max_diff * np.cos((np.pi * field_bkg) / (2 * zero_diff_cos_val))
    zDiff[zDiff < 0] = 0  # 差值小于 0 时设为 0。
    zDiff[field_bkg < 0] = max_diff  # 背景小于 0 时设为最大差值。

    # 设置核心：满足绝对阈值或相对差值阈值。
    core_elements = np.logical_or(
        (field >= always_core_thres), (field - field_bkg) >= zDiff
    )
    core_elements = core_elements.filled(0)
    core_array[core_elements] = CS_CORE

    # 保持原始掩膜区域。
    core_array = np.ma.masked_where(field.mask, core_array)

    return core_array


def core_scalar_scheme(
    field, field_bkg, max_diff, always_core_thres, CORE, use_addition=False
):
    """
    使用标量差值判据识别核心回波。

    Parameters
    ----------
    field : array
        输入场值。
    field_bkg : array
        背景平均场。
    max_diff : float
        判为核心所需最大差值参数。
    always_core_thres : float
        高于该阈值直接判为特征。
    CORE : int
        核心类别赋值。
    use_addition : bool
        标量判据使用加法（True）或乘法（False）。

    Returns
    -------
    core_array : array
        核心识别结果数组。
    """

    # 初始化：默认均非核心。
    core_array = np.zeros_like(field)

    # 计算整场差值阈值。
    # use_addition=True 使用加法，否则使用乘法。
    if use_addition:
        zDiff = (max_diff + field_bkg) - field_bkg
    else:
        zDiff = (max_diff * field_bkg) - field_bkg

    zDiff[zDiff < 0] = 0  # 差值小于 0 时设为 0。
    zDiff[field_bkg < 0] = 0  # 背景小于 0 时设为 0。

    # 设置核心：满足绝对阈值或相对差值阈值。
    core_elements = np.logical_or(
        (field >= always_core_thres), (field - field_bkg) >= zDiff
    )
    core_elements = core_elements.filled(0)
    core_array[core_elements] = CORE

    # 保持原始掩膜区域。
    core_array = np.ma.masked_where(field.mask, core_array)

    return core_array


def create_radius_mask(max_diameter, radius_km, x_spacing, y_spacing, center_mask_x):
    """
    根据直径和半径构造圆形掩膜。

    Parameters
    ----------
    max_diameter : int
        最大直径（像素网格尺度）。
    radius_km : int
        半径（km）。
    x_spacing, y_spacing : float
        x/y 方向像素间距（km）。
    center_mask_x : int
        掩膜中心点索引。

    Returns
    -------
    feature_mask_array : array
        半径掩膜数组。
    """

    feature_mask_array = np.zeros((max_diameter, max_diameter))
    feature_mask_array = create_radial_mask(
        feature_mask_array,
        0,
        radius_km,
        x_spacing,
        y_spacing,
        center_mask_x,
        center_mask_x,
        True,
    )

    return feature_mask_array


def assign_feature_radius_km(field_bkg, val_for_max_rad, max_rad=5):
    """
    根据背景场值分配特征扩张半径（km）。

    Parameters
    ----------
    field_bkg : array
        背景场数组。
    val_for_max_rad : float
        达到最大半径对应的背景场阈值。
    max_rad : float, optional
        最大半径（km）。

    Returns
    -------
    radius_array_km : array
        各格点对应的半径数组。
    """

    radius_array_km = np.ones_like(field_bkg)

    radius_array_km[field_bkg >= (val_for_max_rad - 15)] = max_rad - 3
    radius_array_km[field_bkg >= (val_for_max_rad - 10)] = max_rad - 2
    radius_array_km[field_bkg >= (val_for_max_rad - 5)] = max_rad - 1
    radius_array_km[field_bkg >= val_for_max_rad] = max_rad

    return radius_array_km


def classify_feature_array(
    field,
    feature_array,
    core_array,
    NOSFCECHO,
    FEAT_VAL,
    BKGD_VAL,
    WEAKECHO,
    CORE,
    MINDBZUSE,
    WEAKECHOTHRES,
):
    """
    基于核心与阈值规则生成初始特征分类结果。

    Parameters
    ----------
    field : array
        输入场数组。
    feature_array : array
        输出分类数组。
    core_array : array
        核心数组。
    NOSFCECHO : int
        无地面回波类别编号。
    FEAT_VAL : int
        特征回波类别编号。
    BKGD_VAL : int
        背景回波类别编号。
    WEAKECHO : int
        弱回波类别编号。
    CORE : int
        核心类别编号。
    MINDBZUSE : float
        分类最小阈值，低于该值设为无地面回波。
    WEAKECHOTHRES : float
        弱回波阈值，低于该值设为弱回波。

    Returns
    -------
    feature_array : array
        分类结果数组。
    """

    # 按固定优先级赋值，避免重复覆盖冲突。
    # 初始先设为背景回波。
    feature_array[:] = BKGD_VAL
    # 掩膜区域设为无地面回波。
    feature_array[field.mask] = NOSFCECHO
    # 核心设为特征回波。
    feature_array[core_array == CORE] = FEAT_VAL
    # 低于弱回波阈值设为弱回波。
    feature_array[field < WEAKECHOTHRES] = WEAKECHO
    # 低于最小阈值设为无地面回波。
    feature_array[field < MINDBZUSE] = NOSFCECHO

    return feature_array
