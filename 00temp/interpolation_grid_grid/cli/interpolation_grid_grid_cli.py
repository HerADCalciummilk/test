# -*- coding: utf-8 -*-
"""格点→格点融合 CLI：``method`` 选择 linear、nearest、cubic、conservative。

命令行（在 ``00temp`` 目录执行）::

    python -m interpolation_grid_grid method=linear grid=a.nc domain=20,50,70,140,0.1,0.1
    python -m utils.nimm_cli interpolation_grid_grid method=conservative grid=a.nc domain=20,50,70,140,0.25,0.25 mdtol=0.5 spherical=true

或在本包目录执行::

    python -m cli method=linear grid=a.nc domain=20,50,70,140,0.1,0.1
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

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

# 延迟导入：bootstrap 后再取统一入口的校验
def _normalize_method(method: Optional[str]) -> str:
    from interp_gg_plugin import InterpGg

    return InterpGg._normalize_method(method)


def _abs(path: Optional[str]) -> Optional[str]:
    """相对路径按包根解析（与 conf.ini 约定一致）。"""
    if path is None or not str(path).strip():
        return None
    p = Path(str(path).strip()).expanduser()
    return str(p if p.is_absolute() else (_PKG_ROOT / p).resolve())


def _resolve_io_type(path: str, explicit: Optional[str] = None) -> str:
    if explicit is not None and str(explicit).strip():
        name = str(explicit).strip().lower()
        if name not in ("nc", "m4"):
            raise ValueError(f"格点格式须为 nc 或 m4，收到: {explicit!r}")
        return name
    return "nc" if str(path).lower().endswith(".nc") else "m4"


def _as_float_list(value: Any, name: str, expected_len: int) -> Optional[List[float]]:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if not parts:
            return None
        parsed = [float(p) for p in parts]
    elif isinstance(value, (list, tuple)):
        if not value:
            return None
        parsed = [float(x) for x in value]
    else:
        raise ValueError(f"{name} 须为逗号分隔字符串或数值序列")
    if len(parsed) != expected_len:
        raise ValueError(f"{name} 须为 {expected_len} 个数")
    return parsed


def _read_grid_data(path: str, meb, grid_type: str):
    if grid_type == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _resolve_target_grid(
    glon: Optional[List[float]],
    glat: Optional[List[float]],
    domain: Optional[List[float]],
    grid_template: Optional[str],
    grid_template_type: Optional[str],
    meb,
):
    if glon is not None and glat is not None:
        return meb.basicdata.grid(glon, glat)
    if domain is not None:
        sou, nor, wst, est, dlon, dlat = domain
        return meb.basicdata.grid([wst, est, dlon], [sou, nor, dlat])
    tmpl = _read_grid_data(grid_template, meb, grid_template_type)
    g0 = meb.get_grid_of_data(tmpl)
    return meb.basicdata.grid(g0.glon, g0.glat)


@merge_params()
def process(
    method: str = "linear",
    grid: Optional[str] = None,
    grid_template: Optional[str] = None,
    grid_type: Optional[str] = None,
    grid_template_type: Optional[str] = None,
    output: Optional[str] = None,
    outer_value: float = 0.0,
    mdtol: float = 1.0,
    spherical: bool = True,
    glon: Optional[List[float]] = None,
    glat: Optional[List[float]] = None,
    domain: Optional[List[float]] = None,
    config: Optional[str] = None,
) -> Any:
    """合参后校验 → 按 ``method`` 调用插值插件 → 可选写出 Micaps4。"""
    _ = config  # 仅由 @merge_params 消费，用于切换输入配置 ini

    method_name = _normalize_method(method)

    grid_path = _abs(grid)
    if not grid_path:
        raise ValueError("grid 未指定。请传 grid=... 或在 resource/conf.ini 的 [input] 中填写 grid")
    tmpl_path = _abs(grid_template)
    out_path = _abs(output)

    glon_v = _as_float_list(glon, "glon", 3)
    glat_v = _as_float_list(glat, "glat", 3)
    domain_v = _as_float_list(domain, "domain", 6)

    if (glon_v is None) != (glat_v is None):
        raise ValueError("glon 与 glat 须同时给出")
    has_glon_glat = glon_v is not None and glat_v is not None
    if not (has_glon_glat or domain_v is not None or tmpl_path is not None):
        raise ValueError(
            "无法确定目标网格：请提供 glon+glat，或 domain，或 grid_template（或 conf.ini 对应项）"
        )

    outer_v = None if outer_value is None else float(outer_value)

    from interp_gg_plugin import InterpGg

    try:
        plugin = InterpGg(
            method=method_name,
            outer_value=outer_v,
            mdtol=mdtol,
            spherical=spherical,
        )
    except ValueError as exc:
        # 统一入口的 mdtol 范围错误带上原值，便于 CLI 报错
        if "mdtol" in str(exc):
            raise ValueError(f"mdtol 须在 [0, 1]，收到: {mdtol!r}") from exc
        raise

    g_type = _resolve_io_type(grid_path, grid_type)
    t_type = _resolve_io_type(tmpl_path, grid_template_type) if tmpl_path else None

    if not Path(grid_path).is_file():
        raise FileNotFoundError(f"源格点文件不存在: {grid_path}")
    if tmpl_path and not Path(tmpl_path).is_file():
        raise FileNotFoundError(f"目标网格模板文件不存在: {tmpl_path}")

    import meteva_base as meb

    grd_in = _read_grid_data(grid_path, meb, g_type)
    target = _resolve_target_grid(glon_v, glat_v, domain_v, tmpl_path, t_type, meb)
    result = plugin.process(grd_in, target)

    if result is None:
        raise RuntimeError("插值返回 None：目标超出源网格时请设置 outer_value")
    if out_path:
        out = Path(out_path)
        if out.parent and str(out.parent) not in ("", "."):
            out.parent.mkdir(parents=True, exist_ok=True)
        meb.write_griddata_to_micaps4(result, str(out), creat_dir=True)
        print("写出 →", out)
    print(result)
    return result
