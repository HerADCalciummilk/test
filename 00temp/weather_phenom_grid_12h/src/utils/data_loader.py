# -*- coding: utf-8 -*-
"""
数据加载模块（``src.utils.data_loader``）

使用 meteva.base.get_path 获取路径，meteva.base.read_griddata_from_nc 读取 NC 文件，
返回每个变量在指定 12h 时段内的 ``[4, lat, lon]`` 网格数组。

由 ``src/main.py`` 主程序调用；算法 Plugin 只接收本模块产出的内存数据。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from resource.data_schema import VARS_240H, VARS_72H, MAX_FORECAST_HOUR_72, get_segment_fh
from resource.config import get_nc_path_fmt, str_to_datetime

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# NC文件中各变量的字段名（请根据实际数据文件调整）
# ──────────────────────────────────────────────────────────────
VAR_NC_VARNAME = {
    "R03":     "r03",       # 逐3小时降水量 (mm)
    "PTYPE03": "ptype03",   # 降水相态 (0=无, 1=雨, 2=雪, 3=雨夹雪, 4=冻雨)
    "TCC":     "tcc",       # 总云量 (%, 0~100 或 0~1，自动判断)
    "FOG":     "fog",       # 雾等级 (0=无, 1=轻雾, 2=大雾, 3=浓雾, 4=强浓雾, 5=特强浓雾)
    "HAIL":    "hail",      # 冰雹 (0=无, 1=有)
    "HAZE":    "haze",      # 霾等级 (0=无, 1=轻度, 2=中度, 3=重度, 4=严重)
    "SAND":    "sand",      # 沙尘等级 (0=无, 1=扬沙/浮尘, 2=沙尘暴, 3=强沙尘暴)
    "THUNDER": "thunder",   # 雷暴 (0=无, 1=有)
    "VIS":     "vis",       # 能见度 (m)，备用
}


def _read_one(var: str, init_time_str: str, fh: int):
    """
    用 meteva.base.get_path 获取路径，meteva.base.read_griddata_from_nc 读取单个NC文件

    meteva read_griddata_from_nc 返回 6维 DataArray，维度顺序固定为：
        [member, level, time, dtime, lat, lon]
    对于单一起报时次单一预报时效的NC文件，前4维均为大小1的单元素维度

    Args:
        var          : 变量名，如 'R03'
        init_time_str: 起报时次字符串，格式 YYYYMMDDHH
        fh           : 预报时效（小时），如 3, 6, ..., 240

    Returns:
        (data [lat,lon] float32, lat [nlat] float32, lon [nlon] float32)
        读取失败时返回 (None, None, None)
    """
    try:
        from meteva.base import get_path, read_griddata_from_nc

        init_dt = str_to_datetime(init_time_str)
        fmt = get_nc_path_fmt(var)

        # get_path：第2位置参数=起报时次(datetime)，dt=预报时效整数小时数
        # meteva 占位符：YYYY/MM/DD/HH=起报时次，TTT=3位预报时效
        path = get_path(fmt, init_dt, dt=fh)
        logger.debug(f"  读取路径: {path}")

        # read_griddata_from_nc 返回 meteva 6D DataArray
        # 维度顺序：[member, level, time, dtime, lat, lon]
        # value_name 指定 NC 文件中的变量字段名
        grd = read_griddata_from_nc(
            path,
            value_name=VAR_NC_VARNAME[var],
        )
        if grd is None:
            logger.warning(f"  [{var} FH{fh:03d}] read_griddata_from_nc 返回 None")
            return None, None, None

        # 提取经纬度坐标（meteva 6D DataArray 固定使用 "lat"/"lon" 作为坐标名）
        lat_arr = np.array(grd.coords["lat"].values, dtype=np.float32)
        lon_arr = np.array(grd.coords["lon"].values, dtype=np.float32)

        # 提取 2D 数据：取第0个 member/level/time/dtime 切片
        # 单一时次单一预报时效的NC文件前4维均为大小1
        raw = grd.values   # shape: [member, level, time, dtime, nlat, nlon]
        if raw.ndim == 6:
            data = raw[0, 0, 0, 0, :, :].astype(np.float32)
        elif raw.ndim == 4:
            # 已经广播压缩：[time, dtime, nlat, nlon]
            data = raw[0, 0, :, :].astype(np.float32)
        elif raw.ndim == 2:
            data = raw.astype(np.float32)
        else:
            # 其他情况用 squeeze 兼容
            data = raw.squeeze().astype(np.float32)
            if data.ndim != 2:
                logger.warning(f"  [{var} FH{fh:03d}] 维度异常({raw.ndim}D→{data.ndim}D)，取第0层")
                data = data[0] if data.ndim > 2 else data

        return data, lat_arr, lon_arr

    except FileNotFoundError:
        logger.debug(f"  [{var} FH{fh:03d}] 文件不存在，跳过")
        return None, None, None
    except Exception as e:
        logger.warning(f"  [{var} FH{fh:03d}] 读取异常: {e}")
        return None, None, None


def load_segment(init_time: str, seg_idx: int,
                 max_workers: int = 4) -> tuple:
    """
    并行加载一个12h时段内所有变量的网格数据
    （使用 ThreadPoolExecutor 并发读取 NC 文件，网络共享盘效果显著）

    Args:
        init_time   : 起报时次，格式 YYYYMMDDHH，如 '2026030100'
        seg_idx     : 12h时段序号，从 1 开始（共20段，覆盖FH 003~240）
        max_workers : 并发读取线程数，默认4

    Returns:
        data_dict : dict，key=变量名，value=ndarray[4, lat, lon] float32
                    超出有效时效(72h)的变量，该时次填充全零数组（表示现象不出现）
                    文件缺失的时次填充 NaN
        shape     : (nlat, nlon) 或 None（全部文件缺失时）
        lat_arr   : ndarray[nlat]，纬度坐标（可能为 None）
        lon_arr   : ndarray[nlon]，经度坐标（可能为 None）
    """
    fh_list = get_segment_fh(seg_idx)
    logger.info(f"[{init_time}] 第{seg_idx}段 FH={fh_list}")
    print(f"  加载数据 [{init_time}] 第{seg_idx}段 FH={fh_list} ...")

    # 构建需要实际发起读取的任务（超出时效的直接跳过，后面填零）
    tasks = [(var, fh) for var in VARS_240H for fh in fh_list]
    tasks += [(var, fh) for var in VARS_72H  for fh in fh_list
              if fh <= MAX_FORECAST_HOUR_72]
    print(f"    待读取文件: {len(tasks)} 个 ({len(VARS_240H)}个240h变量 + {len([t for t in tasks if t[0] in VARS_72H])}个72h变量)")

    # ── 并行读取所有 NC 文件 ─────────────────────────────────────
    raw: dict = {}   # (var, fh) -> (data, lat, lon)
    n_workers = min(len(tasks), max_workers)
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_map = {
            executor.submit(_read_one, var, init_time, fh): (var, fh)
            for var, fh in tasks
        }
        for future in as_completed(future_map):
            raw[future_map[future]] = future.result()

    # ── 确定参考形状和坐标 ───────────────────────────────────────
    ref_shape = lat_arr = lon_arr = None
    n_ok = sum(1 for v in raw.values() if v[0] is not None)
    print(f"    成功读取: {n_ok}/{len(tasks)} 个文件")
    for arr, lat, lon in raw.values():
        if arr is not None:
            ref_shape = arr.shape
            lat_arr, lon_arr = lat, lon
            break

    data_dict = {}

    # ── 240h变量：缺失填 NaN ──────────────────────────────────────
    for var in VARS_240H:
        if ref_shape is None:
            data_dict[var] = None
            continue
        filled = [
            raw.get((var, fh), (None,))[0]
            if raw.get((var, fh), (None,))[0] is not None
            else np.full(ref_shape, np.nan, dtype=np.float32)
            for fh in fh_list
        ]
        data_dict[var] = np.stack(filled, axis=0)   # [4, lat, lon]
        print(f"    组装 {var}: shape={data_dict[var].shape}, dtype={data_dict[var].dtype}")

    # ── 72h变量：超时效或缺失填 0 ────────────────────────────────
    for var in VARS_72H:
        if ref_shape is None:
            data_dict[var] = None
            continue
        filled = []
        for fh in fh_list:
            if fh > MAX_FORECAST_HOUR_72:
                filled.append(np.zeros(ref_shape, dtype=np.float32))
            else:
                arr = raw.get((var, fh), (None,))[0]
                filled.append(arr if arr is not None
                              else np.zeros(ref_shape, dtype=np.float32))
        data_dict[var] = np.stack(filled, axis=0)   # [4, lat, lon]
        print(f"    组装 {var}: shape={data_dict[var].shape}, dtype={data_dict[var].dtype}")

    if ref_shape is None:
        logger.error(f"[{init_time}] 第{seg_idx}段：所有文件均缺失，跳过本段")
        print(f"    [WARN] 所有文件缺失，跳过本段")
    else:
        print(f"    数据加载完成: {len(data_dict)} 个变量, 网格 {ref_shape}")

    return data_dict, ref_shape, lat_arr, lon_arr


# ==============================================================================
# 测试入口
# ==============================================================================
if __name__ == "__main__":
    import sys, io
    import xarray as xr
    from unittest.mock import patch

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.disable(logging.CRITICAL)  # 屏蔽日志输出

    ok, fail = [], []
    def check(desc, cond):
        (ok if cond else fail).append(desc)
        print(f"  {'OK' if cond else 'FAIL'} {desc}")

    def make_da(shape2d=(2, 3), lat0=30.0, lon0=110.0):
        """构造 meteva 风格 6D DataArray"""
        lat = np.linspace(lat0, lat0 + shape2d[0] - 1, shape2d[0], dtype=np.float32)
        lon = np.linspace(lon0, lon0 + shape2d[1] - 1, shape2d[1], dtype=np.float32)
        data = np.ones((1, 1, 1, 1, *shape2d), dtype=np.float32)
        return xr.DataArray(data,
            coords={"member": ["d"], "level": [0.], "time": [0], "dtime": [3],
                    "lat": lat, "lon": lon},
            dims=["member", "level", "time", "dtime", "lat", "lon"])

    # TEST 1: get_path 路径生成
    print("\n[TEST 1] get_path 路径生成")
    try:
        from meteva.base import get_path
        from resource.config import get_nc_path_fmt, str_to_datetime
        init_dt = str_to_datetime("2026030100")
        for var, fh in [("R03", 3), ("FOG", 6), ("TCC", 240)]:
            p = get_path(get_nc_path_fmt(var), init_dt, dt=fh)
            check(f"{var} FH{fh:03d} 路径正确",
                  var in p and "2026030100" in p and f"{fh:03d}" in p and p.endswith(".nc"))
    except Exception as e:
        check(f"路径生成异常: {e}", False)

    # TEST 2: _read_one Mock
    print("\n[TEST 2] _read_one")
    try:
        da = make_da((2, 3))
        with patch("meteva.base.get_path", return_value="/f.nc"), \
             patch("meteva.base.read_griddata_from_nc", return_value=da):
            d, lat, lon = _read_one("R03", "2026030100", 3)
        check("shape==(2,3)",  d is not None and d.shape == (2, 3))
        check("dtype float32", d is not None and d.dtype == np.float32)
        # 文件不存在 → (None, None, None)
        with patch("meteva.base.get_path", return_value="/f.nc"), \
             patch("meteva.base.read_griddata_from_nc", side_effect=FileNotFoundError):
            d2, _, _ = _read_one("FOG", "2026030100", 6)
        check("FileNotFoundError → None", d2 is None)
    except Exception as e:
        check(f"_read_one 异常: {e}", False)

    # TEST 3: load_segment seg=1（全在72h内）
    print("\n[TEST 3] load_segment seg=1")
    try:
        from resource.data_schema import VARS_240H, VARS_72H
        S = (4, 5)
        def _mk(path, value_name=None, **kw): return make_da(S)
        with patch("meteva.base.get_path", return_value="/f.nc"), \
             patch("meteva.base.read_griddata_from_nc", side_effect=_mk):
            dd, shape, _, _ = load_segment("2026030100", 1)
        check("shape正确", shape == S)
        check("所有变量shape=(4,4,5)",
              all(dd.get(v) is not None and dd[v].shape == (4, *S)
                  for v in VARS_240H + VARS_72H))
    except Exception as e:
        check(f"load_segment seg1 异常: {e}", False)

    # TEST 4: load_segment seg=7（72h变量超时效 → 填零）
    print("\n[TEST 4] load_segment seg=7 超72h填零")
    try:
        from resource.data_schema import VARS_72H
        S = (4, 5)
        def _mk2(path, value_name=None, **kw): return make_da(S)
        with patch("meteva.base.get_path", return_value="/f.nc"), \
             patch("meteva.base.read_griddata_from_nc", side_effect=_mk2):
            dd, _, _, _ = load_segment("2026030100", 7)
        check("72h变量全零",
              all(dd.get(v) is not None and np.all(dd[v] == 0) for v in VARS_72H))
    except Exception as e:
        check(f"load_segment seg7 异常: {e}", False)

    print("\n" + "=" * 40)
    print(f"  通过 {len(ok)} / 失败 {len(fail)}" + (f": {fail}" if fail else " -- 全部通过"))
    sys.exit(1 if fail else 0)
