#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""从 ``retrieve.qpe`` 迁移来的定量降水估算算法。
共实现八个算法函数：
    "est_rain_rate_z"；
    "est_rain_rate_zpoly"；
    "est_rain_rate_kdp"；
    "est_rain_rate_a"；
    "est_rain_rate_zkdp"；
    "est_rain_rate_za"；
    "est_rain_rate_hydro"；
    "ZtoR"；
统一入口插件类 ``QPEPlugin``，以及各算法独立的 ``EstimateRainRate*`` /
``EstimateZtoR`` 插件类。插件层只负责参数整理与转发，不改变具体算法函数的计算逻辑。

输入为 meteva 经纬度网格；``level`` 维可大于 1，表示多仰角叠在同一 lat/lon 上
（与体扫逐库计算对应，需预处理将各扫网格化后写入 ``level``）。单层网格等价于
``level=1``。对比 Py-ART 单扫结果时可使用 ``radar_qpe_retrieval.cli.grid_prep.select_grid_level`` 取指定层。
"""

from __future__ import annotations

from warnings import warn
from typing import Optional

import meteva_base as meb
import numpy as np
import xarray as xr

from radar_qpe_retrieval.utils.base_plugin import PostProcessingPlugin
from radar_qpe_retrieval.src.utils._freq import get_coeff_ra, get_coeff_rkdp
from radar_qpe_retrieval.src.utils._grid import rebuild_to_meb_griddata


class QPEPlugin(PostProcessingPlugin):
    """QPE 算法统一插件入口。

    本插件用于将多个定量降水估计算法封装为统一调用形式。调用者只需
    通过 ``method`` 指定算法名称，再在 ``process`` 中传入对应的
    meteva_base 网格数据即可。插件层只负责方法分发和输入完整性检查，
    不改变具体算法函数的计算逻辑。

    可选方法
    --------
    z : 调用 ``est_rain_rate_z``，根据反射率和幂律 Z-R 关系估算降水率。
    zpoly : 调用 ``est_rain_rate_zpoly``，根据反射率多项式关系估算降水率。
    kdp : 调用 ``est_rain_rate_kdp``，根据 KDP 估算降水率。
    a : 调用 ``est_rain_rate_a``，根据比衰减估算降水率。
    zkdp : 调用 ``est_rain_rate_zkdp``，融合反射率和 KDP 结果。
    za : 调用 ``est_rain_rate_za``，融合反射率和比衰减结果。
    hydro : 调用 ``est_rain_rate_hydro``，结合水凝物分类估算降水率。
    ztor : 调用 ``ZtoR``，使用 ``Z = aR^b`` 形式转换降水率。

    输入数据对应关系
    ----------------
    z、zpoly、ztor : 需要 ``refl``。
    kdp : 需要 ``kdp``。
    a : 需要 ``att``。
    zkdp : 需要 ``refl`` 和 ``kdp``。
    za : 需要 ``refl`` 和 ``att``。
    hydro : 需要 ``refl``、``att`` 和 ``hydro``。

    常用显式参数说明
    ----------------
    z_alpha, z_beta : Z-R 关系系数，用于 ``z``、``zkdp``、``za`` 和
        ``hydro`` 中的液态降水部分。
    kdp_alpha, kdp_beta : KDP-R 关系系数，用于 ``kdp`` 和 ``zkdp``。
    a_alpha, a_beta : A-R 关系系数，用于 ``a``、``za`` 和 ``hydro``。
    snow_alpha, snow_beta : 冰相或雪相 Z-R 关系系数，用于 ``hydro``。
    ztor_a, ztor_b : ``ZtoR`` 专用系数，对应 ``Z = aR^b``。该公式方向
        与 ``est_rain_rate_z`` 不同，因此不与 ``z_alpha/z_beta`` 混用。
    rr_field : 降水率输出字段名。
    main_field, thresh, thresh_max : 融合算法中的主判据字段、阈值和切换方向。
    mp_factor : ``hydro`` 方法中的混合相修正系数。
    """

    def __init__(
        self,
        method: str,
        model_id_attr: Optional[str] = None,
        z_alpha: float = 0.0376,
        z_beta: float = 0.6112,
        kdp_alpha: Optional[float] = None,
        kdp_beta: Optional[float] = None,
        a_alpha: Optional[float] = None,
        a_beta: Optional[float] = None,
        snow_alpha: float = 0.1,
        snow_beta: float = 0.5,
        ztor_a: float = 300.0,
        ztor_b: float = 1.4,
        rr_field: Optional[str] = None,
        main_field: Optional[str] = None,
        thresh: Optional[float] = None,
        thresh_max: Optional[bool] = None,
        mp_factor: float = 0.6,
    ) -> None:
        """
        初始化 QPE 插件。

        参数
        ----
        method : str
            QPE 方法名称，可选 z、zpoly、kdp、a、zkdp、za、hydro、ztor。
        model_id_attr : str or None, optional
            预留的模式标识属性名，当前 QPE 计算中不直接使用。
        z_alpha, z_beta : float, optional
            Z-R 关系系数。用于 z、zkdp、za、hydro 方法。
        kdp_alpha, kdp_beta : float or None, optional
            KDP-R 关系系数。用于 kdp、zkdp 方法。
        a_alpha, a_beta : float or None, optional
            A-R 关系系数。用于 a、za、hydro 方法。
        snow_alpha, snow_beta : float, optional
            冰相或雪相 Z-R 关系系数。用于 hydro 方法。
        ztor_a, ztor_b : float, optional
            ZtoR 方法中 ``Z = aR^b`` 的专用系数。
        rr_field : str or None, optional
            降水率输出字段名。
        main_field : str or None, optional
            融合算法中的主判据字段。
        thresh, thresh_max : optional
            融合算法中的切换阈值及切换方向。
        mp_factor : float or None, optional
            hydro 方法中的混合相修正系数。
        """
        self.method = self._normalize_method(method)
        self.model_id_attr = model_id_attr
        self.method_kwargs = {}

        if self.method == "z":
            self.method_kwargs = {
                "alpha": z_alpha,
                "beta": z_beta,
                "rr_field": rr_field,
            }
        elif self.method == "zpoly":
            self.method_kwargs = {"rr_field": rr_field}
        elif self.method == "kdp":
            self.method_kwargs = {
                "alpha": kdp_alpha,
                "beta": kdp_beta,
                "rr_field": rr_field,
            }
        elif self.method == "a":
            self.method_kwargs = {
                "alpha": a_alpha,
                "beta": a_beta,
                "rr_field": rr_field,
            }
        elif self.method == "zkdp":
            self.method_kwargs = {
                "alphaz": z_alpha,
                "betaz": z_beta,
                "alphakdp": kdp_alpha,
                "betakdp": kdp_beta,
                "rr_field": rr_field,
                "main_field": main_field,
                "thresh": thresh,
                "thresh_max": thresh_max,
            }
        elif self.method == "za":
            self.method_kwargs = {
                "alphaz": z_alpha,
                "betaz": z_beta,
                "alphaa": a_alpha,
                "betaa": a_beta,
                "rr_field": rr_field,
                "main_field": main_field,
                "thresh": thresh,
                "thresh_max": thresh_max,
            }
        elif self.method == "hydro":
            self.method_kwargs = {
                "alphazr": z_alpha,
                "betazr": z_beta,
                "alphazs": snow_alpha,
                "betazs": snow_beta,
                "alphaa": a_alpha,
                "betaa": a_beta,
                "rr_field": rr_field,
                "mp_factor": mp_factor,
                "main_field": main_field,
                "thresh": thresh,
                "thresh_max": thresh_max,
            }
        elif self.method == "ztor":
            self.method_kwargs = {
                "a": ztor_a,
                "b": ztor_b,
                "save_name": rr_field,
            }

        self.method_kwargs = {
            key: value for key, value in self.method_kwargs.items() if value is not None
        }

    @staticmethod
    def _get_qpe_method_map() -> dict:
        return {
            "z": est_rain_rate_z,
            "zpoly": est_rain_rate_zpoly,
            "kdp": est_rain_rate_kdp,
            "a": est_rain_rate_a,
            "zkdp": est_rain_rate_zkdp,
            "za": est_rain_rate_za,
            "hydro": est_rain_rate_hydro,
            "ztor": ZtoR,
        }

    def process(
        self,
        refl: xr.DataArray | None = None,
        kdp: xr.DataArray | None = None,
        att: xr.DataArray | None = None,
        hydro: xr.DataArray | None = None,
    ) -> xr.DataArray:
        """
        根据方法名称分发到对应的 QPE 算法。

        参数
        ----
        refl : xr.DataArray or None, optional
            反射率网格数据。z、zpoly、zkdp、za、hydro、ztor 方法需要。
        kdp : xr.DataArray or None, optional
            比差分相移率网格数据。kdp、zkdp 方法需要。
        att : xr.DataArray or None, optional
            比衰减网格数据。a、za、hydro 方法需要。
        hydro : xr.DataArray or None, optional
            水凝物分类网格数据。hydro 方法需要。

        返回
        ----
        xr.DataArray
            降水率网格数据。
        """
        # =====================================
        # 方法分发
        #
        # 插件层只负责整理输入并转发给现有算法函数，
        # 不在这里重新实现降水率公式或融合逻辑。
        # =====================================
        if self.method in ("z", "zpoly", "ztor"):
            self._require_input(refl, "refl")
            return self._get_qpe_method_map()[self.method](refl, **self.method_kwargs)

        if self.method == "kdp":
            self._require_input(kdp, "kdp")
            return self._get_qpe_method_map()[self.method](kdp, **self.method_kwargs)

        if self.method == "a":
            self._require_input(att, "att")
            return self._get_qpe_method_map()[self.method](att, **self.method_kwargs)

        if self.method == "zkdp":
            self._require_input(refl, "refl")
            self._require_input(kdp, "kdp")
            return self._get_qpe_method_map()[self.method](refl, kdp, **self.method_kwargs)

        if self.method == "za":
            self._require_input(refl, "refl")
            self._require_input(att, "att")
            return self._get_qpe_method_map()[self.method](refl, att, **self.method_kwargs)

        if self.method == "hydro":
            self._require_input(refl, "refl")
            self._require_input(att, "att")
            self._require_input(hydro, "hydro")
            return self._get_qpe_method_map()[self.method](refl, att, hydro, **self.method_kwargs)

    @staticmethod
    def _normalize_method(method: str) -> str:
        """统一方法名称并检查是否支持。"""
        method_use = method.lower()
        method_map = QPEPlugin._get_qpe_method_map()
        if method_use not in method_map:
            supported = ", ".join(sorted(method_map))
            raise ValueError(f"Unsupported QPE method '{method}'. Supported methods: {supported}")
        return method_use

    @staticmethod
    def _require_input(grid_data, input_name: str) -> None:
        """检查当前方法所需输入是否提供。"""
        if grid_data is None:
            raise ValueError(f"QPE method requires input '{input_name}'")


class EstimateRainRateZ(PostProcessingPlugin):
    """反射率 Z-R 降水率估算插件。

    封装 ``est_rain_rate_z``，根据 dBZ 反射率网格和幂律 Z-R 关系估算降水率。

    输入
    ----
    refl : xr.DataArray
        meteva_base 反射率网格，单位 dBZ。

    初始化参数
    ----------
    alpha, beta : float, optional
        Z-R 关系系数。
    rr_field : str or None, optional
        输出降水率字段名。
    """

    def __init__(self, alpha: float = 0.0376, beta: float = 0.6112, rr_field: str | None = None) -> None:
        self.method_kwargs = {
            key: value
            for key, value in {
                "alpha": alpha,
                "beta": beta,
                "rr_field": rr_field,
            }.items()
            if value is not None
        }

    def process(self, refl: xr.DataArray) -> xr.DataArray:
        return est_rain_rate_z(refl, **self.method_kwargs)


class EstimateRainRateZPoly(PostProcessingPlugin):
    """反射率多项式 Z-R 降水率估算插件。

    封装 ``est_rain_rate_zpoly``，使用反射率四次多项式经验关系估算降水率。

    输入
    ----
    refl : xr.DataArray
        meteva_base 反射率网格，单位 dBZ。

    初始化参数
    ----------
    rr_field : str or None, optional
        输出降水率字段名。
    """

    def __init__(self, rr_field: str | None = None) -> None:
        self.method_kwargs = {
            key: value for key, value in {"rr_field": rr_field}.items() if value is not None
        }

    def process(self, refl: xr.DataArray) -> xr.DataArray:
        return est_rain_rate_zpoly(refl, **self.method_kwargs)


class EstimateRainRateKdp(PostProcessingPlugin):
    """KDP 降水率估算插件。

    封装 ``est_rain_rate_kdp``，根据比差分相移率网格估算降水率。
    ``alpha``、``beta`` 未指定时按输入网格 ``frequency`` 属性选择频段默认系数。

    输入
    ----
    kdp : xr.DataArray
        meteva_base KDP 网格。

    初始化参数
    ----------
    alpha, beta : float or None, optional
        KDP-R 关系系数。
    rr_field : str or None, optional
        输出降水率字段名。
    """

    def __init__(self, alpha=None, beta=None, rr_field: str | None = None) -> None:
        self.method_kwargs = {
            key: value
            for key, value in {
                "alpha": alpha,
                "beta": beta,
                "rr_field": rr_field,
            }.items()
            if value is not None
        }

    def process(self, kdp: xr.DataArray) -> xr.DataArray:
        return est_rain_rate_kdp(kdp, **self.method_kwargs)


class EstimateRainRateA(PostProcessingPlugin):
    """比衰减降水率估算插件。

    封装 ``est_rain_rate_a``，根据比衰减网格估算降水率。
    ``alpha``、``beta`` 未指定时按输入网格 ``frequency`` 属性选择频段默认系数。

    输入
    ----
    att : xr.DataArray
        meteva_base 比衰减网格。

    初始化参数
    ----------
    alpha, beta : float or None, optional
        A-R 关系系数。
    rr_field : str or None, optional
        输出降水率字段名。
    """

    def __init__(self, alpha=None, beta=None, rr_field: str | None = None) -> None:
        self.method_kwargs = {
            key: value
            for key, value in {
                "alpha": alpha,
                "beta": beta,
                "rr_field": rr_field,
            }.items()
            if value is not None
        }

    def process(self, att: xr.DataArray) -> xr.DataArray:
        return est_rain_rate_a(att, **self.method_kwargs)


class EstimateRainRateZKdp(PostProcessingPlugin):
    """反射率 + KDP 融合降水率估算插件。

    封装 ``est_rain_rate_zkdp``，先分别计算 R(Z) 与 R(KDP)，再按主判据字段与阈值融合。

    输入
    ----
    refl, kdp : xr.DataArray
        反射率（dBZ）与 KDP 网格，须具有相同经纬度坐标。

    初始化参数
    ----------
    alphaz, betaz : float, optional
        R(Z) 关系系数。
    alphakdp, betakdp : float or None, optional
        R(KDP) 关系系数。
    rr_field : str or None, optional
        输出降水率字段名。
    main_field : str or None, optional
        主判据字段，可选 ``refl`` 或 ``kdp``。
    thresh : float or None, optional
        切换阈值。
    thresh_max : bool, optional
        为 ``True`` 时主关系式值大于阈值则切换为次要关系式结果。
    """

    def __init__(
        self,
        alphaz: float = 0.0376,
        betaz: float = 0.6112,
        alphakdp=None,
        betakdp=None,
        rr_field: str | None = None,
        main_field=None,
        thresh=None,
        thresh_max: bool = True,
    ) -> None:
        self.method_kwargs = {
            key: value
            for key, value in {
                "alphaz": alphaz,
                "betaz": betaz,
                "alphakdp": alphakdp,
                "betakdp": betakdp,
                "rr_field": rr_field,
                "main_field": main_field,
                "thresh": thresh,
                "thresh_max": thresh_max,
            }.items()
            if value is not None
        }

    def process(self, refl: xr.DataArray, kdp: xr.DataArray) -> xr.DataArray:
        return est_rain_rate_zkdp(refl, kdp, **self.method_kwargs)


class EstimateRainRateZA(PostProcessingPlugin):
    """反射率 + 比衰减融合降水率估算插件。

    封装 ``est_rain_rate_za``，先分别计算 R(Z) 与 R(A)，再按主判据字段与阈值融合。

    输入
    ----
    refl, att : xr.DataArray
        反射率（dBZ）与比衰减网格，须具有相同经纬度坐标。

    初始化参数
    ----------
    alphaz, betaz : float, optional
        R(Z) 关系系数。
    alphaa, betaa : float or None, optional
        R(A) 关系系数。
    rr_field : str or None, optional
        输出降水率字段名。
    main_field : str or None, optional
        主判据字段，可选 ``refl`` 或 ``att``。
    thresh : float or None, optional
        切换阈值。
    thresh_max : bool, optional
        为 ``True`` 时主关系式值大于阈值则切换为次要关系式结果。
    """

    def __init__(
        self,
        alphaz: float = 0.0376,
        betaz: float = 0.6112,
        alphaa=None,
        betaa=None,
        rr_field: str | None = None,
        main_field=None,
        thresh=None,
        thresh_max: bool = False,
    ) -> None:
        self.method_kwargs = {
            key: value
            for key, value in {
                "alphaz": alphaz,
                "betaz": betaz,
                "alphaa": alphaa,
                "betaa": betaa,
                "rr_field": rr_field,
                "main_field": main_field,
                "thresh": thresh,
                "thresh_max": thresh_max,
            }.items()
            if value is not None
        }

    def process(self, refl: xr.DataArray, att: xr.DataArray) -> xr.DataArray:
        return est_rain_rate_za(refl, att, **self.method_kwargs)


class EstimateRainRateHydro(PostProcessingPlugin):
    """水凝物分类降水率估算插件。

    封装 ``est_rain_rate_hydro``，结合反射率、比衰减与水凝物分类结果估算降水率。

    输入
    ----
    refl, att, hydro : xr.DataArray
        反射率、比衰减与水凝物分类网格，须具有相同经纬度坐标。

    初始化参数
    ----------
    alphazr, betazr : float, optional
        液态降水 R(Z) 系数。
    alphazs, betazs : float, optional
        冰相/雪相 R(Z) 系数。
    alphaa, betaa : float or None, optional
        R(A) 系数。
    rr_field : str or None, optional
        输出降水率字段名。
    mp_factor : float, optional
        湿雪、大冰雹类别的混合相修正系数。
    main_field, thresh, thresh_max : optional
        雨区 R(Z) 与 R(A) 融合判据，含义同 ``est_rain_rate_za``。
    """

    def __init__(
        self,
        alphazr: float = 0.0376,
        betazr: float = 0.6112,
        alphazs: float = 0.1,
        betazs: float = 0.5,
        alphaa=None,
        betaa=None,
        rr_field: str | None = None,
        mp_factor: float = 0.6,
        main_field=None,
        thresh=None,
        thresh_max: bool = False,
    ) -> None:
        self.method_kwargs = {
            key: value
            for key, value in {
                "alphazr": alphazr,
                "betazr": betazr,
                "alphazs": alphazs,
                "betazs": betazs,
                "alphaa": alphaa,
                "betaa": betaa,
                "rr_field": rr_field,
                "mp_factor": mp_factor,
                "main_field": main_field,
                "thresh": thresh,
                "thresh_max": thresh_max,
            }.items()
            if value is not None
        }

    def process(self, refl: xr.DataArray, att: xr.DataArray, hydro: xr.DataArray) -> xr.DataArray:
        return est_rain_rate_hydro(refl, att, hydro, **self.method_kwargs)


class EstimateZtoR(PostProcessingPlugin):
    """经典 Z = aR^b 降水率转换插件。

    封装 ``ZtoR``，使用 NWS 风格的 ``Z = aR^b`` 关系由反射率反算降水率。
    公式方向与 ``est_rain_rate_z`` 的 R(Z) 幂律不同，系数参数独立。

    输入
    ----
    refl : xr.DataArray
        meteva_base 反射率网格，单位 dBZ。

    初始化参数
    ----------
    a, b : float, optional
        ``Z = aR^b`` 关系系数。
    save_name : str, optional
        输出降水率网格名称。
    """

    def __init__(self, a: float = 300.0, b: float = 1.4, save_name: str = "NWS_primary_prate") -> None:
        self.method_kwargs = {
            key: value
            for key, value in {
                "a": a,
                "b": b,
                "save_name": save_name,
            }.items()
            if value is not None
        }

    def process(self, refl: xr.DataArray) -> xr.DataArray:
        return ZtoR(refl, **self.method_kwargs)


def est_rain_rate_z(
    refl: xr.DataArray,
    alpha: float = 0.0376,
    beta: float = 0.6112,
    rr_field: str | None = None,
) -> xr.DataArray:
    """
    根据反射率网格估算降水率。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格，单位 dBZ；``level`` 维可为多仰角。
    alpha, beta : float, optional
        Z-R 关系式系数。
    rr_field : str or None, optional
        输出降水率字段名称。未给定时使用默认名称。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    reflectivity_grid = meb.checkout_griddata(refl, valid_val=(-200.0, 200.0, np.nan))

    # 先将 dBZ 转为线性 Z，再套用幂律 Z-R 关系式。
    refl_data = reflectivity_grid.values
    rain_rate_data = alpha * np.power(
        np.power(10.0, 0.1 * refl_data),
        beta,
    )

    output_name = "radar_estimated_rain_rate" if rr_field is None else rr_field
    return rebuild_to_meb_griddata(
        rain_rate_data,
        reflectivity_grid,
        name=output_name,
        long_name="rain rate estimated from reflectivity",
        extra_attrs={
            "qpe_method": "z",
            "alpha": float(alpha),
            "beta": float(beta),
        },
    )


def est_rain_rate_zpoly(
    refl: xr.DataArray,
    rr_field: str | None = None,
) -> xr.DataArray:
    """
    根据反射率网格使用多项式 Z-R 关系估算降水率。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格数据，单位 dBZ。
    rr_field : str or None, optional
        输出降水率字段名称。未给定时使用默认名称。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    reflectivity_grid = meb.checkout_griddata(refl, valid_val=(-200.0, 200.0, np.nan))

    refl_data = reflectivity_grid.values
    refl2 = refl_data * refl_data
    refl3 = refl_data * refl2
    refl4 = refl_data * refl3

    # 使用反射率多项式经验关系估算降水率。
    rain_rate_data = np.power(
        10.0,
        -2.3
        + 0.17 * refl_data
        - 5.1e-3 * refl2
        + 9.8e-5 * refl3
        - 6e-7 * refl4,
    )

    output_name = "radar_estimated_rain_rate" if rr_field is None else rr_field
    return rebuild_to_meb_griddata(
        rain_rate_data,
        reflectivity_grid,
        name=output_name,
        long_name="rain rate estimated from polynomial reflectivity relation",
        extra_attrs={"qpe_method": "zpoly"},
    )


def est_rain_rate_kdp(
    kdp: xr.DataArray,
    alpha=None,
    beta=None,
    rr_field: str | None = None,
) -> xr.DataArray:
    """
    根据 KDP 网格估算降水率。

    参数
    ----
    kdp : xr.DataArray
        meteva_base KDP 网格数据。
    alpha, beta : float, optional
        KDP-R 关系式系数。未给定时按频段取默认值。
    rr_field : str or None, optional
        输出降水率字段名称。未给定时使用默认名称。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    kdp_grid = meb.checkout_griddata(kdp)

    if alpha is None or beta is None:
        if ("frequency" in kdp_grid.attrs) and (kdp_grid.attrs.get("frequency") is not None):
            alpha, beta = get_coeff_rkdp(kdp_grid.attrs.get("frequency"))
        else:
            alpha, beta = get_coeff_rkdp(5.6e9)  #无法获取雷达频率时使用C频段系数
            warn(
                "Radar frequency unknown. "
                "Default coefficients for C band will be applied."
            )

    kdp_data = kdp_grid.values.copy()

    # KDP 小于 0 时不再直接参与降水率估算。
    kdp_data[kdp_data < 0] = 0.0
    rain_rate_data = alpha * np.power(kdp_data, beta)

    output_name = "radar_estimated_rain_rate" if rr_field is None else rr_field
    return rebuild_to_meb_griddata(
        rain_rate_data,
        kdp_grid,
        name=output_name,
        long_name="rain rate estimated from specific differential phase",
        extra_attrs={
            "qpe_method": "kdp",
            "alpha": float(alpha),
            "beta": float(beta),
        },
    )


def est_rain_rate_a(
    att: xr.DataArray,
    alpha=None,
    beta=None,
    rr_field: str | None = None,
) -> xr.DataArray:
    """
    根据比衰减网格估算降水率。

    参数
    ----
    att : xr.DataArray
        meteva_base 比衰减网格数据。
    alpha, beta : float, optional
        A-R 关系式系数。未给定时按频段取默认值。
    rr_field : str or None, optional
        输出降水率字段名称。未给定时使用默认名称。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    att_grid = meb.checkout_griddata(att)

    if alpha is None or beta is None:
        if ("frequency" in att_grid.attrs) and (att_grid.attrs.get("frequency") is not None):
            alpha, beta = get_coeff_ra(att_grid.attrs.get("frequency"))
        else:
            alpha, beta = get_coeff_ra(5.6e9)  #无法获取雷达频率时使用C频段系数
            warn(
                "Radar frequency unknown. "
                "Default coefficients for C band will be applied."
            )

    att_data = att_grid.values
    rain_rate_data = alpha * np.power(att_data, beta)

    output_name = "radar_estimated_rain_rate" if rr_field is None else rr_field
    return rebuild_to_meb_griddata(
        rain_rate_data,
        att_grid,
        name=output_name,
        long_name="rain rate estimated from specific attenuation",
        extra_attrs={
            "qpe_method": "a",
            "alpha": float(alpha),
            "beta": float(beta),
        },
    )


def est_rain_rate_zkdp(
    refl: xr.DataArray,
    kdp: xr.DataArray,
    alphaz: float = 0.0376,
    betaz: float = 0.6112,
    alphakdp=None,
    betakdp=None,
    rr_field: str | None = None,
    main_field=None,
    thresh=None,
    thresh_max: bool = True,
) -> xr.DataArray:
    """
    融合反射率和 KDP 估算降水率。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格数据，单位 dBZ。
    kdp : xr.DataArray
        meteva_base KDP 网格数据。
    alphaz, betaz : float, optional
        R(Z) 关系式系数。
    alphakdp, betakdp : float or None, optional
        R(KDP) 关系式系数。未给定时按频段取默认值。
    rr_field : str or None, optional
        输出降水率字段名称。未给定时使用默认名称。
    main_field : str, optional
        主判据字段，可选 refl 或 kdp。
    thresh : float, optional
        阈值。满足条件的格点使用另一种关系式结果。
    thresh_max : bool, optional
        是否使用“大于阈值时切换”的方式。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    refl_grid = meb.checkout_griddata(refl, valid_val=(-200.0, 200.0, np.nan))
    kdp_grid = meb.checkout_griddata(kdp)
    if not meb.checkout_griddata_same_coords([refl_grid, kdp_grid]):
        raise ValueError("refl and kdp grid coordinates must be same")

    rain_z = est_rain_rate_z(refl_grid, alpha=alphaz, beta=betaz)
    rain_kdp = est_rain_rate_kdp(
        kdp_grid,
        alpha=alphakdp,
        beta=betakdp,
    )

    # =====================================
    # 融合策略说明
    #
    # 先分别计算 R(Z) 和 R(KDP)，再按主判据字段和阈值决定
    # 哪些格点切换到另一套关系式结果。
    # =====================================
    refl_name = refl_grid.name if isinstance(refl_grid.name, str) else None
    kdp_name = kdp_grid.name if isinstance(kdp_grid.name, str) else None

    if main_field in (None, "refl", "reflectivity", refl_name):
        rain_main = rain_z.copy()
        rain_secondary = rain_kdp
    elif main_field in ("kdp", "specific_differential_phase", kdp_name):
        rain_main = rain_kdp.copy()
        rain_secondary = rain_z
    else:
        rain_main = rain_z.copy()
        rain_secondary = rain_kdp
        thresh = 40.0
        thresh_max = True
        warn(f"Unknown main_field '{main_field}'. Using refl with threshold {thresh}.")

    main_values = rain_main.values
    secondary_values = rain_secondary.values

    if thresh_max:
        is_secondary = main_values > thresh
    else:
        is_secondary = main_values < thresh

    # =====================================
    # 融合缺测补齐
    #
    # 原始 Py-ART 使用的是 MaskedArray。布尔替换时，
    # 若主关系式结果被掩码而次关系式有效，次关系式可能会
    # 直接补入这些格点。这里统一用显式逻辑复现这一行为，
    # 以避免在 NaN 语义下丢失本应由次关系式补齐的有效格点。
    # =====================================
    fill_from_secondary = np.isnan(main_values) & np.isfinite(secondary_values)
    main_values[fill_from_secondary] = secondary_values[fill_from_secondary]

    # 满足切换条件的格点使用次要关系式结果。
    main_values[is_secondary] = secondary_values[is_secondary]

    output_name = "radar_estimated_rain_rate" if rr_field is None else rr_field
    return rebuild_to_meb_griddata(
        main_values,
        refl_grid,
        name=output_name,
        long_name="rain rate estimated from blended reflectivity and kdp",
        extra_attrs={
            "qpe_method": "zkdp",
            "alphaz": float(alphaz),
            "betaz": float(betaz),
            "alphakdp": rain_kdp.attrs.get("alpha"),
            "betakdp": rain_kdp.attrs.get("beta"),
            "main_field": (
                "refl"
                if main_field in (None, "refl", "reflectivity", refl_name)
                else str(main_field)
            ),
            "thresh": None if thresh is None else float(thresh),
            "thresh_max": bool(thresh_max),
        },
    )


def est_rain_rate_za(
    refl: xr.DataArray,
    att: xr.DataArray,
    alphaz: float = 0.0376,
    betaz: float = 0.6112,
    alphaa=None,
    betaa=None,
    rr_field: str | None = None,
    main_field=None,
    thresh=None,
    thresh_max: bool = False,
) -> xr.DataArray:
    """
    融合反射率和比衰减估算降水率。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格数据，单位 dBZ。
    att : xr.DataArray
        meteva_base 比衰减网格数据。
    alphaz, betaz : float, optional
        R(Z) 关系式系数。
    alphaa, betaa : float or None, optional
        R(A) 关系式系数。未给定时按频段取默认值。
    rr_field : str or None, optional
        输出降水率字段名称。未给定时使用默认名称。
    main_field : str, optional
        主判据字段，可选 refl 或 att。
    thresh : float, optional
        阈值。满足条件的格点使用另一种关系式结果。
    thresh_max : bool, optional
        是否使用“大于阈值时切换”的方式。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    refl_grid = meb.checkout_griddata(refl, valid_val=(-200.0, 200.0, np.nan))
    att_grid = meb.checkout_griddata(att)
    if not meb.checkout_griddata_same_coords([refl_grid, att_grid]):
        raise ValueError("refl and att grid coordinates must be same")

    rain_z = est_rain_rate_z(refl_grid, alpha=alphaz, beta=betaz)
    rain_a = est_rain_rate_a(
        att_grid,
        alpha=alphaa,
        beta=betaa,
    )

    # =====================================
    # 融合策略说明
    #
    # ZA 融合与 ZKDP 的实现方式一致，
    # 只是次要关系式换成了 R(A)。
    # =====================================
    refl_name = refl_grid.name if isinstance(refl_grid.name, str) else None
    att_name = att_grid.name if isinstance(att_grid.name, str) else None

    if main_field in ("refl", "reflectivity", refl_name):
        rain_main = rain_z
        rain_secondary = rain_a
    elif main_field in ("att", "a", "specific_attenuation", att_name):
        rain_main = rain_a
        rain_secondary = rain_z
    elif main_field is None:
        rain_main = rain_a
        rain_secondary = rain_z
    else:
        rain_main = rain_a
        rain_secondary = rain_z
        thresh = 0.04
        thresh_max = False
        warn(f"Unknown main_field '{main_field}'. Using att with threshold {thresh}.")

    main_values = rain_main.values
    secondary_values = rain_secondary.values

    if thresh_max:
        is_secondary = main_values > thresh
    else:
        is_secondary = main_values < thresh

    # 与 ZKDP 一致：在 NaN 语义下显式补齐主关系式缺测格点。
    fill_from_secondary = np.isnan(main_values) & np.isfinite(secondary_values)
    main_values[fill_from_secondary] = secondary_values[fill_from_secondary]

    main_values[is_secondary] = secondary_values[is_secondary]

    output_name = "radar_estimated_rain_rate" if rr_field is None else rr_field
    return rebuild_to_meb_griddata(
        main_values,
        refl_grid,
        name=output_name,
        long_name="rain rate estimated from blended reflectivity and attenuation",
        extra_attrs={
            "qpe_method": "za",
            "alphaz": float(alphaz),
            "betaz": float(betaz),
            "alphaa": rain_a.attrs.get("alpha"),
            "betaa": rain_a.attrs.get("beta"),
            "main_field": (
                "att"
                if main_field in (None, "att", "a", "specific_attenuation", att_name)
                else str(main_field)
            ),
            "thresh": None if thresh is None else float(thresh),
            "thresh_max": bool(thresh_max),
        },
    )


def est_rain_rate_hydro(
    refl: xr.DataArray,
    att: xr.DataArray,
    hydro: xr.DataArray,
    alphazr: float = 0.0376,
    betazr: float = 0.6112,
    alphazs: float = 0.1,
    betazs: float = 0.5,
    alphaa=None,
    betaa=None,
    rr_field: str | None = None,
    mp_factor: float = 0.6,
    main_field=None,
    thresh=None,
    thresh_max: bool = False,
) -> xr.DataArray:
    """
    根据水凝物分类结果估算降水率。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格数据，单位 dBZ。
    att : xr.DataArray
        meteva_base 比衰减网格数据。
    hydro : xr.DataArray
        meteva_base 水凝物分类网格数据。
    alphazr, betazr : float, optional
        液态降水 R(Z) 关系式系数。
    alphazs, betazs : float, optional
        冰相或雪相 R(Z) 关系式系数。
    alphaa, betaa : float or None, optional
        R(A) 关系式系数。未给定时按频段取默认值。
    rr_field : str or None, optional
        输出降水率字段名称。未给定时使用默认名称。
    mp_factor : float, optional
        混合相修正系数。
    main_field : str, optional
        雨区主判据字段，可选 refl 或 att。
    thresh : float, optional
        雨区融合阈值。
    thresh_max : bool, optional
        是否使用“大于阈值时切换”的方式。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    refl_grid = meb.checkout_griddata(refl, valid_val=(-200.0, 200.0, np.nan))
    att_grid = meb.checkout_griddata(att)
    hydro_grid = meb.checkout_griddata(hydro, valid_val=(0.0, 20.0, np.nan))
    if not meb.checkout_griddata_same_coords([refl_grid, att_grid, hydro_grid]):
        raise ValueError("refl, att and hydro grid coordinates must be same")

    hydroclass = hydro_grid.values
    is_ds = hydroclass == 1
    is_cr = hydroclass == 2
    is_lr = hydroclass == 3
    is_gr = hydroclass == 4
    is_rn = hydroclass == 5
    is_vi = hydroclass == 6
    is_ws = hydroclass == 7
    is_mh = hydroclass == 8
    is_ih = hydroclass == 9

    rain_z = est_rain_rate_z(refl_grid, alpha=alphazr, beta=betazr)
    snow_z = est_rain_rate_z(refl_grid, alpha=alphazs, beta=betazs)
    rain_a = est_rain_rate_a(
        att_grid,
        alpha=alphaa,
        beta=betaa,
    )

    # =====================================
    # 雨区主关系式选择
    #
    # 对液态降水区域，先按照主判据在 R(Z) 与 R(A) 之间做一次融合，
    # 后面再根据水凝物类别决定每类使用哪种结果。
    # =====================================
    refl_name = refl_grid.name if isinstance(refl_grid.name, str) else None
    att_name = att_grid.name if isinstance(att_grid.name, str) else None

    if main_field in ("refl", "reflectivity", refl_name):
        rain_main = rain_z.copy()
        rain_secondary = rain_a
    elif main_field in ("att", "a", "specific_attenuation", att_name):
        rain_main = rain_a.copy()
        rain_secondary = rain_z
    elif main_field is None:
        rain_main = rain_a.copy()
        rain_secondary = rain_z
    else:
        rain_main = rain_a.copy()
        rain_secondary = rain_z
        thresh = 0.04
        thresh_max = False
        warn(f"Unknown main_field '{main_field}'. Using att with threshold {thresh}.")

    main_values = rain_main.values
    secondary_values = rain_secondary.values

    if thresh_max:
        is_secondary = main_values > thresh
    else:
        is_secondary = main_values < thresh

    # 与 ZKDP / ZA 一致：在 NaN 语义下显式补齐主关系式缺测格点。
    fill_from_secondary = np.isnan(main_values) & np.isfinite(secondary_values)
    main_values[fill_from_secondary] = secondary_values[fill_from_secondary]

    main_values[is_secondary] = secondary_values[is_secondary]

    rr_data = np.full(hydroclass.shape, np.nan, dtype=np.float32)

    # =====================================
    # 分类结果映射
    #
    # 冰相或雪相类别使用 snow_z。
    # 液态降水类别使用融合后的 rain_main。
    # 湿雪和大冰雹乘以混合相修正系数 mp_factor。
    # =====================================
    rr_data[is_ds] = snow_z.values[is_ds]
    rr_data[is_cr] = snow_z.values[is_cr]
    rr_data[is_vi] = snow_z.values[is_vi]
    rr_data[is_gr] = snow_z.values[is_gr]
    rr_data[is_ih] = snow_z.values[is_ih]

    rr_data[is_lr] = rain_main.values[is_lr]
    rr_data[is_rn] = rain_main.values[is_rn]

    rr_data[is_ws] = mp_factor * rain_z.values[is_ws]
    rr_data[is_mh] = mp_factor * rain_z.values[is_mh]

    output_name = "radar_estimated_rain_rate" if rr_field is None else rr_field
    return rebuild_to_meb_griddata(
        rr_data,
        refl_grid,
        name=output_name,
        long_name="rain rate estimated from hydrometeor classification",
        extra_attrs={
            "qpe_method": "hydro",
            "alphazr": float(alphazr),
            "betazr": float(betazr),
            "alphazs": float(alphazs),
            "betazs": float(betazs),
            "mp_factor": float(mp_factor),
        },
    )


def ZtoR(
    refl: xr.DataArray,
    a: float = 300.0,
    b: float = 1.4,
    save_name: str = "NWS_primary_prate",
) -> xr.DataArray:
    """
    根据经典 Z-R 关系计算降水率。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格数据，单位 dBZ。
    a, b : float, optional
        Z = aR^b 关系式系数。
    save_name : str, optional
        输出降水率网格的名称。

    返回
    ----
    xr.DataArray
        降水率网格数据，单位 mm/h。
    """
    reflectivity_grid = meb.checkout_griddata(refl, valid_val=(-200.0, 200.0, np.nan))

    refl_data = reflectivity_grid.values
    ref_linear = np.power(10.0, refl_data / 10.0)
    rain_rate_data = np.power(ref_linear / a, 1.0 / b)

    return rebuild_to_meb_griddata(
        rain_rate_data,
        reflectivity_grid,
        name=save_name,
        long_name="NWS primary precipitation rate",
        extra_attrs={
            "qpe_method": "ztor",
            "a": float(a),
            "b": float(b),
        },
    )


__all__ = [
    "QPEPlugin",
    "EstimateRainRateZ",
    "EstimateRainRateZPoly",
    "EstimateRainRateKdp",
    "EstimateRainRateA",
    "EstimateRainRateZKdp",
    "EstimateRainRateZa",
    "EstimateRainRateHydro",
    "EstimateZtoR",
    "est_rain_rate_z",
    "est_rain_rate_zpoly",
    "est_rain_rate_kdp",
    "est_rain_rate_a",
    "est_rain_rate_zkdp",
    "est_rain_rate_za",
    "est_rain_rate_hydro",
    "ZtoR",
]
