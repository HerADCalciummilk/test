# -*- coding: utf-8 -*-
"""
检验数据准备与 TS 出图脚本（``src/utils/verify.py``）。

非主流水线：用 meteva 从实况/预报路径拼 HDF5，再画 TS 柱状图。
直接运行：``python -m utils.verify`` 或 ``python src/utils/verify.py``（需项目根在 path）。

业务数据路径说明（历史备注）
----------------------------
- 实况：CLDAS/CMPAS 逐1h 格点
- 对比产品：mait_st、CGAN、CMA3km、SH9KM 等（见下方 ``para_example``）
"""

import sys
from pathlib import Path


def _bootstrap_paths():
    """项目根优先（加载本地 ``utils/__init__`` 合并共享 ``utils``），再 ``src``。"""
    # verify.py → utils → src → 项目根
    _root = Path(__file__).resolve().parent.parent.parent
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
    "num_process": 8,
    "base_on": "foTime",  # 程序运行时段范围是基于起报时间还是预报时间(foTime 表示基于起报时间，obTime 表示基于实况时间)
    # "begin_time":datetime(2025,6,1,0,0,0),
    "begin_time":datetime(2026,8,20,0,0,0),
    "end_time":datetime(2026,8,21,12,0,0),
    # "end_time":datetime(2025,6,30,12,0,0),
    "time_type": "UT", # 程序运行时段是基于北京时还是世界时，BT表示北京时，UT表示世界时
    "how_fo":"outer", #不同模式数据的合并逻辑，outer 表示取不同模式的时间、时效并集， inner 表示取不同模式的时间时效交集
    # "station_file":r"/data/python_code/mait_24h/info/station_info.txt",
    "station_file":r"/data/mnt/107_Observation/R03_national/sfc/20260401/h03_202604010000.m3",
    # "station_file":"",
    "defalut_value":0,
    "hdf_file_name":"verify_data.h5",
    "interp": meteva.base.interp_gs_nearest,
    "ob_data":{
        "dir_ob": r"/data/mnt/107_Observation/R03_national/sfc/YYYYMMDD/h03_YYYYMMDDHH00.m3",
        "hour": [0, 23, 1],
        "read_method": meteva.base.io.read_stadata_from_micaps3,
        "read_para": {},
        "reasonable_value": [0, 1000],
        "operation":None,
        "operation_para": {},
        "time_type": "BT",   #数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
    },
    "fo_data":{
        "QPFFrequencyMatch_Rain03": {
            "dir_fo": r"/data/code/nimm_pip_repos/QPF_FrequencyMatch_Rain03/output/ecmwf/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour": [0, 12, 12],
            "dtime": [3, 144, 3],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  #数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },
        "frequency_matching_rain03": {
            "dir_fo": r"/data/code/nimm_pip_repos/frequency_matching_rain03/resource/data/output/ecmwf/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour": [0, 12, 12],
            "dtime": [3, 144, 3],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",   #数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },
    },
    "output_dir":r"/data/code/nimm_pip_repos/frequency_matching_rain03/resource/data/output/ecmwf"
}

if __name__ == "__main__":
    print("开始准备检验数据（先读实况，再逐产品读预报；缺文件会刷屏，不是卡死）", flush=True)
    sta_all = prepare_dataset(para_example)
    print("prepare_dataset 结束", flush=True)
    if sta_all is None or (hasattr(sta_all, "empty") and sta_all.empty):
        raise RuntimeError(
            "没有拼出检验样本。上面的 does not exist / there is not file data "
            "表示该 dir_fo 在 begin_time–end_time 内一个 .m3 都没读到。"
            "请先确认产品已写出，且路径、起报、时效与 para 一致。"
        )
    print(sta_all)
    sta_all.to_hdf("h5_file", key="df")
    sta_all = sta_all[~(sta_all["ob"] >= 999)].copy()
    sta_all = sta_all.reset_index(drop=True)
    grade_list = [0.1, 10, 25, 50]
    # 业务机无显示器时 show=True 会卡住
    result = mpd.score(
        sta_all, mem.ts, grade_list=grade_list, g="dtime",
        plot="bar", ncol=1, save_path="ts_bar.png", show=False)
    print("TS 图已写入 ts_bar.png", flush=True)

    # file = "/data/code/nimm_pip_repos/frequency_matching_rain03/resource/data/output/ecmwf/20260820/2026082000.003.m3"
    # sta = meteva.base.io.read_stadata_from_micaps3(file)
    # print(sta)
    #
    # file = "/data/code/nimm_pip_repos/QPF_FrequencyMatch_Rain03/output/ecmwf/20260820/2026082000.003.m3"
    # sta = meteva.base.io.read_stadata_from_micaps3(file)
    # print(sta)


