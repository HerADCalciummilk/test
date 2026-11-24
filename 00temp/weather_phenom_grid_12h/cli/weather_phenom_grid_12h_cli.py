# -*- coding: utf-8 -*-
"""网格天气现象综合电码。

``process`` 只排多个起报。一个起报在 ``_process``。
``pro_count>1`` 且起报多于 1 个时并行。显式 ``is_multi=False`` 强制串行。
"""
from __future__ import annotations

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _path in (str(_SRC), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from resource.data_schema import MAX_SEGMENTS
from src.processor import DEFAULT_OUTPUT_DIR, run_segment as _save_segment
from src.utils.data_loader import load_segment
from src.utils.output import print_stats
from src.weather_phenom_grid_12h_plugin import WeatherPhenomGrid12hPlugin
from utils.merge_params import merge_params
from utils.multipro_plugin import SimpleParallelTool

logger = logging.getLogger(__name__)


def _apply_env(data_root, numexpr_threads) -> None:
    if numexpr_threads is not None:
        os.environ["NUMEXPR_MAX_THREADS"] = str(numexpr_threads)
        os.environ["NUMEXPR_NUM_THREADS"] = str(numexpr_threads)
    if data_root is not None:
        os.environ["SCMOC_DATA_ROOT"] = str(data_root)


def _one_segment(init_time: str, seg_idx: int, output_dir: str, max_workers: int):
    data_dict, shape, lat_arr, lon_arr = load_segment(
        init_time, seg_idx, max_workers=max_workers
    )
    return _save_segment(
        data_dict, shape, lat_arr, lon_arr,
        init_time, seg_idx, output_dir=output_dir,
    )


def _run_init(
    init_time: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    seg_range: Optional[Tuple[int, int]] = None,
    max_seg_workers: int = 5,
    max_workers: int = 8,
) -> Dict[int, np.ndarray]:
    """线程池处理一个起报的各 12h 时段。"""
    s_start, s_end = seg_range if seg_range else (1, MAX_SEGMENTS)
    logger.info(
        f"{'=' * 55}\n"
        f"起报时次: {init_time}  时段: {s_start}~{s_end}  "
        f"时段并行: {max_seg_workers}  文件并行: {max_workers}\n"
        f"{'=' * 55}"
    )
    results: Dict[int, np.ndarray] = {}
    with ThreadPoolExecutor(max_workers=max_seg_workers) as executor:
        future_map = {
            executor.submit(_one_segment, init_time, seg_idx, output_dir, max_workers): seg_idx
            for seg_idx in range(s_start, s_end + 1)
        }
        for future in as_completed(future_map):
            seg_idx = future_map[future]
            try:
                result = future.result()
                if result is not None:
                    results[seg_idx] = result
            except Exception as exc:
                logger.error(f"  时段{seg_idx}处理异常: {exc}", exc_info=True)
    n_total = s_end - s_start + 1
    logger.info(f"完成 {init_time}：成功 {len(results)}/{n_total} 个时段")
    print(f"\n✓ 起报时次 {init_time} 处理完成，成功 {len(results)}/{n_total} 个时段")
    return results


def _stats_only(init_time: str, seg_idx: int, max_workers: int = 4) -> np.ndarray:
    data_dict, shape, _lat, _lon = load_segment(init_time, seg_idx, max_workers=max_workers)
    if shape is None:
        raise FileNotFoundError(f"[{init_time}] 段{seg_idx} 无数据")
    result = WeatherPhenomGrid12hPlugin().process(data_dict)
    print(f"\n[{init_time}] 段{seg_idx} 天气现象分布:")
    print_stats(result)
    return result


def _process(
    init_time: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    seg_range: Optional[Tuple[int, int]] = None,
    max_seg_workers: int = 3,
    max_workers: int = 4,
    stats_only: bool = False,
    data_root: Optional[str] = None,
    numexpr_threads: Optional[int] = None,
) -> Dict[str, Dict[int, np.ndarray]]:
    """处理一个起报时次。"""
    _apply_env(data_root, numexpr_threads)
    if isinstance(seg_range, list):
        seg_range = tuple(seg_range)
    if stats_only:
        seg = seg_range[0] if seg_range else 1
        return {init_time: {seg: _stats_only(init_time, seg, max_workers=max_workers)}}
    return {
        init_time: _run_init(
            init_time,
            output_dir=output_dir,
            seg_range=seg_range,
            max_seg_workers=max_seg_workers,
            max_workers=max_workers,
        )
    }


def _as_times(init_times) -> List[str]:
    if isinstance(init_times, str):
        if "," in init_times:
            return [item.strip() for item in init_times.split(",") if item.strip()]
        return [init_times]
    return list(init_times)


@merge_params(section="process", casters={"seg_range": "int_tuple"}, anchor=__file__)
def process(
    init_times=None,
    output_dir: str = "./PHENOM",
    seg_range: tuple = None,
    max_seg_workers: int = 3,
    max_workers: int = 4,
    data_root: str = None,
    stats_only: bool = False,
    numexpr_threads: int = None,
    is_multi: bool = None,
    pro_count: int = 1,
    config=None,
):
    """展开起报列表。``pro_count>1`` 时并行调用 ``_process``。"""
    _ = config
    if not init_times:
        raise ValueError("缺少参数: init_times（调用参数与配置文件均未提供）")
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    _apply_env(data_root, numexpr_threads)
    if isinstance(seg_range, list):
        seg_range = tuple(seg_range)
    times = _as_times(init_times)
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    count = int(pro_count or 1)
    if is_multi is False:
        count = 1
    elif is_multi is True and count <= 1:
        count = 4

    fixed = dict(
        output_dir=output_dir,
        seg_range=seg_range,
        max_seg_workers=max_seg_workers,
        max_workers=max_workers,
        stats_only=bool(stats_only),
        data_root=data_root,
        numexpr_threads=numexpr_threads,
    )
    if count > 1 and len(times) > 1:
        sw_all = datetime.now()
        raw = SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=count,
            fixed_params=fixed,
        ).process({"init_time": times})
        print(">>> Time elasped: " + str((datetime.now() - sw_all).total_seconds()))
        all_results: Dict[str, Dict[int, np.ndarray]] = {}
        if raw:
            for item in raw:
                if isinstance(item, dict):
                    all_results.update(item)
        return all_results

    all_results = {}
    for init_time in times:
        all_results.update(_process(init_time=init_time, **fixed))
    return all_results
