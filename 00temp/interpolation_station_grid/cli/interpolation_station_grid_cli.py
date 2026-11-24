# -*- coding: utf-8 -*-
"""网格站点融合。``module`` 选择 idw、idw_delta、gaussian、kriging、cressman。

``python -m cli module=idw sta=sta.csv grid=grid.nc``
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


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


def _read_grid_data(path: str, meb, grid_type: str):
    if grid_type == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _read_sta_data(path: str, meb, sta_type: str):
    if sta_type == "csv":
        return meb.read_stadata_from_csv(path)
    return meb.read_stadata_from_micaps3(path)


def _write_grid_data(grd, path: str, meb, grid_type: str) -> None:
    out = Path(path)
    if out.parent and str(out.parent) not in ("", "."):
        out.parent.mkdir(parents=True, exist_ok=True)
    if grid_type == "nc":
        meb.write_griddata_to_nc(grd, str(out), creat_dir=True)
    else:
        meb.write_griddata_to_micaps4(grd, str(out), creat_dir=True)


@merge_params(section="cli")
def process(
    module=None,
    sta=None,
    grid=None,
    background=None,
    reprocess=None,
    sta_type=None,
    grid_type=None,
    background_type=None,
    output=None,
    output_type=None,
    effect_r=None,
    near_num=None,
    decrease=None,
    gaussian=None,
    half_r=None,
    r_list=None,
    kriging_model=None,
    kriging_sill=None,
    kriging_range=None,
    kriging_nugget=None,
    config=None,
) -> Any:
    """读站/格点 → 按 ``module`` 调用插件 → 可选写出。

    - ``grid`` / ``background`` 至少其一（由 ``resolve_args`` 校验）。
    - 有 ``grid``：读场后只取**网格信息**（``grid_info``）传给插件；场值不参与插值。
    - 无 ``grid``：``grid_info=None``，由插件从 ``background`` 取水平网格。
    - ``background``：按需读入场值，交给插件作远点/初场或偏差底场。
    - ``reprocess`` / ``gaussian``：透传 ``InterpSg``（仅 idw / idw_delta）。
      ``idw_delta`` 固定高斯×偏差；``idw`` 在 ``reprocess=true`` 且未显式指定时默认高斯。

    Returns
    -------
    插值结果格点场。
    """
    import meteva_base as meb

    if config:
        set_main_ini(config)
    try:
        # 显式参数 > ini > PRESET；并校验 grid/background、reprocess 约束
        module_name = resolve_module(module, config=config)
        cfg = resolve_args(
            module=module_name,
            sta=sta,
            grid=grid,
            background=background,
            reprocess=reprocess,
            effect_r=effect_r,
            near_num=near_num,
            decrease=decrease,
            gaussian=gaussian,
            half_r=half_r,
            kriging_model=kriging_model,
            kriging_sill=kriging_sill,
            kriging_range=kriging_range,
            kriging_nugget=kriging_nugget,
            r_list=r_list,
            output=output,
            sta_type=sta_type,
            grid_type=grid_type,
            background_type=background_type,
            output_type=output_type,
            config=config,
        )
        sta_data = _read_sta_data(cfg["sta"], meb, cfg["sta_type"])

        # grid 路径 → 仅提取 glon/glat 等网格信息；真正背景场另读
        grid_info = None
        if cfg["grid"]:
            grid_data = _read_grid_data(cfg["grid"], meb, cfg["grid_type"])
            if hasattr(meb, "get_grid_of_data"):
                grid_info = meb.get_grid_of_data(grid_data)
            else:
                grid_info = meb.basicdata.get_grid_of_data(grid_data)

        def _read_background():
            # 懒加载：各分支统一用此闭包，避免无背景时仍读盘
            if not cfg["background"]:
                return None
            return _read_grid_data(
                cfg["background"], meb, cfg["background_type"]
            )

        do_reprocess = bool(cfg["reprocess"])

        # 统一入口 InterpSg(method=...)；算法差异只在构造参数
        from interp_sg_plugin import InterpSg

        if module_name == "idw":
            plugin = InterpSg(
                method="idw",
                effectR=cfg["effect_r"],
                nearNum=cfg["near_num"],
                decrease=cfg["decrease"],
                gaussian=bool(cfg["gaussian"]),
                reprocess=do_reprocess,
            )
        elif module_name == "idw_delta":
            plugin = InterpSg(
                method="idw_delta",
                effectR=cfg["effect_r"],
                nearNum=cfg["near_num"],
                decrease=cfg["decrease"],
            )
        elif module_name == "gaussian":
            plugin = InterpSg(
                method="gaussian",
                halfR=cfg["half_r"],
                reprocess=do_reprocess,
            )
        elif module_name == "kriging":
            plugin = InterpSg(
                method="kriging",
                model=cfg["kriging_model"],
                sill=cfg["kriging_sill"],
                range_=cfg["kriging_range"],
                nugget=cfg["kriging_nugget"],
                nearNum=cfg["near_num"],
                reprocess=do_reprocess,
            )
        elif module_name == "cressman":
            plugin = InterpSg(
                method="cressman",
                r_list=cfg["r_list"],
                nearNum=cfg["near_num"],
                reprocess=do_reprocess,
            )
        else:
            raise ValueError("未知 module: %s" % module_name)

        result = plugin.process(
            sta_data, grid_info, background=_read_background()
        )

        if result is None:
            raise RuntimeError("插值返回 None")
        if cfg["output"]:
            _write_grid_data(result, cfg["output"], meb, cfg["output_type"])
            print("写出 →", cfg["output"])
        print(result)
        return result
    finally:
        if config:
            set_main_ini(None)
