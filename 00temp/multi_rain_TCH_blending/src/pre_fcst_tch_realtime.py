# -*- coding: utf-8 -*-
"""TCH 多模式集成：读数、路径与起报时次辅助。

权重与加权合成见 ``TchWeightPlugin`` / ``TchBlendPlugin``；
调度流程在 ``cli/multi_rain_TCH_blending_cli.py``。

命令行（在 ``00temp`` 目录）::

    python -m multi_rain_TCH_blending
"""
from __future__ import annotations

import datetime
import os
import sys
from typing import Optional

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
for _p in (_SRC_DIR, _ROOT_DIR):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _SRC_DIR)
sys.path.insert(0, _ROOT_DIR)

import meteva.base as meb
import numpy as np
import xarray as xr

def normalize_ipt_type(ipt_type: Optional[str] = None) -> str:
    """输入格点格式：默认 ``nc``；兼容 ``m4`` / micaps4。"""
    text = str(ipt_type or "nc").strip().lower()
    if text in ("nc", "netcdf", "netcdf4"):
        return "nc"
    if text in ("m4", "micaps4", "diamond4"):
        return "m4"
    raise ValueError("不支持的 ipt_type=%r，仅支持 nc / m4" % (ipt_type,))


def detect_grid_format(path: str, preferred: Optional[str] = None) -> str:
    """按扩展名识别格点格式；无扩展名时回落到 ``preferred``（默认 nc）。"""
    ext = os.path.splitext(str(path))[1].lstrip(".").lower()
    if ext in ("nc", "nc4", "cdf"):
        return "nc"
    if ext in ("m4", "micaps4"):
        return "m4"
    pref = normalize_ipt_type(preferred)
    if pref == "nc":
        raise ValueError("无法识别为 nc：%s（请使用 .nc 后缀或 ipt_type=nc 且路径正确）" % path)
    return pref


def read_model_grid(path: str, ipt_type: Optional[str] = None):
    """按格式读模式降水格点：nc → ``read_griddata_from_nc``，m4 → micaps4。"""

    fmt = detect_grid_format(path, preferred=ipt_type)
    if fmt == "nc":
        print("读取 NetCDF：", path)
        grd = meb.read_griddata_from_nc(path)
    else:
        print("读取 Micaps4：", path)
        grd = meb.read_griddata_from_micaps4(path)
    if grd is None:
        raise RuntimeError("格点读取失败（格式=%s）：%s" % (fmt, path))
    return grd, fmt


def model_grid_path(dir_model, model_name, initial_time, fcst_hr, ipt_type: Optional[str] = "nc"):
    """拼某个模式、某个时效的格点路径（默认 ``.nc``，可选 ``.m4``）。

    ``meteva.base.get_path`` 会把整段字符串里的 ``MM`` 换成月份。
    目录名 ``NIMM`` 因此会被改成 ``NI05``。这里只把文件名模板交给它。
    """

    fmt = normalize_ipt_type(ipt_type)
    trnow = datetime.datetime.strftime(initial_time, "%Y-%m-%d %H:%M:%S %p")
    date_str = trnow[0:4] + trnow[5:7] + trnow[8:10]
    folder = dir_model + model_name + "/sfc/" + date_str + "/"
    return folder + meb.get_path("YYYYMMDDHH.TTT", initial_time, fcst_hr) + "." + fmt


def resolve_model_file(dir_model, model_name, initial_time, fcst_hr, ipt_type: Optional[str] = "nc"):
    """解析实际存在的模式文件：优先配置格式（默认 nc），没有再尝试备用格式。"""
    preferred = normalize_ipt_type(ipt_type)
    order = ("nc", "m4") if preferred == "nc" else ("m4", "nc")
    tried = []
    for fmt in order:
        path = model_grid_path(dir_model, model_name, initial_time, fcst_hr, ipt_type=fmt)
        tried.append(path)
        if os.path.exists(path):
            if fmt != preferred:
                print(
                    "提示：优先格式 %s 不存在，改用已存在的 %s：%s"
                    % (preferred, fmt, path)
                )
            return path, fmt
    return None, preferred


def model_m4_path(dir_model, model_name, initial_time, fcst_hr):
    """兼容旧名：固定拼 ``.m4`` 路径。"""
    return model_grid_path(dir_model, model_name, initial_time, fcst_hr, ipt_type="m4")


def get_model_data(
    dir_model,
    model_list_source,
    initial_time,
    fcst_hr,
    grid_lon,
    grid_lat,
    ipt_type: Optional[str] = "nc",
):
    """读取指定时效各模式降水格点场，插值到统一网格后按成员合并。

    默认按 NetCDF（``.nc``）查找并用 ``read_griddata_from_nc`` 读取；
    若 nc 不存在再尝试 micaps4。某模式文件都不存在时跳过该成员。
    """

    preferred = normalize_ipt_type(ipt_type)
    grid2 = meb.grid(list(grid_lon), list(grid_lat))
    time2 = initial_time
    model_array = []
    ii = 0

    for num in range(0, len(model_list_source)):
        name = model_list_source[num]
        fname, fmt = resolve_model_file(dir_model, name, time2, fcst_hr, ipt_type=preferred)
        print(fname or model_grid_path(dir_model, name, time2, fcst_hr, ipt_type=preferred))

        if not fname:
            print("当前模式资料不存在（已试 nc/m4）：" + name)
            continue

        print("当前模式资料存在：%s（格式=%s）" % (name, fmt))
        grd, used_fmt = read_model_grid(fname, ipt_type=fmt)
        if used_fmt != fmt:
            print("警告：路径扩展名与探测格式不一致，已按 %s 读取" % used_fmt)
        grd = meb.interp_gg_linear(grd, grid2)
        meb.set_griddata_coords(grd, member_list=[name])

        if ii == 0:
            model_array = grd
        else:
            model_array = xr.concat([model_array, grd], dim="member")
        ii = ii + 1

    return model_array


def build_title(trnow, hour_str, dtime, model_name):
    """构造 Micaps 输出标题：YYYY年MM月DD日HH时{h}时效24小时降水预报场(名称)。"""
    return (
        trnow[0:4] + "年" + trnow[5:7] + "月" + trnow[8:10] + "日"
        + hour_str + "时" + str(dtime)
        + "h时效24小时降水预报场(" + model_name + ")"
    )


def select_initial_time(now, threshold, late_hour, early_hour):
    """按北京时阈值把“当前时间”落到 UTC 00 或前一日 UTC 12。"""
    time1 = now
    if time1.hour >= threshold:
        initial_hour = late_hour
    else:
        initial_hour = early_hour
        time1 = time1 - datetime.timedelta(hours=24)
    return datetime.datetime(time1.year, time1.month, time1.day, initial_hour, 0)


def clock(initial_time: Optional[str] = None) -> datetime.datetime:
    """解析起报字符串；空则取当前时间。"""
    if initial_time:
        return datetime.datetime.strptime(str(initial_time).strip(), "%Y%m%d%H%M%S")
    return datetime.datetime.now()


def prepare_ensemble_for_tch(qpf_model, maskout_series):
    """掩膜后展平为 ``(格点, 成员)``，供权重插件使用。"""
    nx = qpf_model["lon"].shape[0]
    ny = qpf_model["lat"].shape[0]
    ndim = qpf_model["member"].shape[0]
    qpf_flat = np.array(qpf_model[:, 0, 0, 0, :, :]).reshape(ndim, ny * nx).transpose()
    mask_rep = np.expand_dims(maskout_series, 0).repeat(ndim, axis=0).transpose()
    qpf_flat = np.array(qpf_flat, copy=True)
    qpf_flat[mask_rep == -1] = 0
    return qpf_flat, int(ndim), int(ny), int(nx)
