# -*- coding: utf-8 -*-
"""``util_context`` 与 background ini 相关单元测试。"""
import datetime
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO, "src")
_ordered = (_REPO, _SRC)
for _p in _ordered:
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed(_ordered):
    sys.path.insert(0, _p)

from utils.util_context import RunContext, build_run_context
from mait_1_plugin_util import _analysis_background_ini
from utils.util_env import get_resolved_paths


def test_build_run_context_assembles_layers():
    dt = datetime.datetime(2024, 1, 1, 8, 0)
    ctx = build_run_context(
        beta_path_template="beta/YYYYMMDDHH",
        is_obs_bjt=True,
        clip_coords=[70.0, 140.0, 0.0, 60.0, 0.1, 0.1],
        split_lat=2,
        split_lon=2,
        dt_now=dt,
        sd_sta_info={"mock": True},
        model_name=["ecmwf", "grapesgfs"],
        model_path=["/a/VVV.m3", "/b/VVV.m3"],
        fact_path="/fact/YYMMDDHH.000",
        output_sample_path="/out/YYYYMMDDHH.VVV",
        background_templates={"ecmwf": "/bg/ec/TTT.m4", "grapesgfs": "/bg/gfs/TTT.m4"},
        area_scale=0.5,
        predict_type=1,
    )
    assert isinstance(ctx, RunContext)
    assert ctx.session.dt_now == dt
    assert ctx.models.model_name == ("ecmwf", "grapesgfs")
    assert ctx.paths.background_templates["ecmwf"] == "/bg/ec/TTT.m4"
    assert ctx.grid.predict_type == 1
    assert ctx.dt_search_base() == dt - datetime.timedelta(hours=8)


def test_analysis_background_ini_reads_resource_file():
    bg = os.path.join(_REPO, "resource", "para_1_background.ini")
    templates = _analysis_background_ini(bg)
    assert "ecmwf" in templates
    assert templates["ecmwf"].endswith("TTT.m4")


def test_util_env_resolves_paths_from_mait_1_ini():
    paths = get_resolved_paths()
    assert paths["background_ini"].endswith("local_background.ini")
    assert paths["para_ini"].endswith("local.ini")
    assert paths["mask_dat"].endswith("mask010.dat")
    ini_path = os.path.join(_REPO, "resource", "mait_1.ini")
    assert os.path.isfile(ini_path)
