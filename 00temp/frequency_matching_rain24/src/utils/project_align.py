# -*- coding: utf-8 -*-
"""
兼容旧名：请改用 ``utils.cressman_extrap_reprocess``。

本文件仅做再导出，逻辑都在 ``cressman_extrap_reprocess.py``。
"""
from utils.cressman_extrap_reprocess import *  # noqa: F401,F403
from utils.cressman_extrap_reprocess import (  # noqa: F401
    OpticalFlowProject,
    LagrangianAligned,
    cressman_project_innov,
    cressman_innov_wrap,
    cressman_innov_gressman_like,
    extrapolate_like_lagrangian,
)

# 业务常用别名
project_innov_wrap = cressman_project_innov
