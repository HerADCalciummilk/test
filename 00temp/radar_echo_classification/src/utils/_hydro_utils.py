#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""hydroclass_semisupervised 专用辅助函数。"""

from warnings import warn

import numpy as np


def ma_broadcast_to(array, tup):
    """
    保证掩膜数组在广播时不丢失 mask。

    Parameters
    ----------
    array : Numpy masked array or normal array
        待广播的掩膜数组或普通数组。
    tup : shape as tuple
        目标广播形状。

    Returns
    -------
    broadcasted_array
        广播后的数组；若输入带 mask，则一并保留，否则仅返回广播后的数据。
    """
    broadcasted_array = np.broadcast_to(array, tup)

    if np.ma.is_masked(array):
        initial_mask = np.ma.getmask(array)
        initial_fill_value = array.fill_value
        broadcasted_mask = np.broadcast_to(initial_mask, tup)
        return np.ma.array(
            broadcasted_array, mask=broadcasted_mask, fill_value=initial_fill_value
        )

    return broadcasted_array


def _standardize(data, field_name, mx=None, mn=None):
    """
    将雷达变量标准化到 [-1, 1] 区间。

    Parameters
    ----------
    data : array
        雷达变量场。
    field_name : str
        变量名称（relH、Zh、ZDR、KDP 或 RhoHV）。
    mx, mn : floats or None, optional
        数据上下界。未给定时按变量默认阈值表取值。

    Returns
    -------
    field_std : array
        标准化后的变量场。

    """
    if field_name == "relH":
        field_std = 2.0 / (1.0 + np.ma.exp(-0.005 * data)) - 1.0
        return field_std

    if (mx is None) or (mn is None):
        dlimits_dict = _data_limits_table()
        if field_name not in dlimits_dict:
            raise ValueError(
                "Field "
                + field_name
                + " unknown. "
                + "Valid field names for standardizing are: "
                + "relH, Zh, ZDR, KDP and RhoHV"
            )
        mx, mn = dlimits_dict[field_name]

    if field_name == "KDP":
        data[data < -0.5] = -0.5
        data = 10.0 * np.ma.log10(data + 0.6)
    elif field_name == "RhoHV":
        # 避免 log 计算出现无穷值。
        data[data > 1.0] = 1.0
        data = 10.0 * np.ma.log10(1.0000000000001 - data)

    mask = np.ma.getmaskarray(data)
    field_std = 2.0 * (data - mn) / (mx - mn) - 1.0
    field_std[data < mn] = -1.0
    field_std[data > mx] = 1.0
    field_std[mask] = np.ma.masked

    return field_std


def _assign_to_class(
    fields_dict,
    mass_centers,
    var_names=("Zh", "ZDR", "KDP", "RhoHV", "relH"),
    weights=np.array([1.0, 1.0, 1.0, 0.75, 0.5]),
    t_vals=None,
):
    """
    根据变量与质心距离为每个距离库点分配水凝物类别。

    Parameters
    ----------
    fields_dict : dict
        已标准化到 [-1, 1] 的输入变量字典。
    mass_centers : matrix
        已标准化的类别质心矩阵，形状为 (nclasses, nvariables)。
    var_names : array of str
        变量名称列表。
    weights : array
        各变量权重，长度为 nvariables。
    t_vals : array
        距离到比例变换系数，长度为 nclasses。

    Returns
    -------
    hydroclass : int array
        分类结果索引。
    entropy : float array
        分类熵。
    t_dist : float matrix
        当计算熵时返回各类别的变换后距离，
        可视作各水凝物占比的代理量，形状为 (nrays, nbins, nclasses)。

    """
    # 逐条扫描线计算到各类质心的距离，
    # 缺测值不参与距离累加。
    nrays = fields_dict[var_names[0]].shape[0]
    nbins = fields_dict[var_names[0]].shape[1]
    nclasses = mass_centers.shape[0]
    nvariables = mass_centers.shape[1]
    dtype = fields_dict[var_names[0]].dtype

    hydroclass = np.ma.empty((nrays, nbins), dtype=np.uint8)
    entropy = None
    t_dist = None
    if t_vals is not None:
        entropy = np.ma.empty((nrays, nbins), dtype=dtype)
        t_dist = np.ma.masked_all((nrays, nbins, nclasses), dtype=dtype)

    for ray in range(nrays):
        data = []
        for var_name in var_names:
            data.append(fields_dict[var_name][ray, :])
        data = np.ma.array(data, dtype=dtype)
        weights_mat = np.broadcast_to(
            weights.reshape(nvariables, 1), (nvariables, nbins)
        )
        dist = np.ma.zeros((nclasses, nbins), dtype=dtype)

        mask = np.ma.getmaskarray(fields_dict[var_names[0]][ray, :])
        for i in range(nclasses):
            centroids_class = mass_centers[i, :]
            centroids_class = np.broadcast_to(
                centroids_class.reshape(nvariables, 1), (nvariables, nbins)
            )
            dist_ray = np.ma.sqrt(
                np.ma.sum(((centroids_class - data) ** 2.0) * weights_mat, axis=0)
            )
            dist_ray[mask] = np.ma.masked
            dist[i, :] = dist_ray

        # argsort 后第一个类别即最近质心对应的水凝物类型。
        class_vec = dist.argsort(axis=0, fill_value=10e40)
        hydroclass_ray = (class_vec[0, :] + 1).astype(np.uint8)
        hydroclass_ray[mask] = 0
        hydroclass[ray, :] = hydroclass_ray

        if t_vals is None:
            continue

        # 若要求熵，则进一步将距离映射为“相对占比”，
        # 并计算分类熵。
        t_vals_ray = np.ma.masked_where(mask, t_vals[class_vec[0, :]])
        t_vals_ray = ma_broadcast_to(t_vals_ray.reshape(1, nbins), (nclasses, nbins))
        t_dist_ray = np.ma.exp(-t_vals_ray * dist)

        dist_total = np.ma.sum(t_dist_ray, axis=0)
        dist_total = ma_broadcast_to(dist_total.reshape(1, nbins), (nclasses, nbins))
        t_dist_ray /= dist_total

        entropy_ray = -np.ma.sum(
            t_dist_ray * np.ma.log(t_dist_ray) / np.ma.log(nclasses), axis=0
        )
        entropy_ray[mask] = np.ma.masked
        entropy[ray, :] = entropy_ray

        t_dist[ray, :, :] = np.ma.transpose(t_dist_ray)

    if t_vals is not None:
        t_dist *= 100.0

    return hydroclass, entropy, t_dist


def _assign_to_class_scan(
    fields_dict,
    mass_centers,
    var_names=("Zh", "ZDR", "KDP", "RhoHV", "relH"),
    weights=np.array([1.0, 1.0, 1.0, 0.75, 0.5]),
    t_vals=None,
):
    """
    根据变量与质心距离为每个距离库点分配水凝物类别。
    该版本一次性处理整幅扫描数据。

    Parameters
    ----------
    fields_dict : dict
        已标准化到 [-1, 1] 的输入变量字典。
    mass_centers : matrix
        已标准化的类别质心矩阵。
    var_names : array of str
        变量名称列表。
    weights : array
        各变量权重。
    t_vals : matrix
        距离到比例变换系数。

    Returns
    -------
    hydroclass : int array
        分类结果索引。
    entropy : float array
        分类熵。
    t_dist : float matrix
        当计算熵时返回各类别的变换后距离，
        可视作各水凝物占比的代理量，形状为 (nrays, nbins, nclasses)。

    """
    # 向量化版本一次处理整幅扫描数据，
    # 逻辑与 _assign_to_class 相同，
    # 只是把逐条扫描线循环改成了整体矩阵运算。
    nrays = fields_dict[var_names[0]].shape[0]
    nbins = fields_dict[var_names[0]].shape[1]
    nclasses = mass_centers.shape[0]
    nvariables = mass_centers.shape[1]
    dtype = fields_dict[var_names[0]].dtype

    data = []
    for var_name in var_names:
        data.append(fields_dict[var_name])
    data = np.ma.array(data, dtype=dtype)
    weights_mat = np.broadcast_to(
        weights.reshape(nvariables, 1, 1), (nvariables, nrays, nbins)
    )

    mask = np.ma.getmaskarray(fields_dict[var_names[0]])
    dist = np.ma.zeros((nrays, nbins, nclasses), dtype=dtype)
    t_dist = None
    entropy = None
    for i in range(nclasses):
        centroids_class = mass_centers[i, :]
        centroids_class = np.broadcast_to(
            centroids_class.reshape(nvariables, 1, 1), (nvariables, nrays, nbins)
        )
        dist_aux = np.ma.sqrt(
            np.ma.sum(((centroids_class - data) ** 2.0) * weights_mat, axis=0)
        )
        dist_aux[mask] = np.ma.masked
        dist[:, :, i] = dist_aux

    del data
    del weights_mat

    class_vec = dist.argsort(axis=-1, fill_value=10e40)
    hydroclass = np.ma.asarray(class_vec[:, :, 0] + 1, dtype=np.uint8)
    hydroclass[mask] = 0

    if t_vals is not None:
        t_vals_aux = np.ma.masked_where(mask, t_vals[class_vec[:, :, 0]])
        t_vals_aux = ma_broadcast_to(
            t_vals_aux.reshape(nrays, nbins, 1), (nrays, nbins, nclasses)
        )
        t_dist = np.ma.exp(-t_vals_aux * dist)
        del t_vals_aux

        dist_total = np.ma.sum(t_dist, axis=-1)
        dist_total = ma_broadcast_to(
            dist_total.reshape(nrays, nbins, 1), (nrays, nbins, nclasses)
        )
        t_dist /= dist_total
        del dist_total

        entropy = -np.ma.sum(t_dist * np.ma.log(t_dist) / np.ma.log(nclasses), axis=-1)
        entropy[mask] = np.ma.masked

        t_dist *= 100.0

    return hydroclass, entropy, t_dist


def _get_mass_centers(freq):
    """
    获取给定频率对应的水凝物分类质心。

    Parameters
    ----------
    freq : float
        雷达频率，单位 Hz。

    Returns
    -------
    mass_centers : ndarray 2D
        各水凝物类别与变量对应的质心矩阵，
        形状为 (nclasses, nvariables)。

    """
    mass_centers_dict = _mass_centers_table()

    freq_band = get_freq_band(freq)
    if (freq_band is not None) and (freq_band in mass_centers_dict):
        return mass_centers_dict[freq_band]

    if freq < 4e9:
        freq_band_aux = "C"
    elif freq > 12e9:
        freq_band_aux = "X"

    mass_centers = mass_centers_dict[freq_band_aux]
    warn(
        "Radar frequency out of range. "
        + "Centroids only valid for C or X band. "
        + freq_band_aux
        + " band centroids will be applied"
    )

    return mass_centers


def _mass_centers_table():
    """
    定义不同频段对应的水凝物分类质心查找表。

    Returns
    -------
    mass_centers_dict : dict
        频段到质心矩阵的映射字典。

    """
    nclasses = 9
    nvariables = 5
    mass_centers_c = np.zeros((nclasses, nvariables))
    mass_centers_x = np.zeros((nclasses, nvariables))

    mass_centers_dict = dict()
    # C 波段质心（由 MeteoSwiss Albis 雷达样本推导）。
    #                       Zh        ZDR     kdp   RhoHV    delta_Z
    mass_centers_c[0, :] = [13.5829, 0.4063, 0.0497, 0.9868, 1330.3]  # DS
    mass_centers_c[1, :] = [02.8453, 0.2457, 0.0000, 0.9798, 0653.8]  # CR
    mass_centers_c[2, :] = [07.6597, 0.2180, 0.0019, 0.9799, -1426.5]  # LR
    mass_centers_c[3, :] = [31.6815, 0.3926, 0.0828, 0.9978, 0535.3]  # GR
    mass_centers_c[4, :] = [39.4703, 1.0734, 0.4919, 0.9876, -1036.3]  # RN
    mass_centers_c[5, :] = [04.8267, -0.5690, 0.0000, 0.9691, 0869.8]  # VI
    mass_centers_c[6, :] = [30.8613, 0.9819, 0.1998, 0.9845, -0066.1]  # WS
    mass_centers_c[7, :] = [52.3969, 2.1094, 2.4675, 0.9730, -1550.2]  # MH
    mass_centers_c[8, :] = [50.6186, -0.0649, 0.0946, 0.9904, 1179.9]  # IH/HDG

    mass_centers_dict.update({"C": mass_centers_c})

    # X 波段质心（由 MeteoSwiss DX50 雷达样本推导）。
    #                       Zh        ZDR     kdp    RhoHV   delta_Z
    mass_centers_x[0, :] = [19.0770, 0.4139, 0.0099, 0.9841, 1061.7]  # DS
    mass_centers_x[1, :] = [03.9877, 0.5040, 0.0000, 0.9642, 0856.6]  # CR
    mass_centers_x[2, :] = [20.7982, 0.3177, 0.0004, 0.9858, -1375.1]  # LR
    mass_centers_x[3, :] = [34.7124, -0.3748, 0.0988, 0.9828, 1224.2]  # GR
    mass_centers_x[4, :] = [33.0134, 0.6614, 0.0819, 0.9802, -1169.8]  # RN
    mass_centers_x[5, :] = [08.2610, -0.4681, 0.0000, 0.9722, 1100.7]  # VI
    mass_centers_x[6, :] = [35.1801, 1.2830, 0.1322, 0.9162, -0159.8]  # WS
    mass_centers_x[7, :] = [52.4539, 2.3714, 1.1120, 0.9382, -1618.5]  # MH
    mass_centers_x[8, :] = [44.2216, -0.3419, 0.0687, 0.9683, 1272.7]  # IH/HDG

    mass_centers_dict.update({"X": mass_centers_x})

    return mass_centers_dict


def _data_limits_table():
    """
    定义标准化时各变量使用的数据上下界。

    Returns
    -------
    dlimits_dict : dict
        各变量上下界映射字典。

    """
    dlimits_dict = dict()
    dlimits_dict.update({"Zh": (60.0, -10.0)})
    dlimits_dict.update({"ZDR": (5.0, -1.5)})
    dlimits_dict.update({"KDP": (7.0, -10.0)})
    dlimits_dict.update({"RhoHV": (-5.23, -50.0)})
    dlimits_dict.update({"RelH": (5000.0, -5000.0)})

    return dlimits_dict


def get_freq_band(freq):
    """
    根据频率返回频段名称（S、C、X 等）。

    Parameters
    ----------
    freq : float
        雷达频率，单位 Hz。

    Returns
    -------
    freq_band : str
        频段名称。

    """
    if freq >= 2e9 and freq < 4e9:
        return "S"
    if freq >= 4e9 and freq < 8e9:
        return "C"
    if freq >= 8e9 and freq <= 12e9:
        return "X"

    warn("Unknown frequency band")

    return None


def _compute_coeff_transform(
    mass_centers, weights=np.array([1.0, 1.0, 1.0, 0.75, 0.5]), value=50.0
):
    """
    计算距离到比例变换所需系数。

    Parameters
    ----------
    mass_centers : ndarray 2D
        各类别和变量的质心矩阵，形状为 (nclasses, nvariables)。
    weights : array
        各变量权重，长度为 nvariables。
    value : float
        控制距离变换衰减速率的参数。

    Returns
    -------
    t_vals : ndarray 1D
        各类别对应的距离变换系数，长度为 nclasses。

    """
    nclasses, nvariables = np.shape(mass_centers)
    t_vals = np.empty((nclasses, nclasses), dtype=mass_centers.dtype)
    for i in range(nclasses):
        weights_mat = np.broadcast_to(
            weights.reshape(1, nvariables), (nclasses, nvariables)
        )
        centroids_class = mass_centers[i, :]
        centroids_class = np.broadcast_to(
            centroids_class.reshape(1, nvariables), (nclasses, nvariables)
        )
        t_vals[i, :] = np.sqrt(
            np.sum(
                weights_mat * np.power(np.abs(centroids_class - mass_centers), 2.0),
                axis=1,
            )
        )

    # 取每类距离中的次小值（最小值为自身距离 0）。
    t_vals = np.sort(t_vals, axis=-1)[:, 1]
    t_vals = np.log(value) / t_vals

    return t_vals
