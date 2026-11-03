#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形平滑系数生成 CLI。

在本包目录执行::

    python -m cli.dsc_generate_orographic_smoothing_coefficients --orography-path orog.nc --output-path out.nc
    python cli/dsc_generate_orographic_smoothing_coefficients.py --orography-path orog.nc --output-path out.nc

Python::

    from cli.dsc_generate_orographic_smoothing_coefficients import (
        DscGenerateOrographicSmoothingCoefficientsCli,
    )
    DscGenerateOrographicSmoothingCoefficientsCli.call(
        orography_path="orog.nc",
        output_path="out.nc",
    )
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
import xarray as xr


def _bootstrap_paths() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


_bootstrap_paths()

from utils.cli_base import CliBase


def _set_kwargs(**kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


def process(
    orography_path: str,
    mask_path: Optional[str] = None,
    *,
    min_gradient_smoothing_coefficient: float = 0.5,
    max_gradient_smoothing_coefficient: float = 0.0,
    power: float = 1.0,
    use_mask_boundary: bool = False,
    invert_mask: bool = False,
    output_path: Optional[str] = None,
    config=None,
) -> tuple[xr.DataArray, xr.DataArray]:
    """读取地形（及可选掩码）并生成 x/y 方向递归滤波平滑系数。

    功能：按地形相邻格点梯度计算平滑系数，平坦处系数偏大、陡峭处偏小；
    可选按掩码在区域或海陆过渡边界将系数置零。

    流程：
    1. 从 nc 读取 meb 六维地形场（及可选掩码）；
    2. 调用 ``OrographicSmoothingCoefficients`` 计算相邻梯度、幂次系数并缩放到
       ``[min_gradient_smoothing_coefficient, max_gradient_smoothing_coefficient]``；
    3. 若提供掩码，按 ``use_mask_boundary`` / ``invert_mask`` 置零；
    4. 若指定 ``output_path``，将两个系数场写入同一 NetCDF。

    参数
    ----------
    orography_path : str
        地形场 nc 路径（meb 六维单场）。
    mask_path : str, optional
        可选掩码 nc 路径，网格须与地形一致；不传则不做掩码置零。
    min_gradient_smoothing_coefficient : float, default 0.5
        梯度最小处（平坦）使用的平滑系数，须满足 ``0 <= value <= 0.5``。
    max_gradient_smoothing_coefficient : float, default 0.0
        梯度最大处（陡峭）使用的平滑系数，须满足 ``0 <= value <= 0.5``。
    power : float, default 1.0
        未归一化系数公式中的幂次：``|gradient| ** power``。
    use_mask_boundary : bool, default False
        仅在传入 ``mask_path`` 时生效。``True`` 时只置零掩码过渡边界；
        ``False`` 时置零掩码区域及边界。
    invert_mask : bool, default False
        反转掩码置零语义（``use_mask_boundary=True`` 时无效）。
    output_path : str, optional
        输出 nc 路径；为 ``None`` 时仅返回结果、不写盘。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    tuple[xr.DataArray, xr.DataArray]
        ``(smoothing_coefficient_x, smoothing_coefficient_y)``：
        x 方向 lon 少 1，y 方向 lat 少 1（中点坐标）。
    """
    from generate_orographic_smoothing_coefficients.src.generate_orographic_smoothing_coefficients import (
        OrographicSmoothingCoefficients,
    )

    orography = meb.read_griddata_from_nc(orography_path)
    mask = meb.read_griddata_from_nc(mask_path) if mask_path is not None else None
    coeff_x, coeff_y = OrographicSmoothingCoefficients(
        min_gradient_smoothing_coefficient=min_gradient_smoothing_coefficient,
        max_gradient_smoothing_coefficient=max_gradient_smoothing_coefficient,
        power=power,
        use_mask_boundary=use_mask_boundary,
        invert_mask=invert_mask,
    ).process(orography, mask=mask)

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        xr.Dataset(
            {
                str(coeff_x.name): coeff_x.astype("float32"),
                str(coeff_y.name): coeff_y.astype("float32"),
            }
        ).to_netcdf(output)
    return coeff_x, coeff_y


class DscGenerateOrographicSmoothingCoefficientsCli(CliBase):
    """按地形梯度生成 x/y 方向递归滤波平滑系数。"""

    prog = "python -m cli.dsc_generate_orographic_smoothing_coefficients"
    description = (
        "按地形相邻格点梯度生成 x/y 平滑系数。\n"
        "平坦处系数偏大，陡峭处偏小；可选按掩码置零。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.dsc_generate_orographic_smoothing_coefficients --help\n"
        "  python -m cli.dsc_generate_orographic_smoothing_coefficients "
        "--orography-path orog.nc --output-path out.nc\n"
        "  python cli/dsc_generate_orographic_smoothing_coefficients.py "
        "--orography-path orog.nc --mask-path mask.nc --output-path out.nc\n"
        "\n"
        "说明:\n"
        "  - 省略系数参数时 process 默认 min=0.5、max=0.0、power=1\n"
        "  - 省略掩码开关时 process 默认不按边界置零、不反转掩码\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--orography-path",
            dest="orography_path",
            required=True,
            metavar="PATH",
            help="地形场 nc（meb 六维单场）。",
        )
        parser.add_argument(
            "--mask-path",
            dest="mask_path",
            default=None,
            metavar="PATH",
            help="可选掩码 nc，网格须与地形一致。省略则不做掩码置零。",
        )
        parser.add_argument(
            "--min-gradient-smoothing-coefficient",
            dest="min_gradient_smoothing_coefficient",
            type=float,
            default=None,
            metavar="FLOAT",
            help="平坦处平滑系数，0 到 0.5。省略则使用 0.5。",
        )
        parser.add_argument(
            "--max-gradient-smoothing-coefficient",
            dest="max_gradient_smoothing_coefficient",
            type=float,
            default=None,
            metavar="FLOAT",
            help="陡峭处平滑系数，0 到 0.5。省略则使用 0.0。",
        )
        parser.add_argument(
            "--power",
            dest="power",
            type=float,
            default=None,
            metavar="FLOAT",
            help="未归一化系数的幂次 |gradient| ** power。省略则使用 1。",
        )
        CliBase.add_optional_bool(
            parser,
            "--use-mask-boundary",
            dest="use_mask_boundary",
            help_true="只在掩码过渡边界把系数置零。",
            help_false="在掩码区域及边界把系数置零。省略时 process 默认为 False。",
        )
        CliBase.add_optional_bool(
            parser,
            "--invert-mask",
            dest="invert_mask",
            help_true="反转掩码置零语义（use_mask_boundary 为真时无效）。",
            help_false="不反转掩码。省略时 process 默认为 False。",
        )
        parser.add_argument(
            "--output-path",
            dest="output_path",
            default=None,
            metavar="PATH",
            help="输出 nc，同时写入 x/y 两个系数场。省略则只返回、不写文件。",
        )
        parser.add_argument(
            "--config",
            dest="config",
            default=None,
            metavar="PATH",
            help=(
                "运行配置文件，传给 process 的 config。"
                "相对路径按项目根解析。"
                "本模块无 ini 读取器，省略则不改路径。"
            ),
        )

    def run(
        self,
        orography_path=None,
        mask_path=None,
        min_gradient_smoothing_coefficient=None,
        max_gradient_smoothing_coefficient=None,
        power=None,
        use_mask_boundary=None,
        invert_mask=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            orography_path,
            mask_path=mask_path,
            output_path=output_path,
            config=config,
            **_set_kwargs(
                min_gradient_smoothing_coefficient=min_gradient_smoothing_coefficient,
                max_gradient_smoothing_coefficient=max_gradient_smoothing_coefficient,
                power=power,
                use_mask_boundary=use_mask_boundary,
                invert_mask=invert_mask,
            ),
        )
        return 0


def dsc_generate_orographic_smoothing_coefficients_cli(
    argv: Optional[Sequence[str]] = None,
) -> int:
    """命令行入口。``python -m cli.dsc_generate_orographic_smoothing_coefficients`` 与直接运行本文件都进这里。"""
    return DscGenerateOrographicSmoothingCoefficientsCli().main(argv)


main = dsc_generate_orographic_smoothing_coefficients_cli


if __name__ == "__main__":
    raise SystemExit(dsc_generate_orographic_smoothing_coefficients_cli())
