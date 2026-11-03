# -*- coding: utf-8 -*-
from mait_3h import process, process_single, process_multi


def test_process_serial_dispatches_each_time_input(monkeypatch):
    calls = []

    def fake_single(*args, **kwargs):
        calls.append(kwargs["param"]["time_input"])

    monkeypatch.setattr("mait_3h.process_single", fake_single)
    process(
        time_inputs=["202503092000", "202503100800"],
        is_multi=False,
        predict_valid_list=[3],
    )
    assert calls == ["202503092000", "202503100800"]


def test_process_multi_uses_parallel_tool(monkeypatch):
    seen = {}

    class _FakeTool:
        def __init__(self, **kwargs):
            seen["num_process"] = kwargs.get("num_process")
            seen["target"] = kwargs.get("target_func")

        def process(self, parallel_params):
            seen["params"] = parallel_params

    monkeypatch.setattr("mait_3h.SimpleParallelTool", _FakeTool)
    process(
        time_inputs=["202503092000", "202503100800"],
        is_multi=True,
        pro_count=4,
        predict_valid_list=[3],
    )
    assert seen["num_process"] == 4
    assert seen["target"] is process_single
    assert [p["time_input"] for p in seen["params"]["param"]] == [
        "202503092000", "202503100800",
    ]


def test_time_input_alias():
    assert callable(process_single)
    assert callable(process_multi)
