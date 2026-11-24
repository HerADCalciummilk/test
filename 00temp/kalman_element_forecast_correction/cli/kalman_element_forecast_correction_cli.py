# -*- coding: utf-8 -*-
"""Kalman 要素预报订正。

``process`` 按 ``module`` 调度订正或拷贝。
订正链路调用 ``run_variable``，其中使用 ``KalmanME`` 与 ``KalmanFix``。
配置键都是具名参数。``None`` 再读 ini。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PARENT = _ROOT.parent
for _path in (str(_ROOT), str(_PARENT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from kalman_element_forecast_correction.utils.util_env import (
    resolve_kalman,
    resolve_module,
    resolve_trans,
)
from utils.merge_params import merge_params


def _date_range(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    if start_date:
        start_time = datetime.strptime(start_date, "%Y%m%d")
        end_time = datetime.strptime(end_date or start_date, "%Y%m%d")
        print(f"手动模式：处理 {start_time:%Y%m%d} 至 {end_time:%Y%m%d}")
        return start_time, end_time
    yesterday = datetime.now() - timedelta(days=1)
    start_time = datetime(yesterday.year, yesterday.month, yesterday.day)
    print(f"实时模式：自动处理前一天 {start_time:%Y-%m-%d}")
    return start_time, start_time


@merge_params(sections=("cli", "kalman", "trans"), anchor=__file__)
def process(
    module: str = None,
    start_date: str = None,
    end_date: str = None,
    base_dir: str = None,
    obs_root: str = None,
    alpha: float = None,
    back_days: int = None,
    variables: str = None,
    obs_end_time: str = None,
    date: str = None,
    swvl_source: str = None,
    stl_source: str = None,
    target_base: str = None,
    config: str = None,
):
    """按 module 运行订正或源数据拷贝。"""
    name = resolve_module(module, config=config)
    if name == "trans":
        from kalman_element_forecast_correction.src.data_transfer import (
            DEFAULT_TRANSFER_CONFIG,
            TransferConfig,
            copy_process_data,
        )

        resolved = resolve_trans(
            date=date,
            swvl_source=swvl_source,
            stl_source=stl_source,
            target_base=target_base,
            config=config,
        )
        run_date = datetime.strptime(resolved["date"], "%Y%m%d") if resolved["date"] else None
        config_obj = TransferConfig(
            source_bases={"SWVL": resolved["swvl_source"], "STL": resolved["stl_source"]},
            target_base=resolved["target_base"],
            level_mapping=DEFAULT_TRANSFER_CONFIG.level_mapping,
        )
        # 把 SWVL/STL 源场拷到处理目录
        copy_process_data(run_date, config=config_obj)
        return 0

    resolved = resolve_kalman(
        start_date=start_date,
        end_date=end_date,
        base_dir=base_dir,
        obs_root=obs_root,
        alpha=alpha,
        back_days=back_days,
        variables=variables,
        obs_end_time=obs_end_time,
        config=config,
    )
    start_time, end_time = _date_range(resolved["start_date"], resolved["end_date"])
    variables_list = [item.strip().upper() for item in resolved["variables"].split(",") if item.strip()]
    obs_end = datetime.strptime(resolved["obs_end_time"], "%Y%m%d%H") if resolved["obs_end_time"] else None
    from kalman_element_forecast_correction.src.kalman_cli import run_variable

    total_success = 0
    # run_variable 内调用 KalmanME 与 KalmanFix
    for variable in variables_list:
        total_success += run_variable(
            variable,
            start_time,
            end_time,
            base_dir=resolved["base_dir"],
            obs_root=resolved["obs_root"],
            alpha=resolved["alpha"],
            back_days=resolved["back_days"],
            obs_end_time=obs_end,
        )
    print(f"全部 Kalman 任务完成，成功任务数：{total_success}")
    return 0
