# -*- coding: utf-8 -*-
"""坐标投影转换：等经纬度 ↔ 等距。

``backend``（默认 cartopy）：
- ``cartopy``：cartopy CRS + RegularGridInterpolator
- ``iris``：iris regridder

``mode``：
- ``lonlat-to-equal``：输入等经纬度 Cube，生成 Lambert 等距 Cube
- ``equal-to-lonlat``：输入等距 Cube，生成等经纬度 Cube
"""
from __future__ import annotations

import os
import sys
from typing import List

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
# ROOT 优先，确保包级 utils（合并 src/utils + 00temp/utils）被正确加载
for _p in (_SRC_DIR, _CLI_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.merge_params import merge_params

_MODES = ("lonlat-to-equal", "equal-to-lonlat")
_MODE_ALIASES = {
    "lonlat_to_equal": "lonlat-to-equal",
    "equal_to_lonlat": "equal-to-lonlat",
    "latlon-to-equal": "lonlat-to-equal",
    "equal-to-latlon": "equal-to-lonlat",
}
_BACKENDS = ("cartopy", "iris")
_BACKEND_ALIASES = {
    "cartopy": "cartopy",
    "iris": "iris",
    "ir": "iris",
}


def _abs_path(path):
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    text = os.path.expanduser(text)
    if os.path.isabs(text):
        return os.path.normpath(text)
    return os.path.normpath(os.path.join(_ROOT_DIR, text))


def _float_seq(value, n):
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        vals = [float(item.strip()) for item in value.split(",") if item.strip()]
    else:
        vals = [float(item) for item in value]
    if len(vals) != n:
        raise ValueError("%d 个数期望，得到 %d 个" % (n, len(vals)))
    return vals


def _normalize_mode(mode: str) -> str:
    resolved = (mode or "").strip().lower().replace("_", "-")
    resolved = _MODE_ALIASES.get(resolved, resolved)
    if resolved not in _MODES:
        raise ValueError(
            "mode 无效。可选 lonlat-to-equal、equal-to-lonlat"
        )
    return resolved


def _normalize_backend(backend: str) -> str:
    resolved = (backend or "cartopy").strip().lower()
    resolved = _BACKEND_ALIASES.get(resolved, resolved)
    if resolved not in _BACKENDS:
        raise ValueError("backend 无效。可选 cartopy、iris（默认 cartopy）")
    return resolved


def _process_lonlat_to_equal(cfg):
    import iris

    if cfg["backend"] == "iris":
        from cube_lonlat_to_equal import CubeLonlatToEqual as Plugin
    else:
        from cube_lonlat_to_equal_cartopy import CubeLonlatToEqualCartopy as Plugin

    cube_in = iris.load_cube(cfg["source_cube"])
    result = Plugin(
        projection_extent=tuple(cfg["projection_extent"]),
        secant_latitudes=tuple(cfg["secant_latitudes"]),
        grid_distance=cfg["grid_distance"],
        regrid_mode=cfg["regrid_mode"],
        extrapolation_mode=cfg["extrapolation_mode"],
    ).process(cube_in)
    print(result)
    return result


def _process_equal_to_lonlat(cfg):
    import iris

    if cfg["backend"] == "iris":
        from cube_equal_to_lonlat import CubeEqualToLonlat as Plugin
    else:
        from cube_equal_to_lonlat_cartopy import CubeEqualToLonlatCartopy as Plugin

    cube_in = iris.load_cube(cfg["source_cube"])
    result = Plugin(
        lonlat_extent=tuple(cfg["lonlat_extent"]),
        grid_spacing=cfg["grid_spacing"],
        regrid_mode=cfg["regrid_mode"],
        extrapolation_mode=cfg["extrapolation_mode"],
    ).process(cube_in)
    print(result)
    return result


@merge_params(sections=["cli", "lonlat_to_equal", "equal_to_lonlat"])
def process(
    mode: str = None,
    backend: str = None,
    source_cube: str = None,
    projection_extent: List[float] = None,
    secant_latitudes: List[float] = None,
    grid_distance: float = None,
    lonlat_extent: List[float] = None,
    grid_spacing: float = None,
    regrid_mode: str = None,
    extrapolation_mode: str = None,
    config=None,
):
    """按 ``mode`` / ``backend`` 做等经纬度与等距互转。

    ``backend`` 默认 cartopy；``backend=iris`` 走 iris regridder。
    """
    _ = config
    resolved = _normalize_mode(mode if mode is not None else "lonlat-to-equal")
    engine = _normalize_backend(backend if backend is not None else "cartopy")
    path = _abs_path(source_cube)
    if not path:
        raise ValueError("缺少参数: source_cube（调用参数与配置文件均未提供）")

    regrid = (regrid_mode if regrid_mode is not None else "bilinear").strip().lower()
    if regrid not in ("bilinear", "nearest"):
        raise ValueError("regrid_mode 只支持 bilinear 或 nearest")
    extrap = (extrapolation_mode if extrapolation_mode is not None else "nanmask").strip()
    distance = 1000.0 if grid_distance is None else float(grid_distance)
    spacing = 0.1 if grid_spacing is None else float(grid_spacing)

    if resolved == "lonlat-to-equal":
        extent = projection_extent if projection_extent is not None else [83.0, 138.0, 12.0, 53.0]
        secant = secant_latitudes if secant_latitudes is not None else [25.0, 47.0]
        if isinstance(extent, str):
            extent = _float_seq(extent, 4)
        if isinstance(secant, str):
            secant = _float_seq(secant, 2)
        if len(extent) != 4:
            raise ValueError("projection_extent 须为 lonmin,lonmax,latmin,latmax 四个数")
        if len(secant) != 2:
            raise ValueError("secant_latitudes 须为两个纬度")
        return _process_lonlat_to_equal(
            {
                "backend": engine,
                "source_cube": path,
                "projection_extent": extent,
                "secant_latitudes": secant,
                "grid_distance": distance,
                "regrid_mode": regrid,
                "extrapolation_mode": extrap,
            }
        )

    extent = lonlat_extent if lonlat_extent is not None else (
        projection_extent if projection_extent is not None else [83.0, 138.0, 12.0, 53.0]
    )
    if isinstance(extent, str):
        extent = _float_seq(extent, 4)
    if len(extent) != 4:
        raise ValueError("lonlat_extent 须为 lonmin,lonmax,latmin,latmax 四个数")
    return _process_equal_to_lonlat(
        {
            "backend": engine,
            "source_cube": path,
            "lonlat_extent": extent,
            "grid_spacing": spacing,
            "regrid_mode": regrid,
            "extrapolation_mode": extrap,
        }
    )
