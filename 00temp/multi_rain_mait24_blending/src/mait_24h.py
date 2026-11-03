# -*- coding: utf-8 -*-
"""
24 小时气象预报集成主程序（``src/mait_24h.py``）。

流程概要
--------
1. ``process`` — 合并参数与 ini 默认值，单进程或多进程派发 ``time_inputs``。
2. ``RunProcess._setup_context`` — 读 ``mait_24.ini`` 路径、``para_24.ini``、站点表、背景 ini，
   初始化日志，调用 ``build_run_context`` 得到 ``ctx``。
3. ``RunProcess._process_single`` — 读掩码后按 ``predict_valid_list`` 循环：
   读历史/当前资料 → beta → TS 权重 → 写 Micaps3/beta → 插值网格 → 写 Micaps4。
   日志仅在主流程记录；子函数失败抛异常，由主流程 ``log.error``。

多进程时每个 ``time_input`` 独立日志文件（子进程文件名含 pid），避免并发写冲突。

调用方式
--------
- 模块调用：``from mait_24h import process`` → ``process(time_inputs=[...], ...)``
- 直接运行：``python src/mait_24h.py``（在 ``__main__`` 中改传参）
- 命令行：``python -m cli --time-inputs=...``（项目根目录）
"""
import sys
from pathlib import Path


def _bootstrap_paths():
    """项目根优先（加载本地 ``utils/__init__`` 合并 ``00temp/utils``），再 ``src``。"""
    _src = Path(__file__).resolve().parent
    _root = _src.parent
    ordered = (str(_root), str(_src))
    for p in ordered:
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed(ordered):
        sys.path.insert(0, p)


_bootstrap_paths()

import datetime
import os
import numpy as np
import pandas as pd

from utils.multipro_plugin import SimpleParallelTool
from utils.util_context import build_run_context
from mait_24_plugin import AnalysisTsWeightProcess, StationDataInterp2GridDataProcess

from mait_24_plugin_util import (
    _read_history_source_micaps3,
    _read_now_source_micaps3_micaps4,
    _analysis_background_ini,
)
from utils.util_env import (
    get_resolved_paths,
    get_default_clip_coords,
    get_default_predict_valid_list,
    get_default_is_obs_bjt,
    get_default_is_multi,
    get_default_pro_count,
    get_default_split_lat,
    get_default_split_lon,
)
from utils.util_new import (
    read_grid_mask_nc, _prepare, _analysis_para_ini, init_run_log,
    _data_write_to_micaps3, write_grid_to_micaps4,
    get_now_beta_file_path_npy, get_his_beta_file_path_npy, read_his_beta_npy, write_beta_npy,
)


class RunProcess():
    """单次起报时刻（``time_input``）的完整集成流水线。"""

    def __init__(self, time_input, para_path, beta_path, is_obs_bjt, clip_coords, split_lat=1, split_lon=1, predict_valid_list=None):
        self.time_input = time_input
        self.para_path = para_path
        self.beta_path = beta_path
        self.is_obs_bjt = is_obs_bjt
        self.clip_coords = clip_coords
        self.split_lat = split_lat
        self.split_lon = split_lon
        self.predict_valid_list = predict_valid_list
        if predict_valid_list is None:
            self.predict_valid_list = [i for i in range(36, 252 + 24, 24)]

    def _setup_context(self):
        """
        准备阶段：解析配置、读站点表、组装 ``RunContext``。

        文件依赖（均在调用 ``build_run_context`` 之前完成）：
        - ``resource/mait_24.ini``（经 ``get_resolved_paths``）
        - ``para_24.ini``、``para_24_background.ini``、``station_info.txt``

        返回 ``(ctx, env_paths, log)``；失败时 ``ctx`` 为 ``None``，日志仍可用。
        """
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        env_paths = get_resolved_paths()
        para_filepath = self.para_path or env_paths["para_ini"]
        beta_filepath = self.beta_path or env_paths["beta_path_template"]

        log = init_run_log(env_paths["log_file_template"], time_input=self.time_input)
        log.info("启动 time_input=%s valid_list=%s", self.time_input, self.predict_valid_list)

        try:
            dt_now, sd_sta_info = _prepare(self.time_input, env_paths["station_info"])
        except Exception as e:
            log.error("准备阶段失败: %s", e)
            return None, None, log

        ini_tuple = _analysis_para_ini(para_filepath)
        if not ini_tuple:
            log.error("参数文件不存在或内容错误: %s", para_filepath)
            return None, None, log
        model_name, model_path, fact_path, output_sample_path = ini_tuple

        background_templates = _analysis_background_ini(env_paths["background_ini"])
        ctx = build_run_context(
            beta_path_template=beta_filepath,
            is_obs_bjt=self.is_obs_bjt,
            clip_coords=self.clip_coords,
            split_lat=self.split_lat,
            split_lon=self.split_lon,
            dt_now=dt_now,
            sd_sta_info=sd_sta_info,
            model_name=model_name,
            model_path=model_path,
            fact_path=fact_path,
            output_sample_path=output_sample_path,
            background_templates=background_templates,
        )
        return ctx, env_paths, log

    def _process_single(self):
        """执行单个 ``time_input`` 下全部预报时效的处理。"""
        ctx, env_paths, log = self._setup_context()
        if ctx is None:
            return

        model_name = list(ctx.models.model_name)
        try:
            gd_mask_val, gd_mask_xn, gd_mask_yn = read_grid_mask_nc(env_paths["mask_nc"])
        except Exception as e:
            log.error("掩码文件读取失败: %s", e)
            return

        for predict_valid in self.predict_valid_list:
            try:
                # 昨日同时效模式 + 实况；再读当前时效各模式 Micaps3 与背景 Micaps4
                sta_before_flg, sta_current_flg, sd_current_model, sd_before_model, sd_fact, md_current_datetime, dt_model_current = (
                    _read_history_source_micaps3(predict_valid, ctx))
                sta_current_flg, gd_back_ground, grid_base = _read_now_source_micaps3_micaps4(
                    dt_model_current, predict_valid, sta_current_flg, sd_current_model,
                    md_current_datetime, ctx)
            except Exception as e:
                log.error("读取资料失败 valid=%sh: %s", predict_valid, e)
                return

            if not np.any(sta_before_flg):
                log.error("历史模式数据均不存在 valid=%sh", predict_valid)
                return
            if not np.any(sta_current_flg):
                log.error("当前模式数据均不存在 valid=%sh", predict_valid)
                return

            obeta_file_path_list = get_now_beta_file_path_npy(grid_base, ctx)
            ibeta_file_path_list, iflag_list = get_his_beta_file_path_npy(grid_base, ctx)
            score_before_list, iflag_list = read_his_beta_npy(
                ibeta_file_path_list, iflag_list, grid_base, ctx)

            analysis_ts = AnalysisTsWeightProcess(
                grid_base, sd_before_model, sd_current_model, sd_fact,
                sta_before_flg, sta_current_flg, iflag_list, score_before_list, ctx)
            sd_output, score_last = analysis_ts.process()

            score_last_np = np.asarray(score_last)
            sd_outputs = []
            for idx, obeta_file_paths in enumerate(obeta_file_path_list[0]):
                for jdx, obeta_file_path in enumerate(obeta_file_paths):
                    write_beta_npy(obeta_file_path, model_name, score_last_np[0][idx][jdx])
                    sd_outputs.append(sd_output[0][idx][jdx])
            __sd_output = pd.concat(sd_outputs, ignore_index=True)

            _data_write_to_micaps3(__sd_output, grid_base, ctx)
            gd_final_output = StationDataInterp2GridDataProcess(
                gd_mask_val, gd_mask_xn, gd_mask_yn, grid_base, gd_back_ground, __sd_output).process()
            write_grid_to_micaps4(gd_final_output, grid_base, ctx)
            log.info("时效 %sh 处理完成", predict_valid)

        log.info("全部时效处理完成 time_input=%s", self.time_input)


def process_single(para_path, beta_path, is_obs_bjt, clip_coords, split_lat, split_lon, predict_valid_list, **params):
    """多进程 worker 入口：处理一个 ``time_input``。"""
    RunProcess(
        params['param']['time_input'], para_path, beta_path, is_obs_bjt,
        clip_coords, split_lat, split_lon, predict_valid_list,
    )._process_single()


def process_multi(params, pro_count, para_path, beta_path, is_obs_bjt, clip_coords, split_lat, split_lon, predict_valid_list):
    """多进程批量处理多个 ``time_input``。"""
    sw_all = datetime.datetime.now()
    print("=----------------------------------------> ???")
    parallel_tool = SimpleParallelTool(
        target_func=process_single,
        parallel_mode="async",
        with_return=True,
        num_process=pro_count,
        fixed_params={
            "para_path": para_path,
            "beta_path": beta_path,
            "is_obs_bjt": is_obs_bjt,
            "clip_coords": clip_coords,
            "split_lat": split_lat,
            "split_lon": split_lon,
            "predict_valid_list": predict_valid_list,
        }
    )
    parallel_tool.process({"param": params})
    print(">>> Time elasped: " + str((datetime.datetime.now() - sw_all).total_seconds()))


def process(*,
            time_inputs: list = None,
            predict_valid_list: list = None,
            para_path: str = None,
            beta_path: str = None,
            is_obs_bjt = None,
            is_multi = None,
            clip_coords: list = None,
            pro_count = None,
            split_lat = None,
            split_lon = None,
            ):
    """
    24 小时集成主入口。

    ``time_inputs`` 为必传列表。其余为 ``None`` 时从 ``resource/mait_24.ini`` 读取默认值
    （见 ``utils/util_env.py``）。
    """
    if predict_valid_list is None:
        predict_valid_list = get_default_predict_valid_list()
    if is_obs_bjt is None:
        is_obs_bjt = get_default_is_obs_bjt()
    if is_multi is None:
        is_multi = get_default_is_multi()
    if clip_coords is None:
        clip_coords = get_default_clip_coords()
    if pro_count is None:
        pro_count = get_default_pro_count()
    if split_lat is None:
        split_lat = get_default_split_lat()
    if split_lon is None:
        split_lon = get_default_split_lon()

    params = [{"time_input": t} for t in time_inputs]

    if not is_multi:
        for param in params:
            process_single(para_path, beta_path, is_obs_bjt, clip_coords, split_lat, split_lon, predict_valid_list, **{"param": param})
    else:
        process_multi(params, pro_count, para_path, beta_path, is_obs_bjt, clip_coords, split_lat, split_lon, predict_valid_list)


if __name__ == "__main__":
    # 直接运行：在此修改 process 传参即可；命令行请用 python -m cli ...
    target_dateime = datetime.datetime.now().replace(hour=8, minute=0, second=0)
    target_dateime = target_dateime.replace(day=target_dateime.day - 2)
    # target_dateime = datetime.datetime(2026,8,9,8)
    time_inputs = [(target_dateime + datetime.timedelta(hours=h)).strftime("%Y%m%d%H00") for h in [0, 12]]
    print(time_inputs)

    process(
        # time_inputs=["202605240800"],
        time_inputs=time_inputs,
        predict_valid_list=[36, 60, 84, 108, 132, 156, 180, 204, 228, 252],
        para_path=None,
        beta_path=None,
        is_obs_bjt=True,
        is_multi=False,
        clip_coords=[70.0, 140.0, 0.0, 60.0, 0.1, 0.1],
        pro_count=6,
        split_lat=1,
        split_lon=1,
    )
