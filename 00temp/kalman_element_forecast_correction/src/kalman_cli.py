"""Kalman workflow used by the SWVL and STL CLI tasks."""

from __future__ import annotations

import gc
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np

from kalman_element_forecast_correction.src.kalman_fix_plugin import KalmanFix
from kalman_element_forecast_correction.src.kalman_me_plugin import KalmanME
from kalman_element_forecast_correction.utils.grid_utils import check_for_meb_griddata, require_meteva_base


@dataclass(frozen=True)
class KalmanVariableConfig:
    """Path templates for one Kalman soil variable."""

    name: str
    obs_name: str
    levels: tuple[str, ...] = ("5", "10", "40")


VARIABLE_CONFIGS = {
    "SWVL": KalmanVariableConfig(name="SWVL", obs_name="SoilMoisture"),
    "STL": KalmanVariableConfig(name="STL", obs_name="SoilTemper"),
}


def process(
    fcst_path: str,
    obs_path: str,
    time: datetime,
    dtimes,
    kalme_path: str,
    alpha: float = 0.1,
    is_mae: bool = False,
    grid_info=None,
    back_days: int = 5,
    is_kalme_out: bool = True,
    output: str | None = None,
    is_kal_fix: bool = True,
    maskout=None,
    keep_in_memory: bool = False,
    obs_end_time: datetime | None = None,
) -> tuple[list, list]:
    """Run Kalman ME update and optional forecast correction for one start time."""
    meb = require_meteva_base()
    print("=== 当前使用的 fcst_path 模板 ===")
    print(fcst_path)
    print("=== 当前使用的 kalme_path 模板 ===")
    print(kalme_path)

    if grid_info is None:
        grid_info = meb.grid([70, 140, 0.05], [0, 60, 0.05])
    if maskout is not None:
        mask = meb.interp_gg_nearest(maskout, grid=grid_info, outer_value=0).values.astype(int)

    try:
        len(dtimes)
    except TypeError:
        dtimes = [dtimes]

    kal_me_list = []
    result_list = []

    for dtime in dtimes:
        kal_me = None
        try:
            kal_file = meb.get_path(kalme_path, time=time, dt=dtime)
            if _obs_time_allowed(time, dtime, obs_end_time) and os.path.exists(kal_file):
                kal_me = meb.read_griddata_from_nc(kal_file)
                kal_me = meb.interp_gg_linear(kal_me, grid=grid_info, outer_value=np.nan)
                kal_me = check_for_meb_griddata(kal_me)
                print(f"提示：最新 Kalman ME 文件已存在，直接读取：{kal_file}")
            else:
                print(f"KAL_ME 更新开始：{time.strftime('%Y%m%d%H%M')} -- {dtime}")
                time0 = time - timedelta(days=(back_days + int(dtime / 24)))
                flag, time_back = find_files_in_timerange(
                    kalme_path,
                    time0,
                    time,
                    dtime=dtime,
                    obs_end_time=obs_end_time,
                )
                if flag:
                    kal_me = kalman_me_update_timerange(
                        fcst_path,
                        obs_path,
                        kalme_path,
                        time_back=time_back,
                        time_max=time,
                        dtime=dtime,
                        alpha=alpha,
                        is_mae=is_mae,
                        grid_info=grid_info,
                        is_output=is_kalme_out,
                        obs_end_time=obs_end_time,
                    )
                else:
                    kal_me = kalman_me_update_timerange(
                        fcst_path,
                        obs_path,
                        kalme_path,
                        time_back=time0,
                        time_max=time,
                        dtime=dtime,
                        alpha=alpha,
                        is_mae=is_mae,
                        grid_info=grid_info,
                        is_output=is_kalme_out,
                        obs_end_time=obs_end_time,
                    )
            if keep_in_memory:
                kal_me_list.append(kal_me)
        except Exception as err:
            print("## 01 Kalman ME 计算流程出错：")
            print(err)

        if not is_kal_fix:
            continue

        result = None
        try:
            fcst_file = meb.get_path(fcst_path, time=time, dt=dtime)
            if not os.path.exists(fcst_file):
                print(f"错误：预报文件不存在：{fcst_file}")
                continue
            fcst = _read_forecast(fcst_file, grid_info)
            result = KalmanFix()(fcst, me_before=kal_me)

            if maskout is not None:
                result.values[mask == 0] = meb.IV

            if output is not None:
                out_file = meb.get_path(output, time, dt=dtime)
                meb.write_griddata_to_nc(result, out_file, creat_dir=True, effectiveNum=3)
                print(out_file)
        except Exception as err:
            print("## 02 Kalman Fix 订正流程出错：")
            print(err)

        if result is not None and keep_in_memory:
            result_list.append(result)
        elif result is None:
            print(f"提示：未生成订正结果：{fcst_path}")

        if not keep_in_memory:
            for var_name in ("fcst", "result", "kal_me"):
                if var_name in locals():
                    del locals()[var_name]
            gc.collect()

    return kal_me_list, result_list


def kalman_me_update_timerange(
    fcst_path: str,
    obs_path: str,
    kalme_path: str,
    time_back: datetime,
    time_max: datetime,
    dtime: int = 24,
    alpha: float = 0.1,
    is_mae: bool = False,
    grid_info=None,
    is_output: bool = False,
    obs_end_time: datetime | None = None,
):
    """Update Kalman ME from ``time_back`` to ``time_max``."""
    meb = require_meteva_base()
    kalme_plugin = KalmanME(alpha=alpha, is_mae=is_mae)
    flag, time_kal = find_files_in_timerange(
        kalme_path,
        time_back,
        time_max,
        dtime=dtime,
        obs_end_time=obs_end_time,
    )
    if flag:
        kal_file = meb.get_path(kalme_path, time_kal, dt=dtime)
        kal_me = meb.read_griddata_from_nc(kal_file)
        kal_me = meb.interp_gg_linear(kal_me, grid=grid_info, outer_value=np.nan)
        kal_me = check_for_meb_griddata(kal_me)
    else:
        time_list = meb.get_date_list_create(gtime=[time_back, time_max, 24])
        for time_i in time_list:
            flag0, fcst, obs = fcst_obs_exists(
                fcst_path,
                obs_path,
                time=time_i,
                dtime=dtime,
                grid_info=grid_info,
                obs_end_time=obs_end_time,
            )
            if flag0:
                kal_me = kalme_plugin(fcst, obs, me_before=None)
                del fcst, obs
                gc.collect()
                time_kal = time_i
                break
            if time_i >= time_max:
                raise ValueError("kalman_CLI 错误：训练时段内不存在可用的预报和实况数据")
        if is_output:
            out_file = meb.get_path(kalme_path, time_kal, dt=dtime)
            meb.write_griddata_to_nc(kal_me, out_file, creat_dir=True, effectiveNum=3)
            print(f"kalME 输出：{out_file}")

    time0 = time_kal + timedelta(hours=24)
    return _kalman_me_update(
        fcst_path,
        obs_path,
        kalme_path,
        kal_me,
        kalme_plugin,
        time0,
        time_max,
        dtime=dtime,
        grid_info=grid_info,
        is_output=is_output,
        show=True,
        obs_end_time=obs_end_time,
    )


def _kalman_me_update(
    fcst_path: str,
    obs_path: str,
    kalme_path: str,
    kal_me: xr.DataArray,
    kalme_plugin: KalmanME,
    time0: datetime,
    time1: datetime,
    dtime: int = 24,
    grid_info=None,
    is_output: bool = True,
    show: bool = True,
    obs_end_time: datetime | None = None,
):
    meb = require_meteva_base()
    time_list = meb.get_date_list_create(gtime=[time0, time1, 24])
    for time_i in time_list:
        flag1, fcst, obs = fcst_obs_exists(
            fcst_path,
            obs_path,
            time=time_i,
            dtime=dtime,
            grid_info=grid_info,
            obs_end_time=obs_end_time,
        )
        if flag1:
            kal_me = kalme_plugin(fcst, obs, me_before=kal_me)
            del fcst, obs
            gc.collect()
            if is_output:
                out_file = meb.get_path(kalme_path, time_i, dt=dtime)
                meb.write_griddata_to_nc(kal_me, out_file, creat_dir=True, effectiveNum=3)
                if show:
                    print(f"kalME 输出：{out_file}")
        else:
            msg = f"kalman_CLI 提示：更新时段内预报或实况数据不存在：{time_i}-{dtime}"
            if show:
                print(msg)
    return kal_me


def fcst_obs_exists(
    fcst_path: str,
    obs_path: str,
    time: datetime,
    dtime: int = 24,
    grid_info=None,
    obs_end_time: datetime | None = None,
) -> tuple[bool, object | None, object | None]:
    """Read forecast and observation if both files exist."""
    meb = require_meteva_base()
    if grid_info is None:
        grid_info = meb.grid([70, 140, 0.05], [0, 60, 0.05])
    fcst_file = meb.get_path(fcst_path, time, dt=dtime)
    obs_time = time + timedelta(hours=int(dtime))
    if not _obs_time_allowed(time, dtime, obs_end_time):
        return False, None, None
    obs_file = meb.get_path(obs_path, obs_time, dt=0)

    if not (os.path.exists(fcst_file) and os.path.exists(obs_file)):
        return False, None, None

    fcst = _read_forecast(fcst_file, grid_info)
    obs = meb.read_griddata_from_nc(obs_file)
    obs = meb.interp_gg_linear(obs, grid=grid_info, outer_value=np.nan)
    obs = check_for_meb_griddata(obs, valid_val=(-1000, 1000, np.nan))

    if (obs.values == 0).all() or (fcst.values == 0).all():
        return False, None, None
    return True, fcst, obs


def find_files_in_timerange(
    path_fmt: str,
    time0: datetime,
    time1: datetime,
    dtime: int = 24,
    obs_end_time: datetime | None = None,
) -> tuple[bool, datetime | None]:
    """Find the latest file in a time range."""
    meb = require_meteva_base()
    time_list = meb.get_date_list_create(gtime=[time0, time1, 24])[::-1]
    for time_i in time_list:
        if not _obs_time_allowed(time_i, dtime, obs_end_time):
            continue
        file_path = meb.get_path(path_fmt, time=time_i, dt=dtime)
        if os.path.exists(file_path):
            return True, time_i
    return False, None


def get_run_times(start_time: datetime, end_time: datetime, hours: Iterable[int] = (0, 12)):
    """Create run times for each date and configured cycle hour."""
    meb = require_meteva_base()
    times = []
    date_list = meb.get_date_list_create(gtime=[start_time, end_time, 24])
    for date_i in date_list:
        for hour in hours:
            times.append(datetime(date_i.year, date_i.month, date_i.day, hour))
    return times


def run_variable(
    variable: str,
    start_time: datetime,
    end_time: datetime,
    *,
    base_dir: str = "/data234/GUO_data/Kalman_data",
    obs_root: str = "/data234/DataPool/01CLDAS/00HRCLDAS/Hourly",
    alpha: float = 0.15,
    back_days: int = 5,
    dtimes=None,
    obs_end_time: datetime | None = None,
) -> int:
    """Run one variable across levels and cycles."""
    if dtimes is None:
        dtimes = np.arange(0, 360, 6)
    cfg = VARIABLE_CONFIGS[variable]
    times = get_run_times(start_time, end_time)
    total_success = 0

    for level in cfg.levels:
        print(f"开始处理 {variable} 层级：{level}")
        fcst_path = f"{base_dir}/process_data/{variable}/{level}/YYYY/YYYYMMDD/YYYYMMDDHH.TTT.nc"
        obs_path = f"{obs_root}/{cfg.obs_name}/{level}/YYYY/YYYYMMDD/YYYYMMDDHH.TTT.nc"
        kalme_path = f"{base_dir}/kal_me/{variable}/{level}/YYYY/YYYYMMDD/YYMMDDHH.TTT.nc"
        output = f"{base_dir}/output/{variable}/{level}/YYYY/YYYYMMDD/YYMMDDHH.TTT.nc"

        for run_time in times:
            print(f"处理起报时间：{run_time:%Y-%m-%d %H:%M}")
            try:
                process(
                    fcst_path=fcst_path,
                    obs_path=obs_path,
                    time=run_time,
                    dtimes=dtimes,
                    kalme_path=kalme_path,
                    alpha=alpha,
                    back_days=back_days,
                    is_kalme_out=True,
                    output=output,
                    is_kal_fix=True,
                    obs_end_time=obs_end_time,
                )
                total_success += 1
                print(f"完成 {variable} 层级 {level} {run_time:%Y%m%d%H}\n")
            except Exception as err:
                print(f"失败 {variable} 层级 {level} {run_time:%Y%m%d%H}: {err}\n")
    return total_success


def _read_forecast(fcst_file: str, grid_info):
    meb = require_meteva_base()
    fcst = meb.read_griddata_from_nc(fcst_file)
    fcst = meb.interp_gg_linear(fcst, grid=grid_info, outer_value=np.nan)
    fcst = check_for_meb_griddata(fcst, valid_val=(-1000, 1000, np.nan))
    data_valid = fcst.values[~np.isnan(fcst.values)]
    if len(data_valid) > 0:
        median_val = np.median(data_valid)
        if median_val > 150:
            print(f"检测到中位数 {median_val:.1f}：判断为开尔文，自动转换为摄氏度")
            fcst.values = fcst.values - 273.15
        else:
            print(f"检测到中位数 {median_val:.1f}：判断为摄氏度，保持不变")
    return fcst


def _obs_time_allowed(time: datetime, dtime: int, obs_end_time: datetime | None = None) -> bool:
    if obs_end_time is None:
        return True
    return time + timedelta(hours=int(dtime)) <= obs_end_time
