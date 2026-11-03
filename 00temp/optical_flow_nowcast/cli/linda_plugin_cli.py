"""CLI for linda_plugin.

Run from this package directory::

    python -m cli.linda_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6
    python cli/linda_plugin_cli.py --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths() -> None:
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import resolve_args


class LindaPluginCli(CliBase):
    """LINDA 临近预报。"""

    prog = "python -m cli.linda_plugin_cli"
    description = (
        "LINDA 临近预报。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。\n"
        "只打印解析后的参数，不读取降水场，不运行预报。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.linda_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6\n"
        "  python cli/linda_plugin_cli.py --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--precip", default=None, help="降水场路径，多个用逗号分隔。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--velocity", default=None, help="平流速度场路径。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--timesteps", type=int, default=None, help="外推时次数。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--delta-min", dest="delta_min", type=int, default=None, help="实况间隔，分钟。省略则读 ini，预设 10")
        parser.add_argument("--add-perturbations", dest="add_perturbations", action="store_true", default=None, help="加扰动得到集合。省略则读 ini，预设不加")
        parser.add_argument("--no-add-perturbations", dest="add_perturbations", action="store_false", default=None, help="只做确定性预报")
        parser.add_argument("--feature-method", dest="feature_method", default=None, help="特征检测。省略则读 ini，预设 blob")
        parser.add_argument("--max-num-features", dest="max_num_features", type=int, default=None, help="最多保留的特征数。省略则读 ini，预设 25")
        parser.add_argument("--ari-order", dest="ari_order", type=int, default=None, help="ARI 阶数。省略则读 ini，预设 1")
        parser.add_argument("--kernel-type", dest="kernel_type", default=None, help="核类型。省略则读 ini，预设 anisotropic")
        parser.add_argument("--localization-window-radius", dest="localization_window_radius", type=float, default=None, help="定位窗标准差。省略则读 ini，预设由场尺寸决定")
        parser.add_argument("--errdist-window-radius", dest="errdist_window_radius", type=float, default=None, help="误差分布窗标准差。省略则读 ini，预设由场尺寸决定")
        parser.add_argument("--acf-window-radius", dest="acf_window_radius", type=float, default=None, help="误差自相关窗标准差。省略则读 ini，预设由场尺寸决定")
        parser.add_argument("--extrap-method", dest="extrap_method", default=None, help="外推方法。省略则读 ini，预设 semilagrangian")
        parser.add_argument("--pert-thrs", dest="pert_thrs", default=None, help="扰动参数估计阈值，两个数。省略则读 ini，预设 0.5,1.0")
        parser.add_argument("--n-ens-members", dest="n_ens_members", type=int, default=None, help="集合成员数。省略则读 ini，预设 10")
        parser.add_argument("--vel-pert-method", dest="vel_pert_method", default=None, help="平流扰动。省略则读 ini，预设 bps")
        parser.add_argument("--kmperpixel", type=float, default=None, help="空间分辨率（千米/像素）。省略则读 ini，预设空")
        parser.add_argument("--timestep", type=float, default=None, help="速度场时间步（分钟）。省略则读 ini，预设空")
        parser.add_argument("--num-workers", dest="num_workers", type=int, default=None, help="并行 worker 数。省略则读 ini，预设 1")
        parser.add_argument("--seed", type=int, default=None, help="随机种子。省略则读 ini，预设空")
        parser.add_argument("--use-multiprocessing", dest="use_multiprocessing", action="store_true", default=None, help="使用多进程。省略则读 ini，预设关闭")
        parser.add_argument("--no-use-multiprocessing", dest="use_multiprocessing", action="store_false", default=None, help="不使用多进程")
        parser.add_argument("--measure-time", dest="measure_time", action="store_true", default=None, help="统计耗时。省略则读 ini，预设不统计")
        parser.add_argument("--no-measure-time", dest="measure_time", action="store_false", default=None, help="不统计耗时")
        parser.add_argument("--return-output", dest="return_output", action="store_true", default=None, help="返回预报场。省略则读 ini，预设返回")
        parser.add_argument("--no-return-output", dest="return_output", action="store_false", default=None, help="不返回预报场")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        cfg = resolve_args("linda", **params)
        print("linda_plugin")
        print(" ".join(f"{key}={value}" for key, value in cfg.items()))
        return 0


def build_parser() -> argparse.ArgumentParser:
    return LindaPluginCli().build_parser()


def linda_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.linda_plugin_cli`` 与直接运行本文件都进这里。"""
    return LindaPluginCli().main(argv)


main = linda_plugin_cli


if __name__ == "__main__":
    raise SystemExit(linda_plugin_cli())
