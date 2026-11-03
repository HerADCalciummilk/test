# -*- coding: utf-8 -*-
"""
MAIT 1 小时预报检验脚本。

命令行
------
- 模块入口：``python -m cli verify ts --h5-file=...``（项目根目录）
- 直接运行：``python -m cli.verify ts --h5-file=...``
"""
import importlib.util
import sys
from pathlib import Path


def _bootstrap_paths():
    """项目根优先（加载本地 ``utils/__init__`` 合并 ``00temp/utils``），再 ``src``。"""
    _root = Path(__file__).resolve().parent.parent
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

para_example = {
    "num_process": 6,
    "base_on": "foTime",  # 程序运行时段范围是基于起报时间还是预报时间(foTime 表示基于起报时间，obTime 表示基于实况时间)
    "begin_time": datetime(2026, 4, 15, 8, 0, 0),
    "end_time": datetime(2026, 4, 20, 20, 0, 0),
    "time_type": "BT",  # 程序运行时段是基于北京时还是世界时，BT表示北京时，UT表示世界时
    "how_fo": "outer",  # 不同模式数据的合并逻辑，outer 表示取不同模式的时间、时效并集， inner 表示取不同模式的时间时效交集
    # "station_file":r"/data/python_code/mait_24h/info/station_info.txt",
    "station_file": r"/data/mnt/107_Observation/R01_national/sfc/20260401/h01_202604010000.m3",
    # "station_file":"",
    "defalut_value": 0,
    "hdf_file_name": "mait_1_verify_data.h5",
    "interp": meteva.base.interp_gs_nearest,
    "ob_data": {
        "dir_ob": r"/data/mnt/107_Observation/R01_national/sfc/YYYYMMDD/h01_YYYYMMDDHH00.m3",
        "hour": [0, 23, 1],
        "read_method": meteva.base.io.read_stadata_from_micaps3,
        "read_para": {},
        "reasonable_value": [0, 1000],
        "operation": None,
        "operation_para": {},
        "time_type": "BT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
    },
    "fo_data": {
        "mait_st": {
            "dir_fo": r"/data100/st_qpf/rain01/mait_st/sfc/YYYY/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour": [0, 23, 1],
            "dtime": [0, 36, 1],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT",
        },
        "mait_01": {
            "dir_fo": r"/data/code/nimm_pip_repos/multi_rain_mait01_blending/resource/data/output/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "hour": [0, 23, 1],
            "dtime": [0, 36, 1],
            "read_method": meteva.base.io.read_stadata_from_micaps3,
            "read_para": {},
            "reasonable_value": [0, 1000],
            "operation": None,
            "operation_para": {},
            "time_type": "UT",  # 数据文件是以北京时还是世界时命名，BT表示北京时，UT表示世界时
            "move_fo_time": 0,
            "file_time_type": "UT",
        },
    },
    "output_dir": r"/data/code/nimm_pip_repos/multi_rain_mait01_blending/resource/data/output/verify_mait_1",
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
    sta_all["hour"] = pd.to_datetime(sta_all["time"]).dt.hour

    # 筛选8时和20时的数据
    sta_all_08 = sta_all[sta_all["hour"] == 8].copy()
    sta_all_20 = sta_all[sta_all["hour"] == 20].copy()

    # 重置索引
    sta_all_08 = sta_all_08.reset_index(drop=True)
    sta_all_20 = sta_all_20.reset_index(drop=True)

    # 删除临时小时列
    sta_all.drop(columns=["hour"], inplace=True)
    sta_all_08.drop(columns=["hour"], inplace=True)
    sta_all_20.drop(columns=["hour"], inplace=True)

    # 打印数据信息
    print(sta_all_08)
    print("=------------------------------------------------------------------------------->>>")
    print(sta_all_20)

    # 定义阈值列表
    grade_list = [0.1, 10, 25, 50, 100]

    # 定义预报时效列表
    dtimes = [n for n in range(1, 37, 1)]

    # 创建验证结果DataFrame
    verify_df_08 = pd.DataFrame({"dtime": dtimes})
    verify_df_20 = pd.DataFrame({"dtime": dtimes})

    # 定义预报产品名称列表
    pro_names = ["mait_st", "mait_chen"]  # 后续添加新的产品名称只需修改这里

    # 遍历每个预报时效
    for idx, dtime in enumerate(dtimes):
        # 获取观测数据
        ob_sta_08 = sta_all_08[sta_all_08["dtime"] == dtime]["ob"].values
        ob_sta_20 = sta_all_20[sta_all_20["dtime"] == dtime]["ob"].values

        # 遍历每个预报产品
        for pro_name in pro_names:
            # 获取预报数据
            pro_sta_08 = sta_all_08[sta_all_08["dtime"] == dtime][pro_name].values
            pro_sta_20 = sta_all_20[sta_all_20["dtime"] == dtime][pro_name].values

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
                verify_df_08.loc[idx, f"{pro_name}_hit_{grade}"] = pro_hfmc_08[grade_idx][0]
                verify_df_08.loc[idx, f"{pro_name}_miss_{grade}"] = pro_hfmc_08[grade_idx][1]
                verify_df_08.loc[idx, f"{pro_name}_over_{grade}"] = pro_hfmc_08[grade_idx][2]
                verify_df_08.loc[idx, f"{pro_name}_ts_{grade}"] = pro_ts_08[grade_idx]

                # 填充20时验证结果
                verify_df_20.loc[idx, f"{pro_name}_hit_{grade}"] = pro_hfmc_20[grade_idx][0]
                verify_df_20.loc[idx, f"{pro_name}_miss_{grade}"] = pro_hfmc_20[grade_idx][1]
                verify_df_20.loc[idx, f"{pro_name}_over_{grade}"] = pro_hfmc_20[grade_idx][2]
                verify_df_20.loc[idx, f"{pro_name}_ts_{grade}"] = pro_ts_20[grade_idx]

                # 打印最终验证结果
    print(verify_df_08)
    print(verify_df_20)

    # 保存验证结果到CSV文件
    verify_df_08.to_csv("verify_results_08.csv")
    verify_df_20.to_csv("verify_results_20.csv")

    # 保存验证结果到HDF文件
    verify_df_08.to_hdf("verify_results.h5", key="res_08")
    verify_df_20.to_hdf("verify_results.h5", key="res_20")
    sta_all.to_hdf("verify_results.h5", key="sta_all")

    return


def get_ts(sta_all, grade_list, product_list, h5_file, plot="bar", show=True):
    result = mpd.score(
        sta_all,
        mem.ts,
        grade_list=grade_list,
        g="dtime",
        plot=plot,
        save_path=f"ts_{plot}.png",
        show=show,
    )
    res_array = result[0]
    dtimes = result[1]
    df_list = []

    for i, shixiao in enumerate(dtimes):
        for j, product in enumerate(product_list):
            row = [product] + res_array[i, j].tolist()
            df_list.append([shixiao] + row)

    columns = ["时效", "产品名称"] + grade_list

    df = pd.DataFrame(df_list, columns=columns)
    df.to_hdf(h5_file, key="ts", mode="a")
    print(df)

    return df


def get_dt_ts(ts, dt, grade_list):
    df_36 = ts[ts["时效"] == dt]
    ts_values = df_36[grade_list].values
    product_names = df_36["产品名称"].tolist()
    print(ts_values)
    print(product_names)

    # 使用meteva的绘图函数
    name_list_dict2 = {"预报成员": product_names, "分级(单位：mm)": grade_list}
    meb.bar(
        ts_values,
        name_list_dict=name_list_dict2,
        ylabel="TS评分",
        title=f"{dt}时效TS评分",
        save_path=f"ts_{dt}.png",
        grid=True,
        show=True,
    )

    return


def _load_sta_all(h5_file, key="sta_all", rename=None):
    sta_all = pd.read_hdf(h5_file, key=key)
    if rename:
        for pair in rename.split(","):
            old_name, new_name = [x.strip() for x in pair.split("=", 1)]
            sta_all.rename(columns={old_name: new_name}, inplace=True)
    return sta_all


def process_prepare(*, para_file, recover=True):
    """从配置脚本读取 ``para`` 并调用 ``prepare_dataset`` 生成检验数据集。"""
    from utils.data_prepare_plugin import prepare_dataset

    spec = importlib.util.spec_from_file_location("verify_para", para_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    para = getattr(mod, "para", None) or getattr(mod, "para_example", None)
    if para is None:
        raise ValueError(f"{para_file} 中需定义 para 或 para_example")
    sta_all = prepare_dataset(para, recover=recover)
    print(sta_all)
    return sta_all


def process_result(*, h5_file, key="sta_all", rename=None):
    """从 HDF 读取站点数据并计算 HFMC/TS 表格。"""
    sta_all = _load_sta_all(h5_file, key=key, rename=rename)
    get_verify_result(sta_all)


def process_ts(
    *,
    h5_file,
    grade_list,
    product_list,
    key="sta_all",
    rename=None,
    plot="bar",
    show=True,
):
    """计算 TS 评分、绘图并写入 HDF。"""
    sta_all = _load_sta_all(h5_file, key=key, rename=rename)
    print(sta_all)
    return get_ts(sta_all, grade_list, product_list, h5_file, plot=plot, show=show)


def process_plot_dt(*, h5_file, dtime, grade_list, rename=None):
    """从 HDF 读取 TS 结果并绘制指定时效柱状图。"""
    ts_res = pd.read_hdf(h5_file, key="ts")
    if rename:
        for pair in rename.split(","):
            old_name, new_name = [x.strip() for x in pair.split("=", 1)]
            ts_res["产品名称"] = ts_res["产品名称"].replace(old_name, new_name)
    get_dt_ts(ts_res, dtime, grade_list)


# ---------------------------------------------------------------------------
# 命令行（Clize）
# ---------------------------------------------------------------------------

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
    def optional_bool_cli(s):
        if s is None:
            return None
        if isinstance(s, bool):
            return s
        t = str(s).strip().lower()
        if t in ("", "none"):
            return None
        if t in ("1", "true", "yes", "y", "on"):
            return True
        if t in ("0", "false", "no", "n", "off"):
            return False
        raise ValueError("期望布尔：true/false/1/0 等")

    return comma_str_list, comma_float_list, optional_str, optional_bool_cli


def _make_cli_commands():
    from clize.runner import Clize

    comma_str_list, comma_float_list, optional_str, optional_bool_cli = _cli_converters()

    def prepare(*, para_file: str, recover: optional_bool_cli = True):
        """
        组织检验数据（调用 prepare_dataset）

        :param para_file: 含 ``para`` 或 ``para_example`` 的 Python 配置文件
        :param recover: 是否增量恢复已有 HDF
        """
        process_prepare(para_file=para_file, recover=recover)

    def result(*, h5_file: str, key: optional_str = "sta_all", rename: optional_str = None):
        """
        计算 HFMC/TS 表格并写出 CSV/HDF

        :param h5_file: 含 ``sta_all`` 的 HDF 路径
        :param key: HDF key，默认 ``sta_all``
        :param rename: 列重命名，如 ``mait_chen=mait_1h``
        """
        process_result(h5_file=h5_file, key=key, rename=rename)

    def ts(
        *,
        h5_file: str,
        grade_list: comma_float_list,
        product_list: comma_str_list,
        key: optional_str = "sta_all",
        rename: optional_str = None,
        plot: optional_str = "bar",
        show: optional_bool_cli = True,
    ):
        """
        计算 TS 评分并绘图

        :param h5_file: 含 ``sta_all`` 的 HDF 路径
        :param grade_list: 降水阈值，逗号分隔，如 ``0.1,1,10,20``
        :param product_list: 预报产品列名，逗号分隔
        :param rename: 列重命名，如 ``mait_chen=mait_1h``
        """
        process_ts(
            h5_file=h5_file,
            grade_list=grade_list,
            product_list=product_list,
            key=key,
            rename=rename,
            plot=plot,
            show=show,
        )

    def plot_dt(
        *,
        h5_file: str,
        dtime: int,
        grade_list: comma_float_list,
        rename: optional_str = None,
    ):
        """
        绘制指定时效 TS 柱状图

        :param h5_file: 含 ``ts`` key 的 HDF 路径
        :param dtime: 预报时效（小时）
        :param grade_list: 降水阈值，逗号分隔
        """
        process_plot_dt(h5_file=h5_file, dtime=dtime, grade_list=grade_list, rename=rename)

    return [Clize(prepare), Clize(result), Clize(ts), Clize(plot_dt)]


def main():
    """
    Clize 命令行入口。
    python -m cli.verify ts prepare   # 第一步：生成检验数据集h5
    python -m cli.verify ts result   # 第二步：读取h5，手动计算hfmc、ts输出csv/h5
    python -m cli.verify ts ts       # 第三步：meteva.score批量算TS，绘图存入h5
    python -m cli.verify ts plot_dt  # 第四步：读取已经算好的ts结果，画单时效柱状图
    """
    from clize.runner import SubcommandDispatcher, run

    run(SubcommandDispatcher(commands=_make_cli_commands()))


if __name__ == "__main__":
    main()
