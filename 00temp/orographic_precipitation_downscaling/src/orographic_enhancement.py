#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形增强算法。

本模块实现并迁移了 IMPROVER 地形增强核心流程，支持
``xarray.DataArray`` 与 ``numpy.ndarray`` 输入。整体计算链路为：

1. 在元插件中提取边界层代表高度的温湿压与风场；
2. 将风速风向解析为目标网格坐标系下的 ``u/v`` 风分量；
3. 在主插件中计算迎风抬升项 ``v·gradZ``、格点增强与上游贡献；
4. 输出地形增强结果（单位 ``m s-1``），并在可用时重组为标准六维网格。

网格输入适配、饱和水汽压与数值辅助实现见 ``orographic_precipitation_downscaling.src.utils``。
"""
from __future__ import annotations

from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr

import meteva_base as meb
from pyproj import CRS, Transformer
from scipy.ndimage import uniform_filter1d

from orographic_precipitation_downscaling.utils.base_plugin import BasePlugin
from orographic_precipitation_downscaling.utils.utils import (
    convert_units,
    rebuild_to_meb_griddata,
)
from orographic_precipitation_downscaling.src.utils._grid import (
    _convert_units,
    _coord_values_for_crs,
    _estimate_grid_spacing_meters,
    _get_data_crs,
    _get_spatial_coord_names,
    _grid_spacings_meters,
    _make_field_on_target,
    _needs_regridding,
    _normalize_to_2d_field,
    _prepare_input,
    _regrid_scalar_field,
    _sort_spatial_dataarray,
)
from orographic_precipitation_downscaling.src.utils._numerics import (
    _regridded_adjacent_gradient,
    _square_neighbourhood_mean,
)
from orographic_precipitation_downscaling.src.utils._svp import calculate_svp_in_air

R_WATER_VAPOUR = 461.6  # 水汽气体常数，单位 J K-1 kg-1


class ResolveWindComponents(BasePlugin):
    """风场分量解析插件。

    该插件对应原算法中“先解风分量再计算地形增强”的步骤，负责把
    ``wind_speed + wind_direction`` 转换为目标网格坐标系下的 ``u/v`` 分量。
    主要处理链路如下：

    1. 统一风速单位到 ``m s-1``，统一风向角度到弧度计算。
    2. 根据风向约定（from/to）确定风矢量指向。
    3. 若输入为投影网格，计算真北与网格北夹角并进行方向修正。
    4. 若源网格与目标网格投影不一致，执行分量旋转与重采样。
    5. 输出与目标网格对齐的风分量，供地形增强主算法直接使用。

    输入支持 ``xarray.DataArray`` 与 ``numpy.ndarray``：
    - DataArray 路径尽量保留坐标与属性；
    - ndarray 路径返回纯数组分量。

    说明
    ----------
    该插件内部计算核心基于二维场。若输入是标准六维且前四维长度为 1，
    会在入口自动压缩到二维计算，并在返回时尽量保持与目标网格一致的坐标语义。
    """

    @staticmethod
    def _bearing_radians(
        lat1_deg: np.ndarray, lon1_deg: np.ndarray, lat2_deg: np.ndarray, lon2_deg: np.ndarray
    ) -> np.ndarray:
        """计算两组经纬度点之间的方位角。"""
        lat1 = np.deg2rad(lat1_deg)
        lon1 = np.deg2rad(lon1_deg)
        lat2 = np.deg2rad(lat2_deg)
        lon2 = np.deg2rad(lon2_deg)
        dlon = lon2 - lon1
        numerator = np.sin(dlon) * np.cos(lat2)
        denominator = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
        return np.arctan2(numerator, denominator)

    @staticmethod
    def _calculate_true_north_offset(target: Union[xr.DataArray, np.ndarray]) -> np.ndarray:
        """计算目标网格上真北与网格北的夹角。"""
        target_values = np.asarray(target)
        if not isinstance(target, xr.DataArray):
            return np.zeros(target_values.shape, dtype=np.float32)
        target = _sort_spatial_dataarray(target)
        crs = _get_data_crs(target)
        if crs is None or crs.is_geographic:
            return np.zeros(target.shape, dtype=np.float32)
        y_name, x_name = _get_spatial_coord_names(target)
        x_values = _coord_values_for_crs(target.coords[x_name], crs)
        y_values = _coord_values_for_crs(target.coords[y_name], crs)
        x_mesh, y_mesh = np.meshgrid(x_values, y_values)
        delta = _estimate_grid_spacing_meters(target)
        transformer = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
        lon0, lat0 = transformer.transform(x_mesh, y_mesh)
        lon1, lat1 = transformer.transform(x_mesh, y_mesh + delta)
        return (-ResolveWindComponents._bearing_radians(lat0, lon0, lat1, lon1)).astype(np.float32)

    @staticmethod
    def _calculate_true_north_offset_for_points(
        crs: Optional[CRS], x_points: np.ndarray, y_points: np.ndarray, delta_m: float
    ) -> np.ndarray:
        """计算指定投影坐标点上的真北偏角。"""
        if crs is None or crs.is_geographic:
            return np.zeros(np.asarray(x_points).shape, dtype=np.float32)
        transformer = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
        lon0, lat0 = transformer.transform(x_points, y_points)
        lon1, lat1 = transformer.transform(x_points, y_points + delta_m)
        return (-ResolveWindComponents._bearing_radians(lat0, lon0, lat1, lon1)).astype(np.float32)

    @staticmethod
    def _wind_direction_is_from(data: Union[xr.DataArray, np.ndarray]) -> bool:
        """判断风向字段使用的是 from 还是 to 约定。"""
        if not isinstance(data, xr.DataArray):
            return True
        candidates = [
            str(data.name or ""),
            str(data.attrs.get("standard_name", "")),
            str(data.attrs.get("long_name", "")),
            str(data.attrs.get("direction_convention", "")),
        ]
        if any("from" in item.lower() for item in candidates):
            return True
        if any("to" in item.lower() for item in candidates):
            return False
        return True

    @staticmethod
    def _rotate_grid_components(
        uwind: np.ndarray, vwind: np.ndarray, angle_adjustment: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """旋转已有网格风分量以适配另一套网格方向。"""
        rotated_u = uwind * np.cos(angle_adjustment) + vwind * np.sin(angle_adjustment)
        rotated_v = vwind * np.cos(angle_adjustment) - uwind * np.sin(angle_adjustment)
        return rotated_u.astype(np.float32), rotated_v.astype(np.float32)

    def process(self, wind_speed: Union[xr.DataArray, np.ndarray], wind_direction: Union[xr.DataArray, np.ndarray], target_grid: Union[xr.DataArray, np.ndarray]) -> Tuple[Union[xr.DataArray, np.ndarray], Union[xr.DataArray, np.ndarray]]:
        """将风速风向解析为网格风分量。

        参数
        ----------
        wind_speed : Union[xr.DataArray, np.ndarray]
            风速场。
        wind_direction : Union[xr.DataArray, np.ndarray]
            风向场（相对真北角度）。
        target_grid : Union[xr.DataArray, np.ndarray]
            目标网格模板（通常为地形网格）。

        返回值
        -------
        tuple
            ``(uwind, vwind)``，类型与输入数据结构一致：
            - xarray 输入返回 ``xr.DataArray``；
            - numpy 输入返回 ``np.ndarray``。
        """
        wind_speed = _normalize_to_2d_field(wind_speed, "wind_speed")
        wind_direction = _normalize_to_2d_field(wind_direction, "wind_direction")
        target_grid = _normalize_to_2d_field(target_grid, "target_grid")

        if isinstance(target_grid, xr.DataArray):
            target_grid = _sort_spatial_dataarray(target_grid)
        speed_values, speed_units, speed_da = _prepare_input(wind_speed, "m s-1")
        direction_values, _, direction_da = _prepare_input(wind_direction, "degrees")
        if isinstance(speed_da, xr.DataArray):
            speed_values = convert_units(speed_da, "m s-1").astype(np.float64)
        else:
            speed_values = np.asarray(_convert_units(speed_values, speed_units, "m s-1"), dtype=np.float64)
        direction_reference = direction_da if direction_da is not None else wind_direction

        if isinstance(speed_da, xr.DataArray) and isinstance(target_grid, xr.DataArray):
            source_adjustment = self._calculate_true_north_offset(speed_da).astype(np.float64)
            angle = np.deg2rad(direction_values.astype(np.float64)) + source_adjustment
            if self._wind_direction_is_from(direction_reference):
                angle = angle + np.pi
            source_uwind = (speed_values * np.sin(angle)).astype(np.float32)
            source_vwind = (speed_values * np.cos(angle)).astype(np.float32)
            source_crs = _get_data_crs(speed_da)
            target_crs = _get_data_crs(target_grid)
            if source_crs is not None and target_crs is not None and not source_crs.equals(target_crs):
                source_y_name, source_x_name = _get_spatial_coord_names(speed_da)
                source_x_values = _coord_values_for_crs(speed_da.coords[source_x_name], source_crs)
                source_y_values = _coord_values_for_crs(speed_da.coords[source_y_name], source_crs)
                source_x_mesh, source_y_mesh = np.meshgrid(source_x_values, source_y_values)
                transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
                target_x_on_source, target_y_on_source = transformer.transform(source_x_mesh, source_y_mesh)
                target_adjustment = self._calculate_true_north_offset_for_points(
                    target_crs,
                    target_x_on_source,
                    target_y_on_source,
                    _estimate_grid_spacing_meters(target_grid),
                ).astype(np.float64)
                rotation = target_adjustment - source_adjustment
                source_uwind, source_vwind = self._rotate_grid_components(source_uwind, source_vwind, rotation)
            uwind_da = _make_field_on_target(source_uwind, "m s-1", speed_da, speed_da.attrs.copy())
            vwind_da = _make_field_on_target(source_vwind, "m s-1", speed_da, speed_da.attrs.copy())
            if _needs_regridding(uwind_da, target_grid):
                uwind_da = _regrid_scalar_field(uwind_da, target_grid)
            if _needs_regridding(vwind_da, target_grid):
                vwind_da = _regrid_scalar_field(vwind_da, target_grid)
            uwind_values = uwind_da.values
            vwind_values = vwind_da.values
            uwind = _make_field_on_target(uwind_values, "m s-1", target_grid)
            vwind = _make_field_on_target(vwind_values, "m s-1", target_grid)
            return uwind, vwind

        source_adjustment = np.zeros(speed_values.shape, dtype=np.float64)
        angle = np.deg2rad(direction_values.astype(np.float64)) + source_adjustment
        if self._wind_direction_is_from(direction_reference):
            angle = angle + np.pi
        uwind = (speed_values * np.sin(angle)).astype(np.float32)
        vwind = (speed_values * np.cos(angle)).astype(np.float32)
        return uwind, vwind


class MetaOrographicEnhancement(BasePlugin):
    """地形增强元插件（前处理与流程编排）。

    该类不直接计算增强值，而是负责组织输入并调度子插件。核心职责包括：

    1. 从多层温湿压/风场中提取边界层代表高度二维切片；
    2. 调用 :class:`ResolveWindComponents` 生成 ``u/v`` 风分量；
    3. 调用 :class:`OrographicEnhancement` 计算最终地形增强。

    设计上将“风场解析”和“增强计算”解耦，便于后续独立校验两个阶段。
    气象场选层后为二维；地形保持原始维度传入主算法，由
    :class:`OrographicEnhancement` 内部压维计算并按地形模板重组六维输出。
    """

    def __init__(self, boundary_height: float = 1000.0, boundary_height_units: str = "m"):
        """初始化元插件，指定从多层气象场中抽取的边界层代表高度。

        该高度作为边界层顶的代理层：对带 ``level`` 坐标的输入，选取与
        ``boundary_height`` 最接近的一层（允许偏差 0.1 个单位）；输入已是
        二维场时不再选层。

        参数
        ----------
        boundary_height : float, 默认 1000.0
            边界层代表高度，须与气象场 ``level`` 坐标在同一高度量纲下可比。
        boundary_height_units : str, 默认 ``m``
            ``boundary_height`` 的单位，同时用于把 ``level`` 坐标换算到同一单位后再选层。
        """
        self.boundary_height = boundary_height
        self.boundary_height_units = boundary_height_units

    @staticmethod
    def _extract_height_level(data: Union[xr.DataArray, np.ndarray], boundary_height: float, boundary_height_units: str) -> Union[xr.DataArray, np.ndarray]:
        """从输入场中提取边界层代表高度对应的二维切片。

        参数
        ----------
        data : Union[xr.DataArray, np.ndarray]
            输入场，可以是二维场，也可以是带 ``level`` 坐标的多层场（含标准六维网格）。
        boundary_height : float
            目标边界层代表高度。
        boundary_height_units : str
            目标边界层高度对应的单位。

        返回值
        -------
        Union[xr.DataArray, np.ndarray]
            提取后的二维场；若输入本身已经是二维，则直接返回排序后的原场。
        """
        # 按边界层代表高度在 level 坐标上选取最接近的一层。
        if not isinstance(data, xr.DataArray):
            if np.asarray(data).ndim > 2:
                raise ValueError("numpy 输入包含垂直维时，必须改用带 level 坐标的 xarray 输入")
            return data
        if data.ndim <= 2:
            return _sort_spatial_dataarray(data)
        level_coord = data.coords["level"]
        if (level_coord.attrs.get("units") or "").strip():
            level_values = convert_units(level_coord, boundary_height_units)
        else:
            level_values = _convert_units(level_coord.values, "m", boundary_height_units)
        index = int(np.argmin(np.abs(level_values - boundary_height)))
        if abs(float(level_values[index]) - boundary_height) > 0.1:
            raise ValueError(f"未找到高度 {boundary_height}{boundary_height_units} 附近的层次")
        result = data.isel({level_coord.dims[0]: index}, drop=True).squeeze(drop=True)
        if result.ndim != 2:
            raise ValueError("提取高度层后仍不是二维场")
        return _sort_spatial_dataarray(result)

    def process(self, temperature: Union[xr.DataArray, np.ndarray], humidity: Union[xr.DataArray, np.ndarray], pressure: Union[xr.DataArray, np.ndarray], wind_speed: Union[xr.DataArray, np.ndarray], wind_direction: Union[xr.DataArray, np.ndarray], orography: Union[xr.DataArray, np.ndarray]) -> xr.DataArray:
        """提取边界层输入并组织地形增强主流程。

        功能说明
        ----------
        从多层输入中提取边界层代表高度的二维温湿压和风场，完成风向解析、
        投影方向修正及必要的重采样，然后调用地形增强主算法。

        参数
        ----------
        temperature : Union[xr.DataArray, np.ndarray]
            温度场，可以是二维场，也可以是带 ``level`` 坐标的多层场。
        humidity : Union[xr.DataArray, np.ndarray]
            相对湿度场，可以是二维场，也可以是带 ``level`` 坐标的多层场。
        pressure : Union[xr.DataArray, np.ndarray]
            气压场，可以是二维场，也可以是带 ``level`` 坐标的多层场。
        wind_speed : Union[xr.DataArray, np.ndarray]
            风速场，可以是二维场，也可以是带 ``level`` 坐标的多层场。
        wind_direction : Union[xr.DataArray, np.ndarray]
            风向场，约定为相对真北的角度。
        orography : Union[xr.DataArray, np.ndarray]
            地形高度场，作为目标输出网格。

        返回值
        -------
        xr.DataArray
            地形增强结果，单位为 ``m s-1``。
            六维输出重组由 :class:`OrographicEnhancement` 根据地形维度完成。
        """
        # 入口阶段对 xarray 输入执行严格六维校验，避免隐式兼容改变语义。
        input_fields = {
            "temperature": temperature,
            "humidity": humidity,
            "pressure": pressure,
            "wind_speed": wind_speed,
            "wind_direction": wind_direction,
        }
        for name, field in input_fields.items():
            if isinstance(field, xr.DataArray):
                # 不做值域裁剪，避免气压/地形等高值被误置无效。
                input_fields[name] = meb.checkout_griddata(
                    field,
                    is_single=False,
                    valid_val=(-np.inf, np.inf, np.nan),
                )
        temperature = input_fields["temperature"]
        humidity = input_fields["humidity"]
        pressure = input_fields["pressure"]
        wind_speed = input_fields["wind_speed"]
        wind_direction = input_fields["wind_direction"]

        # 约化为边界层代表高度上的二维场，直接传入主算法。
        temperature = self._extract_height_level(temperature, self.boundary_height, self.boundary_height_units)
        humidity = self._extract_height_level(humidity, self.boundary_height, self.boundary_height_units)
        pressure = self._extract_height_level(pressure, self.boundary_height, self.boundary_height_units)
        wind_speed = self._extract_height_level(wind_speed, self.boundary_height, self.boundary_height_units)
        wind_direction = self._extract_height_level(wind_direction, self.boundary_height, self.boundary_height_units)

        if isinstance(orography, xr.DataArray):
            orography = meb.checkout_griddata(
                orography,
                is_single=True,
                valid_val=(-np.inf, np.inf, np.nan),
            )
        elif np.asarray(orography).ndim != 2:
            raise ValueError("orography 必须是二维单场")

        uwind, vwind = ResolveWindComponents()(wind_speed, wind_direction, orography)
        return OrographicEnhancement()(temperature, humidity, pressure, uwind, vwind, orography)


class OrographicEnhancement(BasePlugin):
    """地形增强主算法插件。

    该类实现地形增强的数值核心。``xarray`` 输入须为标准六维单场（前四维长度为 1），
    ``numpy`` 输入须为二维数组；计算内核在二维场上完成，六维输出由地形模板重组。
    主要步骤如下：

    1. 单位统一与网格对齐（必要时重采样到地形网格）；
    2. 计算地形梯度并得到迎风抬升项 ``v·gradZ``；
    3. 基于阈值条件生成掩码（地形高度、湿度、抬升强度）；
    4. 计算格点地形增强贡献（``mm h-1``）；
    5. 按风向回溯上游贡献并高斯加权叠加；
    6. 转换到 ``m s-1``，构造带坐标输出。

    参数阈值（地形、湿度、抬升、上游影响距离、云寿命、效率系数）
    与原算法保持一致，便于与官方结果对照验证。

    说明
    ----------
    该类是数值计算核心。即使输入为六维单场，也会先压缩到二维完成计算，
    再按模板重组输出，避免在三维/六维上重复实现同一套二维物理逻辑。
    """

    def __init__(self) -> None:
        self.orog_thresh_m = 20.0
        self.rh_thresh_ratio = 0.8
        self.vgradz_thresh_ms = 0.0005

        self.upstream_range_of_influence_km = 15.0
        self.cloud_lifetime_s = 102.0
        self.efficiency_factor = 0.23265

        #初始化类成员以存储重采样变量用于水汽增强计算
        self.temperature = None
        self.humidity = None
        self.pressure = None
        self.uwind = None
        self.vwind = None
        self.topography = None
        self.grid_spacing_km = None

    def __repr__(self) -> str:
        return "<OrographicEnhancement()>"

    def _prepare_field(self, data: Union[xr.DataArray, np.ndarray], default_unit: str, target: Optional[xr.DataArray] = None) -> Tuple[np.ndarray, Optional[xr.DataArray], str]:
        """统一单个输入场的单位、数组和值域网格。

        参数
        ----------
        data : Union[xr.DataArray, np.ndarray]
            输入场。
        default_unit : str
            默认单位。
        target : xr.DataArray, optional
            目标网格模板。

        返回值
        -------
        tuple
            - 数值数组
            - 可选的 xarray 数据场
            - 规范化后的单位字符串
        """
        values, units, data_array = _prepare_input(data, default_unit)
        if data_array is not None and target is not None and _needs_regridding(data_array, target):
            data_array = _regrid_scalar_field(data_array, target)
            values = np.asarray(data_array.values, dtype=np.float32)
        return values, data_array, units

    def _calculate_vgradz(self, uwind: np.ndarray, vwind: np.ndarray, topography: np.ndarray, y_spacing_m: float, x_spacing_m: float) -> np.ndarray:
        """计算迎风抬升项 ``v·gradZ`` 。

        参数
        ----------
        uwind : np.ndarray
            x 方向风分量。
        vwind : np.ndarray
            y 方向风分量。
        topography : np.ndarray
            地形高度场。
        y_spacing_m : float
            y 方向网格间距，单位为米。
        x_spacing_m : float
            x 方向网格间距，单位为米。

        返回值
        -------
        np.ndarray
            迎风抬升项数组。
        """
        # 先做与梯度方向垂直的三点平滑，再求地形梯度并与风矢量点乘。
        topo_for_gradx = uniform_filter1d(topography, 3, axis=0, mode="nearest")
        topo_for_grady = uniform_filter1d(topography, 3, axis=1, mode="nearest")
        grad_x = _regridded_adjacent_gradient(topo_for_gradx, x_spacing_m, axis=1)
        grad_y = _regridded_adjacent_gradient(topo_for_grady, y_spacing_m, axis=0)
        return (uwind * grad_x + vwind * grad_y).astype(np.float32)

    def _generate_mask(self, topography: np.ndarray, humidity: np.ndarray, vgradz: np.ndarray) -> np.ndarray:
        """生成不参与地形增强计算的掩码。

        参数
        ----------
        topography : np.ndarray
            地形高度场。
        humidity : np.ndarray
            相对湿度场。
        vgradz : np.ndarray
            迎风抬升项。

        返回值
        -------
        np.ndarray
            布尔掩码数组，``True`` 表示该点不参与计算。
        """
        # 只在地形、湿度和抬升条件都满足时，才计算地形增强。
        topo_nbhood = _square_neighbourhood_mean(topography, size=3)
        mask = np.full(topography.shape, False, dtype=bool)
        mask = np.where(topo_nbhood < self.orog_thresh_m, True, mask)
        mask = np.where(humidity < self.rh_thresh_ratio, True, mask)
        mask = np.where(np.abs(vgradz) < self.vgradz_thresh_ms, True, mask)
        mask = np.where(~np.isfinite(humidity), True, mask)
        mask = np.where(~np.isfinite(vgradz), True, mask)
        return mask

    def _point_orogenh(self, temperature: np.ndarray, humidity: np.ndarray, svp: np.ndarray, vgradz: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """计算格点尺度的地形增强贡献。

        参数
        ----------
        temperature : np.ndarray
            温度场。
        humidity : np.ndarray
            相对湿度场。
        svp : np.ndarray
            饱和水汽压场。
        vgradz : np.ndarray
            迎风抬升项。
        mask : np.ndarray
            计算掩码。

        返回值
        -------
        np.ndarray
            格点地形增强贡献，单位为 ``mm h-1`` 。
        """
        point_orogenh = np.zeros(temperature.shape, dtype=np.float32)
        valid_mask = np.logical_not(mask)
        if np.any(valid_mask):
            # 格点增强沿用原始经验公式，结果单位为 mm h-1。
            prefactor = 3600.0 / R_WATER_VAPOUR
            numerator = humidity[valid_mask] * svp[valid_mask] * vgradz[valid_mask]
            point_orogenh[valid_mask] = prefactor * numerator / temperature[valid_mask]
        return np.where(point_orogenh > 0, point_orogenh, 0).astype(np.float32)

    @staticmethod
    def _upstream_distances(max_roi: np.ndarray, max_sin_cos: np.ndarray, length: int) -> np.ndarray:
        """块内上游距离（格点）。超出该点 ``max_roi`` 的层记为 NaN。"""
        n_rows, n_cols = max_roi.shape
        dist = np.full((length, n_rows, n_cols), np.nan, dtype=np.float32)
        steps = np.arange(length, dtype=np.float32)[:, None, None]
        scale = np.asarray(max_sin_cos, dtype=np.float32)
        safe = np.where(scale > 0, scale, np.float32(1))
        filled = steps / safe[None, :, :]
        use = steps < max_roi[None, :, :]
        dist[use] = filled[use]
        return dist

    @staticmethod
    def _upstream_source_index(
        distance: np.ndarray,
        sin_wind_dir: np.ndarray,
        cos_wind_dir: np.ndarray,
        y0: int,
        n_cols: int,
        n_rows: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """把块内回溯距离换成上游格点索引，并限制在全域范围内。

        全程 float32，避免 ``arange`` 整型与 ``0.0`` 把 (length, ny, nx) 抬成 float64。
        非有限距离处 ``dist_safe=0``，索引落回当前格点。
        """
        _, n_chunk, _ = distance.shape
        xpos = np.arange(n_cols, dtype=np.float32)[None, None, :]
        ypos = np.arange(y0, y0 + n_chunk, dtype=np.float32)[None, :, None]
        sin = np.asarray(sin_wind_dir, dtype=np.float32)[None, :, :]
        cos = np.asarray(cos_wind_dir, dtype=np.float32)[None, :, :]
        dist = np.asarray(distance, dtype=np.float32)
        dist_safe = np.where(np.isfinite(dist), dist, np.float32(0.0))
        x_source = np.rint(xpos - dist_safe * sin).astype(np.int32)
        y_source = np.rint(ypos - dist_safe * cos).astype(np.int32)
        np.clip(x_source, 0, n_cols - 1, out=x_source)
        np.clip(y_source, 0, n_rows - 1, out=y_source)
        return x_source, y_source

    def _add_upstream_component(self, point_orogenh: np.ndarray) -> np.ndarray:
        """叠加上游格点对当前格点的增强贡献。

        参数
        ----------
        point_orogenh : np.ndarray
            格点地形增强贡献，单位为 ``mm h-1`` 。

        返回值
        -------
        np.ndarray
            叠加上游贡献后的地形增强结果，单位为 ``mm h-1`` 。
        """
        # 沿风向回溯有限距离，对上游格点增强做高斯加权平均。
        uwind = np.nan_to_num(self.uwind, nan=0.0).astype(np.float32)
        vwind = np.nan_to_num(self.vwind, nan=0.0).astype(np.float32)
        wind_speed = np.sqrt(np.square(uwind) + np.square(vwind)).astype(np.float32)
        moving_mask = np.logical_not(np.isclose(wind_speed, 0.0))
        sin_wind_dir = np.zeros(wind_speed.shape, dtype=np.float32)
        cos_wind_dir = np.zeros(wind_speed.shape, dtype=np.float32)
        sin_wind_dir[moving_mask] = uwind[moving_mask] / wind_speed[moving_mask]
        cos_wind_dir[moving_mask] = vwind[moving_mask] / wind_speed[moving_mask]
        max_sin_cos = np.where(
            np.abs(sin_wind_dir) > np.abs(cos_wind_dir),
            np.abs(sin_wind_dir),
            np.abs(cos_wind_dir),
        ).astype(np.float32, copy=False)
        upstream_roi = self.upstream_range_of_influence_km / self.grid_spacing_km
        max_roi = (upstream_roi * max_sin_cos).astype(np.int32)
        if np.max(max_roi) <= 0:
            return point_orogenh.astype(np.float32)
        length = int(np.max(max_roi))
        grid_spacing_m = 1000.0 * self.grid_spacing_km
        # 扩散尺度由风速和云寿命共同决定，二者越大，上游影响越远。
        stddev = (wind_speed * self.cloud_lifetime_s / grid_spacing_m).astype(np.float32)
        variance = np.square(stddev)
        # 上游贡献需分配 (length, ny, nx) 三维缓冲；大网格整域一次计算峰值内存过高。
        # 按行分块，块内公式与整域一次计算相同。行块高度按单块 float32 三维缓冲预算自适应：
        # row_chunk = clip(budget / (length * nx * 4), 下限 8, 上限 256)；
        # 预算指单个 (length, row_chunk, nx) 数组，不是循环内全部临时数组之和。
        ny, nx = wind_speed.shape
        weighted_values = np.zeros((ny, nx), dtype=np.float32)
        sum_of_weights = np.zeros((ny, nx), dtype=np.float32)
        point = np.asarray(point_orogenh, dtype=np.float32)
        max_chunk_bytes = 64 * 1024 * 1024
        row_chunk = max(8, min(256, max_chunk_bytes // (max(length, 1) * nx * 4)))
        half = np.float32(-0.5)
        for y0 in range(0, ny, row_chunk):
            y1 = min(ny, y0 + row_chunk)
            dist = self._upstream_distances(max_roi[y0:y1], max_sin_cos[y0:y1], length)
            x_source, y_source = self._upstream_source_index(
                dist, sin_wind_dir[y0:y1], cos_wind_dir[y0:y1], y0, nx, ny
            )
            source_values = point[y_source, x_source]
            var = variance[y0:y1]
            usable = np.isfinite(dist) & (var > 0)
            # 无效处 dist/var 置安全值，整段保持 float32，最后再掩回 0
            dist_u = np.where(usable, dist, np.float32(0.0))
            var_b = np.where(var > 0, var, np.float32(1.0))
            value_weight = np.exp(half * np.square(dist_u) / var_b).astype(np.float32, copy=False)
            value_weight = np.where(usable, value_weight, np.float32(0.0)).astype(
                np.float32, copy=False
            )
            sum_of_weights[y0:y1] = np.sum(value_weight, axis=0)
            weighted_values[y0:y1] = np.sum(source_values * value_weight, axis=0)
            del dist, x_source, y_source, source_values, value_weight, dist_u, usable
        valid_mask = moving_mask & (sum_of_weights > 0)
        weighted_values[valid_mask] = self.efficiency_factor * (
            weighted_values[valid_mask] / sum_of_weights[valid_mask]
        )
        return weighted_values.astype(np.float32)

    def process(self, temperature: Union[xr.DataArray, np.ndarray], humidity: Union[xr.DataArray, np.ndarray], pressure: Union[xr.DataArray, np.ndarray], uwind: Union[xr.DataArray, np.ndarray], vwind: Union[xr.DataArray, np.ndarray], topography: Union[xr.DataArray, np.ndarray]) -> xr.DataArray:
        """在目标地形网格上计算地形增强结果。

        功能说明
        ----------
        统一输入单位和网格后，计算迎风抬升、格点增强与上游贡献，
        最终输出地形增强场。

        参数
        ----------
        temperature : Union[xr.DataArray, np.ndarray]
            温度场。
        humidity : Union[xr.DataArray, np.ndarray]
            相对湿度场。
        pressure : Union[xr.DataArray, np.ndarray]
            气压场。
        uwind : Union[xr.DataArray, np.ndarray]
            网格 x 方向风分量。
        vwind : Union[xr.DataArray, np.ndarray]
            网格 y 方向风分量。
        topography : Union[xr.DataArray, np.ndarray]
            地形高度场，也是目标输出网格。

        返回值
        -------
        xr.DataArray
            地形增强结果，单位为 ``m s-1``。
            若地形为六维单场，输出重组为标准六维网格；否则输出二维场。
        """
        # --- 1. 保存六维地形模板（压维前）---
        # xarray 地形须为标准六维 meb 网格；模板用于最后重组输出并继承 grid_mapping_attrs 等属性。
        # numpy 二维地形无模板，输出为无坐标的二维 DataArray。
        topography_template_6d: Optional[xr.DataArray] = None
        if isinstance(topography, xr.DataArray):
            if set(topography.dims) != {"member", "level", "time", "dtime", "lat", "lon"}:
                raise ValueError(
                    "topography 的 xarray 输入必须是标准六维网格 "
                    "(member, level, time, dtime, lat, lon)"
                )
            topography_template_6d = topography.transpose(
                "member", "level", "time", "dtime", "lat", "lon"
            )

        # --- 2. 输入压维为二维计算场 ---
        # 六维单场（前四维长度为 1）squeeze 到 lat/lon；内核在二维上运算。
        temperature = _normalize_to_2d_field(temperature, "temperature")
        humidity = _normalize_to_2d_field(humidity, "humidity")
        pressure = _normalize_to_2d_field(pressure, "pressure")
        uwind = _normalize_to_2d_field(uwind, "uwind")
        vwind = _normalize_to_2d_field(vwind, "vwind")
        topography = _normalize_to_2d_field(topography, "topography")

        # --- 3. 地形作为目标网格，统一单位到 m ---
        topography_values, topography_units, topography_da = _prepare_input(topography, "m")
        if topography_values.ndim != 2:
            raise ValueError("topography 必须是二维场")
        if isinstance(topography_da, xr.DataArray):
            topography_values = convert_units(topography_da, "m")
        else:
            topography_values = np.asarray(_convert_units(topography_values, topography_units, "m"), dtype=np.float32)
        target_grid = topography_da if isinstance(topography_da, xr.DataArray) else None

        # --- 4. 各气象场对齐到地形网格并提取数组 ---
        temperature_values, temperature_da, temperature_units = self._prepare_field(temperature, "K", target_grid)
        humidity_values, humidity_da, humidity_units = self._prepare_field(humidity, "1", target_grid)
        pressure_values, pressure_da, pressure_units = self._prepare_field(pressure, "Pa", target_grid)
        uwind_values, uwind_da, uwind_units = self._prepare_field(uwind, "m s-1", target_grid)
        vwind_values, vwind_da, vwind_units = self._prepare_field(vwind, "m s-1", target_grid)
        for name, values in {"temperature": temperature_values, "humidity": humidity_values, "pressure": pressure_values, "uwind": uwind_values, "vwind": vwind_values}.items():
            if values.ndim != 2:
                raise ValueError(f"{name} 必须是二维场")
            if values.shape != topography_values.shape:
                raise ValueError(f"{name} 与 topography 的形状不一致")

        # --- 5. 单位换算到算法标准（K / 1 / Pa / m s-1）---
        if isinstance(temperature_da, xr.DataArray):
            temperature_values = convert_units(temperature_da, "K")
        else:
            temperature_values = np.asarray(_convert_units(temperature_values, temperature_units, "K"), dtype=np.float32)
        if isinstance(humidity_da, xr.DataArray):
            humidity_values = convert_units(humidity_da, "1")
        else:
            humidity_values = np.asarray(_convert_units(humidity_values, humidity_units, "1"), dtype=np.float32)
        if isinstance(pressure_da, xr.DataArray):
            pressure_values = convert_units(pressure_da, "Pa")
        else:
            pressure_values = np.asarray(_convert_units(pressure_values, pressure_units, "Pa"), dtype=np.float32)
        if isinstance(uwind_da, xr.DataArray):
            uwind_values = convert_units(uwind_da, "m s-1")
        else:
            uwind_values = np.asarray(_convert_units(uwind_values, uwind_units, "m s-1"), dtype=np.float32)
        if isinstance(vwind_da, xr.DataArray):
            vwind_values = convert_units(vwind_da, "m s-1")
        else:
            vwind_values = np.asarray(_convert_units(vwind_values, vwind_units, "m s-1"), dtype=np.float32)

        # --- 6. 网格距（用于梯度与上游回溯尺度）---
        # xarray：投影米制直接差分；真经纬（含无 units 的业务 meb）按度换算为米。
        # numpy：无坐标，沿用 1 km。
        if target_grid is not None:
            y_spacing_m, x_spacing_m = _grid_spacings_meters(target_grid)
        else:
            y_spacing_m, x_spacing_m = 1000.0, 1000.0

        self.temperature = temperature_values
        self.humidity = humidity_values
        self.pressure = pressure_values
        self.uwind = uwind_values
        self.vwind = vwind_values
        self.topography = topography_values
        self.grid_spacing_km = float((x_spacing_m + y_spacing_m) / 2.0 / 1000.0)

        # --- 7. 地形增强计算内核（二维）---
        vgradz = self._calculate_vgradz(self.uwind, self.vwind, self.topography, y_spacing_m, x_spacing_m)
        mask = self._generate_mask(self.topography, self.humidity, vgradz)
        svp = calculate_svp_in_air(self.temperature, self.pressure)
        point_orogenh = self._point_orogenh(self.temperature, self.humidity, svp, vgradz, mask)
        orogenh_mmh = self._add_upstream_component(point_orogenh)
        orogenh_ms = (orogenh_mmh / 3600000.0).astype(np.float32)  # mm/h → m/s

        # --- 8. 输出包装 ---
        if topography_template_6d is not None:
            result = rebuild_to_meb_griddata(
                orogenh_ms,
                topography_template_6d,
                name="orographic_enhancement",
                units="m s-1",
            )
            result.attrs.pop("standard_name", None)
            result.attrs["long_name"] = "orographic_enhancement"
            return result
        #输入为二维numpy数组，输出为无坐标的二维DataArray
        return xr.DataArray(
            orogenh_ms,
            attrs={"units": "m s-1", "long_name": "orographic_enhancement"},
            name="orographic_enhancement",
        )
