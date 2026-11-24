# -*- coding: utf-8 -*-
from datetime import datetime

from cli.frequency_matching_rain03_cli import (
    _expand_run_times,
    _is_datetime_token,
    _para_for,
    _parse_token,
)


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
    assert _parse_token("2026082000") == datetime(2026, 8, 20, 0, 0)
    assert _parse_token("202608200000") == datetime(2026, 8, 20, 0, 0)


def test_expand_single_and_range():
    assert _expand_run_times("2026082000") == [datetime(2026, 8, 20, 0, 0)]
    assert _expand_run_times(["2026082000", "2026082002"]) == [
        datetime(2026, 8, 20, 0, 0),
        datetime(2026, 8, 20, 1, 0),
        datetime(2026, 8, 20, 2, 0),
    ]


def test_para_for_ecmwf():
    configs = {"ecmwf": {"model_template": "a", "fact_template": "b", "output_template": "c"}}
    para, key = _para_for(configs, "ecmwf", "ecmwf", _Log())
    assert key == "ecmwf"
    assert para["model_template"] == "a"
