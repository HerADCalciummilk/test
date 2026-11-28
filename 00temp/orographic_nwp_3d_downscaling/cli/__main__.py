# -*- coding: utf-8 -*-
"""``python -m cli`` → 已装饰的 ``process``（合 conf.ini，并接收 key=value）。"""
from .orographic_nwp_3d_downscaling_cli import process
from utils.merge_params import from_argv

from_argv(process)()
