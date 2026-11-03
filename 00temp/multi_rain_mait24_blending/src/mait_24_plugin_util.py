# -*- coding: UTF-8 -*-
# @Software : python
import datetime

import numpy as np
import meteva_base as meb
import os
from utils.util_context import RunContext
from utils.util_new import copy_data, GridData


def _analysis_background_ini(para_filepath):
    """
    解析 ``para_24_background.ini``：每行 ``模式键名=MICAPS4 路径模板``，与 ``para_24.ini`` 中模式键名一致。

    文件为 **GBK**；无 ``modelNum`` 头；空行与 ``#`` 开头行忽略。路径占位符须与 ``meteva_base.get_path``
    约定一致（如 ``YYYYMMDD``、``YYYYMMDDHH``、``TTT`` 等），由调用方传入起报时刻与预报时效展开。

    :param para_filepath: ini 绝对路径
    :return: ``dict[str, str]`` 模式键名 -> 路径模板；失败或路径无效时返回空字典
    """
    out = {}
    if not para_filepath or not os.path.exists(para_filepath):
        return out
    try:
        with open(para_filepath, "r", encoding="GBK") as sr:
            for str_tmp in sr:
                str_tmp = str_tmp.strip()
                if not str_tmp or str_tmp.startswith("#"):
                    continue
                if "=" not in str_tmp:
                    continue
                k, v = str_tmp.split("=", 1)
                key = k.strip()
                val = v.strip()
                if key:
                    out[key] = val
    except Exception:
        return {}
    return out


def _analysis_time1(dt_now):
    """
    时间函数1
    `_analysis_time1` 是 MAIT 系统里“**模式世界起报时间**”计算器。
    输入任意本地时刻 `dt_now`，它告诉你：
    1. 模式应使用的**当前起报 UTC 时间**（`md_current_datetime`）
    2. 该起报时间相对于本地时刻的**小时偏移量**（`num3`）
    规则一句话：
    - **本地 13–23 时** → 取**当天 00 UTC**
    - **其余时段** → 取**前一天 12 UTC**
    返回的两个值直接被下游用来拼接模式文件路径、计算预报时效，保证无论本地几点运行，永远拿到最接近且已落地的模式起报场。
    """
    # 获取模式数据时间
    if dt_now.hour > 12 and dt_now.hour <= 23:
        md_current_yr = dt_now.year
        md_current_mo = dt_now.month
        md_current_dy = dt_now.day
        md_current_hr_utc = 0
        num3 = 0
    else:
        dt_before = dt_now - datetime.timedelta(days=1)
        md_current_yr = dt_before.year
        md_current_mo = dt_before.month
        md_current_dy = dt_before.day
        md_current_hr_utc = 12
        num3 = 12

    md_current_datetime = datetime.datetime(
        md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc, 0,
        0)

    return md_current_datetime, num3


def _analysis_time2(md_current_datetime, predict_valid, num3, is_obs_bjt):
    """
    时间函数2
    `_analysis_time2` 是 MAIT 的“**预报时效 → 实况对应时刻**”转换器。
    输入模式起报时间、预报时效、偏移标志，输出三条时间：
    1. `dt_fact`
       需要读取的**实况观测时刻**（已按 `is_obs_bjt` 转成北京时或世界时）。
    2. `dt_valid`
       预报的**验证时刻**（= 起报 + predict_valid）。
    3. `dt_model_current`
       原封不动返回起报时刻，方便下游拼接文件路径。
    核心逻辑：
    - 当 `num3 == 0`（00 UTC 起报）→ 实况取**前一天**；否则取**当天**。
    - 把实况时刻的小时强制换成验证时刻的小时，保证日界对齐。
    - 最后根据 `is_obs_bjt` 加 8 h，确保读到的观测与预报在同一时区对比。
    """
    dt_model_current = md_current_datetime
    dt_valid = dt_model_current + datetime.timedelta(hours=predict_valid)

    if num3 == 0:
        dt_fact = dt_model_current - datetime.timedelta(days=1)
    else:
        dt_fact = dt_model_current + datetime.timedelta(days=0)

    dt_fact = datetime.datetime(dt_fact.year, dt_fact.month, dt_fact.day, dt_valid.hour, 0, 0)
    # 将24小时预报转换为北京时间
    if is_obs_bjt == True:  # 根据世界时或北京时读取对应实况数据
        obs_delta_hours = 8
    else:
        obs_delta_hours = 0

    dt_fact = dt_fact + datetime.timedelta(hours=obs_delta_hours)
    return dt_fact, dt_valid, dt_model_current


def _analysis_time3(md_current_datetime, predict_valid, num3):
    """
    时间函数3
    `_analysis_time3` 只做一件事：
    **根据当前起报时刻与预报时效，反推出“用于评分更新”的历史模式起报时刻。**

    步骤
    1. 算出验证时刻 `dt_valid = 起报 + predict_valid`
    2. 按 `num3` 规则（同 time1/time2）得到实况日界 `dt_fact`
    3. 把 `dt_fact` 的小时强制换成验证时刻的小时，保证日界对齐
    4. **再减一次 predict_valid** → 得到历史模式起报时刻 `dt_model_before`
    返回
    - `dt_model_current`：当前起报（原样带回）
    - `dt_model_before`：历史起报，用来读取“前一天”的模式场，与实况做 TS 评分
    一句话：**“昨天同一时效”的模式文件叫啥时间，就靠它算出来。**
    """
    # # 读取之前模式数据用于进行评分更新
    dt_model_current = md_current_datetime
    dt_valid = dt_model_current + datetime.timedelta(hours=predict_valid)
    if num3 == 0:
        dt_fact = dt_model_current - datetime.timedelta(days=1)
    else:
        dt_fact = dt_model_current + datetime.timedelta(days=0)
    dt_fact = datetime.datetime(dt_fact.year, dt_fact.month, dt_fact.day, dt_valid.hour, 0, 0)
    dt_model_before = dt_fact - datetime.timedelta(hours=predict_valid)
    return dt_model_current, dt_model_before


def _read_history_source_micaps3(predict_valid, ctx: RunContext):
    """
    读取micaps3
    该函数是 MAIT-24h 系统的“历史样本读取器”，核心任务只有一句话：
    **把“昨天同一时效”的模式场和对应实况一次性读进来，为后续 TS 评分更新准备历史样本。**
    逐段拆解
    1. 起报时间
       调用 `_analysis_time1` 得到模式世界当前起报时刻 `md_current_datetime` 及其小时偏移 `num3`。
    2. 容器初始化
       - `sd_before_model`：与模式个数等长的列表，准备存放“昨天”各模式站点数据
       - `sd_current_model`：同名结构，但这里仅做占位，**本函数并不读当前时效**（留给上游）
       - `sta_before_flg / sta_current_flg`：0/1 标志，记录文件是否存在/是否成功读取
    3. 实况路径
       用 `_analysis_time2` 算出验证时刻 `dt_valid` 与观测时刻 `dt_fact`（已按 `is_obs_bjt` 做时区偏移），拼出 MICAPS-III 实况文件名并立即读取到 `sd_fact`；文件缺失或格式错误直接抛异常，中断流程。
    4. 历史模式路径
       再用 `_analysis_time3` 算出“昨天同一时效”的起报时刻 `dt_model_before`。
       遍历所有模式路径模板（`model_path[i]` 中的 `VVV` 被替换成 `TTT` 以兼容不同模板），拼出历史文件全路径：
       - 文件不存在 → 标志置 0，写 info 日志
       - 存在则读入站点数据 → 存入 `sd_before_model[i]`，标志置 1；若读取失败同样置 0 并写 error 日志
    5. 返回
       - `sta_before_flg`：昨天各模式数据可用性 0/1 数组
       - `sta_current_flg`：全 0 占位（上游另行填充）
       - `sd_current_model`：空壳列表（上游另行填充）
       - `sd_before_model`：昨天各模式站点数据
       - `sd_fact`：对应实况降水
       - `md_current_datetime`：当前起报 UTC 时刻
       - `dt_model_current`：同起报时刻（原样带回，方便上游拼接当前时效路径）
    一句话总结
    **`_read_history_source_micaps3` 把“昨天同一时效”的所有模式场和实况一次性读好，并告诉你哪些模式昨天有数据、哪些缺失，为 TS 评分滚动更新提供历史样本。**

    """
    dt_now = ctx.session.dt_now
    sd_sta_info = ctx.session.sd_sta_info
    fact_path = ctx.paths.fact_path
    model_path = ctx.paths.model_path
    is_obs_bjt = ctx.session.is_obs_bjt

    # md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc, num3 = _analysis_time1(dt_now)
    md_current_datetime, num3 = _analysis_time1(dt_now)
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
    for i_model in range(len(model_path)):
        # 之前模式站点数据
        sd_before_model.append(copy_data(sd_sta_info))
        # 当前模式站点数据
        sd_current_model.append(copy_data(sd_sta_info))
    # 实况站点数据
    sta_before_flg = np.zeros(len(model_path))
    sta_current_flg = np.zeros(len(model_path))
    ################################################################################
    dt_fact, dt_valid, dt_model_current = _analysis_time2(md_current_datetime, predict_valid, num3, is_obs_bjt)

    sta_rain_file_path = meb.get_path(fact_path, dt_fact, 000)
    if not os.path.exists(sta_rain_file_path):
        raise FileNotFoundError(sta_rain_file_path)

    try:
        sd_fact = meb.read_stadata_from_micaps3(
            filename=sta_rain_file_path, station=sd_sta_info, dtime=0, level=0, show=True)
    except Exception as e:
        raise RuntimeError("实况读取失败: %s" % sta_rain_file_path) from e
    ################################################################################
    dt_model_current, dt_model_before = _analysis_time3(md_current_datetime, predict_valid, num3)
    for i_model in range(len(model_path)):
        input_file_path = meb.get_path(
            model_path[i_model].replace('VVV', 'TTT'), dt_model_before,
            predict_valid)
        if not os.path.exists(input_file_path):
            sta_before_flg[i_model] = 0.0
        else:
            try:
                i_model_df = meb.read_stadata_from_micaps3(
                    filename=input_file_path, station=sd_sta_info,
                    time=dt_model_before, dtime=predict_valid, level=0, show=True)
                sd_before_model[i_model] = i_model_df
                sta_before_flg[i_model] = 1.0
            except Exception:
                sta_before_flg[i_model] = 0.0

    return sta_before_flg, sta_current_flg, sd_current_model, sd_before_model, sd_fact, md_current_datetime, dt_model_current


def _read_now_source_micaps3_micaps4(
        dt_model_current, predict_valid, sta_current_flg, sd_current_model,
        md_current_datetime, ctx: RunContext):
    """
    读取当前时效各模式 MICAPS3 站点场，以及首份可用的 MICAPS4 背景格点 ``gd_back_ground``。

    MICAPS4 路径见 ``background_templates``（``para_24_background.ini``）；缺键时回退为同模式 MICAPS3 改 ``.m4``。

    :return: ``sta_current_flg``, ``gd_back_ground``, ``grid_base``
    """
    sd_sta_info = ctx.session.sd_sta_info
    model_name = ctx.models.model_name
    model_path = ctx.paths.model_path
    background_templates = ctx.paths.background_templates

    lon_start, lon_end, d_lon = 70.0, 140.0, 0.1
    lat_start, lat_end, d_lat = 0.0, 60.0, 0.1
    gd_back_ground = None

    for i_model in range(len(model_path)):
        input_file_path = meb.get_path(
            model_path[i_model].replace('VVV', 'TTT'), dt_model_current, predict_valid)

        if not os.path.exists(input_file_path):
            sta_current_flg[i_model] = 0.0
        else:
            try:
                j_model_df = meb.read_stadata_from_micaps3(
                    filename=input_file_path, time=dt_model_current,
                    dtime=predict_valid, station=sd_sta_info, level=0, show=True)
                sd_current_model[i_model] = j_model_df
                sta_current_flg[i_model] = 1.0
            except Exception:
                sta_current_flg[i_model] = 0.0

        if gd_back_ground is None:
            path_m3_md = meb.get_path(
                model_path[i_model].replace('VVV', 'TTT'),
                md_current_datetime, predict_valid)
            m4_file = path_m3_md[:-3] + ".m4"
            if background_templates:
                bg_tpl = background_templates.get(model_name[i_model])
                if bg_tpl:
                    m4_file = meb.get_path(bg_tpl, md_current_datetime, predict_valid)
            if os.path.exists(m4_file):
                gd_back_ground = GridData(m4_file)
                lon_start = gd_back_ground.lon_start
                lon_end = gd_back_ground.lon_end
                lat_start = gd_back_ground.lat_start
                lat_end = gd_back_ground.lat_end
                d_lon = gd_back_ground.lon_interval
                d_lat = gd_back_ground.lat_interval

    grid_base = meb.grid(
        glon=[lon_start, lon_end, d_lon],
        glat=[lat_start, lat_end, d_lat],
        gtime=[md_current_datetime, md_current_datetime, "{}h".format(predict_valid)],
        dtime_list=[predict_valid],
    )

    return sta_current_flg, gd_back_ground, grid_base



