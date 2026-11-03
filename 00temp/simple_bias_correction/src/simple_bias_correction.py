#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""简单加性偏差计算与订正插件（由 IMPROVER ``simple_bias_correction`` 迁移）。

已复刻：

- ``evaluate_additive_error`` / ``CalculateForecastBias``
- ``apply_additive_correction`` / ``ApplyBiasCorrection``

输入以 ``xarray.DataArray`` 为主（meb 六维：``member, level, time, dtime, lat, lon``；
起报对应 ``time``，预测周期对应 ``dtime``）。误差/订正函数亦支持普通
``numpy.ndarray``。缺测统一用 ``NaN`` 表示。
"""
from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import numpy.ma as ma
import xarray as xr
import meteva_base as meb

from simple_bias_correction.utils.base_plugin import BasePlugin
from simple_bias_correction.src.utils._calibration_utilities import (
    _as_datetime64_scalar,
    add_warning_comment,
    align_operand_units_to_reference,
    check_forecast_consistency,
    clip_dataarray,
    create_unified_time_values,
    ensure_meb6d,
    filter_non_matching_by_valid_time,
    generate_mandatory_attributes,
    get_frt_hours,
    has_time_bounds,
    is_probability_named_dataarray,
    split_forecasts_and_bias,
    strip_placeholder_time_bounds,
)

__all__ = [
    "evaluate_additive_error",
    "apply_additive_correction",
    "CalculateForecastBias",
    "ApplyBiasCorrection",
]


def evaluate_additive_error(
    forecasts: Union[xr.DataArray, np.ndarray],
    truths: Union[xr.DataArray, np.ndarray],
    collapse_dim: str,
) -> np.ndarray:
    """计算平均加性误差（error = forecast - truth）。

    参数
    ----------
    forecasts :
        历史预报场（``DataArray`` 或 ``ndarray``）。
    truths :
        对应实况场。
    collapse_dim :
        求平均所沿的维度名；仅当输入为 DataArray 且该维存在时生效。
        对纯 ndarray，若 ``collapse_dim == "time"`` 且数组至少 3 维，
        则对第 0 维求平均（约定时间维在最前）。

    返回
    -------
    np.ndarray
        平均加性误差；缺测位置为 NaN（两侧缺测取并集后对有效点求平均）。
    """
    time_axis = None
    if isinstance(forecasts, xr.DataArray) and isinstance(truths, xr.DataArray):
        # 仅按维度对齐数值；标量坐标（如 dtime）允许不同
        if forecasts.shape != truths.shape or list(forecasts.dims) != list(truths.dims):
            truths = truths.transpose(*forecasts.dims)
            if forecasts.shape != truths.shape:
                raise ValueError(
                    f"forecasts 与 truths 形状不一致: {forecasts.shape} vs {truths.shape}"
                )
        if collapse_dim in forecasts.dims:
            time_axis = forecasts.get_axis_num(collapse_dim)
        # 实况换算到预报单位后再求差；meb 与 Iris 官方场均为 float32，
        # 在 float32 上求平均，避免 float64 均值再压回 float32 带来的多日舍入差
        fc_arr = np.asarray(forecasts.values, dtype=np.float32)
        tr_arr = np.asarray(
            align_operand_units_to_reference(truths, forecasts), dtype=np.float32
        )
        fc_data = ma.array(fc_arr, mask=np.isnan(fc_arr))
        tr_data = ma.array(tr_arr, mask=np.isnan(tr_arr))
    elif isinstance(forecasts, np.ndarray) and isinstance(truths, np.ndarray):
        if forecasts.shape != truths.shape:
            raise ValueError(
                f"forecasts 与 truths 形状不一致: {forecasts.shape} vs {truths.shape}"
            )
        # 纯数组约定：collapse_dim 为 time 时对 leading 维求平均
        if collapse_dim == "time" and forecasts.ndim >= 3:
            time_axis = 0
        fc_arr = np.asarray(forecasts, dtype=np.float32)
        tr_arr = np.asarray(truths, dtype=np.float32)
        fc_data = ma.array(fc_arr, mask=np.isnan(fc_arr))
        tr_data = ma.array(tr_arr, mask=np.isnan(tr_arr))
    else:
        raise TypeError(
            "forecasts 与 truths 须同为 xarray.DataArray 或同为 numpy.ndarray。"
        )

    forecast_errors = fc_data - tr_data
    forecast_errors.mask = ma.mask_or(
        ma.getmaskarray(fc_data), ma.getmaskarray(tr_data)
    )

    # MaskedArray → ndarray，缺测填回 NaN；均值结果保持 float32
    if time_axis is not None:
        mean_err = ma.mean(forecast_errors, axis=time_axis, dtype=np.float32)
    else:
        mean_err = forecast_errors
    if ma.is_masked(mean_err):
        return np.asarray(mean_err.filled(np.nan), dtype=np.float32)
    return np.asarray(mean_err, dtype=np.float32)


def apply_additive_correction(
    forecast: Union[xr.DataArray, np.ndarray],
    bias: Union[xr.DataArray, np.ndarray],
    fill_masked_bias_values: bool = True,
) -> np.ndarray:
    """用加性偏差订正预报：``corrected = forecast - bias``。

    参数
    ----------
    forecast :
        待订正预报。
    bias :
        偏差场（定义为 forecast - truth）。
    fill_masked_bias_values :
        为 True 时，偏差中的 NaN 填 0，使对应位置预报保持不变。

    返回
    -------
    np.ndarray
        订正后的数值；偏差缺测未填充时对应位置为 NaN。
    """
    if isinstance(forecast, xr.DataArray) and isinstance(bias, xr.DataArray):
        fc = np.asarray(forecast.values, dtype=np.float32)
        bias_arr = np.asarray(
            align_operand_units_to_reference(bias, forecast), dtype=np.float32
        )
    else:
        fc = np.asarray(
            forecast.values if isinstance(forecast, xr.DataArray) else forecast,
            dtype=np.float32,
        )
        bias_arr = np.asarray(
            bias.values if isinstance(bias, xr.DataArray) else bias,
            dtype=np.float32,
        )
    if fill_masked_bias_values:
        # 偏差缺测填 0 → 该处订正量为 0
        bias_arr = np.where(np.isnan(bias_arr), np.float32(0.0), bias_arr)

    # 去掉偏差中长度为 1 的维，同一偏差场广播订正各 member
    bias_arr = np.squeeze(bias_arr)

    try:
        corrected = fc - bias_arr
    except ValueError as err:
        raise ValueError(
            f"预报与偏差无法广播相减: forecast.shape={fc.shape}, bias.shape={bias_arr.shape}"
        ) from err
    return corrected.astype(fc.dtype, copy=False)


class CalculateForecastBias(BasePlugin):
    """由历史预报与实况评估预报偏差（forecast - truth）。"""

    def __init__(self):
        """初始化；默认使用加性误差评估。"""
        self.error_method = evaluate_additive_error

    def _ensure_single_valued_forecast(self, forecasts: xr.DataArray) -> xr.DataArray:
        """限制非时间层次为单值，并去掉长度为 1 的 ``member`` / ``level`` 维。

        本方法仅做时间对齐，并在输出时沿 ``time`` 求平均；因此除时间相关维外，
        其余层次（``member``、``level``）必须长度为 1。

        meb 六维 ``member, level, time, dtime, lat, lon``：
        - ``member`` / ``level``：长度必须为 1（随后 squeeze）；
          多阈值概率场在 meb 中落在 ``level``，同样会被此处拒绝；
        - ``time``：可为多值（历史样本维，用于对齐与平均）；
        - ``dtime`` / ``lat`` / ``lon``：此处不限制。

        概率场：meb 无 ``threshold`` 维名时，按变量名 ``probability_of_*``
        （threshold 插件输出约定）拒绝单阈值概率误入。
        """
        if is_probability_named_dataarray(forecasts):
            raise ValueError(
                "Forecasts provided as probability data. Historical forecasts must be single"
                " valued realisable forecast (realization, percentile or ensemble mean)."
            )
        result = forecasts
        for dim_name in ("member", "level"):
            if dim_name not in result.dims:
                continue
            if result.sizes[dim_name] > 1:
                raise ValueError(
                    f"Multiple {dim_name} values detected. Expect historical forecasts"
                    "to be single valued forecasts."
                )
            result = result.squeeze(dim_name, drop=True)

        return result

    def _define_metadata(self, forecasts: xr.DataArray) -> Dict[str, str]:
        """定义偏差场属性，并覆盖 title。"""
        attributes = generate_mandatory_attributes([forecasts])
        attributes["title"] = "Forecast bias data"
        return attributes

    def _create_bias_template(self, forecasts: xr.DataArray) -> xr.DataArray:
        """构造偏差输出壳（元数据 / 坐标），数值随后被覆盖。

        对应原版 ``_create_bias_cube``；此处输入输出均为 ``xarray.DataArray``。

        meb：起报为 ``time``。多起报时须收成长度 1（取最新起报），并写
        ``attrs['time_bounds']``；``time`` 维直接保留为长度 1，不再 drop 后再补。
        最后补齐缺失的 ``member`` / ``level`` / ``dtime``。
        """
        attributes = self._define_metadata(forecasts)
        diagnostic_name = f"forecast_error_of_{forecasts.name or 'data'}"

        bias = forecasts.copy(deep=True)
        bias.name = diagnostic_name
        bias.attrs = dict(forecasts.attrs)
        bias.attrs.update(attributes)
        bias.attrs["long_name"] = diagnostic_name

        if "time" in list(bias.dims):
            time_point, time_bounds = create_unified_time_values(bias["time"])
            # 保留 time 维长度 1：isel 用列表索引；坐标改为统一起报点
            bias = bias.isel(time=[0])
            bias = bias.assign_coords(time=[time_point])
            bias = bias.copy(data=np.zeros(bias.shape, dtype=forecasts.dtype))
            if time_bounds is not None:
                bias.attrs["time_bounds"] = [
                    np.datetime_as_string(time_bounds[0]),
                    np.datetime_as_string(time_bounds[1]),
                ]
            else:
                bias.attrs.pop("time_bounds", None)
        elif "time" not in bias.coords:
            raise ValueError("预报缺少 time 坐标。")

        return ensure_meb6d(bias)

    def process(
        self, historic_forecasts: xr.DataArray, truths: xr.DataArray
    ) -> xr.DataArray:
        """评估历史预报相对实况的平均偏差。

        参数
        ----------
        historic_forecasts :
            一个或多个历史单值预报。
        truths :
            对应实况。

        返回
        -------
        xr.DataArray
            偏差场 ``forecast_error_of_<name>``；多时刻时为时间平均偏差；
            ``member``、``level``、``time``、``dtime`` 四维长度均为 1。
        """
        if not isinstance(historic_forecasts, xr.DataArray):
            raise TypeError("historic_forecasts 须为 xarray.DataArray。")
        if not isinstance(truths, xr.DataArray):
            raise TypeError("truths 须为 xarray.DataArray。")

        # 入口按 meb 六维约定校验（保证 time/dtime 等为维）
        historic_forecasts = strip_placeholder_time_bounds(
            meb.checkout_griddata(
                historic_forecasts, valid_val=(-np.inf, np.inf, np.nan)
            )
        )
        truths = strip_placeholder_time_bounds(
            meb.checkout_griddata(truths, valid_val=(-np.inf, np.inf, np.nan))
        )

        historic_forecasts = self._ensure_single_valued_forecast(historic_forecasts)
        # 实况同样要求非时间层次为单值
        truths = self._ensure_single_valued_forecast(truths)

        # 按 valid time 对齐
        historic_forecasts, truths = filter_non_matching_by_valid_time(
            historic_forecasts, truths
        )
        check_forecast_consistency(historic_forecasts)

        bias = self._create_bias_template(historic_forecasts)
        error_data = self.error_method(
            historic_forecasts, truths, collapse_dim="time"
        )
        # 写入偏差数值（缺测已是 NaN）；误差为空间场，reshape 到六维壳
        bias = bias.copy(deep=True)
        bias.data = np.asarray(error_data, dtype=bias.dtype).reshape(bias.shape)
        return bias


class ApplyBiasCorrection(BasePlugin):
    """对预报逐成员施加简单加性偏差订正。"""

    def __init__(
        self,
        lower_bound: Optional[float] = None,
        upper_bound: Optional[float] = None,
        fill_masked_bias_values: bool = False,
    ):
        """初始化订正插件。

        参数
        ----------
        lower_bound / upper_bound :
            订正后的物理上下界；``None`` 表示该侧不裁剪。
        fill_masked_bias_values :
            偏差 NaN 是否填 0（默认 False，与原插件默认一致）。
        """
        self._correction_method = apply_additive_correction
        self._lower_bound = lower_bound
        self._upper_bound = upper_bound
        self._fill_masked_bias_values = fill_masked_bias_values

    def _split_forecasts_and_bias(
        self, inputs: Sequence[xr.DataArray]
    ) -> tuple[xr.DataArray, Optional[List[xr.DataArray]]]:
        """拆分预报与偏差；无偏差时告警并返回原预报。"""
        forecast, bias_list = split_forecasts_and_bias(inputs)
        if not bias_list:
            msg = (
                "There are no forecast_error (bias) fields provided for calibration. "
                "The uncalibrated forecast will be returned."
            )
            warnings.warn(msg)
            return add_warning_comment(forecast), None
        return forecast, bias_list

    def _get_mean_bias(self, bias_values: Sequence[xr.DataArray]) -> xr.DataArray:
        """从一个或多个偏差场得到平均偏差。

        多个输入时，每个偏差必须是单起报且**无** ``time_bounds``；否则报错。
        """
        if len(bias_values) == 1:
            return bias_values[0]

        for bias in bias_values:
            if has_time_bounds(bias):
                t_coord = bias.coords.get("time")
                t_pts = None if t_coord is None else t_coord.values
                raise ValueError(
                    "Collapsing multiple bias values to a mean value is unsupported for "
                    "bias values defined over multiple reference forecast values. Bias cube"
                    f"for frt: {t_pts} has bounds"
                    f"{bias.attrs.get('time_bounds')}, expected {None}."
                )

        # 沿 time（起报）拼接后求平均
        stacked = []
        for bias in bias_values:
            if "time" not in bias.coords:
                raise ValueError("偏差场缺少 time 坐标。")
            t_val = _as_datetime64_scalar(
                np.asarray(bias["time"].values).ravel()[0]
            )
            piece = bias
            if "time" in piece.dims:
                piece = piece.isel(time=0, drop=True)
            stacked.append(piece.expand_dims(time=[t_val]))

        merged = xr.concat(stacked, dim="time", coords="different", compat="equals")
        time_point, time_bounds = create_unified_time_values(merged["time"])
        mean_bias = merged.mean(dim="time", keep_attrs=True)
        mean_bias = mean_bias.astype(bias_values[0].dtype, copy=False)
        if "time" in mean_bias.dims:
            mean_bias = mean_bias.isel(time=0, drop=True)
        mean_bias = mean_bias.expand_dims(time=[time_point])
        mean_bias = mean_bias.transpose(
            "member", "level", "time", "dtime", "lat", "lon",
            missing_dims="ignore",
        )
        if time_bounds is not None:
            mean_bias.attrs["time_bounds"] = [
                np.datetime_as_string(time_bounds[0]),
                np.datetime_as_string(time_bounds[1]),
            ]
        return mean_bias

    def _check_forecast_bias_consistent(
        self, forecast: xr.DataArray, bias_data: Sequence[xr.DataArray]
    ) -> None:
        """检查预报与偏差的起报小时（``time``）、``dtime`` 是否一致。"""
        bias_frt_hours: set[int] = set()
        for cube in bias_data:
            if "time" not in cube.coords:
                raise ValueError("偏差场缺少 time 坐标。")
            bias_frt_hours |= get_frt_hours(cube["time"])

        if "time" not in forecast.coords:
            raise ValueError("预报缺少 time 坐标。")
        fcst_frt_hours = get_frt_hours(forecast["time"])
        combined_frt_hours = fcst_frt_hours | bias_frt_hours

        if len(bias_frt_hours) != 1:
            raise ValueError(
                "Multiple forecast_reference_time valid-hour values detected across bias datasets."
            )
        if len(combined_frt_hours) != 1:
            raise ValueError(
                "forecast_reference_time valid-hour differ between forecast and bias datasets."
            )

        bias_period: set = set()
        for cube in bias_data:
            if "dtime" not in cube.coords:
                raise ValueError("偏差场缺少 dtime 坐标。")
            bias_period.update(
                float(v) for v in np.asarray(cube["dtime"].values).ravel().tolist()
            )

        if "dtime" not in forecast.coords:
            raise ValueError("预报缺少 dtime 坐标。")
        fcst_period = {
            float(v) for v in np.asarray(forecast["dtime"].values).ravel().tolist()
        }
        combined_period_values = fcst_period | bias_period

        if len(bias_period) != 1:
            raise ValueError(
                "Multiple forecast period values detected across bias datasets."
            )
        if len(combined_period_values) != 1:
            raise ValueError(
                "Forecast period differ between forecast and bias datasets."
            )

    def process(self, *inputs: Union[xr.DataArray, Sequence[xr.DataArray]]) -> xr.DataArray:
        """拆分输入并施加偏差订正。

        参数
        ----------
        inputs :
            一个预报 ``DataArray``，以及零个或多个偏差 ``DataArray``
            （名称含 ``forecast_error``）；也可传入嵌套序列。

        返回
        -------
        xr.DataArray
            订正后的预报；无偏差时返回带 warning comment 的原预报。
        """
        flat: List[xr.DataArray] = []
        for item in inputs:
            if isinstance(item, xr.DataArray):
                flat.append(item)
            elif isinstance(item, (list, tuple)):
                flat.extend(item)
            else:
                raise TypeError(
                    "ApplyBiasCorrection 输入须为 xarray.DataArray 或其序列。"
                )

        # 入口按 meb 六维约定校验（统一维序与坐标）；
        # 同时剔除 checkout 为缺少 bounds 的场写入的占位 time_bounds=[0, 0]：
        # 该占位值不代表真实起报范围，若保留会随订正结果泄漏到输出元数据，
        # 并可能被下游误判为多起报偏差场（真实 bounds 的判定见 has_time_bounds）。
        flat = [
            strip_placeholder_time_bounds(
                meb.checkout_griddata(da, valid_val=(-np.inf, np.inf, np.nan))
            )
            for da in flat
        ]

        forecast, bias_list = self._split_forecasts_and_bias(flat)
        if bias_list is None:
            return forecast

        self._check_forecast_bias_consistent(forecast, bias_list)
        bias = self._get_mean_bias(bias_list)

        corrected = forecast.copy(deep=True)
        corrected.data = self._correction_method(
            forecast, bias, self._fill_masked_bias_values
        ).astype(forecast.dtype, copy=False)

        if (self._lower_bound is not None) or (self._upper_bound is not None):
            corrected = clip_dataarray(
                corrected, self._lower_bound, self._upper_bound
            )
        return corrected
