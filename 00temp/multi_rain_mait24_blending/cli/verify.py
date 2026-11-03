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

_DEFAULT_H5 = Path(__file__).resolve().parent.parent / "resource" / "verify_data.h5"
_DEFAULT_GRADES = [0.1, 10, 25, 50, 100]
_DEFAULT_PRODUCTS = [
    "ec_dz", "ec", "aifs_dz", "aifs", "fengqing_dz", "fengqing", "mait", "mait_ai",
]

para_example= {
    "num_process": 4,
    "base_on": "foTime",  # 程序运行时段范围是基于起报时间还是预报时间(foTime 表示基于起报时间，obTime 表示基于实况时间)
    "begin_time":datetime(2025,7,1,0,0,0),
    #"end_time":datetime(2025,7,30,12,0,0),
    "end_time":datetime(2025,7,16,12,0,0),
    "time_type": "BT", # 程序运行时段是基于北京时还是世界时，BT表示北京时，UT表示世界时
    "how_fo":"outer", #不同模式数据的合并逻辑，outer 表示取不同模式的时间、时效并集， inner 表示取不同模式的时间时效交集
    # "station_file":r"/data/python_code/mait_24h/info/station_info.txt",
    "station_file":r"/mnt/Observation/r24/sfc/25070108.000",
    # "station_file":"",
    "defalut_value":0,
    "hdf_file_name":"verify_data.h5",
    "interp": meteva.base.interp_gs_nearest,
    "ob_data":{
        "dir_ob": r"/mnt/Observation/r24/sfc/YYMMDDHH.000",
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
            "dir_fo": r"/mnt/sm_qpf/v2021/rain24/ecmwf/sfc/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour":[0,12,12],
            "dtime":[36,252,24],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  #数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "ec": {
            "dir_fo": r"/mnt/nimm_data/model_RT/globalECMWF_C1D/APCP24/YYYY/YYYYMMDD/NC/YYYYMMDDHH.TTT.nc",
            "hour": [0, 12, 12],
            "dtime": [36, 252, 24],
            "read_method": meteva.base.io.read_griddata_from_nc,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "aifs_dz": {
            "dir_fo": r"/mnt/245sm_qpf/rain24_py/ecmwf_aifs/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour":[0,12,12],
            "dtime":[36,252,24],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",   #数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "aifs": {
            "dir_fo": r"/mnt/nimm_data/model_RT/globalECMWF_AIFS/APCP24/YYYY/YYYYMMDD/NC/YYYYMMDDHH.TTT.nc",
            "hour": [0, 12, 12],
            "dtime": [36, 252, 24],
            "read_method": meteva.base.io.read_griddata_from_nc,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "fengqing_dz": {
            "dir_fo": r"/mnt/245sm_qpf/rain24_py/fengqing/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour":[0,12,12],
            "dtime":[36,252,24],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "fengqing": {
            "dir_fo": r"/mnt/nimm_data/model_RT/FENGQING/APCP24/YYYY/YYYYMMDD/NC/YYYYMMDDHH.TTT.nc",
            "hour": [0, 12, 12],
            "dtime": [36, 252, 24],
            "read_method": meteva.base.io.read_griddata_from_nc,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "mait": {
            "dir_fo": r"/mnt/245sm_qpf/rain24_py/mait/YYYYMMDD/YYYYMMDDHH.TTT.m3",
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

        "mait_chen": {
            "dir_fo": r"/mnt/245sm_qpf/rain24_py/mait_chen/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour":[0,12,12],
            "dtime":[36,252,24],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT"
        },

        "mait_ai": {
            # "dir_fo": r"/mnt/245sm_qpf/rain24_py/mait_ai/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "dir_fo": r"/mnt/245sm_qpf/rain24_py/mait_chen_fq/YYYYMMDD/YYYYMMDDHH.TTT.m3",
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
    "output_dir":r"/data/python_code/mait_24h/verify_data"
}


def get_verify_result(sta_all):
    """
    计算并保存验证结果。

    参数
    ----------
    sta_all : pandas.DataFrame
        包含观测和预报数据的DataFrame

    返回值
    -------
    None
    """
    # 添加小时列用于筛选
    sta_all['hour'] = pd.to_datetime(sta_all['time']).dt.hour

    # 筛选8时和20时的数据
    sta_all_08 = sta_all[sta_all['hour'] == 8].copy()
    sta_all_20 = sta_all[sta_all['hour'] == 20].copy()

    # 重置索引
    sta_all_08 = sta_all_08.reset_index(drop=True)
    sta_all_20 = sta_all_20.reset_index(drop=True)

    # 删除临时小时列
    sta_all.drop(columns=['hour'], inplace=True)
    sta_all_08.drop(columns=['hour'], inplace=True)
    sta_all_20.drop(columns=['hour'], inplace=True)

    # 打印数据信息
    print(sta_all_08)
    print("=------------------------------------------------------------------------------->>>")
    print(sta_all_20)

    # 定义阈值列表
    grade_list = [0.1, 10, 25, 50, 100]

    # 定义预报时效列表
    dtimes = [36, 60, 84, 108, 132, 156, 180, 204, 228, 252]

    # 创建验证结果DataFrame
    verify_df_08 = pd.DataFrame({'dtime': dtimes})
    verify_df_20 = pd.DataFrame({'dtime': dtimes})

    # 定义预报产品名称列表
    pro_names = ['ec_dz', 'ec', 'aifs_dz', 'aifs', 'fengqing_dz', 'fengqing', 'mait', 'mait_chen', 'mait_ai']  # 后续添加新的产品名称只需修改这里

    # 遍历每个预报时效
    for idx, dtime in enumerate(dtimes):
        # 获取观测数据
        ob_sta_08 = sta_all_08[sta_all_08['dtime'] == dtime]['ob'].values
        ob_sta_20 = sta_all_20[sta_all_20['dtime'] == dtime]['ob'].values

        # 遍历每个预报产品
        for pro_name in pro_names:
            # 获取预报数据
            pro_sta_08 = sta_all_08[sta_all_08['dtime'] == dtime][pro_name].values
            pro_sta_20 = sta_all_20[sta_all_20['dtime'] == dtime][pro_name].values

            # 计算验证指标
            pro_hfmc_08 = mem.hfmc(ob_sta_08, pro_sta_08, grade_list=grade_list)
            pro_hfmc_20 = mem.hfmc(ob_sta_20, pro_sta_20, grade_list=grade_list)

            pro_ts_08 = mem.ts(ob_sta_08, pro_sta_08, grade_list=grade_list)
            pro_ts_20 = mem.ts(ob_sta_20, pro_sta_20, grade_list=grade_list)

            # 打印验证结果
            print("=--------------------------------------------------->>> ", dtime, pro_name)
            print(pro_hfmc_08)
            print(pro_hfmc_20)
            print(pro_ts_08)
            print(pro_ts_20)

            # 填充验证结果到DataFrame
            for grade_idx, grade in enumerate(grade_list):
                # 填充8时验证结果
                verify_df_08.loc[idx, f'{pro_name}_hit_{grade}'] = pro_hfmc_08[grade_idx][0]
                verify_df_08.loc[idx, f'{pro_name}_miss_{grade}'] = pro_hfmc_08[grade_idx][1]
                verify_df_08.loc[idx, f'{pro_name}_over_{grade}'] = pro_hfmc_08[grade_idx][2]
                verify_df_08.loc[idx, f'{pro_name}_ts_{grade}'] = pro_ts_08[grade_idx]

                # 填充20时验证结果
                verify_df_20.loc[idx, f'{pro_name}_hit_{grade}'] = pro_hfmc_20[grade_idx][0]
                verify_df_20.loc[idx, f'{pro_name}_miss_{grade}'] = pro_hfmc_20[grade_idx][1]
                verify_df_20.loc[idx, f'{pro_name}_over_{grade}'] = pro_hfmc_20[grade_idx][2]
                verify_df_20.loc[idx, f'{pro_name}_ts_{grade}'] = pro_ts_20[grade_idx]

                # 打印最终验证结果
    print(verify_df_08)
    print(verify_df_20)

    # 保存验证结果到CSV文件
    verify_df_08.to_csv('verify_results_08.csv')
    verify_df_20.to_csv('verify_results_20.csv')

    # 保存验证结果到HDF文件
    verify_df_08.to_hdf('verify_results.h5', key='res_08')
    verify_df_20.to_hdf('verify_results.h5', key='res_20')
    sta_all.to_hdf('verify_results.h5', key='sta_all')

    return


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


def get_dt_ts(ts, dt, grade_list):
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


def run_verify(
    *,
    h5_file: str = None,
    h5_key: str = "df",
    grade_list=None,
    product_list=None,
    plot: str = "bar",
    action: str = "ts",
    dtime: int = None,
):
    if h5_file is None:
        h5_file = str(_DEFAULT_H5)
    if grade_list is None:
        grade_list = list(_DEFAULT_GRADES)
    if product_list is None:
        product_list = list(_DEFAULT_PRODUCTS)

    action = action.strip().lower()
    if action == "ts":
        sta_all = pd.read_hdf(h5_file, key=h5_key)
        print(sta_all)
        get_ts(sta_all, grade_list, product_list, h5_file, plot=plot)
    elif action == "verify-result":
        sta_all = pd.read_hdf(h5_file, key=h5_key)
        get_verify_result(sta_all)
    elif action == "dt-ts":
        if dtime is None:
            raise ValueError("action=dt-ts 时必须指定 --dtime")
        ts_res = pd.read_hdf(h5_file, key="ts")
        get_dt_ts(ts_res, dtime, grade_list)
    else:
        raise ValueError(f"未知 action: {action}，可选 ts / verify-result / dt-ts")


def _cli_converters():
    from clize.parser import value_converter

    @value_converter
    def comma_str_list(s):
        if s is None or not str(s).strip():
            return None
        return [x.strip() for x in str(s).split(",") if x.strip()]

    @value_converter
    def comma_float_list(s):
        if s is None or not str(s).strip():
            return None
        return [float(x.strip()) for x in str(s).split(",") if x.strip()]

    @value_converter
    def optional_str(s):
        if s is None or not str(s).strip():
            return None
        return str(s)

    @value_converter
    def optional_int_cli(s):
        if s is None:
            return None
        t = str(s).strip()
        if not t:
            return None
        return int(t)

    return comma_str_list, comma_float_list, optional_str, optional_int_cli


def _make_cli_entry():
    from clize.runner import Clize

    comma_str_list, comma_float_list, optional_str, optional_int_cli = _cli_converters()

    def run_cli(
        *,
        h5_file: optional_str = None,
        h5_key: optional_str = "df",
        grade_list: comma_float_list = None,
        product_list: comma_str_list = None,
        plot: optional_str = "bar",
        action: optional_str = "ts",
        dtime: optional_int_cli = None,
    ):
        """
        24 小时预报检验（Clize 命令行）

        :param h5_file: 检验数据 HDF5；省略则用 resource/verify_data.h5
        :param h5_key: sta_all 在 HDF5 中的 key，默认 df
        :param grade_list: 降水阈值（mm），逗号分隔，如 0.1,10,25,50,100
        :param product_list: 产品名，逗号分隔
        :param plot: TS 图类型，默认 bar
        :param action: ts（默认）/ verify-result / dt-ts
        :param dtime: action=dt-ts 时的预报时效（小时）
        """
        run_verify(
            h5_file=h5_file,
            h5_key=h5_key or "df",
            grade_list=grade_list,
            product_list=product_list,
            plot=plot or "bar",
            action=action or "ts",
            dtime=dtime,
        )

    return Clize(run_cli)


def main():
    from clize.runner import run
    run(_make_cli_entry())


if __name__ == "__main__":
    main()
