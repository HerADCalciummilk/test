#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""概率预报可靠性订正的编排入口。

用历史概率预报与阈值化实况构建可靠性表，经聚合与整理后，将观测频率
映射回待发布概率场。本文件提供四个插件类：

- ``ConstructReliabilityCalibrationTables``：建表
- ``AggregateReliabilityCalibrationTables``：多表或按坐标求和
- ``ManipulateReliabilityTable``：合并欠采样箱、强制观测频率单调
- ``ApplyReliabilityCalibration``：按表插值订正概率

网格（meb 六维 ``Dataset`` / ``DataArray``）与站点（meb 长表
``DataFrame``）共用 ``src.utils`` 下按阶段拆分的数值内核
（``construct`` / ``manipulate`` / ``apply``）；Aggregate 以编排层
适配为主。各插件的 ``process`` 按输入类型分发到对应路径。数据约定见
``docs/reliability_calibration.md``。
"""
from __future__ import annotations

import warnings
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import xarray as xr

import meteva_base as meb
from numpy.ma.core import MaskedArray

from probability_reliability_correction.src.utils import apply as apply_kernel
from probability_reliability_correction.src.utils import construct as construct_kernel
from probability_reliability_correction.src.utils import manipulate as manipulate_kernel
from probability_reliability_correction.src.utils._reliability import (
    TABLE_ROW_NAMES,
    align_forecast_truth_meb,
    check_forecast_consistency_meb,
    ensure_meb_spatial_size_one,
    probability_bins_from_dataset,
    reliability_table_from_array,
    table_frt_point,
    validate_reliability_table_meb,
)
from probability_reliability_correction.src.utils._station import (
    AGGREGATED_STATION_ID,
    RELIABILITY_LONG_COLUMNS,
    SPATIAL_KIND_AGGREGATED,
    SPATIAL_KIND_STATION,
    aggregate_stations_to_sentinel,
    align_forecast_truth_sta,
    check_forecast_consistency_sta,
    ensure_sta_data,
    probability_bins_from_long_table,
    sum_station_reliability_tables,
    table_frt_bounds_sta,
    validate_reliability_table_sta,
    value_column,
    reliability_long_table_from_array,
)
from probability_reliability_correction.utils.base_plugin import BasePlugin, PostProcessingPlugin
from probability_reliability_correction.utils.utils import rebuild_to_meb_griddata


class ConstructReliabilityCalibrationTables(BasePlugin):
    """由历史概率预报与阈值化实况构建可靠性表。

    将预报概率落入互不重叠的概率箱，累计各箱的观测次数、预报概率和与
    预报次数，得到后续 Manipulate / Apply 使用的计数表。一次调用产出
    一张表：要求起报钟点唯一、``dtime`` 唯一；多有效时间在同钟点下累加。
    网格输出为含三计数变量的 meb ``Dataset``；站点输出为可靠性长表
    ``DataFrame``（``spatial_kind=station``）。
    """

    def __init__(
        self,
        n_probability_bins: int = 5,
        single_value_lower_limit: bool = False,
        single_value_upper_limit: bool = False,
    ) -> None:
        """配置概率箱划分方式。

        Parameters
        ----------
        n_probability_bins :
            概率箱个数（含可选的 0/1 单值端点箱）。
        single_value_lower_limit :
            为 True 时在 ``[0, tol]`` 增加单独的下端点箱。
        single_value_upper_limit :
            为 True 时在 ``[1-tol, 1]`` 增加单独的上端点箱。
        """
        self.single_value_tolerance = construct_kernel.SINGLE_VALUE_TOLERANCE
        self.probability_bins = self._define_probability_bins(
            n_probability_bins,
            single_value_lower_limit,
            single_value_upper_limit,
        )
        self.table_columns = np.array(TABLE_ROW_NAMES)
        self.expected_table_shape = (len(self.table_columns), n_probability_bins)

    def __repr__(self) -> str:
        bin_values = ", ".join(
            [f"[{item[0]:1.2f} --> {item[1]:1.2f}]" for item in self.probability_bins]
        )
        return (
            "<ConstructReliabilityCalibrationTables: probability_bins: "
            f"{bin_values}>"
        )

    def _define_probability_bins(
        self,
        n_probability_bins: int,
        single_value_lower_limit: bool,
        single_value_upper_limit: bool,
    ) -> np.ndarray:
        """定义互不重叠的概率箱边界，形状 ``(n_bins, 2)``。"""
        tol = np.float32(self.single_value_tolerance)
        n_bins = int(n_probability_bins)

        # 端点箱占用配额：先从内部均匀箱数中扣减，再在首尾插入单值箱
        if single_value_lower_limit and single_value_upper_limit:
            if n_bins <= 2:
                raise ValueError(
                    "Cannot use both single_value_lower_limit and "
                    "single_value_upper_limit with 2 or fewer "
                    "probability bins."
                )
            n_bins = n_bins - 2
        elif single_value_lower_limit or single_value_upper_limit:
            n_bins = n_bins - 1

        # 用 nextafter 使相邻箱上/下界紧挨且不重叠
        bin_lower = np.linspace(0, 1, n_bins + 1, dtype=np.float32)
        bin_upper = np.nextafter(bin_lower, 0, dtype=np.float32)
        bin_upper[-1] = 1.0
        bins = np.stack([bin_lower[:-1], bin_upper[1:]], 1).astype(np.float32)

        if single_value_lower_limit:
            bins[0, 0] = np.nextafter(tol, 1, dtype=np.float32)
            lowest_bin = np.array([0, tol], dtype=np.float32)
            bins = np.vstack([lowest_bin, bins]).astype(np.float32)

        if single_value_upper_limit:
            bins[-1, 1] = np.nextafter(1.0 - tol, 0, dtype=np.float32)
            highest_bin = np.array([1.0 - tol, 1], dtype=np.float32)
            bins = np.vstack([bins, highest_bin]).astype(np.float32)

        return bins

    def _process_grid(
        self,
        historic_forecasts: xr.DataArray,
        truths: xr.DataArray,
        aggregate_coords: Optional[List[str]] = None,
    ) -> xr.Dataset:
        """网格路径：校验对齐后建表，可选按坐标聚合。"""
        forecast = meb.checkout_griddata(
            historic_forecasts, valid_val=(-np.inf, np.inf, np.nan)
        )
        truth = meb.checkout_griddata(truths, valid_val=(-np.inf, np.inf, np.nan))
        check_forecast_consistency_meb(forecast)
        forecast, truth = align_forecast_truth_meb(forecast, truth)

        # 概率场要求 member 长度为 1，并去掉该维以便后续处理
        if forecast.sizes["member"] != 1 or truth.sizes["member"] != 1:
            raise ValueError(
                "网格概率场的 member 维长度须为 1（可靠性订正当前不支持多样本成员维）。"
            )
        forecast_sm = forecast.isel(member=0, drop=True)
        truth_sm = truth.isel(member=0, drop=True)

        thresholds = np.asarray(forecast_sm["level"].values)
        # 已去掉 member：level×time×dtime×lat×lon → 内核返回 level×3×bin×lat×lon
        stacked = construct_kernel.construct_reliability_stack(
            np.asarray(forecast_sm.values, dtype=np.float32),
            np.asarray(truth_sm.values, dtype=np.float32),
            self.probability_bins,
            single_value_tolerance=self.single_value_tolerance,
        )

        # 表的 time 取样本最大有效时间，bounds 覆盖全部参与建表的时段
        times = pd.to_datetime(np.atleast_1d(forecast_sm["time"].values))
        time_point = times.max()
        time_bounds = (times.min(), times.max())
        dtime = float(forecast_sm["dtime"].values[0])
        relative = forecast.attrs.get(
            "relative_to_threshold",
            forecast_sm.attrs.get("relative_to_threshold"),
        )

        ds = reliability_table_from_array(
            stacked,
            thresholds=thresholds,
            probability_bins=self.probability_bins,
            lat=np.asarray(forecast_sm["lat"].values),
            lon=np.asarray(forecast_sm["lon"].values),
            time_point=time_point,
            time_bounds=time_bounds,
            dtime=dtime,
            relative_to_threshold=relative,
        )
        if "units" in getattr(forecast_sm["level"], "attrs", {}):
            for name in TABLE_ROW_NAMES:
                ds[name]["level"].attrs["units"] = forecast_sm["level"].attrs["units"]

        if aggregate_coords:
            ds = AggregateReliabilityCalibrationTables().process(
                [ds], coordinates=list(aggregate_coords)
            )
        validate_reliability_table_meb(ds)
        return ds

    def _process_station(
        self,
        historic_forecasts: pd.DataFrame,
        truths: pd.DataFrame,
        aggregate_coords: Optional[List[str]] = None,
        *,
        forecast_data_name: Optional[str] = None,
        truth_data_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """站点路径：对齐后按站建长表，可选对 id 聚合。"""
        forecast = ensure_sta_data(historic_forecasts)
        truth = ensure_sta_data(truths)
        check_forecast_consistency_sta(forecast)
        fc_name = value_column(forecast, forecast_data_name)
        tr_name = value_column(truth, truth_data_name)
        (
            fc_ltx,
            tr_ltx,
            thresholds,
            station_ids,
            lons,
            lats,
            dtime,
            frts,
        ) = align_forecast_truth_sta(
            forecast,
            truth,
            forecast_data_name=fc_name,
            truth_data_name=tr_name,
        )
        stacked = construct_kernel.construct_reliability_stack_points(
            fc_ltx,
            tr_ltx,
            self.probability_bins,
            single_value_tolerance=self.single_value_tolerance,
        )
        relative = forecast.attrs.get("relative_to_threshold")
        table = reliability_long_table_from_array(
            stacked,
            thresholds=thresholds,
            probability_bins=self.probability_bins,
            station_ids=station_ids,
            lons=lons,
            lats=lats,
            time_point=pd.Timestamp(np.max(frts)),
            time_bounds=(pd.Timestamp(np.min(frts)), pd.Timestamp(np.max(frts))),
            dtime=dtime,
            relative_to_threshold=relative,
            spatial_kind=SPATIAL_KIND_STATION,
        )
        if aggregate_coords:
            coords = list(aggregate_coords)
            if coords and set(coords) != {"id"}:
                raise ValueError(
                    "站点路径 aggregate_coords 仅支持 [\"id\"] "
                    f"（对全部站点求和），收到 {coords}"
                )
            table = AggregateReliabilityCalibrationTables().process(
                [table], coordinates=coords
            )
        validate_reliability_table_sta(table)
        return table

    def process(
        self,
        historic_forecasts: Union[xr.DataArray, pd.DataFrame],
        truths: Union[xr.DataArray, pd.DataFrame],
        aggregate_coords: Optional[List[str]] = None,
        *,
        forecast_data_name: Optional[str] = None,
        truth_data_name: Optional[str] = None,
    ) -> Union[xr.Dataset, pd.DataFrame]:
        """构建可靠性表，按输入类型分发到网格或站点路径。

        预报与实况须同为 ``DataArray`` 或同为 ``DataFrame``。建表前校验
        起报钟点与 ``dtime`` 唯一性，并按有效时间对齐。可选在建表后立即
        对指定坐标求和（网格 ``lat``/``lon``，站点仅 ``id``）。

        Parameters
        ----------
        historic_forecasts, truths :
            网格：meb 六维概率/事件场；站点：meb 六列 ``DataFrame``。
        aggregate_coords :
            建表后要求和的坐标。网格常用 ``["lat", "lon"]``；
            站点传 ``["id"]`` 则聚合成哨兵站 ``id=-1``。
        forecast_data_name, truth_data_name :
            仅站点路径：要素列名；默认自动检测唯一非六列列。

        Returns
        -------
        xr.Dataset or pd.DataFrame
            网格：含 ``observation_count`` /
            ``sum_of_forecast_probabilities`` / ``forecast_count`` 的
            六维可靠性表 ``Dataset``。  

            站点：可靠性长表 ``DataFrame``（``spatial_kind=station``；
            若 ``aggregate_coords=["id"]`` 则为 ``aggregated``、``id=-1``）。
        """
        if isinstance(historic_forecasts, pd.DataFrame) or isinstance(
            truths, pd.DataFrame
        ):
            if not (
                isinstance(historic_forecasts, pd.DataFrame)
                and isinstance(truths, pd.DataFrame)
            ):
                raise TypeError("站点路径要求预报与实况均为 DataFrame。")
            return self._process_station(
                historic_forecasts,
                truths,
                aggregate_coords=aggregate_coords,
                forecast_data_name=forecast_data_name,
                truth_data_name=truth_data_name,
            )
        return self._process_grid(
            historic_forecasts, truths, aggregate_coords=aggregate_coords
        )


class AggregateReliabilityCalibrationTables(BasePlugin):
    """聚合可靠性表：多表按时间段拼接求和，可选对指定空间坐标求和。

    多表聚合要求各表的预报参考时间区间（``time_bound``）不重叠，避免同一预报样本被重复计数。
    网格可对 ``lat``/``lon``（或其一）求和；站点仅支持 ``coordinates=["id"]``，
    结果写入哨兵站 ``id=-1`` 并标记 ``spatial_kind=aggregated``。
    """

    def __repr__(self) -> str:
        return "<AggregateReliabilityCalibrationTables>"

    @staticmethod
    def _check_frt_bounds(tables: Sequence[xr.Dataset]) -> None:
        """检查网格多表的预报参考时间区间是否互不重叠。"""
        lowers = []
        uppers = []
        for ds in tables:
            if "time_bound_lower" in ds.coords and "time_bound_upper" in ds.coords:
                lowers.append(pd.Timestamp(ds["time_bound_lower"].values))
                uppers.append(pd.Timestamp(ds["time_bound_upper"].values))
            else:
                t = table_frt_point(ds)
                lowers.append(t)
                uppers.append(t)
        # 要求上一表上界严格小于下一表下界（按输入顺序）
        if not all(x < y for x, y in zip(uppers, lowers[1:])):
            raise ValueError(
                "Reliability calibration tables have overlapping "
                "forecast reference time bounds, indicating that "
                "the same forecast data has contributed to the "
                "construction of both tables. Cannot aggregate."
            )

    @staticmethod
    def _check_frt_bounds_sta(tables: Sequence[pd.DataFrame]) -> None:
        """检查站点多表的预报参考时间区间是否互不重叠。"""
        lowers = []
        uppers = []
        for df in tables:
            lo, hi = table_frt_bounds_sta(df)
            lowers.append(lo)
            uppers.append(hi)
        if not all(x < y for x, y in zip(uppers, lowers[1:])):
            raise ValueError(
                "Reliability calibration tables have overlapping "
                "forecast reference time bounds, indicating that "
                "the same forecast data has contributed to the "
                "construction of both tables. Cannot aggregate."
            )

    def _process_station(
        self,
        tables: List[pd.DataFrame],
        coordinates: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """站点路径：多表计数求和，可选将全部站点聚到哨兵站。"""
        coordinates = [] if coordinates is None else list(coordinates)
        for t in tables:
            validate_reliability_table_sta(t)

        if len(tables) == 1:
            ds = tables[0]
            if not coordinates:
                return ds
        else:
            self._check_frt_bounds_sta(tables)
            ds = sum_station_reliability_tables(tables)

        if coordinates:
            if set(coordinates) != {"id"}:
                raise ValueError(
                    "站点路径 coordinates 仅支持 [\"id\"]，"
                    f"收到 {coordinates}"
                )
            ds = aggregate_stations_to_sentinel(ds)
        validate_reliability_table_sta(ds)
        return ds

    def _process_grid(
        self,
        reliability_tables: Union[xr.Dataset, Sequence[xr.Dataset]],
        coordinates: Optional[List[str]] = None,
    ) -> xr.Dataset:
        """网格路径：多表计数求和，可选对指定空间维求和。"""
        coordinates = [] if coordinates is None else list(coordinates)
        tables = (
            [reliability_tables]
            if isinstance(reliability_tables, xr.Dataset)
            else list(reliability_tables)
        )
        for t in tables:
            validate_reliability_table_meb(t)

        if len(tables) == 1:
            ds = tables[0]
            if not coordinates:
                return ds
        else:
            self._check_frt_bounds(tables)
            ds = tables[0].copy(deep=True)
            for name in TABLE_ROW_NAMES:
                # 直接对数组求和，避免不同 time 坐标触发 xarray 对齐产生 NaN
                stacked = np.stack(
                    [np.asarray(t[name].values, dtype=np.float32) for t in tables],
                    axis=0,
                )
                summed = np.sum(stacked, axis=0).astype(np.float32)
                ds[name] = ds[name].copy(data=summed)
            all_times = [table_frt_point(t) for t in tables]
            all_low = [
                pd.Timestamp(
                    t["time_bound_lower"].values
                    if "time_bound_lower" in t.coords
                    else table_frt_point(t)
                )
                for t in tables
            ]
            all_up = [
                pd.Timestamp(
                    t["time_bound_upper"].values
                    if "time_bound_upper" in t.coords
                    else table_frt_point(t)
                )
                for t in tables
            ]
            # 合并后 time 仍为长度 1；bounds 覆盖全部参与表的时段
            ds = ds.assign_coords(
                time=("time", np.array([max(all_times)])),
                time_bound_lower=min(all_low),
                time_bound_upper=max(all_up),
            )

        if coordinates:
            # 只对实际存在的维求和；聚合后用模板把 lat/lon 写回长度为 1
            sum_dims = [c for c in coordinates if c in ds["observation_count"].dims]
            if sum_dims:
                template = tables[0]
                summed_vars = {}
                for name in TABLE_ROW_NAMES:
                    summed_vars[name] = ds[name].sum(dim=sum_dims, keep_attrs=True)
                ds = ensure_meb_spatial_size_one(
                    xr.Dataset(summed_vars, attrs=dict(template.attrs)), template
                )
                for key in ("time_bound_lower", "time_bound_upper"):
                    if key in tables[0].coords:
                        ds = ds.assign_coords({key: tables[0][key]})
        validate_reliability_table_meb(ds)
        return ds

    def process(
        self,
        reliability_tables: Union[
            xr.Dataset,
            pd.DataFrame,
            Sequence[Union[xr.Dataset, pd.DataFrame]],
        ],
        coordinates: Optional[List[str]] = None,
    ) -> Union[xr.Dataset, pd.DataFrame]:
        """对可靠性表求和聚合，按输入类型分发到网格或站点路径。

        可同时或单独完成两类操作：
        (1)多张表在时间段不重叠时对三计数
        变量逐箱相加；
        (2)对 ``coordinates`` 指定的空间维/站点 id 求和。
        单表且未指定坐标时原样返回。不可混用 ``Dataset`` 与 ``DataFrame``。

        Parameters
        ----------
        reliability_tables :
            单表或表序列（网格 ``Dataset`` / 站点 ``DataFrame``）。
        coordinates :
            要求和的坐标名。网格可用 ``lat``、``lon`` 或其组合；
            站点仅 ``["id"]``。

        Returns
        -------
        xr.Dataset or pd.DataFrame
            与输入同类型的聚合后可靠性表。网格空间求和后 ``lat``/``lon``
            长度仍为 1；站点对 ``id`` 求和后为哨兵站 ``id=-1``，
            ``spatial_kind=aggregated``。多表合并时 ``time`` 取各表代表
            起报的最大，``time_bound_*`` 覆盖全部参与时段。
        """
        if isinstance(reliability_tables, pd.DataFrame):
            tables_sta: List[pd.DataFrame] = [reliability_tables]
            return self._process_station(tables_sta, coordinates=coordinates)
        if isinstance(reliability_tables, (list, tuple)) and reliability_tables:
            if all(isinstance(t, pd.DataFrame) for t in reliability_tables):
                return self._process_station(
                    list(reliability_tables), coordinates=coordinates
                )
            if any(isinstance(t, pd.DataFrame) for t in reliability_tables):
                raise TypeError("多表聚合不可混用 Dataset 与 DataFrame。")
        return self._process_grid(reliability_tables, coordinates=coordinates)


class ManipulateReliabilityTable(BasePlugin):
    """整理可靠性表：合并欠采样箱，并强制观测频率随预报概率单调。

    对每条「阈值 × 空间点」的箱曲线调用数值内核：预报次数低于
    箱内预报次数下限 的箱与邻箱合并；若观测频率非单调，则合并
    下降邻箱并假定观测频率在合并段内恒定。默认要求空间已聚合（网格
    lat/lon 长度为 1，或站点 ``spatial_kind=aggregated``）；
    ``point_by_point=True`` 时对每个格点/站点分别整理。
    """

    def __init__(
        self, minimum_forecast_count: int = 200, point_by_point: bool = False
    ) -> None:
        """配置欠采样阈值与是否逐点整理。

        Parameters
        ----------
        minimum_forecast_count :
            箱内预报次数下限；低于此值的箱视为欠采样并合并。须 ≥ 1。
        point_by_point :
            True 时对每个 ``(level, lat, lon)`` 或 ``(level, id)`` 分别整理；
            False 时要求输入空间维已聚合。
        """
        if minimum_forecast_count < 1:
            raise ValueError(
                "The minimum_forecast_count must be at least 1 as empty "
                "bins in the reliability table are not handled."
            )
        self.minimum_forecast_count = minimum_forecast_count
        self.point_by_point = point_by_point

    def _enforce_min_count_and_monotonicity(
        self,
        observation_count: np.ndarray,
        forecast_probability_sum: np.ndarray,
        forecast_count: np.ndarray,
        bounds: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """对单条箱曲线合并欠采样箱并强制观测频率单调。"""
        return manipulate_kernel.enforce_min_count_and_monotonicity(
            observation_count,
            forecast_probability_sum,
            forecast_count,
            bounds,
            self.minimum_forecast_count,
        )

    def _process_flat_table(self, ds: xr.Dataset) -> xr.Dataset:
        """整理单阈值、单空间点的网格可靠性表。"""
        # 空间与时间维已退化：沿 member（概率箱）取一维计数曲线
        obs = np.asarray(
            ds["observation_count"].isel(
                level=0, time=0, dtime=0, lat=0, lon=0, drop=False
            ).values,
            dtype=np.float32,
        ).reshape(-1)
        psum = np.asarray(
            ds["sum_of_forecast_probabilities"].isel(
                level=0, time=0, dtime=0, lat=0, lon=0, drop=False
            ).values,
            dtype=np.float32,
        ).reshape(-1)
        fcnt = np.asarray(
            ds["forecast_count"].isel(
                level=0, time=0, dtime=0, lat=0, lon=0, drop=False
            ).values,
            dtype=np.float32,
        ).reshape(-1)
        bounds = probability_bins_from_dataset(ds)
        obs, psum, fcnt, bounds = self._enforce_min_count_and_monotonicity(
            obs, psum, fcnt, bounds
        )

        # 合并后箱数可能减少：按新边界重建 member 与概率箱坐标
        centers = np.mean(bounds, axis=1).astype(np.float32)
        n_bin = centers.size
        level = np.atleast_1d(ds["level"].values.astype(np.float32))
        if level.size > 1:
            level = level[:1]
        time_coord = np.atleast_1d(ds["time"].values)[:1]
        dtime_coord = np.atleast_1d(ds["dtime"].values.astype(np.float32))[:1]
        lat = np.atleast_1d(ds["lat"].values.astype(np.float32))[:1]
        lon = np.atleast_1d(ds["lon"].values.astype(np.float32))[:1]
        member = np.arange(n_bin, dtype=np.int32)

        coords = {
            "member": member,
            "level": level,
            "time": time_coord,
            "dtime": dtime_coord,
            "lat": lat,
            "lon": lon,
            "probability_bin": ("member", centers),
            "probability_bin_bound_lower": ("member", bounds[:, 0]),
            "probability_bin_bound_upper": ("member", bounds[:, 1]),
        }
        for key in ("time_bound_lower", "time_bound_upper"):
            if key in ds.coords:
                coords[key] = ds[key].values

        data_vars = {}
        for name, vec in zip(TABLE_ROW_NAMES, (obs, psum, fcnt)):
            arr = vec.reshape(n_bin, 1, 1, 1, 1, 1).astype(np.float32)
            data_vars[name] = xr.DataArray(
                arr,
                coords=coords,
                dims=("member", "level", "time", "dtime", "lat", "lon"),
                name=name,
                attrs=dict(ds[name].attrs) if name in ds else {},
            )
        out = xr.Dataset(data_vars, attrs=dict(ds.attrs))
        return out

    def _process_flat_station_group(self, group: pd.DataFrame) -> pd.DataFrame:
        """整理单个 ``(level, id)`` 分组的箱曲线并写回长表行。"""
        group = group.sort_values("bin_index")
        obs = np.asarray(group["observation_count"].values, dtype=np.float32)
        psum = np.asarray(
            group["sum_of_forecast_probabilities"].values, dtype=np.float32
        )
        fcnt = np.asarray(group["forecast_count"].values, dtype=np.float32)
        bounds = probability_bins_from_long_table(group)
        obs, psum, fcnt, bounds = self._enforce_min_count_and_monotonicity(
            obs, psum, fcnt, bounds
        )
        centers = np.mean(bounds, axis=1).astype(np.float32)
        n_bin = centers.size
        base = group.iloc[0]
        rows = []
        for ibin in range(n_bin):
            rows.append(
                {
                    "level": np.float32(base["level"]),
                    "time": pd.Timestamp(base["time"]),
                    "dtime": np.float32(base["dtime"]),
                    "id": np.int32(base["id"]),
                    "lon": np.float32(base["lon"]),
                    "lat": np.float32(base["lat"]),
                    "bin_index": np.int32(ibin),
                    "probability_bin": centers[ibin],
                    "probability_bin_bound_lower": np.float32(bounds[ibin, 0]),
                    "probability_bin_bound_upper": np.float32(bounds[ibin, 1]),
                    "observation_count": np.float32(obs[ibin]),
                    "sum_of_forecast_probabilities": np.float32(psum[ibin]),
                    "forecast_count": np.float32(fcnt[ibin]),
                }
            )
        return pd.DataFrame(rows)

    def _process_grid(self, reliability_table: xr.Dataset) -> List[xr.Dataset]:
        """网格路径：按阈值（及可选格点）整理，返回 Dataset 列表。"""
        validate_reliability_table_meb(reliability_table)

        if self.point_by_point:
            results: List[xr.Dataset] = []
            for lev in reliability_table["level"].values:
                sub = reliability_table.sel(level=[lev])
                for lat in sub["lat"].values:
                    for lon in sub["lon"].values:
                        point = sub.sel(lat=[lat], lon=[lon])
                        results.append(self._process_flat_table(point))
            return results

        # 默认：空间须已聚合，否则箱统计混杂不同格点
        if (
            reliability_table.sizes.get("lat", 1) != 1
            or reliability_table.sizes.get("lon", 1) != 1
        ):
            raise ValueError(
                "ManipulateReliabilityTable 默认要求空间维已聚合为长度 1；"
                "请先 Aggregate(lat/lon)，或设置 point_by_point=True。"
            )

        results = []
        for lev in np.atleast_1d(reliability_table["level"].values):
            sub = reliability_table.sel(level=[lev])
            results.append(self._process_flat_table(sub))
        return results

    def _process_station(self, reliability_table: pd.DataFrame) -> pd.DataFrame:
        """站点路径：按 ``(level, id)`` 整理，合并为一张长表。"""
        validate_reliability_table_sta(reliability_table)
        attrs = dict(reliability_table.attrs)
        kind = attrs.get("spatial_kind", SPATIAL_KIND_STATION)

        if self.point_by_point:
            pieces = []
            for (_, _), group in reliability_table.groupby(
                ["level", "id"], sort=True
            ):
                pieces.append(self._process_flat_station_group(group))
            out = pd.concat(pieces, ignore_index=True)
        else:
            # 非逐站模式：须已是哨兵站聚合表
            if kind != SPATIAL_KIND_AGGREGATED:
                n_id = reliability_table["id"].nunique()
                if n_id != 1 or int(reliability_table["id"].iloc[0]) != int(
                    AGGREGATED_STATION_ID
                ):
                    raise ValueError(
                        "ManipulateReliabilityTable 站点默认要求已聚合"
                        f"（spatial_kind=aggregated, id={AGGREGATED_STATION_ID}）；"
                        "请先 Aggregate(coordinates=['id'])，或设置 point_by_point=True。"
                    )
            pieces = []
            for (_, _), group in reliability_table.groupby(
                ["level", "id"], sort=True
            ):
                pieces.append(self._process_flat_station_group(group))
            out = pd.concat(pieces, ignore_index=True)
            attrs["spatial_kind"] = SPATIAL_KIND_AGGREGATED

        out = out[list(RELIABILITY_LONG_COLUMNS)]
        for col in TABLE_ROW_NAMES:
            out[col] = out[col].astype(np.float32)
        out["bin_index"] = out["bin_index"].astype(np.int32)
        out["id"] = out["id"].astype(np.int32)
        out = out.sort_values(["level", "id", "bin_index"]).reset_index(drop=True)
        out.attrs = attrs
        validate_reliability_table_sta(out)
        return out

    def process(
        self, reliability_table: Union[xr.Dataset, pd.DataFrame]
    ) -> Union[List[xr.Dataset], pd.DataFrame]:
        """整理可靠性表，按输入类型分发到网格或站点路径。

        Parameters
        ----------
        reliability_table :
            待整理的网格 ``Dataset`` 或站点长表 ``DataFrame``。

        Returns
        -------
        list of xr.Dataset or pd.DataFrame
            网格：按阈值（及 ``point_by_point`` 时按格点）拆开的
            ``Dataset`` 列表；合并后各阈值概率箱个数可能不同。  
            
            站点：一张可靠性长表；不同阈值可有不同箱数；默认路径下
            ``spatial_kind=aggregated``。
        """
        if isinstance(reliability_table, pd.DataFrame):
            return self._process_station(reliability_table)
        return self._process_grid(reliability_table)


class ApplyReliabilityCalibration(PostProcessingPlugin):
    """用可靠性表对概率预报做分段线性订正。

    对每个阈值从计数表得到箱中心预报概率 ``P_bin`` 与观测频率
    ``f_obs``，再对原始概率场插值并裁剪到 ``[0, 1]``。订正后按
    ``relative_to_threshold`` 强制跨阈值单调（``above`` 非增、``below``
    非减）。默认使用空间已聚合的整场曲线；``point_by_point=True`` 时
    对每个格点/站点使用各自曲线。箱数不足 2 的阈值跳过订正并告警；
    预报阈值在表中找不到则报错。
    """

    def __init__(self, point_by_point: bool = False) -> None:
        """配置是否逐空间点应用可靠性曲线。

        Parameters
        ----------
        point_by_point :
            True 时网格按 ``(lat, lon)``、站点按 ``id`` 匹配各自曲线；
            False 时要求表已空间聚合（网格 lat/lon 为 1，或站点
            ``spatial_kind=aggregated``）。
        """
        self.point_by_point = point_by_point

    @staticmethod
    def _table_for_threshold(
        reliability_table: Union[xr.Dataset, Sequence[xr.Dataset]], threshold_value
    ) -> xr.Dataset:
        """按 ``level`` 精确匹配对应阈值的可靠性表。"""
        target = np.asarray(threshold_value, dtype=np.float32).item()
        tables = (
            [reliability_table]
            if isinstance(reliability_table, xr.Dataset)
            else list(reliability_table)
        )
        for ds in tables:
            lev = np.asarray(ds["level"].values, dtype=np.float32)
            hits = np.flatnonzero(lev == target)
            if hits.size == 0:
                continue
            if ds.sizes.get("level", 1) > 1:
                return ds.isel(level=[int(hits[0])])
            return ds
        raise ValueError(
            "No reliability table found to match threshold "
            f"{threshold_value}."
        )

    @staticmethod
    def _calculate_reliability_probabilities(
        reliability_table: xr.Dataset,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """由网格表计数换算可靠性曲线 ``(P_bin, f_obs)``。"""
        # 空间与阈值已退化：沿 member（概率箱）取一维计数
        obs = np.asarray(
            reliability_table["observation_count"]
            .isel(level=0, time=0, dtime=0, lat=0, lon=0)
            .values,
            dtype=np.float32,
        ).reshape(-1)
        psum = np.asarray(
            reliability_table["sum_of_forecast_probabilities"]
            .isel(level=0, time=0, dtime=0, lat=0, lon=0)
            .values,
            dtype=np.float32,
        ).reshape(-1)
        fcnt = np.asarray(
            reliability_table["forecast_count"]
            .isel(level=0, time=0, dtime=0, lat=0, lon=0)
            .values,
            dtype=np.float32,
        ).reshape(-1)
        return apply_kernel.reliability_curve_from_counts(obs, psum, fcnt)

    @staticmethod
    def _curve_from_station_rows(
        rows: pd.DataFrame,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """由站点长表行换算可靠性曲线。"""
        sub = rows.sort_values("bin_index")
        return apply_kernel.reliability_curve_from_counts(
            np.asarray(sub["observation_count"].values, dtype=np.float32),
            np.asarray(sub["sum_of_forecast_probabilities"].values, dtype=np.float32),
            np.asarray(sub["forecast_count"].values, dtype=np.float32),
        )

    @staticmethod
    def _interpolate(
        forecast_threshold: Union[MaskedArray, np.ndarray],
        reliability_probabilities: np.ndarray,
        observation_frequencies: np.ndarray,
    ) -> Union[MaskedArray, np.ndarray]:
        """按可靠性曲线对概率场做分段线性插值。"""
        return apply_kernel.interpolate_probabilities(
            forecast_threshold,
            reliability_probabilities,
            observation_frequencies,
        )

    @staticmethod
    def _probability_is_above_or_below(cube: xr.DataArray) -> Optional[str]:
        """将 ``relative_to_threshold`` 规范为 ``above`` / ``below``。"""
        return apply_kernel.normalize_relative_to_threshold(
            cube.attrs.get("relative_to_threshold")
        )

    def _ensure_monotonicity_across_thresholds(self, cube: xr.DataArray) -> None:
        """就地强制网格概率沿阈值维单调。"""
        # level 在六维中为轴 1；单阈值时内核直接返回
        cube.values[:] = apply_kernel.ensure_monotonicity_across_thresholds(
            cube.values,
            cube.attrs.get("relative_to_threshold"),
            level_axis=1,
        )

    def _ensure_monotonicity_sta(
        self, forecast: pd.DataFrame, data_name: str
    ) -> pd.DataFrame:
        """按 ``(id, time, dtime)`` 组强制站点概率跨阈值单调。"""
        relative = forecast.attrs.get("relative_to_threshold")
        if forecast["level"].nunique() <= 1:
            return forecast
        if apply_kernel.normalize_relative_to_threshold(relative) is None:
            raise ValueError(
                "Cube threshold coordinate does not define whether "
                "thresholding is above or below the defined thresholds."
            )
        out = forecast.copy()
        pieces = []
        for _, group in out.groupby(["id", "time", "dtime"], sort=False):
            g = group.sort_values("level")
            # 扩成 (1, level, 1) 以复用网格内核（level_axis=1）
            vals = np.asarray(g[data_name].values, dtype=np.float32)[np.newaxis, :, np.newaxis]
            fixed = apply_kernel.ensure_monotonicity_across_thresholds(
                vals, relative, level_axis=1
            )
            g = g.copy()
            g[data_name] = fixed[0, :, 0].astype(np.float32)
            pieces.append(g)
        result = pd.concat(pieces, ignore_index=True)
        result.attrs = dict(forecast.attrs)
        return result

    def _apply_calibration(
        self, forecast: xr.DataArray, reliability_table: Union[xr.Dataset, Sequence[xr.Dataset]]
    ) -> xr.DataArray:
        """用整场（空间已聚合）可靠性表订正网格概率。"""
        calibrated = np.array(forecast.values, copy=True, dtype=np.float32)
        uncalibrated_thresholds = []
        for ilev, thr in enumerate(forecast["level"].values):
            table = self._table_for_threshold(reliability_table, thr)
            # 不自动空间聚合：表须已折叠，否则应走 point_by_point
            if table.sizes.get("lat", 1) != 1 or table.sizes.get("lon", 1) != 1:
                raise ValueError(
                    "Reliability table still has spatial dimensions with size > 1. "
                    "Aggregate lat/lon first, or set point_by_point=True."
                )
            rel_p, obs_f = self._calculate_reliability_probabilities(table)
            if rel_p is None:
                # 箱数不足，保留该阈值原始概率
                uncalibrated_thresholds.append(float(thr))
                continue
            for im in range(forecast.sizes["member"]):
                for it in range(forecast.sizes["time"]):
                    for idt in range(forecast.sizes["dtime"]):
                        field = calibrated[im, ilev, it, idt]
                        calibrated[im, ilev, it, idt] = self._interpolate(
                            field, rel_p, obs_f
                        )
        out = rebuild_to_meb_griddata(
            calibrated, forecast, dtype=np.float32, units="1"
        )
        # 订正后始终检查跨阈值单调（缺 relative_to_threshold 则报错）
        self._ensure_monotonicity_across_thresholds(out)
        if uncalibrated_thresholds:
            warnings.warn(
                "The following thresholds were not calibrated due to "
                "insufficient forecast counts in reliability table bins: "
                f"{uncalibrated_thresholds}"
            )
        return out

    def _apply_point_by_point(
        self, forecast: xr.DataArray, reliability_table: Union[xr.Dataset, Sequence[xr.Dataset]]
    ) -> xr.DataArray:
        """按格点匹配可靠性表并逐点订正网格概率。"""
        tables = (
            [reliability_table]
            if isinstance(reliability_table, xr.Dataset)
            else list(reliability_table)
        )
        calibrated = np.array(forecast.values, copy=True, dtype=np.float32)
        for ilat, lat in enumerate(forecast["lat"].values):
            for ilon, lon in enumerate(forecast["lon"].values):
                point_tables = []
                for ds in tables:
                    # 整场表：切片到当前点；已是单点表：按 lat/lon 精确匹配
                    if ds.sizes.get("lat", 1) > 1 or ds.sizes.get("lon", 1) > 1:
                        point_tables.append(ds.sel(lat=[lat], lon=[lon]))
                    else:
                        ds_lat = float(np.asarray(ds["lat"].values).reshape(-1)[0])
                        ds_lon = float(np.asarray(ds["lon"].values).reshape(-1)[0])
                        if ds_lat == float(lat) and ds_lon == float(lon):
                            point_tables.append(ds)
                if not point_tables:
                    raise ValueError(
                        "No reliability table found for spatial point "
                        f"lat={lat}, lon={lon}."
                    )
                # 扩回六维单点，复用整场订正逻辑
                point_fc = forecast.isel(lat=ilat, lon=ilon)
                point_fc = point_fc.expand_dims(
                    {"lat": [lat], "lon": [lon]},
                ).transpose("member", "level", "time", "dtime", "lat", "lon")
                cal_point = self._apply_calibration(point_fc, point_tables)
                calibrated[:, :, :, :, ilat, ilon] = cal_point.values[:, :, :, :, 0, 0]
        return rebuild_to_meb_griddata(
            calibrated, forecast, dtype=np.float32, units="1"
        )

    def _apply_station(
        self,
        forecast: pd.DataFrame,
        reliability_table: pd.DataFrame,
        *,
        data_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """站点路径：按聚合表或逐站表插值订正概率列。"""
        forecast = ensure_sta_data(forecast)
        validate_reliability_table_sta(reliability_table)
        col = value_column(forecast, data_name)
        kind = reliability_table.attrs.get("spatial_kind", SPATIAL_KIND_STATION)
        out = forecast.copy()
        # pandas 列视图可能只读，订正结果写到可写副本
        values = np.array(out[col].to_numpy(dtype=np.float32, copy=True), copy=True)
        uncalibrated_thresholds = set()

        if kind == SPATIAL_KIND_AGGREGATED:
            if self.point_by_point:
                warnings.warn(
                    "reliability table is aggregated; point_by_point 将被忽略，"
                    "全部站点共用 id=-1 曲线。"
                )
            # 全站共用哨兵站曲线
            for thr in np.unique(np.asarray(out["level"].values, dtype=np.float32)):
                rows = reliability_table.loc[
                    (reliability_table["level"].astype(np.float32) == thr)
                    & (reliability_table["id"] == AGGREGATED_STATION_ID)
                ]
                if rows.empty:
                    raise ValueError(
                        "No reliability table found to match threshold "
                        f"{thr}."
                    )
                rel_p, obs_f = self._curve_from_station_rows(rows)
                mask = out["level"].astype(np.float32) == thr
                if rel_p is None:
                    uncalibrated_thresholds.add(float(thr))
                    continue
                values[mask.to_numpy()] = self._interpolate(
                    values[mask.to_numpy()], rel_p, obs_f
                )
        else:
            if not self.point_by_point:
                raise ValueError(
                    "站点可靠性表仍为逐站（spatial_kind=station）。"
                    "请先 Aggregate(coordinates=['id'])，或设置 point_by_point=True。"
                )
            # 逐站：每个 (level, id) 使用各自曲线
            for (thr, sid), _ in out.groupby(["level", "id"], sort=False):
                thr_f = np.float32(thr)
                sid_i = np.int32(sid)
                rows = reliability_table.loc[
                    (reliability_table["level"].astype(np.float32) == thr_f)
                    & (reliability_table["id"].astype(np.int32) == sid_i)
                ]
                if rows.empty:
                    raise ValueError(
                        "No reliability table found for spatial point "
                        f"id={sid_i}, threshold={thr_f}."
                    )
                rel_p, obs_f = self._curve_from_station_rows(rows)
                mask = (out["level"].astype(np.float32) == thr_f) & (
                    out["id"].astype(np.int32) == sid_i
                )
                if rel_p is None:
                    uncalibrated_thresholds.add(float(thr_f))
                    continue
                values[mask.to_numpy()] = self._interpolate(
                    values[mask.to_numpy()], rel_p, obs_f
                )

        out[col] = values.astype(np.float32)
        out.attrs = dict(forecast.attrs)
        out = self._ensure_monotonicity_sta(out, col)
        if uncalibrated_thresholds:
            warnings.warn(
                "The following thresholds were not calibrated due to "
                "insufficient forecast counts in reliability table bins: "
                f"{sorted(uncalibrated_thresholds)}"
            )
        return out

    def process(
        self,
        forecast: Union[xr.DataArray, pd.DataFrame],
        reliability_table: Optional[
            Union[xr.Dataset, pd.DataFrame, Sequence[xr.Dataset]]
        ] = None,
        *,
        data_name: Optional[str] = None,
    ) -> Union[xr.DataArray, pd.DataFrame]:
        """应用可靠性订正，按输入类型分发到网格或站点路径。

        ``reliability_table`` 为 ``None`` 时原样返回预报（便于流水线占位）。
        预报与表须同为网格或同为站点类型。网格在 ``point_by_point`` 下
        逐格点订正，否则使用空间已聚合的整场曲线。

        Parameters
        ----------
        forecast :
            待订正的概率预报（网格 ``DataArray`` 或站点 ``DataFrame``）。
        reliability_table :
            整理后的可靠性表；可为单表、网格表列表，或 ``None``。
        data_name :
            仅站点路径：概率要素列名；默认自动检测。

        Returns
        -------
        xr.DataArray or pd.DataFrame
            与 ``forecast`` 同类型的订正结果：概率裁剪到 ``[0, 1]``，
            并按 ``relative_to_threshold`` 强制跨阈值单调。网格为 meb
            六维 ``DataArray``（``units="1"``）；站点为含订正后要素列的
            六列 ``DataFrame``。表为 ``None`` 时返回输入 ``forecast`` 本身。
        """
        if reliability_table is None:
            return forecast
        if isinstance(forecast, pd.DataFrame) or isinstance(
            reliability_table, pd.DataFrame
        ):
            if not (
                isinstance(forecast, pd.DataFrame)
                and isinstance(reliability_table, pd.DataFrame)
            ):
                raise TypeError("站点路径要求预报与可靠性表均为 DataFrame。")
            return self._apply_station(
                forecast, reliability_table, data_name=data_name
            )
        forecast = meb.checkout_griddata(
            forecast, valid_val=(-np.inf, np.inf, np.nan)
        )
        tables = (
            [reliability_table]
            if isinstance(reliability_table, xr.Dataset)
            else list(reliability_table)
        )
        for t in tables:
            validate_reliability_table_meb(t)
        if self.point_by_point:
            return self._apply_point_by_point(forecast, reliability_table)
        return self._apply_calibration(forecast, reliability_table)
