# -*- coding: utf-8 -*-
"""correct_tp_24h_entry 的调用层次：不启动订正。"""
import inspect
import pickle
from datetime import datetime, timedelta


def test_class_owns_algorithm_and_plugin():
    from pathlib import Path

    import cli.frequency_matching_rain24_cli as entry
    from frequency_matching_rain24_plugin import Lagrangian, OpticalFlow
    from interpolation import GressManInterpolation, bilinear_interp, mesh_val
    from utils.base_plugin import BasePlugin

    source = Path(entry.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("import correct_tp_24h")
        assert not stripped.startswith("from correct_tp_24h import")
        assert not stripped.startswith("from correct_tp_24h.")
    assert issubclass(entry.correct_24H_TP, entry.gain_dataset)
    assert issubclass(entry.correct_24H_TP, BasePlugin)
    assert entry.correct_24H_TP.optical_flow_cls is OpticalFlow
    assert entry.correct_24H_TP.lagrangian_cls is Lagrangian
    assert entry.correct_24H_TP.cressman_fn is GressManInterpolation
    assert entry.correct_24H_TP.mesh_val_fn is mesh_val
    assert entry.correct_24H_TP.bilinear_fn is bilinear_interp
    assert entry.correct_24H_TP.cycle_correct_Slice.__module__ == "cli.frequency_matching_rain24_cli"
    shell = entry.correct_24H_TP()
    assert shell.bool is False
    assert shell.mainProc() is None


def test_process_is_class_entry_with_runtime_args():
    from pathlib import Path

    import cli.frequency_matching_rain24_cli as entry

    source = Path(entry.__file__).read_text(encoding="utf-8")
    assert "get_runtime_config" not in source
    assert "conf.ini" not in source
    assert "process" not in entry.__dict__
    names = inspect.unwrap(entry.correct_24H_TP.process.__func__).__code__.co_varnames
    assert names[:4] == ("cls", "plugin", "rpt_times", "pro_count")
    for key in (
        "station_info", "mask_nc", "ipt_model", "ipt_obs", "ipt_type", "opt_type", "over_w",
        "start_dtime", "end_dtime", "inter_dtime1", "inter_dtime2", "report_inter",
        "res", "clip_coords",
    ):
        assert key in names
    for key in ("is_multi", "default_plugin", "rpt_list"):
        assert key not in names


def test_class_call_enters_process(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    seen = []

    def fake(cls, plugin, rpt_times, pro_count=1):
        seen.append((plugin, rpt_times, pro_count))

    monkeypatch.setattr(entry.correct_24H_TP, "process", classmethod(fake))
    entry.correct_24H_TP.process(plugin="a.json", rpt_times=["2025100100"], pro_count=3)
    entry.correct_24H_TP()(plugin="b.json", rpt_times=["2025100112"], pro_count=1)
    assert seen == [("a.json", ["2025100100"], 3), ("b.json", ["2025100112"], 1)]


def test_process_single_is_the_correction(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    job = entry.correct_24H_TP.__new__(entry.correct_24H_TP)
    job.bool = True
    seen = {}

    def fake_cycle(self):
        seen["cycle"] = True
        return ["slice"]

    def fake_sta(self, slices):
        seen["slices"] = slices
        return None

    monkeypatch.setattr(entry.correct_24H_TP, "cycle_correct_Slice", fake_cycle)
    monkeypatch.setattr(entry.correct_24H_TP, "_correct_current_TP_sta", fake_sta)
    job.mainProc()
    assert seen["cycle"] is True
    assert seen["slices"] == ["slice"]


def test_serial_schedule_matches_legacy_tasks(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    rpt = ["2025100100", "2025100112"]
    defaults = inspect.signature(entry.correct_24H_TP.process).parameters
    start_dtime = defaults["start_dtime"].default
    end_dtime = defaults["end_dtime"].default
    inter_dtime1 = defaults["inter_dtime1"].default
    inter_dtime2 = defaults["inter_dtime2"].default
    report_inter = defaults["report_inter"].default
    stime = datetime.strptime(rpt[0], "%Y%m%d%H")
    etime = datetime.strptime(rpt[1], "%Y%m%d%H")
    legacy = set()
    cursor = etime
    while cursor >= stime:
        begin = start_dtime
        while begin <= end_dtime:
            legacy.add((cursor.strftime("%Y%m%d%H"), begin))
            begin += inter_dtime1 if begin < 60 else inter_dtime2
        cursor -= timedelta(hours=report_inter)

    called = []

    def fake_one(plugin, param, **run):
        called.append((plugin, param["report_time"].strftime("%Y%m%d%H"), param["dtime"]))

    monkeypatch.setattr(entry.correct_24H_TP, "process_single", staticmethod(fake_one))
    entry.correct_24H_TP.process(plugin="dummy.json", rpt_times=rpt, pro_count=1)

    assert {(item[1], item[2]) for item in called} == legacy
    assert {item[0] for item in called} == {"dummy.json"}
    assert len(called) == len(legacy)


def test_one_builds_instance_and_calls_process_single(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    calls = []

    def fake_init(self, parafile=None, report_time=None, dtime=None, **run):
        self.parafile = parafile
        self.rpt = report_time
        self.dtime = dtime
        self.bool = False
        calls.append(("init", parafile, dtime))

    def fake_single(self):
        calls.append(("run", self.parafile, self.dtime))

    monkeypatch.setattr(entry.correct_24H_TP, "__init__", fake_init)
    monkeypatch.setattr(entry.correct_24H_TP, "mainProc", fake_single)
    when = datetime(2025, 10, 1, 0)
    entry.correct_24H_TP.process_single("p.json", {"report_time": when, "dtime": 36})
    assert calls == [("init", "p.json", 36), ("run", "p.json", 36)]


def test_one_is_picklable():
    import cli.frequency_matching_rain24_cli as entry

    again = pickle.loads(pickle.dumps(entry.correct_24H_TP.process_single))
    assert callable(again)
    assert getattr(again, "__func__", again) is getattr(
        entry.correct_24H_TP.process_single, "__func__", entry.correct_24H_TP.process_single
    )


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
    entry.correct_24H_TP.process(
        plugin="dummy.json",
        rpt_times=["2025100100"],
        pro_count=2,
    )
    target = seen["target"]
    expected = entry.correct_24H_TP.process_single
    assert getattr(target, "__func__", target) is getattr(expected, "__func__", expected)
    assert seen["num_process"] == 2
    assert seen["fixed"]["plugin"] == "dummy.json"
    tasks = seen["parallel"]["param"]
    defaults = inspect.signature(entry.correct_24H_TP.process).parameters
    expect_dtimes = entry._expand_dtime_list(
        defaults["start_dtime"].default,
        defaults["end_dtime"].default,
        defaults["inter_dtime1"].default,
        defaults["inter_dtime2"].default,
    )
    assert [item["dtime"] for item in tasks] == expect_dtimes
    assert {item["report_time"].strftime("%Y%m%d%H") for item in tasks} == {"2025100100"}


def test_pro_count_one_stays_in_process(monkeypatch):
    import cli.frequency_matching_rain24_cli as entry

    def forbid_pool(*args, **kwargs):
        raise AssertionError("pro_count=1 不应启动进程池")

    called = []
    monkeypatch.setattr(entry, "SimpleParallelTool", forbid_pool)
    monkeypatch.setattr(
        entry.correct_24H_TP,
        "process_single",
        staticmethod(lambda plugin, param, **run: called.append(plugin)),
    )
    entry.correct_24H_TP.process(plugin="dummy.json", rpt_times=["2025100100"], pro_count=1)
    assert called
    assert set(called) == {"dummy.json"}
