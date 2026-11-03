#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""站点高差订正。

当模式格点高度与实际站点高度不一致时，可用历史预报与实况估计订正因子，
再乘到新的站点预报上，以减弱高度差带来的系统性偏差。

- ``EstimateDzRescaling``：估计订正因子
- ``ApplyDzRescaling``：将订正因子应用到预报

数据为站点表：每一行对应一个站点在某一时效的记录。
``time`` 为起报时间，``dtime`` 为预报时效（小时），``id`` 为站点编号。
"""
from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd
from meteva_base import set_stadata_coords_dtype
from numpy.polynomial.polynomial import polyfit

from station_height_difference_correction.utils.base_plugin import PostProcessingPlugin
from station_height_difference_correction.src.utils._sta import (
    align_forecast_truth,
    get_neighbour_finding_method_name,
    require_columns,
)


class EstimateDzRescaling(PostProcessingPlugin):
    """估计站点高差订正因子。

    思路简述：格点与站点的高度差记为 ``dz``。用历史预报与实况学习
    「高度差越大，预报相对实况的偏差大致如何变化」，得到斜率 ``s``，
    再对每个站点计算订正因子 ``exp(-s * dz)``。之后把该因子乘到预报上，
    相当于按高度差做缩放订正。

    拟合关系：``ln(预报/实况) ≈ s * dz``。
    订正因子：``scaled_vertical_displacement = clip(exp(-s * dz))``。
    """

    def __init__(
        self,
        forecast_period: float,
        forecast_data_name: str,
        truth_data_name: Optional[str] = None,
        dz_lower_bound: Optional[Union[str, float]] = None,
        dz_upper_bound: Optional[Union[str, float]] = None,
        land_constraint: bool = False,
        similar_altitude: bool = False,
    ) -> None:
        """方法初始化。

        Parameters
        ----------
        forecast_period : float
            代表性预报时效（小时）。历史预报里可以有多个时效；
            输出订正因子表的 ``dtime`` 统一写成该值。
        forecast_data_name : str
            预报表中的要素列名，例如风速列 ``wind_speed``。
        truth_data_name : str, optional
            实况表中的要素列名；不填则与预报要素列名相同。
        dz_lower_bound : float, optional
            允许参与训练的高度差下界（更低/更负的站点不参与学习）。
            不填表示不设下界。计算订正因子时也会按该边界做幅度限制。
        dz_upper_bound : float, optional
            允许参与训练的高度差上界。不填表示不设上界。
        land_constraint : bool
            为 True 时，优先使用「落在陆地上的邻近格点」这类邻点方案。
            可与 ``similar_altitude`` 同时开启。
        similar_altitude : bool
            为 True 时，优先使用「与站点高度更接近的邻近格点」方案。
            可与 ``land_constraint`` 同时开启。
        """
        self.forecast_period = float(forecast_period)
        self.forecast_data_name = forecast_data_name
        self.truth_data_name = (
            forecast_data_name if truth_data_name is None else truth_data_name
        )
        self.dz_lower_bound = (
            -np.inf if dz_lower_bound is None else np.float32(dz_lower_bound)
        )
        self.dz_upper_bound = (
            np.inf if dz_upper_bound is None else np.float32(dz_upper_bound)
        )
        # 只用一次多项式（直线）拟合，保留斜率 s 作为订正强度
        self.polyfit_deg = 1
        self.neighbour_selection_method = get_neighbour_finding_method_name(
            land_constraint=land_constraint, similar_altitude=similar_altitude
        )

    def _extract_dz(self, neighbour: pd.DataFrame) -> pd.DataFrame:
        """取出邻点高度差，并按所选邻点方案筛选。"""
        dz = neighbour.copy()
        if "neighbour_selection_method" in dz.columns:
            mask = (
                dz["neighbour_selection_method"] == self.neighbour_selection_method
            )
            dz = dz.loc[mask].copy()
            if dz.empty:
                raise ValueError(
                    f"neighbour 中无方法为 {self.neighbour_selection_method!r} 的记录"
                )
        return dz

    def _fit_polynomial(
        self,
        forecast_values: np.ndarray,
        truth_values: np.ndarray,
        dz_values: np.ndarray,
    ) -> float:
        """根据预报、实况与高度差学习斜率 ``s``。

        对可用样本拟合 ``ln(预报/实况) ≈ s * dz``，返回斜率 ``s``。
        """
        fc = np.asarray(forecast_values, dtype=float)
        tr = np.asarray(truth_values, dtype=float)
        dz = np.asarray(dz_values, dtype=float)

        # 基本可用：预报与高度差有效，且高度差落在训练上下界内
        base = (
            (fc != 0)
            & (dz >= self.dz_lower_bound)
            & (dz <= self.dz_upper_bound)
            & np.isfinite(fc)
            & np.isfinite(dz)
        )
        valid = base & (tr != 0) & np.isfinite(tr)
        # 实况缺测时仍保留该点，对数误差记为 1.0，避免样本被静默丢弃
        missing_truth = base & ~np.isfinite(tr)

        if not (np.any(valid) or np.any(missing_truth)):
            raise ValueError("拟合样本为空：请检查零值过滤与 dz 上下界")

        log_error_ratio = np.empty(fc.shape, dtype=float)
        log_error_ratio[valid] = np.log(fc[valid] / tr[valid])
        log_error_ratio[missing_truth] = 1.0
        use = valid | missing_truth

        coeffs = polyfit(dz[use], log_error_ratio[use], self.polyfit_deg)
        return float(coeffs[1])

    def _compute_scaled_dz(
        self, scale_factor: float, dz: np.ndarray
    ) -> np.ndarray:
        """由斜率与高度差计算订正因子，并限制在训练边界对应的幅度内。"""
        scaled_dz = np.exp(-1.0 * scale_factor * dz)
        # 用上下界高度差各自算出的因子，确定允许的最小/最大订正幅度
        # （斜率符号变化时，下界高度差不一定对应较小因子）
        scaled_dz_a = np.exp(-1.0 * scale_factor * self.dz_lower_bound)
        scaled_dz_b = np.exp(-1.0 * scale_factor * self.dz_upper_bound)
        scaled_dz_lower = np.amin([scaled_dz_a, scaled_dz_b])
        scaled_dz_upper = np.amax([scaled_dz_a, scaled_dz_b])
        return np.clip(scaled_dz, scaled_dz_lower, scaled_dz_upper)

    def process(
        self,
        forecast: pd.DataFrame,
        truth: pd.DataFrame,
        neighbour: pd.DataFrame,
    ) -> pd.DataFrame:
        """估计各站点的高差订正因子。

        先在「预报、实况、邻点高差三者共有的站点」上学习斜率，
        再把订正因子算到邻点表中的全部站点上，供后续应用步骤使用。

        Parameters
        ----------
        forecast : pandas.DataFrame
            历史站点预报表。需包含站点坐标列、预报要素列，
            以及百分位列 ``percentile``（本方法固定使用 50 分位）。
        truth : pandas.DataFrame
            对应时段的站点实况表。需包含站点坐标列与实况要素列。
        neighbour : pandas.DataFrame
            邻点高差表。至少包含站点编号 ``id`` 与高度差
            ``vertical_displacement``；也可包含邻点方案名称、经纬度。

        Returns
        -------
        pandas.DataFrame
            订正因子站点表。主要字段：
            ``scaled_vertical_displacement``（订正因子）、
            ``dtime``（取初始化时的代表性时效）、
            ``forecast_reference_time_hour``（起报小时，便于应用时匹配）。
        """
        if not isinstance(forecast, pd.DataFrame):
            raise TypeError(f"forecast 期望 DataFrame，得到 {type(forecast)!r}")
        if not isinstance(truth, pd.DataFrame):
            raise TypeError(f"truth 期望 DataFrame，得到 {type(truth)!r}")
        if not isinstance(neighbour, pd.DataFrame):
            raise TypeError(f"neighbour 期望 DataFrame，得到 {type(neighbour)!r}")

        require_columns(forecast, ("level", "time", "dtime", "id", "lon", "lat"))
        require_columns(truth, ("level", "time", "dtime", "id", "lon", "lat"))
        require_columns(neighbour, ("id", "vertical_displacement"))
        require_columns(forecast, (self.forecast_data_name,))
        require_columns(truth, (self.truth_data_name,))

        forecast = forecast.copy()
        truth = truth.copy()
        neighbour = neighbour.copy()

        dz_all = self._extract_dz(neighbour)

        fc_col = self.forecast_data_name
        tr_col = self.truth_data_name
        # 百分位预报只取中位（50），避免不同分位混在一起拟合
        require_columns(forecast, ("percentile",))
        forecast = forecast.loc[forecast["percentile"] == 50.0].copy()
        if forecast.empty:
            raise ValueError("预报中无 percentile=50 的记录")

        # 学习只用三者共有的站点；订正因子后面仍会写到邻点表全部站点
        sites = set(forecast["id"]) & set(truth["id"]) & set(dz_all["id"])
        if not sites:
            raise ValueError("预报、实况与 neighbour 无共同站点 id")
        forecast_train = forecast[forecast["id"].isin(sites)].copy()
        truth_train = truth[truth["id"].isin(sites)].copy()
        dz_train = dz_all[dz_all["id"].isin(sites)].copy()

        # 按「有效时间 = 起报 + 时效」与站点编号对齐预报和实况
        aligned = align_forecast_truth(
            forecast_train,
            truth_train,
            forecast_col=fc_col,
            truth_col=tr_col,
        )
        aligned = aligned.merge(
            dz_train[["id", "vertical_displacement"]], on="id", how="inner"
        )
        if aligned.empty:
            raise ValueError("对齐后训练样本为空")

        scale_factor = self._fit_polynomial(
            aligned["_forecast_value"].to_numpy(dtype=float),
            aligned["_truth_value"].to_numpy(dtype=float),
            aligned["vertical_displacement"].to_numpy(dtype=float),
        )

        frt_hour = int(pd.to_datetime(forecast_train["time"].iloc[0]).hour)
        scaled_values = self._compute_scaled_dz(
            scale_factor,
            dz_all["vertical_displacement"].to_numpy(dtype=float),
        )

        out = pd.DataFrame(
            {
                "level": np.float32(0),
                "time": pd.to_datetime(forecast_train["time"].iloc[0]),
                "dtime": np.int32(self.forecast_period),
                "id": dz_all["id"].to_numpy(),
                "lon": (
                    dz_all["lon"].to_numpy()
                    if "lon" in dz_all.columns
                    else np.nan
                ),
                "lat": (
                    dz_all["lat"].to_numpy()
                    if "lat" in dz_all.columns
                    else np.nan
                ),
                "forecast_reference_time_hour": np.float32(frt_hour),
                "scaled_vertical_displacement": scaled_values.astype(np.float32),
            }
        )
        # 邻点表若无经纬度，则从预报表补齐，便于后续制图或质检
        if out["lon"].isna().all() or out["lat"].isna().all():
            loc = (
                forecast.drop_duplicates("id")[["id", "lon", "lat"]]
                if {"lon", "lat"}.issubset(forecast.columns)
                else None
            )
            if loc is not None:
                out = out.drop(columns=["lon", "lat"]).merge(
                    loc, on="id", how="left"
                )

        return set_stadata_coords_dtype(
            out,
            level_type=np.float32,
            dtime_type=np.int32,
            id_type=np.int32,
            lat_type=np.float32,
            lon_type=np.float32,
            data_type=np.float32,
        )


class ApplyDzRescaling(PostProcessingPlugin):
    """将高差订正因子乘到站点预报上。

    对每个站点、每个时效，找到匹配的订正因子后执行：
    ``订正后预报 = 原预报 × scaled_vertical_displacement``。
    """

    def __init__(
        self,
        forecast_data_name: str,
        frt_hour_leniency: int = 1,
    ) -> None:
        """方法初始化。

        Parameters
        ----------
        forecast_data_name : str
            待订正预报表中的要素列名，例如 ``wind_speed``。
        frt_hour_leniency : int
            起报小时匹配的容差（小时）。例如容差为 1 时，
            会依次尝试完全相同、±1 小时的起报小时。
        """
        self.forecast_data_name = forecast_data_name
        self.frt_hour_leniency = int(frt_hour_leniency)

    def _check_mismatched_sites(
        self, forecast: pd.DataFrame, scaled_dz: pd.DataFrame
    ) -> None:
        """检查预报与订正因子覆盖的站点是否一致。"""
        fc_ids = set(forecast["id"].unique())
        sd_ids = set(scaled_dz["id"].unique())
        if fc_ids != sd_ids:
            mismatched = fc_ids.symmetric_difference(sd_ids)
            raise ValueError(
                "预报与 scaled_vertical_displacement 的站点不一致。"
                f"预报站点数: {len(fc_ids)}，"
                f"scaled_vertical_displacement 站点数: {len(sd_ids)}。"
                f"不一致站点: {set(map(str, mismatched))}。"
            )

    @staticmethod
    def _choose_forecast_period(
        forecast_period: float, scaled_dz_periods: np.ndarray
    ) -> float:
        """为当前预报时效挑选订正因子表中的时效。

        优先取「不早于当前预报时效」的最近一个；若因子时效都更短，则取最长的那个。
        """
        periods = np.sort(np.unique(scaled_dz_periods.astype(float)))
        diffs = periods - float(forecast_period)
        if np.any(diffs >= 0):
            return float(periods[np.argmax(diffs >= 0)])
        return float(periods[-1])

    def _extract_scaled_dz(
        self,
        scaled_dz: pd.DataFrame,
        forecast_period: float,
        frt_hour: int,
    ) -> pd.DataFrame:
        """按时效与起报小时取出对应的订正因子。"""
        chosen_fp = self._choose_forecast_period(
            forecast_period, scaled_dz["dtime"].to_numpy()
        )
        fp_mask = scaled_dz["dtime"].astype(float) == chosen_fp

        # 先尝试完全匹配起报小时，再逐步放宽到容差范围内
        offsets = sorted(
            range(-self.frt_hour_leniency, self.frt_hour_leniency + 1),
            key=abs,
        )
        has_frt = "forecast_reference_time_hour" in scaled_dz.columns
        for offset in offsets:
            hour = (int(frt_hour) + offset) % 24
            if has_frt:
                hour_mask = (
                    scaled_dz["forecast_reference_time_hour"].astype(int) % 24
                    == hour
                )
                extracted = scaled_dz.loc[fp_mask & hour_mask]
            else:
                extracted = scaled_dz.loc[fp_mask]
            if not extracted.empty:
                return extracted.drop_duplicates(subset=["id"], keep="first")

        raise ValueError(
            "未找到合适的 scaled_vertical_displacement："
            f"需要 dtime>={forecast_period}（选用 {chosen_fp}）且 "
            f"forecast_reference_time_hour 接近 {frt_hour}"
            f"（容差 {self.frt_hour_leniency}）。"
        )

    def process(
        self,
        forecast: pd.DataFrame,
        scaled_dz: pd.DataFrame,
    ) -> pd.DataFrame:
        """对站点预报乘以高差订正因子。

        按起报小时与预报时效分组，为每组匹配订正因子后逐站相乘。
        预报与订正因子须覆盖同一批站点。

        Parameters
        ----------
        forecast : pandas.DataFrame
            待订正的站点预报表。需包含站点坐标列与要素列
            ``forecast_data_name``。
        scaled_dz : pandas.DataFrame
            订正因子表。至少包含 ``id``、``dtime``、
            ``scaled_vertical_displacement``；建议包含
            ``forecast_reference_time_hour`` 以便按起报小时匹配。

        Returns
        -------
        pandas.DataFrame
            订正后的站点预报表，结构与输入预报相同，
            要素列已乘上对应订正因子。
        """
        if not isinstance(forecast, pd.DataFrame):
            raise TypeError(f"forecast 期望 DataFrame，得到 {type(forecast)!r}")
        if not isinstance(scaled_dz, pd.DataFrame):
            raise TypeError(f"scaled_dz 期望 DataFrame，得到 {type(scaled_dz)!r}")

        require_columns(forecast, ("level", "time", "dtime", "id", "lon", "lat"))
        require_columns(
            scaled_dz, ("id", "dtime", "scaled_vertical_displacement")
        )
        require_columns(forecast, (self.forecast_data_name,))

        forecast = forecast.copy()
        scaled_dz = scaled_dz.copy()

        self._check_mismatched_sites(forecast, scaled_dz)

        data_col = self.forecast_data_name
        out = forecast.copy()
        values = out[data_col].to_numpy(dtype=float, copy=True)

        frt_hours = pd.to_datetime(out["time"]).dt.hour.to_numpy()
        dtimes = out["dtime"].to_numpy(dtype=float)
        ids = out["id"].to_numpy()

        # 同一时效、同一起报小时共用一套因子，再按站点编号对应相乘
        for fp in np.unique(dtimes):
            for hour in np.unique(frt_hours[dtimes == fp]):
                row_mask = (dtimes == fp) & (frt_hours == hour)
                extracted = self._extract_scaled_dz(
                    scaled_dz, float(fp), int(hour)
                )
                factor_map = extracted.set_index("id")[
                    "scaled_vertical_displacement"
                ]
                factors = (
                    pd.Series(ids[row_mask]).map(factor_map).to_numpy(dtype=float)
                )
                if np.isnan(factors).any():
                    missing = pd.unique(ids[row_mask][np.isnan(factors)])
                    raise ValueError(
                        "部分站点缺少 scaled_vertical_displacement 因子，"
                        f"站点: {missing.tolist()}"
                    )
                values[row_mask] = values[row_mask] * factors

        out[data_col] = values
        return set_stadata_coords_dtype(
            out,
            level_type=np.float32,
            dtime_type=np.int32,
            id_type=np.int32,
            lat_type=np.float32,
            lon_type=np.float32,
            data_type=np.float32,
        )
