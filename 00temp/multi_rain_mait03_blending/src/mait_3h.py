# -*- coding: utf-8 -*-
"""
3 小时气象预报集成主程序（``src/mait_3h.py``）。

由 ``mait_3h`` 迁入 NIMM 布局；算法（TS 加权 → 频率匹配 → Cressman）保持不变。
时效默认 3–252 h、步长 3。

调用::

    from mait_3h import process
    process(time_inputs=["202608200000", "202608201200"], is_multi=False, pro_count=3)

    python -m cli --time-inputs=202608200000
    python -m cli --time-inputs=202608200000,202608201200 --is-multi=true --pro-count=4
    python src/mait_3h.py
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path


def _bootstrap_paths():
    _src = Path(__file__).resolve().parent
    _root = _src.parent
    for p in (str(_root), str(_src)):
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed((str(_root), str(_src))):
        sys.path.insert(0, p)


_bootstrap_paths()

from mait_3_plugin import (
    AnalysisTsWeightProcess,
    StationDataInterp2GridDataProcess,
    DataFlgProcess,
)
from mait_3_plugin_util import (
    write_beta,
    _data_write_to_micaps3,
    get_now_beta_file_path,
    get_his_beta_file_path,
    read_his_beta,
    write_grid_to_micaps4,
    _prepare,
    _analysis_para_ini,
    _analysis_background_ini,
    _read_history_source_micaps3,
    _read_now_source_micaps3_micaps4,
    read_grid_mask,
)
from utils.util_env import (
    get_resolved_paths,
    get_default_clip_coords,
    get_default_predict_valid_list,
    get_default_is_obs_bjt,
    get_default_pro_count,
    get_default_is_interp,
    get_default_is_multi,
    get_repo_root,
)
from utils.multipro_plugin import SimpleParallelTool


class RunProcess:
    """单次起报的时效循环：读数 → TS 加权 → 频率匹配 → Cressman → 写 Micaps3/4。"""

    def __init__(
        self,
        time_input,
        para_path,
        beta_path,
        background_path,
        is_obs_bjt,
        is_interp,
        clip_coords,
        predict_valid_list=None,
    ):
        self.time_input = time_input
        self.para_path = para_path
        self.beta_path = beta_path
        self.background_path = background_path
        self.is_obs_bjt = is_obs_bjt
        self.is_interp = is_interp
        self.clip_coords = clip_coords
        self.predict_valid_list = predict_valid_list

    def _process_single(self):
        """处理一个起报的全部时效（与 mait01/24 相同：多进程按起报分发）。

        步骤：解析 para → 读历史/当前/实况/背景 → 可用性检查 →
        TS+beta 加权与站点频率匹配 → 写 m3 → Cressman 上格点 → 写 m4。
        """
        area_scale = 0.5  # 训练区相对子区外扩比例
        predict_type = 3  # 3 小时累积降水

        app_dir = get_repo_root()
        os.chdir(app_dir)
        env_paths = get_resolved_paths()

        predict_valid_list = self.predict_valid_list
        if isinstance(predict_valid_list, int):
            predict_valid_list = [predict_valid_list]
        print(predict_valid_list, flush=True)
        if not predict_valid_list:
            return

        for predict_valid in predict_valid_list:
            log_file = env_paths["log_file_template"]
            para_filepath = self.para_path or env_paths["para_ini"]
            beta_filepath = self.beta_path or env_paths["beta_path_template"]
            background_filepath = self.background_path or env_paths["background_ini"]
            sd_sta_info_file = env_paths["station_info"]
            background_templates = _analysis_background_ini(background_filepath)

            simple_log, dt_now, sd_sta_info = _prepare(
                self.time_input, log_file, sd_sta_info_file)

            ini_tuple = _analysis_para_ini(para_filepath, simple_log)
            if not ini_tuple:
                print(f"[SKIP] para invalid or missing: {para_filepath}", flush=True)
                return
            model_num, model_name, model_path, fact_path, output_sample_path = ini_tuple

            # 历史模式站点 + 实况；当前模式时间由起报与时效推出
            hist = _read_history_source_micaps3(
                predict_valid, dt_now, model_num, sd_sta_info, fact_path, simple_log,
                model_path, self.is_obs_bjt)
            if hist is None:
                print(f"[SKIP] valid={predict_valid:03d}: fact missing, continue next lead time", flush=True)
                continue
            (
                sta_before_flg, sta_current_flg1, sd_current_model, sd_before_model,
                sd_fact, md_current_yr, md_current_mo, md_current_dy,
                md_current_hr_utc, dt_model_current,
            ) = hist

            sta_current_flg2, gd_back_ground, grid_base = _read_now_source_micaps3_micaps4(
                model_num, model_path, dt_model_current, predict_valid, model_name,
                sta_current_flg1, simple_log, sd_sta_info, sd_current_model,
                md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc,
                background_templates=background_templates)

            data_flg_process = DataFlgProcess(
                model_num, sta_before_flg, sta_current_flg2, simple_log)
            before_total_flg, currentTotalFlg, sta_current_flg = data_flg_process.process()

            if before_total_flg == 0.0:
                print("All Before Data Is Not Exist!\n", flush=True)
                continue
            if currentTotalFlg == 0.0:
                print("All Current Data Is Not Exist!\n", flush=True)
                continue

            # 历史 beta 参与 (1-α)s_before + α s_now
            obeta_file_path_list = get_now_beta_file_path(beta_filepath, grid_base)
            ibeta_file_path_list, iflag_list = get_his_beta_file_path(beta_filepath, grid_base)
            score_before_list, iflag_list = read_his_beta(
                ibeta_file_path_list, iflag_list, model_num, model_name, grid_base)

            analysis_ts_and_to_station_data = AnalysisTsWeightProcess(
                grid_base, area_scale, model_num,
                sd_before_model, sd_current_model, sd_sta_info, sd_fact,
                sta_before_flg, model_name, sta_current_flg,
                iflag_list, score_before_list)
            sd_output, score_last = analysis_ts_and_to_station_data.process()
            obeta_file_path = obeta_file_path_list[0][0][0]
            write_beta(obeta_file_path, model_num, model_name, score_last)
            _data_write_to_micaps3(predict_type, output_sample_path, sd_output, grid_base)

            mask_file = env_paths["mask_dat"]
            gd_mask_val, gd_mask_xn, gd_mask_yn = read_grid_mask(mask_file, grid_base)
            station2grid = StationDataInterp2GridDataProcess(
                gd_mask_val, gd_mask_xn, gd_mask_yn,
                grid_base, gd_back_ground, sd_output)
            gd_final_output = station2grid.process()
            write_grid_to_micaps4(
                gd_final_output, output_sample_path, predict_type,
                self.clip_coords, grid_base, self.is_interp)


def process_single(
    para_path, beta_path, background_path, is_obs_bjt, is_interp, clip_coords,
    predict_valid_list, **params,
):
    """多进程 worker：处理一个 ``time_input`` 的全部时效。"""
    param = params["param"]
    print(param, flush=True)
    RunProcess(
        param["time_input"], para_path, beta_path, background_path,
        is_obs_bjt, is_interp, clip_coords, predict_valid_list,
    )._process_single()


def process_multi(
    params, pro_count, para_path, beta_path, background_path, is_obs_bjt, is_interp,
    clip_coords, predict_valid_list,
):
    """用 ``SimpleParallelTool`` 按多个起报并行（与 mait01/24 相同）。"""
    sw_all = datetime.datetime.now()
    parallel_tool = SimpleParallelTool(
        target_func=process_single,
        parallel_mode="async",
        with_return=True,
        num_process=pro_count,
        fixed_params={
            "para_path": para_path,
            "beta_path": beta_path,
            "background_path": background_path,
            "is_obs_bjt": is_obs_bjt,
            "is_interp": is_interp,
            "clip_coords": clip_coords,
            "predict_valid_list": predict_valid_list,
        },
    )
    parallel_tool.process({"param": params})
    print(">>> Time elasped: " + str((datetime.datetime.now() - sw_all).total_seconds()))


def process(
    time_inputs=None,
    time_input=None,
    para_path=None,
    beta_path=None,
    background_path=None,
    is_obs_bjt=None,
    is_interp=None,
    is_multi=None,
    clip_coords=None,
    pro_count=None,
    predict_valid_list=None,
):
    """
    可调度入口。未传项从 ``resource/mait_3.ini`` 读取。

    多进程与 mait01/24 一致：``is_multi=True`` 时用 ``SimpleParallelTool``
    按 **起报时刻** 分发；每个 worker 串行跑该起报的全部时效。

    参数
    ----
    time_inputs : list[str], optional
        UTC 起报列表。写 ``YYYYMMDD0000`` / ``YYYYMMDD1200``，产品就出该 00/12Z
        （内部再转成作业时刻给 ``_analysis_time1``）。也兼容旧的 ``0800`` / ``2000``。
    time_input : str, optional
        单个起报（兼容旧调用）；与 ``time_inputs`` 同时给时以列表为准。
    predict_valid_list : list[int], optional
        预报时效（小时），默认 3–252、步长 3。
    para_path / beta_path / background_path : str, optional
        模式路径 ini、beta 模板、背景格点 ini；空则读 ``mait_3.ini``。
    is_obs_bjt : bool, optional
        实况是否按北京时（+8 h）。
    is_interp : bool, optional
        写出格点前是否按 ``clip_coords`` 双线性裁剪。
    is_multi : bool, optional
        多个起报是否多进程；``None`` 读 ini（默认 false）。
    clip_coords : list[float], optional
        ``lon0,lon1,lat0,lat1,dlon,dlat``。
    pro_count : int, optional
        起报并行进程数（仅 ``is_multi=True`` 时生效）。
    """
    if is_obs_bjt is None:
        is_obs_bjt = get_default_is_obs_bjt()
    if is_interp is None:
        is_interp = get_default_is_interp()
    if is_multi is None:
        is_multi = get_default_is_multi()
    if pro_count is None:
        pro_count = get_default_pro_count()
    if clip_coords is None:
        clip_coords = get_default_clip_coords()
    if predict_valid_list is None:
        predict_valid_list = get_default_predict_valid_list()

    if time_inputs is None:
        if time_input:
            time_inputs = [time_input]
        else:
            time_inputs = [datetime.datetime.now().strftime("%Y%m%d%H%M")]
    elif isinstance(time_inputs, str):
        time_inputs = [time_inputs]

    params = [{"time_input": t} for t in time_inputs]
    common = (
        para_path, beta_path, background_path, is_obs_bjt, is_interp, clip_coords,
        predict_valid_list,
    )
    if not is_multi:
        for param in params:
            process_single(*common, **{"param": param})
    else:
        process_multi(params, pro_count, *common)



if __name__ == "__main__":
    process(
        time_inputs=["202608201200"],
        para_path=None,
        beta_path=None,
        background_path=None,
        is_obs_bjt=True,
        is_interp=False,
        is_multi=False,
        clip_coords=[70.0, 140.0, 0.0, 60.0, 0.1, 0.1],
        pro_count=3,
    )

