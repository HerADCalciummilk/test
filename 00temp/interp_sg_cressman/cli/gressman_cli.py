# -*- coding: utf-8 -*-
"""新增算法入口：度制幂次 GressMan（rain24 原版）。

与 ``interp_sg_cressman_cli``（km 版核）并列独立，不改旧入口。
在 ``cli`` 目录执行 ``python -m gressman_cli``。
"""
import os
import sys
from datetime import datetime
from typing import List

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.merge_params import merge_params
from utils.multipro_plugin import SimpleParallelTool

import meteva.base as meb
import meteva.base as meb
from gressman_plugin import GressManInterpolation



def _abs_path(path):
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    text = os.path.expanduser(text)
    if os.path.isabs(text):
        return os.path.normpath(text)
    return os.path.normpath(os.path.join(_ROOT_DIR, text))


def _float_seq(value, n=None):
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        vals = [float(item.strip()) for item in value.split(",") if item.strip()]
    elif isinstance(value, (int, float)):
        vals = [float(value)]
    else:
        vals = [float(item) for item in value]
    if n is not None and len(vals) != n:
        raise ValueError("期望 %d 个数，得到 %d 个" % (n, len(vals)))
    return vals


def _read_sta(path, sta_type):

    if not path or not os.path.exists(path):
        raise FileNotFoundError("站点文件不存在: %s" % path)
    if (sta_type or "m3").lower() == "nc":
        return meb.read_stadata_from_nc(path)
    return meb.read_stadata_from_micaps3(path)


def _read_griddata(path, gtype):

    if not path or not os.path.exists(path):
        raise FileNotFoundError("格点文件不存在: %s" % path)
    if (gtype or "m4").lower() == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _process(param, **run):
    """读站点与背景格点，度制 GressMan 插值后写出 Micaps4。"""
    merged = {**param, **run}
    try:


        sta = _read_sta(merged["sta_path"], merged["sta_type"])
        background_path = merged.get("background_path")
        if not background_path:
            raise ValueError("GressMan 需要 background_path（背景/初值格点）")
        background = _read_griddata(background_path, merged["background_type"])
        grd_out = GressManInterpolation(
            sta,
            background,
            merged["distance_limits"],
            num_limit=merged["num_limit"],
            smooth=merged["smooth"],
            power_param=merged["power_param"],
            rain_limit=merged["rain_limit"],
        )
        output_path = merged["output_path"]
        out_dir = os.path.dirname(output_path or "")
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        meb.write_griddata_to_micaps4(grd_out, output_path, creat_dir=True)
        print("GressMan 插值完成 →", output_path)
        return grd_out
    except Exception as exc:
        print("GressMan 插值失败 %s: %s" % (param.get("sta_path"), exc))
        return False


@merge_params()
def process(
    sta_path: str = None,
    background_path: str = None,
    output_path: str = "resource/output/gressman.m4",
    distance_limits: List[float] = None,
    num_limit: float = 1.0,
    smooth: float = 0.001,
    power_param: float = 2.0,
    rain_limit: float = None,
    sta_type: str = "m3",
    background_type: str = "m4",
    pro_count: int = 1,
    config=None,
):
    """新增 GressMan 入口。``config`` 只换配置文件。不改 km 版 ``interp_sg_cressman_cli``。"""
    sta_path = _abs_path(sta_path)
    background_path = _abs_path(background_path)
    output_path = _abs_path(output_path)
    if not sta_path:
        raise ValueError("缺少参数: sta_path")
    if not background_path:
        raise ValueError("缺少参数: background_path")
    if not output_path:
        raise ValueError("缺少参数: output_path")
    if distance_limits is None:
        distance_limits = [0.8, 0.6, 0.4, 0.2]
    params = [{
        "sta_path": sta_path,
        "output_path": output_path,
        "background_path": background_path,
    }]
    run = {
        "distance_limits": _float_seq(distance_limits, None) or list(distance_limits),
        "num_limit": float(num_limit),
        "smooth": float(smooth),
        "power_param": float(power_param),
        "rain_limit": None if rain_limit is None else float(rain_limit),
        "sta_type": (sta_type or "m3").lower(),
        "background_type": (background_type or "m4").lower(),
    }
    count = int(pro_count or 1)
    if count > 1:
        started = datetime.now()
        SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=count,
            fixed_params=run,
        ).process({"param": params})
        print(">>> Time elasped: " + str((datetime.now() - started).total_seconds()))
    else:
        for param in params:
            _process(param, **run)
