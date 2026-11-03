# -*- coding: utf-8 -*-
"""基础结构与环境测试。"""


def test_project_layout():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for name in ("cli", "docs", "nbs", "resource", "src", "test", "utils", "00log", "00temp"):
        assert (root / name).is_dir(), f"missing directory: {name}"
    assert (root / "NIMM_list.md").is_file()


def test_import_core_modules():
    import correct_tp_24h
    from cli import __main__ as cli_main
    from utils import config, util_env, data_proc, data_save
    from utils.multipro_plugin import SimpleParallelTool
    from utils.data_prepare_plugin import prepare_dataset

    assert hasattr(config, "fact_level")
    assert hasattr(data_proc, "creat_M3_grd")
    assert hasattr(data_save, "write_griddata")
    assert hasattr(correct_tp_24h, "process")
    assert hasattr(correct_tp_24h, "process_single")
    assert hasattr(correct_tp_24h, "process_multi")
    assert hasattr(correct_tp_24h, "mainProcess")
    assert hasattr(cli_main, "main")
    assert hasattr(util_env, "get_resolved_paths")
    assert hasattr(util_env, "get_default_is_multi")
    assert hasattr(util_env, "get_default_pro_count")
    assert SimpleParallelTool is not None
    assert callable(prepare_dataset)


def test_expand_schedules():
    import correct_tp_24h as m

    dtimes = m._expand_dtime_list()
    assert dtimes[0] == m.start_dtime
    assert dtimes[-1] <= m.end_dtime
    assert all(isinstance(x, int) for x in dtimes)

    times = m._expand_report_times(["2025100100"])
    assert len(times) == 1
    assert times[0].strftime("%Y%m%d%H") == "2025100100"


def test_schedule_matches_legacy_pool_tasks(monkeypatch):
    """调度任务集必须与原 Pool 双层循环一致，且每个任务只调用 correctTP_24。"""
    from datetime import datetime, timedelta

    import correct_tp_24h as m

    rpt = ["2025100100", "2025100112"]
    # 旧逻辑展开
    stime = datetime.strptime(rpt[0], "%Y%m%d%H")
    etime = datetime.strptime(rpt[1], "%Y%m%d%H")
    legacy = set()
    e = etime
    while e >= stime:
        begin = m.start_dtime
        while begin <= m.end_dtime:
            legacy.add((e.strftime("%Y%m%d%H"), begin))
            begin += m.inter_dtime1 if begin < 60 else m.inter_dtime2
        e -= timedelta(hours=m.report_inter)

    called = []

    def _fake_correct(parafile, report_time, dtime):
        called.append((report_time.strftime("%Y%m%d%H"), dtime))

    monkeypatch.setattr(m, "correctTP_24", _fake_correct)
    m.process(plugin="dummy.json", is_multi=False, pro_count=1, rpt_times=rpt)

    assert set(called) == legacy
    assert len(called) == len(legacy)


def test_cli_help():
    import pytest
    from cli import __main__ as cli_main

    with pytest.raises(SystemExit) as ei:
        cli_main.main(["--help"])
    assert ei.value.code == 0

    parser = cli_main._build_parser()
    help_text = parser.format_help()
    for key in (
        "--plugin",
        "--config",
        "--rpt-list",
        "--is-multi",
        "--pro-count",
        "correct_tp_24h.process",
        "frequency_matching_rain24_cli.py",
    ):
        assert key in help_text
    assert "--backend" not in help_text
    assert "correct_tp_24h_nowcast" in help_text


def test_two_mains_bind_their_own_modules():
    import correct_tp_24h as origin
    import correct_tp_24h_nowcast as project

    assert origin.correct_24H_TP.optical_flow_cls.__module__ == "cal_optical_flow"
    assert origin.correct_24H_TP.lagrangian_cls.__module__ == "cal_optical_flow"
    assert origin.correct_24H_TP.cressman_fn.__module__ == "interpolation"
    assert origin.correct_24H_TP.mesh_val_fn.__module__ == "interpolation"
    assert origin.correct_24H_TP.bilinear_fn.__module__ == "interpolation"
    assert project.correct_24H_TP_Nowcast.optical_flow_cls.__module__ == "cal_optical_flow_nowcast"
    assert project.correct_24H_TP_Nowcast.lagrangian_cls.__module__ == "cal_optical_flow_nowcast"
    assert project.correct_24H_TP_Nowcast.cressman_fn.__module__ == "interpolation_sg_cressman"
    assert project.correct_24H_TP_Nowcast.mesh_val_fn.__module__ == "interpolation_gg_linear"
    assert project.correct_24H_TP_Nowcast.bilinear_fn.__module__ == "interpolation_gg_linear"
    assert "backend" not in origin.process.__code__.co_varnames
    assert not issubclass(project.correct_24H_TP_Nowcast, origin.correct_24H_TP)
    assert project.correct_24H_TP_Nowcast.__module__ == "correct_tp_24h_nowcast"
    assert "correct_tp_24h" not in project.__dict__


def test_project_bilinear_keeps_old_shapes():
    import meteva.base as meb
    import numpy as np
    import pandas as pd

    from interpolation_gg_linear import bilinear_interp, mesh_val

    grid = meb.grid([100, 101, 0.5], [30, 31, 0.5])
    values = np.arange(9, dtype=float).reshape(1, 1, 1, 1, 3, 3)
    grd = meb.grid_data(grid, values)
    out = mesh_val(grd, [100, 101, 30, 31, 0.5])
    assert tuple(np.asarray(out.values).squeeze().shape) == (3, 3)

    sta = pd.DataFrame({"id": [1, 2], "lon": [100.25, 120.0], "lat": [30.25, 40.0], "data0": [0.0, 0.0]})
    sta2 = bilinear_interp(out, sta, dbUndef=0.0)
    assert len(sta2) == len(sta)
    assert np.isfinite(sta2["data0"].iloc[0])
    assert sta2["data0"].iloc[1] == 0.0


def test_nowcast_cressman_stays_inside_slice_neighborhood():
    import meteva.base as meb
    import numpy as np
    import pandas as pd

    from correct_tp_24h_nowcast import correct_by_opticalFlow_nowcast
    from interpolation_gg_linear import mesh_val

    grid = meb.grid([100, 110, 0.5], [20, 30, 0.5])
    nlon = int(round((110 - 100) / 0.5)) + 1
    nlat = int(round((30 - 20) / 0.5)) + 1
    grd = meb.grid_data(grid, np.zeros((1, 1, 1, 1, nlat, nlon)))
    sta = pd.DataFrame(
        {"id": [1, 2], "lon": [103.0, 109.0], "lat": [23.0, 29.0], "data0": [1.0, 2.0]}
    )
    seen = {}

    def _cressman(sta_in, grd_in, radii, rain_limit=None):
        seen["nlon"] = meb.basicdata.get_grid_of_data(grd_in).nlon
        seen["nsta"] = len(sta_in)
        seen["radii"] = list(radii)
        return grd_in

    worker = correct_by_opticalFlow_nowcast(
        [[0], [1.0]],
        [102, 105, 22, 25],
        [grd],
        [grd],
        [sta],
        cressman_fn=_cressman,
        mesh_val_fn=mesh_val,
    )
    worker.gain_his_slice(0)
    assert seen["nlon"] < nlon
    assert seen["nsta"] == 1
    assert seen["radii"] == [1.0, 0.8, 0.6, 0.4]


def test_nowcast_process_uses_its_own_task(monkeypatch):
    import correct_tp_24h as origin
    import correct_tp_24h_nowcast as project

    origin_called = []
    project_called = []

    def _origin(parafile, report_time, dtime):
        origin_called.append(dtime)

    def _project(parafile, report_time, dtime):
        project_called.append(dtime)

    monkeypatch.setattr(origin, "correctTP_24", _origin)
    monkeypatch.setattr(project, "correctTP_24", _project)
    project.process(plugin="dummy.json", is_multi=False, pro_count=1, rpt_times=["2025100100"])
    assert project_called
    assert origin_called == []


def test_resolved_paths():
    from utils.util_env import get_resolved_paths

    paths = get_resolved_paths()
    assert "station_info" in paths
    assert "mask_nc" in paths
    assert "default_plugin" in paths
    assert paths["station_info"].endswith("sta.m3")


def test_cli_forwards_process_arguments(monkeypatch):
    from cli import frequency_matching_rain24_cli as cli_mod

    seen = {}

    def fake_process(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(cli_mod, "process", fake_process)
    code = cli_mod.frequency_matching_rain24_cli(
        [
            "--plugin=resource/CMA_MESO.json",
            "--config=resource/optimize_tp_24.ini",
            "--rpt-list=2025100100,2025100112",
            "--is-multi",
            "false",
            "--pro-count",
            "8",
        ]
    )
    assert code == 0
    assert seen["plugin"] == "resource/CMA_MESO.json"
    assert seen["config"] == "resource/optimize_tp_24.ini"
    assert seen["rpt_list"] == ["2025100100", "2025100112"]
    assert seen["is_multi"] is False
    assert seen["pro_count"] == 8
    for key in (
        "default_plugin",
        "log_file",
        "station_info",
        "mask_nc",
        "ipt_model",
        "ipt_obs",
        "ipt_type",
        "opt_type",
        "over_w",
        "start_dtime",
        "end_dtime",
        "inter_dtime1",
        "inter_dtime2",
        "report_inter",
        "res",
        "clip_coords",
    ):
        assert seen[key] is None, key

    seen.clear()
    code = cli_mod.FrequencyMatchingRain24Cli.call(
        plugin="resource/CMA_MESO.json",
        is_multi=True,
        pro_count=4,
    )
    assert code == 0
    assert seen["plugin"] == "resource/CMA_MESO.json"
    assert seen["config"] is None
    assert seen["rpt_list"] is None
    assert seen["is_multi"] is True
    assert seen["pro_count"] == 4


def test_process_uses_external_config(monkeypatch, tmp_path):
    import correct_tp_24h as runner
    from utils.util_env import get_default_is_multi, get_default_pro_count, get_resolved_paths

    ini = tmp_path / "ext.ini"
    ini.write_text(
        "\n".join(
            [
                "rpt_list=2026010100",
                "is_multi=false",
                "pro_count=2",
                "default_plugin=resource/CMA_MESO.json",
            ]
        ),
        encoding="utf-8",
    )
    seen = {}

    def fake_schedule(plugin, is_multi, pro_count, rpt_times, config=None):
        seen["rpt_list"] = list(runner.rpt_list)
        seen["is_multi"] = get_default_is_multi()
        seen["pro_count"] = get_default_pro_count()
        seen["plugin"] = get_resolved_paths()["default_plugin"]
        seen["config"] = config

    before = list(runner.rpt_list)
    monkeypatch.setattr(runner, "_schedule", fake_schedule)
    runner.process(config=str(ini))

    assert seen["rpt_list"] == ["2026010100"]
    assert seen["is_multi"] is False
    assert seen["pro_count"] == 2
    assert seen["plugin"].endswith("CMA_MESO.json")
    assert seen["config"] == str(ini)
    assert list(runner.rpt_list) == before
    assert get_default_is_multi() is True


def test_call_overrides_apply_and_clear_on_error(monkeypatch):
    import correct_tp_24h as runner
    from utils.util_env import get_call_overrides, get_resolved_paths, get_runtime_config

    seen = {}

    def fake_schedule(plugin, is_multi, pro_count, rpt_times, config=None):
        cfg = get_runtime_config()
        seen["plugin"] = plugin
        seen["rpt_times"] = rpt_times
        seen["rpt_list"] = list(runner.rpt_list)
        seen["res"] = cfg["res"]
        seen["slon"] = cfg["slon"]
        seen["elon"] = cfg["elon"]
        seen["slat"] = cfg["slat"]
        seen["elat"] = cfg["elat"]
        seen["default_plugin"] = get_resolved_paths()["default_plugin"]
        raise RuntimeError("stop")

    before_res = get_runtime_config()["res"]
    monkeypatch.setattr(runner, "_schedule", fake_schedule)
    try:
        runner.process(
            plugin="explicit.json",
            default_plugin="resource/CMA_MESO.json",
            rpt_times=["2026020200"],
            rpt_list=["2026010100"],
            res=0.25,
            clip_coords=[1.0, 2.0, 3.0, 4.0],
        )
    except RuntimeError as exc:
        assert str(exc) == "stop"
    assert seen["plugin"] == "explicit.json"
    assert seen["rpt_times"] == ["2026020200"]
    assert seen["rpt_list"] == ["2026010100"]
    assert seen["res"] == 0.25
    assert seen["slon"] == 1.0
    assert seen["elon"] == 2.0
    assert seen["slat"] == 3.0
    assert seen["elat"] == 4.0
    assert seen["default_plugin"].endswith("CMA_MESO.json")
    assert get_call_overrides() == {}
    assert get_runtime_config()["res"] == before_res
