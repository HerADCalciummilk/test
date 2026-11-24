# -*- coding: utf-8 -*-
"""基础结构与环境测试。"""


def test_project_layout():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for name in ("cli", "docs", "nbs", "resource", "src", "test", "utils", "00log", "00temp"):
        assert (root / name).is_dir(), f"missing directory: {name}"
    assert (root / "NIMM_list.md").is_file()


def test_import_core_modules():
    import cli.frequency_matching_rain24_cli as correct_tp_24h
    from cli import __main__ as cli_main
    from utils import config, util_env, data_proc, data_save
    from utils.multipro_plugin import SimpleParallelTool
    from utils.data_prepare_plugin import prepare_dataset

    assert hasattr(config, "fact_level")
    assert hasattr(data_proc, "creat_M3_grd")
    assert hasattr(data_save, "write_griddata")
    assert hasattr(correct_tp_24h.correct_24H_TP, "process")
    assert hasattr(correct_tp_24h.correct_24H_TP, "process_single")
    assert hasattr(correct_tp_24h.correct_24H_TP, "process_multi")
    wrapped = correct_tp_24h.correct_24H_TP.process.__func__
    assert wrapped.__nimm_submodule__ == "frequency_matching_rain24"
    assert wrapped.__nimm_ini__ == "resource/conf.ini"
    assert hasattr(cli_main, "main")
    assert hasattr(util_env, "get_resolved_paths")
    assert hasattr(util_env, "get_default_is_multi")
    assert hasattr(util_env, "get_default_pro_count")
    assert SimpleParallelTool is not None
    assert callable(prepare_dataset)


def test_expand_schedules():
    import cli.frequency_matching_rain24_cli as m

    dtimes = m._expand_dtime_list(36, 252, 12, 12)
    assert dtimes[0] == 36
    assert dtimes[-1] <= 252
    assert all(isinstance(x, int) for x in dtimes)

    times = m._expand_report_times(["2025100100"], 12)
    assert len(times) == 1
    assert times[0].strftime("%Y%m%d%H") == "2025100100"


def test_schedule_matches_legacy_pool_tasks(monkeypatch):
    """调度任务集必须与原 Pool 双层循环一致，且每个任务只调用 correctTP_24。"""
    from datetime import datetime, timedelta

    import cli.frequency_matching_rain24_cli as m

    rpt = ["2025100100", "2025100112"]
    stime = datetime.strptime(rpt[0], "%Y%m%d%H")
    etime = datetime.strptime(rpt[1], "%Y%m%d%H")
    legacy = set()
    e = etime
    while e >= stime:
        begin = 36
        while begin <= 252:
            legacy.add((e.strftime("%Y%m%d%H"), begin))
            begin += 12
        e -= timedelta(hours=12)

    called = []

    def _fake_one(plugin, param, **run):
        called.append((param["report_time"].strftime("%Y%m%d%H"), param["dtime"]))

    monkeypatch.setattr(m.correct_24H_TP, "process_single", staticmethod(_fake_one))
    m.correct_24H_TP.process(plugin="dummy.json", rpt_times=rpt, pro_count=1)

    assert set(called) == legacy
    assert len(called) == len(legacy)


def test_process_decorator_knows_submodule_and_ini():
    import cli.frequency_matching_rain24_cli as entry

    wrapped = entry.correct_24H_TP.process.__func__
    assert wrapped.__nimm_submodule__ == "frequency_matching_rain24"
    assert wrapped.__nimm_ini__ == "resource/conf.ini"


def test_origin_binds_original_modules():
    import cli.frequency_matching_rain24_cli as origin

    assert origin.correct_24H_TP.optical_flow_cls.__module__ == "frequency_matching_rain24_plugin"
    assert origin.correct_24H_TP.lagrangian_cls.__module__ == "frequency_matching_rain24_plugin"
    assert origin.correct_24H_TP.cressman_fn.__module__ == "interpolation"
    assert origin.correct_24H_TP.mesh_val_fn.__module__ == "interpolation"
    assert origin.correct_24H_TP.bilinear_fn.__module__ == "interpolation"
    assert "backend" not in origin.correct_24H_TP.process.__func__.__code__.co_varnames


def test_resolved_paths():
    from utils.util_env import get_resolved_paths

    paths = get_resolved_paths()
    assert "station_info" in paths
    assert "mask_nc" in paths
    assert "default_plugin" in paths
    assert paths["station_info"].endswith("sta.m3")


def test_cli_forwards_process_arguments(monkeypatch, tmp_path):
    import cli.frequency_matching_rain24_cli as cli_mod

    seen = {}

    def fake_multi(cls, plugin, params, pro_count, run):
        seen["plugin"] = plugin
        seen["pro_count"] = pro_count
        seen["run"] = run
        seen["dtime"] = params[0]["dtime"]
        seen["count"] = len(params)

    monkeypatch.setattr(cli_mod.correct_24H_TP, "process_multi", classmethod(fake_multi))
    ext = tmp_path / "ext.ini"
    ext.write_text("ipt_model=9\npro_count=2\nstart_dtime=24\nrpt_times=2025100100\n", encoding="utf-8")
    cli_mod.correct_24H_TP.process(
        plugin="resource/CMA_MESO.json",
        pro_count=8,
        config=str(ext),
    )
    assert seen["plugin"] == "resource/CMA_MESO.json"
    assert seen["pro_count"] == 8
    assert seen["run"]["ipt_model"] == 9
    assert seen["dtime"] == 24
    assert seen["run"]["station_info"].endswith("sta.m3")
    assert seen["count"] == 20

    seen.clear()

    def fake_single(plugin, param, **run):
        seen["plugin"] = plugin
        seen["run"] = run
        seen["rpt"] = param["report_time"]

    monkeypatch.setattr(cli_mod.correct_24H_TP, "process_single", staticmethod(fake_single))
    cli_mod.correct_24H_TP.process(
        plugin="resource/CMA_MESO.json",
        rpt_times=["2025100100"],
        pro_count=1,
        ipt_model=3,
    )
    assert seen["plugin"] == "resource/CMA_MESO.json"
    assert seen["run"]["ipt_model"] == 3
    assert seen["run"]["ipt_obs"] == 1



def test_process_reads_required_keys_from_ini(monkeypatch):
    import cli.frequency_matching_rain24_cli as runner

    seen = {}

    def fake_multi(cls, plugin, params, pro_count, run):
        seen["plugin"] = plugin
        seen["pro_count"] = pro_count
        seen["times"] = [item["report_time"].strftime("%Y%m%d%H") for item in params]

    monkeypatch.setattr(runner.correct_24H_TP, "process_multi", classmethod(fake_multi))
    runner.correct_24H_TP.process()
    assert seen["plugin"].endswith("ecmwf.json")
    assert seen["pro_count"] == 4
    assert "2026081200" in seen["times"]
    assert "2026081312" in seen["times"]
