#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""陆地/海洋分区邻域处理命令行。

在本包目录执行::

    python cli/ens_nbhood_land_and_sea.py --input-data-path PATH --mask-path PATH --radii 20000
    python -m cli.ens_nbhood_land_and_sea --input-data-path PATH --mask-path PATH --radii 20000

Python::

    from cli.ens_nbhood_land_and_sea import EnsNbhoodLandAndSeaCli
    EnsNbhoodLandAndSeaCli.call(input_data_path="PATH", mask_path="PATH", radii=[20000])
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import xarray as xr
import meteva_base as meb


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


def _csv_floats(text: str):
    parts = [item.strip() for item in str(text).split(",") if item.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("需要逗号分隔的数值")
    return [float(item) for item in parts]


def _csv_ints(text: str):
    parts = [item.strip() for item in str(text).split(",") if item.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("需要逗号分隔的整数")
    return [int(item) for item in parts]


def process(
    input_data_path: str,
    mask_path: str,
    radii: Sequence[float],
    weights_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    neighbourhood_shape: str = "square",
    lead_times: Optional[Sequence[int]] = None,
    area_sum: bool = False, config=None) -> xr.DataArray:
    """执行陆地/海洋分区邻域处理并合并输出。

    参数
    ----------
    input_data_path : str
        待处理输入场 nc 文件路径。
    mask_path : str
        陆地/海洋或地形带掩码 nc 文件路径。
    radii : sequence of float
        邻域半径（米）。
    weights_path : str, optional
        地形带折叠权重 nc 文件路径；地形带掩码（``level`` 或 ``topographic_zone``）时必填。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    neighbourhood_shape : str, default="square"
        邻域形状，``square`` / ``circular``。
    lead_times : sequence of int, optional
        与 ``radii`` 对应的时效（小时）。
    area_sum : bool, default=False
        是否输出邻域和（True）而非邻域平均（False）。

    返回
    -------
    xr.DataArray
        陆海合并后的邻域处理结果。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "weights_path": (weights_path, "str"),
        "output_path": (output_path, "str"),
        "lead_times": (lead_times, "int_list"),
    })
    weights_path = _over['weights_path']
    output_path = _over['output_path']
    lead_times = _over['lead_times']
    from neighbourhood_probability_processing.src.utils._helpers import radius_by_lead_time
    from neighbourhood_probability_processing.src.nbhood import NeighbourhoodProcessing
    from neighbourhood_probability_processing.src.use_nbhood import ApplyNeighbourhoodProcessingWithAMask

    input_data = meb.checkout_griddata(meb.read_griddata_from_nc(input_data_path), valid_val=(-np.inf, np.inf, np.nan))
    # 地形带 mask/weights 优先 meb 六维；纯海陆掩码可能是二维或六维单层
    def _read_mask_or_weights(path: str) -> xr.DataArray:
        try:
            return meb.read_griddata_from_nc(path)
        except Exception:
            return xr.open_dataarray(path, decode_timedelta=False)

    mask = _read_mask_or_weights(mask_path)
    weights = None if weights_path is None else _read_mask_or_weights(weights_path)

    radius_or_radii, parsed_lead_times = radius_by_lead_time(list(radii), lead_times)

    # 分层带维：Generate* 为 level（层数>1）；历史样例可为 topographic_zone
    band_coord = None
    for candidate in ("level", "topographic_zone"):
        if candidate in mask.dims and int(mask.sizes[candidate]) > 1:
            band_coord = candidate
            break

    if band_coord is not None:
        if mask.attrs.get("topographic_zones_include_seapoints") == "True":
            raise ValueError(
                "地形带掩码必须排除海点：topographic_zones_include_seapoints 不能为 True。"
            )
        if weights is None:
            raise TypeError(
                "使用地形带掩码时必须提供 weights_path（用于折叠分层维）。"
            )
        if weights.attrs.get("topographic_zones_include_seapoints") == "True":
            raise ValueError(
                "weights 必须排除海点：topographic_zones_include_seapoints 不能为 True。"
            )
        if band_coord not in weights.dims:
            raise ValueError(f"weights 中缺少分层维 {band_coord}")

        # 原算法语义：优先使用首层权重的 mask 识别海点；
        # 若读取路径未保留显式 mask，则退化为“非有限值视为海点”。
        layer0 = weights.isel({band_coord: 0})
        # 海陆判别只需二维空间；挤压 meb 单点维
        for dim in ("member", "time", "dtime"):
            if dim in layer0.dims and layer0.sizes[dim] == 1:
                layer0 = layer0.isel({dim: 0}, drop=True)
        layer0_values = np.asanyarray(layer0.values)
        if np.ma.isMaskedArray(layer0_values):
            sea_mask_bool = np.ma.getmaskarray(layer0_values)
        else:
            sea_mask_bool = ~np.isfinite(np.asarray(layer0_values, dtype=np.float64))
        # 保证 land/sea 掩码为二维空间，供 NeighbourhoodProcessing 使用
        sea_mask_bool = np.asarray(sea_mask_bool, dtype=bool)
        while sea_mask_bool.ndim > 2:
            sea_mask_bool = np.squeeze(sea_mask_bool)
        if sea_mask_bool.ndim != 2:
            raise ValueError(
                f"无法从权重首层得到二维海点掩码，当前 shape={sea_mask_bool.shape}"
            )
        spatial_dims = tuple(layer0.dims[-2:])
        sea_only = xr.DataArray(
            sea_mask_bool.astype(np.int8),
            dims=spatial_dims,
            coords={d: layer0.coords[d] for d in spatial_dims},
            name="sea_binary_mask",
        )
        land_only = xr.DataArray(
            np.logical_not(sea_mask_bool).astype(np.int8),
            dims=spatial_dims,
            coords={d: layer0.coords[d] for d in spatial_dims},
            name="land_binary_mask",
        )
    else:
        if weights is not None:
            raise TypeError("当前 mask 不含地形带分层维，传入 weights 不会被使用。")
        # 输入约定：land=1, sea=0
        land_only = xr.where(mask > 0, 1, 0).astype(np.int8).rename("land_binary_mask")
        sea_only = xr.where(mask > 0, 0, 1).astype(np.int8).rename("sea_binary_mask")

    result_land = None
    result_sea = None

    # 用于处理陆地邻域部分
    if float(np.nanmax(land_only.values)) > 0.0:
        if band_coord is not None:
            result_land = ApplyNeighbourhoodProcessingWithAMask(
                coord_for_masking=band_coord,
                neighbourhood_method=neighbourhood_shape,
                radii=radius_or_radii,
                lead_times=parsed_lead_times,
                collapse_weights=weights,
                sum_only=area_sum,
            ).process(input_data, mask)
        else:
            result_land = NeighbourhoodProcessing(
                neighbourhood_shape,
                radius_or_radii,
                lead_times=parsed_lead_times,
                sum_only=area_sum,
                re_mask=True,
            ).process(input_data, land_only)

    # 用于处理海点的邻域部分
    if float(np.nanmax(sea_only.values)) > 0.0:
        result_sea = NeighbourhoodProcessing(
            neighbourhood_shape,
            radius_or_radii,
            lead_times=parsed_lead_times,
            sum_only=area_sum,
            re_mask=True,
        ).process(input_data, sea_only)

    if result_land is None and result_sea is None:
        raise RuntimeError("陆地和海洋区域均为空，无法执行邻域处理。")
    if result_land is None:
        result = result_sea
    elif result_sea is None:
        result = result_land
    else:
        land_values = np.asarray(result_land.values, dtype=np.float32)
        sea_values = np.asarray(result_sea.values, dtype=np.float32)
        combined = np.nan_to_num(land_values, nan=0.0) + np.nan_to_num(sea_values, nan=0.0)
        result = xr.DataArray(
            combined.astype(np.float32, copy=False),
            dims=result_land.dims,
            coords=result_land.coords,
            attrs=dict(result_land.attrs),
            name=result_land.name,
        )

    result = result.astype(np.float32, copy=False)
    if output_path is not None:
        # meb.write_griddata_to_nc 会把 NaN 量化成 int32 哨兵，改用 xarray 直写。
        # 先写临时文件再替换，减轻 Windows 上目标文件被占用时的直接覆盖失败。
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "neighbourhood_result"
        tmp = output_file.with_suffix(output_file.suffix + ".tmp")
        if tmp.exists():
            tmp.unlink()
        result.to_dataset(name=var_name).to_netcdf(
            tmp,
            mode="w",
            encoding={
                var_name: {
                    "dtype": "float32",
                    "_FillValue": np.float32(np.nan),
                }
            },
        )
        try:
            tmp.replace(output_file)
        except PermissionError as err:
            raise PermissionError(
                f"无法覆盖 {output_file}（可能被 Jupyter 或其他进程占用）。"
                f"临时文件已写至 {tmp}，请关闭占用后重试。"
            ) from err

    return result


class EnsNbhoodLandAndSeaCli(CliBase):
    """``ens_nbhood_land_and_sea`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/ens_nbhood_land_and_sea.py"
    description = (
        "陆地/海洋分区邻域处理。\n"
        "输入路径、掩码和半径必填。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/ens_nbhood_land_and_sea.py --help\n"
        "  python cli/ens_nbhood_land_and_sea.py --input-data-path PATH --mask-path PATH "
        "--radii 20000 --output-path OUT.nc\n"
        "  python -m cli.ens_nbhood_land_and_sea --input-data-path PATH --mask-path PATH "
        "--radii 20000 --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--input-data-path", required=True, metavar="PATH", help="待处理输入场 NetCDF。必填。")
        parser.add_argument("--mask-path", required=True, metavar="PATH", help="陆地/海洋或地形带掩码 NetCDF。必填。")
        parser.add_argument("--radii", required=True, type=_csv_floats, help="邻域半径（米），逗号分隔。必填。")
        parser.add_argument("--weights-path", default=None, metavar="PATH", help="地形带折叠权重 NetCDF。地形带掩码时需要。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 NetCDF。省略则不写文件。")
        parser.add_argument("--neighbourhood-shape", default=None, choices=("square", "circular"), help="邻域形状。省略则用 square。")
        parser.add_argument("--lead-times", dest="lead_times", type=_csv_ints, default=None, help="与 radii 对应的时效（小时），逗号分隔。")
        self.add_optional_bool(parser, "--area-sum", help_true="输出邻域和。", help_false="输出邻域平均。省略则用函数默认值 false。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def ens_nbhood_land_and_sea_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.ens_nbhood_land_and_sea`` 都进这里。"""
    return EnsNbhoodLandAndSeaCli().main(argv)


main = ens_nbhood_land_and_sea_cli


if __name__ == "__main__":
    raise SystemExit(ens_nbhood_land_and_sea_cli())
