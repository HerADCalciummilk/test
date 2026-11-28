# -*- coding: utf-8 -*-
"""格点→站点插值 CLI：``method`` 选择 linear、nearest、cubic。

命令行（在 ``00temp`` 目录执行）::

    python -m interpolation_grid_station method=linear grid=a.nc sta=sta.csv
    python -m utils.nimm_cli interpolation_grid_station method=nearest grid=a.nc sta=sta.csv used_coords=xy

或在本包目录执行::

    python -m cli method=linear grid=a.nc sta=sta.csv
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_paths() -> None:
    root = _PKG_ROOT
    parent = root.parent
    # 包根必须先于 src，否则 import utils 会命中 src/utils
    for path in (str(parent), str(root / "src"), str(root)):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


_bootstrap_paths()

from utils.merge_params import merge_params


def _normalize_method(method: Optional[str]) -> str:
    from interp_gs_plugin import InterpGs

    return InterpGs._normalize_method(method)


def _abs(path: Optional[str]) -> Optional[str]:
    """相对路径按包根解析（与 conf.ini 约定一致）。"""
    if path is None or not str(path).strip():
        return None
    p = Path(str(path).strip()).expanduser()
    return str(p if p.is_absolute() else (_PKG_ROOT / p).resolve())


def _resolve_grid_type(path: str, explicit: Optional[str] = None) -> str:
    if explicit is not None and str(explicit).strip():
        name = str(explicit).strip().lower()
        if name not in ("nc", "m4"):
            raise ValueError(f"格点格式须为 nc 或 m4，收到: {explicit!r}")
        return name
    return "nc" if str(path).lower().endswith(".nc") else "m4"


def _resolve_sta_type(path: str, explicit: Optional[str] = None) -> str:
    if explicit is not None and str(explicit).strip():
        name = str(explicit).strip().lower()
        if name not in ("csv", "m3"):
            raise ValueError(f"站点格式须为 csv 或 m3，收到: {explicit!r}")
        return name
    return "csv" if str(path).lower().endswith(".csv") else "m3"


def _read_grid_data(path: str, meb, grid_type: str):
    if grid_type == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _read_sta_data(path: str, meb, sta_type: str):
    if sta_type == "csv":
        return meb.read_stadata_from_csv(path)
    return meb.read_stadata_from_micaps3(path)


@merge_params()
def process(
    method: str = "linear",
    grid: Optional[str] = None,
    sta: Optional[str] = None,
    grid_type: Optional[str] = None,
    sta_type: Optional[str] = None,
    output: Optional[str] = None,
    output_type: Optional[str] = None,
    used_coords: str = "xy",
    config: Optional[str] = None,
) -> Any:
    """合参后校验 → 按 ``method`` 调用插值插件 → 可选写出站点。"""
    _ = config  # 仅由 @merge_params 消费，用于切换输入配置 ini

    method_name = _normalize_method(method)

    grid_path = _abs(grid)
    if not grid_path:
        raise ValueError(
            "grid 未指定。请传 grid=... 或在 resource/conf.ini 的 [input] 中填写 grid"
        )
    sta_path = _abs(sta)
    if not sta_path:
        raise ValueError(
            "sta 未指定。请传 sta=... 或在 resource/conf.ini 的 [input] 中填写 sta"
        )
    out_path = _abs(output)

    from interp_gs_plugin import InterpGs

    try:
        plugin = InterpGs(method=method_name, used_coords=used_coords)
    except ValueError:
        raise

    g_type = _resolve_grid_type(grid_path, grid_type)
    s_type = _resolve_sta_type(sta_path, sta_type)

    if not Path(grid_path).is_file():
        raise FileNotFoundError(f"源格点文件不存在: {grid_path}")
    if not Path(sta_path).is_file():
        raise FileNotFoundError(f"目标站点文件不存在: {sta_path}")

    import meteva_base as meb

    grd_in = _read_grid_data(grid_path, meb, g_type)
    sta_in = _read_sta_data(sta_path, meb, s_type)
    result = plugin.process(grd_in, sta_in)

    if result is None:
        raise RuntimeError(
            "插值返回 None：目标站点均在源网格外，或 dtime 范围无交集"
        )
    if out_path:
        out = Path(out_path)
        if out.parent and str(out.parent) not in ("", "."):
            out.parent.mkdir(parents=True, exist_ok=True)
        o_type = _resolve_sta_type(out_path, output_type)
        if o_type == "csv":
            meb.write_stadata_to_csv(result, str(out), creat_dir=True)
        else:
            meb.write_stadata_to_micaps3(result, str(out), creat_dir=True)
        print("写出 →", out)
    print(result)
    return result
