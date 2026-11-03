#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形平滑系数生成 CLI 示例。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import meteva_base as meb
import xarray as xr


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


def main() -> None:
    """定义输入/输出路径并调用 ``process``（默认 ``resource/`` 样例）。"""
    import sys

    _PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    input_dir = _PACKAGE_ROOT / "resource" / "cli_input"
    output_dir = _PACKAGE_ROOT / "resource" / "cli_output"
    process(
        orography_path=str(input_dir / "input_orography_meb.nc"),
        min_gradient_smoothing_coefficient=0.5,
        max_gradient_smoothing_coefficient=0.0,
        power=1.0,
        use_mask_boundary=False,
        invert_mask=False,
        output_path=str(output_dir / "cli_basic_result.nc"),
    )


if __name__ == "__main__":
    main()
