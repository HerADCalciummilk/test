# -*- coding: utf-8 -*-
"""TCH 误差评估与 BTCH 集成权重。

``TchWeightPlugin``：不确定度估计与权重计算。
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

import numpy as np
from scipy import optimize

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
for _p in (_SRC_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.base_plugin import BasePlugin


class TchWeightPlugin(BasePlugin):
    """由多模式展平场计算 TCH 不确定度与 BTCH 权重。"""

    def get_weight_mul(self, err_array):
        """按误差乘积归一化计算各模式集成权重（BTCH）。

        权重 w_i 正比于除第 i 个模式外其余模式误差的平方连乘，
        因此单个模式误差越小，其权重越大。
        """
        w = np.zeros(np.shape(err_array))
        n = len(err_array)

        amul_list = []
        for i in range(n):
            amul = 1
            for j in range(n):
                if i != j:
                    amul = amul * pow(err_array[j], 2)
            amul_list.append(amul)

        accu = 0.0
        for amul in amul_list:
            accu = accu + amul

        for i in range(n):
            w[i] = amul_list[i] / accu

        return w

    def cal_uct(self, arr):
        """基于误差协方差矩阵估计各模式（含参考场）的不确定性。

        参数
            arr : ndarray, shape (M, N)
                各模式预报场按列排列；最后一列（N-1）为参考场，其余为待评估场。
        返回
            uct   : ndarray，各列的绝对不确定度；
            r_uct : ndarray，各列的相对不确定度（%）。
        """

        def my_fun(r):
            """优化目标函数：误差协方差矩阵重构的残差平方和。"""
            f = 0
            for j in range(0, len(S)):
                f = f + np.power(r[j], 2)
                for k in range(0, len(S)):
                    if j < k:
                        f = np.power((S[j, k] - r[len(S)] + r[j] + r[k]), 2) + f
            K = np.linalg.det(S)
            return f / np.power(K, 2 * len(S))

        M, N = np.shape(arr)

        ref_arr = arr[:, N - 1]
        tar_arr = arr[:, 0:N - 1]

        Y = tar_arr - np.repeat(np.reshape(ref_arr, (M, 1)), N - 1, axis=1)

        S = np.cov(Y.T)
        print(S)

        u = np.ones((1, N - 1))
        R = np.zeros((N, N))
        R[N - 1, N - 1] = 1 / (2 * np.dot(np.dot(u, np.linalg.inv(S)), u.T))

        x0 = R[:, N - 1]

        u_ = np.ones((1, len(S)))
        det_S = np.linalg.det(S)
        inv_S = np.linalg.inv(S)
        denominator = np.power(det_S, 2 / len(S))

        cons = {
            "type": "ineq",
            "fun": lambda r: (r[len(S)] - np.dot(
                np.dot(
                    np.reshape(r[0:-1], (1, len(r) - 1)) - r[len(S)] * u_, inv_S),
                (np.reshape(r[0:-1], (1, len(r) - 1)) - r[len(S)] * u_).T)) / denominator,
        }

        x = optimize.minimize(
            my_fun,
            x0,
            method="COBYLA",
            tol=2e-10,
            constraints=cons,
        )

        R[:, N - 1] = x.x

        for ii in range(0, N - 1):
            for jj in range(0, N - 1):
                if ii < jj or ii == jj:
                    R[ii, jj] = S[ii, jj] - R[N - 1, N - 1] + R[ii, N - 1] + R[jj, N - 1]
        R += R.T - np.diag(R.diagonal())
        for ii in range(0, N):
            for jj in range(0, N):
                R[jj, ii] = R[ii, jj]

        uct = np.sqrt(R.diagonal())
        r_uct = uct / np.mean(abs(arr), axis=0) * 100

        return uct, r_uct

    def process(self, ensemble_2d, **kwargs: Any) -> Dict[str, np.ndarray]:
        """
        Args:
            ensemble_2d: shape ``(格点数, 成员数)``，最后一列作参考场。
            **kwargs: 预留扩展，当前未用。

        Returns:
            ``{"uct": ..., "r_uct": ..., "weights": ...}``
        """
        _ = kwargs
        arr = np.asarray(ensemble_2d, dtype=float)
        uct, r_uct = self.cal_uct(arr)
        weights = self.get_weight_mul(uct)
        return {"uct": uct, "r_uct": r_uct, "weights": weights}
