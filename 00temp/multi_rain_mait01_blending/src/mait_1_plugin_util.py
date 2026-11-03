# -*- coding: UTF-8 -*-
"""
MAIT 1h 数据读取与时间工具（``mait_1_plugin_util.py``）。

与数值结果相关的分工：

- **站点 Micaps3**：仍按模式配置 ini（``local.ini`` / ``para_1.ini``）模板 + ``VVV→TTT`` + 36h 回溯（``_find_model_file_with_backtrack``）
- **背景格点 M4**：按 ``para_1_background.ini`` 模板（``.m4``）+ ``dt_search_base`` 与 36h 回溯；均无则全 0 规则格点（与 mait_st 无 m4 时一致）
- **``gd_back_ground`` / ``grid_base`` 经纬度**：仍取**第一个**成功读入的背景文件元数据（与旧版“只取一份背景场”一致）
- **时间函数** ``_analysis_time1/2/3``：未改规则；``is_obs_bjt`` 在 time2 中 +8h 对齐实况

配置路径（``mait_1.ini``、background ini）只影响读哪些文件，不改变 TS/插值/频率匹配公式。
"""

import datetime

import numpy as np
import meteva_base as meb
import os
from utils.util_new import copy_data, GridData, NcData, create_regular_background_grid
from utils.util_context import RunContext


def _analysis_background_ini(para_filepath):
    """解析 ``para_1_background.ini``：每行 ``模式键名=格点路径模板``，键名须与 local.ini / para_1.ini 一致。支持 UTF-8/GBK/GB18030；``#`` 与空行忽略。"""
    out = {}
    if not para_filepath or not os.path.exists(para_filepath):
        return out
    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            with open(para_filepath, "r", encoding=encoding) as sr:
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
            if out:
                return out
        except (UnicodeDecodeError, OSError):
            continue
        except Exception:
            return {}
    return out


def _resolve_background_file_path(bg_tpl, base_time, predict_valid):
    """按 background ini 模板（已含 TTT、``.m4``）展开路径，36h 回溯；不做 VVV→TTT 替换。"""
    found, ref_time, ref_valid = _find_model_file_with_backtrack(
        bg_tpl, base_time, predict_valid, max_back_hours=36, start_back_hours=1,
        replace_vvv=False,
    )
    if found is not None:
        return found, ref_time, ref_valid
    path = meb.get_path(bg_tpl, base_time, predict_valid)
    return path, base_time, predict_valid


def _load_background_grid(file_path, grid0):
    """读取背景格点；当前配置为 ``.m4``，亦兼容 ``.nc``。"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".nc":
        grid_field = meb.read_griddata_from_nc(file_path, grid=grid0)
        meta = NcData(file_path)
        return grid_field, meta
    if ext == ".m4":
        grid_field = meb.read_griddata_from_micaps4(file_path, grid=grid0)
        meta = GridData(file_path)
        return grid_field, meta
    raise ValueError("背景格点仅支持 .m4 或 .nc: %s" % file_path)


def _find_model_file_with_backtrack(
        model_template, base_time, base_valid, max_back_hours=36, start_back_hours=1,
        replace_vvv=True):
    """
    在 [start_back_hours, max_back_hours] 内按小时回溯，找最近存在的模式文件。
    返回 (path, ref_time, ref_valid)；找不到则 (None, None, None)。
    站点 M3 默认 replace_vvv=True；background ini 调用时传 replace_vvv=False。
    """
    template = model_template.replace('VVV', 'TTT') if replace_vvv else model_template
    for back_h in range(start_back_hours, max_back_hours + 1):
        ref_time = base_time - datetime.timedelta(hours=back_h)
        ref_valid = base_valid + back_h
        p = meb.get_path(template, ref_time, ref_valid)
        if os.path.exists(p):
            return p, ref_time, ref_valid
    return None, None, None


def _analysis_time1(dt_now):
    """
    鏃堕棿鍑芥暟1
    `_analysis_time1` 鏄?MAIT 绯荤粺閲屸€?*妯″紡涓栫晫璧锋姤鏃堕棿**鈥濊绠楀櫒銆?    杈撳叆浠绘剰鏈湴鏃跺埢 `dt_now`锛屽畠鍛婅瘔浣狅細
    1. 妯″紡搴斾娇鐢ㄧ殑**褰撳墠璧锋姤 UTC 鏃堕棿**锛坄md_current_datetime`锛?    2. 璇ヨ捣鎶ユ椂闂寸浉瀵逛簬鏈湴鏃跺埢鐨?*灏忔椂鍋忕Щ閲?*锛坄num3`锛?    瑙勫垯涓€鍙ヨ瘽锛?    - **鏈湴 13鈥?3 鏃?* 鈫?鍙?*褰撳ぉ 00 UTC**
    - **鍏朵綑鏃舵** 鈫?鍙?*鍓嶄竴澶?12 UTC**
    杩斿洖鐨勪袱涓€肩洿鎺ヨ涓嬫父鐢ㄦ潵鎷兼帴妯″紡鏂囦欢璺緞銆佽绠楅鎶ユ椂鏁堬紝淇濊瘉鏃犺鏈湴鍑犵偣杩愯锛屾案杩滄嬁鍒版渶鎺ヨ繎涓斿凡钀藉湴鐨勬ā寮忚捣鎶ュ満銆?    """
    # 鑾峰彇妯″紡鏁版嵁鏃堕棿
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
    鏃堕棿鍑芥暟2
    `_analysis_time2` 鏄?MAIT 鐨勨€?*棰勬姤鏃舵晥 鈫?瀹炲喌瀵瑰簲鏃跺埢**鈥濊浆鎹㈠櫒銆?    杈撳叆妯″紡璧锋姤鏃堕棿銆侀鎶ユ椂鏁堛€佸亸绉绘爣蹇楋紝杈撳嚭涓夋潯鏃堕棿锛?    1. `dt_fact`
       闇€瑕佽鍙栫殑**瀹炲喌瑙傛祴鏃跺埢**锛堝凡鎸?`is_obs_bjt` 杞垚鍖椾含鏃舵垨涓栫晫鏃讹級銆?    2. `dt_valid`
       棰勬姤鐨?*楠岃瘉鏃跺埢**锛? 璧锋姤 + predict_valid锛夈€?    3. `dt_model_current`
       鍘熷皝涓嶅姩杩斿洖璧锋姤鏃跺埢锛屾柟渚夸笅娓告嫾鎺ユ枃浠惰矾寰勩€?    鏍稿績閫昏緫锛?    - 褰?`num3 == 0`锛?0 UTC 璧锋姤锛夆啋 瀹炲喌鍙?*鍓嶄竴澶?*锛涘惁鍒欏彇**褰撳ぉ**銆?    - 鎶婂疄鍐垫椂鍒荤殑灏忔椂寮哄埗鎹㈡垚楠岃瘉鏃跺埢鐨勫皬鏃讹紝淇濊瘉鏃ョ晫瀵归綈銆?    - 鏈€鍚庢牴鎹?`is_obs_bjt` 鍔?8 h锛岀‘淇濊鍒扮殑瑙傛祴涓庨鎶ュ湪鍚屼竴鏃跺尯瀵规瘮銆?    """
    dt_model_current = md_current_datetime
    dt_valid = dt_model_current + datetime.timedelta(hours=predict_valid)
    if num3 == 0:
        dt_fact = dt_model_current - datetime.timedelta(days=1)
    else:
        dt_fact = dt_model_current + datetime.timedelta(days=0)
    dt_fact = datetime.datetime(dt_fact.year, dt_fact.month, dt_fact.day, dt_valid.hour, 0, 0)
    if is_obs_bjt == True:
        obs_delta_hours = 8
    else:
        obs_delta_hours = 0

    dt_fact = dt_fact + datetime.timedelta(hours=obs_delta_hours)
    return dt_fact, dt_valid, dt_model_current


def _analysis_time3(md_current_datetime, predict_valid, num3):
    """
    鏃堕棿鍑芥暟3
    `_analysis_time3` 鍙仛涓€浠朵簨锛?    **鏍规嵁褰撳墠璧锋姤鏃跺埢涓庨鎶ユ椂鏁堬紝鍙嶆帹鍑衡€滅敤浜庤瘎鍒嗘洿鏂扳€濈殑鍘嗗彶妯″紡璧锋姤鏃跺埢銆?*

    姝ラ
    1. 绠楀嚭楠岃瘉鏃跺埢 `dt_valid = 璧锋姤 + predict_valid`
    2. 鎸?`num3` 瑙勫垯锛堝悓 time1/time2锛夊緱鍒板疄鍐垫棩鐣?`dt_fact`
    3. 鎶?`dt_fact` 鐨勫皬鏃跺己鍒舵崲鎴愰獙璇佹椂鍒荤殑灏忔椂锛屼繚璇佹棩鐣屽榻?    4. **鍐嶅噺涓€娆?predict_valid** 鈫?寰楀埌鍘嗗彶妯″紡璧锋姤鏃跺埢 `dt_model_before`
    杩斿洖
    - `dt_model_current`锛氬綋鍓嶈捣鎶ワ紙鍘熸牱甯﹀洖锛?    - `dt_model_before`锛氬巻鍙茶捣鎶ワ紝鐢ㄦ潵璇诲彇鈥滃墠涓€澶┾€濈殑妯″紡鍦猴紝涓庡疄鍐靛仛 TS 璇勫垎
    涓€鍙ヨ瘽锛?*鈥滄槰澶╁悓涓€鏃舵晥鈥濈殑妯″紡鏂囦欢鍙暐鏃堕棿锛屽氨闈犲畠绠楀嚭鏉ャ€?*
    """
    # # 璇诲彇涔嬪墠妯″紡鏁版嵁鐢ㄤ簬杩涜璇勫垎鏇存柊
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
    """读取昨日同时效实况与各模式 Micaps3 站点场，返回历史样本与当前占位容器。"""
    dt_now = ctx.session.dt_now
    sd_sta_info = ctx.session.sd_sta_info
    fact_path = ctx.paths.fact_path
    model_path = ctx.paths.model_path
    is_obs_bjt = ctx.session.is_obs_bjt

    md_current_datetime, num3 = _analysis_time1(dt_now)
    sd_before_model = list()
    sd_current_model = list()
    for i_model in range(len(model_path)):
        # 涔嬪墠妯″紡绔欑偣鏁版嵁
        sd_before_model.append(copy_data(sd_sta_info))
        # 褰撳墠妯″紡绔欑偣鏁版嵁
        sd_current_model.append(copy_data(sd_sta_info))
    # 瀹炲喌绔欑偣鏁版嵁
    sta_before_flg = np.zeros(len(model_path))
    sta_current_flg = np.zeros(len(model_path))
    ################################################################################
    dt_fact, dt_valid, dt_model_current = _analysis_time2(md_current_datetime, predict_valid, num3, is_obs_bjt)
    # 瀹炲喌鏄寳浜椂
    sta_rain_file_path = meb.get_path(fact_path, dt_fact, 000)
    print("=-------------------------------------------->>> :: ", sta_rain_file_path)
    if not os.path.exists(sta_rain_file_path):
        # simple_log.error(sta_rain_file_path + " is not exist")
        # predict_valid += predict_interval
        raise Exception

    try:
        sd_fact = meb.read_stadata_from_micaps3(filename=sta_rain_file_path, station=sd_sta_info, dtime=0,
                                                level=0,
                                                show=True)
    except:
        # simple_log.error(sta_rain_file_path + " Is Not Correct")
        # predict_valid += predict_interval
        raise Exception
        # continue
    ################################################################################
    dt_model_current, dt_model_before = _analysis_time3(md_current_datetime, predict_valid, num3)
    for i_model in range(len(model_path)):
        input_file_path = meb.get_path(
            model_path[i_model].replace('VVV', 'TTT'), dt_model_before,
            predict_valid)
        # simple_log.info(model_path[i_model] + ": " + input_file_path)
        if not os.path.exists(input_file_path):
            sta_before_flg[i_model] = 0.0
            # simple_log.info(input_file_path + " Is Not Exist")
        else:
            try:
                i_model_df = meb.read_stadata_from_micaps3(filename=input_file_path,
                                                           station=sd_sta_info,
                                                           time=dt_model_before, dtime=predict_valid,
                                                           level=0,
                                                           show=True)

                sd_before_model[i_model] = i_model_df
                sta_before_flg[i_model] = 1.0
            except:
                # simple_log.error(input_file_path + " Is Not Correct")
                sta_before_flg[i_model] = 0.0

    return sta_before_flg, sta_current_flg, sd_current_model, sd_before_model, sd_fact, md_current_datetime, dt_model_current


def _read_mait_st_like_score_samples(predict_valid, ctx: RunContext, check_num=10):
    """读取近 check_num 日同时效样本及前 1 小时 front 样本，供 TS 权重计算。"""
    dt_now = ctx.session.dt_now
    sd_sta_info = ctx.session.sd_sta_info
    fact_path = ctx.paths.fact_path
    model_path = ctx.paths.model_path
    is_obs_bjt = ctx.session.is_obs_bjt

    # 妯″紡妫€绱㈠熀鍑嗭細dt_input = process_time - 8h锛坕s_obs_bjt 鏃讹級
    dt_input = dt_now - datetime.timedelta(hours=8 if is_obs_bjt else 0)
    dt_model_current = dt_input
    dt_model_before = dt_input

    model_num = len(model_path)
    model_ref_time = [dt_model_current for _ in range(model_num)]
    model_ref_valid = [predict_valid for _ in range(model_num)]
    for m in range(model_num):
        _, ref_time, ref_valid = _find_model_file_with_backtrack(
            model_path[m], dt_input, predict_valid, max_back_hours=36, start_back_hours=1
        )
        if ref_time is not None:
            model_ref_time[m] = ref_time
            model_ref_valid[m] = ref_valid

    before_model = [[copy_data(sd_sta_info) for _ in range(check_num)] for _ in range(model_num)]
    before_model_flag = np.zeros((model_num, check_num))
    before_fact = [copy_data(sd_sta_info) for _ in range(check_num)]
    before_fact_flag = np.zeros(check_num)

    # mait_st 鐨勫巻鍙插疄鍐靛熀鍑嗕娇鐢?model_ref_time[0] + model_ref_valid[0]
    dt_fact_ref = model_ref_time[0] + datetime.timedelta(hours=model_ref_valid[0])
    for k in range(check_num):
        dt_hist_fact = dt_fact_ref - datetime.timedelta(hours=24 * (k + 1))

        fact_file = meb.get_path(fact_path, dt_hist_fact, 0)
        if os.path.exists(fact_file):
            try:
                before_fact[k] = meb.read_stadata_from_micaps3(
                    filename=fact_file, station=sd_sta_info, dtime=0, level=0, show=True
                )
                before_fact_flag[k] = 1.0
            except Exception:
                before_fact_flag[k] = 0.0

        for m in range(model_num):
            dt_hist_model = model_ref_time[m] - datetime.timedelta(hours=24 * (k + 1))
            hist_valid = model_ref_valid[m]
            model_file = meb.get_path(model_path[m].replace('VVV', 'TTT'), dt_hist_model, hist_valid)
            if os.path.exists(model_file):
                try:
                    before_model[m][k] = meb.read_stadata_from_micaps3(
                        filename=model_file, station=sd_sta_info, time=dt_hist_model, dtime=hist_valid, level=0, show=True
                    )
                    before_model_flag[m, k] = 1.0
                except Exception:
                    before_model_flag[m, k] = 0.0

    front_model = [copy_data(sd_sta_info) for _ in range(model_num)]
    front_model_flag = np.zeros(model_num)
    front_fact = None

    dt_front_fact = dt_input - datetime.timedelta(hours=1)
    front_fact_file = meb.get_path(fact_path, dt_front_fact, 0)
    if os.path.exists(front_fact_file):
        try:
            front_fact = meb.read_stadata_from_micaps3(
                filename=front_fact_file, station=sd_sta_info, dtime=0, level=0, show=True
            )
        except Exception:
            front_fact = None

    if front_fact is not None:
        for m in range(model_num):
            # 瀵归綈 mait_st锛歠ront 妯″紡鏃舵晥 = (front_valid_time - ref_time).hours
            dt_front_valid = dt_input - datetime.timedelta(hours=1)
            front_valid = int((dt_front_valid - model_ref_time[m]).total_seconds() / 3600.0)
            if front_valid < 0:
                continue
            front_model_file = meb.get_path(
                model_path[m].replace('VVV', 'TTT'),
                model_ref_time[m],
                front_valid
            )
            if os.path.exists(front_model_file):
                try:
                    front_model[m] = meb.read_stadata_from_micaps3(
                        filename=front_model_file,
                        station=sd_sta_info,
                        time=model_ref_time[m],
                        dtime=front_valid,
                        level=0,
                        show=True
                    )
                    front_model_flag[m] = 1.0
                except Exception:
                    front_model_flag[m] = 0.0

    return before_model, before_model_flag, before_fact, before_fact_flag, front_model, front_model_flag, front_fact


def _read_now_source_micaps3_nc(
        dt_model_current, predict_valid, sta_current_flg, sd_current_model,
        md_current_datetime, ctx: RunContext, dt_search_base=None):
    """
    读取当前时效 Micaps3 站点场 + 背景 M4 场。

    - 站点：模式配置 ini 的 M3 模板，检索基准 ``dt_search_base``
    - 背景：``para_1_background.ini`` 的 ``.m4`` 模板，同一检索基准与 36h 回溯；首个读成功者作 ``gd_back_ground``
    - 均无可用背景文件时：70–140°E / 0–60°N 全 0 格点（与 mait_st 无 m4 时一致）

    :return: sta_current_flg, gd_back_ground, grid_base, grid_model_dict
    """
    sd_sta_info = ctx.session.sd_sta_info
    model_name = ctx.models.model_name
    model_path = ctx.paths.model_path
    background_templates = ctx.paths.background_templates
    clip_coords = ctx.grid.clip_coords
    if dt_search_base is None:
        dt_search_base = ctx.dt_search_base()

    grid_model_dict = {}
    grid0 = meb.grid(
        glon=[clip_coords[0], clip_coords[1], clip_coords[-2]],
        glat=[clip_coords[2], clip_coords[3], clip_coords[-1]],
    )

    lon_start, lon_end, d_lon = 70.0, 140.0, 0.1
    lat_start, lat_end, d_lat = 0.0, 60.0, 0.1
    gd_back_ground = None
    search_base_time = dt_search_base

    for i_model in range(len(model_path)):
        input_file_path, ref_time, ref_valid = _find_model_file_with_backtrack(
            model_path[i_model], search_base_time, predict_valid, max_back_hours=36, start_back_hours=1
        )
        if input_file_path is None:
            input_file_path = meb.get_path(
                model_path[i_model].replace("VVV", "TTT"), search_base_time, predict_valid)
            ref_time = search_base_time
            ref_valid = predict_valid

        if not os.path.exists(input_file_path):
            sta_current_flg[i_model] = 0.0
        else:
            try:
                j_model_df = meb.read_stadata_from_micaps3(
                    filename=input_file_path, time=ref_time, dtime=ref_valid,
                    station=sd_sta_info, level=0, show=True)
                sd_current_model[i_model] = j_model_df
                sta_current_flg[i_model] = 1.0
            except Exception:
                sta_current_flg[i_model] = 0.0

        bg_tpl = background_templates[model_name[i_model]]
        bg_file, _, _ = _resolve_background_file_path(bg_tpl, search_base_time, predict_valid)
        if not os.path.exists(bg_file):
            grid_model_dict[model_name[i_model]] = ""
            continue
        try:
            grid_field, bg_meta = _load_background_grid(bg_file, grid0)
            grid_model_dict[model_name[i_model]] = grid_field
            if gd_back_ground is None:
                gd_back_ground = bg_meta
                lon_start = gd_back_ground.lon_start
                lon_end = gd_back_ground.lon_end
                lat_start = gd_back_ground.lat_start
                lat_end = gd_back_ground.lat_end
                d_lon = gd_back_ground.lon_interval
                d_lat = gd_back_ground.lat_interval
        except Exception:
            grid_model_dict[model_name[i_model]] = ""

    if gd_back_ground is None:
        gd_back_ground = create_regular_background_grid(
            lon_start, lon_end, lat_start, lat_end, d_lon, d_lat)

    grid_base = meb.grid(
        glon=[lon_start, lon_end, d_lon],
        glat=[lat_start, lat_end, d_lat],
        gtime=[
            md_current_datetime,
            md_current_datetime,
            "{}h".format(predict_valid)],
        dtime_list=[predict_valid],
    )

    return sta_current_flg, gd_back_ground, grid_base, grid_model_dict
