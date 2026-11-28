import configparser
import inspect
from pathlib import Path

import numpy as np

from src.fast_refine_interp_util_plugin import dem_interp_scalar

from cli.orographic_nwp_3d_downscaling_cli import process
from src.fast_refine_interp_plugin import (
    BestEtaPlugin,
    MaxMinPlugin,
    SpatialInterpPlugin,
    TimeInterpPlugin,
)
from utils.base_plugin import BasePlugin


def test_plugins_are_base_plugins():
    for cls in (SpatialInterpPlugin, MaxMinPlugin, TimeInterpPlugin, BestEtaPlugin):
        assert issubclass(cls, BasePlugin)
        assert callable(getattr(cls(), "process"))


def test_conf_keys_are_process_parameters():
    parser = configparser.ConfigParser()
    parser.read(Path(__file__).resolve().parents[1] / "resource" / "conf.ini", encoding="utf-8")
    names = set(inspect.signature(process).parameters)
    assert set(parser["process"]) <= names
    assert process.__nimm_merge_params__


def test_higher_target_is_cooler():
    lon = np.array([0.0, 1.0])
    lat = np.array([0.0, 1.0])
    grid_lon, grid_lat = np.meshgrid(lon, lat)
    source = {
        "begin_lon": 0.0,
        "begin_lat": 0.0,
        "lon_res": 1.0,
        "lat_res": 1.0,
        "Nlon": 2,
        "Nlat": 2,
        "ndy2d_x_lon": grid_lon,
        "ndy2d_y_lat": grid_lat,
        "alt": np.zeros((2, 2), dtype=float),
        "2t": np.full((2, 2), 20.0),
    }
    target = {
        "lon": np.array([0.5]),
        "lat": np.array([0.5]),
        "alt": np.array([1000.0]),
    }
    lapse = np.full((2, 2), -0.006)
    cool = dem_interp_scalar(target, source, lapse, eta=1.0, skey="2t")
    flat = dem_interp_scalar(
        {"lon": target["lon"], "lat": target["lat"], "alt": np.array([0.0])},
        source,
        lapse,
        eta=1.0,
        skey="2t",
    )
    assert float(cool[0]) < float(flat[0])
    assert abs(float(cool[0]) - 14.0) < 1e-6


def test_process_writes_hour_element_eta_h5():
    source = inspect.getsource(process)
    assert 'eta_file["hour"] + "_" + eta_file["element"] + "_eta.h5"' in source
    assert "dWS3_Interp" in source
    assert "dCopy_rlt" in source


def test_process_rejects_unknown_operation():
    try:
        process(operation="x")
    except ValueError as exc:
        assert "operation" in str(exc)
    else:
        raise AssertionError("operation=x 应被拒绝")
