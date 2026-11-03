# -*- coding: UTF-8 -*-
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

import pandas as pd
import mait_1h

"""
10种网格预报
通过mait1得到的ts权重，将模式数据的权重*上述得到的0/1的网格预报的值，然后各个模式的相加，得到最终的输出的网格预报数据值
跑2025年7月1日-2025年7月21日之间的数据
"""

if __name__ == '__main__':
    # 业务运行时间范围（世界时，含起止时刻）
    time_start_str, time_end_str = '20250701000000', '20250703230000'
    date_str_list = pd.date_range(time_start_str, time_end_str, freq='D').strftime('%Y%m%d').to_list()
    dtimes = list(range(1, 48 + 1, 1))
    is_obs_bjt = True # 实况是世界时
    is_multi = True  # 是否以多进程方式执行
    clip_coords = [70.0, 140.0, 0.0, 60.0, 0.1, 0.1]
    pro_count = 6
    time_inputs = []
    for date_str in date_str_list:
        for i in range(24):
            time_input = date_str + f"{i:02d}00"  # 传的时间为世界时
            time_inputs.append(time_input)

    keyword = {
        "time_inputs" : time_inputs,
        "predict_valid_list" : dtimes,
        "is_obs_bjt" : is_obs_bjt,
        "is_multi" : is_multi,
        "clip_coords" : clip_coords,
        "pro_count" : pro_count,
    }
    mait_1h.process(**keyword)

