import meteva
import pandas as pd
import meteva_base as meb

import meteva.method as mem
import meteva.product as mpd


from datetime import datetime

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

from utils.data_prepare_plugin import prepare_dataset

para_example= {
    "num_process": 4,
    "base_on": "foTime",  # 程序运行时段范围是基于起报时间还是预报时间(foTime 表示基于起报时间，obTime 表示基于实况时间)
    "begin_time":datetime(2026,8,21,0,0,0),
    "end_time":datetime(2026,8,22,12,0,0),
    "time_type": "UT", # 程序运行时段是基于北京时还是世界时，BT表示北京时，UT表示世界时
    "how_fo":"outer", #不同模式数据的合并逻辑，outer 表示取不同模式的时间、时效并集， inner 表示取不同模式的时间时效交集
    # "station_file":r"/data/python_code/mait_24h/info/station_info.txt",
    "station_file":r"/data/code/nimm_pip_repos/multi_optimize_tp_24h/resource/sta.m3",
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
        "ec_dz": {
            "dir_fo": r"/data/mnt/107_sm_model/rain24/ecmwf/YYYYMMDD/YYYYMMDDHH.TTT",
            "hour": [0, 12, 12],
            "dtime": [36, 252, 24],
            "read_method": meteva.base.io.read_griddata_from_micaps4,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  #数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "multi_optimize_tp_24h": {
            "dir_fo": r"/data/code/nimm_pip_repos/multi_optimize_tp_24h/resource/output/rain24/ecmwf/YYYYMMDDHH/YYYYMMDDHH.TTT.m3",
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
    "output_dir":r"/data/code/nimm_pip_repos/multi_optimize_tp_24h/resource/output/"
}


def get_ts(sta_all, grade_list, product_list, h5_file, plot="bar"):
    result = mpd.score(sta_all, mem.ts, grade_list=grade_list, g="dtime", plot=plot, save_path=f"ts_{plot}.png", show=True)
    res_array = result[0]
    dtimes = result[1]
    df_list = []

    for i, shixiao in enumerate(dtimes):
        for j, product in enumerate(product_list):
            row = [product] + res_array[i, j].tolist()
            df_list.append([shixiao] + row)

    columns = ["时效", "产品名称"] + grade_list

    df = pd.DataFrame(df_list, columns=columns)
    df.to_hdf(h5_file, key="ts", mode='a')
    print(df)

    return df


def get_dt_ts(ts, dt):
    df_36 = ts[ts["时效"] == dt]
    ts_values = df_36[grade_list].values
    product_names = df_36["产品名称"].tolist()
    print(ts_values)
    print(product_names)

    # 使用meteva的绘图函数
    name_list_dict2 = {"预报成员": product_names,
                       "分级(单位：mm)": grade_list}
    meb.bar(
        ts_values,
        name_list_dict=name_list_dict2,
        ylabel="TS评分",
        title=f"{dt}时效TS评分",
        save_path=f"ts_{dt}.png",
        grid=True,
        show=True
    )

    return


if __name__ == "__main__":
    h5_file = "/data/code/nimm_pip_repos/multi_optimize_tp_24h/resource/output/verify_data.h5"
    sta_all = prepare_dataset(para_example)
    print(sta_all)
    sta_all.to_hdf(h5_file, key="df")

    # sta_all = pd.read_hdf(h5_file, key="df")
    # print(sta_all)
    product_list = ["ec_dz", "multi_optimize_tp_24h"]
    grade_list = [0.1, 10, 25, 50, 100]
    result = mpd.score(sta_all, mem.ts, grade_list=grade_list, g="dtime", plot="bar", ncol=1, save_path=f"multi_optimize_tp_24h_ts_bar.png", show=True)




