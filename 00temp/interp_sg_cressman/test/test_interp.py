# -*- coding: utf-8 -*-
"""手工对照：``InterpSgCressman`` 插值出图。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for p in (str(_ROOT), str(_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import meteva_base as meb

from interp_sg_cressman_plugin import InterpSgCressman

sta_file = r"D:\Work\NIMM_pip_repos_tmp\interp_sg_cressman\resource\input\ecmf\2026052200.036.m3"
sta = meb.read_stadata_from_micaps3(sta_file)
grid0 = meb.grid([70, 140, 0.1], [15, 55, 0.1])

grd1 = InterpSgCressman(
    r_list=[1000, 200, 100, 50], nearNum=100
).process(sta, grid=grid0)
print(grd1)
meb.plot_tools.contourf_2d_grid(grd1)
