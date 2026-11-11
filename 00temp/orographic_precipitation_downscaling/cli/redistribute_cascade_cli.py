#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""按调用方给出的多个尺度，依次做地形增强和降水订正。

一次调用处理一个时次。每一次订正都是一次独立的尺度订正：传入该次的降水格距和模式地形格距。
重分配和订正后中心加权九点×2 都在 ``RedistributeOrographicEnhancement`` 内部完成。

在本包目录执行::

    python cli/dsc_redistribute_cascade.py --precip-path PATH --temperature-path PATH --humidity-path PATH --pressure-path PATH --uwind-path PATH --vwind-path PATH --orography-model-path PATH --orography-target-path PATH --stages 20,5,1 --zero-below 0.2 --output-path OUT.nc
    python -m cli.dsc_redistribute_cascade --precip-path PATH --temperature-path PATH --humidity-path PATH --pressure-path PATH --uwind-path PATH --vwind-path PATH --orography-model-path PATH --orography-target-path PATH --stages 20,5,1 --output-path OUT.nc

Python::

    from cli.dsc_redistribute_cascade import DscRedistributeCascadeCli
    DscRedistributeCascadeCli.call(precip_path="PATH", temperature_path="PATH", humidity_path="PATH", pressure_path="PATH", uwind_path="PATH", vwind_path="PATH", orography_model_path="PATH", orography_target_path="PATH", stages="20,5,1", output_path="OUT.nc")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
import numpy as np
import xarray as xr


def _bootstrap_paths() -> None:
    """沿用原脚本：把 00temp 放进 sys.path，并让包根上的 utils 优先。"""
    root = Path(__file__).resolve().parent.parent
    temp_root = root.parent
    temp_s = str(temp_root)
    if temp_s not in sys.path:
        sys.path.insert(0, temp_s)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.conf_ini import overlay_none

# 读入时不按数值范围截断，缺测留给后续插值和订正处理。
_UNBOUNDED = (-np.inf, np.inf, np.nan)


def _parse_level_km(stages: str) -> list[float]:
    """把 ``20,5,1`` 解析成严格递减的分辨率列表，单位 km。"""
    text = str(stages).strip()
    if not text:
        raise ValueError("stages 不能为空，例如 20,5,1")
    try:
        levels = [float(item) for item in text.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError(f"stages 须为逗号分隔的公里数，收到 {stages!r}") from exc
    if len(levels) < 2:
        raise ValueError(f"stages 至少两档，收到 {stages!r}")
    if any(level <= 0 for level in levels):
        raise ValueError(f"stages 中的分辨率须为正，收到 {levels}")
    if any(nxt >= prev for prev, nxt in zip(levels, levels[1:])):
        raise ValueError(f"stages 须从粗到细严格递减，收到 {levels}")
    return levels


def _aggregate_factor(level_km: float, target_km: float) -> int:
    """目标地形聚合成该档网格时的整数倍数。"""
    ratio = float(level_km) / float(target_km)
    factor = int(round(ratio))
    if factor < 2 or abs(ratio - factor) > 1e-3:
        raise ValueError(
            f"分辨率 {level_km:g} km 不是目标 {target_km:g} km 的整数倍（≥2），无法聚合地形"
        )
    return factor


def build_cascade_stages(
    stages: str,
    *,
    precip_spacing_km: float,
    zero_below: Optional[float] = None,
) -> list[dict]:
    """把尺度列表展开成每一次订正的设置。

    每次订正记下自己的降水格距和模式地形格距。ΔOE 半径和守恒块边长由插件按这两个格距计算。
    ``zero_below`` 只赋给最粗一次。订正后的中心加权九点×2 在插件内部完成。
    """
    from orographic_precipitation_downscaling.src.redistribute_orographic_enhancement import (
        block_edge_cells,
        doe_smooth_radius_cells,
    )

    levels = _parse_level_km(stages)
    if zero_below is None:
        zero_below = 0.0
    zero_below = float(zero_below)
    if zero_below < 0:
        raise ValueError(f"zero_below 须非负，收到 {zero_below}")
    if float(precip_spacing_km) <= 0:
        raise ValueError(f"precip_spacing_km 须为正，收到 {precip_spacing_km}")

    target_km = levels[-1]
    # 中间尺度必须是最细目标地形的整数倍，否则后面无法块平均出模式地形。
    for level_km in levels[1:-1]:
        _aggregate_factor(level_km, target_km)

    specs = []
    for index, (model_orography_km, grid_km) in enumerate(zip(levels, levels[1:])):
        # 第一次用原始预报的降水格距。之后降水已落在上一次的目标网格上，
        # 其格距等于这一次的模式地形格距。
        stage_precip_km = precip_spacing_km if index == 0 else model_orography_km
        specs.append(
            {
                "from_km": model_orography_km,
                "to_km": grid_km,
                "precip_spacing_km": stage_precip_km,
                "model_orography_spacing_km": model_orography_km,
                # 半径和块边长按标称尺度记下，便于核对。插件仍用两个格距和实际目标网格重算。
                "smooth_radius": doe_smooth_radius_cells(stage_precip_km, grid_km),
                "block_cells": block_edge_cells(model_orography_km, grid_km),
                # 小雨清空只做最粗一次。
                "zero_below_mmh": zero_below if index == 0 else 0.0,
            }
        )
    return specs


def _ensure_units(data: xr.DataArray, fallback: str) -> xr.DataArray:
    """缺单位时补上，并把 CF 写法 ``m s**-1`` 收成 ``m s-1``。"""
    units = str(data.attrs.get("units") or "").strip()
    if not units:
        data.attrs["units"] = fallback
    if data.attrs.get("units") == "m s**-1":
        data.attrs["units"] = "m s-1"
    return data


def _read_field(path: str, fallback_unit: str, *, single: bool = False) -> xr.DataArray:
    """读成 meb 六维网格。地形传 ``single=True``，只要一张 lat/lon。"""
    data = meb.checkout_griddata(
        meb.read_griddata_from_nc(path),
        is_single=single,
        valid_val=_UNBOUNDED,
    )
    return _ensure_units(data, fallback_unit)


def _aggregate_orog(orog_target: xr.DataArray, factor: int) -> xr.DataArray:
    """把目标地形按 factor×factor 块平均到更粗的网格。"""
    out = orog_target.coarsen(lat=factor, lon=factor, boundary="trim").mean()
    out.attrs = dict(orog_target.attrs)
    out.attrs["units"] = orog_target.attrs.get("units") or "m"
    out.name = orog_target.name or "orography"
    return out


def _on_grid(field: xr.DataArray, grid, units: str) -> xr.DataArray:
    """双线性插到目标网格，范围外为 NaN。"""
    moved = meb.interp_gg_linear(field, grid, outer_value=np.nan)
    moved.attrs["units"] = units
    return moved


def process(
    precip_path: str,
    temperature_path: str,
    humidity_path: str,
    pressure_path: str,
    uwind_path: str,
    vwind_path: str,
    orography_model_path: str,
    orography_target_path: str,
    stages: str,
    output_path: Optional[str] = None,
    *,
    zero_below: Optional[float] = None,
    wet_threshold: Optional[float] = None,
    config=None,
) -> xr.DataArray:
    """读取一个时次的输入，按多个尺度依次订正降水，并在给出路径时写 NetCDF。

    要素场彼此应在同一张预报网格上；它们与地形、降水的分辨率可以不同。
    每个尺度先算地形增强，再把降水和模式增强场双线性插到该次目标网格上订正。

    参数
    ----------
    precip_path, temperature_path, humidity_path, pressure_path, uwind_path, vwind_path
        该时次的降水与温湿压、U、V。五个要素场须共享空间和时效坐标。
    orography_model_path
        最粗一次订正使用的模式地形。
    orography_target_path
        最细一次订正的目标地形。中间尺度的模式地形由它按整数倍数聚合。
    stages
        从粗到细的订正尺度，单位 km，例如 ``20,5,1`` 或 ``25,10,5,1``。
        每一次订正后的中心加权九点×2 在插件内部完成。
    output_path
        输出 NetCDF。省略则不写文件。
    zero_below
        最粗一次订正的小雨清空阈值，单位 mm/h。省略则不清空；更细的尺度不再清空。
    wet_threshold
        各次订正共用的有雨阈值，单位 mm/h。省略则用 0.1。
        ΔOE 等权窗半径按该次降水格距计算，守恒块边长按该次模式地形格距计算，都在插件内部完成。
    config
        运行配置 ini。省略则用包内 ``resource/conf.ini``。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(
        __file__,
        config,
        {
            "output_path": (output_path, "str"),
            "zero_below": (zero_below, "float"),
            "wet_threshold": (wet_threshold, "float"),
        },
    )
    output_path = _over["output_path"]
    zero_below = _over["zero_below"]
    wet_threshold = _over["wet_threshold"]

    temperature = _read_field(temperature_path, "degC")
    humidity = _read_field(humidity_path, "%")
    pressure = _read_field(pressure_path, "Pa")
    uwind = _read_field(uwind_path, "m s-1")
    vwind = _read_field(vwind_path, "m s-1")
    for label, field in (
        ("相对湿度场", humidity),
        ("气压场", pressure),
        ("东西风场", uwind),
        ("南北风场", vwind),
    ):
        if not meb.checkout_griddata_same_coords([temperature, field], is_time_match=True):
            raise ValueError(f"{label}与温度场的空间/时效坐标不一致")

    from orographic_precipitation_downscaling.src.orographic_enhancement import (
        OrographicEnhancement,
    )
    from orographic_precipitation_downscaling.src.redistribute_orographic_enhancement import (
        RedistributeOrographicEnhancement,
    )
    from orographic_precipitation_downscaling.src.utils._grid import (
        _estimate_grid_spacing_meters,
    )

    precip = _read_field(precip_path, "mm h-1")
    orography_model = _read_field(orography_model_path, "m", single=True)
    orography_target = _read_field(orography_target_path, "m", single=True)
    if wet_threshold is None:
        wet_threshold = 0.1
    wet_threshold = float(wet_threshold)
    if wet_threshold < 0:
        raise ValueError(f"wet_threshold 须非负，收到 {wet_threshold}")

    # 降水格距必须在插值前从原始预报上量。插到目标网格后坐标只剩目标格距。
    stage_specs = build_cascade_stages(
        stages,
        precip_spacing_km=_estimate_grid_spacing_meters(precip) / 1000.0,
        zero_below=zero_below,
    )
    target_km = float(stage_specs[-1]["to_km"])
    # 最粗地形用模式地形文件，最细地形用目标地形文件。
    orogs: dict[float, xr.DataArray] = {
        float(stage_specs[0]["from_km"]): orography_model,
        target_km: orography_target,
    }
    for spec in stage_specs:
        grid_km = float(spec["to_km"])
        if grid_km in orogs:
            continue
        # 中间尺度的模式地形由目标地形按整数倍块平均得到，不做插值。
        orogs[grid_km] = _aggregate_orog(
            orography_target, _aggregate_factor(grid_km, target_km)
        )

    # 每个地形尺度各算一次增强。气象场与地形网格不同时，增强计算内部会重网格。
    oe_api = OrographicEnhancement()
    enhancements: dict[float, xr.DataArray] = {}
    for level_km, orog in orogs.items():
        enhancement = oe_api(temperature, humidity, pressure, uwind, vwind, orog)
        if not str(enhancement.attrs.get("units") or "").strip():
            enhancement.attrs["units"] = "m s-1"
        enhancements[level_km] = enhancement

    precip_units = str(precip.attrs.get("units") or "mm h-1")
    field = precip
    for spec in stage_specs:
        model_km = float(spec["from_km"])
        grid_km = float(spec["to_km"])
        grid_orog = orogs[grid_km]
        grid = meb.get_grid_of_data(grid_orog)
        # 插件要求三张场已经在同一张目标网格上，插值在调用前完成。
        precip_on_grid = _on_grid(field, grid, precip_units)
        model_units = str(enhancements[model_km].attrs.get("units") or "m s-1")
        oe_model = _on_grid(enhancements[model_km], grid, model_units)
        oe_target = enhancements[grid_km]
        corrected, _adjustment = RedistributeOrographicEnhancement(
            wet_threshold_mmh=wet_threshold,
            zero_below_mmh=float(spec["zero_below_mmh"]),
            precip_spacing_km=float(spec["precip_spacing_km"]),
            model_orography_spacing_km=float(spec["model_orography_spacing_km"]),
        )(precip_on_grid, oe_target, oe_model)
        if not str(corrected.attrs.get("units") or "").strip():
            corrected.attrs["units"] = precip_units
        corrected.name = precip.name or "precipitation_rate"
        # 下一次订正的降水就是这一次的结果。
        field = corrected
    result = field
    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "precipitation_rate"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")
    return result


class DscRedistributeCascadeCli(CliBase):
    """``dsc_redistribute_cascade`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/dsc_redistribute_cascade.py"
    description = (
        "按多个尺度依次做地形增强和降水订正，处理一个时次。\n"
        "输入路径和 --stages 必填。每一次订正后的中心加权九点×2 在插件内部完成。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/dsc_redistribute_cascade.py --help\n"
        "  python cli/dsc_redistribute_cascade.py --precip-path PATH --temperature-path PATH "
        "--humidity-path PATH --pressure-path PATH --uwind-path PATH --vwind-path PATH "
        "--orography-model-path PATH --orography-target-path PATH "
        "--stages 20,5,1 --zero-below 0.2 "
        "--output-path OUT.nc\n"
        "  python -m cli.dsc_redistribute_cascade --precip-path PATH --temperature-path PATH "
        "--humidity-path PATH --pressure-path PATH --uwind-path PATH --vwind-path PATH "
        "--orography-model-path PATH --orography-target-path PATH "
        "--stages 25,10,5,1 --output-path OUT.nc\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--precip-path", required=True, metavar="PATH", help="预报降水 NetCDF。必填。")
        parser.add_argument("--temperature-path", required=True, metavar="PATH", help="温度场 NetCDF。必填。")
        parser.add_argument("--humidity-path", required=True, metavar="PATH", help="相对湿度场 NetCDF。必填。")
        parser.add_argument("--pressure-path", required=True, metavar="PATH", help="气压场 NetCDF。必填。")
        parser.add_argument("--uwind-path", required=True, metavar="PATH", help="东西风 NetCDF。必填。")
        parser.add_argument("--vwind-path", required=True, metavar="PATH", help="南北风 NetCDF。必填。")
        parser.add_argument(
            "--orography-model-path",
            required=True,
            metavar="PATH",
            help="最粗一次订正使用的模式地形 NetCDF。必填。",
        )
        parser.add_argument(
            "--orography-target-path",
            required=True,
            metavar="PATH",
            help="最细一次订正的目标地形 NetCDF。必填。中间尺度由它聚合。",
        )
        parser.add_argument(
            "--stages",
            required=True,
            help="从粗到细的分辨率（km），逗号分隔。例如 20,5,1 或 25,10,5,1。必填。",
        )
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 NetCDF。省略则不写文件。")
        parser.add_argument(
            "--zero-below",
            dest="zero_below",
            type=float,
            default=None,
            help="最粗一次订正的小雨清空阈值（mm/h）。省略则不清空。",
        )
        parser.add_argument(
            "--wet-threshold",
            dest="wet_threshold",
            type=float,
            default=None,
            help="各次订正共用的有雨阈值（mm/h）。省略则用 0.1。",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def dsc_redistribute_cascade_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.dsc_redistribute_cascade`` 都进这里。"""
    return DscRedistributeCascadeCli().main(argv)


main = dsc_redistribute_cascade_cli


if __name__ == "__main__":
    raise SystemExit(dsc_redistribute_cascade_cli())
