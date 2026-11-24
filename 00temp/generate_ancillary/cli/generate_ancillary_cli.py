# -*- coding: utf-8 -*-
"""海陆掩码二值化。本包主入口。

``@merge_params`` 挂在 ``process`` 上。读掩码 nc，调用 ``CorrectLandSeaMask``，按需写盘。
"""
from __future__ import annotations

import os
import sys

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_TEMP_DIR = os.path.dirname(_ROOT_DIR)
for _p in (_TEMP_DIR, _ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import meteva_base as meb

from generate_ancillary.src.generate_ancillary import CorrectLandSeaMask
from utils.merge_params import merge_params


@merge_params()
def process(landmask_path=None, output_path=None, config=None):
    """读取海陆掩码并输出 0/1。``config`` 只换配置文件。"""
    _ = config
    if landmask_path is None or not str(landmask_path).strip():
        raise ValueError("缺少参数: landmask_path")
    landmask = meb.read_griddata_from_nc(landmask_path)
    result = CorrectLandSeaMask().process(landmask)
    if output_path:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result
