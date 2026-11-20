# -*- coding: utf-8 -*-
"""NIMM 共享插件工具包。

提供 ``cli_base``、``base_plugin``、``multipro_plugin``、``data_prepare_plugin``、
``data_distribute_pulgin``、``conf_ini``、``grid_combine``、``interpolating`` 等跨算法通用模块。

格点双线性、站点 Cressman 已分别落在 ``interpolation_grid_grid``、``interpolation_station_grid``；
通用插值函数集中在 ``interpolating``（站点→格点支持可选 ``background``：有则先算偏差再插值）。

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
