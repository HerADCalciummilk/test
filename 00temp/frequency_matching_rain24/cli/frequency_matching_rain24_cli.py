# -*- coding: utf-8 -*-
"""24 小时降水频率匹配订正命令行。

解析参数后调用 ``correct_tp_24h.process``（原光流 ``cal_optical_flow``，
原 Cressman ``interpolation.GressManInterpolation``）。
项目光流与项目 Cressman 用 ``correct_tp_24h_nowcast.process``。

在本包目录执行::

    python -m cli --plugin=resource/CMA_MESO.json
    python cli/frequency_matching_rain24_cli.py --plugin=resource/CMA_MESO.json

Python::

    from cli.frequency_matching_rain24_cli import FrequencyMatchingRain24Cli
    FrequencyMatchingRain24Cli.call(plugin="resource/CMA_MESO.json", pro_count=8)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths():
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    # 项目根须在 src 之前，保证 utils 包走根目录 utils/__init__.py（合并 src/utils）
    for path in (str(root), str(src)):
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_paths()

from correct_tp_24h import process
from utils.cli_base import CliBase


def _parse_bool(text):
    """解析 true/false/1/0；空串视为未指定（None）。"""
    if text is None:
        return None
    value = str(text).strip().lower()
    if value in ("", "none"):
        return None
    if value in ("1", "true", "yes", "y", "on"):
        return True
    if value in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("期望布尔值：true/false/1/0/yes/no")


def _parse_rpt_list(text):
    """逗号分隔起报时间，如 2025100100,2025100112；空串视为未指定。"""
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _parse_clip_coords(text):
    """slon,elon,slat,elat；空串视为未指定。"""
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    parts = [item.strip() for item in value.split(",") if item.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("clip_coords 需要 4 个浮点数：slon,elon,slat,elat")
    return [float(item) for item in parts]


def _add_text(parser, dest, help_text):
    parser.add_argument(
        f"--{dest.replace('_', '-')}",
        dest=dest,
        default=None,
        metavar="VALUE",
        help=help_text,
    )


def _add_int(parser, dest, help_text):
    parser.add_argument(
        f"--{dest.replace('_', '-')}",
        dest=dest,
        type=int,
        default=None,
        metavar="N",
        help=help_text,
    )


class FrequencyMatchingRain24Cli(CliBase):
    """``frequency_matching_rain24`` 的命令行。``run`` 转调 ``process``。"""

    description = (
        "frequency_matching_rain24：24 小时累积降水频率匹配订正。\n"
        "本命令解析参数后调用主程序 correct_tp_24h.process"
        "（原光流 cal_optical_flow，原 Cressman interpolation）。\n"
        "未在命令行给出的项从配置 ini 读取，默认 resource/conf.ini。\n"
        "项目光流与项目 Cressman 见 correct_tp_24h_nowcast.py。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli --help\n"
        "  python -m cli --plugin=resource/CMA_MESO.json\n"
        "  python cli/frequency_matching_rain24_cli.py --plugin=resource/CMA_MESO.json\n"
        "  python -m cli --config=resource/conf.ini "
        "--rpt-list=2025100100,2025100112 --is-multi true --pro-count 8\n"
        "\n"
        "说明:\n"
        "  - 本命令固定走 correct_tp_24h（cal_optical_flow + interpolation）\n"
        "  - 项目光流/Cressman：from correct_tp_24h_nowcast import process\n"
        "    或 python src/correct_tp_24h_nowcast.py\n"
        "  - --config 指定运行配置 ini，并传给 process；省略则用 resource/conf.ini\n"
        "  - 起报为空或未指定时，按该 ini 的 rpt_list（空则走实时最近一天）\n"
        "  - 预报时效默认由该 ini 的 start_dtime/end_dtime/inter_dtime* 决定，可用同名参数覆盖\n"
        "  - 多进程任务粒度为「起报 × 时效」，与主程序一致\n"
        "  - 双线性：本命令用 interpolation.py；项目双线性见 interpolation_gg_linear.py\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--plugin",
            default=None,
            metavar="PATH",
            help=(
                "模式路径配置 JSON（含 tp_model / tp_obs / correct_tp_outpath）。"
                "示例：resource/CMA_MESO.json。"
                "省略则使用配置 ini 的 default_plugin。"
            ),
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help=(
                "运行配置 ini，传给 correct_tp_24h.process 的 config。"
                "相对路径按项目根目录解析。"
                "省略则使用 resource/conf.ini。"
            ),
        )
        parser.add_argument(
            "--rpt-list",
            dest="rpt_list",
            type=_parse_rpt_list,
            default=None,
            metavar="YYYYMMDDHH[,...]",
            help=(
                "起报时间列表，逗号分隔，传给 process 的 rpt_list。"
                "process 在 rpt_times 为 None 时使用它。"
                "1 个值表示单时次；2 个值表示起止闭区间（按 report_inter 展开）；"
                "省略则使用配置 ini 的 rpt_list（空表示实时）。"
            ),
        )
        parser.add_argument(
            "--is-multi",
            type=_parse_bool,
            default=None,
            metavar="BOOL",
            help=(
                "是否用多进程并行调度「起报×时效」任务。"
                "取值：true/false（或 1/0）。"
                "省略则使用配置 ini 的 is_multi（默认 true）。"
            ),
        )
        parser.add_argument(
            "--pro-count",
            type=int,
            default=None,
            metavar="N",
            help=(
                "多进程并行进程数（正整数）。"
                "仅在 is_multi=true 时生效。"
                "省略则使用配置 ini 的 pro_count（若无则回退旧键 pool_num）。"
            ),
        )
        _add_text(
            parser,
            "default_plugin",
            "覆盖 ini 的 default_plugin。同时给出 --plugin 时以 --plugin 为准。省略则用 ini。",
        )
        _add_text(parser, "log_file", "日志路径模板，覆盖 ini 的 log_file。省略则用 ini。")
        _add_text(parser, "station_info", "站点表路径，覆盖 ini 的 station_info。省略则用 ini。")
        _add_text(parser, "mask_nc", "掩膜 nc 路径，覆盖 ini 的 mask_nc。省略则用 ini。")
        _add_int(parser, "ipt_model", "模式时间类型，覆盖 ini 的 ipt_model。省略则用 ini。")
        _add_int(parser, "ipt_obs", "实况时间类型，覆盖 ini 的 ipt_obs。省略则用 ini。")
        _add_text(parser, "ipt_type", "模式资料格式，覆盖 ini 的 ipt_type。省略则用 ini。")
        _add_text(parser, "opt_type", "输出格式，覆盖 ini 的 opt_type。省略则用 ini。")
        _add_int(parser, "over_w", "已有产品是否覆盖，覆盖 ini 的 over_w。省略则用 ini。")
        _add_int(parser, "start_dtime", "起始预报时效，覆盖 ini 的 start_dtime。省略则用 ini。")
        _add_int(parser, "end_dtime", "结束预报时效，覆盖 ini 的 end_dtime。省略则用 ini。")
        _add_int(parser, "inter_dtime1", "短时效步长，覆盖 ini 的 inter_dtime1。省略则用 ini。")
        _add_int(parser, "inter_dtime2", "长时效步长，覆盖 ini 的 inter_dtime2。省略则用 ini。")
        _add_int(parser, "report_inter", "起报间隔小时，覆盖 ini 的 report_inter。省略则用 ini。")
        parser.add_argument(
            "--res",
            dest="res",
            type=float,
            default=None,
            metavar="DEG",
            help="格距，覆盖 ini 的 res。省略则用 ini。",
        )
        parser.add_argument(
            "--clip-coords",
            dest="clip_coords",
            type=_parse_clip_coords,
            default=None,
            metavar="SLON,ELON,SLAT,ELAT",
            help="裁剪范围四个浮点数，覆盖 ini 的 clip_coords，并同步 slon/elon/slat/elat。省略则用 ini。",
        )

    def run(
        self,
        plugin=None,
        config=None,
        rpt_list=None,
        is_multi=None,
        pro_count=None,
        default_plugin=None,
        log_file=None,
        station_info=None,
        mask_nc=None,
        ipt_model=None,
        ipt_obs=None,
        ipt_type=None,
        opt_type=None,
        over_w=None,
        start_dtime=None,
        end_dtime=None,
        inter_dtime1=None,
        inter_dtime2=None,
        report_inter=None,
        res=None,
        clip_coords=None,
    ) -> int:
        process(
            plugin=plugin,
            default_plugin=default_plugin,
            config=config,
            is_multi=is_multi,
            pro_count=pro_count,
            rpt_list=rpt_list,
            log_file=log_file,
            station_info=station_info,
            mask_nc=mask_nc,
            ipt_model=ipt_model,
            ipt_obs=ipt_obs,
            ipt_type=ipt_type,
            opt_type=opt_type,
            over_w=over_w,
            start_dtime=start_dtime,
            end_dtime=end_dtime,
            inter_dtime1=inter_dtime1,
            inter_dtime2=inter_dtime2,
            report_inter=report_inter,
            res=res,
            clip_coords=clip_coords,
        )
        return 0


def _build_parser() -> argparse.ArgumentParser:
    return FrequencyMatchingRain24Cli().build_parser()


def frequency_matching_rain24_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return FrequencyMatchingRain24Cli().main(argv)


if __name__ == "__main__":
    raise SystemExit(frequency_matching_rain24_cli())
