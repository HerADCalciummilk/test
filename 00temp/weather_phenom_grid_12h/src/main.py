# -*- coding: utf-8 -*-
"""
网格天气现象综合电码生成 — 主程序模块（``src/main.py``）。

依据：QX/T 740-2024《基于网格预报的城镇预报生成规范 天气现象》

外部模块调用
------------
::

    from src.main import process
    process("2026030100")
    process(
        ["2026030100", "2026030112"],
        seg_range=(1, 6),
        output_dir="./PHENOM",
        is_multi=True,
        pro_count=2,
    )

命令行（参数解析在 cli）
----------------------
::

    python -m cli 2026030100
    python -m cli 2026030100 2026030112 --seg-range 1 6 --is-multi --pro-count 2

直接运行本文件（在 ``__main__`` 中给 ``process`` 传参）::

    python src/main.py
"""
from __future__ import annotations

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

# ── 路径引导：项目根入 path；00temp 入 path（共享 SimpleParallelTool）──
_SRC_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SRC_DIR.parent
_00TEMP = _PROJECT_ROOT.parent
_src_str = str(_SRC_DIR)
_root_str = str(_PROJECT_ROOT)
_00temp_str = str(_00TEMP)
while _src_str in sys.path:
    sys.path.remove(_src_str)
for _p in (_root_str, _00temp_str):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from resource.data_schema import MAX_SEGMENTS  # noqa: E402
from src.utils.data_loader import load_segment  # noqa: E402
from src.processor import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    run_segment as _process_segment,
)
from src.utils.output import print_stats  # noqa: E402
from src.identifier import DIA_WeatherPhenomIdentifier  # noqa: E402
from src.selector import DIA_WeatherPhenomSelector  # noqa: E402
from src.logic_judger import DIA_WeatherPhenomLogicJudger  # noqa: E402
from src.encoder import DIA_WeatherPhenomEncoder  # noqa: E402
from utils.multipro_plugin import SimpleParallelTool  # noqa: E402

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 编排：单时段 / 单起报
# ──────────────────────────────────────────────────────────────

def run_segment(
    init_time: str,
    seg_idx: int,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    max_workers: int = 4,
) -> Optional[np.ndarray]:
    """
    加载并处理一个 12h 时段。

    Returns:
        result ndarray[lat, lon] int32；失败/数据缺失时返回 None
    """
    data_dict, shape, lat_arr, lon_arr = load_segment(
        init_time, seg_idx, max_workers=max_workers
    )
    return _process_segment(
        data_dict, shape, lat_arr, lon_arr,
        init_time, seg_idx, output_dir=output_dir,
    )


def run(
    init_time: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    seg_range: Optional[Tuple[int, int]] = None,
    max_seg_workers: int = 5,
    max_workers: int = 8,
) -> Dict[int, np.ndarray]:
    """
    线程池并行处理一个起报时次的全部（或指定范围）12h 时段。

    Returns:
        {seg_idx: result_array}，跳过的时段不在字典中
    """
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
            executor.submit(
                run_segment, init_time, seg_idx, output_dir, max_workers
            ): seg_idx
            for seg_idx in range(s_start, s_end + 1)
        }
        for future in as_completed(future_map):
            seg_idx = future_map[future]
            try:
                r = future.result()
                if r is not None:
                    results[seg_idx] = r
            except Exception as e:
                logger.error(f"  时段{seg_idx}处理异常: {e}", exc_info=True)

    n_total = s_end - s_start + 1
    logger.info(f"完成 {init_time}：成功 {len(results)}/{n_total} 个时段")
    print(f"\n✓ 起报时次 {init_time} 处理完成，成功 {len(results)}/{n_total} 个时段")
    return results


def _run_stats_only(
    init_time: str,
    seg_idx: int,
    max_workers: int = 4,
) -> np.ndarray:
    """仅计算并打印统计，不写 NC。"""
    data_dict, shape, lat_arr, lon_arr = load_segment(
        init_time, seg_idx, max_workers=max_workers
    )
    if shape is None:
        raise FileNotFoundError(f"[{init_time}] 段{seg_idx} 无数据")
    occur = DIA_WeatherPhenomIdentifier().process(data_dict)
    idx_a, idx_b = DIA_WeatherPhenomSelector().process(occur)
    logic, idx_fa, idx_fb = DIA_WeatherPhenomLogicJudger().process(
        idx_a, idx_b, occur
    )
    result = DIA_WeatherPhenomEncoder().process(idx_fa, idx_fb, logic)
    print(f"\n[{init_time}] 段{seg_idx} 天气现象分布:")
    print_stats(result)
    return result


def _process_one_init_time(
    init_time: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    seg_range: Optional[Tuple[int, int]] = None,
    max_seg_workers: int = 3,
    max_workers: int = 4,
    stats_only: bool = False,
) -> Dict[int, np.ndarray]:
    """处理单个起报时次（串行/多进程 worker 共用）。"""
    if stats_only:
        seg = seg_range[0] if seg_range else 1
        result = _run_stats_only(init_time, seg, max_workers=max_workers)
        return {seg: result}
    return run(
        init_time,
        output_dir=output_dir,
        seg_range=seg_range,
        max_seg_workers=max_seg_workers,
        max_workers=max_workers,
    )


def _process_worker(
    output_dir: str = DEFAULT_OUTPUT_DIR,
    seg_range: Optional[Tuple[int, int]] = None,
    max_seg_workers: int = 3,
    max_workers: int = 4,
    stats_only: bool = False,
    data_root: Optional[str] = None,
    numexpr_threads: Optional[int] = None,
    **params,
) -> Dict[str, Dict[int, np.ndarray]]:
    """
    多进程 worker：处理 ``params['param']`` 中的单个起报时次。

    接口形态参考 multi_rain_mait24_blending / multi_wind_fft_blending
    对 ``SimpleParallelTool`` 的用法（固定参数 + ``param`` 并行项）。
    """
    if numexpr_threads is not None:
        os.environ["NUMEXPR_MAX_THREADS"] = str(numexpr_threads)
        os.environ["NUMEXPR_NUM_THREADS"] = str(numexpr_threads)
    if data_root is not None:
        os.environ["SCMOC_DATA_ROOT"] = data_root

    case = params["param"]
    init_time = case["init_time"] if isinstance(case, dict) else case
    seg_results = _process_one_init_time(
        init_time,
        output_dir=output_dir,
        seg_range=seg_range,
        max_seg_workers=max_seg_workers,
        max_workers=max_workers,
        stats_only=stats_only,
    )
    return {init_time: seg_results}


def _process_multi(
    cases: List[Dict[str, str]],
    pro_count: int,
    fixed_params: dict,
) -> Dict[str, Dict[int, np.ndarray]]:
    """多进程批量处理多个起报时次。"""
    sw_all = datetime.now()
    parallel_tool = SimpleParallelTool(
        target_func=_process_worker,
        parallel_mode="async",
        with_return=True,
        num_process=pro_count,
        fixed_params=fixed_params,
    )
    raw = parallel_tool.process({"param": cases})
    print(">>> Time elasped: " + str((datetime.now() - sw_all).total_seconds()))

    all_results: Dict[str, Dict[int, np.ndarray]] = {}
    if raw:
        for item in raw:
            if isinstance(item, dict):
                all_results.update(item)
    return all_results


# ──────────────────────────────────────────────────────────────
# 对外统一 API
# ──────────────────────────────────────────────────────────────

def process(
    init_times: Union[str, Sequence[str]],
    output_dir: str = DEFAULT_OUTPUT_DIR,
    seg_range: Optional[Tuple[int, int]] = None,
    max_seg_workers: int = 3,
    max_workers: int = 4,
    data_root: Optional[str] = None,
    stats_only: bool = False,
    numexpr_threads: Optional[int] = None,
    is_multi: bool = False,
    pro_count: int = 4,
    config: Optional[str] = None,
) -> Dict[str, Dict[int, np.ndarray]]:
    """
    网格天气现象综合电码生成主入口。

    Args:
        init_times       : 起报时次 YYYYMMDDHH，或列表
        output_dir       : 输出根目录
        seg_range        : (start, end) 时段范围（含端点），默认全部 1~20
        max_seg_workers  : 单起报内时段间线程并行数
        max_workers      : 单时段内文件读取并行线程数
        data_root        : 覆盖 SCMOC 数据根目录（写入环境变量）
        stats_only       : True 时只算首段并打印统计，不保存
        numexpr_threads  : 限制 NumExpr 线程数，降低高并发 CPU 争用
        is_multi         : 多起报时是否多进程；单起报时忽略
        pro_count        : 多进程并行数（``is_multi=True`` 时生效）
        config           : 运行配置 ini。为空时读 resource/conf.ini，只填补仍为 None 的项。

    Returns:
        {init_time: {seg_idx: result_array}}
    """
    _over = _nimm_overlay(config, {
        "seg_range": (seg_range, "int_tuple"),
        "data_root": (data_root, "str"),
        "numexpr_threads": (numexpr_threads, "int"),
    })
    seg_range = _over['seg_range']
    data_root = _over['data_root']
    numexpr_threads = _over['numexpr_threads']
    if numexpr_threads is not None:
        os.environ["NUMEXPR_MAX_THREADS"] = str(numexpr_threads)
        os.environ["NUMEXPR_NUM_THREADS"] = str(numexpr_threads)
    if data_root is not None:
        os.environ["SCMOC_DATA_ROOT"] = data_root

    if isinstance(init_times, str):
        times: List[str] = [init_times]
    else:
        times = list(init_times)

    common = dict(
        output_dir=output_dir,
        seg_range=seg_range,
        max_seg_workers=max_seg_workers,
        max_workers=max_workers,
        stats_only=stats_only,
        data_root=data_root,
        numexpr_threads=numexpr_threads,
    )

    # 单起报或不启用多进程：串行
    if len(times) == 1 or not is_multi:
        all_results: Dict[str, Dict[int, np.ndarray]] = {}
        for init_time in times:
            all_results[init_time] = _process_one_init_time(
                init_time,
                output_dir=output_dir,
                seg_range=seg_range,
                max_seg_workers=max_seg_workers,
                max_workers=max_workers,
                stats_only=stats_only,
            )
        return all_results

    # 多起报 + 多进程（参考 mait24 / fft：SimpleParallelTool + param 列表）
    cases = [{"init_time": t} for t in times]
    return _process_multi(cases, pro_count=pro_count, fixed_params=common)


if __name__ == "__main__":
    # 直接运行：在此修改 process 传参即可；命令行请用 python -m cli ...
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    process(
        init_times="2026030100",
        output_dir=DEFAULT_OUTPUT_DIR,
        seg_range=(1, 3),
        max_seg_workers=3,
        max_workers=4,
        is_multi=False,
        pro_count=4,
        stats_only=False,
    )
