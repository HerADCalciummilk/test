# -*- coding: utf-8 -*-
"""格点→站点插值。``module`` 选择 linear、nearest、cubic。

``python -m cli module=linear grid=a.nc sta=sta.csv``
"""
from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    parent = root.parent
    for path in (str(parent), str(root / "src"), str(root)):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


_bootstrap_paths()

from utils.merge_params import merge_params
from utils.util_env import resolve_args, resolve_module, set_main_ini


@merge_params(section="cli")
def process(
    module: str = None,
    grid: str = None,
    sta: str = None,
    grid_type: str = None,
    sta_type: str = None,
    output: str = None,
    output_type: str = None,
    used_coords: str = None,
    config=None,
):
    """补齐参数后按 module 调用已有插件。"""
    import meteva_base as meb

    if config:
        set_main_ini(config)
    try:
        module_name = resolve_module(module, config=config)
        cfg = resolve_args(
            module=module_name,
            grid=grid,
            sta=sta,
            output=output,
            used_coords=used_coords,
            grid_type=grid_type,
            sta_type=sta_type,
            output_type=output_type,
            config=config,
        )
        if cfg["grid_type"] == "nc":
            grd_in = meb.read_griddata_from_nc(cfg["grid"])
        else:
            grd_in = meb.read_griddata_from_micaps4(cfg["grid"])
        if cfg["sta_type"] == "csv":
            sta_in = meb.read_stadata_from_csv(cfg["sta"])
        else:
            sta_in = meb.read_stadata_from_micaps3(cfg["sta"])

        if module_name == "linear":
            from interp_gs_linear_plugin import InterpGsLinear

            result = InterpGsLinear(used_coords=cfg["used_coords"]).process(grd_in, sta_in)
        elif module_name == "nearest":
            from interp_gs_nearest_plugin import InterpGsNearest

            result = InterpGsNearest().process(grd_in, sta_in)
        elif module_name == "cubic":
            from interp_gs_cubic_plugin import InterpGsCubic

            result = InterpGsCubic().process(grd_in, sta_in)
        else:
            raise ValueError("未知 module: %s" % module_name)

        if result is None:
            raise RuntimeError("插值返回 None：目标站点均在源网格外，或 dtime 范围无交集")
        if cfg["output"]:
            if cfg["output_type"] == "csv":
                meb.write_stadata_to_csv(result, cfg["output"], creat_dir=True)
            else:
                meb.write_stadata_to_micaps3(result, cfg["output"], creat_dir=True)
            print("写出 →", cfg["output"])
        print(result)
        return result
    finally:
        if config:
            set_main_ini(None)
