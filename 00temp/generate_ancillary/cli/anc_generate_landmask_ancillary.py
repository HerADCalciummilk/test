#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""海陆掩码二值化 CLI 示例。

约定（无 Improver ``cli`` 装饰器）::

    - ``process`` 接收文件路径，在函数内完成读入、计算与可选写出；
    - ``main`` 中定义路径等参数，再直接调用 ``process``。

包根目录执行::

    python -m cli landmask
    python cli/anc_generate_landmask_ancillary.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import meteva_base as meb
import xarray as xr

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def process(landmask_path: str, output_path: Optional[str] = None) -> xr.DataArray:
    """读取海陆掩码并输出 0/1 二值化结果。

    功能逻辑：
    插值后的海陆掩码场中，格点值为 0~1 之间的浮点数，表示该格点为陆地的概率。
    本方法以 0.5 为阈值进行二值化：
    - 格点值 < 0.5：判定为海，置为 0
    - 格点值 >= 0.5：判定为陆，置为 1
    当output_path不为空时，输出结果为float32类型的二值掩码场。

    输入输出均为 meteva_base 标准六维网格数据（member, level, time, dtime, lat, lon），
    维度保持不变，仅修改格点值。

    参数
    ----------
    landmask_path : str
        输入海陆掩码 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径。为空时仅返回结果，不写盘。

    返回
    -------
    xr.DataArray
        二值化后的海陆掩码，维度保持输入不变。
    """
    from generate_ancillary.src.generate_ancillary import CorrectLandSeaMask

    landmask = meb.read_griddata_from_nc(landmask_path)
    result = CorrectLandSeaMask().process(landmask)

    if output_path is not None:
        # 避免 meteva_base 在 int32 + scale_factor 编码时触发类型冲突。
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

    landmask_path = str(input_dir / "input_landmask_meb.nc")
    output_path = str(output_dir / "cli_landmask_result.nc")

    process(landmask_path=landmask_path, output_path=output_path)


if __name__ == "__main__":
    main()
