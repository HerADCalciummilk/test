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

import pandas as pd
import mait_24h

"""
10种网格预报
通过mait24得到的ts权重，将模式数据的权重*上述得到的0/1的网格预报的值，然后各个模式的相加，得到最终的输出的网格预报数据值
跑2025年7月15日-2025年8月31日之间的数据
"""

if __name__ == '__main__':
    time_start_str, time_end_str = '20250701000000','20250801000000'

    date_str_list = pd.date_range(time_start_str, time_end_str, freq='D').strftime('%Y%m%d').to_list()
    dtimes = [36, 60, 84, 108, 132, 156, 180, 204, 228, 252]
    para_path = r'./para/para_24.ini'
    beta_path = r'./beta_24/YYYYMMDDHH'
    is_obs_bjt = True # 实况是世界时
    is_multi = True  # 是否以多进程方式执行
    clip_coords = [70.0, 140.0, 0.0, 60.0, 0.1, 0.1]
    pro_count = 8
    split_lat = 1
    split_lon = 1
    time_inputs = []
    for date_str in date_str_list:
        for hour_minute in ['0800','2000']:
            time_input = date_str + hour_minute # 传的时间为世界时
            time_inputs.append(time_input)

    keyword = {
        "time_inputs" : time_inputs,
        "predict_valid_list" : dtimes,
        "para_path" : para_path,
        "beta_path" : beta_path,
        "is_obs_bjt" : is_obs_bjt,
        "is_multi" : is_multi,
        "clip_coords" : clip_coords,
        "pro_count" : pro_count,
        "split_lat" : split_lat,
        "split_lon" : split_lon
    }
    mait_24h.process(**keyword)

