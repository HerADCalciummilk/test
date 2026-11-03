#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.

from warnings import warn

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


def get_coeff_rkdp(freq):
    """
    获取特定频率的R(kdp)幂律系数。

    Parameters
    ----------
    freq : float
        雷达频率 [Hz].

    Returns
    -------
    alpha, beta : floats
        幂律系数。

    """
    coeff_rkdp_dict = _coeff_rkdp_table()

    freq_band = get_freq_band(freq)
    if (freq_band is not None) and (freq_band in coeff_rkdp_dict):
        return coeff_rkdp_dict[freq_band]

    if freq < 2e9:
        freq_band_aux = "S"
    elif freq > 12e9:
        freq_band_aux = "X"

    warn(
        "Radar frequency out of range. "
        + "Coefficients only applied to S, C or X band. "
        + freq_band_aux
        + " band coefficients will be used."
    )

    return coeff_rkdp_dict[freq_band_aux]


def _coeff_rkdp_table():
    """定义每个频段的 R(kdp) 幂律系数。"""
    coeff_rkdp_dict = dict()

    # S band: Beard and Chuang coefficients
    coeff_rkdp_dict.update({"S": (50.70, 0.8500)})

    # C band: Beard and Chuang coefficients
    coeff_rkdp_dict.update({"C": (29.70, 0.8500)})

    # X band: Brandes coefficients
    coeff_rkdp_dict.update({"X": (15.81, 0.7992)})

    return coeff_rkdp_dict


def get_coeff_ra(freq):
    """
    获取特定频率的R(A)幂律系数。

    Parameters
    ----------
    freq : float
        雷达频率 [Hz].

    Returns
    -------
    alpha, beta : floats
        幂律系数。

    """
    coeff_ra_dict = _coeff_ra_table()

    freq_band = get_freq_band(freq)
    if (freq_band is not None) and (freq_band in coeff_ra_dict):
        return coeff_ra_dict[freq_band]

    if freq < 2e9:
        freq_band_aux = "S"
    elif freq > 12e9:
        freq_band_aux = "X"

    warn(
        "Radar frequency out of range. "
        + "Coefficients only applied to S, C or X band. "
        + freq_band_aux
        + " band coefficients will be used."
    )

    return coeff_ra_dict[freq_band_aux]


def _coeff_ra_table():
    """定义每个频段的 R(A) 幂律系数。"""
    coeff_ra_dict = dict()

    # S band: at 10 deg C according to tables from Ryzhkov et al. 2014
    coeff_ra_dict.update({"S": (3100.0, 1.03)})

    # C band: at 10 deg C according to tables from Diederich et al. 2015
    coeff_ra_dict.update({"C": (250.0, 0.91)})

    # X band: at 10 deg C according to tables from Diederich et al. 2015
    coeff_ra_dict.update({"X": (45.5, 0.83)})

    return coeff_ra_dict