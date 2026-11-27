# -*- coding: utf-8 -*-
"""``python -m cli [key=value ...]`` → 已装饰的 ``process``（合 conf.ini）。"""

from .interpolation_station_grid_cli import process
from utils.merge_params import from_argv

from_argv(process)()
