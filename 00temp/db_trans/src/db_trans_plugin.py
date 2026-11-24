# -*- coding: utf-8 -*-
"""降水强度变换（原 ``dB_trans``）。

``DbTransPlugin`` 继承 ``BasePlugin``，四个变换为实例方法；
``process`` 按 ``method`` 调度。

共用参数（各方法均可）：``R``、``metadata``、``inverse``。
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import scipy.stats as scipy_stats
from scipy.interpolate import interp1d

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
for _p in (_SRC_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.base_plugin import BasePlugin

warnings.filterwarnings(
    "ignore", category=RuntimeWarning
)  # To deactivate warnings for comparison operators with NaNs

METHODS = ("db", "box", "nq", "sqrt")
ArrayLike = Union[np.ndarray, list, tuple]


class DbTransPlugin(BasePlugin):
    """降水强度正/逆变换。"""

    METHODS = METHODS

    def dB_transform(
        self, R, metadata=None, threshold=None, zerovalue=None, inverse=False
    ):
        """Methods to transform precipitation intensities to/from dB units.

        共用参数：``R``、``metadata``、``inverse``。

        本方法非复用（特有）参数：
            threshold: 阈值（与 ``R`` 同单位）。正变换默认 0.1；逆变换默认 -10（dB）。
                省略时优先用 ``metadata["threshold"]``。
            zerovalue: 低于阈值的无雨格点赋值。正变换默认 ``threshold_dB - 5``；
                逆变换默认 0.0。

        Parameters
        ----------
        R: array-like
            Array of any shape to be (back-)transformed.
        metadata: dict, optional
            Metadata dictionary containing the transform, zerovalue and threshold
            attributes as described in the documentation of
            :py:mod:`pysteps.io.importers`.
        threshold: float, optional
            Optional value that is used for thresholding with the same units as R.
            If None, the threshold contained in metadata is used.
            If no threshold is found in the metadata,
            a value of 0.1 is used as default.
        zerovalue: float, optional
            The value to be assigned to no rain pixels as defined by the threshold.
            It is equal to the threshold - 1 by default.
        inverse: bool, optional
            If set to True, it performs the inverse transform. False by default.

        Returns
        -------
        R: array-like
            Array of any shape containing the (back-)transformed units.
        metadata: dict
            The metadata with updated attributes.
        """

        R = R.copy()

        if metadata is None:
            if inverse:
                metadata = {"transform": "dB"}
            else:
                metadata = {"transform": None}

        else:
            metadata = metadata.copy()

        # to dB units
        if not inverse:

            if metadata["transform"] == "dB":
                return R, metadata

            if threshold is None:
                threshold = metadata.get("threshold", 0.1)

            zeros = R < threshold

            # Convert to dB
            R[~zeros] = 10.0 * np.log10(R[~zeros])
            threshold = 10.0 * np.log10(threshold)

            # Set value for zeros
            if zerovalue is None:
                zerovalue = threshold - 5  # TODO: set to a more meaningful value
            R[zeros] = zerovalue

            metadata["transform"] = "dB"
            metadata["zerovalue"] = zerovalue
            metadata["threshold"] = threshold

            return R, metadata

        # from dB units
        elif inverse:

            if metadata["transform"] != "dB":
                return R, metadata

            if threshold is None:
                threshold = metadata.get("threshold", -10.0)
            if zerovalue is None:
                zerovalue = 0.0

            R = 10.0 ** (R / 10.0)
            threshold = 10.0 ** (threshold / 10.0)
            R[R < threshold] = zerovalue

            metadata["transform"] = None
            metadata["threshold"] = threshold
            metadata["zerovalue"] = zerovalue

            return R, metadata

    def boxcox_transform(
        self, R, metadata=None, Lambda=None, threshold=None, zerovalue=None, inverse=False
    ):
        """
        The one-parameter Box-Cox transformation.

        共用参数：``R``、``metadata``、``inverse``。

        本方法非复用（特有）参数：
            Lambda: Box-Cox 幂参数；默认 0（对数变换）。也可写在
                ``metadata["BoxCox_lambda"]``。``Lambda < 1`` 适合正偏，``> 1`` 适合负偏。
            threshold: 阈值（与 ``R`` 同单位）。正变换默认 0.1；逆变换默认 -10。
            zerovalue: 无雨格点赋值。正变换默认 ``threshold - 1``；逆变换默认 0.0。

        The Box-Cox transform is a well-known power transformation introduced by
        Box and Cox (1964). In its one-parameter version, the Box-Cox transform
        takes the form T(x) = ln(x) for Lambda = 0,
        or T(x) = (x**Lambda - 1)/Lambda otherwise.

        Default parameters will produce a log transform (i.e. Lambda=0).

        Parameters
        ----------
        R: array-like
            Array of any shape to be transformed.
        metadata: dict, optional
            Metadata dictionary containing the transform, zerovalue and threshold
            attributes as described in the documentation of
            :py:mod:`pysteps.io.importers`.
        Lambda: float, optional
            Parameter Lambda of the Box-Cox transformation.
            It is 0 by default, which produces the log transformation.

            Choose Lambda < 1 for positively skewed data, Lambda > 1 for negatively
            skewed data.
        threshold: float, optional
            The value that is used for thresholding with the same units as R.
            If None, the threshold contained in metadata is used.
            If no threshold is found in the metadata,
            a value of 0.1 is used as default.
        zerovalue: float, optional
            The value to be assigned to no rain pixels as defined by the threshold.
            It is equal to the threshold - 1 by default.
        inverse: bool, optional
            If set to True, it performs the inverse transform. False by default.

        Returns
        -------
        R: array-like
            Array of any shape containing the (back-)transformed units.
        metadata: dict
            The metadata with updated attributes.

        References
        ----------
        Box, G. E. and Cox, D. R. (1964), An Analysis of Transformations. Journal
        of the Royal Statistical Society: Series B (Methodological), 26: 211-243.
        doi:10.1111/j.2517-6161.1964.tb00553.x
        """

        R = R.copy()

        if metadata is None:
            if inverse:
                metadata = {"transform": "BoxCox"}
            else:
                metadata = {"transform": None}

        else:
            metadata = metadata.copy()

        if not inverse:

            if metadata["transform"] == "BoxCox":
                return R, metadata

            if Lambda is None:
                Lambda = metadata.get("BoxCox_lambda", 0.0)

            if threshold is None:
                threshold = metadata.get("threshold", 0.1)

            zeros = R < threshold

            # Apply Box-Cox transform
            if Lambda == 0.0:
                R[~zeros] = np.log(R[~zeros])
                threshold = np.log(threshold)

            else:
                R[~zeros] = (R[~zeros] ** Lambda - 1) / Lambda
                threshold = (threshold**Lambda - 1) / Lambda

            # Set value for zeros
            if zerovalue is None:
                zerovalue = threshold - 1  # TODO: set to a more meaningful value
            R[zeros] = zerovalue

            metadata["transform"] = "BoxCox"
            metadata["BoxCox_lambda"] = Lambda
            metadata["zerovalue"] = zerovalue
            metadata["threshold"] = threshold

        elif inverse:

            if metadata["transform"] not in ["BoxCox", "log"]:
                return R, metadata

            if Lambda is None:
                Lambda = metadata.pop("BoxCox_lambda", 0.0)
            if threshold is None:
                threshold = metadata.get("threshold", -10.0)
            if zerovalue is None:
                zerovalue = 0.0

            # Apply inverse Box-Cox transform
            if Lambda == 0.0:
                R = np.exp(R)
                threshold = np.exp(threshold)

            else:
                R = np.exp(np.log(Lambda * R + 1) / Lambda)
                threshold = np.exp(np.log(Lambda * threshold + 1) / Lambda)

            R[R < threshold] = zerovalue

            metadata["transform"] = None
            metadata["zerovalue"] = zerovalue
            metadata["threshold"] = threshold

        return R, metadata

    def NQ_transform(self, R, metadata=None, inverse=False, **kwargs):
        """
        The normal quantile transformation as in Bogner et al (2012).
        Zero rain vales are set to zero in norm space.

        共用参数：``R``、``metadata``、``inverse``。

        本方法非复用（特有）参数：
            a: 绘图位置偏移分数，通常在 (0, 1)；默认 0（均匀间距）。
                经 ``kwargs["a"]`` 传入。逆变换不另要 ``a``，但依赖正变换写入
                ``metadata["inqt"]`` 的插值函数。

        Parameters
        ----------
        R: array-like
            Array of any shape to be transformed.
        metadata: dict, optional
            Metadata dictionary containing the transform, zerovalue and threshold
            attributes as described in the documentation of
            :py:mod:`pysteps.io.importers`.
        inverse: bool, optional
            If set to True, it performs the inverse transform. False by default.

        Other Parameters
        ----------------
        a: float, optional
            The offset fraction to be used for plotting positions;
            typically in (0,1).
            The default is 0., that is, it spaces the points evenly in the uniform
            distribution.

        Returns
        -------
        R: array-like
            Array of any shape containing the (back-)transformed units.
        metadata: dict
            The metadata with updated attributes.

        References
        ----------
        Bogner, K., Pappenberger, F., and Cloke, H. L.: Technical Note: The normal
        quantile transformation and its application in a flood forecasting system,
        Hydrol. Earth Syst. Sci., 16, 1085-1094,
        https://doi.org/10.5194/hess-16-1085-2012, 2012.
        """

        # defaults
        a = kwargs.get("a", 0.0)

        R = R.copy()
        shape0 = R.shape
        R = R.ravel().astype(float)
        idxNan = np.isnan(R)
        R_ = R[~idxNan]

        if metadata is None:
            if inverse:
                metadata = {"transform": "NQT"}
            else:
                metadata = {"transform": None}
            metadata["zerovalue"] = np.min(R_)

        else:
            metadata = metadata.copy()

        if not inverse:
            # Plotting positions
            # https://en.wikipedia.org/wiki/Q%E2%80%93Q_plot#Plotting_position
            n = R_.size
            Rpp = ((np.arange(n) + 1 - a) / (n + 1 - 2 * a)).reshape(R_.shape)

            # NQ transform
            Rqn = scipy_stats.norm.ppf(Rpp)
            R__ = np.interp(R_, R_[np.argsort(R_)], Rqn)

            # set zero rain to 0 in norm space
            R__[R[~idxNan] == metadata["zerovalue"]] = 0

            # build inverse transform
            metadata["inqt"] = interp1d(
                Rqn, R_[np.argsort(R_)], bounds_error=False, fill_value=(R_.min(), R_.max())
            )

            metadata["transform"] = "NQT"
            metadata["zerovalue"] = 0
            metadata["threshold"] = R__[R__ > 0].min()

        else:
            f = metadata.pop("inqt")
            R__ = f(R_)
            metadata["transform"] = None
            metadata["zerovalue"] = R__.min()
            metadata["threshold"] = R__[R__ > R__.min()].min()

        R[~idxNan] = R__

        return R.reshape(shape0), metadata

    # 别名：文档/口头常称 Q_transform
    Q_transform = NQ_transform

    def sqrt_transform(self, R, metadata=None, inverse=False, **kwargs):
        """
        Square-root transform.

        共用参数：``R``、``metadata``、``inverse``。

        本方法非复用（特有）参数：无。
            不另收 ``threshold`` / ``zerovalue`` / ``Lambda`` / ``a``；
            正/逆变换只改写 ``metadata`` 里已有的 ``zerovalue``、``threshold``（开方或平方）。

        Parameters
        ----------
        R: array-like
            Array of any shape to be transformed.
        metadata: dict, optional
            Metadata dictionary containing the transform, zerovalue and threshold
            attributes as described in the documentation of
            :py:mod:`pysteps.io.importers`.
        inverse: bool, optional
            If set to True, it performs the inverse transform. False by default.

        Returns
        -------
        R: array-like
            Array of any shape containing the (back-)transformed units.
        metadata: dict
            The metadata with updated attributes.

        """
        _ = kwargs

        R = R.copy()

        if metadata is None:
            if inverse:
                metadata = {"transform": "sqrt"}
            else:
                metadata = {"transform": None}
            metadata["zerovalue"] = np.nan
            metadata["threshold"] = np.nan
        else:
            metadata = metadata.copy()

        if not inverse:
            # sqrt transform
            R = np.sqrt(R)

            metadata["transform"] = "sqrt"
            metadata["zerovalue"] = np.sqrt(metadata["zerovalue"])
            metadata["threshold"] = np.sqrt(metadata["threshold"])
        else:
            # inverse sqrt transform
            R = R**2

            metadata["transform"] = None
            metadata["zerovalue"] = metadata["zerovalue"] ** 2
            metadata["threshold"] = metadata["threshold"] ** 2

        return R, metadata

    def process(
        self,
        R: ArrayLike,
        method: str = "db",
        metadata: Optional[dict] = None,
        inverse: bool = False,
        **kwargs: Any,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """按 ``method`` 执行一次变换。

        Args:
            R: 降水强度数组（任意形状）。
            method: ``db`` / ``box`` / ``nq`` / ``sqrt``。
            metadata: 可选元数据字典；省略时由各变换自行构造。
            inverse: 是否逆变换。
            **kwargs: 各方法非复用（特有）参数，经关键字传入：

                - **db**
                    - ``threshold``: 阈值（与 ``R`` 同单位）。正变换默认 0.1；
                      逆变换默认 -10（dB）。省略时优先用 ``metadata["threshold"]``。
                    - ``zerovalue``: 低于阈值的无雨格点赋值。正变换默认
                      ``threshold_dB - 5``；逆变换默认 0.0。
                - **box**
                    - ``Lambda`` / ``lam``: Box-Cox 幂参数；默认 0（对数）。
                      也可写在 ``metadata["BoxCox_lambda"]``。``<1`` 适合正偏，
                      ``>1`` 适合负偏。
                    - ``threshold``: 阈值（与 ``R`` 同单位）。正变换默认 0.1；
                      逆变换默认 -10。
                    - ``zerovalue``: 无雨格点赋值。正变换默认 ``threshold - 1``；
                      逆变换默认 0.0。
                - **nq**
                    - ``a``: 绘图位置偏移分数，通常在 (0, 1)；默认 0（均匀间距）。
                      逆变换不另要 ``a``，但依赖正变换写入 ``metadata["inqt"]``。
                      （单次 ``process`` 调用对 nq 只做正变换。）
                - **sqrt**
                    - 无特有参数；不收 ``threshold`` / ``zerovalue`` / ``Lambda`` /
                      ``a``。正/逆变换只改写 ``metadata`` 里已有的
                      ``zerovalue``、``threshold``（开方或平方）。

        Returns:
            ``(变换后数组, metadata)``。
        """
        name = str(method or "").strip().lower()
        if name not in self.METHODS:
            raise ValueError("method 无效。可选: %s" % (", ".join(self.METHODS),))
        if name == "nq" and inverse:
            raise ValueError(
                "nq 的逆变换依赖正变换留下的 metadata，单次调用只做正变换"
            )

        array = np.asarray(R, dtype=float)
        shared = {"metadata": metadata, "inverse": bool(inverse)}

        if name == "db":
            return self.dB_transform(
                array,
                threshold=kwargs.get("threshold"),
                zerovalue=kwargs.get("zerovalue"),
                **shared,
            )
        if name == "box":
            return self.boxcox_transform(
                array,
                Lambda=kwargs.get("Lambda", kwargs.get("lam")),
                threshold=kwargs.get("threshold"),
                zerovalue=kwargs.get("zerovalue"),
                **shared,
            )
        if name == "nq":
            return self.NQ_transform(array, a=kwargs.get("a", 0.0), **shared)
        return self.sqrt_transform(array, **shared)
