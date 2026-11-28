# -*- coding: utf-8 -*-
"""格点→站点插值统一入口。

按 ``method`` 分派到 ``InterpGsLinear`` / ``InterpGsNearest`` /
``InterpGsCubic``。接口仍为 ``process(grd, sta)``。

各算法插件可继续单独使用；本类仅作对外门面。构造参数已全部显式列出，
未用于当前 ``method`` 的项忽略。
"""
from __future__ import annotations

from typing import Any

from utils.base_plugin import PostProcessingPlugin

from interp_gs_cubic_plugin import InterpGsCubic
from interp_gs_linear_plugin import InterpGsLinear
from interp_gs_nearest_plugin import InterpGsNearest

_LINEAR_COORDS = ("xy", "xyz", "xydt")


class InterpGs(PostProcessingPlugin):
    """格点→站点插值统一入口。

    Parameters
    ----------
    method :
        ``linear`` / ``nearest`` / ``cubic``。
    used_coords :
        仅 ``method="linear"``：``xy`` / ``xyz`` / ``xydt``，默认 ``xy``。
        其它 method 忽略该参数。
    """

    METHODS = ("linear", "nearest", "cubic")

    def __init__(self, method: str = "linear", *, used_coords: str = "xy"):
        name = self._normalize_method(method)
        coords = self._normalize_used_coords(used_coords)

        if name == "linear":
            self._impl = InterpGsLinear(used_coords=coords)
        elif name == "nearest":
            self._impl = InterpGsNearest()
        elif name == "cubic":
            self._impl = InterpGsCubic()
        else:  # pragma: no cover
            raise ValueError(f"未知 method: {name}")

        self.method = name
        # 保留构造入参；仅 linear 实际使用 used_coords
        self.used_coords = coords

    @classmethod
    def _normalize_method(cls, method: Any) -> str:
        if method is None or (isinstance(method, str) and not method.strip()):
            raise ValueError("method 未指定。可选: " + "、".join(cls.METHODS))
        name = str(method).strip().lower()
        if name not in cls.METHODS:
            raise ValueError(
                f"未知 method: {method!r}。可选: " + "、".join(cls.METHODS)
            )
        return name

    @staticmethod
    def _normalize_used_coords(used_coords: Any) -> str:
        if used_coords is None or (
            isinstance(used_coords, str) and not used_coords.strip()
        ):
            return "xy"
        coords = str(used_coords).strip().lower()
        if coords not in _LINEAR_COORDS:
            raise ValueError(
                f'used_coords 仅支持 {_LINEAR_COORDS}，收到: {used_coords!r}'
            )
        return coords

    def process(self, grd, sta):
        """格点→站点插值（转调 ``method`` 对应子插件）。"""
        return self._impl.process(grd, sta)
