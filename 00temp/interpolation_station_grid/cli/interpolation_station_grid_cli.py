# -*- coding: utf-8 -*-
"""网格站点融合 CLI。

``process`` 由 ``@merge_params`` 合参，优先级：显式（命令行 key=value / Python 关键字）
> 输入配置 ini > ``resource/conf.ini`` 非空项 > 签名预设。函数体只做校验与调用插件，
不再读取 ini。

``method`` 选择 idw、gaussian、kriging、cressman。
``reprocess`` 与 ``idw_gaussian`` 相互独立。

示例（在 00temp 目录执行）::

    python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv grid=resource/target_grid.nc
    python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv background=resource/bg_fcst_idw.nc reprocess=true
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

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

_METHODS = ("idw", "gaussian", "kriging", "cressman")
_KRIGING_MODELS = ("spherical", "exponential", "gaussian")


@merge_params()
def process(
    method: str = "idw",
    reprocess: bool = False,
    outer_value: Optional[float] = None,
    sta: str = None,
    grid: str = None,
    background: str = None,
    sta_type: str = None,
    grid_type: str = None,
    background_type: str = None,
    output: str = None,
    output_type: str = None,
    idw_effect_r: float = 1000,
    idw_near_num: int = 8,
    idw_decrease: int = 2,
    idw_gaussian: bool = False,
    gaussian_half_r: float = 20,
    kriging_model: str = "spherical",
    kriging_near_num: int = 20,
    kriging_sill: float = None,
    kriging_range: float = None,
    kriging_nugget: float = 0.0,
    cressman_r_list: Optional[List[float]] = None,
    cressman_near_num: int = 100,
    cressman_rain_limit: Optional[float] = None,
    cressman_num_limit: float = 1.0,
    cressman_smooth: float = 0.001,
    cressman_power_param: float = 2.0,
    cressman_r_km_scale: float = 1.35,
    cressman_innov_gain: float = 1.0,
    cressman_residual_passes: int = 0,
    cressman_residual_degree_polish: bool = True,
    cressman_residual_polish_rounds: int = 1,
    cressman_degree_blend: float = 0.85,
    cressman_station_anchor_radius: float = 0.35,
    cressman_station_anchor_strength: float = 0.0,
    config=None,
):
    """站点 → 格点插值。参数已由装饰器合参，这里只校验并调用 ``InterpSg``。

    - ``grid`` 与 ``background`` 至少其一；``grid`` 只取网格信息，场值不参与插值。
    - ``reprocess=true`` 时必须提供 ``background``。
    - ``output`` 给出则写格点 nc/m4，否则只打印结果。
    - ``cressman_*`` 里除 ``cressman_r_list`` / ``cressman_near_num`` 外，均只在
      ``method=cressman`` 且 ``reprocess=true`` 时生效；其余情况被忽略。
    """
    import meteva_base as meb
    from interp_sg_plugin import InterpSg

    name = _normalize_method(method)
    do_reprocess = _as_bool(reprocess)

    sta_path = _abs(sta)
    grid_path = _abs(grid)
    bg_path = _abs(background)
    out_path = _abs(output)

    if not sta_path:
        raise ValueError("缺少 sta（站点文件）。请传 sta=...，或在 resource/conf.ini [input] 中填写")
    if not grid_path and not bg_path:
        raise ValueError("须提供 grid 或 background。请传 grid=... / background=...")
    if do_reprocess and not bg_path:
        raise ValueError("reprocess=true 时必须提供 background。请传 background=...")
    for label, path in (("sta", sta_path), ("grid", grid_path), ("background", bg_path)):
        if path and not Path(path).is_file():
            raise FileNotFoundError(f"{label} 文件不存在: {path}（相对路径按包根解析）")

    _check_numbers(
        idw_effect_r=idw_effect_r,
        idw_near_num=idw_near_num,
        idw_decrease=idw_decrease,
        gaussian_half_r=gaussian_half_r,
        kriging_near_num=kriging_near_num,
        kriging_nugget=kriging_nugget,
        kriging_sill=kriging_sill,
        kriging_range=kriging_range,
        cressman_near_num=cressman_near_num,
        cressman_rain_limit=cressman_rain_limit,
        cressman_num_limit=cressman_num_limit,
        cressman_smooth=cressman_smooth,
        cressman_power_param=cressman_power_param,
        cressman_r_km_scale=cressman_r_km_scale,
        cressman_innov_gain=cressman_innov_gain,
        cressman_residual_passes=cressman_residual_passes,
        cressman_residual_polish_rounds=cressman_residual_polish_rounds,
        cressman_degree_blend=cressman_degree_blend,
        cressman_station_anchor_radius=cressman_station_anchor_radius,
        cressman_station_anchor_strength=cressman_station_anchor_strength,
    )
    if kriging_model not in _KRIGING_MODELS:
        raise ValueError("kriging_model 仅支持 spherical / exponential / gaussian")

    sta_t = _io_type(sta_path, sta_type, default="m3", suffix_map={".csv": "csv"})
    grid_t = _io_type(grid_path, grid_type, default="m4", suffix_map={".nc": "nc"}) if grid_path else None
    bg_t = _io_type(bg_path, background_type, default="m4", suffix_map={".nc": "nc"}) if bg_path else None
    out_t = _io_type(out_path, output_type, default="m4", suffix_map={".nc": "nc"}) if out_path else None

    sta_data = _read_sta(sta_path, meb, sta_t)
    grid_info = None
    if grid_path:
        grid_data = _read_grid(grid_path, meb, grid_t)
        grid_info = meb.get_grid_of_data(grid_data)
    bg_data = _read_grid(bg_path, meb, bg_t) if bg_path else None

    outer_v = None if outer_value is None else float(outer_value)
    if name == "idw":
        plugin = InterpSg(
            method="idw",
            effectR=idw_effect_r,
            nearNum=idw_near_num,
            decrease=idw_decrease,
            gaussian=_as_bool(idw_gaussian),
            outer_value=outer_v,
            reprocess=do_reprocess,
        )
    elif name == "gaussian":
        plugin = InterpSg(
            method="gaussian",
            halfR=gaussian_half_r,
            outer_value=outer_v,
            reprocess=do_reprocess,
        )
    elif name == "kriging":
        plugin = InterpSg(
            method="kriging",
            model=kriging_model,
            sill=kriging_sill,
            range_=kriging_range,
            nugget=kriging_nugget,
            nearNum=kriging_near_num,
            outer_value=outer_v,
            reprocess=do_reprocess,
        )
    else:  # cressman
        plugin = InterpSg(
            method="cressman",
            r_list=_as_float_list(cressman_r_list) if cressman_r_list is not None else None,
            nearNum=cressman_near_num,
            outer_value=outer_v,
            reprocess=do_reprocess,
            rain_limit=cressman_rain_limit,
            num_limit=cressman_num_limit,
            smooth=cressman_smooth,
            power_param=cressman_power_param,
            r_km_scale=cressman_r_km_scale,
            innov_gain=cressman_innov_gain,
            residual_passes=cressman_residual_passes,
            residual_degree_polish=_as_bool(cressman_residual_degree_polish),
            residual_polish_rounds=cressman_residual_polish_rounds,
            degree_blend=cressman_degree_blend,
            station_anchor_radius=cressman_station_anchor_radius,
            station_anchor_strength=cressman_station_anchor_strength,
        )

    result = plugin.process(sta_data, grid_info, background=bg_data)
    if result is None:
        raise RuntimeError("插值返回 None：目标超出源网格时请检查 background / outer_value")
    if out_path:
        _write_grid(result, out_path, meb, out_t)
        print("写出 →", out_path)
    print(result)
    return result


def _normalize_method(method) -> str:
    name = str(method or "").strip().lower()
    if name not in _METHODS:
        raise ValueError("method 未指定或无效，可选 idw、gaussian、kriging、cressman")
    return name


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _as_float_list(value) -> List[float]:
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return [float(p) for p in parts]
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    return [float(value)]


def _check_numbers(**kw) -> None:
    if kw["idw_effect_r"] <= 0:
        raise ValueError("idw_effect_r 必须大于 0")
    if kw["gaussian_half_r"] <= 0:
        raise ValueError("gaussian_half_r 必须大于 0")
    for key in ("idw_near_num", "kriging_near_num", "cressman_near_num"):
        if int(kw[key]) < 1:
            raise ValueError("%s 必须大于等于 1" % key)
    if int(kw["idw_decrease"]) < 0:
        raise ValueError("idw_decrease 不能为负")
    if float(kw["kriging_nugget"]) < 0:
        raise ValueError("kriging_nugget 不能为负")
    for key in ("kriging_range", "kriging_sill"):
        if kw[key] is not None and float(kw[key]) <= 0:
            raise ValueError("%s 必须大于 0" % key)
    # Cressman 度制路径（reprocess=true）高级参数；其它路径不使用，但仍先校验取值
    if not 0.0 <= float(kw["cressman_degree_blend"]) <= 1.0:
        raise ValueError("cressman_degree_blend 须在 [0, 1]")
    for key in ("cressman_power_param", "cressman_r_km_scale", "cressman_station_anchor_radius"):
        if float(kw[key]) <= 0:
            raise ValueError("%s 必须大于 0" % key)
    for key in (
        "cressman_num_limit",
        "cressman_smooth",
        "cressman_innov_gain",
        "cressman_residual_passes",
        "cressman_residual_polish_rounds",
        "cressman_station_anchor_strength",
    ):
        if float(kw[key]) < 0:
            raise ValueError("%s 不能为负" % key)


def _abs(path: Optional[str]) -> Optional[str]:
    """相对路径按包根解析（与 ini 约定一致）。"""
    if path is None or not str(path).strip():
        return None
    p = Path(str(path).strip()).expanduser()
    return str(p if p.is_absolute() else (_PKG_ROOT / p).resolve())


def _io_type(path: Optional[str], explicit: Optional[str], *, default: str, suffix_map: dict) -> str:
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip().lower()
    suffix = Path(path).suffix.lower() if path else ""
    return suffix_map.get(suffix, default)


def _read_sta(path: str, meb, sta_type: str):
    if sta_type == "csv":
        return meb.read_stadata_from_csv(path)
    return meb.read_stadata_from_micaps3(path)


def _read_grid(path: str, meb, grid_type: str):
    if grid_type == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _write_grid(grd, path: str, meb, grid_type: str) -> None:
    out = Path(path)
    if out.parent and str(out.parent) not in ("", "."):
        out.parent.mkdir(parents=True, exist_ok=True)
    if grid_type == "nc":
        meb.write_griddata_to_nc(grd, str(out), creat_dir=True)
    else:
        meb.write_griddata_to_micaps4(grd, str(out), creat_dir=True)
