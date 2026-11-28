# -*- coding: utf-8 -*-
"""NIMM 共享插件工具包。

提供 ``cli_base``、``nimm_cli``、``base_plugin``、``multipro_plugin``、
``data_prepare_plugin``、``data_distribute_pulgin``、``merge_params`` 等跨算法通用模块。

各算法项目通过本地 ``utils/__init__.py`` 将本目录并入 ``utils`` 包后，
统一使用 ``from utils.xxx import ...``。

常用可调用插件
--------------
- ``from utils.cli_base import CliBase, merge_params``
- ``from utils.merge_params import merge_params, collect_merged_params``
- ``from utils.nimm_cli import nimm_cli``
- ``from utils.base_plugin import BasePlugin``
- ``from utils.multipro_plugin import SimpleParallelTool``

统一调度（在 ``00temp`` 目录）::

    python -m utils.nimm_cli
    python -m frequency_matching_rain24
    python -m frequency_matching_rain24 pro_count=1
"""
