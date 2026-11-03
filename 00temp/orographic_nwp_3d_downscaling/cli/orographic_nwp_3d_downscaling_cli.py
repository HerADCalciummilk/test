# -*- coding: utf-8 -*-
"""快速精细化插值命令行。

在本包目录执行::

    python -m cli --work-dir .
    python cli/orographic_nwp_3d_downscaling_cli.py --work-dir .
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import set_main_ini


_INI_STRINGS = (
    "dem_head",
    "dem_format",
    "validate_area",
    "plot_format",
    "PQ_shortname",
    "forecast_time",
    "custom_path",
)
_INI_BOOLS = (
    "recall",
    "Interp_Time",
    "validate",
    "del_no_eta",
    "out_China",
    "eta_cmn_out",
    "VR_plot",
    "rlt_plot",
    "MICAPS_out",
    "Interp_Maxmin",
    "maxmin_update",
    "maxmin_validate",
    "FH_parallel",
    "BT_parallel",
    "Para_parallel",
)
_INI_INTS = (
    "FH_max_pcount",
    "FH_DI_timeout",
    "FH_TI_timeout",
    "BT_max_pcount",
    "BT_timeout",
    "Para_max_pcount",
    "Para_timeout",
)
_THRESHOLD_KEYS = (
    "2t",
    "2rh",
    "10ws",
    "10u",
    "10v",
    "2t_max",
    "2t_min",
    "2rh_max",
    "2rh_min",
    "10ws_max",
)


def _add_ini_arguments(parser, add_optional_bool) -> None:
    """resource/conf.ini 的键。省略时为 None，交给 ini。"""
    for name in _INI_STRINGS:
        parser.add_argument(
            "--" + name.replace("_", "-"),
            dest=name,
            default=None,
            metavar="VALUE",
            help=f"覆盖 ini 的 {name}。省略则用 ini。",
        )
    for name in _INI_BOOLS:
        extra = ""
        if name == "maxmin_update":
            extra = " 这是 MaxMinInfo.update，与操作开关 --update（0/1）不是同一项。"
        elif name == "validate":
            extra = " 这是 InstantInfo.validate。"
        elif name == "maxmin_validate":
            extra = " 这是 MaxMinInfo.validate。"
        add_optional_bool(
            parser,
            "--" + name.replace("_", "-"),
            dest=name,
            help_true=f"将 {name} 设为 true。{extra}",
            help_false=f"将 {name} 设为 false。{extra}",
        )
    for name in _INI_INTS:
        parser.add_argument(
            "--" + name.replace("_", "-"),
            dest=name,
            type=int,
            default=None,
            metavar="N",
            help=f"覆盖 ini 的 {name}。省略则用 ini。",
        )
    for name in _THRESHOLD_KEYS:
        parser.add_argument(
            "--" + name,
            dest=name,
            type=float,
            default=None,
            metavar="FLOAT",
            help=f"覆盖 threshold.{name}。省略则用 ini。",
        )


def _plugin_cls():
    try:
        from nimm_g_interp.src.fast_refine_interp_plugin import FastRefineInterpPlugin
    except ModuleNotFoundError:
        from src.fast_refine_interp_plugin import FastRefineInterpPlugin
    return FastRefineInterpPlugin


class OrographicNwp3dDownscalingCli(CliBase):
    """``orographic_nwp_3d_downscaling`` 的命令行。``run`` 转调插件 ``process``。"""

    description = "运行快速精细化插值算法。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --work-dir .\n"
        "  python cli/orographic_nwp_3d_downscaling_cli.py --work-dir .\n"
        "\n"
        "说明:\n"
        "  --update 是操作开关（0/1，是否强制更新）。\n"
        "  --maxmin-update 才是 ini 的 MaxMinInfo.update，与 --update 不是同一项。\n"
        "  --validate 对应 InstantInfo.validate，--maxmin-validate 对应 MaxMinInfo.validate。\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置文件，传给入口。相对路径按项目根目录解析。省略则用包内默认 ini。",
        )
        parser.add_argument("--work-dir", required=True, help="业务运行目录，通常放置 Fast_refine_interp_*.ini。")
        parser.add_argument("--root-path", help="业务根目录，包含 Parameter 和 lib；不传时自动推断。")
        parser.add_argument("--model-region", default="EC_12P5KM", help="模式区域，如 EC_12P5KM。")
        parser.add_argument("--s3-method", default="g_interp", help="结果目录中的算法方法名。")
        parser.add_argument("--para-file", default="Fast_refine_interp_site.ini", help="算法参数文件名。")
        parser.add_argument("--resolution", default="site", choices=["site", "1km", "5km"], help="插值分辨率。")
        parser.add_argument("--operation", default="i", choices=["i", "p", "ip"], help="i=插值，p=求参，ip=两者。")
        parser.add_argument("--begin-date", help="业务时间，格式 YYYYMMDDHH。")
        parser.add_argument("--site-name", default="Station1", help="站点文件名。")
        parser.add_argument("--debug", type=int, default=0, help="调试等级。")
        parser.add_argument("--update", type=int, default=0, help="是否强制更新，0/1。")
        _add_ini_arguments(parser, self.add_optional_bool)

    def run(
        self,
        work_dir=None,
        root_path=None,
        model_region="EC_12P5KM",
        s3_method="g_interp",
        para_file="Fast_refine_interp_site.ini",
        resolution="site",
        operation="i",
        begin_date=None,
        site_name="Station1",
        debug=0,
        update=0,
        config=None,
        dem_head=None,
        dem_format=None,
        recall=None,
        Interp_Time=None,
        validate=None,
        validate_area=None,
        del_no_eta=None,
        out_China=None,
        eta_cmn_out=None,
        VR_plot=None,
        rlt_plot=None,
        plot_format=None,
        MICAPS_out=None,
        PQ_shortname=None,
        Interp_Maxmin=None,
        maxmin_update=None,
        maxmin_validate=None,
        forecast_time=None,
        custom_path=None,
        FH_parallel=None,
        FH_max_pcount=None,
        FH_DI_timeout=None,
        FH_TI_timeout=None,
        BT_parallel=None,
        BT_max_pcount=None,
        BT_timeout=None,
        Para_parallel=None,
        Para_max_pcount=None,
        Para_timeout=None,
        **threshold,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            plugin = _plugin_cls()(
                debug=debug,
                update=update,
                operation=operation,
                begin_date=begin_date,
                resolution=resolution,
                para_file=para_file,
                work_dir=work_dir,
                model_region=model_region,
                root_path=root_path,
                s3_method=s3_method,
                site_name=site_name,
            )
            return plugin.process(
                config=config,
                dem_head=dem_head,
                dem_format=dem_format,
                recall=recall,
                Interp_Time=Interp_Time,
                validate=validate,
                validate_area=validate_area,
                del_no_eta=del_no_eta,
                out_China=out_China,
                eta_cmn_out=eta_cmn_out,
                VR_plot=VR_plot,
                rlt_plot=rlt_plot,
                plot_format=plot_format,
                MICAPS_out=MICAPS_out,
                PQ_shortname=PQ_shortname,
                Interp_Maxmin=Interp_Maxmin,
                maxmin_update=maxmin_update,
                maxmin_validate=maxmin_validate,
                forecast_time=forecast_time,
                custom_path=custom_path,
                FH_parallel=FH_parallel,
                FH_max_pcount=FH_max_pcount,
                FH_DI_timeout=FH_DI_timeout,
                FH_TI_timeout=FH_TI_timeout,
                BT_parallel=BT_parallel,
                BT_max_pcount=BT_max_pcount,
                BT_timeout=BT_timeout,
                Para_parallel=Para_parallel,
                Para_max_pcount=Para_max_pcount,
                Para_timeout=Para_timeout,
                **threshold,
            )
        finally:
            if config:
                set_main_ini(None)


def build_parser() -> argparse.ArgumentParser:
    return OrographicNwp3dDownscalingCli().build_parser()


def orographic_nwp_3d_downscaling_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return OrographicNwp3dDownscalingCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(orographic_nwp_3d_downscaling_cli())
