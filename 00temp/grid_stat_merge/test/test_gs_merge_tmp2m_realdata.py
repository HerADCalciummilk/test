# -*- coding: utf-8 -*-
"""简单实测：ECMWF 2m 温度格点 + 关测气温站点 → 格站融合。"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_ROOT), str(_ROOT / "src")]

import meteva.base as meb
from grid_stat_merge import do_gs_merge

GRID = r"D:\data1\zhongzhuan\20260828\model_RT\globalECMWF_D1D\TMP_2M\2026\20260826\2026082600.012.nc"
STA = r"D:\data1\zhongzhuan\20260828\107_Observation\TEM_national\sfc\20260826\h01_202608262000.m3"
OUT = _ROOT / "resource" / "output" / "tmp2m_gs_merge.m4"


def test_gs_merge_tmp2m():
    assert os.path.isfile(GRID) and os.path.isfile(STA)
    grd = meb.read_griddata_from_nc(GRID)
    meb.plot_tools.contourf_2d_grid(grd)
    sta = meb.read_stadata_from_micaps3(STA)
    out = do_gs_merge(grd, sta, R=100, sta_val_col="data0")
    meb.plot_tools.contourf_2d_grid(out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    meb.write_griddata_to_micaps4(out, str(OUT), creat_dir=True)
    assert OUT.is_file()
    print("OK →", OUT)


if __name__ == "__main__":
    test_gs_merge_tmp2m()
