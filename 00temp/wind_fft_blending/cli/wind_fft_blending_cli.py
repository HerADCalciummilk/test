# -*- coding: utf-8 -*-
"""多风场 FFT 融合命令行。

在本包目录执行::

    python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11>
    python cli/wind_fft_blending_cli.py --main-uv <主风场.m11> --ass-uv <辅助风场.m11>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
_00TEMP = _ROOT.parent
for _p in (str(_ROOT), str(_SRC), str(_00TEMP)):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_00TEMP))
sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_ROOT))

_TEST_DATA = (
    _ROOT.parents[1].parent
    / "NIMM_pip_testdata"
    / "multi_wind_fft_blending"
    / "test_data"
)

from utils.cli_base import CliBase

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


class WindFftBlendingCli(CliBase):
    """``wind_fft_blending`` 的命令行。``run`` 转调 ``main.process``。"""

    description = (
        "多风场 FFT 融合执行入口。\n"
        "未在命令行给出的项先读 resource/conf.ini，ini 无该项再用代码预设。"
    )
    epilog = (
        "命令行示例（在本包根目录执行）:\n"
        "  python -m cli --help\n"
        "  python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11> "
        "--output-dir resource/output --output-prefix sample_a\n\n"
        "样例数据目录（与 NIMM_pip_repos 同级）:\n"
        f"  {_TEST_DATA}\n\n"
        "单任务示例:\n"
        "  python -m cli \\\n"
        f"    --main-uv {_TEST_DATA}/sample_a1_uv.m11 \\\n"
        f"    --ass-uv {_TEST_DATA}/sample_a2_uv.m11 \\\n"
        f"    --output-dir {_TEST_DATA} \\\n"
        "    --output-prefix sample_a\n\n"
        "多任务 + 多进程示例:\n"
        "  python -m cli \\\n"
        f"    --main-uv {_TEST_DATA}/sample_a1_uv.m11 {_TEST_DATA}/sample_b1_uv.m11 \\\n"
        f"    --ass-uv {_TEST_DATA}/sample_a2_uv.m11 {_TEST_DATA}/sample_b2_uv.m11 \\\n"
        "    --output-prefix sample_a sample_b \\\n"
        f"    --output-dir {_TEST_DATA} \\\n"
        "    --is-multi --pro-count 2\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--main-uv",
            dest="main_uv_path",
            nargs="+",
            default=None,
            help="主风场 Micaps11；可传多个表示多个任务。省略则读 ini 的 main_uv_path",
        )
        parser.add_argument(
            "--ass-uv",
            dest="ass_uv_path",
            nargs="+",
            default=None,
            help="辅助风场 Micaps11。单主场时可多个，多主场时数量须与主场一致。省略则读 ini 的 ass_uv_path",
        )
        parser.add_argument(
            "--output-dir",
            default=None,
            help="输出目录。省略则读 ini 的 output_dir，预设 resource/output",
        )
        parser.add_argument(
            "--output-prefix",
            nargs="+",
            default=None,
            help="输出文件名前缀；多主场时数量须与主场一致。省略则读 ini，预设 fft_merge",
        )
        parser.add_argument(
            "--feature-border",
            type=int,
            default=None,
            help="FFT 特征匹配网格边长。省略则读 ini 的 feature_border，预设 128",
        )
        parser.add_argument(
            "--max-iterations",
            type=int,
            default=None,
            help="位移场求解最大迭代次数。省略则读 ini，预设 1024",
        )
        parser.add_argument(
            "--move-percent",
            type=float,
            default=None,
            help="主场向辅助场移动比例 (0, 1]。省略则读 ini，预设 1.0",
        )
        parser.add_argument(
            "--write-linear-compare",
            dest="write_linear_compare",
            action="store_true",
            default=None,
            help="写出线性平均对比结果。省略则读 ini，预设开启",
        )
        parser.add_argument(
            "--no-write-linear-compare",
            dest="write_linear_compare",
            action="store_false",
            default=None,
            help="不写出线性平均对比结果",
        )
        parser.add_argument(
            "--is-multi",
            dest="is_multi",
            action="store_true",
            default=None,
            help="多任务时多进程执行。省略则读 ini，预设关闭（串行）",
        )
        parser.add_argument(
            "--no-is-multi",
            dest="is_multi",
            action="store_false",
            default=None,
            help="多任务时串行执行",
        )
        parser.add_argument(
            "--pro-count",
            type=int,
            default=None,
            help="多进程并行数（--is-multi 时生效）。省略则读 ini，预设 4",
        )
        parser.add_argument(
            "--weight-value", dest="weight_value", type=float, default=None,
            help="频域约束权重。省略则读 ini，预设 0.1",
        )
        parser.add_argument(
            "--power-model", dest="power_model", type=int, default=None,
            help="平滑滤波幂律指数，2 或 4。省略则读 ini，预设 2",
        )
        parser.add_argument(
            "--l-scale", dest="l_scale", type=int, default=None,
            help="FFT 谱域尺度比率。省略则读 ini，预设 1",
        )
        parser.add_argument(
            "--reflect-pad", dest="reflect_pad", type=int, default=None,
            help="反射边界像素。省略则读 ini，预设 25",
        )
        parser.add_argument(
            "--config",
            dest="config",
            default=None,
            metavar="PATH",
            help=_CONFIG_HELP,
        )

    def run(
        self,
        main_uv_path=None,
        ass_uv_path=None,
        output_dir=None,
        output_prefix=None,
        feature_border=None,
        max_iterations=None,
        move_percent=None,
        write_linear_compare=None,
        is_multi=None,
        pro_count=None,
        weight_value=None,
        power_model=None,
        l_scale=None,
        reflect_pad=None,
        config=None,
    ) -> int:
        from main import process

        try:
            result = process(
                main_uv_path=main_uv_path,
                ass_uv_path=ass_uv_path,
                output_dir=output_dir,
                output_prefix=output_prefix,
                feature_border=feature_border,
                max_iterations=max_iterations,
                move_percent=move_percent,
                write_linear_compare=write_linear_compare,
                is_multi=is_multi,
                pro_count=pro_count,
                weight_value=weight_value,
                power_model=power_model,
                l_scale=l_scale,
                reflect_pad=reflect_pad,
                config=config,
            )
        except Exception as exc:
            print(f"执行失败: {exc}", file=sys.stderr)
            return 1

        if isinstance(result, list):
            return 0 if result and all(result) else 1
        return 0 if result else 1


def _build_arg_parser() -> argparse.ArgumentParser:
    return WindFftBlendingCli().build_parser()


def wind_fft_blending_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return WindFftBlendingCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(wind_fft_blending_cli())
