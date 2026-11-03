# -*- coding: utf-8 -*-
from datetime import datetime

from runner import _is_datetime_token, _parse_run_datetime, _select_data_key_and_runtimes


class _Log:
    def write_error(self, *args, **kwargs):
        pass

    def write_info(self, *args, **kwargs):
        pass


def test_accept_10_and_12_digit_tokens():
    assert _is_datetime_token("2026082000")
    assert _is_datetime_token("202608200000")
    assert not _is_datetime_token("20260820")
    assert not _is_datetime_token("ecmwf")


def test_parse_10_digit_as_hourly():
    assert _parse_run_datetime("2026082000") == datetime(2026, 8, 20, 0, 0)
    assert _parse_run_datetime("202608200000") == datetime(2026, 8, 20, 0, 0)


def test_select_ecmwf_10_digit():
    configs = {"ecmwf": {"model_template": "a", "fact_template": "b", "output_template": "c"}}
    para, run_dts, key = _select_data_key_and_runtimes(
        ["ecmwf", "2026082000"], configs, "ecmwf", _Log())
    assert key == "ecmwf"
    assert run_dts == [datetime(2026, 8, 20, 0, 0)]
    assert para["model_template"] == "a"
