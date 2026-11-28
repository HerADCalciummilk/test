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


def test_normalize_case_and_only_four_methods():
    assert InterpSg._normalize_method("IDW") == "idw"
    assert InterpSg._normalize_method("Gaussian") == "gaussian"
    for bad in ("unknown", "total", "idw_delta", "delta"):
        with pytest.raises(ValueError, match="method"):
            InterpSg(method=bad)


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


def test_gaussian_independent_of_reprocess():
    # reprocess 与 gaussian 相互独立，互不默认
    deviation = InterpSg(method="idw", reprocess=True, effectR=1000, nearNum=8)
    assert deviation.reprocess is True
    assert deviation._impl.gaussian is False
    gauss_abs = InterpSg(method="idw", reprocess=False, gaussian=True, effectR=1000)
    assert gauss_abs.reprocess is False
    assert gauss_abs._impl.gaussian is True


def test_gaussian_and_cressman_construct():
    g = InterpSg(method="gaussian", halfR=20)
    assert g.method == "gaussian"
    c = InterpSg(method="cressman", r_list=[60.0, 40.0], nearNum=50)
    assert c.method == "cressman"


# ---------------------------------------------------------------------------
# 完整性：参数覆盖、默认值、全方法 × reprocess 与直接子插件结果一致
# ---------------------------------------------------------------------------
from interp_sg_cressman_plugin import InterpSgCressman  # noqa: E402
from interp_sg_gaussian_plugin import InterpSgGaussian  # noqa: E402
from interp_sg_kriging import InterpSgKriging  # noqa: E402

_SUB_PLUGINS = {
    "idw": InterpSgIdw,
    "gaussian": InterpSgGaussian,
    "kriging": InterpSgKriging,
    "cressman": InterpSgCressman,
}


def _sub_params(cls):
    return {k: v for k, v in inspect.signature(cls.__init__).parameters.items() if k != "self"}


@pytest.mark.parametrize("method", sorted(_SUB_PLUGINS))
def test_facade_exposes_every_sub_plugin_param(method):
    """子插件新增的构造参数必须同步到门面，不能漏。"""
    facade = inspect.signature(InterpSg.__init__).parameters
    missing = set(_sub_params(_SUB_PLUGINS[method])) - set(facade)
    assert not missing, f"门面缺少 {method} 子插件参数: {sorted(missing)}"


@pytest.mark.parametrize("method", sorted(_SUB_PLUGINS))
def test_facade_defaults_match_sub_plugin(method):
    """同名参数的默认值与子插件一致（nearNum / gaussian 为 None，表示沿用子插件默认）。"""
    facade = inspect.signature(InterpSg.__init__).parameters
    deferred = {"nearNum", "gaussian"}
    for name, param in _sub_params(_SUB_PLUGINS[method]).items():
        if name in deferred or param.default is inspect.Parameter.empty:
            continue
        assert facade[name].default == param.default, f"{method}.{name} 默认值不一致"
    assert facade["nearNum"].default is None
    assert facade["gaussian"].default is None


def _synthetic_inputs():
    rng = np.random.default_rng(1)
    n = 40
    sta = meb.sta_data(
        pd.DataFrame(
            {
                "level": 0.0,
                "time": pd.to_datetime(["2020-01-01"] * n),
                "dtime": 0,
                "id": np.arange(n),
                "lon": rng.uniform(110, 114, n),
                "lat": rng.uniform(30, 34, n),
                "data0": rng.uniform(0, 30, n),
            }
        )
    )
    grid = meb.basicdata.grid([109.5, 114.5, 0.25], [29.5, 34.5, 0.25])
    bg = meb.grid_data(grid)
    bg.data = [[[[rng.uniform(0, 20, (grid.nlat, grid.nlon)).astype(np.float32)]]]]
    return sta, grid, bg


_MATCH_CASES = {
    "idw": lambda rp: dict(effectR=300, nearNum=8, decrease=2),
    "idw_gaussian": lambda rp: dict(effectR=200, nearNum=8, decrease=2, gaussian=True),
    "gaussian": lambda rp: dict(halfR=150),
    "kriging": lambda rp: dict(model="spherical", nearNum=12),
    "cressman": lambda rp: dict(),
    "cressman_params": lambda rp: dict(
        rain_limit=0.01,
        degree_blend=1.0,
        r_list=[1.0, 0.8, 0.6, 0.4] if rp else [80.0, 40.0],
    ),
}


@pytest.mark.parametrize("reprocess", [False, True])
@pytest.mark.parametrize("case", sorted(_MATCH_CASES))
def test_facade_matches_direct_plugin_all_methods(case, reprocess):
    method = case.split("_")[0]
    kw = _MATCH_CASES[case](reprocess)
    sta, grid, bg = _synthetic_inputs()
    via_facade = InterpSg(method=method, reprocess=reprocess, **kw).process(sta, grid, background=bg)
    direct = _SUB_PLUGINS[method](reprocess=reprocess, **kw).process(sta, grid, background=bg)
    assert via_facade is not None and direct is not None
    np.testing.assert_allclose(
        np.asarray(via_facade.values, float), np.asarray(direct.values, float), equal_nan=True
    )


def test_radius_params_keep_decimals():
    """千米半径允许小数，不能被取整（曾因 int() 把 12.5 截成 12）。"""
    assert InterpSgGaussian(halfR=12.5).halfR == 12.5
    assert InterpSg(method="gaussian", halfR=12.5)._impl.halfR == 12.5
    assert InterpSg(method="idw", effectR=300.5)._impl.effectR == 300.5
    with pytest.raises(ValueError, match="halfR"):
        InterpSgGaussian(halfR=0.0)
