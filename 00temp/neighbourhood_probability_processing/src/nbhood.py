#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""适配 meteva_base 的邻域处理算法。

本模块迁移自 Improver 的 nbhood 算法，实现了面向 ``xarray.DataArray``
与 ``numpy.ndarray`` 的邻域平均、邻域求和和邻域百分位计算。
"""

from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import xarray as xr

import meteva_base as meb
from numpy import ndarray
from scipy.ndimage import correlate

from neighbourhood_probability_processing.utils.base_plugin import PostProcessingPlugin
from neighbourhood_probability_processing.utils.utils import rebuild_to_meb_griddata
from neighbourhood_probability_processing.src.utils._grid import (
    _distance_to_number_of_grid_cells,
    _extract_lead_times_from_xarray,
    _infer_grid_spacing_from_xarray,
    _parse_grid_spacing,
)
from neighbourhood_probability_processing.src.utils._helpers import (
    _as_iterable,
    _extract_data_array,
    _slice_lead_times_for_reshaped_data,
    apply_missing_fill,
    radius_by_lead_time,
)
from neighbourhood_probability_processing.src.utils._kernels import _boxsum, _pad_and_roll
from neighbourhood_probability_processing.src.utils._regrid import prepare_geographic_input, restore_geographic_output

# 默认百分位序列
DEFAULT_PERCENTILES = (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0)

__all__ = [
    "BaseNeighbourhoodProcessing",
    "GeneratePercentilesFromANeighbourhood",
    "NeighbourhoodProcessing",
    "check_radius_against_distance",
    "circular_kernel",
]


def check_radius_against_distance(
    radius: float,
    y_coords: Optional[ndarray] = None,
    x_coords: Optional[ndarray] = None,
    shape: Optional[Tuple[int, int]] = None,
    grid_spacing: Optional[Union[float, Tuple[float, float]]] = None,
) -> None:
    """检查邻域半径不超过空间域尺寸。"""
    if y_coords is not None and x_coords is not None:
        y_extent = float(np.max(y_coords) - np.min(y_coords))
        x_extent = float(np.max(x_coords) - np.min(x_coords))
    elif shape is not None and grid_spacing is not None:
        y_spacing, x_spacing = _parse_grid_spacing(grid_spacing)
        y_extent = (shape[0] - 1) * y_spacing
        x_extent = (shape[1] - 1) * x_spacing
    else:
        raise ValueError("必须提供空间坐标或 shape + grid_spacing")
    max_allowed = np.sqrt(x_extent**2 + y_extent**2) * 0.5
    if radius > max_allowed:
        raise ValueError(f"邻域半径 {radius} 米超过空间域允许的最大距离 {max_allowed} 米")


def circular_kernel(ranges: int, weighted_mode: bool) -> ndarray:
    """构造圆形邻域核。"""
    area = ranges * ranges
    kernel = np.ones((int(1 + ranges * 2), int(1 + ranges * 2)), dtype=np.float64)
    open_grid = np.array(
        np.ogrid[[slice(-x, x + 1) for x in (ranges, ranges)]], dtype=object
    )
    if weighted_mode:
        open_grid_summed_squared = np.sum(open_grid**2.0).astype(float)
        kernel[:] = (area - open_grid_summed_squared) / area
        mask = kernel < 0.0
    else:
        mask = np.reshape(np.sum(open_grid**2) > area, kernel.shape)
    kernel[mask] = 0.0
    return kernel


class BaseNeighbourhoodProcessing(PostProcessingPlugin):
    """邻域处理基础类。

    负责邻域算法共享的前置逻辑：
      1. 校验半径与时效参数
      2. 校验所有输入路径上的未掩码 ``NaN``（与上游 IMPROVER 一致）
      3. 在配置 ``lead_times`` 时按输入时效插值得到当前半径
      4. 在工具可用时校验 xarray 网格格式

    Parameters
    ----------
    radii : float or list[float]
        邻域半径，单位米。
    lead_times : list[int], optional
        与 ``radii`` 对应的时效序列，单位小时。必须与 radii 长度一致。

    Raises
    ------
    ValueError
        当 radii 与 lead_times 长度不一致时。

    Notes
    -----
    本类不执行具体的邻域统计计算，仅为子类提供共享的输入校验和半径插值功能。
    """

    def __init__(
        self, radii: Union[float, List[float]], lead_times: Optional[List[int]] = None
    ) -> None:
        radius_or_radii, parsed_lead_times = radius_by_lead_time(radii, lead_times)
        if isinstance(radius_or_radii, list):
            self.radii = [float(x) for x in radius_or_radii]
        else:
            self.radius = float(radius_or_radii)
            self.radii = [self.radius]
        self.lead_times = parsed_lead_times
        if self.lead_times is not None and len(self.radii) != len(self.lead_times):
            raise ValueError(
                "radii 与 lead_times 的长度不一致，无法继续处理。"
            )

    def _find_radii(self, input_lead_times: Optional[ndarray] = None) -> Union[float, ndarray]:
        """根据时效插值获取半径。

        参数
        ----------
        input_lead_times : ndarray, optional
            输入数据对应的时效，单位为小时。

        返回值
        -------
        float 或 ndarray
            插值后的邻域半径。
        """
        if input_lead_times is None:
            raise ValueError("设置了 lead_times 时必须提供 input_lead_times")
        return np.interp(input_lead_times, self.lead_times, self.radii)

    def process(
        self,
        data: Union[xr.DataArray, ndarray],
        input_lead_times: Optional[Union[float, ndarray]] = None,
    ) -> Union[xr.DataArray, ndarray]:
        """
        执行基础输入校验并准备当前半径。

        本方法不执行邻域统计，只完成前置处理并原样返回输入对象，
        供子类继续计算。

        参数
        ----------
        data : xr.DataArray 或 ndarray
            输入数据。
        input_lead_times : float 或 ndarray, optional
            输入时效（小时）。当配置 ``lead_times`` 且输入为 ndarray 时，
            必须显式提供。

        返回
        -------
        xr.DataArray 或 ndarray
            原样返回输入对象。
        """
        # 拦截裸 NaN；内部掩码仅通过 MaskedArray.mask 表达。
        if isinstance(data, xr.DataArray):
            data = meb.checkout_griddata(data, valid_val=(-np.inf, np.inf, np.nan))
            values = np.asarray(data.values)
            if np.isnan(values).any():
                raise ValueError("输入数据中存在未掩码的 NaN 值。")
        else:
            values = _extract_data_array(data)
            if np.ma.isMaskedArray(values):
                raw_values = np.ma.getdata(values)
                raw_mask = np.ma.getmaskarray(values)
                if np.isnan(raw_values[~raw_mask]).any():
                    raise ValueError("输入数据中存在未掩码的 NaN 值。")
            elif np.isnan(values).any():
                raise ValueError("输入数据中存在未掩码的 NaN 值。")

        if self.lead_times is not None:
            if input_lead_times is None:
                if isinstance(data, xr.DataArray):
                    input_lead_times = _extract_lead_times_from_xarray(data)
                else:
                    raise ValueError(
                        "numpy.ndarray 输入在设置 lead_times 时必须显式提供 "
                        "input_lead_times"
                    )
            lead_values = np.asarray(input_lead_times, dtype=np.float64)
            self.radius = self._find_radii(input_lead_times=lead_values)
        return data


class NeighbourhoodProcessing(BaseNeighbourhoodProcessing):
    """邻域均值/邻域和处理插件。

    以输入最后两维作为空间维 (y, x)，按前导维逐片执行邻域统计。
    支持方形/圆形邻域、可选加权圆核、外部掩码与输出重掩码。

    Parameters
    ----------
    neighbourhood_method : {"square", "circular"}
        邻域形状：
        - "square": 方形邻域
        - "circular": 圆形邻域
    radii : float or list[float]
        邻域半径，单位米。
    lead_times : list[int], optional
        与 radii 对应的时效序列，单位小时。
    weighted_mode : bool, default=False
        是否使用加权圆核，仅在 ``neighbourhood_method="circular"`` 时有效。
    sum_only : bool, default=False
        输出类型控制：
        - True: 输出邻域和
        - False: 输出邻域均值
    re_mask : bool, default=True
        是否在输出中标记无效格点。
        ``MaskedArray`` 路径返回 ``MaskedArray``：无效位**数值**仍为邻域统计结果，以 ``mask`` 标记（与上游 IMPROVER 一致）。
        ``DataArray`` 六维路径在 ``re_mask=True`` 时将无效格点写为 ``NaN``，供 CLI 以 float32 直写 NetCDF 保留缺测；``re_mask=False`` 时无效位保留邻域统计值。

    Raises
    ------
    ValueError
        1. neighbourhood_method 不是 "square" 或 "circular"
        2. weighted_mode 为 True 但 neighbourhood_method 不是 "circular"
        3. 邻域半径超过空间域允许的最大距离
        4. 空间坐标不是等间距网格
        5. x 和 y 方向的网格间距不一致

    Notes
    -----
    1. 对于 xarray.DataArray 输入，会自动推断网格间距和空间坐标。
    2. 对于 numpy.ndarray 输入，必须显式提供 grid_spacing 参数。
    3. 当输入为标准 meb 六维 xarray.DataArray 时，输出会重组为六维 xarray，
       保持维度顺序为 ("member", "level", "time", "dtime", "lat", "lon")。
    4. 加权圆形邻域核的权重由公式 ``(area - r²)/area`` 计算，其中 r 为到中心点的距离。

    Examples
    --------
    >>> import numpy as np
    >>> from neighbourhood_probability_processing import NeighbourhoodProcessing
    >>> 
    >>> # 创建示例数据
    >>> data = np.random.rand(10, 20, 30)  # 前导维 + 空间维
    >>> 
    >>> # 圆形邻域均值，半径 2000 米
    >>> processor = NeighbourhoodProcessing(
    ...     neighbourhood_method="circular",
    ...     radii=2000.0
    ... )
    >>> result = processor.process(data, grid_spacing=1000.0)
    """

    def __init__(
        self,
        neighbourhood_method: str,
        radii: Union[float, List[float]],
        lead_times: Optional[List[int]] = None,
        weighted_mode: bool = False,
        sum_only: bool = False,
        re_mask: bool = True,
    ) -> None:
        super().__init__(radii, lead_times=lead_times)
        if neighbourhood_method not in ["square", "circular"]:
            raise ValueError(
                f"neighbourhood_method 仅支持 'square' 或 'circular'，当前为 {neighbourhood_method}。"
            )
        if weighted_mode and neighbourhood_method != "circular":
            raise ValueError(
                "weighted_mode 只能与 circular 邻域配合使用，"
                f"当前 neighbourhood_method 为 {neighbourhood_method}。"
            )
        self.neighbourhood_method = neighbourhood_method
        self.weighted_mode = weighted_mode
        self.sum_only = sum_only
        self.re_mask = re_mask
        self.nb_size = 0
        self.kernel: Optional[ndarray] = None

    def _calculate_neighbourhood(
        self,
        data: ndarray,
        mask: Optional[ndarray] = None,
        *,
        remask_as_fill: bool = False,
    ) -> Union[ndarray, np.ma.MaskedArray]:
        """对单个二维切片执行邻域处理。

        ``re_mask=True`` 时：
        - ``remask_as_fill=True``（DataArray 路径）：无效格点直接写 ``NaN``；
        - 否则（MaskedArray 路径）：与上游一致，返回 ``MaskedArray``。
        """
        is_complex = issubclass(data.dtype.type, np.complexfloating)
        if self.neighbourhood_method == "circular" and is_complex:
            raise ValueError("circular 邻域不支持复数输入。")
        if not self.sum_only and not is_complex:
            if isinstance(data, np.ma.MaskedArray):
                raw_values = np.ma.getdata(data)
                raw_mask = np.ma.getmaskarray(data)
                valid_values = raw_values[~raw_mask]
                min_val = np.nanmin(valid_values)
                max_val = np.nanmax(valid_values)
            else:
                min_val = np.nanmin(np.asarray(data))
                max_val = np.nanmax(np.asarray(data))

        # 外部 mask==0；MaskedArray 输入时合并内部 mask。
        data_mask = mask == 0 if mask is not None else np.zeros(data.shape, dtype=bool)
        if isinstance(data, np.ma.MaskedArray):
            data_mask = data_mask | np.ma.getmaskarray(data)
            data = data.data

        if is_complex:
            loc_data_dtype = np.complex128
            out_data_dtype = np.complex64
        else:
            loc_data_dtype = np.float64
            out_data_dtype = np.float32
        data = np.array(data, dtype=loc_data_dtype)

        mask_type = np.float32 if self.neighbourhood_method == "circular" else np.int64
        valid_data_mask = np.ones(data.shape, dtype=mask_type)
        valid_data_mask[data_mask] = 0
        data[data_mask] = 0

        if self.sum_only:
            max_extreme_data = None
        else:
            # 先统计邻域内有效点数量，后续平均值计算要用它做分母。
            area_sum = self._do_nbhood_sum(valid_data_mask)
            max_extreme_data = area_sum.astype(loc_data_dtype)

        data = self._do_nbhood_sum(data, max_extreme=max_extreme_data)

        if not self.sum_only:
            with np.errstate(divide="ignore", invalid="ignore"):
                data = data / area_sum
            data[area_sum == 0] = np.nan
            if not is_complex:
                data = data.clip(min_val, max_val)

        data = data.astype(out_data_dtype)
        if self.re_mask:
            if remask_as_fill:
                return apply_missing_fill(data, data_mask)
            return np.ma.masked_array(data, data_mask, copy=False)
        return data

    def _do_nbhood_sum(
        self, data: np.ndarray, max_extreme: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """计算单个二维切片的邻域和。"""
        data_shape = data.shape
        ystart = xstart = 0
        ystop, xstop = data.shape
        size = data.size
        extreme = 0
        fill_value = 0
        half_nb_size = self.nb_size // 2

        for _extreme, _fill_value in {0: 0, 1: max_extreme}.items():
            if _fill_value is None or issubclass(data.dtype.type, np.complexfloating):
                continue
            # 仅在包含有效信号的最小外接窗口上做邻域计算，减少大面积零值场的开销。
            nonextreme_indices = np.argwhere(data != _extreme)
            if nonextreme_indices.size == 0:
                _ystart = _ystop = _xstart = _xstop = 0
            else:
                (_ystart, _xstart), (_ystop, _xstop) = (
                    nonextreme_indices.min(0),
                    nonextreme_indices.max(0) + 1,
                )
                _ystart = max(0, _ystart - half_nb_size)
                _ystop = min(data_shape[0], _ystop + half_nb_size)
                _xstart = max(0, _xstart - half_nb_size)
                _xstop = min(data_shape[1], _xstop + half_nb_size)
            _size = (_ystop - _ystart) * (_xstop - _xstart)
            if _size < size:
                size, extreme, fill_value, ystart, ystop, xstart, xstop = (
                    _size,
                    _extreme,
                    _fill_value,
                    _ystart,
                    _ystop,
                    _xstart,
                    _xstop,
                )

        if size != data.size:
            if isinstance(fill_value, np.ndarray):
                untrimmed = fill_value.astype(data.dtype)
            else:
                untrimmed = np.full(data_shape, fill_value, dtype=data.dtype)

        if size:
            data = data[ystart:ystop, xstart:xstop]
            if self.neighbourhood_method == "square":
                data = _boxsum(data, self.nb_size, mode="constant", constant_values=extreme)
            else:
                data = correlate(data, self.kernel, mode="nearest")
        else:
            data = untrimmed

        if data.shape != data_shape:
            untrimmed[ystart:ystop, xstart:xstop] = data
            data = untrimmed
        return data

    def process(
        self,
        data: Union[xr.DataArray, ndarray],
        mask: Optional[Union[xr.DataArray, ndarray]] = None,
        input_lead_times: Optional[Union[float, ndarray]] = None,
        grid_spacing: Optional[Union[float, Tuple[float, float]]] = None,
    ) -> Union[xr.DataArray, ndarray]:
        """
        执行邻域均值或邻域和计算。

        处理流程：
        1. 基类校验输入并准备半径；
        2. 展平前导维并逐二维切片批处理；
        3. 推断（或读取）网格间距并将半径换算为格点数；
        4. 逐切片执行方形/圆形邻域统计；
        5. 对标准 meb 六维 xarray 输入重组为六维输出。

        参数
        ----------
        data : xr.DataArray 或 ndarray
            输入数据，最后两维视为空间维。
        mask : xr.DataArray 或 ndarray, optional
            外部掩码，值为 0 的位置视为无效点。``DataArray`` 输入仅支持此外部
            掩码；``MaskedArray`` 内部掩码须走 ndarray 路径并显式提供
            ``grid_spacing``。
        input_lead_times : float 或 ndarray, optional
            输入时效（小时），用于与 ``lead_times`` 联合确定半径。
        grid_spacing : float 或 tuple[float, float], optional
            ndarray 路径使用的网格间距（米）。xarray 路径通常自动推断。

        返回
        -------
        xr.DataArray 或 ndarray
            邻域处理结果。标准 meb 六维 xarray 输入返回六维 xarray，
            其余场景返回数组结果。
        """
        geo_ctx = None
        geographic_template = None
        input_is_dataarray = isinstance(data, xr.DataArray)

        if input_is_dataarray:
            geographic_template = data
            data, mask, geo_ctx = prepare_geographic_input(data, mask)

        data = super().process(data, input_lead_times=input_lead_times)
        values = _extract_data_array(data)
        if values.ndim < 2:
            raise ValueError("输入数据至少需要二维空间网格")

        y_size, x_size = values.shape[-2], values.shape[-1]
        leading_shape = values.shape[:-2]
        flat_values = values.reshape((-1, y_size, x_size))
        flat_mask = None
        if mask is not None:
            mask_array = _extract_data_array(mask)
            try:
                flat_mask = np.broadcast_to(mask_array, values.shape)
            except ValueError as exc:
                raise ValueError(
                    f"mask 形状 {mask_array.shape} 无法广播到输入数据形状 {values.shape}"
                ) from exc
        if flat_mask is not None:
            flat_mask = flat_mask.reshape((-1, y_size, x_size))

        if isinstance(data, xr.DataArray):
            base_spacing, y_coords, x_coords = _infer_grid_spacing_from_xarray(data)
            spacing_y = spacing_x = base_spacing
            check_radius_against_distance(
                float(np.max(np.atleast_1d(self.radius))),
                y_coords=y_coords,
                x_coords=x_coords,
            )
        else:
            spacing_y, spacing_x = _parse_grid_spacing(grid_spacing)
            check_radius_against_distance(
                float(np.max(np.atleast_1d(self.radius))),
                shape=(y_size, x_size),
                grid_spacing=(spacing_y, spacing_x),
            )

        lead_values = None
        if self.lead_times is not None:
            if input_lead_times is None and isinstance(data, xr.DataArray):
                input_lead_times = _extract_lead_times_from_xarray(data)
            lead_values = _slice_lead_times_for_reshaped_data(
                np.asarray(input_lead_times, dtype=np.float64), leading_shape, y_size, x_size
            )

        output_slices = []
        for index, data_slice in enumerate(flat_values):
            if lead_values is not None:
                current_radius = float(self._find_radii(np.asarray([lead_values[index]]))[0])
            else:
                current_radius = float(self.radius)

            # 半径先换算为整格范围，再根据邻域形状构造核或窗口尺寸。
            grid_spacing_for_radius = max(spacing_y, spacing_x)
            grid_cells = _distance_to_number_of_grid_cells(
                current_radius, grid_spacing_for_radius
            )
            if self.neighbourhood_method == "circular":
                self.kernel = circular_kernel(grid_cells, self.weighted_mode)
                self.nb_size = max(self.kernel.shape)
            else:
                self.nb_size = 2 * grid_cells + 1

            mask_slice = None if flat_mask is None else flat_mask[index]
            output_slices.append(
                self._calculate_neighbourhood(
                    data_slice,
                    mask_slice,
                    remask_as_fill=input_is_dataarray,
                )
            )

        if self.re_mask and not input_is_dataarray:
            result = np.ma.stack(output_slices).reshape((*leading_shape, y_size, x_size))
        else:
            result = np.stack(output_slices).reshape((*leading_shape, y_size, x_size))

        if input_is_dataarray and set(data.dims) == {
            "member",
            "level",
            "time",
            "dtime",
            "lat",
            "lon",
        }:
            template = data.transpose("member", "level", "time", "dtime", "lat", "lon")
            output_name = data.name if data.name is not None else template.name
            if output_name is None:
                output_name = "neighbourhood_result"
            result = rebuild_to_meb_griddata(
                np.asarray(result, dtype=np.float32),
                template,
                name=output_name,
                units=str(data.attrs.get("units", "")),
            )

        if geo_ctx is not None:
            return restore_geographic_output(
                result,
                geo_ctx,
                template=geographic_template,
                name=geographic_template.name if geographic_template is not None else None,
                units=str(geographic_template.attrs.get("units", ""))
                if geographic_template is not None
                else None,
            )
        return result


class GeneratePercentilesFromANeighbourhood(BaseNeighbourhoodProcessing):
    """圆形邻域百分位处理插件。

    在每个二维空间切片上构造圆形邻域窗口，计算指定百分位序列。

    Parameters
    ----------
    radii : float or list[float]
        邻域半径，单位米。
    lead_times : list[int], optional
        与 radii 对应的时效序列，单位小时。
    percentiles : float or list[float], default=DEFAULT_PERCENTILES
        用于计算的百分位值。默认为 (10.0, 20.0, ..., 90.0)。

    Raises
    ------
    ValueError
        1. 邻域半径超过空间域允许的最大距离
        2. 空间坐标不是等间距网格
        3. x 和 y 方向的网格间距不一致
    NotImplementedError
        输入数据为 masked array 时。

    Notes
    -----
    1. 本插件仅支持圆形邻域，不支持方形邻域。
    2. 当输入为标准 meb 六维 xarray.DataArray 时：
        - 输出保持六维；``member`` 仍为集合成员
        - 邻域百分位写入 ``level`` 坐标（输入 ``level`` 长度须为 1，即无物理层次占位）
        - 属性 ``level_type="neighbourhood_percentile"``、``level_units="%"``
    3. 对于 numpy.ndarray 输入，输出数组的首轴为 percentile 维。
    4. 不支持 masked array 输入。

    See Also
    --------
    DEFAULT_PERCENTILES : 默认百分位序列
    NeighbourhoodProcessing : 邻域均值/和计算插件

    Examples
    --------
    >>> import xarray as xr
    >>> import numpy as np
    >>> from neighbourhood_probability_processing import GeneratePercentilesFromANeighbourhood
    >>> 
    >>> # 创建 meb 格式的示例数据
    >>> data = xr.DataArray(
    ...     np.random.rand(2, 1, 1, 3, 100, 120),  # (member, level, time, dtime, lat, lon)
    ...     dims=("member", "level", "time", "dtime", "lat", "lon")
    ... )
    >>> 
    >>> # 计算 25%、50%、75% 百分位
    >>> processor = GeneratePercentilesFromANeighbourhood(
    ...     radii=3000.0,
    ...     percentiles=[25.0, 50.0, 75.0]
    ... )
    >>> result = processor.process(data)
    >>> print(result.dims)  # 输出: ('member', 'level', 'time', 'dtime', 'lat', 'lon')
    >>> print(result.sizes["level"])  # 百分位个数，如 3
    >>> print(result.attrs.get("level_type"))  # neighbourhood_percentile
    """

    def __init__(
        self,
        radii: Union[float, List[float]],
        lead_times: Optional[List[int]] = None,
        percentiles: Union[float, List[float]] = DEFAULT_PERCENTILES,
    ) -> None:
        super().__init__(radii, lead_times=lead_times)
        self.percentiles = tuple(float(x) for x in _as_iterable(percentiles))

    def _pad_and_unpad_array(self, data_2d: ndarray, kernel: ndarray) -> ndarray:
        """对二维切片计算邻域百分位。"""
        kernel_mask = kernel > 0
        nb_slices = _pad_and_roll(
            data_2d, kernel.shape, mode="mean", stat_length=max(kernel.shape) // 2
        )
        percentiles = np.asarray(self.percentiles, dtype=np.float32)
        result = np.empty((len(percentiles), *data_2d.shape), dtype=np.float32)
        for nb_chunk, output_chunk in zip(nb_slices, result.swapaxes(0, 1)):
            np.percentile(
                nb_chunk[..., kernel_mask],
                percentiles,
                axis=-1,
                out=output_chunk,
                overwrite_input=True,
            )
        return result

    def process(
        self,
        data: Union[xr.DataArray, ndarray],
        input_lead_times: Optional[Union[float, ndarray]] = None,
        grid_spacing: Optional[Union[float, Tuple[float, float]]] = None,
    ) -> Union[xr.DataArray, ndarray]:
        """
        计算邻域百分位结果。

        处理流程：
        1. 基类校验输入并准备半径；
        2. 展平前导维并逐二维切片计算圆形邻域百分位；
        3. ndarray 路径输出首轴为 percentile；
        4. 标准 meb 六维 xarray 路径将邻域百分位写入 ``level`` 维（``member`` 不变）。

        参数
        ----------
        data : xr.DataArray 或 ndarray
            输入数据，最后两维视为空间维。
        input_lead_times : float 或 ndarray, optional
            输入时效（小时），用于与 ``lead_times`` 联合确定半径。
        grid_spacing : float 或 tuple[float, float], optional
            ndarray 路径使用的网格间距（米）。xarray 路径通常自动推断。

        返回
        -------
        xr.DataArray 或 ndarray
            邻域百分位结果。ndarray 路径首轴为 percentile；
            标准 meb 六维 xarray 路径返回六维 xarray。
        """
        geo_ctx = None
        geographic_template = None
        if isinstance(data, xr.DataArray):
            geographic_template = data
            data, _, geo_ctx = prepare_geographic_input(data)

        data = super().process(data, input_lead_times=input_lead_times)
        values = _extract_data_array(data)
        if np.ma.isMaskedArray(values):
            raise NotImplementedError("GeneratePercentilesFromANeighbourhood 暂不支持 masked 输入。")
        if values.ndim < 2:
            raise ValueError("输入数据至少需要二维空间网格")

        y_size, x_size = values.shape[-2], values.shape[-1]
        leading_shape = values.shape[:-2]
        flat_values = values.reshape((-1, y_size, x_size))

        if isinstance(data, xr.DataArray):
            spacing, y_coords, x_coords = _infer_grid_spacing_from_xarray(data)
            check_radius_against_distance(
                float(np.max(np.atleast_1d(self.radius))),
                y_coords=y_coords,
                x_coords=x_coords,
            )
        else:
            spacing_y, spacing_x = _parse_grid_spacing(grid_spacing)
            spacing = max(spacing_y, spacing_x)
            check_radius_against_distance(
                float(np.max(np.atleast_1d(self.radius))),
                shape=(y_size, x_size),
                grid_spacing=(spacing_y, spacing_x),
            )

        lead_values = None
        if self.lead_times is not None:
            if input_lead_times is None and isinstance(data, xr.DataArray):
                input_lead_times = _extract_lead_times_from_xarray(data)
            lead_values = _slice_lead_times_for_reshaped_data(
                np.asarray(input_lead_times, dtype=np.float64), leading_shape, y_size, x_size
            )

        output = np.empty(
            (len(self.percentiles), flat_values.shape[0], y_size, x_size),
            dtype=np.float32,
        )
        for index, data_slice in enumerate(flat_values):
            if lead_values is not None:
                current_radius = float(self._find_radii(np.asarray([lead_values[index]]))[0])
            else:
                current_radius = float(self.radius)
            grid_cells = _distance_to_number_of_grid_cells(current_radius, spacing)
            kernel = circular_kernel(grid_cells, weighted_mode=False)
            output[:, index] = self._pad_and_unpad_array(data_slice, kernel)

        result = output.reshape((len(self.percentiles), *leading_shape, y_size, x_size))

        if isinstance(data, xr.DataArray) and set(data.dims) == {
            "member",
            "level",
            "time",
            "dtime",
            "lat",
            "lon",
        }:
            template = data.transpose("member", "level", "time", "dtime", "lat", "lon")
            n_input_level = int(template.sizes["level"])
            if n_input_level != 1:
                raise ValueError(
                    "六维 meb 百分位邻域要求输入 level 长度为 1（无物理层次占位）；"
                    f"当前 level={n_input_level}。"
                )

            # result: (percentile, member, level=1, time, dtime, lat, lon)
            result_vals = np.asarray(result, dtype=np.float32)[:, :, 0, :, :, :, :]
            merged = xr.DataArray(
                np.moveaxis(result_vals, 0, 1),
                dims=("member", "level", "time", "dtime", "lat", "lon"),
                coords={
                    "member": template.coords["member"].values,
                    "level": np.asarray(self.percentiles, dtype=np.float32),
                    "time": template.coords["time"].values,
                    "dtime": template.coords["dtime"].values,
                    "lat": template.coords["lat"].values,
                    "lon": template.coords["lon"].values,
                },
                attrs=dict(template.attrs),
                name=data.name if data.name is not None else "neighbourhood_result",
            )
            merged.attrs["level_type"] = "neighbourhood_percentile"
            merged.attrs["level_units"] = "%"
            if merged.name is None:
                merged = merged.copy()
                merged.name = "neighbourhood_result"
            result = merged

        if geo_ctx is not None:
            return restore_geographic_output(
                result,
                geo_ctx,
                template=geographic_template,
                name=geographic_template.name if geographic_template is not None else None,
                units=str(geographic_template.attrs.get("units", ""))
                if geographic_template is not None
                else None,
            )

        return result
