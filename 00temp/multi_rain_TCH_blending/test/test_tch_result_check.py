# -*- coding: utf-8 -*-
"""样例数据上检验 TCH 权重与加权场；无数据则跳过。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for _p in (str(_SRC), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_DATA = Path(r"D:\Work\NIMM_pip_testdata\multi_rain_mait24_blending\test_data")
_NEED = _DATA / "ecmwf" / "sfc" / "20260524" / "2026052400.036.m4"
_ARCHIVED = _DATA / "tch" / "sfc" / "20260524" / "micaps" / "2026052400.036.m4"

pytestmark = pytest.mark.skipif(not _NEED.is_file(), reason="缺少 TCH 样例数据")


@pytest.fixture(scope="module")
def tch_run():
    import meteva.base as meb
    from pre_fcst_tch_realtime import (
        clock,
        get_model_data,
        prepare_ensemble_for_tch,
        select_initial_time,
    )
    from tch_blend_plugin import TchBlendPlugin
    from tch_weight_plugin import TchWeightPlugin
    from utils.util_env import resolve_process_args, set_main_ini

    set_main_ini(None)
    cfg = resolve_process_args(
        fcst_hours=[36],
        ipt_type="m4",
        initial_time="20260524120000",
        dir_model_data=str(_DATA) + os.sep,
    )
    mask_path = cfg["maskout_file"]
    if not os.path.isabs(mask_path):
        mask_path = str(_ROOT / mask_path)
    mask = np.fromfile(mask_path, "f").reshape((cfg["ny_mask"], cfg["nx_mask"]), order="C")
    mask_s = mask.reshape(cfg["nx_mask"] * cfg["ny_mask"])
    tm = select_initial_time(
        clock(cfg["initial_time"]),
        cfg["initial_hour_threshold"],
        cfg["initial_hour_late"],
        cfg["initial_hour_early"],
    )
    qpf = get_model_data(
        cfg["dir_model_data"],
        cfg["model_list"],
        tm,
        36,
        cfg["grid_lon"],
        cfg["grid_lat"],
        ipt_type="m4",
    )
    flat, ndim, _, _ = prepare_ensemble_for_tch(qpf, mask_s)
    wout = TchWeightPlugin().process(flat)
    blend = TchBlendPlugin().process(qpf, wout["weights"])
    arr = np.asarray(blend["qpf_combine"].values, float).squeeze()
    return {
        "qpf": qpf,
        "weights": wout["weights"],
        "uct": wout["uct"],
        "arr": arr,
        "ndim": ndim,
        "meb": meb,
    }


def test_weights_valid(tch_run):
    w = tch_run["weights"]
    assert np.isclose(w.sum(), 1.0)
    assert np.all(w >= 0)
    assert np.all(np.isfinite(tch_run["uct"]))
    assert np.all(tch_run["uct"] >= 0)


def test_weight_inverse_to_uncertainty(tch_run):
    from scipy.stats import spearmanr

    rho, _ = spearmanr(tch_run["uct"], tch_run["weights"])
    assert rho < 0


def test_blend_is_weighted_sum(tch_run):
    qpf = tch_run["qpf"]
    w = tch_run["weights"]
    arr = tch_run["arr"]
    manual = None
    for i in range(tch_run["ndim"]):
        field = np.array(qpf[i, 0, 0, 0, :, :], dtype=float) * float(w[i])
        manual = field if manual is None else manual + field
    assert np.nanmax(np.abs(arr - manual)) < 1e-5
    assert np.all(np.isfinite(arr))
    assert float(np.nanmin(arr)) >= -1e-6


def test_close_to_archived_product(tch_run):
    if not _ARCHIVED.is_file():
        pytest.skip("无归档 TCH 产品")
    ref = tch_run["meb"].read_griddata_from_micaps4(str(_ARCHIVED))
    refa = np.asarray(ref.values, float).squeeze()
    arr = tch_run["arr"]
    assert arr.shape == refa.shape
    # 归档 Micaps4 常为 1 位小数
    assert float(np.nanmax(np.abs(arr - refa))) < 0.1
    assert float(np.corrcoef(arr.ravel(), refa.ravel())[0, 1]) > 0.999
