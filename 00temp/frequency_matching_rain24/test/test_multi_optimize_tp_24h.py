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
    for key in ("--plugin", "--rpt-list", "--is-multi", "--pro-count", "correct_tp_24h.process"):
        assert key in help_text


def test_resolved_paths():
    from utils.util_env import get_resolved_paths

    paths = get_resolved_paths()
    assert "station_info" in paths
    assert "mask_nc" in paths
    assert "default_plugin" in paths
    assert paths["station_info"].endswith("sta.m3")
