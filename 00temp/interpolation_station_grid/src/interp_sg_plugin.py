# -*- coding: utf-8 -*-
"""站点→格点插值统一入口。

按 ``method`` 分派到 ``InterpSgIdw`` / ``InterpSgGaussian`` /
``InterpSgKriging`` / ``InterpSgCressman``。接口仍为
``process(sta, grid=None, background=None)``。

各算法插件可继续单独使用；本类仅作对外门面。构造参数已全部显式列出，
未用于当前 ``method`` 的项忽略。

``idw``：绝对值路径默认纯 IDW；``reprocess=True`` 时默认 IDW×高斯
（可用 ``gaussian=False`` 关闭）。``idw_delta``：固定 ``gaussian=True`` +
``reprocess=True``（历史 CLI 模块名）。
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from utils.base_plugin import PostProcessingPlugin

from interp_sg_cressman_plugin import InterpSgCressman
from interp_sg_gaussian_plugin import InterpSgGaussian
from interp_sg_idw_plugin import InterpSgIdw
from interp_sg_kriging import InterpSgKriging

_METHOD_ALIASES = {
    "total": "idw",
    "delta": "idw_delta",
    "idw-delta": "idw_delta",
}

_METHODS = ("idw", "idw_delta", "gaussian", "kriging", "cressman")


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


class InterpSg(PostProcessingPlugin):
    """站点→格点插值统一入口。

    Parameters
    ----------
    method :
        ``idw`` / ``idw_delta`` / ``gaussian`` / ``kriging`` / ``cressman``。
        ``total``→``idw``；``delta`` / ``idw-delta``→``idw_delta``。
    reprocess :
        是否走偏差/创新量路径。``idw_delta`` 固定 ``True``。
    outer_value :
        背景对齐越界填充，透传给子插件。
    effectR :
        IDW / ``idw_delta``：纯 IDW 硬截断半径；高斯权重时为高斯尺度（米量级）。
    nearNum :
        IDW / Kriging / Cressman 近邻站点数。``None`` 时用各子插件默认
        （IDW 8、Kriging 20、Cressman 100）。
    decrease :
        IDW / ``idw_delta``：距离衰减指数。
    gaussian :
        仅 ``method="idw"``：是否乘高斯核。``None`` 时：``reprocess=True`` 默认
        ``True``，否则 ``False``。``idw_delta`` 固定 ``True``。
    halfR :
        仅 ``method="gaussian"``：高斯半径（米），须 ``> 0``。
    model, sill, range_, nugget :
        仅 ``method="kriging"``：变异函数模型 / 基台 / 变程 / 块金。
    r_list :
        仅 ``method="cressman"``：影响半径列表；``None`` 时按路径选用子插件默认。
    rain_limit, num_limit, smooth, power_param, r_km_scale, innov_gain,
    residual_passes, residual_degree_polish, residual_polish_rounds,
    degree_blend, station_anchor_radius, station_anchor_strength :
        仅 ``method="cressman"`` 且 ``reprocess=True`` 时生效（透传子插件）。
    """

    METHODS = _METHODS

    def __init__(
        self,
        method: str = "idw",
        *,
        reprocess: Any = False,
        outer_value: Optional[float] = None,
        # IDW / idw_delta
        effectR: Optional[int] = 1000,
        nearNum: Optional[int] = None,
        decrease: Optional[int] = 2,
        gaussian: Optional[bool] = None,
        # Gaussian
        halfR: Optional[int] = 20,
        # Kriging
        model: str = "spherical",
        sill: Optional[float] = None,
        range_: Optional[float] = None,
        nugget: float = 0.0,
        # Cressman
        r_list: Optional[Sequence[float]] = None,
        rain_limit: Any = None,
        num_limit: float = 1.0,
        smooth: float = 0.001,
        power_param: float = 2.0,
        r_km_scale: float = 1.35,
        innov_gain: float = 1.0,
        residual_passes: int = 0,
        residual_degree_polish: bool = True,
        residual_polish_rounds: int = 1,
        degree_blend: float = 0.85,
        station_anchor_radius: float = 0.35,
        station_anchor_strength: float = 0.0,
    ):
        name = self._normalize_method(method)
        do_reprocess = _as_bool(reprocess, False)

        if name == "idw":
            # reprocess=True 默认 IDW×高斯；显式 gaussian=False 可关
            use_gauss = (
                _as_bool(gaussian, False)
                if gaussian is not None
                else do_reprocess
            )
            kw: dict[str, Any] = {
                "effectR": effectR,
                "decrease": decrease,
                "gaussian": use_gauss,
                "outer_value": outer_value,
                "reprocess": do_reprocess,
            }
            if nearNum is not None:
                kw["nearNum"] = nearNum
            self._impl = InterpSgIdw(**kw)
        elif name == "idw_delta":
            # 历史模块：偏差订正 + IDW×高斯
            kw = {
                "effectR": effectR,
                "decrease": decrease,
                "gaussian": True,
                "outer_value": outer_value,
                "reprocess": True,
            }
            if nearNum is not None:
                kw["nearNum"] = nearNum
            self._impl = InterpSgIdw(**kw)
        elif name == "gaussian":
            self._impl = InterpSgGaussian(
                halfR=halfR,
                outer_value=outer_value,
                reprocess=do_reprocess,
            )
        elif name == "kriging":
            kw = {
                "model": model,
                "sill": sill,
                "range_": range_,
                "nugget": nugget,
                "outer_value": outer_value,
                "reprocess": do_reprocess,
            }
            if nearNum is not None:
                kw["nearNum"] = nearNum
            self._impl = InterpSgKriging(**kw)
        elif name == "cressman":
            kw = {
                "r_list": r_list,
                "outer_value": outer_value,
                "reprocess": do_reprocess,
                "rain_limit": rain_limit,
                "num_limit": num_limit,
                "smooth": smooth,
                "power_param": power_param,
                "r_km_scale": r_km_scale,
                "innov_gain": innov_gain,
                "residual_passes": residual_passes,
                "residual_degree_polish": residual_degree_polish,
                "residual_polish_rounds": residual_polish_rounds,
                "degree_blend": degree_blend,
                "station_anchor_radius": station_anchor_radius,
                "station_anchor_strength": station_anchor_strength,
            }
            if nearNum is not None:
                kw["nearNum"] = nearNum
            self._impl = InterpSgCressman(**kw)
        else:  # pragma: no cover
            raise ValueError(f"未知 method: {name}")

        self.method = name
        self.reprocess = self._impl.reprocess
        self.outer_value = outer_value

    @classmethod
    def _normalize_method(cls, method: Any) -> str:
        if method is None or (isinstance(method, str) and not method.strip()):
            raise ValueError(
                "method 未指定。可选: " + "、".join(cls.METHODS)
            )
        name = _METHOD_ALIASES.get(str(method).strip(), str(method).strip())
        if name not in _METHODS:
            raise ValueError(
                f"未知 method: {method!r}。可选: " + "、".join(cls.METHODS)
            )
        return name

    def process(self, sta, grid=None, background=None):
        """站点→格点插值（转调 ``method`` 对应子插件）。"""
        return self._impl.process(sta, grid=grid, background=background)
