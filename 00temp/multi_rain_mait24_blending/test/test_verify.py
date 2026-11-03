# -*- coding: utf-8 -*-
"""
24 小时预报检验（``cli/verify.py``）。

命令行
------
- 模块入口：``python -m cli verify --h5-file=...``
- 独立运行：``python cli/verify.py --h5-file=...``
"""
import sys
from pathlib import Path


def _bootstrap_paths():
    """项目根优先（加载本地 ``utils/__init__`` 合并 ``00temp/utils``），再 ``src``。"""
    _cli = Path(__file__).resolve().parent
    _root = _cli.parent
    _src = _root / "src"
    ordered = (str(_root), str(_src))
    for p in ordered:
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed(ordered):
        sys.path.insert(0, p)


_bootstrap_paths()

import meteva
import pandas as pd
import meteva_base as meb

import meteva.method as mem
import meteva.product as mpd

from datetime import datetime

from utils.data_prepare_plugin import prepare_dataset



para_example= {
    "num_process": 4,
    "base_on": "foTime",  # 程序运行时段范围是基于起报时间还是预报时间(foTime 表示基于起报时间，obTime 表示基于实况时间)
    "begin_time":datetime(2026, 8, 12, 00, 0, 0),
    #"end_time":datetime(2025,7,30,12,0,0),
    "end_time":datetime(2026, 8, 13, 12, 0, 0),
    "time_type": "UT", # 程序运行时段是基于北京时还是世界时，BT表示北京时，UT表示世界时
    "how_fo":"outer", #不同模式数据的合并逻辑，outer 表示取不同模式的时间、时效并集， inner 表示取不同模式的时间时效交集
    # "station_file":r"/data/python_code/mait_24h/info/station_info.txt",
    "station_file":r"/data/mnt/107_Observation/r24/sfc/25070108.000",
    # "station_file":"",
    "defalut_value":0,
    "hdf_file_name":"verify_data.h5",
    "interp": meteva.base.interp_gs_nearest,
    "ob_data":{
        "dir_ob": r"/data/mnt/107_Observation/r24/sfc/YYMMDDHH.000",
        "hour": [8, 20, 12],
        "read_method": meteva.base.io.read_stadata_from_micaps3,
        "read_para": {},
        "reasonable_value": [0, 1000],
        "operation":None,
        "operation_para": {},
        "time_type": "BT",   #数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
    },
    "fo_data":{
        "mait": {
            "dir_fo": r"/data/mnt/107_sm_qpf/v2021/rain24/mait/sfc/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour": [0, 12, 12],
            "dtime": [36, 252, 24],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "mait_24h": {
            "dir_fo": r"/data/code/nimm_pip_repos/multi_rain_mait24_blending/resource/data/output/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour": [0, 12, 12],
            "dtime": [36, 252, 24],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },
    },
    "output_dir":r"/data/code/nimm_pip_repos/multi_rain_mait24_blending/resource/data/output/verify_mait_24"
}

def get_ts(sta_all, grade_list, plot="bar", show=True):
    result = mpd.score(
        sta_all,
        mem.ts,
        grade_list=grade_list,
        g="dtime",
        gll=[36, 60, 84, 108, 132, 156, 180, 204, 228, 252],
        plot=plot,
        save_path=f"ts_{plot}_v1.png",
        show=show,
    )
    print(result)

    return


if __name__ == "__main__":
    # 组织获取检验数据
    sta_all = prepare_dataset(para_example)
    print(sta_all)
    h5_file = "mait_24_verify_new.h5"
    sta_all.to_hdf(h5_file, key="df")

    sta_all = sta_all[~(sta_all["ob"] >= 999)].copy()
    sta_all = sta_all.reset_index(drop=True)

    # sta_all = pd.read_hdf(h5_file, key="sta_all")
    # print(sta_all)
    # unique_values = sta_all['id'].unique()
    # print(len(unique_values), unique_values)

    # product_list = ["mait", "mait_24h"]
    grade_list = [0.1, 10, 25, 50, 100]
    get_ts(sta_all, grade_list)  # 保存ts评分结果