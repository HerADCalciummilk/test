# -*- coding: UTF-8 -*-
# @Software : python
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
_ordered = (_ROOT, _SRC)
for _p in _ordered:
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed(_ordered):
    sys.path.insert(0, _p)

os.chdir(_ROOT)

import pandas as pd
import mait_3h

"""
3 小时多模式降水自适应集成（TS 加权 → 频率匹配 → Cressman）。
按日展开 08/20 起报后一次交给 mait_3h.process。
默认跑 2025 年 7 月 1 日–8 月 1 日（世界时）。
"""

if __name__ == "__main__":
    time_start_str, time_end_str = "20250701000000", "20250801000000"

    date_str_list = pd.date_range(
        time_start_str, time_end_str, freq="D"
    ).strftime("%Y%m%d").to_list()
    dtimes = list(range(3, 252 + 1, 3))
    # 空则读 mait_3.ini；这里显式给出，与 RunProcess 里 beta_path%(i,j) 一致
    para_path = os.path.join(_ROOT, "resource", "para_3.ini")
    beta_path = os.path.join(_ROOT, "beta_3h", "YYYYMMDDHH", "%02d_%02d_TTT.info")
    is_obs_bjt = True  # True：实况时刻 +8 h（北京时）
    is_multi = True  # 按起报多进程（SimpleParallelTool）
    is_interp = False
    clip_coords = [70.0, 140.0, 0.0, 60.0, 0.1, 0.1]
    pro_count = 8
    time_inputs = []
    for date_str in date_str_list:
        for hour_minute in ["0800", "2000"]:
            time_input = date_str + hour_minute  # YYYYMMDDHHMM，世界时
            time_inputs.append(time_input)

    keyword = {
        "time_inputs": time_inputs,
        "predict_valid_list": dtimes,
        "para_path": para_path,
        "beta_path": beta_path,
        "is_obs_bjt": is_obs_bjt,
        "is_interp": is_interp,
        "is_multi": is_multi,
        "clip_coords": clip_coords,
        "pro_count": pro_count,
    }
    mait_3h.process(**keyword)
