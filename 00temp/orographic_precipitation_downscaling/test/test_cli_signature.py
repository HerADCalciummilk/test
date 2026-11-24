# -*- coding: utf-8 -*-
"""四条命令的 process 具名参数。不跑预报。"""
import inspect


def test_precipitation_process_signatures():
    from orographic_precipitation_downscaling.cli.apply_cli import process as apply_process
    from orographic_precipitation_downscaling.cli.meta_cli import process as meta_process
    from orographic_precipitation_downscaling.cli.orographic_precipitation_downscaling_cli import (
        process as redistribute_process,
    )
    from orographic_precipitation_downscaling.cli.uv_cli import process as uv_process

    meta_names = inspect.signature(meta_process).parameters
    for key in ("temperature_path", "wind_speed_path", "orography_path", "output_path", "config"):
        assert key in meta_names
    uv_names = inspect.signature(uv_process).parameters
    for key in ("uwind_path", "vwind_path", "orography_path", "output_path", "config"):
        assert key in uv_names
    apply_names = inspect.signature(apply_process).parameters
    for key in ("precip_path", "operation", "allowed_time_diff", "output_path", "config"):
        assert key in apply_names
    redist_names = inspect.signature(redistribute_process).parameters
    for key in ("stages", "zero_below", "wet_threshold", "output_path", "config"):
        assert key in redist_names
    for names in (meta_names, uv_names, apply_names, redist_names):
        assert not any(item.kind is inspect.Parameter.VAR_KEYWORD for item in names.values())
