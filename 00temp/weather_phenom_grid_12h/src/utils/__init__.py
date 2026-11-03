# -*- coding: utf-8 -*-
"""
src 层工具模块

  - data_loader : SCMOC 网格 NC 加载（``load_segment``）
  - output      : NetCDF 写出与电码统计等输出辅助
"""

from .output import save_nc, print_stats
from .data_loader import load_segment

__all__ = [
    "save_nc",
    "print_stats",
    "load_segment",
]
