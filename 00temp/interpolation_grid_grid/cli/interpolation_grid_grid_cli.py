# -*- coding: utf-8 -*-
"""格点→格点融合。``module`` 选择 linear、nearest、cubic、conservative。

``python -m cli module=linear grid=a.nc domain=20,50,70,140,0.1,0.1``
"""
from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    parent = root.parent
    # 包根必须先于 src，否则 import utils 会命中 src/utils
    for path in (str(parent), str(root / "src"), str(root)):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


_bootstrap_paths()

from utils.merge_params import merge_params
from utils.util_env import resolve_args, resolve_module, set_main_ini


def _read_grid_data(path: str, meb, grid_type: str):
    if grid_type == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _resolve_target_grid(cfg: dict, meb):
    if cfg["glon"] is not None and cfg["glat"] is not None:
        return meb.basicdata.grid(cfg["glon"], cfg["glat"])
    if cfg["domain"] is not None:
        sou, nor, wst, est, dlon, dlat = cfg["domain"]
        return meb.basicdata.grid([wst, est, dlon], [sou, nor, dlat])
    tmpl = _read_grid_data(cfg["grid_template"], meb, cfg["grid_template_type"])
    g0 = meb.get_grid_of_data(tmpl)
    return meb.basicdata.grid(g0.glon, g0.glat)


@merge_params(section="cli")
def process(
    module: str = None,
    grid: str = None,
    grid_template: str = None,
    grid_type: str = None,
    grid_template_type: str = None,
    output: str = None,
    outer_value: float = None,
    mdtol: float = None,
    glon: str = None,
    glat: str = None,
    domain: str = None,
    config=None,
):
    """补齐参数后按 module 调用已有插件。"""
    import meteva_base as meb

    if config:
        set_main_ini(config)
    try:
        # 方法节里的 outer_value 等仍由 resolve_args 读取，避免各节同名键互相覆盖
        module_name = resolve_module(module, config=config)
        cfg = resolve_args(
            module=module_name,
            grid=grid,
            grid_template=grid_template,
            output=output,
            outer_value=outer_value,
            mdtol=mdtol,
            glon=glon,
            glat=glat,
            domain=domain,
            grid_type=grid_type,
            grid_template_type=grid_template_type,
            config=config,
        )
        grd_in = _read_grid_data(cfg["grid"], meb, cfg["grid_type"])
        target = _resolve_target_grid(cfg, meb)

        if module_name == "linear":
            from interp_gg_linear_plugin import InterpGgLinear

            result = InterpGgLinear(outer_value=cfg["outer_value"]).process(grd_in, target)
        elif module_name == "nearest":
            from interp_gg_nearest_plugin import InterpGgNearest

            result = InterpGgNearest(outer_value=cfg["outer_value"]).process(grd_in, target)
        elif module_name == "cubic":
            from interp_gg_cubic_plugin import InterpGgCubic

            result = InterpGgCubic(outer_value=cfg["outer_value"]).process(grd_in, target)
        elif module_name == "conservative":
            from interp_gg_conservative_plugin import InterpGgConservative

            result = InterpGgConservative(
                outer_value=cfg["outer_value"],
                mdtol=cfg["mdtol"],
            ).process(grd_in, target)
        else:
            raise ValueError("未知 module: %s" % module_name)

        if result is None:
            raise RuntimeError("插值返回 None：目标超出源网格时请设置 outer_value")
        if cfg["output"]:
            out = Path(cfg["output"])
            if out.parent and str(out.parent) not in ("", "."):
                out.parent.mkdir(parents=True, exist_ok=True)
            meb.write_griddata_to_micaps4(result, str(out), creat_dir=True)
            print("写出 →", out)
        print(result)
        return result
    finally:
        if config:
            set_main_ini(None)
