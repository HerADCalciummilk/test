#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""地形带权重辅助场生成 CLI 示例。

约定（无 Improver ``cli`` 装饰器）::

    - ``process`` 接收文件路径，在函数内完成读入、计算与可选写出；
    - ``main`` 中定义路径等参数，再直接调用 ``process``。

包根目录执行::

    python -m cli weights
    python cli/dsc_generate_topographic_zone_weights.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import meteva_base as meb
import xarray as xr

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def process(
    orography_path: str,
    landmask_path: Optional[str] = None,
    thresholds_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """读取输入数据并生成地形带折叠权重。

    读取地形高度与可选海陆掩码，生成各地形带权重：格点在带中心时该带权重为 1.0；
    在带边界时上下带各为 0.5；其余在中心与边界之间线性变化。

    参数
    ----------
    orography_path : str
        标准网格地形高度场 nc 路径。
    landmask_path : str, optional
        标准网格海陆掩码 nc 路径（陆=1，海=0）。若提供则屏蔽海点；
        为空时对陆点与海点均生成权重。
    thresholds_path : str, optional
        地形带配置 JSON 路径。字典格式示例::

            {"bounds": [[0, 50], [50, 200]], "units": "m"}

        为空时使用默认 ``THRESHOLDS_DICT``，形如::

            {
                "bounds": [
                    [-500.0, 50.0], [50.0, 100.0], [100.0, 150.0],
                    [150.0, 200.0], [200.0, 250.0], [250.0, 300.0],
                    [300.0, 400.0], [400.0, 500.0], [500.0, 650.0],
                    [650.0, 800.0], [800.0, 950.0], [950.0, 6000.0],
                ],
                "units": "m",
            }

    output_path : str, optional
        输出 nc 路径；为空时仅返回结果。

    返回
    -------
    xr.DataArray
        沿 ``level`` 维堆叠的地形带权重（meteva_base 六维）。
    """
    from generate_ancillary.src.generate_ancillary import THRESHOLDS_DICT
    from generate_ancillary.src.generate_topographic_zone_weights import (
        GenerateTopographicZoneWeights,
    )

    orography = meb.read_griddata_from_nc(orography_path)

    if thresholds_path is None:
        thresholds_dict = THRESHOLDS_DICT
    else:
        with open(thresholds_path, "r", encoding="utf-8") as input_file:
            thresholds_dict = json.load(input_file)

    landmask = (
        meb.read_griddata_from_nc(landmask_path) if landmask_path is not None else None
    )

    result = GenerateTopographicZoneWeights().process(
        orography=orography,
        thresholds_dict=thresholds_dict,
        landmask=landmask,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


def main() -> None:
    """定义输入/输出路径并调用 ``process``。

    默认使用 ``resource/cli_input`` 下经纬 meb 六维样例；业务使用时在此修改路径即可。
    """
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    input_dir = _PACKAGE_ROOT / "resource" / "cli_input"
    output_dir = _PACKAGE_ROOT / "resource" / "cli_output"

    orography_path = input_dir / "input_orog_meb.nc"
    landmask_path = input_dir / "input_land_meb.nc"
    thresholds_path = input_dir / "bounds_topographic_zone_weights.json"
    output_path = output_dir / "cli_topographic_zone_weights_result.nc"

    process(
        orography_path=str(orography_path),
        landmask_path=str(landmask_path) if landmask_path.is_file() else None,
        thresholds_path=str(thresholds_path) if thresholds_path.is_file() else None,
        output_path=str(output_path),
    )


if __name__ == "__main__":
    main()
