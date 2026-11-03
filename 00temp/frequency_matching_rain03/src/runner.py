# -*- coding: utf-8 -*-
"""
逐 3 小时单模式降水频率匹配订正主程序（``src/runner.py``）。

历史相似个例（TS+Bias）→ 分位频率匹配 →（时效 ``<=0`` 时）光流平流
→ Cressman 上格点 → 再 FM。时效默认 3–252 h、步长 3。

调用::

    from runner import process
    process(data_key="ecmwf", run_times=["202605220800"])

    python -m cli ecmwf 202605220800
    python src/runner.py ecmwf 202605220800
"""
from __future__ import annotations

import sys
import os
import time
import json
import traceback
import subprocess
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


def _bootstrap_paths():
    _src = Path(__file__).resolve().parent
    _root = _src.parent
    for p in (str(_root), str(_src)):
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed((str(_root), str(_src))):
        sys.path.insert(0, p)


_bootstrap_paths()

from utils.types import (
    ConfigureData, ScatterData, GridData, PointData, LineData, FileFlag
)
from proc import (
    StringProcess, FrequencyMatch, Ensemble, SpatialAnalisis,
    OpticalFlow, RainExtrapolation
)
from utils.log import Log
from utils.util_env import get_resolved_paths
from utils.util_paths import REPO_ROOT
from utils.io_meb import expand_data_path, find_grid_file, find_sta_file


def _is_datetime_token(token: str) -> bool:
    """起报时刻：``YYYYMMDDHH``（10 位）或 ``YYYYMMDDHHMM``（12 位）。"""
    s = str(token).strip()
    return s.isdigit() and len(s) in (10, 12)


def _parse_run_datetime(token: str) -> datetime:
    """把 10/12 位数字串解析为 ``datetime``；10 位按整点（分钟为 0）。"""
    s = str(token).strip()
    if len(s) == 10 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d%H")
    if len(s) == 12 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d%H%M")
    raise ValueError(f"unsupported datetime token: {token}")


def _load_path_configs(base: Path, log: Log):
    """读 ``path.json``，返回 ``{key: {model,fact,output}_template}`` 与 ``default`` 键。"""
    paths = get_resolved_paths()
    path_json = Path(paths["path_json"])
    if not path_json.exists():
        log.write_error("Path Json File Is Not Exist!", 1)
        raise RuntimeError("Path Json File Is Not Exist!")
    try:
        payload = json.loads(path_json.read_text(encoding="utf-8"))
    except Exception as exc:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!") from exc
    default_key = None
    raw_configs = {}
    if isinstance(payload, dict) and isinstance(payload.get("configs"), dict):
        raw_configs = payload["configs"]
        if isinstance(payload.get("default"), str):
            default_key = payload["default"]
    elif isinstance(payload, dict):
        raw_configs = payload
    else:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!")
    configs = {}
    for key, cfg in raw_configs.items():
        if not isinstance(cfg, dict):
            continue
        mt = cfg.get("model_template")
        ft = cfg.get("fact_template")
        ot = cfg.get("output_template")
        if all(isinstance(v, str) and v.strip() for v in [mt, ft, ot]):
            configs[str(key)] = {
                "model_template": mt.strip(),
                "fact_template": ft.strip(),
                "output_template": ot.strip(),
            }
    if not configs:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!")
    return configs, default_key


def _select_data_key_and_runtimes(args, configs, default_key, log):
    """从 argv 解析模式键与起报：0/1/2 个 ``YYYYMMDDHH`` 或 ``YYYYMMDDHHMM``。"""
    data_key = None
    date_args = []
    for token in args:
        if _is_datetime_token(token):
            date_args.append(token)
        elif data_key is None and not token.startswith("--"):
            data_key = token.strip()
        else:
            log.write_error(f"Args Is Not Right! token={token}", 1)
            raise RuntimeError("Args Is Not Right!")
    if data_key is None or not data_key:
        if default_key and default_key in configs:
            data_key = default_key
        elif len(configs) == 1:
            data_key = next(iter(configs.keys()))
        else:
            log.write_error("Data Key Is Not Specified!", 1)
            raise RuntimeError("Data Key Is Not Specified!")
    para = configs.get(data_key)
    if para is None:
        log.write_error(f"Data Key Is Not Exist! key={data_key}", 1)
        raise RuntimeError(f"Data Key Is Not Exist! key={data_key}")
    if not date_args:
        log.write_info("未指定起报时间，使用当前系统时间", 1)
        run_dts = [datetime.now()]
    elif len(date_args) == 1:
        try:
            run_dts = [_parse_run_datetime(date_args[0])]
        except ValueError:
            log.write_error("Date Args Content Is Not Right!", 1)
            raise RuntimeError("Date Args Content Is Not Right!")
    elif len(date_args) == 2:
        try:
            t1 = _parse_run_datetime(date_args[0])
            t2 = _parse_run_datetime(date_args[1])
        except ValueError:
            log.write_error("Date Args Content Is Not Right!", 1)
            raise RuntimeError("Date Args Content Is Not Right!")
        if t1 > t2:
            log.write_error("Date Args Range Is Not Right!", 1)
            raise RuntimeError("Date Args Range Is Not Right!")
        run_dts = []
        current = t1
        while current <= t2:
            run_dts.append(current)
            current += timedelta(hours=1)
    else:
        log.write_error("Date Args Number Is Not Right!", 1)
        raise RuntimeError("Date Args Number Is Not Right!")
    return para, run_dts, data_key


def _load_grid_config(base: Path, log: Log):
    """读 ``config.json`` 的中心区与分辨率；缺省 70–140°E、0–60°N、0.1°、外扩 1°。"""
    cfg = ConfigureData()
    cfg.center_lon_left = 70.0
    cfg.center_lon_right = 140.0
    cfg.center_lat_bottom = 0.0
    cfg.center_lat_top = 60.0
    cfg.dlon = 0.1
    cfg.dlat = 0.1
    cfg.lonlat_ext = 1.0
    paths = get_resolved_paths()
    config_path = Path(paths["config_json"])
    if not config_path.exists():
        log.write_info("config.json not found, using default grid config", 0)
        return cfg
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.write_error(f"Failed to read config.json: {e}, using defaults", 1)
        return cfg
    if not isinstance(raw, dict):
        return cfg
    grid = raw.get("grid", raw)
    if not isinstance(grid, dict):
        return cfg
    cfg.center_lon_left = float(grid.get("lon_start", cfg.center_lon_left))
    cfg.center_lon_right = float(grid.get("lon_end", cfg.center_lon_right))
    cfg.center_lat_bottom = float(grid.get("lat_start", cfg.center_lat_bottom))
    cfg.center_lat_top = float(grid.get("lat_end", cfg.center_lat_top))
    cfg.dlon = float(grid.get("dlon", cfg.dlon))
    cfg.dlat = float(grid.get("dlat", cfg.dlat))
    cfg.lonlat_ext = float(grid.get("expand", cfg.lonlat_ext))
    log.write_info("config.json loaded successfully", 0)
    return cfg


_MASK_LON_START = 70.0
_MASK_LON_END = 140.0
_MASK_LAT_START = 0.0
_MASK_LAT_END = 60.0
_MASK_RESOLUTIONS = (0.01, 0.05, 0.1)


def _mask_shape_for_resolution(resolution):
    xn = int(round((_MASK_LON_END + 1e-05 - _MASK_LON_START) / resolution)) + 1
    yn = int(round((_MASK_LAT_END + 1e-05 - _MASK_LAT_START) / resolution)) + 1
    return xn, yn


def _load_mask_grid(mask_path, preferred_resolution):
    mask_path = Path(mask_path)
    byte_size = mask_path.stat().st_size
    if byte_size % 4 != 0:
        raise RuntimeError(f"Mask file byte size is not a float32 grid: {mask_path}")

    value_count = byte_size // 4
    resolutions = [preferred_resolution]
    resolutions.extend(res for res in _MASK_RESOLUTIONS if abs(res - preferred_resolution) >= 1e-10)

    for resolution in resolutions:
        xn, yn = _mask_shape_for_resolution(resolution)
        if xn * yn == value_count:
            gd_mask = GridData(
                _MASK_LON_START, _MASK_LON_END,
                _MASK_LAT_START, _MASK_LAT_END,
                resolution, resolution)
            gd_mask.read_float_val_from_bin(str(mask_path))
            return gd_mask

    expected = ", ".join(
        f"{res:g}deg={_mask_shape_for_resolution(res)[0] * _mask_shape_for_resolution(res)[1]}"
        for res in _MASK_RESOLUTIONS)
    raise RuntimeError(
        f"Mask file size does not match supported full-grid masks: {mask_path}; "
        f"values={value_count}; expected {expected}")


def _build_forecast_tasks(run_dts):
    """每个起报回溯 0–24 h 再减 8 h，与时效 3–252（步长 3）做成任务表。"""
    num = 24  # 回溯小时数（再减 8 h 对齐北京时）
    cycles = list(dict.fromkeys(
        run_dt - timedelta(hours=h + 8) for run_dt in run_dts for h in range(num + 1)
    ))
    return [
        (date_time, predict_valid)
        for date_time in cycles
        for predict_valid in range(3, 252 + 1, 3)
    ]


def _get_single_task_from_env():
    date_token = os.environ.get("QPF_SINGLE_TASK_DATE")
    valid_token = os.environ.get("QPF_SINGLE_PREDICT_VALID")
    if not date_token and not valid_token:
        return None
    if not date_token or not valid_token:
        raise RuntimeError("QPF single-task environment is incomplete")
    return datetime.strptime(date_token, "%Y%m%d%H"), int(valid_token)


def _get_lead_time_worker_count(task_count):
    if task_count <= 1:
        return 1
    env_value = os.environ.get("QPF_LEADTIME_WORKERS")
    if env_value:
        try:
            return max(1, min(task_count, int(env_value)))
        except ValueError:
            pass
    return max(1, min(task_count, 8))


def _task_result(status, desc):
    return {"status": status, "desc": desc}


def _add_task_result(summary, result):
    summary["total"] += 1
    status = result.get("status") if isinstance(result, dict) else None
    if status in ("success", "skip", "fail"):
        summary[status] += 1
    else:
        summary["fail"] += 1


def _execute_forecast_tasks(tasks, max_workers, task_runner=None, executor_cls=None):
    task_runner = task_runner or _run_single_task_subprocess
    executor_cls = executor_cls or ThreadPoolExecutor
    summary = {"total": 0, "success": 0, "skip": 0, "fail": 0}

    if max_workers <= 1:
        for task in tasks:
            try:
                _add_task_result(summary, task_runner(task))
            except Exception:
                _add_task_result(summary, _task_result("fail", str(task)))
        return summary

    with executor_cls(max_workers=max_workers) as executor:
        futures = [executor.submit(task_runner, task) for task in tasks]
        for future in futures:
            try:
                _add_task_result(summary, future.result())
            except Exception:
                _add_task_result(summary, _task_result("fail", "worker exception"))
    return summary


def _child_datetime_args(run_dts):
    if not run_dts:
        return []
    if len(run_dts) == 1:
        return [run_dts[0].strftime("%Y%m%d%H%M")]
    return [run_dts[0].strftime("%Y%m%d%H%M"), run_dts[-1].strftime("%Y%m%d%H%M")]


def _run_single_task_subprocess(task):
    env = os.environ.copy()
    env["QPF_DISABLE_LEADTIME_MP"] = "1"
    env["QPF_SINGLE_TASK_DATE"] = task["date_time"].strftime("%Y%m%d%H")
    env["QPF_SINGLE_PREDICT_VALID"] = str(task["predict_valid"])

    completed = subprocess.run(
        [sys.executable, task["script_path"], *task["argv"]],
        cwd=task["cwd"],
        env=env,
        check=False)

    desc = task["desc"]
    if completed.returncode == 0:
        return _task_result("success", desc)
    if completed.returncode == 3:
        return _task_result("skip", desc)
    return _task_result("fail", desc)


def _describe_task_io(model_tpl, output_tpl, date_time, predict_valid):
    """展开输出/模式路径，无后缀时尝试 ``.m4`` / ``.nc``。"""
    desc = StringProcess.date_replace("YYYYMMDDHH_VVV", date_time, predict_valid)
    out_m3 = expand_data_path(output_tpl + ".m3", date_time, predict_valid)
    out_m4 = expand_data_path(output_tpl + ".m4", date_time, predict_valid)
    model_raw, model_path = find_grid_file(model_tpl, date_time, predict_valid)
    return {
        "desc": desc,
        "out_m3": out_m3,
        "out_m4": out_m4,
        "model_raw": model_raw,
        "model_path": model_path,
        "output_exists": os.path.exists(out_m3) and os.path.exists(out_m4),
        "model_missing": model_path is None,
    }


def _run_parallel_lead_time_tasks(script_path, cwd, argv, tasks, text2, text4, log):
    summary = {"total": len(tasks), "success": 0, "skip": 0, "fail": 0}
    runnable_tasks = []
    missing_examples = []

    for date_time, predict_valid in tasks:
        io_info = _describe_task_io(text2, text4, date_time, predict_valid)
        desc = io_info["desc"]
        path2 = io_info["out_m3"]
        path3 = io_info["out_m4"]
        path4 = io_info["model_path"] or io_info["model_raw"]

        if io_info["output_exists"] or io_info["model_missing"]:
            if io_info["output_exists"]:
                log.write_info(f"[SKIP] {desc}: output files already exist", 0)
            else:
                log.write_info(f"[SKIP] {desc}: model input not found: {io_info['model_raw']}", 0)
                if len(missing_examples) < 3:
                    missing_examples.append(io_info["model_raw"])
            summary["skip"] += 1
            continue

        runnable_tasks.append({
            "script_path": script_path,
            "cwd": cwd,
            "argv": argv,
            "date_time": date_time,
            "predict_valid": predict_valid,
            "desc": desc,
        })

    if missing_examples:
        log.write_info(
            f"[SKIP] {summary['skip']} tasks missing model input, e.g. {missing_examples[0]} "
            f"(also tried .m4/.nc)",
            1)

    max_workers = _get_lead_time_worker_count(len(runnable_tasks))
    log.write_info(f"Lead-time subprocess workers: {max_workers}", 1)
    run_summary = _execute_forecast_tasks(runnable_tasks, max_workers=max_workers)
    summary["success"] += run_summary["success"]
    summary["skip"] += run_summary["skip"]
    summary["fail"] += run_summary["fail"]
    return summary


def process(data_key=None, run_times=None):
    """
    可调度入口。未传项回落 ``path.json`` 的 ``default`` 与当前时刻。

    参数
    ----
    data_key : str, optional
        ``resource/path.json`` 中的模式键（如 ``ecmwf``）。
    run_times : sequence, optional
        起报时刻（``datetime`` 或 ``YYYYMMDDHH`` / ``YYYYMMDDHHMM``）；两个时刻表示闭区间按小时展开。
    """
    argv = []
    if data_key:
        argv.append(str(data_key))
    if run_times:
        if not isinstance(run_times, (list, tuple)):
            run_times = [run_times]
        for t in run_times:
            if isinstance(t, datetime):
                argv.append(t.strftime("%Y%m%d%H%M"))
            else:
                argv.append(str(t))
    return main(argv)


def main(argv=None):
    """命令行主循环：解析配置 → 时效并行或单任务 → 相似 / FM / Cressman → 写盘。"""
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print("+++++   03 Hour Rain Forecast V2021          +++++++++")
    print("+++++  Created By CaoYong 2021.05.07         +++++++++")
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")

    if argv is None:
        argv = sys.argv[1:]

    start_time = time.time()
    paths = get_resolved_paths()
    base = REPO_ROOT
    base_dir = str(base) + os.sep
    log_tpl = str(paths["log_file_template"])
    log = Log(expand_data_path(log_tpl, datetime.now(), 0))

    # 统计计数器
    total_tasks = 0
    success_tasks = 0
    skip_tasks = 0
    fail_tasks = 0
    missing_logged = 0

    # ---------- 参数解析 & 配置读取 ----------
    configs, default_key = _load_path_configs(base, log)
    para, run_dts, data_key = _select_data_key_and_runtimes(argv, configs, default_key, log)
    configure_data = _load_grid_config(base, log)

    text2 = para["model_template"]
    text3 = para["fact_template"]
    text4 = para["output_template"]

    log.write_info(f"model_template: {text2}", 0)
    log.write_info(f"fact_template: {text3}", 0)
    log.write_info(f"output_template: {text4}", 0)

    log.write_info(
        f"Region: lon=[{configure_data.center_lon_left}, {configure_data.center_lon_right}], "
        f"lat=[{configure_data.center_lat_bottom}, {configure_data.center_lat_top}], "
        f"dlon={configure_data.dlon}, dlat={configure_data.dlat}, ext={configure_data.lonlat_ext}", 0)

    single_task = _get_single_task_from_env()
    if single_task is None and os.environ.get("QPF_DISABLE_LEADTIME_MP") != "1":
        tasks = _build_forecast_tasks(run_dts)
        child_argv = [data_key, *_child_datetime_args(run_dts)]
        task_summary = _run_parallel_lead_time_tasks(
            str(Path(__file__).resolve()), str(REPO_ROOT), child_argv, tasks, text2, text4, log)

        elapsed = time.time() - start_time
        summary = (
            f"==========================================\n"
            f"Run finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Total tasks: {task_summary['total']}\n"
            f"  Success: {task_summary['success']}\n"
            f"  Skipped: {task_summary['skip']}\n"
            f"  Failed:  {task_summary['fail']}\n"
            f"Time elapsed: {elapsed / 60.0:.1f} min ({elapsed:.1f} sec)\n"
            f"=========================================="
        )
        log.write_info(summary, 1)
        print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        return

    # 读取站点信息
    sta_info_path = str(paths["station_info"])
    # print("=-------------------------->>>> sta_info_path: ", sta_info_path)
    if not os.path.exists(sta_info_path):
        msg = f"Station info file not found: {sta_info_path}"
        log.write_error(msg, 1)
        raise Exception(msg)
    try:
        sd_sta_info = ScatterData(sta_info_path, FileFlag.stainfo)
        log.write_info(f"Loaded {sd_sta_info.length} stations from sta.info", 0)
    except Exception as e:
        log.write_error(f"Failed to read sta.info: {traceback.format_exc()}", 1)
        raise

    sd_sta_info = sd_sta_info.frame_by_line(LineData(
        [configure_data.large_lon_left, configure_data.large_lon_right,
         configure_data.large_lon_right, configure_data.large_lon_left],
        [configure_data.large_lat_bottom, configure_data.large_lat_bottom,
         configure_data.large_lat_top, configure_data.large_lat_top]))
    log.write_info(f"Stations in large region: {sd_sta_info.length}", 0)

    # 读取掩膜 — 根据分辨率选择对应的 mask 文件（resource/）
    resource_dir = Path(paths["mask_file"]).parent
    _mask_res = configure_data.dlon
    if abs(_mask_res - 0.01) < 0.001:
        mask_file = "mask001.dat"
    elif abs(_mask_res - 0.05) < 0.001:
        mask_file = "mask005.dat"
    else:
        mask_file = "mask010.dat"

    mask_path = str(resource_dir / mask_file)
    # print("=-------------------------->>>> mask_path: ", mask_path)
    if not os.path.exists(mask_path):
        log.write_info(f"{mask_file} not found, fallback to mask010.dat", 0)
        mask_path = str(paths["mask_file"])
    if not os.path.exists(mask_path):
        msg = f"Mask file not found: {mask_path}"
        log.write_error(msg, 1)
        raise Exception(msg)
    try:
        gd_mask = _load_mask_grid(mask_path, configure_data.dlon)
        log.write_info(
            f"Mask loaded ({mask_file}): {gd_mask.xn}x{gd_mask.yn}, "
            f"range=lon[{_MASK_LON_START}, {_MASK_LON_END}], "
            f"lat[{_MASK_LAT_START}, {_MASK_LAT_END}], "
            f"dlon={gd_mask.d_lon}, dlat={gd_mask.d_lat}", 0)
    except Exception as e:
        log.write_error(f"Failed to read {mask_file}: {traceback.format_exc()}", 1)
        raise

    num = 24
    cycles = list(dict.fromkeys(
        run_dt - timedelta(hours=h + 8) for run_dt in run_dts for h in range(num + 1)
    ))
    if single_task is not None:
        cycles = [single_task[0]]
    # 单时效：读当前场 → 历史窗 → 相似/FM → 写 m3 → Cressman/FM → 写 m4
    for date_time in cycles:
        num2 = 3
        num3 = 3
        num4 = 3
        num5 = 252

        predict_valids = [single_task[1]] if single_task is not None else range(num4, num5 + 1, num3)
        for predict_valid in predict_valids:
            total_tasks += 1
            task_desc = StringProcess.date_replace(
                "YYYYMMDDHH_VVV", date_time, predict_valid)

            task_start_time = time.time()
            try:
                io_info = _describe_task_io(text2, text4, date_time, predict_valid)
                path2 = io_info["out_m3"]
                path3 = io_info["out_m4"]
                path4 = io_info["model_path"] or io_info["model_raw"]

                if io_info["output_exists"] or io_info["model_missing"]:
                    if io_info["output_exists"]:
                        log.write_info(f"[SKIP] {task_desc}: output files already exist", 0)
                    else:
                        missing_logged += 1
                        log.write_info(
                            f"[SKIP] {task_desc}: model input not found: {io_info['model_raw']}",
                            1 if missing_logged <= 3 else 0)
                    skip_tasks += 1
                    continue

                log.write_info(f"[START] {task_desc}", 1)

                print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
                print(StringProcess.date_replace(
                    "Process Model Time Is: YYYYMMDDHH_VVV", date_time, predict_valid))
                print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
                print("Read the Currect ModelData...")

                dt_input = date_time
                text6 = io_info["model_path"]
                print("Current Model Data: " + text6)
                log.write_info(f"Current model: {text6}", 0)

                gd_current_model = None
                try:
                    gd_current_model = GridData(text6)
                    log.write_info(f"Model grid: {gd_current_model.xn}x{gd_current_model.yn}", 0)
                except Exception as ex:
                    log.write_error(
                        f"[FAIL] {task_desc}: cannot read model data {text6}\n"
                        f"{traceback.format_exc()}", 1)
                    fail_tasks += 1
                    continue

                gd_current_model = gd_current_model.mesh_val(
                    configure_data.large_lon_left, configure_data.large_lon_right,
                    configure_data.large_lat_bottom, configure_data.large_lat_top,
                    configure_data.dlon, configure_data.dlat)
                log.write_info(
                    f"Current model after mesh: max={gd_current_model.max_value():.3f} "
                    f"n>=10={int((gd_current_model.val >= 10).sum())} "
                    f"n>=25={int((gd_current_model.val >= 25).sum())} "
                    f"n>=50={int((gd_current_model.val >= 50).sum())}", 0)

                print("Read the History ModelData...")
                num6 = 15  # 同期窗半径（天）
                num7 = 4   # 回溯年数（当年 + 往 3 年）
                ltgd_model_raw = []
                ltsd_fact = []

                hist_found = 0
                hist_missing = 0
                hist_bad = 0

                for j in range(num7):
                    date_time2 = date_time
                    date_time3 = date_time
                    if j == 0:
                        date_time2 = date_time - timedelta(days=365 * j) - timedelta(days=num6)
                        date_time3 = date_time - timedelta(days=365 * j) - timedelta(days=1)
                    else:
                        date_time2 = date_time - timedelta(days=365 * j) - timedelta(days=num6)
                        date_time3 = date_time - timedelta(days=365 * j) + timedelta(days=num6)

                    date_time4 = date_time2
                    while date_time4 <= date_time3:
                        dt_input2 = date_time4 + timedelta(hours=predict_valid)
                        text7_raw, text7 = find_grid_file(text2, date_time4, predict_valid)
                        text8_raw, text8 = find_sta_file(text3, dt_input2, 0)

                        if text7 and text8:
                            if date_time4 == date_time2 or date_time4 == date_time3:
                                print("dtModel: " + text7)
                                print("dtFact: " + text8)
                            try:
                                grid_data = GridData(text7)
                                grid_data = grid_data.mesh_val(
                                    configure_data.large_lon_left, configure_data.large_lon_right,
                                    configure_data.large_lat_bottom, configure_data.large_lat_top,
                                    configure_data.dlon, configure_data.dlat)
                                scatter_data = sd_sta_info.copy_scatter_data()
                                scatter_data.read_val_from_micaps3(text8)
                                scatter_data.clear_to_num_greater_than(0.0, 500.0)
                                scatter_data.clear_to_num_less_than(0.0, 0.0)
                                ltgd_model_raw.append(grid_data)
                                ltsd_fact.append(scatter_data)
                                hist_found += 1
                            except Exception:
                                print("bad dtModel: " + text7)
                                print("bad dtFact: " + text8)
                                log.write_error(
                                    f"[BAD_DATA] {task_desc}: year={j}, date={date_time4.strftime('%Y%m%d')}\n"
                                    f"  dtModel={text7}\n  dtFact={text8}\n"
                                    f"  {traceback.format_exc()}", 0)
                                hist_bad += 1
                        else:
                            missing_files = []
                            if text7 is None:
                                missing_files.append(f"model={text7_raw}")
                                hist_missing += 1
                            if text8 is None:
                                missing_files.append(f"fact={text8_raw}")
                                hist_missing += 1
                            if missing_files:
                                log.write_info(
                                    f"[MISSING] {task_desc}: year={j}, date={date_time4.strftime('%Y%m%d')} | "
                                    f"{', '.join(missing_files)}", 0)
                            if date_time4 == date_time2 or date_time4 == date_time3:
                                print("lack dtModel: " + (text7 or text7_raw))
                                print("lack dtFact: " + (text8 or text8_raw))

                        date_time4 = date_time4 + timedelta(days=1)

                fact_max = max((sd.max_value() for sd in ltsd_fact), default=0.0)
                log.write_info(
                    f"History data for {task_desc}: found={hist_found}, missing={hist_missing}, "
                    f"bad={hist_bad}, fact_max={fact_max:.3f}", 0)

                dy_n_used = len(ltgd_model_raw)
                if dy_n_used <= 0:
                    log.write_error(f"[FAIL] {task_desc}: no history data used! (found=0)", 1)
                    fail_tasks += 1
                    continue

                gd_train_model = [None] * dy_n_used
                gd_train_model_smooth = [None] * dy_n_used
                sd_train_fact = [None] * dy_n_used
                print("dyused: " + str(dy_n_used))

                smooth_num = 30  # 历史场 9 点平滑次数
                # 并行化历史成员处理 (匹配C# Parallel.For, scipy/numpy操作会释放GIL)
                def _process_history_member(n):
                    try:
                        m = ltgd_model_raw[n].copy_grid_data()
                        ms = ltgd_model_raw[n].copy_grid_data()
                        ms.smooth9(smooth_num)
                        f = ltsd_fact[n].copy_scatter_data()
                        return n, m, ms, f, None
                    except Exception as e:
                        return n, None, None, None, traceback.format_exc()

                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [executor.submit(_process_history_member, n) for n in range(dy_n_used)]
                    for future in futures:
                        n, m, ms, f, err = future.result()
                        if err is not None:
                            log.write_error(
                                f"[WARN] {task_desc}: history member {n} processing failed\n{err}", 0)
                            gd_train_model[n] = ltgd_model_raw[n].copy_grid_data()
                            gd_train_model_smooth[n] = ltgd_model_raw[n].copy_grid_data()
                            sd_train_fact[n] = ltsd_fact[n].copy_scatter_data()
                        else:
                            gd_train_model[n] = m
                            gd_train_model_smooth[n] = ms
                            sd_train_fact[n] = f

                gd_current_model_smooth = gd_current_model.copy_grid_data()

                fact_level = [0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0,
                              30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 500.0]
                similar_level = [25.0, 50.0]  # TS+Bias 量级

                scatter_data2 = None

                if predict_valid <= 0:
                    # 细粒度分块：将配置区域按约5°切分
                    _lon_edges = np.arange(
                        configure_data.center_lon_left,
                        configure_data.center_lon_right + 0.001, 5.0).tolist()
                    _lat_edges = np.arange(
                        configure_data.center_lat_bottom,
                        configure_data.center_lat_top + 0.001, 5.0).tolist()
                    center_lon_left = _lon_edges[:-1]
                    center_lon_right = _lon_edges[1:]
                    center_lat_bottom = _lat_edges[:-1]
                    center_lat_top = _lat_edges[1:]
                else:
                    center_lon_left = [configure_data.center_lon_left]
                    center_lon_right = [configure_data.center_lon_right]
                    center_lat_bottom = [configure_data.center_lat_bottom]
                    center_lat_top = [configure_data.center_lat_top]

                num8 = configure_data.lonlat_ext
                large_lon_left = [cl - num8 for cl in center_lon_left]
                large_lon_right = [cr + num8 for cr in center_lon_right]
                large_lat_bottom = [cb - num8 for cb in center_lat_bottom]
                large_lat_top = [ct + num8 for ct in center_lat_top]

                dlon = configure_data.dlon
                dlat = configure_data.dlat

                sd_correct_model = {}
                sub_region_count = 0

                # Precompute the mask meshed to the large region (same for all sub-regions)
                gd_mask_large = gd_mask.copy_grid_data()
                gd_mask_large = gd_mask_large.mesh_val(
                    configure_data.large_lon_left, configure_data.large_lon_right,
                    configure_data.large_lat_bottom, configure_data.large_lat_top,
                    configure_data.dlon, configure_data.dlat)

                for jy in range(len(center_lat_bottom)):
                    for ix in range(len(center_lon_left)):
                        db_lon2 = [center_lon_left[ix], center_lon_right[ix],
                                   center_lon_right[ix], center_lon_left[ix]]
                        db_lat2 = [center_lat_bottom[jy], center_lat_bottom[jy],
                                   center_lat_top[jy], center_lat_top[jy]]
                        scatter_data7 = sd_sta_info.frame_by_line(LineData(db_lon2, db_lat2))

                        db_lon3 = [large_lon_left[ix], large_lon_right[ix],
                                   large_lon_right[ix], large_lon_left[ix]]
                        db_lat3 = [large_lat_bottom[jy], large_lat_bottom[jy],
                                   large_lat_top[jy], large_lat_top[jy]]
                        sd_sta_info_train = sd_sta_info.frame_by_line(LineData(db_lon3, db_lat3))

                        if scatter_data7.length > 0:
                            print(f"jy: {jy} ix: {ix}")
                            sub_region_count += 1

                            try:
                                arr = [None] * dy_n_used
                                for k in range(dy_n_used):
                                    arr[k] = gd_train_model_smooth[k].copy_grid_data()
                                    arr[k].mask_val(gd_mask_large, 0.0)
                                    arr[k] = arr[k].mesh_val(
                                        large_lon_left[ix], large_lon_right[ix],
                                        large_lat_bottom[jy], large_lat_top[jy],
                                        5.0 * dlon, 5.0 * dlat)

                                grid_data5 = gd_current_model_smooth.copy_grid_data()
                                grid_data5.mask_val(gd_mask_large, 0.0)
                                grid_data5 = grid_data5.mesh_val(
                                    large_lon_left[ix], large_lon_right[ix],
                                    large_lat_bottom[jy], large_lat_top[jy],
                                    5.0 * dlon, 5.0 * dlat)

                                # 粗网格上按 TS+Bias 排序历史个例
                                index = Ensemble.get_similarity_index_by_ts_and_bias(
                                    arr, grid_data5, dy_n_used, similar_level)

                                num18 = 0
                                num19 = 0.0
                                num20 = 2.4  # 评分累加截断
                                for l in range(len(index[0])):
                                    num19 += index[1][l]
                                    num18 += 1
                                    if num19 > num20:
                                        break

                                num21 = min(20, num18)
                                num22 = max(int(0.5 * dy_n_used), num18)

                                gd_sentive_model = [None] * num22
                                sd_sentive_model = [None] * num22
                                sd_sentive_fact = [None] * num22

                                for n in range(num22):
                                    gd_sentive_model[n] = gd_train_model_smooth[int(index[0][n])].mesh_val(
                                        large_lon_left[ix], large_lon_right[ix],
                                        large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                                    sd_sentive_model[n] = sd_sta_info_train.copy_scatter_data()
                                    sd_sentive_model[n].bilinear_interpolation_from_grid_data(
                                        gd_sentive_model[n])
                                    sd_sentive_fact[n] = sd_sta_info_train.copy_scatter_data()
                                    sd_sentive_fact[n].read_from_sactter_data(
                                        sd_train_fact[int(index[0][n])])

                                # 相似个例站点场建分位映射（两端各丢 5 个样本）
                                used_model_level_and_extend2 = FrequencyMatch.get_used_model_level_and_extend(
                                    sd_sentive_model, sd_sentive_fact, fact_level, 5)
                                log.write_info(
                                    f"Subregion FM levels={len(used_model_level_and_extend2[0])} "
                                    f"model={used_model_level_and_extend2[0]} "
                                    f"fact={used_model_level_and_extend2[1]}", 0)

                                grid_data6 = gd_current_model_smooth.mesh_val(
                                    large_lon_left[ix], large_lon_right[ix],
                                    large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)

                                grid_data7 = grid_data6.copy_grid_data()
                                if len(used_model_level_and_extend2[0]) < 2:
                                    grid_data7 = gd_current_model.mesh_val(
                                        large_lon_left[ix], large_lon_right[ix],
                                        large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                                else:
                                    grid_data7 = FrequencyMatch.correct_model_data(
                                        grid_data6, used_model_level_and_extend2[1],
                                        used_model_level_and_extend2[0])

                                # 仅时效<=0：光流反演 + 半拉格朗日（默认 3–252 不进入）
                                if predict_valid <= 0:
                                    array2 = [
                                        GridData(large_lon_left[ix], large_lon_right[ix],
                                                 large_lat_bottom[jy], large_lat_top[jy], dlon, dlat),
                                        GridData(large_lon_left[ix], large_lon_right[ix],
                                                 large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                                    ]
                                    num22_opt = num21
                                    array3 = [None] * num22_opt
                                    array4 = [None] * num22_opt

                                    for num23 in range(num22_opt):
                                        array3[num23] = gd_train_model[int(index[0][num23])].copy_grid_data()
                                        sd_input_data = sd_train_fact[int(index[0][num23])].copy_scatter_data()
                                        array4[num23] = SpatialAnalisis.gress_man_interpolation_for_rain(
                                            sd_input_data, array3[num23],
                                            [1.0, 0.8, 0.6, 0.4])
                                        array3[num23].smooth9(smooth_num)
                                        array3[num23] = array3[num23].mesh_val(
                                            large_lon_left[ix], large_lon_right[ix],
                                            large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                                        array4[num23].smooth9(smooth_num)
                                        array4[num23] = array4[num23].mesh_val(
                                            large_lon_left[ix], large_lon_right[ix],
                                            large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)

                                        used_model_level_and_extend3 = FrequencyMatch.get_used_model_level_and_extend(
                                            [array3[num23]], [array4[num23]], fact_level)
                                        if len(used_model_level_and_extend3[0]) >= 2:
                                            array3[num23] = FrequencyMatch.correct_model_data(
                                                array3[num23], used_model_level_and_extend3[1],
                                                used_model_level_and_extend3[0])

                                        array4[num23] = array4[num23].mesh_val(
                                            large_lon_left[ix], large_lon_right[ix],
                                            large_lat_bottom[jy], large_lat_top[jy],
                                            1.0 * dlon, 1.0 * dlat)
                                        array3[num23] = array3[num23].mesh_val(
                                            large_lon_left[ix], large_lon_right[ix],
                                            large_lat_bottom[jy], large_lat_top[jy],
                                            1.0 * dlon, 1.0 * dlat)

                                    array2[0] = array3[0].copy_grid_data()
                                    array2[1] = array3[0].copy_grid_data()
                                    array2[0].clear_to_num(0.0)
                                    array2[1].clear_to_num(0.0)

                                    min_window = [[5.0, 5.0]]
                                    OpticalFlow.get_wind_from_optical_flow(
                                        array3, array4, min_window, array2, 25.0, 0.1, 50)

                                    array2[0] = array2[0].mesh_val(
                                        large_lon_left[ix], large_lon_right[ix],
                                        large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                                    array2[1] = array2[1].mesh_val(
                                        large_lon_left[ix], large_lon_right[ix],
                                        large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)

                                    grid_data8 = grid_data7.copy_grid_data()
                                    min_val = 10.0
                                    max_val = 25.0
                                    grid_data8.standardize_by_max_min(min_val, max_val)
                                    gd_u_wnd = array2[0].multi_val_form_new_grid_data(grid_data8)
                                    gd_v_wnd = array2[1].multi_val_form_new_grid_data(grid_data8)

                                    grid_data7 = RainExtrapolation.simple_semi_lagrangian_in_angle(
                                        gd_u_wnd, gd_v_wnd, grid_data7, 1.0)

                                sd_correct_model[(ix, jy)] = scatter_data7.copy_scatter_data()
                                sd_correct_model[(ix, jy)].bilinear_interpolation_from_grid_data(
                                    grid_data7)
                                sd_correct_model[(ix, jy)].clear_to_num_less_than(0.0, 0.01)

                            except Exception as ex_sub:
                                log.write_error(
                                    f"[WARN] {task_desc}: sub-region (ix={ix}, jy={jy}) failed\n"
                                    f"  {traceback.format_exc()}", 0)

                log.write_info(
                    f"Sub-regions processed: {sub_region_count}/{len(center_lat_bottom) * len(center_lon_left)}", 0)

                db_lon = [center_lon_left[0],
                          center_lon_right[-1],
                          center_lon_right[-1],
                          center_lon_left[0]]
                db_lat = [center_lat_bottom[0],
                          center_lat_bottom[0],
                          center_lat_top[-1],
                          center_lat_top[-1]]
                scatter_data2 = sd_sta_info.frame_by_line(LineData(db_lon, db_lat))

                for jy in range(len(center_lat_bottom)):
                    for ix in range(len(center_lon_left)):
                        if (ix, jy) in sd_correct_model:
                            scatter_data2.read_from_sactter_data(sd_correct_model[(ix, jy)])

                # 输出站点数据（meb：sta_data → write_stadata_to_micaps3）
                scatter_data3 = scatter_data2.copy_scatter_data()
                text9 = expand_data_path(text4 + ".m3", date_time, predict_valid)
                print(text9)
                scatter_data3.clear_to_num_less_than(0.0, 0.01)
                try:
                    scatter_data3.writer_to_micaps3(
                        text9, dt_input=date_time, i_valid=predict_valid)
                    sta_max = scatter_data3.max_value() if scatter_data3.length else 0.0
                    log.write_info(
                        f"Output station data: {text9} max={sta_max:.3f} "
                        f"nsta={scatter_data3.length}", 0)
                except Exception as e:
                    log.write_error(
                        f"[FAIL] {task_desc}: cannot write .m3 file {text9}\n"
                        f"  {traceback.format_exc()}", 1)
                    fail_tasks += 1
                    continue

                # .m3raw 输出暂时关闭 — 原始模式插值到站点的数据，非核心产品
                # scatter_data4 = scatter_data3.copy_scatter_data()
                # scatter_data4.bilinear_interpolation_from_grid_data(gd_current_model)
                # str_header = StringProcess.date_replace(
                #     "diamond 3 YYYY年MM月DD日HH时VVV时效" + f"{num2:03d}" +
                #     "小时累积降水 00 01 04 08  -1 0 1 0 0",
                #     date_time, predict_valid)
                # text9 = StringProcess.date_replace(text4 + ".m3raw", date_time, predict_valid)
                # print(text9)
                # scatter_data4.clear_to_num_less_than(0.0, 0.01)
                # scatter_data4.writer_to_micaps3(text9, str_header)
                # log.write_info(f"Output raw station data: {text9}", 0)

                print("Output The Correct GridData...")
                grid_data2 = gd_current_model.mesh_val(
                    configure_data.center_lon_left, configure_data.center_lon_right,
                    configure_data.center_lat_bottom, configure_data.center_lat_top,
                    configure_data.dlon, configure_data.dlat)
                gd_mask_mesh = gd_mask.mesh_val(
                    configure_data.center_lon_left, configure_data.center_lon_right,
                    configure_data.center_lat_bottom, configure_data.center_lat_top,
                    configure_data.dlon, configure_data.dlat)

                # 掩膜<0 视为境外：每 5 点抽背景当伪站
                lst_points = []
                for num15 in range(0, gd_mask_mesh.yn, 5):
                    for num16 in range(0, gd_mask_mesh.xn, 5):
                        if gd_mask_mesh.val[num15, num16] < 0.0:
                            lst_points.append(PointData(
                                grid_data2.lon[num16], grid_data2.lat[num15],
                                grid_data2.val[num15, num16]))

                for num17 in range(scatter_data3.length):
                    lst_points.append(scatter_data3.sta_data[num17].copy_point_data())

                scatter_data5 = ScatterData(lst_points)
                print("sta num for cressman: " + str(len(scatter_data5.sta_data)))
                log.write_info(f"Cressman input points: {len(scatter_data5.sta_data)}", 0)

                # 影响半径按经距的 8/6/4/2 倍逐步订正
                grid_data3 = SpatialAnalisis.gress_man_interpolation_for_rain(
                    scatter_data5, grid_data2,
                    [8.0 * configure_data.dlon, 6.0 * configure_data.dlon,
                     4.0 * configure_data.dlon, 2.0 * configure_data.dlon])
                grid_data3.smooth9(10)

                scatter_data6 = scatter_data3.copy_scatter_data()
                scatter_data6.bilinear_interpolation_from_grid_data(grid_data3)

                fact_level2 = [0.01, 0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0,
                               25.0, 30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0]

                used_model_level_and_extend = FrequencyMatch.get_used_model_level_and_extend(
                    [scatter_data6], [scatter_data3], fact_level2)

                if len(used_model_level_and_extend[0]) < 2:
                    grid_data3 = grid_data2.copy_grid_data()
                    log.write_info("Frequency match levels < 2, using original model data", 0)
                else:
                    grid_data3 = FrequencyMatch.correct_model_data(
                        grid_data3, used_model_level_and_extend[1],
                        used_model_level_and_extend[0])
                    log.write_info(f"Frequency match applied: {len(used_model_level_and_extend[0])} levels", 0)

                grid_data3.clear_to_num_less_than(0.0, 0.01)

                # meb：grid_data → write_griddata_to_micaps4 / write_griddata_to_nc
                text10 = expand_data_path(text4, date_time, predict_valid)
                m4_title = StringProcess.date_replace(
                    f"YYYYMMDDHH_VVV时效{num2:03d}小时降水预报场",
                    date_time, predict_valid)

                # .cybin 和 .m4raw 输出暂时关闭
                # grid_data3.write_val_to_cybin(text10 + ".cybin")
                try:
                    grid_data3.write_val_to_micaps4(
                        text10 + ".m4", title=m4_title,
                        dt_input=date_time, i_valid=predict_valid)
                    log.write_info(f"Output grid data: {text10}.m4", 0)
                except Exception as e:
                    log.write_error(
                        f"[FAIL] {task_desc}: cannot write .m4 file {text10}.m4\n"
                        f"  {traceback.format_exc()}", 1)
                # 同时保存 NC 格式
                try:
                    grid_data3.write_val_to_nc(text10 + ".nc", dt_input=dt_input, i_valid=predict_valid)
                    log.write_info(f"Output grid data: {text10}.nc", 0)
                except Exception as e:
                    log.write_error(
                        f"[FAIL] {task_desc}: cannot write .nc file {text10}.nc\n"
                        f"  {traceback.format_exc()}", 1)

                task_elapsed = time.time() - task_start_time
                success_tasks += 1
                log.write_info(f"[DONE] {task_desc}: completed in {task_elapsed:.1f}s", 1)

            except Exception as ex2:
                fail_tasks += 1
                task_elapsed = time.time() - task_start_time
                task_desc = StringProcess.date_replace(
                    "YYYYMMDDHH_VVV", date_time, predict_valid)
                log.write_error(
                    f"[FAIL] {task_desc}: unhandled exception after {task_elapsed:.1f}s\n"
                    f"  {traceback.format_exc()}", 1)

    elapsed = time.time() - start_time
    summary = (
        f"==========================================\n"
        f"Run finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Total tasks: {total_tasks}\n"
        f"  Success: {success_tasks}\n"
        f"  Skipped: {skip_tasks}\n"
        f"  Failed:  {fail_tasks}\n"
        f"Time elapsed: {elapsed / 60.0:.1f} min ({elapsed:.1f} sec)\n"
        f"=========================================="
    )
    log.write_info(summary, 1)
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    if single_task is not None:
        if fail_tasks > 0:
            raise SystemExit(2)
        if skip_tasks > 0 and success_tasks == 0:
            raise SystemExit(3)


if __name__ == "__main__":
    main()
