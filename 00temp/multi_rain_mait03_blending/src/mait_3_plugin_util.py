# -*- coding: UTF-8 -*-
"""
MAIT 3h 读数、时间、beta 与 Micaps 写出。

- ``_prepare`` / ``_analysis_para_ini`` / ``_analysis_background_ini``：日志、站点表、模式/背景路径 ini
- ``_analysis_time1/2/3``：起报 UTC、实况时刻（可选 +8 h）、历史场时刻
- ``_read_history_source_micaps3`` / ``_read_now_source_micaps3_micaps4``：历史/当前/实况/背景
- ``read_his_beta`` / ``write_beta``：分区权重文件
- ``_data_write_to_micaps3`` / ``write_grid_to_micaps4``：站点与格点产品
"""
# @Software : python
import datetime
import numpy as np
import meteva_base as meb
import os
from utils.util_new import copy_data, data0_str, read_float_val_from_bin, get_log, GridData


def _emit_miss(kind, path, extra=""):
    """缺失/损坏路径打到终端（flush，避免重定向时看不到）。"""
    line = f"[MISS] {kind}: {path}"
    if extra:
        line += f"  ({extra})"
    print(line, flush=True)


def _normalize_time_input(time_input):
    """规范化用户时刻：10 位补 ``00``，返回 ``YYYYMMDDHHMM`` 或 ``None``。"""
    if time_input is None:
        return None
    s = str(time_input).strip()
    if not s:
        return None
    if len(s) == 10:
        s = s + "00"
    return s


def _user_time_to_job_time(time_input):
    """把用户给的 UTC 起报转成 ``_analysis_time1`` 能折回同一起报的作业时刻。

    用户写什么起报，产品就出什么起报：

    - ``YYYYMMDD0000`` → 当日 ``2000`` → 折回当日 00 UTC
    - ``YYYYMMDD1200`` → 次日 ``0800`` → 折回当日 12 UTC
    - 其它（如业务 ``0800`` / ``2000``）原样交给 ``_analysis_time1``
    """
    s = _normalize_time_input(time_input)
    if s is None:
        return None
    dt = datetime.datetime.strptime(s, "%Y%m%d%H%M")
    if dt.hour == 0 and dt.minute == 0:
        return dt.strftime("%Y%m%d") + "2000"
    if dt.hour == 12 and dt.minute == 0:
        return (dt + datetime.timedelta(days=1)).strftime("%Y%m%d") + "0800"
    return s


def _prepare(time_input, log_file, sd_sta_info_file):
    """初始化日志、解析起报时刻、读站点表（值置 0）。

    返回 ``(simple_log, dt_now, sd_sta_info)``。
    """
    # 介绍性开头
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++\n")
    print("+++   Adaptive Integration Rain Forecast V2.0      +++\n")
    print("+++   Create By CaoYong 2023.06.14                 +++\n")
    print("+++   Email: nmc_cy@126.com                        +++\n")
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++\n")
    log_path = meb.get_path(log_file, datetime.datetime.now(), 000)
    if not os.path.exists(os.path.dirname(log_path)):
        os.makedirs(os.path.dirname(log_path))
    simple_log = get_log(log_path)
    simple_log.info('=========' + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + '=================')

    user_time = _normalize_time_input(time_input)
    job_time = _user_time_to_job_time(time_input)
    if job_time is None:
        dt_now = datetime.datetime.now()
        job_time = dt_now.strftime("%Y%m%d%H%M")
        user_time = user_time or job_time
    else:
        dt_now = datetime.datetime.strptime(job_time, "%Y%m%d%H%M")
    md_yr, md_mo, md_dy, md_hr = _analysis_time1(dt_now)
    print(
        f"[TIME] input={user_time} → job={job_time} → "
        f"init={md_yr:04d}{md_mo:02d}{md_dy:02d}{md_hr:02d} UTC",
        flush=True,
    )
    print(f"[PATH] station: {sd_sta_info_file}", flush=True)
    if not os.path.exists(sd_sta_info_file):
        _emit_miss("station", sd_sta_info_file, "not exist")
    sd_sta_info = meb.read_stadata_from_micaps3(sd_sta_info_file)
    sd_sta_info.iloc[:, -1] = 0.0

    return simple_log, dt_now, sd_sta_info


def _analysis_background_ini(para_filepath):
    """解析 ``para_3_background.ini``：``模式键名=MICAPS4 路径模板``，与 ``para_3.ini`` 键名一致。

    无 ``modelNum`` 头；空行与 ``#`` 行忽略。占位符走 ``meb.get_path``（``YYYYMMDD`` / ``TTT``）。
    文件不存在或读失败时返回空字典，调用方回退为同模式 Micaps3 改 ``.m4``。
    """
    out = {}
    if not para_filepath or not os.path.exists(para_filepath):
        return out
    try:
        with open(para_filepath, "r", encoding="GBK") as sr:
            for line in sr:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip()
                if key:
                    out[key] = val
    except Exception:
        return {}
    return out


def _analysis_para_ini(para_filepath, simple_log):
    """解析 ``para_3*.ini``：``modelNum``、各模式路径、``fact``、``staoutputPath``。

    文件不存在或格式错误时写日志并返回 ``None``。
    """
    print(f"[PATH] para: {para_filepath}", flush=True)
    if not os.path.exists(para_filepath):
        _emit_miss("para", para_filepath, "not exist")
        simple_log.error("Para File Is Not Exist!")
        return
    else:
        # # 加载路径配置文件
        with open(para_filepath, 'r', encoding='GBK') as para_sr:
            try:
                str_tmp = para_sr.readline()
                str_array_tmp = str_tmp.split("=")
                model_num = int(str_array_tmp[1])
                model_name = list()
                model_path = list()
                for n in range(model_num):
                    str_tmp = para_sr.readline()
                    str_array_tmp = str_tmp.split("=")
                    model_name.append(str_array_tmp[0].strip())
                    model_path.append(str_array_tmp[1].strip())
                str_tmp = para_sr.readline()
                str_array_tmp = str_tmp.split("=")
                fact_path = str_array_tmp[1].strip()
                str_tmp = para_sr.readline()
                str_array_tmp = str_tmp.split("=")
                output_sample_path = str_array_tmp[1].strip()
                return model_num, model_name, model_path, fact_path, output_sample_path

            except Exception as ex:
                simple_log.error(str(ex))
                simple_log.error("Para Content Is Not Right!")
                return


def _analysis_time1(dt_now):
    """由起报时刻落到 00/12 UTC：13–23 时用当日 00 UTC，否则用昨日 12 UTC。"""
    # 获取模式数据时间
    if dt_now.hour > 12 and dt_now.hour <= 23:
        md_current_yr = dt_now.year
        md_current_mo = dt_now.month
        md_current_dy = dt_now.day
        md_current_hr_utc = 0

    else:
        dt_before = dt_now - datetime.timedelta(days=1)
        md_current_yr = dt_before.year
        md_current_mo = dt_before.month
        md_current_dy = dt_before.day
        md_current_hr_utc = 12

    return md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc


def _analysis_time2(md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc, predict_valid, is_obs_bjt):
    """当前起报 + 时效 → 有效时刻；实况取前一日同时次，可选 +8 h（北京时）。"""
    dt_model_current = datetime.datetime(
        md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc, 0,
        0)
    dt_valid = dt_model_current + datetime.timedelta(hours=predict_valid)

    dt_fact = dt_model_current + datetime.timedelta(days=-1)
    dt_fact = datetime.datetime(dt_fact.year, dt_fact.month, dt_fact.day, dt_valid.hour, 0, 0)
    # 将24小时预报转换为北京时间
    if is_obs_bjt == True:  # 根据世界时或北京时读取对应实况数据
        obs_delta_hours = 8
    else:
        obs_delta_hours = 0
    dt_fact = dt_fact + datetime.timedelta(hours=obs_delta_hours)

    return dt_fact, dt_valid, dt_model_current


def _analysis_time3(md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc, predict_valid):
    """当前起报与「实况时刻回推时效」得到的历史起报，用于读历史模式场。"""
    dt_model_current = datetime.datetime(
        md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc, 0, 0)
    dt_valid = dt_model_current + datetime.timedelta(hours=predict_valid)
    dt_fact = dt_model_current - datetime.timedelta(days=1)
    dt_fact = datetime.datetime(dt_fact.year, dt_fact.month, dt_fact.day, dt_valid.hour, 0, 0)
    dt_model_before = dt_fact - datetime.timedelta(hours=predict_valid)
    return dt_model_current, dt_model_before


def write_beta(obeta_file_path, model_num, model_name, score_last):
    """把当期 ``score_last`` 写成 ``模式名=评分`` 行，供下一时次作 ``s_before``。"""
    os.makedirs(os.path.dirname(obeta_file_path), exist_ok=True)
    with open(obeta_file_path, 'w+') as obeta_sr:
        for n in range(model_num):
            obeta_sr.write(model_name[n] + "=" + str(score_last[n]) + "\n")
    return None


def _data_write_to_micaps3(predict_type, output_sample_path, sd_output, grid_base):
    """融合站点场写 Micaps3（路径模板中 ``VVV`` 换 ``TTT`` 后按起报/时效展开）。"""
    # 输出站点EC订正预报结果
    print("Ouput The Correct StaData...\n")
    sta_header = meb.get_path(
        f"diamond 3 YYYY年MM月DD日HH时VVV时效{predict_type:03d}小时累积降水 00 01 04 08  -1 0 1 0 0".replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    output_sta_path = meb.get_path(
        output_sample_path.replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    sd_output[data0_str] = sd_output[data0_str] * 1.0
    os.makedirs(os.path.dirname(output_sta_path), exist_ok=True)
    meb.set_stadata_coords(sd_output,
                           time=grid_base.gtime[0], dtime=grid_base.dtimes[0])
    meb.write_stadata_to_micaps3(sd_output, save_path=output_sta_path + '.m3',
                                 effectiveNum=2)

    return output_sta_path + '.m3'


def read_grid_mask(mask_file, grid_base):
    """读陆地掩膜：区内约 1、区外约 -1，供境外抽背景伪站。"""
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    d_lon = grid_base.dlon
    d_lat = grid_base.dlat

    # 中国范围里面是1，外面是-1
    gd_mask_val, gd_mask_xn, gd_mask_yn = read_float_val_from_bin(mask_file, lon_start, lon_end,
                                                                  lat_start, lat_end, d_lon,
                                                                  d_lat)
    return gd_mask_val, gd_mask_xn, gd_mask_yn


def write_grid_to_micaps4(gd_final_output, output_sample_path, predict_type, clip_coords, grid_base,is_interp):
    """订正格点写 Micaps4 与 NC；``is_interp`` 时先按 ``clip_coords`` 双线性裁剪。"""
    grid_no_interp = meb.grid_data(grid_base, gd_final_output.data.T)
    grid = grid_no_interp
    # 插值
    if is_interp == True:
        if clip_coords:
            if len(clip_coords) == 6:
                lon_start_clip = clip_coords[0]
                lon_end_clip = clip_coords[1]
                lat_start_clip = clip_coords[2]
                lat_end_clip = clip_coords[3]
                dlon_clip = clip_coords[4]
                dlat_clip = clip_coords[5]
                grid_clip = meb.grid([lon_start_clip, lon_end_clip, dlon_clip], [lat_start_clip, lat_end_clip, dlat_clip])
                grid = meb.interp_gg_linear(grid_no_interp, grid_clip)
    output_grid_path = meb.get_path(
        output_sample_path.replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    os.makedirs(os.path.dirname(output_grid_path), exist_ok=True)

    micaps4_file2 = output_grid_path + ".m4"
    grid_header2 = meb.get_path(
        f"YYYYMMDDHH_VVV时效{predict_type:03d}小时降水预报场".replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    meb.write_griddata_to_micaps4(grid, micaps4_file2, creat_dir=True, effectiveNum=2, title=grid_header2, inte=5,
                                  vmin=0, vmax=200)
    meb.write_griddata_to_nc(grid, output_grid_path + ".nc", creat_dir=True, effectiveNum=2)
    return None

def get_now_beta_file_path(beta_path, grid_base):
    """
            获取当前的beta文件路径
            :param beta_path: beta文件路径，默认为None
            :param app_dir: 程序目录
            :param grid_base: 格点数据实况坐标，时间时效等
            :return: list，[[[beta_file]]]
            """
    dto_beta = grid_base.gtime[0]  # 输出参数文件日期
    predict_valid = grid_base.dtimes[0]

    obeta_file_path_list = []
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    lon_interval = [lon_end - lon_start]
    lat_interval = [lat_end - lat_start]
    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_obeta_file_path_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()

        for j in range(yyn):
            print("J Line Index: ", str(j + 1), '\n')
            for i in range(xxn):
                obeta_file_path = meb.get_path(
                    beta_path%(i,j),
                    dto_beta,
                    predict_valid)  # 生成当前参数文件路径
                ii_obeta_file_path_list[j][i] = obeta_file_path
        obeta_file_path_list.append(ii_obeta_file_path_list)

    return obeta_file_path_list

def get_his_beta_file_path(beta_path, grid_base):
    """
            获取历史的beta文件路径
            :param app_dir: 程序目录
            :param grid_base: 格点数据实况坐标，时间时效等
            :return: beta文件列表和文件是否存在的标识list，list    文件存在[[[beta_file]]],[[[1]]]，文件不存在文件存在[[['0']]],[[[0]]]
            """
    dto_beta = grid_base.gtime[0]  # 输出参数文件日期
    predict_valid = grid_base.dtimes[0]

    ibeta_file_path_list = []
    iflag_list = []
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    lon_interval = [lon_end - lon_start]
    lat_interval = [lat_end - lat_start]

    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_ibeta_file_path_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()
        ii_iflag_list = np.full(shape=(yyn, xxn), fill_value=0, dtype=int).tolist()

        for j in range(yyn):
            print("J Line Index: ", str(j + 1), '\n')
            for i in range(xxn):

                for n in range(1, 10):
                    dti_beta = dto_beta - datetime.timedelta(days=n)  # 计算输入参数文件的日期
                    ibeta_file_path = meb.get_path(
                        beta_path%(i,j),
                        dti_beta,
                        predict_valid)  # 生成当前参数文件路径
                    if os.path.exists(ibeta_file_path):
                        ii_ibeta_file_path_list[j][i] = ibeta_file_path
                        ii_iflag_list[j][i] = 1
                        # iflag = 1
                        break
        ibeta_file_path_list.append(ii_ibeta_file_path_list)
        iflag_list.append(ii_iflag_list)
    return ibeta_file_path_list, iflag_list

def read_his_beta(ibeta_file_path_list, iflag_list, model_num, model_name, grid_base):
    """
    读取历史的beta文件
    :param ibeta_file_path_list: 历史beta文件list
    :param iflag_list: 历史beta文件是否存在的标识的list
    :param model_num: 模式个数
    :param model_name: 模式名称list
    :param grid_base: 格点数据实况坐标，时间时效等
    :return: 历史评分，beta文件是否存在的标识，list，list
    """
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    lon_interval = [lon_end - lon_start]
    lat_interval = [lat_end - lat_start]
    score_before_list = []
    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_score_before_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()

        for j in range(yyn):
            print("J Line Index: ", str(j + 1), '\n')
            for i in range(xxn):
                score_before = [0.0] * model_num  # 得分 score-before，之前得分

                ibeta_file_path = ibeta_file_path_list[i_num][j][i]
                iflag = iflag_list[i_num][j][i]
                if iflag == 1:
                    # 读取
                    with open(ibeta_file_path, 'r') as beta_sr:
                        while True:
                            str_tmp = beta_sr.readline()
                            if str_tmp:
                                str_tmp_array = str_tmp.split('=')
                                for n in range(model_num):  # 不存在的前期的模式信息就为0.0
                                    if str_tmp_array[0].strip() == model_name[n]:
                                        score_before[n] = float(str_tmp_array[1].strip())
                            else:
                                break
                ii_score_before_list[j][i] = score_before
        score_before_list.append(ii_score_before_list)

    return score_before_list, iflag_list


def _read_history_source_micaps3(predict_valid, dt_now, model_num, sd_sta_info, fact_path, simple_log,
                                 model_path,is_obs_bjt):
    """读实况与历史模式 Micaps3，返回到齐标记、历史/当前站点壳、实况与时间分量。"""
    md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc = _analysis_time1(dt_now)
    ################################################################################
    # print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    # print("Process Model Time Is: " + str(md_current_yr) + str(md_current_mo).zfill(2) +
    #       str(md_current_dy).zfill(2) + str(md_current_hr_utc).zfill(2))
    # print("Process Valid Time Is: " + str(predict_valid).zfill(3))
    # print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    ################################################################################

    ################################################################################
    sd_before_model = list()  # 之前模式站点数据
    sd_current_model = list()  # 当前模式站点数据，用于制作集成预报
    for i_model in range(model_num):
        # 之前模式站点数据
        sd_before_model.append(copy_data(sd_sta_info))
        # 当前模式站点数据
        sd_current_model.append(copy_data(sd_sta_info))
    # 实况站点数据
    sta_before_flg = np.zeros(model_num)
    sta_current_flg = np.zeros(model_num)
    ################################################################################
    dt_fact, dt_valid, dt_model_current = _analysis_time2(md_current_yr, md_current_mo, md_current_dy,
                                                          md_current_hr_utc, predict_valid, is_obs_bjt)
    # 实况是北京时
    sta_rain_file_path = meb.get_path(fact_path, dt_fact, 000)
    simple_log.info("fact :" + sta_rain_file_path)
    print(f"[PATH] fact: {sta_rain_file_path}", flush=True)

    if not os.path.exists(sta_rain_file_path):
        _emit_miss("fact", sta_rain_file_path, "not exist")
        simple_log.error(sta_rain_file_path + " is not exist")
        return None

    try:
        sd_fact = meb.read_stadata_from_micaps3(filename=sta_rain_file_path, station=sd_sta_info, dtime=0,
                                                level=0,
                                                show=True)
    except Exception as exc:
        _emit_miss("fact", sta_rain_file_path, str(exc))
        simple_log.error(sta_rain_file_path + " Is Not Correct")
        return None
    ################################################################################
    dt_model_current, dt_model_before = _analysis_time3(md_current_yr, md_current_mo, md_current_dy,
                                                        md_current_hr_utc, predict_valid)
    for i_model in range(model_num):
        input_file_path = meb.get_path(
            model_path[i_model].replace('VVV', 'TTT'), dt_model_before,
            predict_valid)
        simple_log.info(model_path[i_model] + ": " + input_file_path)
        print(f"[PATH] hist-model: {input_file_path}", flush=True)
        if not os.path.exists(input_file_path):
            sta_before_flg[i_model] = 0.0
            _emit_miss("hist-model", input_file_path, "not exist")
            simple_log.info(input_file_path + " Is Not Exist")
        else:
            try:
                i_model_df = meb.read_stadata_from_micaps3(filename=input_file_path,
                                                           station=sd_sta_info,
                                                           time=dt_model_before, dtime=predict_valid,
                                                           level=0,
                                                           show=True)

                sd_before_model[i_model] = i_model_df
                sta_before_flg[i_model] = 1.0
            except Exception as exc:
                _emit_miss("hist-model", input_file_path, str(exc))
                simple_log.error(input_file_path + " Is Not Correct")
                sta_before_flg[i_model] = 0.0

    return sta_before_flg, sta_current_flg, sd_current_model, sd_before_model, sd_fact, md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc, dt_model_current

def _read_now_source_micaps3_micaps4(model_num, model_path, dt_model_current, predict_valid, model_name,
                                     sta_current_flg, simple_log, sd_sta_info, sd_current_model, md_current_yr,
                                     md_current_mo, md_current_dy, md_current_hr_utc, background_templates=None):
    """读当前各模式 Micaps3；首份可用 Micaps4 作 Cressman 背景，并构造 ``grid_base``。

    Micaps4 路径优先 ``background_templates[模式键]``（``para_3_background.ini``）；
    缺键或未配置时回退为同模式 Micaps3 改 ``.m4``。
    """
    background_templates = background_templates or {}
    lon_start, lon_end, d_lon = 70.0, 140.0, 0.1
    lat_start, lat_end, d_lat = 0.0, 60.0, 0.1
    gd_back_ground = None
    md_current_datetime = datetime.datetime(
        md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc)

    for i_model in range(model_num):
        input_file_path = meb.get_path(
            model_path[i_model].replace('VVV', 'TTT'), dt_model_current, predict_valid)
        print(f"[PATH] now-model: {input_file_path}", flush=True)
        if not os.path.exists(input_file_path):
            sta_current_flg[i_model] = 0.0
            _emit_miss("now-model", input_file_path, "not exist")
            simple_log.error(input_file_path + "Is Not Exist")
        else:
            try:
                j_model_df = meb.read_stadata_from_micaps3(filename=input_file_path, time=dt_model_current,
                                                           dtime=predict_valid, station=sd_sta_info,
                                                           level=0,
                                                           show=True)

                sd_current_model[i_model] = j_model_df
                sta_current_flg[i_model] = 1.0

            except Exception as exc:
                _emit_miss("now-model", input_file_path, str(exc))
                simple_log.error(input_file_path + " Is Not Correct")
                sta_current_flg[i_model] = 0.0

        if gd_back_ground is None:
            path_m3_md = meb.get_path(
                model_path[i_model].replace('VVV', 'TTT'),
                md_current_datetime,
                predict_valid)
            m4_file = path_m3_md[:-3] + ".m4"
            bg_tpl = background_templates.get(model_name[i_model])
            if bg_tpl:
                m4_file = meb.get_path(bg_tpl.replace("VVV", "TTT"), md_current_datetime, predict_valid)
            print(f"[PATH] background: {m4_file}", flush=True)
            if os.path.exists(m4_file):
                gd_back_ground = GridData(m4_file)
                lon_start = gd_back_ground.lon_start
                lon_end = gd_back_ground.lon_end
                lat_start = gd_back_ground.lat_start
                lat_end = gd_back_ground.lat_end
                d_lon = gd_back_ground.lon_interval
                d_lat = gd_back_ground.lat_interval
            else:
                _emit_miss("background", m4_file, "not exist")

    if gd_back_ground is None:
        print("[MISS] background: no usable Micaps4 found", flush=True)

    grid_base = meb.grid(
        glon=[lon_start, lon_end, d_lon],
        glat=[lat_start, lat_end, d_lat],
        gtime=[
            md_current_datetime,
            md_current_datetime,
            "{}h".format(predict_valid)], dtime_list=[predict_valid]
    )

    return sta_current_flg, gd_back_ground, grid_base