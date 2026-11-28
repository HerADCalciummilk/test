# -*- coding: utf-8 -*-
"""格点→格点插值统一入口。

按 ``method`` 分派到 ``InterpGgLinear`` / ``InterpGgNearest`` /
``InterpGgCubic`` / ``InterpGgConservative``。接口仍为 ``process(grd, grid)``。

各算法插件可继续单独使用；本类仅作对外门面。构造参数已全部显式列出，
未用于当前 ``method`` 的项忽略。

海陆感知重网格（``InterpGgLandSea``）有独立 ``regrid_mode`` 分派，不经本入口。
"""
from __future__ import annotations

from typing import Any, Optional

from utils.base_plugin import PostProcessingPlugin

from interp_gg_conservative_plugin import InterpGgConservative
from interp_gg_cubic_plugin import InterpGgCubic
from interp_gg_linear_plugin import InterpGgLinear
from interp_gg_nearest_plugin import InterpGgNearest


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off", ""):
        return False
    return bool(value)


class InterpGg(PostProcessingPlugin):
    """格点→格点插值统一入口。

    Parameters
    ----------
    method :
        ``linear`` / ``nearest`` / ``cubic`` / ``conservative``。
    outer_value :
        目标超出源网格（或覆盖不足）时的填充值，透传子插件。
    mdtol :
        仅 ``method="conservative"``：缺测/覆盖容差 ``[0, 1]``，默认 ``1``。
    spherical :
        仅 ``method="conservative"``：是否按球面面积因子，默认 ``True``。
    """

    METHODS = ("linear", "nearest", "cubic", "conservative")

    def __init__(
        self,
        method: str = "linear",
        *,
        outer_value: Optional[float] = None,
        mdtol: float = 1.0,
        spherical: Any = True,
    ):
        name = self._normalize_method(method)
        mdtol_v = float(mdtol)
        spherical_v = _as_bool(spherical, True)
        if name == "conservative" and not (0.0 <= mdtol_v <= 1.0):
            raise ValueError("mdtol 须在 [0, 1]")

        if name == "linear":
            self._impl = InterpGgLinear(outer_value=outer_value)
        elif name == "nearest":
            self._impl = InterpGgNearest(outer_value=outer_value)
        elif name == "cubic":
            self._impl = InterpGgCubic(outer_value=outer_value)
        elif name == "conservative":
            self._impl = InterpGgConservative(
                outer_value=outer_value,
                mdtol=mdtol_v,
                spherical=spherical_v,
            )
        else:  # pragma: no cover
            raise ValueError(f"未知 method: {name}")

        self.method = name
        self.outer_value = outer_value
        # 保留构造入参；仅 conservative 实际使用 mdtol / spherical
        self.mdtol = mdtol_v
        self.spherical = spherical_v

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

    def process(self, grd, grid):
        """格点→格点插值（转调 ``method`` 对应子插件）。"""
        return self._impl.process(grd, grid)
