# -*- coding: utf-8 -*-
"""烟测：本地核函数；完整 do_gs_merge 在 meteva 可用时再跑。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from grid_stat_merge import diffuse_values, gaussian_2d


def test_gaussian_2d_peak_at_center():
    x = np.arange(-5, 6)
    isig = (5 * 0.35) ** 2
    cov = np.array([[isig, 0.0], [0.0, isig]])
    w = gaussian_2d(x, x, 0, 0, cov, scale_factor=1.0)
    assert w.shape == (11, 11)
    cy, cx = w.shape[0] // 2, w.shape[1] // 2
    assert w[cy, cx] == np.nanmax(w)


def test_diffuse_values_smoothes():
    m = np.zeros((7, 7), dtype=float)
    m[2, 2] = 8.0
    m[2, 4] = 8.0
    m[4, 2] = 8.0
    m[4, 4] = 8.0
    fg = np.zeros_like(m)
    out = diffuse_values(m, fg_matrix=fg, num_iterations=10)
    assert out.shape == m.shape
    # 固定散点保持；邻域被扩散抬升
    assert out[2, 2] == 8.0
    assert out[3, 3] > 0


def test_do_gs_merge_if_meteva_ok():
    pytest.importorskip("meteva")
    import meteva.base as meb
    from grid_stat_merge import do_gs_merge, GridStatMergePlugin

    grid = meb.grid([100, 102, 1], [30, 32, 1])
    grd = meb.grid_data(grid)
    grd.values[...] = 10.0
    sta = pd.DataFrame({"lon": [101.0], "lat": [31.0], "val": [20.0]})
    try:
        out = do_gs_merge(grd, sta, R=50.0, sta_val_col="val")
    except TypeError as e:
        # 部分 meteva 版本 reset_lon_range 非可调用，跳过端到端
        pytest.skip("meteva.interp_gs_linear 不可用: %s" % e)
    vals = np.squeeze(np.asarray(out.values, dtype=float))
    assert np.nanmax(vals) > 10.0

    plugin = GridStatMergePlugin(R=50.0, sta_val_col="data0")
    sta2 = pd.DataFrame({"lon": [101.0], "lat": [31.0], "data0": [15.0]})
    try:
        out2 = plugin(grd.copy(deep=True), sta2)
    except TypeError as e:
        pytest.skip("meteva.interp_gs_linear 不可用: %s" % e)
    assert np.squeeze(out2.values).shape == np.squeeze(grd.values).shape
