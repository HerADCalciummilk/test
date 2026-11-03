#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""QPE 插件 CLI 示例。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import meteva_base as meb
import xarray as xr


def process(
    method: str,
    *,
    refl_path: str = None,
    kdp_path: str = None,
    att_path: str = None,
    hydro_path: str = None,
    z_alpha: float = 0.0376,
    z_beta: float = 0.6112,
    kdp_alpha: float = None,
    kdp_beta: float = None,
    a_alpha: float = None,
    a_beta: float = None,
    snow_alpha: float = 0.1,
    snow_beta: float = 0.5,
    ztor_a: float = 300.0,
    ztor_b: float = 1.4,
    rr_field: str = None,
    main_field: str = None,
    thresh: float = None,
    thresh_max: bool = None,
    mp_factor: float = 0.6,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """QPE 统一入口，通过 ``method`` 选择并执行算法。

    参数说明
    --------
    method : str
        算法名称，可选 ``z``、``zpoly``、``kdp``、``a``、``zkdp``、
        ``za``、``hydro``、``ztor``。
    refl_path, kdp_path, att_path, hydro_path : str or None
        各输入网格文件路径（NetCDF）。不同算法所需输入不同：
        - ``z``/``zpoly``/``ztor`` 需要 ``refl_path``
        - ``kdp`` 需要 ``kdp_path``
        - ``a`` 需要 ``att_path``
        - ``zkdp`` 需要 ``refl_path`` + ``kdp_path``
        - ``za`` 需要 ``refl_path`` + ``att_path``
        - ``hydro`` 需要 ``refl_path`` + ``att_path`` + ``hydro_path``
    z_alpha, z_beta : Z-R 关系系数，用于 ``z``、``zkdp``、``za`` 和
        ``hydro`` 中的液态降水部分。
    kdp_alpha, kdp_beta : KDP-R 关系系数，用于 ``kdp`` 和 ``zkdp``。
    a_alpha, a_beta : A-R 关系系数，用于 ``a``、``za`` 和 ``hydro``。
    snow_alpha, snow_beta : 冰相或雪相 Z-R 关系系数，用于 ``hydro``。
    ztor_a, ztor_b : ``ZtoR`` 专用系数，对应 ``Z = aR^b``。该公式方向
        与 ``est_rain_rate_z`` 不同，因此不与 ``z_alpha/z_beta`` 混用。
    rr_field : 降水率输出字段名。
    main_field, thresh, thresh_max : 融合算法中的主判据字段、阈值和切换方向。
    mp_factor : ``hydro`` 方法中的混合相修正系数。
    output_path : str or None
        若提供则将结果写出到该路径。

    返回
    ----
    xr.DataArray
        降水率网格结果。除 ``ztor`` 外默认变量名通常为
        ``radar_estimated_rain_rate``；``ztor`` 默认变量名为
        ``NWS_primary_prate``（可通过 ``rr_field`` 覆盖）。
    """
    from radar_qpe_retrieval.src.qpe import QPEPlugin
    from radar_qpe_retrieval.cli.cinrad_meb import save_meteva_grid_to_netcdf

    refl = meb.read_griddata_from_nc(refl_path) if refl_path is not None else None
    kdp = meb.read_griddata_from_nc(kdp_path) if kdp_path is not None else None
    att = meb.read_griddata_from_nc(att_path) if att_path is not None else None
    hydro = meb.read_griddata_from_nc(hydro_path) if hydro_path is not None else None

    plugin = QPEPlugin(
        method=method,
        z_alpha=z_alpha,
        z_beta=z_beta,
        kdp_alpha=kdp_alpha,
        kdp_beta=kdp_beta,
        a_alpha=a_alpha,
        a_beta=a_beta,
        snow_alpha=snow_alpha,
        snow_beta=snow_beta,
        ztor_a=ztor_a,
        ztor_b=ztor_b,
        rr_field=rr_field,
        main_field=main_field,
        thresh=thresh,
        thresh_max=thresh_max,
        mp_factor=mp_factor,
    )

    result = plugin.process(refl=refl, kdp=kdp, att=att, hydro=hydro)

    if output_path is not None:
        save_meteva_grid_to_netcdf(result, output_path)

    return result


if __name__ == "__main__":
    import sys
    # 添加项目根目录到 Python 路径
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # 设置输入输出路径
    data_dir = Path(__file__).resolve().parents[1] / "test_data" / "qpe" / "cli_input"
    refl_path = str(data_dir / "ACHN_CREF000_20240612_070000.nc")
    output_path = str(
        Path(__file__).resolve().parents[1]
        / "test_data"
        / "qpe"
        / "cli_output"
        / "est_rain_rate_z_cli_run.nc"
    )

    process("z", refl_path=refl_path, output_path=output_path)