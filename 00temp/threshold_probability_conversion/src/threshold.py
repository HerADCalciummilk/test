#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""阈值概率转换算法。

迁移自 IMPROVER ``improver.threshold.Threshold``（硬阈值 + fuzzy + collapse_coord
+ vicinity；不含 LatitudeDependentThreshold）。

算法面向双输入：
- ``xarray.DataArray``：meteva_base 六维（``member, level, time, dtime, lat, lon``），
  阈值映射到 ``level``；
- ``numpy.ndarray``：输出 ``(n_threshold, *spatial_and_other_dims)``。
"""

from __future__ import annotations

import numbers
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import xarray as xr
from cf_units import Unit as CfUnit
from numpy import ndarray
from numpy.ma.core import MaskedArray

import meteva_base as meb
from threshold_probability_conversion.src.utils._comparison_operator import comparison_operator_dict
from threshold_probability_conversion.src.utils._grid import (
    distance_to_number_of_grid_cells,
    infer_equal_area_grid_spacing_m,
)
from threshold_probability_conversion.src.utils._regrid import prepare_grid_spacing_dataarray
from threshold_probability_conversion.src.utils._rescale import rescale
from threshold_probability_conversion.src.utils._vicinity import apply_vicinity_to_slices
from threshold_probability_conversion.utils.base_plugin import BasePlugin

FLOAT_DTYPE = np.float32

__all__ = ["Threshold"]


class Threshold(BasePlugin):
    """将诊断场转为相对阈值的 0–1 真值/概率场。

    支持硬阈值与 fuzzy 线性隶属；多阈值沿 ``level``（numpy 为第 0 维）堆叠。
    可选 ``collapse_coord`` 对集合成员和/或时间求平均得到概率场。
    """

    _ALLOWED_COLLAPSE = frozenset({"member", "time"})

    def __init__(
        self,
        threshold_values: Optional[Union[float, List[float]]] = None,
        threshold_config: Optional[Dict[str, Union[List[float], str]]] = None,
        fuzzy_factor: Optional[float] = None,
        threshold_units: Optional[str] = None,
        comparison_operator: str = ">",
        collapse_coord: Optional[Union[str, List[str]]] = None,
        collapse_cell_methods: Optional[Dict[str, str]] = None,
        vicinity: Optional[Union[float, List[float]]] = None,
        fill_masked: Optional[float] = None,
    ) -> None:
        """初始化阈值与 fuzzy 界。

        Parameters
        ----------
        threshold_values :
            阈值（可多个）。与 ``threshold_config`` 互斥。
        threshold_config :
            ``{"阈值": [下界, 上界]}`` 或 ``{"阈值": "None"}``。
        fuzzy_factor :
            (0, 1) 内的乘性模糊因子；不可与 config 中的显式界同时使用。
        threshold_units :
            阈值单位；若给出则先把数据换到该单位再比较。
        comparison_operator :
            ``> >= < <=`` / ``gt ge lt le``。
        collapse_coord :
            对 meb 非空间维求平均并压成长度 1。仅支持 ``member``、``time``
            及其组合。输入 ``level`` 须为 1（不参与压维）；``dtime`` 未实现。
        collapse_cell_methods :
            可选，记录压维所用统计方法，形如 ``{"member": "mean"}``。
        vicinity :
            邻域半径（米）列表；在 ``collapse_coord`` 之前对阈值真值场做方形邻域最大值。
            支持 xarray meb 六维：米制等距投影，或经纬网（经 ``nbhood`` LAEA 轴换算推断格距）。
        fill_masked :
            比较前用该值填充掩码点。
        """
        if threshold_config and threshold_values is not None:
            raise ValueError(
                "threshold_config and threshold_values are mutually exclusive "
                "arguments - please provide one or the other, not both"
            )
        if threshold_config is None and threshold_values is None:
            raise ValueError(
                "One of threshold_config or threshold_values must be provided."
            )

        thresholds, fuzzy_bounds = self._set_thresholds(
            threshold_values, threshold_config
        )
        self.thresholds = [thresholds] if np.isscalar(thresholds) else list(thresholds)
        self.threshold_units = (
            None if threshold_units is None else CfUnit(threshold_units)
        )

        fuzzy_factor_loc = 1.0
        if fuzzy_factor is not None:
            if fuzzy_bounds is not None:
                raise ValueError(
                    "Invalid combination of keywords. Cannot specify "
                    "both a fuzzy_factor and use a threshold_config that "
                    "specifies bounds."
                )
            if not 0 < fuzzy_factor < 1:
                raise ValueError(
                    "Invalid fuzzy_factor: must be >0 and <1: {}".format(fuzzy_factor)
                )
            if 0 in self.thresholds:
                raise ValueError(
                    "Invalid threshold with fuzzy factor: cannot use a "
                    "multiplicative fuzzy factor with threshold == 0, use "
                    "the threshold_config approach instead."
                )
            fuzzy_factor_loc = fuzzy_factor

        if fuzzy_bounds is None:
            self.fuzzy_bounds = self._generate_fuzzy_bounds(fuzzy_factor_loc)
        else:
            self.fuzzy_bounds = (
                [fuzzy_bounds] if isinstance(fuzzy_bounds, tuple) else list(fuzzy_bounds)
            )
            self._check_fuzzy_bounds()

        self.comparison_operator_dict = comparison_operator_dict()
        self.comparison_operator_string = comparison_operator
        self._decode_comparison_operator_string()
        self.collapse_coord = self._normalize_collapse_coord(collapse_coord)
        self.collapse_cell_methods = self._validate_collapse_cell_methods(
            collapse_cell_methods, self.collapse_coord
        )
        self.vicinity: Optional[List[float]] = None
        if vicinity is not None:
            if isinstance(vicinity, (list, tuple)):
                self.vicinity = [float(x) for x in vicinity]
            else:
                self.vicinity = [float(vicinity)]
        self.fill_masked = None if fill_masked is None else float(fill_masked)
        self.threshold_coord_name: Optional[str] = None
        self.original_units: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"<Threshold: thresholds={self.thresholds}, "
            f"operator={self.comparison_operator_string}>"
        )

    @staticmethod
    def _set_thresholds(
        threshold_values: Optional[Union[float, List[float]]],
        threshold_config: Optional[dict],
    ) -> Tuple[List[float], Optional[List[Tuple[float, float]]]]:
        """解析阈值列表与可选 fuzzy 界。"""
        if threshold_config:
            thresholds: List[float] = []
            fuzzy_bounds: Optional[List[Tuple[float, float]]] = []
            for key in threshold_config.keys():
                thresholds.append(float(key))
                if threshold_config[key] == "None":
                    fuzzy_bounds = None
                    continue
                if fuzzy_bounds is not None:
                    fuzzy_bounds.append(tuple(threshold_config[key]))
            return thresholds, fuzzy_bounds

        if isinstance(threshold_values, numbers.Number):
            threshold_values = [threshold_values]
        thresholds = [float(x) for x in threshold_values]
        return thresholds, None

    def _generate_fuzzy_bounds(
        self, fuzzy_factor_loc: float
    ) -> List[Tuple[float, float]]:
        """由 fuzzy_factor 生成各阈值上下界（因子为 1 时退化为硬阈值）。"""
        fuzzy_bounds = []
        for thr in self.thresholds:
            lower_thr = thr * fuzzy_factor_loc
            upper_thr = thr * (2.0 - fuzzy_factor_loc)
            if thr < 0:
                lower_thr, upper_thr = upper_thr, lower_thr
            fuzzy_bounds.append((lower_thr, upper_thr))
        return fuzzy_bounds

    def _check_fuzzy_bounds(self) -> None:
        """校验显式 fuzzy 界包含对应阈值。"""
        for thr, bounds in zip(self.thresholds, self.fuzzy_bounds):
            if len(bounds) != 2:
                raise ValueError(
                    "Invalid bounds for one threshold: {}."
                    " Expected 2 floats.".format(bounds)
                )
            if bounds[0] > thr or bounds[1] < thr:
                raise ValueError(
                    "Threshold must be within bounds: "
                    "!( {} <= {} <= {} )".format(bounds[0], thr, bounds[1])
                )

    def _decode_comparison_operator_string(self) -> None:
        """解析比较符字符串。"""
        try:
            self.comparison_operator = self.comparison_operator_dict[
                self.comparison_operator_string
            ]
        except KeyError as exc:
            raise ValueError(
                f'String "{self.comparison_operator_string}" '
                "does not match any known comparison_operator method"
            ) from exc

    @classmethod
    def _normalize_collapse_coord(
        cls, collapse_coord: Optional[Union[str, List[str]]]
    ) -> Optional[List[str]]:
        """校验并规范化可压维名（仅 ``member`` / ``time``）。"""
        if collapse_coord is None:
            return None
        if isinstance(collapse_coord, str):
            collapse_coord = [collapse_coord]

        normalized: List[str] = []
        for name in collapse_coord:
            if name not in cls._ALLOWED_COLLAPSE:
                raise ValueError(
                    'collapse_coord 仅支持 "member" 与 "time" 及其组合。'
                )
            if name not in normalized:
                normalized.append(name)
        return normalized

    @classmethod
    def _validate_collapse_cell_methods(
        cls,
        collapse_cell_methods: Optional[Dict[str, str]],
        collapse_coord: Optional[List[str]],
    ) -> Optional[Dict[str, str]]:
        """校验 cell method 仅作用于 collapse 维。"""
        if collapse_cell_methods is None:
            return None
        if collapse_coord is None:
            raise ValueError(
                "Cannot apply cell methods without collapsing a coordinate."
            )
        normalized: Dict[str, str] = {}
        for key, method in collapse_cell_methods.items():
            if key not in collapse_coord:
                raise ValueError(
                    "Cell methods can only be defined for coordinates that "
                    "are being collapsed."
                )
            normalized[key] = method
        return normalized

    def _validate_collapse_dims_present(self, input_data: xr.DataArray) -> None:
        """确认待压维在输入中存在。"""
        if self.collapse_coord is None:
            return
        missing = [d for d in self.collapse_coord if d not in input_data.dims]
        if missing:
            raise ValueError(
                "Cannot collapse over coordinates not present in the input_cube. "
                f"collapse_coords: {self.collapse_coord}\n"
                f"input_dims: {list(input_data.dims)}"
            )

    def _collapse_truth_stack(
        self,
        truths: ndarray,
        mask: Optional[ndarray],
        collapse_dims: List[str],
    ) -> Tuple[ndarray, Optional[ndarray]]:
        """对 ``(..., member, time, dtime, lat, lon)`` 真值堆叠做加权平均。"""
        dim_to_axis = {
            "member": truths.ndim - 5,
            "time": truths.ndim - 4,
            "dtime": truths.ndim - 3,
        }
        collapse_axes = tuple(dim_to_axis[d] for d in collapse_dims)

        if mask is not None:
            contrib = (~mask).astype(np.float64)
        else:
            contrib = np.ones(truths.shape[1:], dtype=np.float64)

        truth_sum = np.sum(truths, axis=collapse_axes, dtype=np.float64, keepdims=True)
        contrib_axes = tuple(a - 1 for a in collapse_axes)
        contrib_sum = np.sum(contrib, axis=contrib_axes, keepdims=True)

        with np.errstate(invalid="ignore", divide="ignore"):
            collapsed = (truth_sum / contrib_sum).astype(FLOAT_DTYPE)

        if mask is not None:
            invalid = contrib_sum <= 0
            if np.any(invalid):
                out_mask = np.broadcast_to(invalid, collapsed.shape)
                collapsed = np.ma.array(collapsed, mask=out_mask)
        return collapsed, contrib_sum

    @staticmethod
    def _in_vicinity_probability_name(base_name: str) -> str:
        """``probability_of_X_above_threshold`` → ``..._in_vicinity_above_threshold``。"""
        for suffix in ("_above_threshold", "_below_threshold"):
            if base_name.endswith(suffix):
                stem = base_name[: -len(suffix)]
                return f"{stem}_in_vicinity{suffix}"
        return f"{base_name}_in_vicinity"

    def _prepare_landmask(
        self,
        landmask: Optional[Union[xr.DataArray, ndarray]],
        spatial_shape: Tuple[int, int],
    ) -> Optional[ndarray]:
        """将海陆掩码规范为与空间切片一致的 bool 二维数组。"""
        if landmask is None:
            return None
        if isinstance(landmask, xr.DataArray):
            work = landmask
            if set(work.dims) >= {"lat", "lon"}:
                work = work.transpose(..., "lat", "lon")
            values = np.asarray(work.values, dtype=np.float32)
            while values.ndim > 2:
                values = values[0]
        else:
            values = np.asarray(landmask)
            while values.ndim > 2:
                values = values[0]
        if values.shape != spatial_shape:
            raise ValueError(
                f"landmask 空间形状须与输入一致，"
                f"landmask={values.shape}, expected={spatial_shape}"
            )
        return values.astype(bool)

    def _apply_vicinity_if_configured(
        self,
        stacked: ndarray,
        input_data: xr.DataArray,
        landmask: Optional[ndarray],
    ) -> Union[ndarray, List[ndarray]]:
        """对阈值堆叠结果施加邻域内最大值。

        单半径返回六维数组；多半径返回各半径对应的六维数组列表。
        """
        if self.vicinity is None:
            return stacked
        spacing_m = infer_equal_area_grid_spacing_m(input_data)
        grid_point_radii = [
            distance_to_number_of_grid_cells(radius, spacing_m)
            for radius in self.vicinity
        ]
        return apply_vicinity_to_slices(stacked, grid_point_radii, landmask)

    @staticmethod
    def _vicinity_variable_suffix(radius_m: float) -> str:
        """多半径 Dataset 变量名后缀，如 ``_r10000``。"""
        if np.isclose(radius_m, round(radius_m)):
            return f"_r{int(round(radius_m))}"
        return f"_r{radius_m}".replace(".", "p")

    def _probability_base_name(self) -> str:
        """生成概率场基名（不含多半径后缀）。"""
        relative = (
            "below"
            if "less_than" in self.comparison_operator.spp_string
            else "above"
        )
        out_name = (
            f"probability_of_{self.threshold_coord_name}_{relative}_threshold"
        )
        if self.vicinity is not None:
            out_name = self._in_vicinity_probability_name(out_name)
        return out_name

    def _assemble_meb_probability_array(
        self,
        stacked: ndarray,
        input_data: xr.DataArray,
        thr_points: ndarray,
        *,
        vicinity_radius_m: Optional[float] = None,
        array_name: Optional[str] = None,
        include_radius_coord: bool = True,
    ) -> xr.DataArray:
        """将 ``(n_thr, member, time, dtime, lat, lon)`` 堆叠转为 meb 六维 DataArray。"""
        if stacked.ndim != 6:
            raise ValueError(
                "meb 阈值堆叠后应为六维 (n_thr,member,time,dtime,lat,lon)，"
                f"当前 shape={stacked.shape}"
            )
        if isinstance(stacked, np.ma.MaskedArray):
            output_mask = stacked.mask
            stacked = np.ma.filled(stacked, np.nan)
        else:
            output_mask = None

        stacked = np.transpose(stacked, (1, 0, 2, 3, 4, 5))
        out_dims = ("member", "level", "time", "dtime", "lat", "lon")
        out_name = array_name if array_name is not None else self._probability_base_name()

        out_coords = {
            "member": input_data.coords["member"],
            "level": thr_points,
            "time": input_data.coords["time"],
            "dtime": input_data.coords["dtime"],
            "lat": input_data.coords["lat"],
            "lon": input_data.coords["lon"],
        }
        if vicinity_radius_m is not None and include_radius_coord:
            out_coords["radius_of_vicinity"] = float(vicinity_radius_m)
        if self.collapse_coord is not None:
            for dim in self.collapse_coord:
                out_coords[dim] = self._collapsed_dim_coord(input_data, dim)

        result = xr.DataArray(
            np.asarray(stacked, dtype=FLOAT_DTYPE),
            dims=out_dims,
            coords=out_coords,
            name=out_name,
        )
        if output_mask is not None:
            result = result.where(~output_mask)
        result.attrs = {}
        gm = input_data.attrs.get("grid_mapping_attrs")
        if gm is not None:
            result.attrs["grid_mapping_attrs"] = gm
        meb.set_griddata_attrs(result, units="1", is_default=True)
        result.attrs["relative_to_threshold"] = self.comparison_operator.spp_string
        result.attrs["spp__relative_to_threshold"] = self.comparison_operator.spp_string
        if self.collapse_coord is not None:
            result.attrs["collapsed_coords"] = list(self.collapse_coord)
            if self.collapse_cell_methods is not None:
                result.attrs["collapse_cell_methods"] = dict(self.collapse_cell_methods)
        if vicinity_radius_m is not None:
            result.attrs["radius_of_vicinity"] = float(vicinity_radius_m)
            result.attrs["radius_of_vicinity_units"] = "m"
        result.coords["level"].attrs["units"] = str(self.original_units)
        return result

    def _assemble_multi_vicinity_dataset(
        self,
        stacked_by_radius: List[ndarray],
        input_data: xr.DataArray,
        thr_points: ndarray,
    ) -> xr.Dataset:
        """多半径 vicinity：每个半径一个六维变量。"""
        if self.vicinity is None or len(self.vicinity) != len(stacked_by_radius):
            raise ValueError("多半径 vicinity 输出与半径列表长度不一致。")
        base_name = self._probability_base_name()
        data_vars = {}
        for radius_m, stacked in zip(self.vicinity, stacked_by_radius):
            var_name = f"{base_name}{self._vicinity_variable_suffix(radius_m)}"
            data_vars[var_name] = self._assemble_meb_probability_array(
                stacked,
                input_data,
                thr_points,
                vicinity_radius_m=float(radius_m),
                array_name=var_name,
                include_radius_coord=False,
            )
        return xr.Dataset(data_vars)

    def _collapsed_dim_coord(
        self,
        input_data: xr.DataArray,
        dim: str,
    ) -> xr.DataArray:
        """压维后保留 meb 六维占位坐标（长度 1）。"""
        coord = input_data.coords[dim]
        if dim == "member":
            return xr.DataArray(np.array([0], dtype=np.int32), dims=("member",))
        if dim == "time":
            return coord.isel({dim: 0}, drop=False)
        return coord.isel({dim: 0}, drop=False)

    def _calculate_truth_value(
        self,
        data: ndarray,
        threshold: float,
        bounds: Tuple[float, float],
        data_dtype: Any,
    ) -> ndarray:
        """对数组做硬阈值或 fuzzy 比较，返回 float32 真值。"""
        # 阈值与数据同 dtype，避免精度导致 == 比较偏差
        threshold_cast = np.float64(threshold).astype(data_dtype)
        if bounds[0] == bounds[1]:
            truth_value = self.comparison_operator.function(data, threshold_cast)
        else:
            truth_value = np.where(
                data < threshold_cast,
                rescale(
                    data,
                    data_range=(bounds[0], threshold_cast),
                    scale_range=(0.0, 0.5),
                    clip=True,
                ),
                rescale(
                    data,
                    data_range=(threshold_cast, bounds[1]),
                    scale_range=(0.5, 1.0),
                    clip=True,
                ),
            )
            if np.ma.is_masked(data):
                truth_value = np.where(data.mask, 0, truth_value)
                truth_value = np.ma.masked_array(truth_value, mask=data.mask)
            # 「小于」类比较：取超过概率的补
            if "less_than" in self.comparison_operator.spp_string:
                truth_value = 1.0 - truth_value

        return np.asarray(truth_value, dtype=FLOAT_DTYPE)

    def _thresholds_in_original_units(self) -> np.ndarray:
        """输出用：把阈值从 threshold_units 换回原场单位。"""
        thr = np.asarray(self.thresholds, dtype=np.float64)
        if self.threshold_units is None or self.original_units is None:
            return thr.astype(FLOAT_DTYPE)
        converted = self.threshold_units.convert(thr, CfUnit(self.original_units))
        return np.asarray(converted, dtype=FLOAT_DTYPE)

    def _prepare_data_array(
        self, values: ndarray, data_units: Optional[str]
    ) -> Tuple[ndarray, Optional[ndarray]]:
        """填充掩码、单位换算到 threshold_units，返回计算用数组与掩码。"""
        mask = None
        if np.ma.isMaskedArray(values):
            if self.fill_masked is not None:
                data = np.ma.filled(values, self.fill_masked)
            else:
                mask = np.ma.getmaskarray(values)
                data = np.ma.array(values.data, mask=mask)
        else:
            data = np.asarray(values)
            if self.fill_masked is not None and np.isnan(data).any():
                # DataArray 路径海点常用 NaN；fill_masked 时替换
                data = np.where(np.isnan(data), self.fill_masked, data)

        if self.threshold_units is not None:
            src_units = data_units or "1"
            data_plain = np.ma.filled(data, np.nan) if np.ma.isMaskedArray(data) else data
            converted = CfUnit(src_units).convert(
                np.asarray(data_plain, dtype=np.float64), self.threshold_units
            )
            # 与 IMPROVER cube.convert_units 一致：换算后在 float32 上与阈值比较
            converted = np.asarray(converted, dtype=FLOAT_DTYPE)
            if mask is not None and self.fill_masked is None:
                data = np.ma.array(converted, mask=mask)
            else:
                data = converted

        if np.ma.isMaskedArray(data):
            visible = data.data[~np.ma.getmaskarray(data)]
            if visible.size and np.isnan(visible).any():
                raise ValueError("Error: NaN detected in input cube data")
        elif np.isnan(np.asanyarray(data)).any():
            raise ValueError("Error: NaN detected in input cube data")

        return data, mask

    def process(
        self,
        input_data: Union[xr.DataArray, ndarray],
        *,
        data_units: Optional[str] = None,
        landmask: Optional[Union[xr.DataArray, ndarray]] = None,
    ) -> Union[xr.DataArray, xr.Dataset, ndarray, MaskedArray]:
        """对输入场施加阈值，返回 0–1 概率/真值场。

        Parameters
        ----------
        input_data :
            诊断场。DataArray 须为 meb 六维；ndarray 任意形状（阈值堆在第 0 维）。
        data_units :
            numpy 路径在指定 ``threshold_units`` 时用于单位换算；DataArray 默认读
            ``attrs["units"]``。
        landmask :
            与空间维同形的海陆掩码（``True`` 为陆）；仅在与 ``vicinity`` 联用时有效。

        Returns
        -------
        xr.DataArray, xr.Dataset, ndarray or MaskedArray
            概率场；DataArray 的 ``level`` 为阈值坐标（原场单位）。
            多半径 ``vicinity`` 时返回 Dataset，每个半径一个六维变量。
        """
        is_xarray = isinstance(input_data, xr.DataArray)

        if not is_xarray and self.collapse_coord is not None:
            raise ValueError(
                "collapse_coord 仅支持 xarray.DataArray（meb 六维）输入。"
            )
        if not is_xarray and self.vicinity is not None:
            raise ValueError("vicinity 仅支持 xarray.DataArray（meb 六维）输入。")
        if self.vicinity is None and landmask is not None:
            raise ValueError("未设置 vicinity 时不能传入 landmask。")

        if is_xarray:
            unbounded = (-np.inf, np.inf, np.nan)
            input_data = meb.checkout_griddata(input_data, valid_val=unbounded)
            self._validate_collapse_dims_present(input_data)
            self.threshold_coord_name = input_data.name or "diagnostic"
            self.original_units = str(input_data.attrs.get("units", "1"))
            units_for_convert = self.original_units
            raw_values = input_data.values
            if np.ma.isMaskedArray(raw_values):
                values = np.ma.asarray(raw_values, dtype=np.float32)
            else:
                values = np.asarray(raw_values, dtype=np.float32)
            fill_value = input_data.attrs.get("_FillValue")
            if fill_value is not None and not np.ma.isMaskedArray(values):
                values = np.ma.masked_equal(values, float(fill_value))
            elif not np.ma.isMaskedArray(values) and np.isnan(values).any():
                # CF 解码后缺测常为 NaN；meb 路径按掩码处理（numpy 路径仍报错）
                values = np.ma.masked_invalid(values)
            # 输入 level 占位长度为 1：去掉后再算，结果写回 level=阈值
            if values.ndim == 6 and values.shape[1] == 1:
                values = values[:, 0, ...]
            elif "level" in input_data.dims and input_data.sizes["level"] != 1:
                raise ValueError(
                    "阈值插件要求输入 level 长度为 1（诊断场占位），"
                    f"当前 sizes['level']={input_data.sizes['level']}"
                )
        else:
            self.threshold_coord_name = "diagnostic"
            self.original_units = data_units or "1"
            units_for_convert = data_units
            # 保留 MaskedArray，供 fill_masked / 掩码传播使用
            values = (
                input_data
                if isinstance(input_data, np.ma.MaskedArray)
                else np.asarray(input_data)
            )

        data, mask = self._prepare_data_array(values, units_for_convert)

        truths = []
        for threshold, bounds in zip(self.thresholds, self.fuzzy_bounds):
            truth = self._calculate_truth_value(
                data, threshold, bounds, np.asanyarray(data).dtype
            )
            if mask is not None and self.fill_masked is None:
                truth = np.ma.array(np.ma.filled(truth, 0), mask=mask)
            truths.append(np.asarray(truth, dtype=FLOAT_DTYPE))

        stacked = np.stack(truths, axis=0)
        thr_points = self._thresholds_in_original_units()

        landmask_2d: Optional[ndarray] = None
        multi_vicinity = self.vicinity is not None and len(self.vicinity) > 1
        if is_xarray and self.vicinity is not None:
            # 经纬输入：LAEA 轴换算后推断格距；格点值与输出坐标仍用原经纬
            spacing_input = prepare_grid_spacing_dataarray(input_data)
            spatial_shape = stacked.shape[-2:]
            landmask_2d = self._prepare_landmask(landmask, spatial_shape)
            if mask is not None:
                lead = stacked.ndim - mask.ndim
                expanded_mask = mask.reshape((1,) * lead + mask.shape)
                # 掩码点在邻域滤波前置 -inf，避免以 0 参与最大值（与 IMPROVER 一致）
                stacked = np.where(expanded_mask, -np.inf, stacked)
            vicinity_result = self._apply_vicinity_if_configured(
                stacked, spacing_input, landmask_2d
            )
            if mask is not None:
                if isinstance(vicinity_result, list):
                    vicinity_result = [
                        np.where(expanded_mask, 0.0, layer) for layer in vicinity_result
                    ]
                else:
                    vicinity_result = np.where(expanded_mask, 0.0, vicinity_result)
            stacked = vicinity_result

        if is_xarray and self.collapse_coord is not None:
            if isinstance(stacked, list):
                collapsed = []
                for layer in stacked:
                    collapsed_layer, _ = self._collapse_truth_stack(
                        layer, mask, self.collapse_coord
                    )
                    collapsed.append(collapsed_layer)
                stacked = collapsed
            else:
                stacked, _ = self._collapse_truth_stack(
                    stacked, mask, self.collapse_coord
                )

        if not is_xarray:
            if mask is not None and self.fill_masked is None:
                stacked_mask = np.broadcast_to(mask, stacked.shape)
                return np.ma.array(stacked, mask=stacked_mask)
            return stacked

        if multi_vicinity:
            if not isinstance(stacked, list):
                raise ValueError("多半径 vicinity 应得到六维数组列表。")
            return self._assemble_multi_vicinity_dataset(
                stacked, input_data, thr_points
            )

        if isinstance(stacked, list):
            raise ValueError("单半径 vicinity 不应得到数组列表。")

        vicinity_radius_m = (
            float(self.vicinity[0]) if self.vicinity is not None else None
        )
        return self._assemble_meb_probability_array(
            stacked,
            input_data,
            thr_points,
            vicinity_radius_m=vicinity_radius_m,
        )
