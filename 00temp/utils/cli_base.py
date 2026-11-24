# -*- coding: utf-8 -*-
"""子模块命令行基类。

命令行和 Python 调用进同一个 ``process``。基类在调用子类 ``process`` 之前：

1. 解析 ``--config``（或 ``call(config=...)``）：省略则定位包内 ``resource/conf.ini``
2. 读取该 ini 中的非空项
3. 与外部参数合并——外部非 ``None`` 优先；仍为 ``None`` 的项用 ini 填补
   （类型按 ``add_arguments`` 中的声明转换）

合并后的参数再交给子类 ``process``，由其转调本模块主程序入口。

同一套整合也以装饰器形式提供，可直接挂在入口函数上::

from utils.cli_base import merge_params

    @merge_params()  # 默认子模块 resource/conf.ini
    def process(plugin=None, config=None, pro_count: int = 8):
        ...

优先级：外部参数 > 输入 config 文件 > 默认 resource/conf.ini > 方法签名预设。

子类只实现两处：

- ``add_arguments``：声明业务参数（省略项默认 ``None``）
- ``process``：把合并后的参数传给模块入口（``process`` / 插件等）

``--config`` 由基类自动登记；子类若已声明同名参数则不再重复添加。

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

from .merge_params import collect_merged_params, merge_params

# 对外暴露：入口函数可用 ``@merge_params`` 在调用前整合 ini 与外部参数
__all__ = ["CliBase", "merge_params", "collect_merged_params"]

_CONFIG_HELP = (
    "运行配置 ini。"
    "相对路径按本包根目录解析。"
    "省略则使用 resource/conf.ini（若存在）。"
)


class CliBase(ABC):
    """命令行与 Python 共用的入口基类。"""

    prog: str = "python -m cli"
    description: str = ""
    epilog: str = ""
    formatter_class = argparse.RawDescriptionHelpFormatter
    #: 可选。用于定位 ``resource/conf.ini`` 的锚点文件路径；
    #: 默认取子类所在模块的 ``__file__``（``cli/*.py`` → 包根为其上一级）。
    conf_anchor: Optional[str] = None
    #: 单节名；扁平无节文件忽略。目标节不存在时 ``merge_params`` 会合并全部节。
    conf_section: str = "process"
    #: 若设置，按顺序合并这些节（后覆盖先），忽略 ``conf_section``。
    conf_sections: Optional[Sequence[str]] = None


    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """子类在此声明参数。省略项的默认值用 ``None``，表示交给 ini / 预设。"""

    @abstractmethod
    def process(self, **params: Any) -> Optional[int]:
        """入口主函数。接收基类合并后的参数，转调模块主程序。

        返回 ``None`` 或 ``0`` 表示成功，其他整数作为退出码。
        """

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=self.prog,
            description=self.description,
            epilog=self.epilog or None,
            formatter_class=self.formatter_class,
        )
        self.add_arguments(parser)
        if "config" not in _param_dests(parser):
            parser.add_argument(
                "--config",
                dest="config",
                default=None,
                metavar="PATH",
                help=_CONFIG_HELP,
            )
        return parser

    def resolve_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """合并外部参数与 ini。

        优先级与 ``merge_params`` 一致：外部非 None > 输入 ``config`` 文件 >
        默认 ``resource/conf.ini`` > 保持 None（CLI 形参预设均为 None）。

        类型按 ``add_arguments`` 的 ``type`` / 布尔 action 转换。
        """
        anchor = self._anchor_file()
        if not anchor:
            return dict(params)

        parser = self.build_parser()
        casters: Dict[str, Any] = {}
        for action in _param_actions(parser):
            if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
                casters[action.dest] = "bool"
            elif action.type is not None:
                casters[action.dest] = action.type

        return collect_merged_params(
            params,
            anchor_file=anchor,
            section=self.conf_section,
            sections=self.conf_sections,
            casters=casters,
            param_names=list(params.keys()),
            presets={},
        )

    @staticmethod
    def require_params(params: Dict[str, Any], *names: str) -> None:
        """合并后仍缺必填项时抛出 ValueError（替代 argparse required=True）。"""
        missing = [name for name in names if params.get(name) is None]
        if missing:
            raise ValueError(
                "缺少参数: "
                + ", ".join(missing)
                + "（命令行与配置 ini 均未提供）"
            )

    def forward_call(self, cli_cls: type, **params: Any) -> int:
        """把已收集参数转给另一个 ``CliBase`` 子类（经其 ``call`` / 再次按该子类节合并）。"""
        app = cli_cls()
        dests = _param_dests(app.build_parser())
        kwargs = {key: value for key, value in params.items() if key in dests}
        return cli_cls.call(**kwargs)

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

    def _anchor_file(self) -> Optional[str]:
        if self.conf_anchor:
            return self.conf_anchor
        mod = sys.modules.get(self.__class__.__module__)
        path = getattr(mod, "__file__", None) if mod is not None else None
        return str(path) if path else None

    def _dispatch(self, params: Dict[str, Any]) -> int:
        try:
            resolved = self.resolve_params(params)
            code = self.process(**resolved)
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


def _cast_ini_for_action(raw: str, action: Optional[argparse.Action]) -> Any:
    """按 argparse action 把 ini 字符串转成参数值。"""
    if action is None:
        return raw
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")

    typ = action.type
    nargs = action.nargs
    needs_list = nargs in ("+", "*") or (isinstance(nargs, int) and nargs != 1)
    if needs_list:
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if typ is None:
            return parts
        return [typ(item) for item in parts]
    if typ is not None:
        return typ(raw)
    return raw


def _exit_code(code: Any) -> int:
    if code is None:
        return 0
    if isinstance(code, bool):
        return 0 if code else 1
    if isinstance(code, int):
        return code
    raise TypeError(
        f"process() 应返回 int、bool 或 None，实际为 {type(code).__name__}"
    )
