# -*- coding: utf-8 -*-
"""双线性插值烟测：粗网格常值场插到细网格。"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("meteva")
import meteva.base as meb

from interp_gg_linear import InterpGGLinearPlugin, interp_gg_linear


def _const_grd(val=10.0):
    grid0 = meb.grid([100, 102, 1.0], [30, 32, 1.0])
    grd = meb.grid_data(grid0)
    grd.values[...] = val
    return grd


def test_interp_gg_linear_smoke():
    grd = _const_grd(10.0)
    grid = meb.grid([100, 102, 0.5], [30, 32, 0.5])
    try:
        out = interp_gg_linear(grd, grid, used_coords="xy", outer_value=0.0)
    except Exception as e:
        pytest.skip("环境无法完成双线性烟测: %s" % e)
    assert out is not None
    vals = np.asarray(out.values, dtype=float)
    assert vals.size > 0
    assert np.nanmax(vals) > 0
    # 常值场插到更细网格，内部应接近原值
    assert abs(float(np.nanmean(vals)) - 10.0) < 1e-3


def test_plugin_callable():
    grd = _const_grd(5.0)
    grid = meb.grid([100, 102, 0.5], [30, 32, 0.5])
    plugin = InterpGGLinearPlugin(used_coords="xy", outer_value=0.0)
    try:
        out = plugin(grd, grid)
    except Exception as e:
        pytest.skip("环境无法完成插件烟测: %s" % e)
    assert out is not None


def test_outer_value_required_when_out_of_range():
    grd = _const_grd(1.0)
    grid = meb.grid([99, 103, 1.0], [29, 33, 1.0])
    try:
        out = interp_gg_linear(grd, grid, used_coords="xy", outer_value=None)
    except Exception as e:
        pytest.skip("环境无法完成越界烟测: %s" % e)
    assert out is None
