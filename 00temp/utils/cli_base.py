# -*- coding: utf-8 -*-
"""子模块命令行基类。

命令行和 Python 调用进同一个 ``run``。参数没给时保持声明时的默认值
（约定为 ``None``），由子类 ``run`` 再读 ini / 预设。本类不读配置文件。

子类只实现两处：

- ``add_arguments``：声明参数
- ``run``：入口主函数，调用本模块的 ``process`` 或插件

命令行::

    python -m cli --mode lonlat-to-equal

Python::

    from cli.projection_cli import ProjectionCli
    ProjectionCli.call(mode="lonlat-to-equal", grid_distance=5000)
"""
from __future__ import annotations

import argparse
import sys
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Sequence


class CliBase(ABC):
    """命令行与 Python 共用的入口基类。"""

    prog: str = "python -m cli"
    description: str = ""
    epilog: str = ""
    formatter_class = argparse.RawDescriptionHelpFormatter

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """子类在此声明参数。省略项的默认值用 ``None``，表示交给 ini / 预设。"""

    @abstractmethod
    def run(self, **params: Any) -> Optional[int]:
        """入口主函数。返回 ``None`` 或 ``0`` 表示成功，其他整数作为退出码。"""

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=self.prog,
            description=self.description,
            epilog=self.epilog or None,
            formatter_class=self.formatter_class,
        )
        self.add_arguments(parser)
        return parser

    def main(self, argv: Optional[Sequence[str]] = None) -> int:
        """命令行入口。``argv`` 为 ``None`` 时使用 ``sys.argv[1:]``。"""
        parser = self.build_parser()
        args = parser.parse_args(None if argv is None else list(argv))
        return self._dispatch(vars(args))

    @classmethod
    def call(cls, **kwargs: Any) -> int:
        """Python 入口。关键字须是参数的 dest，例如 ``grid_distance``。"""
        app = cls()
        parser = app.build_parser()
        dests = _param_dests(parser)
        unknown = sorted(set(kwargs) - dests)
        if unknown:
            known = ", ".join(sorted(dests)) or "(无)"
            names = ", ".join(unknown)
            raise TypeError(
                f"{cls.__name__}.call() 收到未知参数: {names}。可用参数: {known}"
            )
        params = _param_defaults(parser)
        params.update(kwargs)
        return app._dispatch(params)

    @staticmethod
    def add_optional_bool(
        parser: argparse.ArgumentParser,
        flag: str,
        *,
        dest: Optional[str] = None,
        help_true: str,
        help_false: str,
    ) -> None:
        """登记一对可选布尔开关。省略时 dest 为 ``None``。

        ``flag="--is-multi"`` 会同时登记 ``--is-multi`` 与 ``--no-is-multi``。
        """
        name = flag.lstrip("-").replace("_", "-")
        if not name or name.startswith("no-"):
            raise ValueError(
                f"布尔参数须是正向开关名，例如 --is-multi，收到 {flag!r}"
            )
        option_dest = dest or name.replace("-", "_")
        parser.add_argument(
            f"--{name}",
            dest=option_dest,
            action="store_true",
            default=None,
            help=help_true,
        )
        parser.add_argument(
            f"--no-{name}",
            dest=option_dest,
            action="store_false",
            default=None,
            help=help_false,
        )

    def _dispatch(self, params: Dict[str, Any]) -> int:
        try:
            code = self.run(**params)
            return _exit_code(code)
        except NotImplementedError:
            raise
        except Exception:
            print("执行失败:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return 1


def _param_actions(parser: argparse.ArgumentParser):
    for action in parser._actions:
        dest = action.dest
        if not dest or dest == argparse.SUPPRESS:
            continue
        if isinstance(action, (argparse._HelpAction, argparse._VersionAction)):
            continue
        if action.default is argparse.SUPPRESS:
            continue
        yield action


def _param_dests(parser: argparse.ArgumentParser) -> set:
    return {action.dest for action in _param_actions(parser)}


def _param_defaults(parser: argparse.ArgumentParser) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for action in _param_actions(parser):
        params[action.dest] = action.default
    return params


def _exit_code(code: Any) -> int:
    if code is None:
        return 0
    if isinstance(code, bool):
        return 0 if code else 1
    if isinstance(code, int):
        return code
    raise TypeError(
        f"run() 应返回 int、bool 或 None，实际为 {type(code).__name__}"
    )
