#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""QPE 命令行。

在本包目录执行::

    python cli/qpe.py --method z --refl-path PATH [--output-path PATH]
    python -m cli.qpe --method z --refl-path PATH

Python::

    from cli.qpe import QpeCli
    QpeCli.call(method="z", refl_path="PATH")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
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
    output_path: Optional[str] = None, config=None) -> xr.DataArray:
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
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "refl_path": (refl_path, "str"),
        "kdp_path": (kdp_path, "str"),
        "att_path": (att_path, "str"),
        "hydro_path": (hydro_path, "str"),
        "kdp_alpha": (kdp_alpha, "float"),
        "kdp_beta": (kdp_beta, "float"),
        "a_alpha": (a_alpha, "float"),
        "a_beta": (a_beta, "float"),
        "rr_field": (rr_field, "str"),
        "main_field": (main_field, "str"),
        "thresh": (thresh, "float"),
        "thresh_max": (thresh_max, "bool"),
        "output_path": (output_path, "str"),
    })
    refl_path = _over['refl_path']
    kdp_path = _over['kdp_path']
    att_path = _over['att_path']
    hydro_path = _over['hydro_path']
    kdp_alpha = _over['kdp_alpha']
    kdp_beta = _over['kdp_beta']
    a_alpha = _over['a_alpha']
    a_beta = _over['a_beta']
    rr_field = _over['rr_field']
    main_field = _over['main_field']
    thresh = _over['thresh']
    thresh_max = _over['thresh_max']
    output_path = _over['output_path']
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


class QpeCli(CliBase):
    """``qpe`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/qpe.py"
    description = (
        "雷达降水定量反演。用 --method 选择算法。\n"
        "各算法所需路径不同，路径本身可选。"
        "省略的可选项保持函数默认值；仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/qpe.py --help\n"
        "  python cli/qpe.py --method z --refl-path PATH --output-path OUT.nc\n"
        "  python -m cli.qpe --method kdp --kdp-path PATH --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--method", required=True, help="算法：z、zpoly、kdp、a、zkdp、za、hydro、ztor。必填。")
        parser.add_argument("--refl-path", default=None, metavar="PATH", help="反射率网格。z/zpoly/ztor/zkdp/za/hydro 需要。")
        parser.add_argument("--kdp-path", default=None, metavar="PATH", help="KDP 网格。kdp/zkdp 需要。")
        parser.add_argument("--att-path", default=None, metavar="PATH", help="衰减场。a/za/hydro 需要。")
        parser.add_argument("--hydro-path", default=None, metavar="PATH", help="水凝物分类场。hydro 需要。")
        parser.add_argument("--z-alpha", dest="z_alpha", type=float, default=None, help="Z-R 系数 alpha。省略则用 0.0376。")
        parser.add_argument("--z-beta", dest="z_beta", type=float, default=None, help="Z-R 系数 beta。省略则用 0.6112。")
        parser.add_argument("--kdp-alpha", dest="kdp_alpha", type=float, default=None, help="KDP-R 系数 alpha。")
        parser.add_argument("--kdp-beta", dest="kdp_beta", type=float, default=None, help="KDP-R 系数 beta。")
        parser.add_argument("--a-alpha", dest="a_alpha", type=float, default=None, help="A-R 系数 alpha。")
        parser.add_argument("--a-beta", dest="a_beta", type=float, default=None, help="A-R 系数 beta。")
        parser.add_argument("--snow-alpha", dest="snow_alpha", type=float, default=None, help="冰相 Z-R 系数 alpha。省略则用 0.1。")
        parser.add_argument("--snow-beta", dest="snow_beta", type=float, default=None, help="冰相 Z-R 系数 beta。省略则用 0.5。")
        parser.add_argument("--ztor-a", dest="ztor_a", type=float, default=None, help="ZtoR 系数 a。省略则用 300。")
        parser.add_argument("--ztor-b", dest="ztor_b", type=float, default=None, help="ZtoR 系数 b。省略则用 1.4。")
        parser.add_argument("--rr-field", default=None, help="降水率输出字段名。")
        parser.add_argument("--main-field", default=None, help="融合算法主判据字段。")
        parser.add_argument("--thresh", type=float, default=None, help="融合切换阈值。")
        self.add_optional_bool(parser, "--thresh-max", help_true="主场大于阈值时切换。", help_false="主场小于阈值时切换。省略则保持 None。")
        parser.add_argument("--mp-factor", dest="mp_factor", type=float, default=None, help="hydro 混合相修正系数。省略则用 0.6。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="结果 NetCDF。省略则只返回内存结果。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def qpe_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.qpe`` 都进这里。"""
    return QpeCli().main(argv)


main = qpe_cli


if __name__ == "__main__":
    raise SystemExit(qpe_cli())