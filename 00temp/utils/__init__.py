# -*- coding: utf-8 -*-
"""NIMM 共享插件工具包。

提供 ``cli_base``、``base_plugin``、``multipro_plugin``、``data_prepare_plugin``、
``data_distribute_pulgin``、``conf_ini``、``grid_combine`` 等跨算法通用模块。

格点双线性、站点 Cressman 已独立为子模块 ``interp_gg_linear``、``interp_sg_cressman``，
不再放在本目录。

各算法项目通过本地 ``utils/__init__.py`` 将本目录并入 ``utils`` 包后，
统一使用 ``from utils.xxx import ...``。

常用可调用插件
--------------
- ``from utils.cli_base import CliBase``
- ``from utils.base_plugin import BasePlugin``
- ``from utils.multipro_plugin import SimpleParallelTool``
- ``from utils.pressure_to_height_plugin import PressureToHeightPlugin, read_pressure_levels``
- ``from utils.grid_combine import read_multi_griddata, concat_griddata``
"""
