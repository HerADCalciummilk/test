#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""层结递减率计算与温度地形订正模块。

本模块面向使用者提供两类能力：
1. `LapseRate`：根据温度、地形和陆海掩膜估计网格化层结递减率（K/m）。
2. `ApplyGriddedLapseRate`：将层结递减率应用到温度场，实现源地形到目标地形的温度订正。

输入既支持 `xarray.DataArray`（推荐，便于保留坐标与单位元数据），
也支持 `numpy.ndarray`（纯数值计算场景）。
"""

from typing import Union, Tuple
import numpy as np
import xarray as xr

import meteva_base as meb

from orographic_temperature_downscaling.utils.base_plugin import BasePlugin,PostProcessingPlugin
from orographic_temperature_downscaling.utils.utils import (
    convert_units,
    rebuild_to_meb_griddata,
)

_MEB_VALID_VAL = (-np.inf, np.inf, np.nan)


# 物理常数（单位：K/m）
DALR = -0.0098  # 干绝热递减率
ELR = -0.0065   # 环境递减率（标准大气）


def compute_lapse_rate_adjustment(
    lapse_rate: np.ndarray,
    orog_diff: np.ndarray,
    max_orog_diff_limit: float = 50.0
) -> np.ndarray:
    """根据层结递减率与地形高度差计算温度订正量。

    计算逻辑：
    1. 当高度差绝对值不超过 `max_orog_diff_limit` 时，使用 `lapse_rate * orog_diff`；
    2. 超过上限的高度差部分使用环境递减率 `ELR`，避免订正量异常放大。

    参数
    ----------
    lapse_rate : np.ndarray
        层结递减率数组，单位 K/m。
    orog_diff : np.ndarray
        地形高度差数组（目标地形减去源地形），单位 m。
    max_orog_diff_limit : float
        直接应用局地层结递减率的最大高度差（m）。

    返回值
    -------
    np.ndarray
        温度订正量，单位 K，形状与广播后的 `lapse_rate` 一致。
    """
    orog_diff = np.broadcast_to(orog_diff, lapse_rate.shape).copy()
    orig_orog_diff = orog_diff.copy()

    # 如果地形高度差大于最大允许值（如未解析的山顶）或小于负的最大允许值（如未解析的山谷）
    condition1 = orog_diff > max_orog_diff_limit
    condition2 = orog_diff < -max_orog_diff_limit
    orog_diff[condition1] = max_orog_diff_limit
    orog_diff[condition2] = -max_orog_diff_limit
    vertical_adjustment = np.multiply(orog_diff, lapse_rate)

    # 计算绝对地形高度差大于最大允许值的点的额外层结递减率调整
    orig_orog_diff[condition1] = np.clip(
        orig_orog_diff[condition1] - max_orog_diff_limit, 0, None
    )
    orig_orog_diff[condition2] = np.clip(
        orig_orog_diff[condition2] + max_orog_diff_limit, None, 0
    )

    # 假设环境递减率（也称为标准大气递减率）
    vertical_adjustment[condition1] += np.multiply(orig_orog_diff[condition1], ELR)
    vertical_adjustment[condition2] += np.multiply(orig_orog_diff[condition2], ELR)
    return vertical_adjustment


class ApplyGriddedLapseRate(PostProcessingPlugin):
    """将网格化层结递减率应用到温度场的插件。

    典型使用步骤：
    1. 提供源网格温度 `temperature`；
    2. 提供同网格层结递减率 `lapse_rate`（K/m）；
    3. 提供源/目标地形 `source_orog`、`dest_orog`（m）；
    4. 获得目标地形上的温度订正结果。

    设计意图：
    - 该插件不负责估计层结递减率，只负责“应用”已有递减率；
    - 通过地形高度差把温度场从源地形映射到目标地形；
    - 对极端地形差采用分段策略：超过阈值的部分使用标准环境递减率，
      以降低在复杂地形下的过度订正风险。
    """

    def __init__(self):
        """初始化插件实例（当前无额外可配置参数）。"""
        pass


    def _calc_orog_diff(
        self,
        source_orog: Union[xr.DataArray, np.ndarray],
        dest_orog: Union[xr.DataArray, np.ndarray],
    ) -> np.ndarray:
        """计算地形高度差（目标 - 源，单位 m）。"""
        if isinstance(source_orog, xr.DataArray):
            source_m = convert_units(source_orog, "m")
        else:
            source_m = np.asarray(source_orog, dtype=np.float32)
        if isinstance(dest_orog, xr.DataArray):
            dest_m = convert_units(dest_orog, "m")
        else:
            dest_m = np.asarray(dest_orog, dtype=np.float32)
        return dest_m - source_m

    def process(
        self,
        temperature: Union[xr.DataArray, np.ndarray],
        lapse_rate: Union[xr.DataArray, np.ndarray],
        source_orog: Union[xr.DataArray, np.ndarray],
        dest_orog: Union[xr.DataArray, np.ndarray]
    ) -> Union[xr.DataArray, np.ndarray]:
        """应用层结递减率对温度进行地形订正。

        参数
        ----------
        temperature : xr.DataArray 或 np.ndarray
            输入温度场
        lapse_rate : xr.DataArray 或 np.ndarray
            预计算的层结递减率
        source_orog : xr.DataArray 或 np.ndarray
            源地形高度
        dest_orog : xr.DataArray 或 np.ndarray
            目标地形高度

        返回值
        -------
        xr.DataArray 或 np.ndarray
            订正后的温度场（`np.float32`），单位为 K（开尔文）。
            - 输入为 `xarray.DataArray` 时返回 `xarray.DataArray`；
            - 输入为 `numpy.ndarray` 时返回 `numpy.ndarray`。

        说明
        ----
        - 对 `xarray.DataArray` 输入会尝试读取单位并做坐标一致性检查；
        - 内部计算统一在 Kelvin 与 K/m 语义下执行，输出亦为 K（与上游 Improver 一致）；
        - 返回值类型随输入类型而变化，但数值形状与输入温度保持一致。
        """
        temp_template = (
            meb.checkout_griddata(temperature, valid_val=_MEB_VALID_VAL)
            if isinstance(temperature, xr.DataArray)
            else None
        )
        source_template = (
            meb.checkout_griddata(source_orog, valid_val=_MEB_VALID_VAL)
            if isinstance(source_orog, xr.DataArray)
            else None
        )
        dest_template = (
            meb.checkout_griddata(dest_orog, valid_val=_MEB_VALID_VAL)
            if isinstance(dest_orog, xr.DataArray)
            else None
        )

        if isinstance(lapse_rate, xr.DataArray):
            lr_template = meb.checkout_griddata(lapse_rate, valid_val=_MEB_VALID_VAL)
            lr_k_per_m = convert_units(lapse_rate, "K m-1")
            if temp_template is not None:
                if not meb.checkout_griddata_same_coords(
                    [temp_template, lr_template], is_time_match=True
                ):
                    raise ValueError("层结递减率与温度场的空间/时效坐标不一致")
        else:
            lr_k_per_m = np.asarray(lapse_rate, dtype=np.float32)

        if temp_template is not None:
            if source_template is not None:
                if not meb.checkout_griddata_same_coords(
                    [temp_template, source_template], is_time_match=False
                ):
                    raise ValueError("源地形与温度场的坐标不一致")
            if dest_template is not None:
                if not meb.checkout_griddata_same_coords(
                    [temp_template, dest_template], is_time_match=False
                ):
                    raise ValueError("目标地形与温度场的坐标不一致")

        orog_diff = self._calc_orog_diff(source_orog, dest_orog)
        if isinstance(temperature, xr.DataArray):
            temp_k = convert_units(temperature, "K")
        else:
            temp_k = np.asarray(temperature, dtype=np.float32)

        # 应用层结递减率调整
        # 订正项由“局地递减率部分 + 极端高差回退部分”共同组成。
        result = temp_k + compute_lapse_rate_adjustment(lr_k_per_m, orog_diff)
        result = result.astype(np.float32)

        if temp_template is not None:
            return rebuild_to_meb_griddata(
                result,
                template=temp_template,
                name=temp_template.name,
                units="K",
            )

        return result


class LapseRate(BasePlugin):
    """从温度和地形估计局地层结递减率场（K/m）的插件。

    使用者视角下的流程：
    1. 以每个格点为中心提取邻域窗口；
    2. 过滤与中心点高差超过阈值的邻居样本；
    3. 在有效样本上拟合“温度-高度”梯度；
    4. 将结果裁剪到可配置的物理范围。

    结果语义：
    - 输出为每个网格点对应的局地层结递减率（K/m）；
    - 海洋点或局部样本不足时回退到干绝热递减率 `DALR`；
    - 支持二维场和多前导维场（按最后两维为空间维处理）。
    """

    def __init__(
        self,
        max_height_diff: float = 35.0,
        nbhood_radius: int = 7,
        max_lapse_rate: float = -3 * DALR,
        min_lapse_rate: float = DALR,
    ) -> None:
        """初始化层结递减率估计器。

        参数
        ----------
        max_height_diff : float
            邻域样本相对中心点允许的最大高差（m），超出则不参与拟合。
        nbhood_radius : int
            邻域半径，窗口边长为 `2 * nbhood_radius + 1`。
        max_lapse_rate : float
            层结递减率上限（K/m）。
        min_lapse_rate : float
            层结递减率下限（K/m）。
        """

        self.max_height_diff = max_height_diff
        self.nbhood_radius = nbhood_radius
        self.max_lapse_rate = max_lapse_rate
        self.min_lapse_rate = min_lapse_rate

        if self.max_lapse_rate < self.min_lapse_rate:
            raise ValueError("最大层结递减率小于最小层结递减率")

        if self.nbhood_radius < 0:
            raise ValueError("邻域半径小于零")

        if self.max_height_diff < 0:
            raise ValueError("最大高度差小于零")

        # nbhood_size=3对应于以中心点为中心的3x3数组。
        self.nbhood_size = int((2 * nbhood_radius) + 1)

        # 用于邻域检查，确保数组中心为非NaN。
        self.ind_central_point = self.nbhood_size // 2

    def __repr__(self) -> str:
        """返回当前插件配置摘要，便于日志与调试。"""
        desc = (
            "<LapseRate: max_height_diff: {}, nbhood_radius: {},"
            "max_lapse_rate: {}, min_lapse_rate: {}>".format(
                self.max_height_diff,
                self.nbhood_radius,
                self.max_lapse_rate,
                self.min_lapse_rate,
            )
        )
        return desc

    def _create_windows(self, temp: np.ndarray, orog: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """生成温度与地形的邻域滑动窗口视图。

        参数
        ----------
        temp : np.ndarray
            温度数据的2D数组（单个集合成员），单位为开尔文
        orog : np.ndarray
            地形的2D数组，单位为米

        返回值
        -------
        tuple
            - 温度窗口数组
            - 地形窗口数组
        """
        # 注意：由于我们没有 improver 的 neighbourhood_tools，需要实现简单的版本
        # 这里使用 numpy 的 pad 函数来模拟
        pad_width = self.nbhood_radius
        temp_padded = np.pad(temp, pad_width, mode='constant', constant_values=np.nan)
        orog_padded = np.pad(orog, pad_width, mode='constant', constant_values=np.nan)

        # 创建滚动窗口视图
        window_shape = (self.nbhood_size, self.nbhood_size)
        temp_windows = self._rolling_window(temp_padded, window_shape)
        orog_windows = self._rolling_window(orog_padded, window_shape)

        return temp_windows, orog_windows

    def _rolling_window(self, array: np.ndarray, window_shape: Tuple[int, int]) -> np.ndarray:
        """基于 `numpy.sliding_window_view` 构建滑动窗口视图。

        参数
        ----------
        array : np.ndarray
            输入数组
        window_shape : tuple
            窗口形状 (height, width)

        返回值
        -------
        np.ndarray
            滚动窗口数组
        """
        from numpy.lib.stride_tricks import sliding_window_view
        return sliding_window_view(array, window_shape)

    def _generate_lapse_rate_array(
        self,
        temperature_data: np.ndarray,
        orography_data: np.ndarray,
        land_sea_mask_data: np.ndarray,
    ) -> np.ndarray:
        """在单个二维切片上计算层结递减率。

        参数
        ----------
        temperature_data : np.ndarray
            温度数据的2D数组（单个集合成员），单位为开尔文
        orography_data : np.ndarray
            地形的2D数组，单位为米
        land_sea_mask_data : np.ndarray
            2D陆地-海洋掩膜

        返回值
        -------
        np.ndarray
            层结递减率二维数组（K/m）。
        """
        # 将海洋点填充为NaN值
        # 海点不参与局地梯度拟合，避免海陆热力差异污染陆地估计结果。
        temperature_data = np.where(land_sea_mask_data, temperature_data, np.nan)

        # 预分配输出数组
        lapse_rate_array = np.empty_like(temperature_data, dtype=np.float32)

        # 填充数据并生成代表每个点邻域的窗口
        temp_nbhood_window, orog_nbhood_window = self._create_windows(
            temperature_data, orography_data
        )

        # 遍历温度和地形的窗口，计算表面温度随地形高度的梯度 - 即层结递减率
        cnpt = self.ind_central_point
        for i in range(lapse_rate_array.shape[0]):
            for j in range(lapse_rate_array.shape[1]):
                if np.isnan(temperature_data[i, j]):
                    lapse_rate_array[i, j] = DALR
                    continue

                # 获取当前点的邻域窗口
                temp_window = temp_nbhood_window[i, j]
                orog_window = orog_nbhood_window[i, j]

                # 中心点地形高度
                orog_centre = orog_window[cnpt, cnpt]

                # 高度差掩膜：中心点与邻居的高度差大于max_height_diff的点
                height_diff_mask = np.abs(orog_window - orog_centre) > self.max_height_diff

                # 应用高度差掩膜
                temp_filtered = np.where(height_diff_mask, np.nan, temp_window)
                orog_filtered = np.where(np.isnan(temp_filtered), np.nan, orog_window)

                # 计算梯度（层结递减率）
                # 使用简单的线性回归计算梯度
                valid_mask = ~np.isnan(temp_filtered) & ~np.isnan(orog_filtered)
                if np.sum(valid_mask) < 2:
                    # 有效样本不足时，无法拟合局地梯度，回退到干绝热递减率。
                    grad = DALR
                else:
                    # 计算标准差检查
                    temp_std = np.nanstd(temp_filtered)
                    orog_std = np.nanstd(orog_filtered)

                    if np.isclose(temp_std, 0) or np.isclose(orog_std, 0):
                        # 温度或地形无变化时，回归问题退化，同样回退到 DALR。
                        grad = DALR
                    else:
                        # 使用向量化计算斜率：cov(x,y)/var(x)，避免 polyfit 的开销
                        temp_valid = temp_filtered[valid_mask]
                        orog_valid = orog_filtered[valid_mask]

                        # 计算均值
                        temp_mean = np.mean(temp_valid)
                        orog_mean = np.mean(orog_valid)

                        # 计算协方差和方差
                        cov = np.mean((orog_valid - orog_mean) * (temp_valid - temp_mean))
                        var_orog = np.mean((orog_valid - orog_mean) ** 2)

                        if np.isclose(var_orog, 0):
                            grad = DALR
                        else:
                            # 梯度 = cov(orog, temp) / var(orog)
                            grad = cov / var_orog

                # 检查中心点是否为NaN
                if np.isnan(temperature_data[i, j]):
                    grad = DALR

                lapse_rate_array[i, j] = grad

        # 对层结递减率值施加上下限约束
        lapse_rate_array = np.clip(lapse_rate_array, self.min_lapse_rate, self.max_lapse_rate)
        return lapse_rate_array

    def process(
        self,
        temperature: Union[xr.DataArray, np.ndarray],
        orography: Union[xr.DataArray, np.ndarray],
        land_sea_mask: Union[xr.DataArray, np.ndarray],
    ) -> Union[xr.DataArray, np.ndarray]:
        """从温度、地形和陆海掩膜计算层结递减率场。

        参数
        ----------
        temperature : xr.DataArray 或 np.ndarray
            空气温度立方体（K）
        orography : xr.DataArray 或 np.ndarray
            包含地形数据的立方体（米）
        land_sea_mask : xr.DataArray 或 np.ndarray
            包含二进制陆地-海洋掩膜的立方体。陆地点为True，海洋点为False。

        返回值
        -------
        xr.DataArray 或 np.ndarray
            层结递减率数组（K/m）。
            - 输入为 `xarray.DataArray` 时返回 `xarray.DataArray`；
            - 输入为 `numpy.ndarray` 时返回 `numpy.ndarray`。

        说明
        ----
        - 支持二维与多维输入（默认最后两维为空间维）；
        - 多维输入会按非空间维逐片计算；
        - 输出数值数据类型为 `np.float32`；
        """
        temp_template = (
            meb.checkout_griddata(temperature, valid_val=_MEB_VALID_VAL)
            if isinstance(temperature, xr.DataArray)
            else None
        )

        if isinstance(orography, xr.DataArray):
            orog_template = meb.checkout_griddata(orography, valid_val=_MEB_VALID_VAL)
            if temp_template is not None:
                if not meb.checkout_griddata_same_coords(
                    [temp_template, orog_template], is_time_match=False
                ):
                    raise ValueError("地形与温度场的坐标不一致")
        else:
            orography = orography.astype(np.float32, copy=False)

        if isinstance(land_sea_mask, xr.DataArray):
            mask_template = meb.checkout_griddata(
                land_sea_mask, valid_val=_MEB_VALID_VAL
            )
            land_mask_values = mask_template.values.astype(bool, copy=False)
            if temp_template is not None:
                if not meb.checkout_griddata_same_coords(
                    [temp_template, mask_template], is_time_match=True
                ):
                    raise ValueError("陆地-海洋掩膜与温度场的空间/时效坐标不一致")
        else:
            land_mask_values = land_sea_mask.astype(bool, copy=False)

        if isinstance(temperature, xr.DataArray):
            temp_k = convert_units(temperature, "K")
        else:
            temp_k = np.asarray(temperature, dtype=np.float32)
        if isinstance(orography, xr.DataArray):
            orog_values = convert_units(orography, "m")
        else:
            orog_values = np.asarray(orography, dtype=np.float32)

        # 提取2D空间切片（假设最后两个维度是lat, lon）
        # 处理多维情况（member, level, time, dtime, lat, lon）
        original_shape = temp_k.shape
        spatial_shape = original_shape[-2:]
        non_spatial_shape = original_shape[:-2]

        if len(non_spatial_shape) == 0:
            # 2D情况
            lapse_rate_data = self._generate_lapse_rate_array(
                temp_k, orog_values, land_mask_values
            )
        else:
            # 多维情况，逐个处理每个2D切片
            # 先展平前导维，再在每个二维空间切片上复用同一套算法逻辑。
            lapse_rate_data = np.empty_like(temp_k, dtype=np.float32)
            total_slices = np.prod(non_spatial_shape)
            temp_reshaped = temp_k.reshape(total_slices, *spatial_shape)
            orog_reshaped = orog_values.reshape(total_slices, *spatial_shape)
            land_mask_reshaped = land_mask_values.reshape(total_slices, *spatial_shape)

            for i in range(total_slices):
                lapse_rate_data[i] = self._generate_lapse_rate_array(
                    temp_reshaped[i], orog_reshaped[i], land_mask_reshaped[i]
                )

            lapse_rate_data = lapse_rate_data.reshape(original_shape)

        lapse_rate_data = lapse_rate_data.astype(np.float32, copy=False)

        if temp_template is not None:
            return rebuild_to_meb_griddata(
                lapse_rate_data,
                template=temp_template,
                name="air_temperature_lapse_rate",
                units="K m-1",
            )

        return lapse_rate_data
