# -*- coding: utf-8 -*-
"""NIMM 共享插件工具包。

提供 ``cli_base``、``conf_ini``、``base_plugin``、``multipro_plugin``、``data_prepare_plugin``、
``data_distribute_pulgin``、``interp_gg_pulgin``、``grid_stat_merge_plugin``、
``interp_sg_cressman_plugin`` 等跨算法通用模块。

各算法项目通过本地 ``utils/__init__.py`` 将本目录并入 ``utils`` 包后，
统一使用 ``from utils.xxx import ...``。

常用可调用插件
--------------
- ``from utils.cli_base import CliBase``
- ``from utils.conf_ini import ...``
- ``from utils.interp_gg_pulgin import InterpGGLinearPlugin, interp_gg_linear``
- ``from utils.grid_stat_merge_plugin import GridStatMergePlugin, do_gs_merge``
- ``from utils.interp_sg_cressman_plugin import InterpSGCressmanPlugin, interp_sg_cressman``
- ``from utils.pressure_to_height_plugin import PressureToHeightPlugin, read_pressure_levels``
"""
