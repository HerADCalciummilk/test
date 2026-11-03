# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取三条 CLI 的运行参数。

取值优先级由调用方保证：显式参数 > 本 ini 非空项 > ``PRESET``。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

PRESET: Dict[str, Dict[str, Any]] = {
    "noise": {
        "mode": "generate",
        "output_dir": "resource/output/noise",
        "issue_time": "",
        "n_levels": 6,
        "phi1": 0.9,
        "phi2": -0.15,
        "n_ens_members": 5,
        "timesteps": 18,
    },
    "climatological_skill": {
        "input_dir": "",
        "output": "resource/output/climatological_skill.npy",
    },
    "blending": {
        "nowcast": "",
        "nwp": "",
        "output": "resource/output/blended.npy",
        "lead_index": 1,
        "n_cascade_levels": 8,
        "tau_min": 90.0,
        "clim_skill": "",
    },
}


def get_package_root() -> Path:
    """本包根目录（``steps_multi_time_fusion/``）。"""
    return _PKG_ROOT


def clear_ini_cache() -> None:
    """测试用：清空 ini 缓存。"""
    global _CACHE
    _CACHE = None


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按本包目录解析。文件不存在时抛出 ``FileNotFoundError``。
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


def _expand(path: str) -> str:
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    return str((_PKG_ROOT / expanded).resolve())


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _opt_str(section: str, key: str, preset: str, *, path: bool) -> str:
    raw = _raw(section, key)
    value = preset if raw is None else raw
    if path and value:
        return _expand(value)
    return value


def _opt_int(section: str, key: str, preset: int) -> int:
    raw = _raw(section, key)
    return preset if raw is None else int(raw)


def _opt_float(section: str, key: str, preset: float) -> float:
    raw = _raw(section, key)
    return preset if raw is None else float(raw)


def _pick_str(explicit: Optional[str], fallback: str) -> str:
    """显式字符串原样保留；缺省时用已经展开过的 ini/预设值。"""
    if not _missing(explicit):
        return str(explicit).strip()
    return fallback


_MODULE_ALIASES = {"skill": "climatological_skill"}
_MODULES = ("noise", "climatological_skill", "blending")


def resolve_module(module: Optional[str] = None, config: Optional[str] = None) -> str:
    """选择要运行的模块。显式参数优先，否则读 ``[cli] module``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_module(module)
    finally:
        if config:
            set_main_ini(None)


def _resolve_module(module: Optional[str] = None) -> str:
    if _missing(module):
        module = _raw("cli", "module") or ""
    name = _MODULE_ALIASES.get(str(module).strip(), str(module).strip())
    if name not in _MODULES:
        raise ValueError(
            "module 未指定或无效。请传 --module，"
            "可选 noise、climatological_skill（或 skill）、blending"
        )
    return name


def _require(name: str, section: str, value: str) -> str:
    if value:
        return value
    raise ValueError(
        f"{name} 未显式传入，且 resource/conf.ini 的 [{section}] {name} 为空"
    )


def resolve_noise(
    mode: Optional[str] = None,
    output_dir: Optional[str] = None,
    issue_time: Optional[str] = None,
    n_levels: Optional[int] = None,
    phi1: Optional[float] = None,
    phi2: Optional[float] = None,
    n_ens_members: Optional[int] = None,
    timesteps: Optional[int] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐噪声 CLI 参数。``issue_time`` 为空时抛出 ``ValueError``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_noise(
            mode=mode,
            output_dir=output_dir,
            issue_time=issue_time,
            n_levels=n_levels,
            phi1=phi1,
            phi2=phi2,
            n_ens_members=n_ens_members,
            timesteps=timesteps,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_noise(
    mode: Optional[str] = None,
    output_dir: Optional[str] = None,
    issue_time: Optional[str] = None,
    n_levels: Optional[int] = None,
    phi1: Optional[float] = None,
    phi2: Optional[float] = None,
    n_ens_members: Optional[int] = None,
    timesteps: Optional[int] = None,
) -> Dict[str, Any]:
    preset = PRESET["noise"]
    resolved_mode = _pick_str(mode, _opt_str("noise", "mode", str(preset["mode"]), path=False))
    if resolved_mode != "generate":
        raise ValueError("mode 只支持 generate")
    output = _pick_str(
        output_dir,
        _opt_str("noise", "output_dir", str(preset["output_dir"]), path=True),
    )
    issue = _pick_str(
        issue_time,
        _opt_str("noise", "issue_time", str(preset["issue_time"]), path=False),
    )
    return {
        "mode": resolved_mode,
        "output_dir": output,
        "issue_time": _require("issue_time", "noise", issue),
        "n_levels": int(_opt_int("noise", "n_levels", int(preset["n_levels"])) if n_levels is None else n_levels),
        "phi1": float(_opt_float("noise", "phi1", float(preset["phi1"])) if phi1 is None else phi1),
        "phi2": float(_opt_float("noise", "phi2", float(preset["phi2"])) if phi2 is None else phi2),
        "n_ens_members": int(
            _opt_int("noise", "n_ens_members", int(preset["n_ens_members"]))
            if n_ens_members is None
            else n_ens_members
        ),
        "timesteps": int(
            _opt_int("noise", "timesteps", int(preset["timesteps"])) if timesteps is None else timesteps
        ),
    }


def resolve_climatological_skill(
    input_dir: Optional[str] = None,
    output: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, str]:
    """补齐气候态 skill CLI 参数。``input_dir`` 为空时抛出 ``ValueError``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_climatological_skill(input_dir=input_dir, output=output)
    finally:
        if config:
            set_main_ini(None)


def _resolve_climatological_skill(
    input_dir: Optional[str] = None,
    output: Optional[str] = None,
) -> Dict[str, str]:
    preset = PRESET["climatological_skill"]
    directory = _pick_str(
        input_dir,
        _opt_str("climatological_skill", "input_dir", str(preset["input_dir"]), path=True),
    )
    out = _pick_str(
        output,
        _opt_str("climatological_skill", "output", str(preset["output"]), path=True),
    )
    return {
        "input_dir": _require("input_dir", "climatological_skill", directory),
        "output": out,
    }


def resolve_blending(
    nowcast: Optional[str] = None,
    nwp: Optional[str] = None,
    output: Optional[str] = None,
    lead_index: Optional[int] = None,
    n_cascade_levels: Optional[int] = None,
    tau_min: Optional[float] = None,
    clim_skill: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐融合 CLI 参数。``nowcast`` / ``nwp`` 为空时抛出 ``ValueError``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_blending(
            nowcast=nowcast,
            nwp=nwp,
            output=output,
            lead_index=lead_index,
            n_cascade_levels=n_cascade_levels,
            tau_min=tau_min,
            clim_skill=clim_skill,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_blending(
    nowcast: Optional[str] = None,
    nwp: Optional[str] = None,
    output: Optional[str] = None,
    lead_index: Optional[int] = None,
    n_cascade_levels: Optional[int] = None,
    tau_min: Optional[float] = None,
    clim_skill: Optional[str] = None,
) -> Dict[str, Any]:
    preset = PRESET["blending"]
    nowcast_path = _pick_str(
        nowcast,
        _opt_str("blending", "nowcast", str(preset["nowcast"]), path=True),
    )
    nwp_path = _pick_str(
        nwp,
        _opt_str("blending", "nwp", str(preset["nwp"]), path=True),
    )
    out = _pick_str(
        output,
        _opt_str("blending", "output", str(preset["output"]), path=True),
    )
    if _missing(clim_skill):
        clim = _opt_str("blending", "clim_skill", str(preset["clim_skill"]), path=True)
        clim_skill_path = clim or None
    else:
        clim_skill_path = str(clim_skill).strip()
    return {
        "nowcast": _require("nowcast", "blending", nowcast_path),
        "nwp": _require("nwp", "blending", nwp_path),
        "output": out,
        "lead_index": int(
            _opt_int("blending", "lead_index", int(preset["lead_index"]))
            if lead_index is None
            else lead_index
        ),
        "n_cascade_levels": int(
            _opt_int("blending", "n_cascade_levels", int(preset["n_cascade_levels"]))
            if n_cascade_levels is None
            else n_cascade_levels
        ),
        "tau_min": float(
            _opt_float("blending", "tau_min", float(preset["tau_min"])) if tau_min is None else tau_min
        ),
        "clim_skill": clim_skill_path,
    }
