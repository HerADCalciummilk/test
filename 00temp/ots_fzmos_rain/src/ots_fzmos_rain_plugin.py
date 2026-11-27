# -*- coding: utf-8 -*-
"""两段关键算法。只接收已经读好的数据，不读文件、不写结果。

``OtsThresholdPlugin``：用历史 EC 与实况做出 20×10 阈值表。
``OtsForecastPlugin``：用 12 小时场和这张表做反距离插值、分段订正，并合成 24 小时降水。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import numpy as np

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
for _p in (_SRC_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _util_plugin import (
    LEAD_HOURS,
    build_interpolation_plan,
    calculate_lead_threshold,
    combine_rain24,
    correct_precipitation,
    inverse_distance_interpolate,
)
from utils.base_plugin import BasePlugin
from utils.multipro_plugin import SimpleParallelTool


def _threshold_lead(
    fh_index,
    iday,
    start_day,
    station_count,
    ec_by_year,
    obs_by_year,
    begin_year,
    end_year,
):
    """供进程池调用的单时效阈值搜索。失败时返回 None，由插件汇总报错。"""
    try:
        return calculate_lead_threshold(
            fh_index,
            iday,
            start_day,
            station_count,
            ec_by_year,
            obs_by_year,
            begin_year=begin_year,
            end_year=end_year,
        )
    except Exception as exc:
        print("阈值计算失败 fh_index=%s: %s" % (fh_index, exc))
        return None


def _correct_one(forecast_hour, values, source_grid, output_grid, radius, threshold_row):
    """供进程池调用的单时效插值订正。失败时返回 None，24 小时合成会跳过该时效。"""
    try:
        plan = build_interpolation_plan(source_grid, output_grid, radius)
        interpolated = inverse_distance_interpolate(values, plan)
        return correct_precipitation(interpolated, threshold_row)
    except Exception as exc:
        print("格点订正失败 forecast_hour=%s: %s" % (forecast_hour, exc))
        return None


class OtsThresholdPlugin(BasePlugin):
    """第一段：历史样本上的 TS 阈值表。返回形状 (20, 10)。"""

    def process(
        self,
        iday,
        start_day,
        station_count,
        ec_by_year,
        obs_by_year,
        begin_year,
        end_year,
        pro_count=1,
    ):
        fixed = {
            "iday": iday,
            "start_day": start_day,
            "station_count": station_count,
            "ec_by_year": ec_by_year,
            "obs_by_year": obs_by_year,
            "begin_year": begin_year,
            "end_year": end_year,
        }
        count = int(pro_count or 1)
        if count > 1:
            started = datetime.now()
            rows = SimpleParallelTool(
                target_func=_threshold_lead,
                parallel_mode="sync",
                with_return=True,
                num_process=count,
                fixed_params=fixed,
            ).process({"fh_index": list(range(20))})
            print(">>> Time elasped: %s" % (datetime.now() - started).total_seconds())
            if any(row is None for row in rows):
                raise RuntimeError("有预报时效的阈值计算失败")
            return np.vstack(rows)

        table = np.empty((20, 10), dtype=np.float32)
        for fh_index in range(20):
            # 每个时效独立：30 个候选阈值上累计 TS，取该等级最优映射值。
            table[fh_index, :] = calculate_lead_threshold(fh_index, **fixed)
        return table


class OtsForecastPlugin(BasePlugin):
    """第二段：20 个 12 小时场插值订正，再按时效顺序合成 24 小时降水。"""

    def process(self, fields, source_grids, output_grid, radius, thresholds, pro_count=1):
        count = int(pro_count or 1)
        rows = [thresholds[index] for index in range(20)]
        if count > 1:
            started = datetime.now()
            rain12 = SimpleParallelTool(
                target_func=_correct_one,
                parallel_mode="sync",
                with_return=True,
                num_process=count,
                fixed_params={"output_grid": output_grid, "radius": radius},
            ).process(
                {
                    "forecast_hour": list(LEAD_HOURS),
                    "values": list(fields),
                    "source_grid": list(source_grids),
                    "threshold_row": rows,
                }
            )
            print(">>> Time elasped: %s" % (datetime.now() - started).total_seconds())
        else:
            rain12 = []
            plan = None
            plan_grid = None
            for values, source_grid, threshold_row in zip(fields, source_grids, rows):
                if plan is None or source_grid != plan_grid:
                    plan = build_interpolation_plan(source_grid, output_grid, radius)
                    plan_grid = source_grid
                interpolated = inverse_distance_interpolate(values, plan)
                rain12.append(correct_precipitation(interpolated, threshold_row))

        rain24 = [None]
        previous = rain12[0]
        for current in rain12[1:]:
            if previous is not None and current is not None:
                rain24.append(combine_rain24(current, previous))
            else:
                rain24.append(None)
            previous = current
        return rain12, rain24
