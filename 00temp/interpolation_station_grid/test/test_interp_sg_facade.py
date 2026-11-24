# -*- coding: utf-8 -*-
"""InterpSg 统一入口：分派与结果一致性。"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest
import meteva_base as meb

from interp_sg_idw_plugin import InterpSgIdw
from interp_sg_plugin import InterpSg


def _make_sta():
    df = pd.DataFrame(
        {
            "level": [0.0, 0.0, 0.0],
            "time": pd.to_datetime(["2020-01-01"] * 3),
            "dtime": [0, 0, 0],
            "id": [1, 2, 3],
            "lon": [110.0, 111.0, 112.0],
            "lat": [30.0, 31.0, 30.5],
            "data0": [10.0, 12.0, 11.0],
        }
    )
    return meb.sta_data(df)


def _target_grid():
    return meb.basicdata.grid([109.5, 112.5, 0.5], [29.5, 31.5, 0.5])


def test_normalize_aliases():
    assert InterpSg._normalize_method("total") == "idw"
    assert InterpSg._normalize_method("delta") == "idw_delta"
    assert InterpSg._normalize_method("idw-delta") == "idw_delta"


def test_invalid_method():
    with pytest.raises(ValueError, match="method"):
        InterpSg(method="unknown")


def test_signature_lists_all_params():
    params = inspect.signature(InterpSg.__init__).parameters
    expected = {
        "method",
        "reprocess",
        "outer_value",
        "effectR",
        "nearNum",
        "decrease",
        "gaussian",
        "halfR",
        "model",
        "sill",
        "range_",
        "nugget",
        "r_list",
    }
    assert expected <= set(params)


def test_unused_method_params_are_ignored():
    plugin = InterpSg(method="idw", effectR=1000, halfR=99, model="exponential")
    assert plugin.method == "idw"
    assert isinstance(plugin._impl, InterpSgIdw)


def test_idw_matches_direct_plugin():
    sta = _make_sta()
    grid = _target_grid()
    a = InterpSg(
        method="idw", effectR=500000, nearNum=3, decrease=2, reprocess=False
    ).process(sta, grid)
    b = InterpSgIdw(
        effectR=500000, nearNum=3, decrease=2, reprocess=False
    ).process(sta, grid)
    assert a is not None and b is not None
    np.testing.assert_allclose(a.values, b.values, equal_nan=True)


def test_reprocess_defaults_to_gaussian_weight():
    auto = InterpSg(method="idw", reprocess=True, effectR=1000, nearNum=8)
    assert auto.reprocess is True
    assert auto._impl.gaussian is True
    off = InterpSg(
        method="idw", reprocess=True, gaussian=False, effectR=1000, nearNum=8
    )
    assert off._impl.gaussian is False


def test_idw_delta_forces_gaussian_reprocess():
    plugin = InterpSg(method="idw_delta", effectR=1000, nearNum=8, decrease=2)
    assert plugin.method == "idw_delta"
    assert plugin.reprocess is True
    assert plugin._impl.gaussian is True


def test_gaussian_and_cressman_construct():
    g = InterpSg(method="gaussian", halfR=20)
    assert g.method == "gaussian"
    c = InterpSg(method="cressman", r_list=[60000.0, 40000.0], nearNum=50)
    assert c.method == "cressman"
