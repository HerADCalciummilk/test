# -*- coding: utf-8 -*-
"""多时效格点读取，以及不扩展起报时间的拼接。

``meteva_base.concat`` 在只有一个起报时间时，会把时间轴扩成该时刻再加 12 小时。
这里的拼接只用各场实际的 ``time`` 坐标，单个起报时间保持一格。

- ``read_multi_griddata``：同一起报，沿 ``dtime`` 读拼。
- ``concat_griddata``：通用坐标并集拼接。
"""
from __future__ import annotations

import datetime
import os
from typing import Sequence

import meteva_base as meb
import numpy as np


def read_multi_griddata(fmt, time, fhs, io_method=None, is_ob=False, is_fill0=True):
    """读取多个时效文件，沿 ``dtime`` 拼成一块。

    Args:
        fmt: 路径模板，可含 ``YYYY``、``TTT`` 等占位符。
        time: 起报时间。``is_ob`` 为真时，文件时间 = 起报时间 + 时效，写入的时效为 0。
        fhs: 已展开的时效序列。
        io_method: 读网格函数；默认 ``meteva_base.read_griddata_from_nc``。
        is_ob: 按实况路径规则读取。
        is_fill0: 为真时不读时效 0 文件，等读到后续帧后按该帧形状补全 0 场。

    Returns:
        拼好的格点；无文件或拼接失败时返回 ``None``。
    """
    if io_method is None:
        io_method = meb.read_griddata_from_nc

    grd_list = []
    pending_zero = False  # is_fill0 时：已遇到时效 0，等下一帧再补全 0 场
    for i, fh in enumerate(fhs):
        if is_ob:
            time0 = time + datetime.timedelta(hours=int(fh))
            fh0 = 0
        else:
            time0 = time
            fh0 = int(fh)

        path = meb.get_path(fmt, time=time0, dt=fh0)
        if i % 5 == 0:
            print("Read FILE: ", i, time0, fh0, path)
        if not path or not os.path.exists(path):
            print("File missing: {}-{}".format(time0, fh0))
            continue

        # 时效 0 且要求填 0：先记下，真正补场放到读到非 0 时效之后。
        if is_fill0 and fh0 == 0:
            pending_zero = True
            continue

        grd = io_method(path)
        meb.set_griddata_coords(grd, gtime=[time0], dtime_list=[fh0])
        if pending_zero:
            zero = grd.copy()
            zero.values = np.zeros_like(zero.values)
            meb.set_griddata_coords(zero, dtime_list=[0])
            grd_list.append(zero)
            pending_zero = False
        grd_list.append(grd)

    if not grd_list:
        return None
    try:
        return concat_griddata([item.astype(np.float32) for item in grd_list])
    except Exception as err:
        print(err)
        return None


def concat_griddata(data_list: Sequence):
    """沿 member / level / time / dtime 拼接格点。

    起报时间取各场 ``time`` 的并集。
    水平网格不一致时，先插到第一块的经纬度再写入；缺测填 ``meb.IV``。
    """
    grids = [item for item in data_list if item is not None]
    if not grids:
        print("无需要拼接的数据")
        return None

    # 收集各维坐标并集。time/dtime/level 排序；member 保持首次出现顺序。
    times = sorted(_unique_values(grids, "time", lambda v: np.datetime64(v, "ns")))
    dtimes = sorted(_unique_values(grids, "dtime", int))
    levels = sorted(_unique_values(grids, "level", float))
    members = _unique_values(grids, "member", str)

    ref = meb.get_grid_of_data(grids[0])
    combined = meb.grid(
        ref.glon,
        ref.glat,
        [meb.all_type_time_to_datetime(t) for t in times],
        dtime_list=dtimes,
        level_list=levels,
        member_list=members,
        units_attr=ref.units,
        model_var_attr=ref.model_var,
        dtime_units_attr=ref.dtime_units,
        level_type_attr=ref.level_type,
        time_type_attr=ref.time_type,
        time_bounds_attr=ref.time_bounds,
    )
    grd_all = meb.grid_data(combined)
    grd_all.values[...] = meb.IV

    index_level = {float(v): i for i, v in enumerate(grd_all["level"].values)}
    index_time = {np.datetime64(v, "ns"): i for i, v in enumerate(grd_all["time"].values)}
    index_dtime = {int(v): i for i, v in enumerate(grd_all["dtime"].values)}
    index_member = {str(v): i for i, v in enumerate(grd_all["member"].values)}
    grid_xy = meb.grid(combined.glon, combined.glat)
    ref_lon = np.asarray(grids[0]["lon"].values)
    ref_lat = np.asarray(grids[0]["lat"].values)

    for grd in grids:
        same_xy = (
            np.array_equal(np.asarray(grd["lon"].values), ref_lon)
            and np.array_equal(np.asarray(grd["lat"].values), ref_lat)
        )
        source = grd if same_xy else meb.interp_gg_linear(grd, grid_xy, outer_value=np.nan)
        if source is None:
            continue
        for i, level in enumerate(source["level"].values):
            i_level = index_level[float(level)]
            for j, issue_time in enumerate(source["time"].values):
                i_time = index_time[np.datetime64(issue_time, "ns")]
                for k, lead in enumerate(source["dtime"].values):
                    i_dtime = index_dtime[int(lead)]
                    for m, member in enumerate(source["member"].values):
                        i_member = index_member[str(member)]
                        grd_all.values[i_member, i_level, i_time, i_dtime, :, :] = source.values[
                            m, i, j, k, :, :
                        ]

    grd_all.attrs = dict(grids[0].attrs)
    return grd_all


def _unique_values(grids, name, cast):
    """按首次出现顺序收集 ``name`` 维上的不重复坐标。"""
    found = []
    seen = set()
    for grd in grids:
        for value in np.asarray(grd[name].values):
            key = cast(value)
            if key not in seen:
                seen.add(key)
                found.append(key)
    return found
