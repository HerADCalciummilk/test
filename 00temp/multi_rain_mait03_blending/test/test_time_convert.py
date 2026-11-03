# -*- coding: utf-8 -*-
from mait_3_plugin_util import _user_time_to_job_time, _analysis_time1
import datetime


def _init_from_user(time_input):
    job = _user_time_to_job_time(time_input)
    dt = datetime.datetime.strptime(job, "%Y%m%d%H%M")
    y, m, d, h = _analysis_time1(dt)
    return f"{y:04d}{m:02d}{d:02d}{h:02d}"


def test_utc_00_stays_that_day_00z():
    assert _user_time_to_job_time("202608200000") == "202608202000"
    assert _init_from_user("202608200000") == "2026082000"
    assert _init_from_user("2026082000") == "2026082000"


def test_utc_12_stays_that_day_12z():
    assert _user_time_to_job_time("202608201200") == "202608210800"
    assert _init_from_user("202608201200") == "2026082012"


def test_old_job_times_unchanged():
    assert _user_time_to_job_time("202608202000") == "202608202000"
    assert _user_time_to_job_time("202608210800") == "202608210800"
    assert _init_from_user("202608202000") == "2026082000"
    assert _init_from_user("202608210800") == "2026082012"
