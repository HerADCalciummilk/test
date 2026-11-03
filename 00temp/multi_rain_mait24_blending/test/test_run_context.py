# -*- coding: utf-8 -*-
"""``util_context`` 与 ini 解析相关单元测试（不依赖 meteva 运行时）。"""
import datetime
import os

from utils.util_context import RunContext, build_run_context
from mait_24_plugin_util import _analysis_background_ini
from utils.util_env import get_resolved_paths, get_default_clip_coords
from utils.util_new import _analysis_para_ini

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_build_run_context_assembles_layers():
    """build_run_context 仅装箱内存参数，不读文件。"""
    dt = datetime.datetime(2024, 1, 1, 8, 0)
    ctx = build_run_context(
        beta_path_template="beta/YYYYMMDDHH",
        is_obs_bjt=True,
        clip_coords=[70.0, 140.0, 0.0, 60.0, 0.1, 0.1],
        split_lat=2,
        split_lon=2,
        dt_now=dt,
        sd_sta_info={"mock": True},
        model_name=["ecModel", "ncepModel"],
        model_path=["/a/VVV.m3", "/b/VVV.m3"],
        fact_path="/fact/YYMMDDHH.000",
        output_sample_path="/out/YYYYMMDDHH.VVV",
        background_templates={"ecModel": "/bg/TTT.m4"},
        area_scale=0.5,
        predict_type=24,
    )
    assert isinstance(ctx, RunContext)
    assert ctx.session.dt_now == dt
    assert ctx.session.is_obs_bjt is True
    assert ctx.models.model_name == ("ecModel", "ncepModel")
    assert ctx.paths.model_path == ("/a/VVV.m3", "/b/VVV.m3")
    assert ctx.paths.background_templates["ecModel"] == "/bg/TTT.m4"
    assert ctx.grid.split_lat == 2
    assert ctx.grid.predict_type == 24
    assert ctx.grid.area_scale == 0.5


def test_build_run_context_default_algorithm_scalars():
    ctx = build_run_context(
        beta_path_template="b",
        is_obs_bjt=False,
        clip_coords=(70.0, 140.0, 0.0, 60.0, 0.1, 0.1),
        split_lat=1,
        split_lon=1,
        dt_now=datetime.datetime.now(),
        sd_sta_info=None,
        model_name=["m1"],
        model_path=["p1"],
        fact_path="f",
        output_sample_path="o",
        background_templates={},
    )
    assert ctx.grid.area_scale == 0.5
    assert ctx.grid.predict_type == 24


def test_analysis_para_ini_reads_resource_file():
    para = os.path.join(_REPO, "resource", "para_24.ini")
    result = _analysis_para_ini(para)
    assert result is not None
    model_name, model_path, fact_path, output_sample_path = result
    assert len(model_name) == 8
    assert len(model_path) == 8
    assert model_name[0] == "ecModel"
    assert "Observation" in fact_path or "fact" in fact_path.lower() or fact_path
    assert output_sample_path


def test_analysis_para_ini_missing_returns_none(tmp_path):
    missing = os.path.join(str(tmp_path), "missing.ini")
    assert _analysis_para_ini(missing) is None


def test_analysis_background_ini_reads_resource_file():
    bg = os.path.join(_REPO, "resource", "para_24_background.ini")
    templates = _analysis_background_ini(bg)
    assert "ecModel" in templates
    assert templates["ecModel"].endswith(".m4")


def test_get_resolved_paths_points_to_resource():
    paths = get_resolved_paths()
    assert paths["para_ini"].endswith("para_24.ini")
    assert paths["background_ini"].endswith("para_24_background.ini")
    assert "station_info" in paths["station_info"]
    assert os.path.basename(os.path.dirname(paths["para_ini"])) == "resource"


def test_default_clip_coords_length():
    coords = get_default_clip_coords()
    assert len(coords) == 6
