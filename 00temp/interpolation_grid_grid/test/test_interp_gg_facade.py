# -*- coding: utf-8 -*-
"""InterpGg 统一入口：分派与结果一致性。"""
from __future__ import annotations

import inspect

import numpy as np
import pytest
import meteva_base as meb

from helpers import make_meb6d, to_compare_array
from interp_gg_conservative_plugin import InterpGgConservative
from interp_gg_cubic_plugin import InterpGgCubic
from interp_gg_linear_plugin import InterpGgLinear
from interp_gg_nearest_plugin import InterpGgNearest
from interp_gg_plugin import InterpGg


def _src_and_target():
    lons = np.arange(70.0, 80.0, 1.0)
    lats = np.arange(20.0, 30.0, 1.0)
    yy, xx = np.meshgrid(np.arange(lats.size), np.arange(lons.size), indexing="ij")
    data = (5.0 + 0.1 * xx + 0.05 * yy).astype(np.float32)
    grd = make_meb6d(data, lats=lats, lons=lons)
    target = meb.basicdata.grid([71, 77, 2.0], [21, 27, 2.0])
    return grd, target


def test_normalize_case_and_only_four_methods():
    assert InterpGg._normalize_method("Linear") == "linear"
    assert InterpGg._normalize_method("CONSERVATIVE") == "conservative"
    for bad in ("unknown", "bilinear", "area_weighted", "landsea"):
        with pytest.raises(ValueError, match="method"):
            InterpGg(method=bad)


def test_signature_lists_all_params():
    params = set(inspect.signature(InterpGg.__init__).parameters)
    assert {"method", "outer_value", "mdtol", "spherical"} <= params


def test_unused_method_params_are_ignored():
    plugin = InterpGg(method="linear", outer_value=0.0, mdtol=0.3, spherical=False)
    assert plugin.method == "linear"
    assert isinstance(plugin._impl, InterpGgLinear)


def test_each_method_matches_direct_plugin():
    grd, target = _src_and_target()
    cases = [
        ("linear", InterpGgLinear(outer_value=0.0), {}),
        ("nearest", InterpGgNearest(outer_value=0.0), {}),
        ("cubic", InterpGgCubic(outer_value=0.0), {}),
        (
            "conservative",
            InterpGgConservative(outer_value=0.0, mdtol=1.0, spherical=True),
            {"mdtol": 1.0, "spherical": True},
        ),
    ]
    for method, direct, extra in cases:
        a = InterpGg(method=method, outer_value=0.0, **extra).process(grd, target)
        b = direct.process(grd, target)
        assert a is not None and b is not None
        np.testing.assert_allclose(
            to_compare_array(a), to_compare_array(b), equal_nan=True, atol=1e-6
        )


def test_conservative_mdtol_validation():
    with pytest.raises(ValueError, match="mdtol"):
        InterpGg(method="conservative", mdtol=1.5)


def test_exported_from_package():
    import sys
    from pathlib import Path

    temp_root = str(Path(__file__).resolve().parents[2])
    if temp_root not in sys.path:
        sys.path.insert(0, temp_root)
    pkg = __import__("interpolation_grid_grid.src", fromlist=["InterpGg", "__all__"])
    assert "InterpGg" in pkg.__all__
    assert pkg.InterpGg.__name__ == "InterpGg"
