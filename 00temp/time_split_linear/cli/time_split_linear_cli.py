# -*- coding: utf-8 -*-
"""预报时效线性拆分。

``process`` 读入并拼接，再调用 ``TimeSplitLinearPlugin``。
``[timesplit]`` 的键都是具名参数。``None`` 再读 ini。

由 ``python -m time_split_linear`` 或 ``python -m cli`` 启动。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np


def _bootstrap_paths() -> None:
    root = str(Path(__file__).resolve().parent.parent)
    src = str(Path(root) / "src")
    for path in (src, root):
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_paths()

from utils.merge_params import merge_params
from utils.util_env import resolve_args


@merge_params(section="timesplit", anchor=__file__)
def process(
    input_fh: str = None,
    output_fh: str = None,
    interp_method: str = None,
    input_fmt: str = None,
    time: str = None,
    output_fmt: str = None,
    uv_fmt: str = None,
    delta: str = None,
    delta_hour: str = None,
    is_fill0: bool = None,
    is_min: bool = None,
    index: str = None,
    module: str = None,
    config: str = None,
    io_method=None,
) -> Tuple[Any, Any]:
    """补齐参数，读数拼接，再调用时间拆分插件。"""
    cfg = resolve_args(
        module=module,
        input_fh=input_fh,
        output_fh=output_fh,
        interp_method=interp_method,
        input_fmt=input_fmt,
        time=time,
        output_fmt=output_fmt,
        uv_fmt=uv_fmt,
        delta=delta,
        delta_hour=delta_hour,
        is_fill0=is_fill0,
        is_min=is_min,
        index=index,
        config=config,
    )

    axis = str(cfg["index"])
    if axis not in ("dtime", "time"):
        raise ValueError("index 只支持 dtime 或 time")
    fill0 = bool(cfg["is_fill0"])

    # 解析输入时效；输出三元组交给插件再展开
    in_parts = [item.strip() for item in str(cfg["input_fh"]).split(",") if item.strip()]
    if len(in_parts) != 3:
        raise ValueError(f"时效三元组须是 start,stop,step，收到: {cfg['input_fh']}")
    in_start, in_stop, in_step = (float(value) for value in in_parts)
    fhs = np.arange(in_start, in_stop + 1, in_step)
    if np.allclose(fhs, np.rint(fhs)):
        fhs = np.rint(fhs).astype(np.int64)

    out_parts = [item.strip() for item in str(cfg["output_fh"]).split(",") if item.strip()]
    if len(out_parts) != 3:
        raise ValueError(f"时效三元组须是 start,stop,step，收到: {cfg['output_fh']}")
    output_fh_list = [float(value) for value in out_parts]

    # 解析起报时间
    raw_times = [item.strip() for item in str(cfg["time"]).split(",") if item.strip()]
    if not raw_times:
        raise ValueError("time 未指定")
    times = []
    for item in raw_times:
        if len(item) == 12:
            times.append(datetime.strptime(item, "%Y%m%d%H%M"))
        else:
            times.append(datetime.strptime(item, "%Y%m%d%H"))

    if axis == "dtime":
        if len(times) != 1:
            raise ValueError("index=dtime 时 time 只能有一个起报时间")
        read_time = times[0]
        read_fhs = fhs
        is_ob = False
    else:
        if len(times) > 1:
            anchor = times[0]
            read_fhs = []
            for item in times:
                hours = (item - anchor).total_seconds() / 3600.0
                rounded = round(hours)
                if abs(hours - rounded) >= 1e-6:
                    raise ValueError(
                        f"index=time 时各时次须与首时次相差整小时，收到锚点 {anchor} 与 {item}"
                    )
                read_fhs.append(int(rounded))
            read_time = anchor
        else:
            read_time = times[0]
            read_fhs = list(fhs)
        is_ob = True

    # 读主场；有 uv_fmt 时再读 V 分量
    from time_split_linear_plugin import TimeSplitLinearPlugin
    from utils.grid_combine import read_multi_griddata

    fcst = None
    uv = None
    for kind, fmt in (("主场", cfg["input_fmt"]), ("V 分量", cfg.get("uv_fmt"))):
        if not fmt:
            continue
        grd = read_multi_griddata(
            fmt,
            read_time,
            read_fhs,
            io_method=io_method,
            is_ob=is_ob,
            is_fill0=fill0,
        )
        if grd is None:
            print(f"未读到{kind}数据")
            return None, None
        if kind == "主场":
            fcst = grd
        else:
            uv = grd

    # 对内存场做时间插值
    splitter = TimeSplitLinearPlugin(
        output_fh_list=output_fh_list,
        interp_method=cfg["interp_method"],
        output_fmt=cfg.get("output_fmt"),
        delta=cfg.get("delta"),
        is_Min=bool(cfg["is_min"]),
        index=axis,
    )
    return splitter.process(fcst, uv=uv)
