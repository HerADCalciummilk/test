"""CLI for cal_griddata_TimeSplit_plugin.

参数优先级：命令行 > ``resource/conf.ini`` > 代码预设。

模块级 ``process`` 是本 CLI 的核心，负责：
1. 用 ``resolve_args`` 补齐参数；
2. 解析 ``input_fh`` / ``output_fh`` / ``time``；
3. 调用 ``read_multi_griddata`` 读主场（及可选 V 分量）并拼接；
4. 构造 ``TimeSplit``，对内存场做插值（写出由插件按 ``output_fmt`` 处理）。

插件 ``TimeSplit.process`` 只接收内存场；路径、``input_fh``、``is_fill0``、
``io_method`` 只在本模块处理。读数与拼接逻辑直接写在 ``process`` 内，
不再另设 ``load_timesplit_field`` 等辅助函数。

``index`` 与读数的对应关系：
- ``dtime``：一个起报 + 多个时效（``is_ob=False``）；``input_fh`` 为小时时效三元组。
- ``time``：多个起报沿 ``time`` 拼（``is_ob=True``，读入后 ``dtime=0``）。
  ``time`` 可逗号分隔多钟点；若只给一个锚点，则用展开后的 ``input_fh`` 作小时偏移。

在本包目录执行::

    python -m cli.cal_griddata_TimeSplit_plugin_cli --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100
    python cli/cal_griddata_TimeSplit_plugin_cli.py --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100

Python::

    from cli.cal_griddata_TimeSplit_plugin_cli import CalGriddataTimeSplitPluginCli, process
    process(input_fh="0,72,3", output_fh="0,72,1", input_fmt="fcst/YYYYMMDDHH.TTT.nc", time="2023070100")
    CalGriddataTimeSplitPluginCli.call(input_fh="0,72,3", output_fh="0,72,1", input_fmt="fcst/YYYYMMDDHH.TTT.nc", time="2023070100")
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

import numpy as np


def _bootstrap_paths() -> None:
    """把本包根目录放进 ``sys.path``，便于 ``src`` / ``utils`` 导入。"""
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.grid_combine import read_multi_griddata
from utils.util_env import resolve_args


def process(
    input_fh: Optional[str] = None,
    output_fh: Optional[str] = None,
    interp_method: Optional[str] = None,
    input_fmt: Optional[str] = None,
    time: Optional[str] = None,
    output_fmt: Optional[str] = None,
    uv_fmt: Optional[str] = None,
    delta: Optional[str] = None,
    is_fill0: Optional[bool] = None,
    is_min: Optional[bool] = None,
    index: Optional[str] = None,
    config: Optional[str] = None,
    io_method=None,
) -> Tuple[Any, Any]:
    """CLI 核心：补齐参数，读数拼接，再调用 ``TimeSplit``。

    未显式给出的参数按「命令行 > conf.ini > 预设」补齐。

    读数侧（本函数内完成，不进插件构造）：
    ``input_fh`` / ``input_fmt`` / ``time`` / ``uv_fmt`` / ``is_fill0`` / ``io_method``。

    插件侧（传给 ``TimeSplit``）：
    ``output_fh`` → ``output_fh_list``，以及 ``interp_method`` / ``output_fmt`` /
    ``delta`` / ``is_min``→``is_Min`` / ``index``。

    Args:
        input_fh: 输入时效 ``start,stop,step``，单位小时，终点包含在结果中。
            ``index=dtime`` 时即读文件用的预报时效序列。
            ``index=time`` 且 ``time`` 只有一个锚点时，作相对锚点的小时偏移列表。
        output_fh: 输出坐标 ``start,stop,step``。``is_min`` 为真时单位是分钟，
            否则是小时；终点包含在结果中。原样交给插件展开。
        interp_method: 传给 ``DataArray.interp`` 的方法，默认由 ini/预设给出（``slinear``）。
        input_fmt: 输入路径模板，可含 ``YYYY``、``MM``、``DD``、``HH``、``TTT`` 等。
        time: 起报/时次字符串。支持 ``YYYYMMDDHH`` 或 ``YYYYMMDDHHMM``。
            ``index=dtime`` 时必须恰好一个起报。
            ``index=time`` 时可逗号分隔多个钟点（相对首时次须差整小时），
            或只给锚点再用 ``input_fh`` 展开偏移。
        output_fmt: 输出路径模板。为空时插件不写文件。
        uv_fmt: V 分量路径模板。为空时不做风速合成；非空时用与主场相同的
            ``read_time`` / ``read_fhs`` / ``is_ob`` / ``is_fill0`` 再读一遍。
        delta: 累计场差分间隔。为空时不做差分、不裁负（瞬时场走此路径）。
            单位与 ``is_min`` 一致：假=小时，真=分钟；不必等于 ``output_fh`` 步长。
        is_fill0: 仅影响读数：``index=dtime`` 时时效 0 不读文件、改用全 0 场。
            与插件内 ``_ensure_lead0``（插值前补时效 0）是两层不同逻辑。
        is_min: 输出坐标是否按分钟（对应插件 ``is_Min``）。输入读数时效仍是小时。
        index: 插值轴，``dtime`` 或 ``time``；同时决定 ``read_multi_griddata`` 的 ``is_ob``。
        config: 运行配置 ini。相对路径按本包目录解析；省略则用 ``resource/conf.ini``。
        io_method: 读网格函数。为空时使用 ``meteva_base.read_griddata_from_nc``。

    Returns:
        ``(细时间场, 插值前的粗时间场)``。读数失败或插值失败时对应项可能为 ``None``。
    """
    from src.cal_griddata_TimeSplit_plugin import TimeSplit

    # 1) 补齐运行参数（命令行显式值优先，其余走 conf / 预设）
    cfg = resolve_args(
        module="timesplit",
        input_fh=input_fh,
        output_fh=output_fh,
        interp_method=interp_method,
        input_fmt=input_fmt,
        time=time,
        output_fmt=output_fmt,
        uv_fmt=uv_fmt,
        delta=delta,
        is_fill0=is_fill0,
        is_min=is_min,
        index=index,
        config=config,
    )

    axis = str(cfg["index"])
    if axis not in ("dtime", "time"):
        raise ValueError("index 只支持 dtime 或 time")
    fill0 = bool(cfg["is_fill0"])

    # 2) 解析时效三元组：input 在此展开成读数用的 fhs；output 只校验后交给插件再展开
    in_parts = [item.strip() for item in str(cfg["input_fh"]).split(",") if item.strip()]
    if len(in_parts) != 3:
        raise ValueError(f"时效三元组须是 start,stop,step，收到: {cfg['input_fh']}")
    in_start, in_stop, in_step = (float(v) for v in in_parts)
    # 与插件一致：stop 含端点（arange 上界用 stop+1）
    fhs = np.arange(in_start, in_stop + 1, in_step)
    if np.allclose(fhs, np.rint(fhs)):
        fhs = np.rint(fhs).astype(np.int64)

    out_parts = [item.strip() for item in str(cfg["output_fh"]).split(",") if item.strip()]
    if len(out_parts) != 3:
        raise ValueError(f"时效三元组须是 start,stop,step，收到: {cfg['output_fh']}")
    output_fh_list = [float(v) for v in out_parts]

    # 3) 解析 time：支持 YYYYMMDDHH / YYYYMMDDHHMM；dtime 模式限一个起报
    raw_times = [item.strip() for item in str(cfg["time"]).split(",") if item.strip()]
    if not raw_times:
        raise ValueError("time 未指定")
    times = []
    for item in raw_times:
        if len(item) == 12:
            times.append(datetime.strptime(item, "%Y%m%d%H%M"))
        else:
            times.append(datetime.strptime(item, "%Y%m%d%H"))

    if axis == "dtime":
        # 一报多时效：is_ob=False，read_fhs 即展开后的 input_fh
        if len(times) != 1:
            raise ValueError("index=dtime 时 time 只能有一个起报时间")
        read_time = times[0]
        read_fhs = fhs
        is_ob = False
    else:
        # 多钟点沿 time 拼：is_ob=True。多钟点 → 相对首时次的整小时偏移；
        # 单钟点 → 用展开后的 input_fh 作偏移（仍读同一模板上的多个时次）。
        if len(times) > 1:
            anchor = times[0]
            read_fhs = []
            for item in times:
                hours = (item - anchor).total_seconds() / 3600.0
                rounded = round(hours)
                if abs(hours - rounded) >= 1e-6:
                    raise ValueError(
                        f"index=time 时各时次须与首时次相差整小时，收到锚点 {anchor} 与 {item}"
                    )
                read_fhs.append(int(rounded))
            read_time = anchor
        else:
            read_time = times[0]
            read_fhs = list(fhs)
        is_ob = True

    # 4) 读主场；若有 uv_fmt 再读 V（同一套 read_time / read_fhs / is_ob / is_fill0）
    fcst = None
    uv = None
    for kind, fmt in (("主场", cfg["input_fmt"]), ("V 分量", cfg.get("uv_fmt"))):
        if not fmt:
            continue
        grd = read_multi_griddata(
            fmt,
            read_time,
            read_fhs,
            io_method=io_method,
            is_ob=is_ob,
            is_fill0=fill0,
        )
        if grd is None:
            print(f"未读到{kind}数据")
            return None, None
        if kind == "主场":
            fcst = grd
        else:
            uv = grd

    # 5) 构造插件并对内存场插值（写出由插件按 output_fmt 处理）
    splitter = TimeSplit(
        output_fh_list=output_fh_list,
        interp_method=cfg["interp_method"],
        output_fmt=cfg.get("output_fmt"),
        delta=cfg.get("delta"),
        is_Min=bool(cfg["is_min"]),
        index=axis,
    )
    return splitter.process(fcst, uv=uv)


class CalGriddataTimeSplitPluginCli(CliBase):
    """拆分粗预报时效。``run`` 转调模块级 ``process``（读数 + 插件插值）。"""

    prog = "python -m cli.cal_griddata_TimeSplit_plugin_cli"
    description = (
        "Split coarse forecast lead times. Missing args come from resource/conf.ini, then presets. "
        "run() calls process() for reading and TimeSplit."
    )
    epilog = (
        "Example:\n"
        "  python -m cli.cal_griddata_TimeSplit_plugin_cli "
        "--input-fh 0,72,3 --output-fh 0,72,1 "
        "--input-fmt <template> --time 2023070100\n"
        "  python cli/cal_griddata_TimeSplit_plugin_cli.py "
        "--input-fh 0,72,3 --output-fh 0,72,1 "
        "--input-fmt <template> --time 2023070100\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """声明 CLI 参数；默认 ``None`` 表示交给 ini / 预设。"""
        parser.add_argument(
            "--input-fh",
            default=None,
            help="Input leads start,stop,step (hours) for reading; stop included. "
            "With --index time and a single --time, used as hour offsets from that anchor. Empty ini value raises.",
        )
        parser.add_argument(
            "--output-fh",
            default=None,
            help="Output coords start,stop,step for TimeSplit; stop included. "
            "Hours, or minutes when --is-min. Empty ini value raises.",
        )
        parser.add_argument(
            "--is-min",
            dest="is_min",
            action="store_true",
            default=None,
            help="Output coords are minutes. Input reading leads stay hours. Preset off.",
        )
        parser.add_argument(
            "--no-is-min",
            dest="is_min",
            action="store_false",
            default=None,
            help="Output coords are hours.",
        )
        parser.add_argument("--interp-method", default=None, help="Interpolation method for DataArray.interp. Preset slinear.")
        parser.add_argument(
            "--input-fmt",
            default=None,
            help="Input path template for process reading (YYYY/MM/DD/HH/TTT...). Empty ini value raises.",
        )
        parser.add_argument(
            "--index",
            default=None,
            choices=["dtime", "time"],
            help="Interp axis and read mode: dtime=one issue + multi leads; time=multi issues along time. Preset dtime.",
        )
        parser.add_argument(
            "--time",
            default=None,
            help="Issue time YYYYMMDDHH or YYYYMMDDHHMM. For --index time, comma-separated issues (whole-hour gaps) or one anchor. Empty ini value raises.",
        )
        parser.add_argument("--output-fmt", default=None, help="Output path template. Empty means do not write.")
        parser.add_argument(
            "--uv-fmt",
            default=None,
            help="V-wind path template; same time/lead args as main field. Empty means skip wind speed.",
        )
        parser.add_argument(
            "--delta",
            default=None,
            help="Cumulative-field difference interval. Hours when --no-is-min, minutes when --is-min. "
            "Need not equal output step. Empty means skip difference and nonnegative clip.",
        )
        parser.add_argument(
            "--is-fill0",
            dest="is_fill0",
            action="store_true",
            default=None,
            help="When reading (index=dtime), fill lead 0 with zeros instead of a file.",
        )
        parser.add_argument(
            "--no-is-fill0",
            dest="is_fill0",
            action="store_false",
            default=None,
            help="When reading, load lead 0 from file if present.",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="Runtime ini passed to process. A relative path is resolved from the package root. Omit to use resource/conf.ini.",
        )

    def run(
        self,
        input_fh=None,
        output_fh=None,
        interp_method=None,
        input_fmt=None,
        time=None,
        output_fmt=None,
        uv_fmt=None,
        delta=None,
        is_fill0=None,
        is_min=None,
        index=None,
        config=None,
    ) -> int:
        """命令行与 ``Cli.call`` 的入口；参数原样交给模块级 ``process``。"""
        process(
            input_fh=input_fh,
            output_fh=output_fh,
            interp_method=interp_method,
            input_fmt=input_fmt,
            time=time,
            output_fmt=output_fmt,
            uv_fmt=uv_fmt,
            delta=delta,
            is_fill0=is_fill0,
            is_min=is_min,
            index=index,
            config=config,
        )
        return 0


def build_parser() -> argparse.ArgumentParser:
    """供测试与外部复用的参数解析器。"""
    return CalGriddataTimeSplitPluginCli().build_parser()


def cal_griddata_TimeSplit_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli....`` 与直接运行本文件都进这里。"""
    return CalGriddataTimeSplitPluginCli().main(argv)


main = cal_griddata_TimeSplit_plugin_cli


if __name__ == "__main__":
    raise SystemExit(cal_griddata_TimeSplit_plugin_cli())
