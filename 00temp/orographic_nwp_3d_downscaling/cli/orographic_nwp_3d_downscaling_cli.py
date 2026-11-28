# -*- coding: utf-8 -*-
"""地形精细化插值。

``process`` 按四步走：读入，空间插值插件，写出 NetCDF，最优参数插件后写出 eta 的 h5。
空间插值里按开关再做最高最低和时间插值。数值步骤与原流程相同。
``config`` 与 ``ini_path`` 都可指定本次 ini，``config`` 优先。
四级优先级由 ``@merge_params`` 处理：调用参数 > 指定 ini > 默认 ``resource/conf.ini`` > 函数预设。

在 ``00temp``::

    python -m orographic_nwp_3d_downscaling begin_date=2026111813 operation=i debug=1 update=1
    python -m utils.nimm_cli orographic_nwp_3d_downscaling ini_path=resource/conf.ini

在本包目录::

    python -m cli begin_date=2026111813
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fast_refine_interp_plugin import BestEtaPlugin, MaxMinPlugin, SpatialInterpPlugin, TimeInterpPlugin
from utils.interp_io import (
    check_output_files,
    read_element_paths,
    read_environment,
    read_interp_targets,
    read_model_terrain,
    select_forecast_hours,
    write_netcdf,
)
from utils.merge_params import merge_params

_ROOT = Path(_ROOT_DIR)


@merge_params()
def process(
    debug: int = 0,
    update: int = 0,
    pro_count: int = 1,
    operation: str = "i",
    begin_date: str = None,
    resolution: str = "5km",
    para_file: str = "Fast_refine_interp_5km.ini",
    work_dir: str = None,
    model_region: str = "EC_12P5KM",
    root_path: str = None,
    s3_method: str = "g_interp",
    site_name: str = "Station1",
    config=None,
    ini_path=None,
):
    """读入、插值、写出 NetCDF，并在需要时求最优 eta 后写成 h5。

    参数：
        debug：大于等于 1 时打印模式、时间和耗时。
        update：1 表示已有结果也重算，0 表示跳过已有文件。
        pro_count：并行进程数。1 为串行。大于 1 时写入时效池的进程数。
            时效工人绑定在 Class_Interp_dem 的进程初始化器上，不能再套 SimpleParallelTool。
        operation：i 插值，p 求参，ip 两者都做。
        begin_date：北京时业务时间 YYYYMMDDHH。空则用运行时刻。
        resolution：site、1km 或 5km。
        para_file：算法开关文件名，放在 work_dir 下。
        work_dir：参数文件所在目录。空则用本包 resource。
        model_region：模式区域，例如 EC_12P5KM。
        root_path：项目根。空则用本包目录。
        s3_method：结果目录中的方法名。
        site_name：站点文件名。
        config：本次使用的 ini，优先于 ini_path。
        ini_path：本次使用的 ini。
    """
    _ = config, ini_path
    count = 1 if pro_count is None else int(pro_count)
    if count < 1:
        raise ValueError("pro_count 至少为 1")
    name = (operation or "i").strip().lower()
    if name not in {"i", "p", "ip"}:
        raise ValueError("operation 只能是 i、p 或 ip")
    reso = (resolution or "5km").strip()
    if reso not in {"site", "1km", "5km"}:
        raise ValueError("resolution 只能是 site、1km 或 5km")
    if not root_path:
        root_path = str(_ROOT)
    if not work_dir:
        work_dir = str(_ROOT / "resource")

    # 第一步：读运行配置、模式、地形，以及站点或细网格目标点。
    case = {
        "debug": 0 if debug is None else int(debug),
        "update": 0 if update is None else int(update),
        "pro_count": count,
        "operation": name,
        "begin_date": begin_date or None,
        "resolution": reso,
        "para_file": para_file,
        "work_dir": work_dir,
        "model_region": model_region,
        "root_path": root_path,
        "s3_method": s3_method,
        "site_name": site_name,
    }
    case = read_environment(case)
    if count > 1:
        # 原插值池读取 FH_max_pcount、BT_max_pcount，这里只改进程数。
        case["dyPool"]["FH_parallel"] = True
        case["dyPool"]["FH_max_pcount"] = count
        case["dyPool"]["BT_parallel"] = True
        case["dyPool"]["BT_max_pcount"] = count
    case = select_forecast_hours(case)
    case = read_element_paths(case)
    case = check_output_files(case)
    case = read_model_terrain(case)
    case = read_interp_targets(case)

    # 第二步：空间三维插值。插件按预报时效计算，h5 仍在这一步写出。
    if "i" in name:
        case = SpatialInterpPlugin().process(case)
        # 第三步：正式格点产品写成 NetCDF。最高最低和时间插值仍用 h5。
        case = write_netcdf(case)
        if case["dyMaxMinInfo"]["Interp_Maxmin"]:
            case = MaxMinPlugin().process(case)
        if case["dyInstantInfo"]["Interp_Time"] and not case["lTI_update"]:
            case = TimeInterpPlugin().process(case)
    if case["args"].debug >= 1:
        case["cls_myfun"].dPrint_run_time()

    # 第四步：用实况求最优 eta。每个要素写成 {时效}_{要素}_eta.h5。
    if "p" in name:
        case = BestEtaPlugin().process(case)
        for eta_file in case.get("eta_products") or []:
            file_name = eta_file["hour"] + "_" + eta_file["element"] + "_eta.h5"
            daily_h5 = os.path.join(eta_file["daily_dir"], file_name)
            print("out:" + daily_h5)
            case["cls_itp3d"].dWS3_Interp(
                daily_h5,
                eta_file["data"],
                ltInterp_keys=eta_file["keys"],
                dyattr=eta_file["attrs"],
            )
            if eta_file.get("common_dir"):
                common_h5 = os.path.join(eta_file["common_dir"], file_name)
                if case["args"].debug >= 1:
                    print("out:" + common_h5)
                case["cls_itp3d"].dCopy_rlt(daily_h5, common_h5)
    if case["args"].debug >= 1:
        case["cls_myfun"].dPrint_run_time()
    return None
