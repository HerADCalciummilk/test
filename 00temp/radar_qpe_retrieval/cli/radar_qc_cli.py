#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""极坐标雷达质控命令行。

在本包目录执行::

    python cli/radar_qc_cli.py --input-path PATH [--dem-path DEM] [--refl-output-path OUT]
    python -m cli.radar_qc_cli --input-path PATH

Python::

    from cli.radar_qc_cli import RadarQcCli
    RadarQcCli.call(input_path="PATH", refl_output_path="refl.nc")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


def _bootstrap_paths() -> None:
    """把 00temp 与本包根放入 sys.path（与 ``cli/qpe.py`` 一致）。"""
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
    input_path: str = None,
    *,
    radius: int = 300,
    resolution: Tuple[int, int] = (1000, 1000),
    sweep: int = 0,
    dem_path: str = None,
    use_attenuation_correction: bool = True,
    replace_refl_with_corrected: bool = True,
    attenuation_fzl_m: float = 4000.0,
    min_refl_dbz: float = 15.0,
    max_refl_dbz: float = 80.0,
    min_rho: float = 0.85,
    use_zdr: bool = True,
    use_phidp_texture: bool = True,
    use_kdp_texture: bool = True,
    despeckle: bool = True,
    despeckle_size: int = 15,
    refl_output_path: str = None,
    kdp_output_path: str = None,
    att_output_path: str = None,
    config: str = None,
) -> Dict[str, Any]:
    """极坐标质控统一入口：读基数据 → 质控+网格 → 可选落盘。

    路径类参数默认为 ``None``，可由 ``conf.ini`` ``[radar_qc]`` 填补；
    其余有方法默认值。显式传入优先。给定 ``dem_path`` 则做波束遮挡。
    """
    # 仅填补仍为 None 的路径项；有默认值的算法参数不进 overlay
    _over = overlay_none(
        __file__,
        config,
        {
            "input_path": (input_path, "str"),
            "dem_path": (dem_path, "str"),
            "refl_output_path": (refl_output_path, "str"),
            "kdp_output_path": (kdp_output_path, "str"),
            "att_output_path": (att_output_path, "str"),
        },
        section="radar_qc",
    )
    input_path = _over["input_path"]
    dem_path = _over["dem_path"]
    refl_output_path = _over["refl_output_path"]
    kdp_output_path = _over["kdp_output_path"]
    att_output_path = _over["att_output_path"]

    if not input_path:
        raise ValueError("input_path 必填（命令行 --input-path 或 conf.ini [radar_qc]）")

    import meteva_base as meb

    from radar_qpe_retrieval.cli.cinrad_pyart_prep import load_cinrad_pyart_radar
    from radar_qpe_retrieval.cli.polar_qc import save_meteva_grid_to_netcdf
    from radar_qpe_retrieval.src.radar_qc import PolarRadarQCPlugin

    dem = None
    if dem_path is not None:
        dem = meb.read_griddata_from_nc(str(dem_path))

    cinrad_file, radar = load_cinrad_pyart_radar(
        str(input_path), radius=int(radius), prepare=True, dedupe=True
    )
    plugin = PolarRadarQCPlugin(
        resolution=tuple(int(v) for v in resolution),
        sweep=int(sweep),
        min_refl_dbz=float(min_refl_dbz),
        max_refl_dbz=float(max_refl_dbz),
        min_rho=float(min_rho),
        use_zdr=bool(use_zdr),
        use_phidp_texture=bool(use_phidp_texture),
        use_kdp_texture=bool(use_kdp_texture),
        use_attenuation_correction=bool(use_attenuation_correction),
        replace_refl_with_corrected=bool(replace_refl_with_corrected),
        attenuation_fzl_m=float(attenuation_fzl_m),
        despeckle=bool(despeckle),
        despeckle_size=int(despeckle_size),
    )
    result = plugin.process(radar, cinrad_file=cinrad_file, dem=dem)
    refl0, kdp0, att0 = result.refl, result.kdp, result.att

    if refl_output_path is not None:
        save_meteva_grid_to_netcdf(refl0, refl_output_path)
    if kdp_output_path is not None:
        save_meteva_grid_to_netcdf(kdp0, kdp_output_path)
    if att_output_path is not None and att0 is not None:
        save_meteva_grid_to_netcdf(att0, att_output_path)

    return {
        "refl": refl0,
        "kdp": kdp0,
        "att": att0,
        "radar": result.radar,
        "gatefilter": result.gatefilter,
        "cinrad_file": cinrad_file,
    }


class RadarQcCli(CliBase):
    """``radar_qc`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/radar_qc_cli.py"
    description = (
        "极坐标雷达质控：基数据 → PolarRadarQCPlugin → 经纬网格。\n"
        "省略的可选项保持函数默认值；仍为 None 的路径项可从 "
        "--config / resource/conf.ini 的 [radar_qc] 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/radar_qc_cli.py --help\n"
        "  python cli/radar_qc_cli.py --input-path PATH "
        "--refl-output-path refl.nc --kdp-output-path kdp.nc\n"
        "  python -m cli.radar_qc_cli --input-path PATH --dem-path DEM "
        "--att-output-path att.nc --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--input-path",
            default=None,
            metavar="PATH",
            help="雷达基数据。必填（也可写在 conf.ini [radar_qc]）。",
        )
        parser.add_argument(
            "--radius",
            type=int,
            default=None,
            help="读入半径 km。省略则用 300。",
        )
        parser.add_argument(
            "--resolution",
            default=None,
            metavar="NX,NY",
            help="grid_2d 分辨率，如 1000,1000。省略则用 1000,1000。",
        )
        parser.add_argument(
            "--sweep",
            type=int,
            default=None,
            help="输出仰角序号。省略则用 0。",
        )
        parser.add_argument(
            "--dem-path",
            default=None,
            metavar="PATH",
            help="地形高度 NetCDF（meb 网格）。给定则做波束遮挡；省略则跳过。",
        )
        self.add_optional_bool(
            parser,
            "--use-attenuation-correction",
            help_true="开启 Z-PHI 估 A 与订正 Z。",
            help_false="关闭衰减环。省略则开启。",
        )
        self.add_optional_bool(
            parser,
            "--replace-refl-with-corrected",
            help_true="用订正 Z 覆盖 reflectivity。",
            help_false="保留原始 Z，仅另存 corrected_reflectivity。省略则覆盖。",
        )
        parser.add_argument(
            "--attenuation-fzl-m",
            dest="attenuation_fzl_m",
            type=float,
            default=None,
            help="冻结高度 m。省略则用 4000。",
        )
        parser.add_argument(
            "--min-refl-dbz",
            dest="min_refl_dbz",
            type=float,
            default=None,
            help="反射率下限 dBZ。省略则用 15。",
        )
        parser.add_argument(
            "--max-refl-dbz",
            dest="max_refl_dbz",
            type=float,
            default=None,
            help="反射率上限 dBZ。省略则用 80。",
        )
        parser.add_argument(
            "--min-rho",
            dest="min_rho",
            type=float,
            default=None,
            help="ρhv 下限。省略则用 0.85。",
        )
        self.add_optional_bool(
            parser, "--use-zdr", help_true="启用 ZDR 环。", help_false="关闭 ZDR 环。"
        )
        self.add_optional_bool(
            parser,
            "--use-phidp-texture",
            help_true="启用 ΦDP 纹理环。",
            help_false="关闭 ΦDP 纹理环。",
        )
        self.add_optional_bool(
            parser,
            "--use-kdp-texture",
            help_true="启用 KDP 纹理环。",
            help_false="关闭 KDP 纹理环。",
        )
        self.add_optional_bool(
            parser,
            "--despeckle",
            help_true="启用斑点剔除。",
            help_false="关闭斑点剔除。",
        )
        parser.add_argument(
            "--despeckle-size",
            dest="despeckle_size",
            type=int,
            default=None,
            help="斑点连通域大小阈值。省略则用 15。",
        )
        parser.add_argument(
            "--refl-output-path",
            default=None,
            metavar="PATH",
            help="质控后反射率 NetCDF。",
        )
        parser.add_argument(
            "--kdp-output-path",
            default=None,
            metavar="PATH",
            help="质控后 KDP NetCDF。",
        )
        parser.add_argument(
            "--att-output-path",
            default=None,
            metavar="PATH",
            help="质控估出的比衰减 A NetCDF。",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini（[radar_qc]）。相对路径按本包目录解析。省略则用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        res = params.get("resolution")
        if isinstance(res, str) and res.strip():
            parts = [p.strip() for p in res.split(",") if p.strip()]
            params["resolution"] = tuple(int(p) for p in parts)
        # 与 qpe 一致：省略的 CLI 项不传入，沿用 process 默认值
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def radar_qc_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.radar_qc_cli`` 都进这里。"""
    return RadarQcCli().main(argv)


def _build_parser():
    return RadarQcCli().build_parser()


main = radar_qc_cli


if __name__ == "__main__":
    raise SystemExit(radar_qc_cli())
