# -*- coding: utf-8 -*-
"""TCH 多模式集成 24 小时降水预报实时生成脚本（v1.0）。

脚本用途
    读取多家数值模式的 24 小时累积降水格点场，基于误差协方差的不确定性
    估计（cal_uct）计算各模式权重（get_weight_mul），加权合成 TCH 集成
    降水预报场与站点预报，并输出各模式分量场供检验平台使用。

输入数据
    - 模式降水格点文件：<DIR_MODEL_DATA>/<模式名>/sfc/<YYYYMMDD>/YYYYMMDDHH.<时效>.m4
    - 0.1° 全国掩膜文件：MASKOUT_FILE（-1 表示掩膜外，统计前需置零）
    - 国家站站点信息：meteva.base.station_国家站

主要流程
    1. 依据当前时间确定预报起始时次（北京时 08 时或 20 时）；
    2. 对每个预报时效（36/60/84 h）循环：
       a. 读取各模式降水并线性插值到统一网格；
       b. 掩膜处理后基于原始降水量计算各模式不确定性；
       c. 由不确定性计算集成权重，加权得到 TCH 集成场；
       d. 写出格点场（m4）与站点场（m3），北京时目录与检验平台 UTC
          目录各一套；
    3. 逐模式输出分量站点场（含以 50 mm 为基准的百分位归一化版本）。

依赖
    numpy、xarray、scipy、meteva；本脚本不再依赖 sympy、metpy、pandas、
    goto、cv2 等未使用的第三方包。

运行方式
    直接执行：python "pre_fcst_tch_realtime_v1.0 - 副本.py"
    脚本依赖 UNC 网络路径下的模式数据与本地掩膜文件，缺少外部数据时无法
    完整运行；仅做语法检查时使用 python -m py_compile。
"""

import datetime
import os

import numpy as np
import xarray as xr

import meteva.base as meb
from scipy import optimize

# ============================================================
# 配置常量（集中在此便于查看，取值与原脚本保持一致）
# ============================================================

# 0.1° 全国掩膜文件及其网格行列数
MASKOUT_FILE = "maskout_cn_0.1_2.dat"
NX_MASK = 701
NY_MASK = 601

# 模式降水输入目录与 TCH 输出目录（UNC 网络路径）
DIR_MODEL_DATA = r"D:/Work/NIMM_pip_testdata/multi_rain_mait24_blending/test_data"
DIR_TCH_OUTPUT = r"D:/Work/NIMM_pip_testdata/multi_rain_mait24_blending/test_data/tch/sfc_old/"
# 本地调试时可改为：DIR_TCH_OUTPUT = "./data/result/"

# 参与集成的模式成员，其顺序决定权重与输出分量的对应关系
MODEL_LIST = [
    "ecmwf", "german_gfs_hr", "ncep_gfs_hr", "grapes_3km",
    "beijing_mr", "guangzhou_mr", "shanghai_mr",
]

# 统一插值网格：[起始经度, 终止经度, 分辨率]、[起始纬度, 终止纬度, 分辨率]
GRID_LON = [70, 140.0, 0.10]
GRID_LAT = [0.0, 60.0, 0.10]

# 预报时效（小时）：36、60、84，均为 24 小时累积降水时效
FCST_HOURS = range(36, 87, 24)

# 站点数据层次
STATION_LEVEL = 600

# 北京时与 UTC 的时差（小时）
BJT_OFFSET_HOURS = 8

# 起始时次判定：当前北京时 >= 12 时取当日 00 时（北京时 08 时），
# 否则取前一日 12 时（北京时 20 时）
INITIAL_HOUR_THRESHOLD = 12
INITIAL_HOUR_LATE = 0
INITIAL_HOUR_EARLY = 12


def get_weight_mul(err_array):
    """按误差乘积归一化计算各模式集成权重（BTCH）。

    权重 w_i 正比于除第 i 个模式外其余模式误差的平方连乘，
    因此单个模式误差越小，其权重越大。

    参数
        err_array : ndarray, shape (n,)
            各模式的误差（不确定度）序列。
    返回
        w : ndarray, shape (n,)，归一化后的权重，总和为 1。
    """
    w = np.zeros(np.shape(err_array))
    n = len(err_array)

    # 先计算各模式的“其余模式误差平方连乘”，避免后面重复计算
    amul_list = []
    for i in range(n):
        amul = 1
        for j in range(n):
            if i != j:
                amul = amul * pow(err_array[j], 2)
        amul_list.append(amul)

    # 归一化因子，按原顺序累加以保证浮点结果一致
    accu = 0.0
    for amul in amul_list:
        accu = accu + amul

    for i in range(n):
        w[i] = amul_list[i] / accu

    return w

def cal_uct(arr):
    """基于误差协方差矩阵估计各模式（含参考场）的不确定性。

    参数
        arr : ndarray, shape (M, N)
            各模式预报场按列排列；最后一列（N-1）为参考场，其余为待评估场。
    返回
        uct   : ndarray，各列的绝对不确定度；
        r_uct : ndarray，各列的相对不确定度（%）。
    """

    def my_fun(r):
        """优化目标函数：误差协方差矩阵重构的残差平方和。"""
        f = 0
        for j in range(0, len(S)):
            f = f + np.power(r[j], 2)
            for k in range(0, len(S)):
                if j < k:
                    f = np.power((S[j, k] - r[len(S)] + r[j] + r[k]), 2) + f
        K = np.linalg.det(S)
        return f / np.power(K, 2 * len(S))

    M, N = np.shape(arr)

    ref_arr = arr[:, N - 1]  # 参考场
    tar_arr = arr[:, 0:N - 1]  # 其他场

    # 其他场减去参考场，得到误差矩阵
    Y = tar_arr - np.repeat(np.reshape(ref_arr, (M, 1)), N - 1, axis=1)

    S = np.cov(Y.T)  # 误差协方差矩阵 S
    print(S)  # 输出协方差矩阵，便于运行监控

    u = np.ones((1, N - 1))
    R = np.zeros((N, N))
    R[N - 1, N - 1] = 1 / (2 * np.dot(np.dot(u, np.linalg.inv(S)), u.T))

    x0 = R[:, N - 1]  # 优化初值

    # 约束条件：r[N-1] 与误差协方差的重构关系需满足非负约束
    u_ = np.ones((1, len(S)))
    det_S = np.linalg.det(S)
    inv_S = np.linalg.inv(S)
    denominator = np.power(det_S, 2 / len(S))

    cons = {
        'type': 'ineq',
        'fun': lambda r: (r[len(S)] - np.dot(
            np.dot(
                np.reshape(r[0:-1], (1, len(r) - 1)) - r[len(S)] * u_, inv_S),
            (np.reshape(r[0:-1],
                        (1, len(r) - 1)) - r[len(S)] * u_).T)) / denominator
    }

    x = optimize.minimize(my_fun,
                          x0,
                          method='COBYLA',
                          tol=2e-10,
                          constraints=cons)

    R[:, N - 1] = x.x

    # 由参考场与其他场的协方差关系回填协方差矩阵 R
    for ii in range(0, N - 1):
        for jj in range(0, N - 1):
            if ii < jj or ii == jj:
                R[ii, jj] = S[ii, jj] - R[N - 1,
                                          N - 1] + R[ii, N - 1] + R[jj, N - 1]
    R += R.T - np.diag(R.diagonal())
    for ii in range(0, N):
        for jj in range(0, N):
            R[jj, ii] = R[ii, jj]

    uct = np.sqrt(R.diagonal())  # 绝对不确定度
    r_uct = uct / np.mean(abs(arr), axis=0) * 100  # 相对不确定度（%）

    return uct, r_uct


def get_model_data(dir_model, model_list_source, initial_time, fcst_hr):
    """读取指定时效各模式降水格点场，插值到统一网格后按成员合并。

    某模式文件不存在时跳过该成员；返回按 member 维合并的 xarray 数据集。
    """
    grid2 = meb.grid(GRID_LON, GRID_LAT)

    time2 = initial_time
    trnow = datetime.datetime.strftime(time2, '%Y-%m-%d %H:%M:%S %p')
    date_str = trnow[0:4] + trnow[5:7] + trnow[8:10]

    model_array = []
    ii = 0

    for num in range(0, len(model_list_source)):
        # 只把文件名模板交给 get_path。整段路径传入时，目录名 NIMM 里的 MM 会被换成月份。
        folder = dir_model.rstrip("/\\") + "/" + model_list_source[num] + "/sfc/" + date_str + "/"
        fname = folder + meb.get_path("YYYYMMDDHH.TTT", time2, fcst_hr) + ".m4"
        print(fname)

        if os.path.exists(fname):
            print("当前模式资料存在：" + model_list_source[num])
            grd = meb.read_griddata_from_micaps4(fname)
            grd = meb.interp_gg_linear(grd, grid2)

            meb.set_griddata_coords(grd, member_list=[model_list_source[num]])

            if ii == 0:
                model_array = grd
            else:
                model_array = xr.concat([model_array, grd], dim='member')

            ii = ii + 1

    return model_array


def build_title(trnow, hour_str, dtime, model_name):
    """构造 Micaps 输出标题：YYYY年MM月DD日HH时{h}时效24小时降水预报场(名称)。"""
    return (trnow[0:4] + "年" + trnow[5:7] + "月" + trnow[8:10] + "日"
            + hour_str + "时" + str(dtime)
            + "h时效24小时降水预报场(" + model_name + ")")




# ============================================================
# 读取掩膜与站点信息
# ============================================================
maskout_data = np.fromfile(MASKOUT_FILE, 'f')
maskout_data = maskout_data.reshape((NY_MASK, NX_MASK), order='C')
maskout_series = np.array(maskout_data).reshape(NX_MASK * NY_MASK)

station_infor_N_resouce = meb.read_station(meb.station_国家站)
meb.set_stadata_coords(station_infor_N_resouce, level=STATION_LEVEL)


# ============================================================
# 确定预报起始时次（北京时 08 时或 20 时）
# ============================================================
time1 = datetime.datetime.now()

# 固定时次调试示例：
# time1 = datetime.datetime.strptime("20240604040000", "%Y%m%d%H%M%S")

if time1.hour >= INITIAL_HOUR_THRESHOLD:
    initial_hour = INITIAL_HOUR_LATE
else:
    initial_hour = INITIAL_HOUR_EARLY
    time1 = time1 - datetime.timedelta(hours=24)

# time_main = datetime.datetime(time1.year, time1.month, time1.day, initial_hour, 0)
time_main = datetime.datetime(2026, 5, 24, 0, 0)
print(time_main)

trnow = datetime.datetime.strftime(
    time_main + datetime.timedelta(hours=BJT_OFFSET_HOURS), '%Y-%m-%d %H:%M:%S %p')
trnow_utc = datetime.datetime.strftime(time_main, '%Y-%m-%d %H:%M:%S %p')

date_str = trnow[0:4] + trnow[5:7] + trnow[8:10]  # 年-月-日（北京时）
time_str = trnow[11:13]  # 北京时小时

print(trnow)
print(trnow_utc)
print(date_str)
print(time_str)


# ============================================================
# 逐时效生成 TCH 集成预报
# ============================================================
for fcst_num in FCST_HOURS:

    out_dir = DIR_TCH_OUTPUT + date_str
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # 北京时文件名主干：YYMMDDHH.<时效>
    file_tag = (trnow[2:4] + trnow[5:7] + trnow[8:10] + trnow[11:13]
                + "." + str(int(fcst_num)).zfill(3))
    # 检验平台文件名主干：YYYYMMDDHH.<时效>（UTC）
    utc_tag = date_str + trnow_utc[11:13] + "." + str(int(fcst_num)).zfill(3)

    fname_info = out_dir + "/" + file_tag + ".info"
    f_info = open(fname_info, 'w')

    print(fcst_num)

    # 读取参与集成的各模式降水场
    qpf_model = get_model_data(DIR_MODEL_DATA, MODEL_LIST, time_main, fcst_num)
    qpf_model_ev = qpf_model.copy()
    print(qpf_model)

    nx = qpf_model['lon'].shape[0]
    ny = qpf_model['lat'].shape[0]
    ndim = qpf_model['member'].shape[0]
    print(ndim)
    print(nx)
    print(ny)
    model_list_ev = qpf_model['member'].data

    # 转为 (格点数, 成员数) 的二维矩阵，直接使用原始降水量参与误差评估
    qpf_model_ev = np.array(qpf_model_ev[:, 0, 0,
                                       0, :, :]).reshape(ndim,
                                                         ny * nx).transpose()

    # 掩膜外（-1）格点的预报值置零
    maskout_series_ev = np.expand_dims(maskout_series,
                                       0).repeat(ndim, axis=0).transpose()

    print(qpf_model_ev.shape)
    print(maskout_series_ev.shape)

    qpf_model_ev[maskout_series_ev == -1] = 0

    # -------------------------------------------
    # 误差评估：各模式的不确定性
    # -------------------------------------------
    print("|--------------------|")
    print("|--TCH误差评估结果----|")
    print("|--------------------|")
    # test_c 为相对不确定度，当前流程暂未使用
    test_a, test_c = cal_uct(np.array(qpf_model_ev))
    print(test_a)

    # -------------------------------------------
    # 集成权重：由不确定性反算 BTCH 权重
    # -------------------------------------------
    print("|--------------------|")
    print("|--BTCH集成权重结果--|")
    print("|--------------------|")
    test_d = get_weight_mul(test_a)
    print(test_d)
    print(np.sum(test_d))
    print(type(test_d))

    f_info.writelines("模式成员评估结果为：\n")
    f_info.writelines(str(np.round(test_a, 4)) + "\n")
    f_info.writelines("模式成员及其权重系数为：\n")

    # -------------------------------------------
    # 加权合成 TCH 集成场
    # -------------------------------------------
    data_temp = []

    for rank_num in range(0, ndim):

        print(MODEL_LIST[rank_num] + ":   " + str(test_d[rank_num]))
        f_info.writelines(MODEL_LIST[rank_num] + ":  "
                          + str(np.around(test_d[rank_num], 4)) + "\n")

        if rank_num == 0:
            data_temp = np.array(qpf_model[rank_num, 0, 0,
                                           0, :, :]) * test_d[rank_num]
        else:
            data_temp = data_temp + np.array(qpf_model[rank_num, 0, 0,
                                           0, :, :]) * test_d[rank_num]

    data_temp = np.array(data_temp).reshape(1, 1, 1, ny, nx)

    qpf_combine = qpf_model.sel(member=model_list_ev[0]).copy()
    qpf_combine.data = data_temp

    qpf_combine = meb.xarray_to_griddata(qpf_combine)
    meb.set_griddata_coords(qpf_combine, member_list=['tch'])

    dtime = qpf_combine.dtime.data[0]

    # 北京时输出标题
    title_output = build_title(trnow, time_str, dtime, "TCH")

    # 集成场格点数据（文件名无扩展名，与原脚本一致）
    meb.write_griddata_to_micaps4(qpf_combine,
                                  out_dir + "/" + file_tag,
                                  creat_dir=True,
                                  effectiveNum=1,
                                  title=title_output,
                                  show=True)

    sta_combine = meb.interp_gs_linear(qpf_combine, station_infor_N_resouce)

    # 集成场站点数据
    meb.write_stadata_to_micaps3(sta_combine,
                                 out_dir + "/" + file_tag + ".m3",
                                 creat_dir=True,
                                 effectiveNum=1,
                                 title=title_output,
                                 show=True)

    # -------------------------------------------
    # 供检验平台使用的输出（目录与文件名均采用 UTC 时次）
    # -------------------------------------------
    title_output_utc = build_title(trnow, trnow_utc[11:13], dtime, "TCH")

    meb.write_griddata_to_micaps4(qpf_combine,
                                  out_dir + "/micaps/" + utc_tag + ".m4",
                                  creat_dir=True,
                                  effectiveNum=1,
                                  title=title_output_utc,
                                  show=True)

    meb.write_stadata_to_micaps3(sta_combine,
                                 out_dir + "/micaps/" + utc_tag + ".m3",
                                 creat_dir=True,
                                 effectiveNum=1,
                                 title=title_output_utc,
                                 show=True)

    f_info.close()

 
