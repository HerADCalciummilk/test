# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
站点 ``sta`` 必填；``grid`` / ``background`` 至少其一；
``reprocess=true`` / ``idw_delta`` 时须 ``background``。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

PRESET: Dict[str, Any] = {
    "module": "idw",
    "reprocess": False,
    "effect_r": 1000,
    "near_num": 8,
    "decrease": 2,
    "half_r": 20,
    "kriging_model": "spherical",
    "kriging_near_num": 20,
    "kriging_nugget": 0.0,
    "cressman_r_list": [60000.0, 40000.0, 20000.0],
    "cressman_near_num": 100,
}

# total 为旧入口别名，等价于 idw
_MODULE_ALIASES = {
    "total": "idw",
    "delta": "idw_delta",
    "idw-delta": "idw_delta",
}
_MODULES = ("idw", "idw_delta", "gaussian", "kriging", "cressman")
_KRIGING_MODELS = ("spherical", "exponential", "gaussian")


def clear_ini_cache() -> None:
    global _CACHE
    _CACHE = None


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按项目根目录解析。文件不存在时抛出 ``FileNotFoundError``。
    返回实际使用的绝对路径。
    """
    global _INI_PATH, _CACHE
    if path is None or not str(path).strip():
        _INI_PATH = _DEFAULT_INI
        chosen = _DEFAULT_INI
    else:
        raw = Path(str(path).strip()).expanduser()
        chosen = raw if raw.is_absolute() else (_PKG_ROOT / raw)
        chosen = chosen.resolve()
        if not chosen.is_file():
            raise FileNotFoundError(f"配置文件不存在: {chosen}")
        _INI_PATH = chosen
    _CACHE = None
    return str(chosen)


def _parser() -> configparser.ConfigParser:
    global _CACHE
    if _CACHE is None:
        parser = configparser.ConfigParser()
        if _INI_PATH.is_file():
            parser.read(_INI_PATH, encoding="utf-8")
        _CACHE = parser
    return _CACHE


def _raw(section: str, key: str) -> Optional[str]:
    parser = _parser()
    if not parser.has_section(section) or not parser.has_option(section, key):
        return None
    value = parser.get(section, key).strip()
    return value or None


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _expand(path: str) -> str:
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    return str((_PKG_ROOT / expanded).resolve())


def _opt_int(section: str, key: str, preset: int) -> int:
    raw = _raw(section, key)
    return preset if raw is None else int(raw)


def _pick_int(explicit: Optional[int], section: str, key: str, preset: int) -> int:
    if explicit is None:
        return _opt_int(section, key, preset)
    return int(explicit)


def _require(name: str, explicit: Optional[str], section: str, key: str) -> str:
    if not _missing(explicit):
        return str(explicit).strip()
    raw = _raw(section, key)
    if raw is None:
        raise ValueError(
            f"{name} 未指定。请传对应命令行参数，或在 resource/conf.ini 的 [{section}] 中填写 {key}"
        )
    return _expand(raw)


def _optional_path(explicit: Optional[str], section: str, key: str) -> Optional[str]:
    if not _missing(explicit):
        return str(explicit).strip()
    raw = _raw(section, key)
    if raw is None:
        return None
    return _expand(raw)


def _optional_str(explicit: Optional[str], section: str, key: str) -> Optional[str]:
    if not _missing(explicit):
        return str(explicit).strip()
    return _raw(section, key)


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


def _pick_bool(explicit: Any, section: str, key: str, preset: bool) -> bool:
    if explicit is not None and not (isinstance(explicit, str) and not explicit.strip()):
        return _as_bool(explicit, preset)
    raw = _raw(section, key)
    if raw is None:
        return bool(preset)
    return _as_bool(raw, preset)


def resolve_io_type(path: str, explicit: Optional[str] = None) -> str:
    """解析格点格式：显式 ``nc`` / ``m4`` 优先；否则按扩展名（``.nc``→nc，否则 m4）。"""
    if not _missing(explicit):
        name = str(explicit).strip().lower()
        if name not in ("nc", "m4"):
            raise ValueError(f"格点格式须为 nc 或 m4，收到: {explicit!r}")
        return name
    return "nc" if str(path).lower().endswith(".nc") else "m4"


def resolve_sta_type(path: str, explicit: Optional[str] = None) -> str:
    """解析站点格式：显式 ``csv`` / ``m3`` 优先；否则按扩展名（``.csv``→csv，否则 m3）。"""
    if not _missing(explicit):
        name = str(explicit).strip().lower()
        if name not in ("csv", "m3"):
            raise ValueError(f"站点格式须为 csv 或 m3，收到: {explicit!r}")
        return name
    return "csv" if str(path).lower().endswith(".csv") else "m3"


def resolve_module(module: Optional[str] = None, config: Optional[str] = None) -> str:
    """选择融合方式。显式参数优先，否则读 ``[cli] module``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。
    """
    if config:
        set_main_ini(config)
    try:
        if _missing(module):
            module = _raw("cli", "module") or str(PRESET["module"])
        name = _MODULE_ALIASES.get(str(module).strip(), str(module).strip())
        if name not in _MODULES:
            raise ValueError(
                "module 未指定或无效。请传 --module，可选 "
                "idw、idw_delta、gaussian、kriging、cressman"
            )
        return name
    finally:
        if config:
            set_main_ini(None)


def _opt_float(section: str, key: str, preset: float) -> float:
    raw = _raw(section, key)
    return preset if raw is None else float(raw)


def _pick_float(explicit: Optional[float], section: str, key: str, preset: float) -> float:
    if explicit is None:
        return _opt_float(section, key, preset)
    return float(explicit)


def _optional_float(explicit: Optional[float], section: str, key: str) -> Optional[float]:
    if explicit is not None:
        return float(explicit)
    raw = _raw(section, key)
    return None if raw is None else float(raw)


def _parse_r_list(value: Any) -> Optional[list]:
    """将 ``'60000,40000,20000'`` 或数值序列解析为 float 列表。"""
    if value is None:
        return None
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return [float(p) for p in parts] if parts else None
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    raise ValueError("r_list 须为逗号分隔字符串或数值序列")


def _pick_r_list(explicit: Any, section: str, key: str, preset: list) -> list:
    if explicit is not None:
        parsed = _parse_r_list(explicit)
        if parsed is None:
            raise ValueError("r_list 不能为空")
        return parsed
    raw = _raw(section, key)
    if raw is None:
        return list(preset)
    parsed = _parse_r_list(raw)
    if parsed is None:
        raise ValueError("r_list 不能为空")
    return parsed


def resolve_args(
    module: Optional[str] = None,
    sta: Optional[str] = None,
    grid: Optional[str] = None,
    background: Optional[str] = None,
    reprocess: Any = None,
    effect_r: Optional[int] = None,
    near_num: Optional[int] = None,
    decrease: Optional[int] = None,
    half_r: Optional[int] = None,
    kriging_model: Optional[str] = None,
    kriging_sill: Optional[float] = None,
    kriging_range: Optional[float] = None,
    kriging_nugget: Optional[float] = None,
    r_list: Any = None,
    output: Optional[str] = None,
    sta_type: Optional[str] = None,
    grid_type: Optional[str] = None,
    background_type: Optional[str] = None,
    output_type: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐 CLI/API 参数字典，供 ``process`` 直接使用。

    优先级：显式参数 > 当前 ini 非空项 > ``PRESET``。
    ``config`` 非空时临时切到该 ini，返回前恢复默认 ``resource/conf.ini``。

    返回键至少含 ``module`` / ``sta`` / ``grid`` / ``background`` / ``reprocess``
    及对应 ``*_type``；其余按 module 分支（如 ``effect_r``、``r_list``）。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            module=module,
            sta=sta,
            grid=grid,
            background=background,
            reprocess=reprocess,
            effect_r=effect_r,
            near_num=near_num,
            decrease=decrease,
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
        )
    finally:
        if config:
            set_main_ini(None)


def _attach_io_types(
    resolved: Dict[str, Any],
    *,
    sta_type: Optional[str],
    grid_type: Optional[str],
    background_type: Optional[str],
    output: Optional[str],
    output_type: Optional[str],
) -> None:
    """为已解析路径补齐读写格式与可选输出。"""
    resolved["output"] = _optional_path(output, "output", "path")
    explicit_sta = _optional_str(sta_type, "input", "sta_type")
    explicit_grid = _optional_str(grid_type, "input", "grid_type")
    explicit_bg = _optional_str(background_type, "input", "background_type")
    resolved["sta_type"] = resolve_sta_type(resolved["sta"], explicit_sta)
    if resolved["grid"]:
        resolved["grid_type"] = resolve_io_type(resolved["grid"], explicit_grid)
    else:
        resolved["grid_type"] = None
    if resolved["background"]:
        resolved["background_type"] = resolve_io_type(
            resolved["background"], explicit_bg
        )
    else:
        resolved["background_type"] = None
    if resolved["output"]:
        explicit_out = _optional_str(output_type, "output", "type")
        resolved["output_type"] = resolve_io_type(resolved["output"], explicit_out)
    else:
        resolved["output_type"] = None


def _resolve_args(
    module: Optional[str] = None,
    sta: Optional[str] = None,
    grid: Optional[str] = None,
    background: Optional[str] = None,
    reprocess: Any = None,
    effect_r: Optional[int] = None,
    near_num: Optional[int] = None,
    decrease: Optional[int] = None,
    half_r: Optional[int] = None,
    kriging_model: Optional[str] = None,
    kriging_sill: Optional[float] = None,
    kriging_range: Optional[float] = None,
    kriging_nugget: Optional[float] = None,
    r_list: Any = None,
    output: Optional[str] = None,
    sta_type: Optional[str] = None,
    grid_type: Optional[str] = None,
    background_type: Optional[str] = None,
    output_type: Optional[str] = None,
) -> Dict[str, Any]:
    """实际解析逻辑（假定当前 ``_INI_PATH`` 已指向目标 ini）。"""
    name = resolve_module(module)
    # 路径可选：grid / background 至少其一；相对路径相对包根展开
    grid_path = _optional_path(grid, "input", "grid")
    bg_path = _optional_path(background, "input", "background")
    do_reprocess = _pick_bool(
        reprocess, "cli", "reprocess", bool(PRESET["reprocess"])
    )
    if name == "idw_delta":
        # 兼容模块：固定偏差路径，与 --reprocess true 相同，且须 background
        do_reprocess = True
    if not grid_path and not bg_path:
        raise ValueError(
            "须提供 grid 或 background。"
            "请传对应命令行参数，或在 resource/conf.ini 的 [input] 中填写"
        )
    if do_reprocess and not bg_path:
        raise ValueError(
            "reprocess=true（含 idw_delta）时必须提供 background。"
            "请传 --background，或在 resource/conf.ini 的 [input] 中填写 background"
        )

    resolved: Dict[str, Any] = {
        "module": name,
        "sta": _require("sta", sta, "input", "sta"),
        "grid": grid_path,
        "background": bg_path,
        "reprocess": do_reprocess,
    }
    # 补齐 sta/grid/background/output 的读写格式（显式 > ini > 扩展名）
    _attach_io_types(
        resolved,
        sta_type=sta_type,
        grid_type=grid_type,
        background_type=background_type,
        output=output,
        output_type=output_type,
    )

    # ---- 按 module 只填充该算法用到的参数，避免无关键干扰 CLI ----
    if name == "gaussian":
        resolved["half_r"] = _pick_int(half_r, "gaussian", "half_r", int(PRESET["half_r"]))
        if resolved["half_r"] <= 0:
            raise ValueError("half_r 必须大于 0")
        return resolved

    if name == "kriging":
        # sill/range 可为 None → 插件按站点方差/邻站距离自动估计
        model = (
            kriging_model.strip()
            if not _missing(kriging_model)
            else (_raw("kriging", "model") or str(PRESET["kriging_model"]))
        )
        if model not in _KRIGING_MODELS:
            raise ValueError("kriging model 仅支持 spherical / exponential / gaussian")
        resolved["kriging_model"] = model
        resolved["near_num"] = _pick_int(
            near_num, "kriging", "near_num", int(PRESET["kriging_near_num"])
        )
        resolved["kriging_sill"] = _optional_float(kriging_sill, "kriging", "sill")
        resolved["kriging_range"] = _optional_float(kriging_range, "kriging", "range")
        resolved["kriging_nugget"] = _pick_float(
            kriging_nugget, "kriging", "nugget", float(PRESET["kriging_nugget"])
        )
        if resolved["near_num"] < 1:
            raise ValueError("near_num 必须大于等于 1")
        if resolved["kriging_nugget"] < 0:
            raise ValueError("kriging_nugget 不能为负")
        if resolved["kriging_range"] is not None and resolved["kriging_range"] <= 0:
            raise ValueError("kriging_range 必须大于 0")
        if resolved["kriging_sill"] is not None and resolved["kriging_sill"] <= 0:
            raise ValueError("kriging_sill 必须大于 0")
        return resolved

    if name == "cressman":
        # r_list：False 路径为米；True（创新量）为度——单位由插件按 reprocess 解释
        resolved["r_list"] = _pick_r_list(
            r_list, "cressman", "r_list", list(PRESET["cressman_r_list"])
        )
        resolved["near_num"] = _pick_int(
            near_num, "cressman", "near_num", int(PRESET["cressman_near_num"])
        )
        if any(r <= 0 for r in resolved["r_list"]):
            raise ValueError("r_list 中半径必须大于 0")
        if resolved["near_num"] < 1:
            raise ValueError("near_num 必须大于等于 1")
        return resolved

    # idw / idw_delta：共用 effect_r / near_num / decrease（节名与 module 同名）
    resolved["effect_r"] = _pick_int(effect_r, name, "effect_r", int(PRESET["effect_r"]))
    resolved["near_num"] = _pick_int(near_num, name, "near_num", int(PRESET["near_num"]))
    resolved["decrease"] = _pick_int(decrease, name, "decrease", int(PRESET["decrease"]))
    if resolved["effect_r"] <= 0:
        raise ValueError("effect_r 必须大于 0")
    if resolved["near_num"] < 1:
        raise ValueError("near_num 必须大于等于 1")
    return resolved
