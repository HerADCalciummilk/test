# -*- coding: utf-8 -*-
"""主流程 ``RunProcess._setup_context`` 与日志路径单元测试。"""
import datetime
import logging
import os
from unittest.mock import patch

import pandas as pd

import mait_24h
from utils.util_context import RunContext

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fake_sta_info():
    return pd.DataFrame({"id": ["1"], "lon": [110.0], "lat": [30.0], "data0": [0.0]})


def test_setup_context_success(tmp_path):
    """mock 站点读取后，_setup_context 应返回有效 RunContext。"""
    rp = mait_24h.RunProcess(
        time_input="202401010800",
        para_path=os.path.join(_REPO, "resource", "para_24.ini"),
        beta_path=os.path.join(_REPO, "resource", "YYYYMMDDHH"),
        is_obs_bjt=True,
        clip_coords=[70.0, 140.0, 0.0, 60.0, 0.1, 0.1],
        split_lat=1,
        split_lon=1,
        predict_valid_list=[36],
    )
    dt = datetime.datetime(2024, 1, 1, 8, 0)

    with patch("mait_24h._prepare", return_value=(dt, _fake_sta_info())), \
         patch("mait_24h.init_run_log") as mock_log, \
         patch("mait_24h.os.chdir"):
        mock_log.return_value = logging.getLogger("test.setup")
        ctx, env_paths, log = rp._setup_context()

    assert isinstance(ctx, RunContext)
    assert ctx.session.dt_now == dt
    assert len(ctx.models.model_name) == 8
    assert env_paths is not None
    assert log is mock_log.return_value


def test_setup_context_fails_on_bad_para(tmp_path):
    rp = mait_24h.RunProcess(
        time_input="202401010800",
        para_path=os.path.join(str(tmp_path), "no_such_para.ini"),
        beta_path=None,
        is_obs_bjt=True,
        clip_coords=[70.0, 140.0, 0.0, 60.0, 0.1, 0.1],
    )
    with patch("mait_24h._prepare", return_value=(datetime.datetime.now(), _fake_sta_info())), \
         patch("mait_24h.init_run_log", return_value=logging.getLogger("test.fail")), \
         patch("mait_24h.os.chdir"):
        ctx, env_paths, log = rp._setup_context()
    assert ctx is None
    assert log is not None


def test_init_run_log_isolates_by_time_input(tmp_path, monkeypatch):
    """主进程日志文件名应包含 time_input。"""
    from utils import util_new

    fake_base = os.path.join(str(tmp_path), "20250609.txt")

    def fake_get_path(template, dt, dtime):
        return fake_base

    monkeypatch.setattr(util_new.meb, "get_path", fake_get_path)
    monkeypatch.setattr(util_new.mp.current_process(), "name", "MainProcess")

    logger = util_new.init_run_log("log/YYYYMMDD.txt", time_input="202401010800")
    handler = logger.handlers[0]
    assert "202401010800" in handler.baseFilename
    handler.close()


def test_init_run_log_child_adds_pid(tmp_path, monkeypatch):
    """子进程日志文件名应额外包含 pid。"""
    from utils import util_new

    fake_base = os.path.join(str(tmp_path), "20250609.txt")
    pid = os.getpid()

    def fake_get_path(template, dt, dtime):
        return fake_base

    monkeypatch.setattr(util_new.meb, "get_path", fake_get_path)

    class _Proc:
        name = "SpawnProcess-1"

    monkeypatch.setattr(util_new.mp, "current_process", lambda: _Proc())

    logger = util_new.init_run_log("log/YYYYMMDD.txt", time_input="202401010800")
    handler = logger.handlers[0]
    path = handler.baseFilename
    assert "202401010800" in path
    assert str(pid) in path
    handler.close()
