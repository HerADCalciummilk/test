# -*- coding: utf-8 -*-
"""手工对照：用本包 ``interp_sg_cressman`` 替代 meteva_base 同名接口。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for p in (str(_ROOT), str(_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import meteva_base as meb

from interp_sg_cressman import interp_sg_cressman

sta_file = r"D:\Work\NIMM_pip_repos_tmp\interp_sg_cressman\resource\input\ecmf\2026052200.036.m3"
sta = meb.read_stadata_from_micaps3(sta_file)
grid0 = meb.grid([70, 140, 0.1], [15, 55, 0.1])

grd1 = interp_sg_cressman(sta, grid0, r_list=[1000, 200, 100, 50], nearNum=100)
print(grd1)
meb.plot_tools.contourf_2d_grid(grd1)
