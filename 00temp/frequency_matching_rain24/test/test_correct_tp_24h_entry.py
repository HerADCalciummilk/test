# -*- coding: utf-8 -*-
"""CLI 入口层次：不启动订正。站点→格点走 InterpSg，不再经 GressManInterpolation。"""
import inspect
import pickle
from datetime import datetime, timedelta


def test_process_is_module_entry_with_runtime_args():
    from pathlib import Path

    import cli.frequency_matching_rain24_cli as entry
    from interpolation import bilinear_interp, mesh_val
    from utils.merge_params import merge_params

    source = Path(entry.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("import correct_tp_24h")
        assert not stripped.startswith("from correct_tp_24h import")
        assert not stripped.startswith("from correct_tp_24h.")
        assert "GressManInterpolation" not in stripped
    assert not hasattr(entry, "correct_24H_TP")
    assert inspect.unwrap(entry.process) is not None
    assert isinstance(entry.process, type(merge_params()(lambda: None))) or callable(entry.process)
    names = inspect.unwrap(entry.process).__code__.co_varnames
    assert names[:4] == ("match_mode", "plugin", "rpt_times", "pro_count")
    for key in (
        "station_info", "mask_nc", "ipt_model", "ipt_obs", "ipt_type", "opt_type", "over_w",
        "start_dtime", "end_dtime", "inter_dtime1", "inter_dtime2", "report_inter",
        "res", "clip_coords", "config",
    ):
        assert key in names
    assert callable(mesh_val) and callable(bilinear_interp)
    slice_fn, grid_fn, lag = entry.util._cressman_and_lagrangian("original")
    assert slice_fn is None and grid_fn is None  # 插件内用 InterpSg(degree_blend=1.0)
    assert lag.__name__ == "Lagrangian"
    slice_fn, grid_fn, lag = entry.util._cressman_and_lagrangian("aligned")
    assert slice_fn.__name__ == "cressman_project_innov"
    assert grid_fn.__name__ == "cressman_project_innov"
    assert lag.__name__ == "LagrangianAligned"


def test_serial_schedule_matches_expand_helpers(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    rpt = ["2025100100", "2025100112"]
    defaults = inspect.signature(inspect.unwrap(entry.process)).parameters
    start_dtime = defaults["start_dtime"].default
    end_dtime = defaults["end_dtime"].default
    inter_dtime1 = defaults["inter_dtime1"].default
    inter_dtime2 = defaults["inter_dtime2"].default
    report_inter = defaults["report_inter"].default
    expected = {
        (report_time.strftime("%Y%m%d%H"), dtime)
        for report_time in entry.util._expand_report_times(rpt, report_inter)
        for dtime in entry.util._expand_dtime_list(
            start_dtime, end_dtime, inter_dtime1, inter_dtime2
        )
    }

    called = []

    def fake_one(**kw):
        called.append((kw["report_time"].strftime("%Y%m%d%H"), kw["dtime"], kw["plugin"]))

    monkeypatch.setattr(entry, "_process", fake_one)
    inspect.unwrap(entry.process)(plugin="dummy.json", rpt_times=rpt, pro_count=1)
    assert {(item[0], item[1]) for item in called} == expected
    assert {item[2] for item in called} == {"dummy.json"}
    assert len(called) == len(expected)


def test_process_requires_plugin_and_rpt_times():
    import cli.frequency_matching_rain24_cli as entry

    raw = inspect.unwrap(entry.process)
    try:
        raw(plugin=None, rpt_times=["2025100100"], pro_count=1)
    except ValueError as exc:
        assert "plugin" in str(exc)
    else:
        raise AssertionError("缺少 plugin 时应报错")
    try:
        raw(plugin="dummy.json", rpt_times=None, pro_count=1)
    except ValueError as exc:
        assert "rpt_times" in str(exc)
    else:
        raise AssertionError("缺少 rpt_times 时应报错")


def test_process_is_picklable():
    import cli.frequency_matching_rain24_cli as entry

    again = pickle.loads(pickle.dumps(entry.process))
    assert callable(again)


def test_multi_dispatches_the_same_tasks(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    seen = {}

    class FakeTool:
        def __init__(self, target_func, parallel_mode, with_return, num_process, fixed_params=None):
            seen["target"] = target_func
            seen["mode"] = parallel_mode
            seen["num_process"] = num_process
            seen["fixed"] = fixed_params

        def process(self, parallel_params):
            seen["parallel"] = parallel_params

    monkeypatch.setattr(entry, "SimpleParallelTool", FakeTool)
    inspect.unwrap(entry.process)(plugin="dummy.json", rpt_times=["2025100100"], pro_count=2)
    assert seen["target"] is entry._process
    assert seen["num_process"] == 2
    assert seen["fixed"]["plugin"] == "dummy.json"
    assert seen["fixed"]["match_mode"] == "aligned"
    defaults = inspect.signature(inspect.unwrap(entry.process)).parameters
    expect_dtimes = entry.util._expand_dtime_list(
        defaults["start_dtime"].default,
        defaults["end_dtime"].default,
        defaults["inter_dtime1"].default,
        defaults["inter_dtime2"].default,
    )
    assert seen["parallel"]["dtime"] == expect_dtimes
    assert {item.strftime("%Y%m%d%H") for item in seen["parallel"]["report_time"]} == {"2025100100"}


def test_pro_count_one_stays_in_process(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    def forbid_pool(*args, **kwargs):
        raise AssertionError("pro_count=1 不应启动进程池")

    called = []
    monkeypatch.setattr(entry, "SimpleParallelTool", forbid_pool)
    monkeypatch.setattr(
        entry,
        "_process",
        lambda **kw: called.append(kw["plugin"]),
    )
    inspect.unwrap(entry.process)(plugin="dummy.json", rpt_times=["2025100100"], pro_count=1)
    assert called
    assert set(called) == {"dummy.json"}
