# -*- coding: utf-8 -*-
"""FY-4B AGRI L1 解码。

``process`` 按 ``module`` 调用单文件或批量通道插件。
配置键都是具名参数。``None`` 再读 ini。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(_ROOT / "src"), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from utils.merge_params import merge_params
from utils.util_env import resolve_batch, resolve_module, resolve_single


def _centers(text: str):
    return [item.strip() for item in str(text).split(",") if item.strip()]


@merge_params(sections=("cli", "grid", "batch", "single"), anchor=__file__)
def process(
    module: str = None,
    input_root: str = None,
    output_root: str = None,
    start_time: str = None,
    end_time: str = None,
    centers: str = None,
    overwrite: bool = None,
    recursive: bool = None,
    input_hdf: str = None,
    output_dir: str = None,
    resolution: float = None,
    lat_min: float = None,
    lat_max: float = None,
    lon_half_width: float = None,
    channels: str = None,
    resampling: str = None,
    config: str = None,
):
    """按 module 调度单文件或批量解码插件。"""
    module_name = resolve_module(module, config=config)
    grid = {
        "resolution": resolution,
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_half_width": lon_half_width,
        "channels": channels,
        "resampling": resampling,
    }
    if module_name == "single":
        from fy4_latlon_channel_plugin import FY4LatLonChannelPlugin

        cfg = resolve_single(
            input_hdf=input_hdf,
            output_dir=output_dir,
            config=config,
            **grid,
        )
        # 单文件：定标并重采样到经纬度网格
        return FY4LatLonChannelPlugin(
            resolution=cfg["resolution"],
            lat_min=cfg["lat_min"],
            lat_max=cfg["lat_max"],
            lon_half_width=cfg["lon_half_width"],
            channels=cfg["channels"],
            resampling=cfg["resampling"],
        ).process(cfg["input_hdf"], cfg["output_dir"])

    cfg = resolve_batch(
        input_root=input_root,
        output_root=output_root,
        start_time=start_time,
        end_time=end_time,
        centers=centers,
        overwrite=overwrite,
        recursive=recursive,
        config=config,
        **grid,
    )
    # 批量：按时段扫描 HDF，再逐文件调用通道解码
    from fy4_batch_latlon_channel_plugin import FY4BatchLatLonChannelPlugin

    return FY4BatchLatLonChannelPlugin(
        input_root=cfg["input_root"],
        output_root=cfg["output_root"],
        start_time=cfg["start_time"],
        end_time=cfg["end_time"],
        resolution=cfg["resolution"],
        lat_min=cfg["lat_min"],
        lat_max=cfg["lat_max"],
        lon_half_width=cfg["lon_half_width"],
        channels=cfg["channels"],
        resampling=cfg["resampling"],
        centers=_centers(cfg["centers"]),
        overwrite=cfg["overwrite"],
        recursive=cfg["recursive"],
    ).process()
