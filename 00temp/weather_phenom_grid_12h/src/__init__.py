# -*- coding: utf-8 -*-
"""
网格天气现象综合电码生成系统 - 核心源码包
依据 QX/T 740-2024 基于网格预报的城镇预报生成规范
"""

__version__ = "1.0.0"
__author__  = "NMC Algorithm Team"
__license__ = "GPL-3.0"

from resource.config import *
from resource.data_schema import *
from resource.weather_config import *
from .identifier import identify, DIA_WeatherPhenomIdentifier
from .selector import select, DIA_WeatherPhenomSelector
from .logic_judger import judge, DIA_WeatherPhenomLogicJudger
from .encoder import encode, decode, DIA_WeatherPhenomEncoder
from .processor import run_segment, DEFAULT_OUTPUT_DIR
from .utils.output import print_stats, save_nc
from .utils.data_loader import load_segment

# 对外公开的插件类列表（遵循国省统筹算法技术规范 Plugin 接口）
__all__ = [
    "__version__",
    # 算法插件（规范要求的 Class 形式）
    "DIA_WeatherPhenomIdentifier",
    "DIA_WeatherPhenomSelector",
    "DIA_WeatherPhenomLogicJudger",
    "DIA_WeatherPhenomEncoder",
    # 基础函数（向后兼容）
    "identify", "select", "judge", "encode", "decode",
    # 调度接口（纯内存计算；端到端请用 src.main.process）
    "run_segment",
    "DEFAULT_OUTPUT_DIR",
    # 工具（src.utils）
    "print_stats",
    "save_nc",
    "load_segment",
]
