# -*- coding: utf-8 -*-
"""
算法调度模块（纯计算层，不涉及任何文件I/O读取）
对一个12h时段的内存数据执行完整判识流程，输出网格天气现象电码NC文件
流程：判识 → 选取 → 逻辑关系 → 编码 → 保存

职责边界：
  本模块只接收调用方已加载到内存的数据（data_dict/lat/lon），
  不直接读取NC文件、不依赖 meteva 数据加载接口。
  数据加载（文件I/O）统一在 src/utils/data_loader.py 中完成。
  写出与统计辅助位于 src.utils.output。
"""
import os
import logging

import numpy as np

from resource.data_schema import get_segment_fh
from .identifier import DIA_WeatherPhenomIdentifier
from .selector import DIA_WeatherPhenomSelector
from .logic_judger import DIA_WeatherPhenomLogicJudger
from .encoder import DIA_WeatherPhenomEncoder
from .utils.output import save_nc, print_stats

logger = logging.getLogger(__name__)

# 默认输出根目录（与输入数据同服务器，独立子目录）
DEFAULT_OUTPUT_DIR = "./PHENOM"

# ── 算法插件单例（模块级，避免每次调用重复初始化）─────────────
_identifier = DIA_WeatherPhenomIdentifier()
_selector   = DIA_WeatherPhenomSelector()
_judger     = DIA_WeatherPhenomLogicJudger()
_encoder    = DIA_WeatherPhenomEncoder()


def run_segment(data_dict: dict, shape, lat_arr: np.ndarray, lon_arr: np.ndarray,
                init_time: str, seg_idx: int,
                output_dir: str = DEFAULT_OUTPUT_DIR) -> np.ndarray | None:
    """
    处理一个12h时段（纯内存计算，不涉及任何文件I/O读取）

    Args:
        data_dict   : 调用方（cli 层）已加载到内存的变量数据字典
        shape       : (nlat, nlon) 或 None（数据全部缺失时）
        lat_arr     : ndarray[nlat]，纬度坐标（可能为 None）
        lon_arr     : ndarray[nlon]，经度坐标（可能为 None）
        init_time   : 起报时次 YYYYMMDDHH
        seg_idx     : 12h时段序号（1~20）
        output_dir  : 输出根目录

    Returns:
        result ndarray[lat, lon] int32，失败时返回 None
    """
    fh_list = get_segment_fh(seg_idx)
    logger.info(f"  [{seg_idx:02d}] FH {fh_list[0]:03d}~{fh_list[-1]:03d}h")
    print(f"[{seg_idx:02d}] FH {fh_list[0]:03d}~{fh_list[-1]:03d}h 开始处理...")

    if shape is None:
        logger.warning(f"    → 数据全部缺失，跳过")
        print(f"[{seg_idx:02d}] 数据缺失，跳过")
        return None

    # Step 2: 判识（使用插件类）
    occur = _identifier.process(data_dict)
    print(f"[{seg_idx:02d}] 天气现象判识完成")

    # Step 3: 选取A、B（使用插件类，返回 int8 索引）
    idx_A, idx_B = _selector.process(occur)
    print(f"[{seg_idx:02d}] A/B现象选取完成")

    # Step 4: 判断逻辑关系（使用插件类，int8 索引全程传递）
    logic, idx_final_A, idx_final_B = _judger.process(idx_A, idx_B, occur)
    print(f"[{seg_idx:02d}] 逻辑关系判断完成")

    # Step 5: 编码（使用插件类，int8 索引 → int32 电码）
    result = _encoder.process(idx_final_A, idx_final_B, logic)
    print(f"[{seg_idx:02d}] 编码完成，正在保存...")

    # Step 6: 保存（工具模块）
    if lat_arr is not None and lon_arr is not None:
        ttt = seg_idx * 12
        out_file = os.path.join(
            output_dir, init_time,
            f"{init_time}.{ttt:03d}.nc"
        )
        try:
            save_nc(out_file, result, lat_arr, lon_arr, init_time, seg_idx)
            print(f"[{seg_idx:02d}] 已保存 → {out_file}")
        except Exception as e:
            logger.error(f"    保存失败: {e}")
            print(f"[{seg_idx:02d}] 保存失败: {e}")
    else:
        logger.warning(f"    坐标信息缺失，跳过保存")

    return result


# ==============================================================================
#  独立测试：使用随机内存数据验证纯计算流程（不涉及任何文件I/O读取）
# ==============================================================================
if __name__ == "__main__":
    from resource.data_schema import VARS_240H, VARS_72H

    shape = (5, 6)
    data_dict = {v: np.random.rand(4, *shape).astype(np.float32) * 10
                 for v in VARS_240H + VARS_72H}
    lat_arr = np.linspace(30.0, 35.0, shape[0], dtype=np.float32)
    lon_arr = np.linspace(110.0, 115.0, shape[1], dtype=np.float32)

    result = run_segment(data_dict, shape, lat_arr, lon_arr,
                          "2026030100", 1, output_dir="./PHENOM_TEST")
    if result is not None:
        print_stats(result)
