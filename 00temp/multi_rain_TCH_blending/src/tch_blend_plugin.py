# -*- coding: utf-8 -*-
"""TCH 按权重加权合成降水场。

``TchBlendPlugin``：用 BTCH 权重对多模式格点场加权，得到 TCH 集成格点（及可选站点场）。
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

import meteva.base as meb
import numpy as np

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
for _p in (_SRC_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.base_plugin import BasePlugin


class TchBlendPlugin(BasePlugin):
    """对多模式降水格点按权重合成。"""

    def process(self, qpf_model, weights, station=None, **kwargs: Any) -> Dict[str, Any]:
        """
        Args:
            qpf_model: 含 ``member`` 维的模式降水 ``xarray`` / griddata。
            weights: 与成员数一致的一维权重。
            station: 可选站点表；给出时额外插值出站点场。
            **kwargs: 预留扩展。可用 ``member_name``（默认 ``tch``）。

        Returns:
            ``{"qpf_combine": ..., "sta_combine": ...}``；未传 ``station`` 时
            ``sta_combine`` 为 ``None``。
        """
        weights = np.asarray(weights, dtype=float)
        member_name = str(kwargs.get("member_name") or "tch")
        model_list_ev = qpf_model["member"].data
        ny = int(qpf_model["lat"].shape[0])
        nx = int(qpf_model["lon"].shape[0])
        ndim = int(qpf_model["member"].shape[0])
        if len(weights) != ndim:
            raise ValueError(
                "weights 长度须等于成员数，收到 %s vs %s" % (len(weights), ndim)
            )

        data_temp = None
        for rank_num in range(0, ndim):
            field = np.array(qpf_model[rank_num, 0, 0, 0, :, :]) * weights[rank_num]
            if rank_num == 0:
                data_temp = field
            else:
                data_temp = data_temp + field

        data_temp = np.array(data_temp).reshape(1, 1, 1, ny, nx)
        qpf_combine = qpf_model.sel(member=model_list_ev[0]).copy()
        qpf_combine.data = data_temp
        qpf_combine = meb.xarray_to_griddata(qpf_combine)
        meb.set_griddata_coords(qpf_combine, member_list=[member_name])

        sta_combine = None
        if station is not None:
            sta_combine = meb.interp_gs_linear(qpf_combine, station)

        return {
            "qpf_combine": qpf_combine,
            "sta_combine": sta_combine,
            "model_members": model_list_ev,
        }
